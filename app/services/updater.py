"""Orquestra a atualização completa: login -> sala virtual -> disciplinas -> atividades -> banco."""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Optional

from app.automation import parser as P
from app.automation.meetings_parser import extract_meetings
from app.automation.portal import (AutomationError, Cancelled, HumanVerificationRequired, LoginFailed, PortalClient,
                                   PortalLabels,
                                   SessionExpired, StructureChanged)
from app.config import BROWSER_PROFILE_DIR, DIAG_DIR, TZ
from app.database.db import Database
from app.models.activity import Course, dt_to_iso
from app.services import rules as R
from app.services.credentials import Credentials
from app.services.sync import SyncReport, SyncService

log = logging.getLogger(__name__)


@dataclass
class Progress:
    step: str = ""
    course: str = ""
    courses_done: int = 0
    courses_total: int = 0
    activities_found: int = 0
    manual_message: str = ""


def save_courses_info(db: Database, courses: list[Course]) -> None:
    """Guarda início e progresso de todas as disciplinas (usado pelo calendário e pela regra de módulos)."""
    for co in courses:
        if co.source_id:
            db.save_course_info(co.source_id, co.name, co.start_date, co.progress)


def save_course_meetings(db: Database, co: Course, contents: dict) -> None:
    db.save_course_info(co.source_id, co.name, co.start_date, co.progress,
                        [vars(m) for m in extract_meetings(contents, co.start_date)])


def load_courses(c: PortalClient) -> list[Course]:
    """Lista as disciplinas da Sala de Aula Virtual (dados da página, com leitura da tela como alternativa)."""
    courses: list[Course] = []
    try:
        for page in c.list_courses():
            cs, _ = P.parse_courses_json(page)
            courses.extend(cs)
    except StructureChanged as e:
        log.warning("Lista de disciplinas via dados da página falhou (%s); tentando leitura da tela.", e)
    if not courses:
        for name, text, href in c.course_cards_text():
            co = P.parse_course_card_text(name, text)
            if href and "/plataforma/course/" in href:
                co.source_id = href.rstrip("/").split("/")[-1].split("?")[0]
            courses.append(co)
    if not courses:
        raise StructureChanged("Nenhuma disciplina foi encontrada na Sala de Aula Virtual. "
                               "A estrutura do portal pode ter mudado; seus dados locais foram preservados.")
    log.info("Disciplinas encontradas: %s", len(courses))
    return courses


class Updater:
    """Executa a atualização. Deve rodar fora da thread da interface."""

    def __init__(self, db: Database, creds: Credentials, headless: bool = False,
                 labels: Optional[PortalLabels] = None, cancel: Optional[threading.Event] = None,
                 on_progress: Optional[Callable[[Progress], None]] = None,
                 client_factory: Optional[Callable[..., PortalClient]] = None):
        self.db = db
        self.creds = creds
        self.headless = headless
        self.labels = labels or PortalLabels()
        self.cancel = cancel or threading.Event()
        self.on_progress = on_progress or (lambda p: None)
        self.client_factory = client_factory or PortalClient
        self.progress = Progress()

    def _emit(self, **kw) -> None:
        for k, v in kw.items():
            setattr(self.progress, k, v)
        self.on_progress(Progress(**vars(self.progress)))

    def test_connection(self) -> None:
        """Somente autentica no portal (botão "Testar conexão")."""
        with self._client() as c:
            c.login(self.creds)
            self.db.set_meta("last_auth_success", dt_to_iso(datetime.now(TZ)))

    def _client(self) -> PortalClient:
        return self.client_factory(
            profile_dir=BROWSER_PROFILE_DIR, headless=self.headless, labels=self.labels, cancel=self.cancel,
            on_step=lambda s: self._emit(step=s),
            on_manual=lambda m: self._emit(manual_message=m))

    # ------------------------------------------------------------------
    def run(self, client: Optional[PortalClient] = None) -> SyncReport:
        """``client`` já autenticado permite reaproveitar a sessão (atualização semanal: um único login)."""
        report = SyncReport()
        sync = SyncService(self.db)
        run_id = self.db.start_run()
        outcome = "ok"
        try:
            if client is None:
                with self._client() as c:
                    self._emit(step="Validando credenciais")
                    c.login(self.creds)
                    self.db.set_meta("last_auth_success", dt_to_iso(datetime.now(TZ)))
                    self._session(c, sync, report)
            else:
                self._session(client, sync, report)
            self.db.set_meta("last_update", dt_to_iso(datetime.now(TZ)))
            self._emit(step="Atualização concluída", course="")
        except Cancelled:
            report.cancelled = True
            outcome = "cancelado"
            log.info("Atualização cancelada pelo usuário.")
        except AutomationError as e:
            report.errors.append(str(e))
            outcome = "erro"
            log.error("Atualização interrompida: %s", e)
        except Exception as e:  # noqa: BLE001 — nunca derrubar a aplicação; dados locais permanecem intactos
            report.errors.append("Erro inesperado durante a atualização. Os dados locais foram preservados. "
                                 f"Detalhe: {type(e).__name__}: {str(e).splitlines()[0] if str(e) else ''}")
            outcome = "erro"
            log.exception("Erro inesperado na atualização")
        finally:
            try:
                self.db.finish_run(run_id, outcome, report.as_dict())
            except Exception:  # noqa: BLE001
                log.exception("Falha ao registrar histórico da atualização")
        return report

    def _session(self, c: PortalClient, sync: SyncService, report: SyncReport) -> None:
        c.open_classroom()
        courses = self._load_courses(c, report)
        save_courses_info(self.db, courses)
        eligible = []
        for co in courses:
            elig = R.is_course_eligible(co.progress)
            if elig is None:
                report.courses_unknown.append(co.name)
                log.warning("Percentual de conclusão não interpretável: %s (%r)", co.name, co.progress_raw)
            elif elig:
                eligible.append(co)
            else:
                report.courses_skipped.append(f"{co.name} ({co.progress:g}%)")
        self._emit(step="Analisando disciplinas", courses_total=len(eligible), courses_done=0)
        for i, co in enumerate(eligible, 1):
            c.check_cancel()
            self._emit(step="Analisando atividades", course=co.name)
            self._process_course(c, co, sync, report)
            self._emit(courses_done=i, activities_found=report.found)

    def _load_courses(self, c: PortalClient, report: SyncReport) -> list[Course]:
        return load_courses(c)

    def _process_course(self, c: PortalClient, co: Course, sync: SyncService, report: SyncReport) -> None:
        if not co.source_id:
            report.courses_failed.append((co.name, "identificador da disciplina não encontrado"))
            return
        for attempt in (1, 2):
            try:
                data = c.course_contents(co)
                save_course_meetings(self.db, co, data)
                scan = P.parse_contents_json(data, co.name, co.source_id, c.lxp_base, co.start_date)
                acts = P.dedupe(scan.activities)
                # grava imediatamente: uma interrupção posterior não perde o que já foi coletado
                sync.apply(acts, [scan.activities[0].course if scan.activities else
                                  (data.get("context") or {}).get("academicMainName") or co.name], report=report)
                report.courses_processed.append(co.name)
                log.info("Disciplina processada: %s (%s atividades vigentes)", co.name, len(acts))
                return
            except SessionExpired:
                if attempt == 2:
                    raise
                log.info("Sessão expirada; autenticando novamente.")
                self._emit(step="Sessão expirada — autenticando novamente")
                c.login(self.creds)
                c.open_classroom()
            except (Cancelled, LoginFailed, HumanVerificationRequired):
                raise
            except AutomationError as e:
                report.courses_failed.append((co.name, str(e)))
                c.save_diagnostic(DIAG_DIR, f"falha-disciplina-{co.source_id}")
                log.warning("Falha na disciplina %s: %s", co.name, e)
                return
            except Exception as e:  # noqa: BLE001
                report.courses_failed.append((co.name, f"{type(e).__name__}"))
                log.exception("Erro ao processar disciplina %s", co.name)
                return
