"""Escolha do navegador da automação: o primeiro disponível na ordem Chrome > Safari > Firefox > Edge.

* Chrome e Edge: os instalados no computador (Playwright, canais "chrome" e "msedge").
* Safari: só no macOS. O Playwright não controla o aplicativo Safari; usa o WebKit, o mesmo motor do Safari,
  que precisa acompanhar o aplicativo (``playwright install webkit``). Sem ele, a opção é pulada.
* Firefox: o instalado no computador, pelo canal "moz-firefox" (WebDriver BiDi, ainda experimental no Playwright).

Cada navegador tem a sua pasta de perfil (os formatos não são compatíveis); o Chrome mantém a pasta original,
com os cookies da verificação da Cloudflare.
"""
from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from playwright.sync_api import Error as PWError

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class BrowserChoice:
    key: str
    label: str
    engine: str                      # atributo do Playwright: "chromium" | "webkit" | "firefox"
    channel: Optional[str]
    platforms: tuple = ("win32", "darwin", "linux")

    @property
    def launch_args(self) -> dict:
        kw: dict = {"channel": self.channel} if self.channel else {}
        if self.engine == "chromium":
            kw["args"] = ["--disable-features=Translate"]
        return kw


BROWSERS = (
    BrowserChoice("chrome", "Google Chrome", "chromium", "chrome"),
    BrowserChoice("safari", "Safari", "webkit", None, platforms=("darwin",)),
    BrowserChoice("firefox", "Mozilla Firefox", "firefox", "moz-firefox"),
    BrowserChoice("edge", "Microsoft Edge", "chromium", "msedge"),
)
NONE_FOUND = ("Nenhum navegador compatível foi encontrado. Instale o Google Chrome, o Mozilla Firefox ou o "
              "Microsoft Edge e tente novamente.")


def candidates(platform: str = sys.platform) -> list[BrowserChoice]:
    return [b for b in BROWSERS if platform in b.platforms]


def profile_dir(base: Path, choice: BrowserChoice) -> Path:
    return base if choice.key == "chrome" else base.with_name(f"browser-profile-{choice.key}")


def first_available(open_with: Callable[[BrowserChoice], object], platform: str = sys.platform):
    """Tenta ``open_with(navegador)`` na ordem de preferência e retorna ``(resultado, navegador)``.
    Levanta ``LookupError`` com o motivo de cada falha quando nenhum abre."""
    failures = []
    for choice in candidates(platform):
        try:
            result = open_with(choice)
        except PWError as e:
            reason = str(e).strip().splitlines()[0] if str(e).strip() else type(e).__name__
            failures.append(f"{choice.label}: {reason}")
            log.info("%s indisponível (%s); tentando o próximo navegador.", choice.label, reason)
            continue
        log.info("Navegador da automação: %s", choice.label)
        return result, choice
    raise LookupError("; ".join(failures))
