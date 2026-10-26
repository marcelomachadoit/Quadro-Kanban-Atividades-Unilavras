"""Automação do portal Unilavras + Sala de Aula Virtual (Plataforma A) com Playwright.

Somente leitura: a automação apenas navega e lê o conteúdo que as próprias páginas carregam.
Nenhum formulário de resposta é preenchido e nenhum botão de envio é acionado.
"""
from __future__ import annotations

import logging
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlsplit

from playwright.sync_api import Error as PWError
from playwright.sync_api import Page, Response, TimeoutError as PWTimeout, sync_playwright

from app.config import (ACTION_TIMEOUT_MS, MANUAL_AUTH_TIMEOUT_S, MAX_RETRIES, NAV_TIMEOUT_MS, POLITE_DELAY_MS,
                        PORTAL_LOGIN_URL)
from app.models.activity import Course
from app.services.credentials import Credentials
from app.services.logging_setup import register_secret

log = logging.getLogger(__name__)

COURSES_API = re.compile(r"/plataforma/academic/courses/me\?")
CONTENTS_API = re.compile(r"/plataforma/content/academics-main/(\d+)/contents")


class AutomationError(RuntimeError):
    """Erro com mensagem compreensível para o usuário."""


class LoginFailed(AutomationError):
    pass


class HumanVerificationRequired(AutomationError):
    """O portal exigiu verificação humana (ex.: Cloudflare Turnstile). Não é erro de credenciais."""


class SessionExpired(AutomationError):
    pass


VERIFICATION_RE = re.compile(r"verifica[cç][aã]o de seguran[cç]a|captcha|turnstile", re.I)
VERIFICATION_GUIDE = (
    "O portal está exigindo uma verificação de segurança (Cloudflare), o que costuma acontecer depois de várias "
    "tentativas de login seguidas. Suas credenciais NÃO foram recusadas.\n\n"
    "Como liberar: abra o portal no seu navegador habitual (botão \"Abrir portal no navegador\" em Configurações), "
    "entre normalmente e conclua a verificação. Depois aguarde alguns minutos e clique em \"Atualizar dados\" "
    "novamente. Evite várias tentativas seguidas enquanto isso.")


class StructureChanged(AutomationError):
    pass


class Cancelled(AutomationError):
    pass


class BrowserUnavailable(AutomationError):
    pass


@dataclass
class PortalLabels:
    """Rótulos usados para localizar elementos (editáveis nas configurações caso o portal mude)."""
    classroom_tile: str = "Sala de Aula Virtual"
    courses_menu: str = "Disciplinas"


ProgressFn = Callable[[str], None]


def _is_transient(e: Exception) -> bool:
    msg = str(e)
    return isinstance(e, PWTimeout) or any(s in msg for s in (
        "net::ERR_", "NS_ERROR", "Navigation failed", "ECONNRESET", "Target page, context or browser has been closed"
    ))


class PortalClient:
    def __init__(self, profile_dir: Path, headless: bool = False, labels: Optional[PortalLabels] = None,
                 cancel: Optional[threading.Event] = None, on_step: Optional[ProgressFn] = None,
                 on_manual: Optional[ProgressFn] = None):
        self.profile_dir = Path(profile_dir)
        self.headless = headless
        self.labels = labels or PortalLabels()
        self.cancel = cancel or threading.Event()
        self.on_step = on_step or (lambda s: None)
        self.on_manual = on_manual or (lambda s: None)
        self._pw = None
        self._ctx = None
        self.portal: Optional[Page] = None
        self.lxp: Optional[Page] = None
        self.lxp_base: str = ""
        self._creds: Optional[Credentials] = None

    # ---------------------------------------------------------------- ciclo de vida
    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self.close()

    def start(self) -> None:
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self._pw = sync_playwright().start()
        try:
            self._ctx = self._pw.chromium.launch_persistent_context(
                str(self.profile_dir), channel="chrome", headless=self.headless,
                locale="pt-BR", timezone_id="America/Sao_Paulo", viewport={"width": 1366, "height": 860},
                args=["--disable-features=Translate"],
            )
        except PWError as e:
            self._pw.stop()
            self._pw = None
            raise BrowserUnavailable(
                "Não foi possível iniciar o Google Chrome. Verifique se ele está instalado e fechado em outras "
                "automações. Detalhe técnico: " + str(e).splitlines()[0]) from e
        self._ctx.set_default_timeout(ACTION_TIMEOUT_MS)
        self._ctx.set_default_navigation_timeout(NAV_TIMEOUT_MS)
        self.portal = self._ctx.pages[0] if self._ctx.pages else self._ctx.new_page()

    def close(self) -> None:
        for obj in (self._ctx, self._pw):
            try:
                if obj is self._ctx and obj:
                    obj.close()
                elif obj:
                    obj.stop()
            except Exception:
                pass
        self._ctx = self._pw = None

    def check_cancel(self) -> None:
        if self.cancel.is_set():
            raise Cancelled("Atualização interrompida pelo usuário.")

    def _wait(self, page: Page, ms: int) -> None:
        """Pausa curta que mantém o Playwright processando eventos e respeita o cancelamento."""
        step = 250
        for _ in range(max(1, ms // step)):
            self.check_cancel()
            page.wait_for_timeout(step)

    def _retry(self, what: str, fn):
        last = None
        for attempt in range(1, MAX_RETRIES + 1):
            self.check_cancel()
            try:
                return fn()
            except (Cancelled, LoginFailed, StructureChanged, SessionExpired, HumanVerificationRequired):
                raise
            except Exception as e:  # noqa: BLE001
                if not _is_transient(e):
                    raise
                last = e
                log.warning("%s: falha temporária (tentativa %s/%s): %s", what, attempt, MAX_RETRIES,
                            str(e).splitlines()[0])
                if self.portal:
                    self._wait(self.portal, 1500 * attempt)
        raise AutomationError(f"{what}: o portal não respondeu após {MAX_RETRIES} tentativas. "
                              "Verifique sua conexão com a internet.") from last

    # ---------------------------------------------------------------- etapa 1: login
    def login(self, creds: Credentials) -> None:
        # O portal guarda a sessão em sessionStorage: cada navegador novo começa deslogado, então não há
        # sessão anterior a reaproveitar. Os cookies do perfil são mantidos de propósito (inclusive os da
        # verificação da Cloudflare) — apagá-los aumenta a chance de o portal exigir verificação humana.
        self._creds = creds
        register_secret(creds.password)
        self.on_step("Abrindo o portal do aluno")
        p = self.portal
        self._retry("Abrir o portal", lambda: p.goto(PORTAL_LOGIN_URL, wait_until="domcontentloaded"))
        if urlsplit(p.url).path.startswith("/portal"):
            log.info("Sessão do portal já estava ativa.")
            return
        self.on_step("Efetuando login")
        user = p.locator("#username").or_(p.get_by_label(re.compile("usu[aá]rio", re.I))).first
        pwd = p.locator("#password").or_(p.get_by_label(re.compile("senha", re.I))).first
        try:
            user.wait_for(state="visible", timeout=NAV_TIMEOUT_MS)
        except PWTimeout as e:
            raise StructureChanged("A tela de login do portal não exibiu os campos de usuário e senha.") from e
        user.fill(creds.username)
        pwd.fill(creds.password)
        p.get_by_role("button", name=re.compile(r"^\s*Acessar\s*$", re.I)).click()

        outcome = self._wait_login_outcome(p, 40)
        if outcome == "ok":
            log.info("Login efetuado com sucesso.")
            return
        if outcome == "bloqueado":
            log.warning("O portal exigiu verificação humana (Cloudflare Turnstile) e ela não pode ser concluída "
                        "no navegador da automação.")
            raise HumanVerificationRequired(VERIFICATION_GUIDE)
        if outcome.startswith("erro:"):
            raise LoginFailed("O portal recusou o login: " + outcome[5:] +
                              "\nConfira o usuário e a senha em Configurações. Se tiver certeza de que estão "
                              "corretos, o portal pode estar exigindo verificação por excesso de tentativas: entre "
                              "uma vez pelo seu navegador habitual e tente novamente em alguns minutos.")
        # verificação interativa, 2FA ou Microsoft 365 — pausa para ação humana
        self._await_manual("Conclua a verificação na janela do Chrome (CAPTCHA, verificação em duas etapas "
                           "ou Microsoft 365). A atualização continuará automaticamente.")

    def _wait_logged_in(self, p: Page, seconds: int) -> bool:
        for _ in range(seconds * 4):
            self.check_cancel()
            if urlsplit(p.url).path.startswith("/portal"):
                return True
            if self._verification_blocked(p):
                raise HumanVerificationRequired(VERIFICATION_GUIDE)
            p.wait_for_timeout(250)
        return False

    def _wait_login_outcome(self, p: Page, seconds: int) -> str:
        """Resultados: "ok", "bloqueado" (verificação impossível aqui), "manual" (ação humana) ou "erro:<texto>"."""
        err = p.locator("mat-error, .mat-mdc-snack-bar-label, .mat-mdc-simple-snack-bar, [role=alert], .toast-message, "
                        ".mat-mdc-form-field-error")
        verification_since = None
        for i in range(seconds * 4):
            self.check_cancel()
            if urlsplit(p.url).path.startswith("/portal"):
                return "ok"
            if self._verification_blocked(p):
                return "bloqueado"
            try:
                txt = " ".join(t.strip() for t in err.all_inner_texts() if t.strip()) if err.count() else ""
            except PWError:
                txt = ""
            if txt and VERIFICATION_RE.search(txt):
                # o portal pede a verificação e em seguida carrega o widget: aguarda para ver se é interativo
                verification_since = verification_since if verification_since is not None else i
            elif txt:
                return "erro:" + txt[:200]
            if "login.microsoftonline.com" in p.url:
                return "manual"
            if verification_since is not None and i - verification_since > 12 * 4:
                return "manual"
            p.wait_for_timeout(250)
        return "manual" if (verification_since is not None or not self.headless) else \
            "erro:o portal não confirmou a autenticação"

    @staticmethod
    def _verification_blocked(p: Page) -> bool:
        """O widget do portal informa que a verificação não pode ser concluída neste navegador."""
        try:
            return p.locator(".turnstile-help").filter(has_text=re.compile("n[aã]o foi poss[ií]vel", re.I)) \
                .first.is_visible()
        except PWError:
            return False

    def _await_manual(self, msg: str) -> None:
        if self.headless:
            raise HumanVerificationRequired(
                "O portal pediu uma verificação manual (CAPTCHA ou verificação em duas etapas). Ative a opção "
                "\"Mostrar a janela do Chrome durante a atualização\" em Configurações e tente novamente.")
        self.on_manual(msg)
        log.info("Aguardando autenticação manual do usuário no navegador.")
        if not self._wait_logged_in(self.portal, MANUAL_AUTH_TIMEOUT_S):
            raise HumanVerificationRequired("A verificação não foi concluída a tempo. Tente novamente.")
        self.on_manual("")

    # ---------------------------------------------------------------- etapa 2: sala de aula virtual
    def open_classroom(self) -> None:
        self.check_cancel()
        self.on_step("Acessando a Sala de Aula Virtual")
        p = self.portal
        if not urlsplit(p.url).path.startswith("/portal"):
            self._retry("Abrir o portal", lambda: p.goto("https://novoportal.unilavras.edu.br/portal"))
            if not self._wait_logged_in(p, 10):
                raise SessionExpired("A sessão do portal expirou.")
        label = self.labels.classroom_tile
        tile = p.locator("button.platform-link, app-tile button, button, a").filter(
            has=p.locator(".title", has_text=re.compile(rf"^\s*{re.escape(label)}\s*$", re.I)))
        try:
            tile.first.wait_for(state="visible", timeout=NAV_TIMEOUT_MS)
        except PWTimeout:
            tile = p.get_by_role("button", name=re.compile(rf"^\W*\w*\s*{re.escape(label)}\s*$", re.I))
            if not tile.count():
                options = self._tile_titles(p)
                raise StructureChanged(
                    f"Não encontrei a opção \"{label}\" no portal. Opções disponíveis: {', '.join(options) or 'nenhuma'}. "
                    "Se o nome mudou, ajuste-o em Configurações > Avançado.")
        if self.lxp and not self.lxp.is_closed():
            self.lxp.close()
        with self._ctx.expect_page(timeout=NAV_TIMEOUT_MS) as newp:
            tile.first.click()
        self.lxp = newp.value
        self._wait_lxp_ready()
        s = urlsplit(self.lxp.url)
        self.lxp_base = f"{s.scheme}://{s.netloc}"
        log.info("Sala de Aula Virtual aberta em %s", self.lxp_base)

    def _tile_titles(self, p: Page) -> list[str]:
        try:
            return [t.strip() for t in p.locator("app-tile .title, button.platform-link .title").all_inner_texts()][:30]
        except PWError:
            return []

    def _wait_lxp_ready(self) -> None:
        menu = self.lxp.get_by_role("link", name=re.compile(rf"^\s*{re.escape(self.labels.courses_menu)}\s*$", re.I))
        try:
            menu.first.wait_for(state="visible", timeout=90_000)   # a plataforma pode demorar a carregar
        except PWTimeout as e:
            if re.search(r"login|signin|sessions", self.lxp.url, re.I):
                raise SessionExpired("A Sala de Aula Virtual pediu nova autenticação.") from e
            raise StructureChanged(
                f"A Sala de Aula Virtual abriu, mas o menu \"{self.labels.courses_menu}\" não apareceu. "
                "Se o nome mudou, ajuste-o em Configurações > Avançado.") from e

    # ---------------------------------------------------------------- etapa 3: disciplinas
    def list_courses(self) -> list[dict]:
        """Abre "Disciplinas" e retorna as respostas JSON de cada página da lista."""
        self.check_cancel()
        self.on_step("Abrindo a lista de disciplinas")
        lx = self.lxp
        menu = lx.get_by_role("link", name=re.compile(rf"^\s*{re.escape(self.labels.courses_menu)}\s*$", re.I)).first

        def go():
            with lx.expect_response(lambda r: bool(COURSES_API.search(r.url)) and r.request.method == "GET",
                                    timeout=NAV_TIMEOUT_MS) as resp:
                menu.click()
            return self._json(resp.value)

        pages = [self._retry("Carregar disciplinas", go)]
        guard = 0
        while pages[-1].get("nextPage") and guard < 20:
            guard += 1
            self._wait(lx, POLITE_DELAY_MS)
            nxt = lx.locator("button[aria-label*='róxima' i], button[aria-label*='next' i], "
                             ".pagination-next, li.next button").first
            if not nxt.count() or nxt.is_disabled():
                log.warning("Há mais páginas de disciplinas, mas o botão de próxima página não foi encontrado.")
                break
            with lx.expect_response(lambda r: bool(COURSES_API.search(r.url)), timeout=NAV_TIMEOUT_MS) as resp:
                nxt.click()
            pages.append(self._json(resp.value))
        return pages

    def course_cards_text(self) -> list[tuple[str, str, Optional[str]]]:
        """Alternativa pelo DOM: (nome, texto do cartão, href) de cada disciplina exibida."""
        js = """() => Array.from(document.querySelectorAll('a[href*="/plataforma/course/"]'))
            .filter(a => !a.href.includes('openNotices'))
            .map(a => { const card = a.closest('[class*=card], li, article') || a;
                        return [ (a.innerText||'').split('\\n')[0], card.innerText || '', a.getAttribute('href') ]; })"""
        try:
            return self.lxp.evaluate(js)
        except PWError:
            return []

    # ---------------------------------------------------------------- etapa 4: conteúdo da disciplina
    def course_contents(self, course: Course) -> dict:
        self.check_cancel()
        lx = self.lxp
        url = f"{self.lxp_base}/plataforma/course/{course.source_id}"

        def go():
            with lx.expect_response(
                    lambda r: bool(CONTENTS_API.search(r.url)) and CONTENTS_API.search(r.url).group(1) == str(course.source_id),
                    timeout=NAV_TIMEOUT_MS) as resp:
                lx.goto(url, wait_until="domcontentloaded")
            return self._json(resp.value)

        data = self._retry(f"Abrir a disciplina {course.name}", go)
        self._wait(lx, POLITE_DELAY_MS)
        return data

    def back_to_courses(self) -> None:
        try:
            self.lxp.get_by_role("link", name=re.compile(rf"^\s*{re.escape(self.labels.courses_menu)}\s*$", re.I)).first.click()
        except PWError:
            pass

    # ---------------------------------------------------------------- util
    def _json(self, resp: Response) -> dict:
        if resp.status in (401, 403):
            raise SessionExpired("A sessão da Sala de Aula Virtual expirou.")
        if resp.status >= 500:
            raise PWError(f"net::ERR_HTTP_{resp.status}")
        if resp.status >= 400:
            raise StructureChanged(f"O portal respondeu com erro {resp.status} ao carregar dados.")
        try:
            return resp.json()
        except Exception as e:  # noqa: BLE001
            raise StructureChanged("O portal retornou dados em um formato inesperado.") from e

    def save_diagnostic(self, folder: Path, tag: str) -> Optional[Path]:
        """Captura de tela para diagnóstico (sem campos preenchidos). Não salva cookies nem HTML com dados."""
        try:
            folder.mkdir(parents=True, exist_ok=True)
            page = self.lxp if self.lxp and not self.lxp.is_closed() else self.portal
            path = folder / f"{tag}.png"
            page.screenshot(path=str(path))
            return path
        except Exception:  # noqa: BLE001
            return None
