"""Escolha do navegador da automação: o primeiro disponível na ordem Chrome > Chromium > Firefox > Edge.

* Chrome e Edge: os instalados pelos pacotes oficiais (Playwright, canais "chrome" e "msedge", que procuram em
  /opt/google/chrome e /opt/microsoft/msedge).
* Chromium: o da distribuição (``chromium`` no PATH, inclusive o snap do Ubuntu), aberto pelo caminho do executável.
* Firefox: o instalado no computador, pelo canal "moz-firefox" (WebDriver BiDi, ainda experimental no Playwright).

Cada navegador tem a sua pasta de perfil (os formatos não são compatíveis); o Chrome mantém a pasta original,
com os cookies da verificação da Cloudflare. Navegadores em snap só enxergam pastas não ocultas da home, então,
quando o snap existe, o perfil deles fica em ~/snap/<nome>/common.
"""
from __future__ import annotations

import logging
import shutil
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
    platforms: tuple = ("linux",)
    executables: tuple = ()          # nomes ou caminhos procurados quando não há canal do Playwright
    snap: Optional[str] = None       # nome do pacote snap, quando o navegador pode vir por snap

    def executable(self) -> Optional[str]:
        return next(filter(None, map(shutil.which, self.executables)), None)

    @property
    def launch_args(self) -> dict:
        kw: dict = {"channel": self.channel} if self.channel else {}
        exe = self.executable()
        if exe:
            kw["executable_path"] = exe
        if self.engine == "chromium":
            kw["args"] = ["--disable-features=Translate"]
        return kw


BROWSERS = (
    BrowserChoice("chrome", "Google Chrome", "chromium", "chrome"),
    BrowserChoice("chromium", "Chromium", "chromium", None,
                  executables=("chromium", "/snap/bin/chromium", "chromium-browser"), snap="chromium"),
    BrowserChoice("firefox", "Mozilla Firefox", "firefox", "moz-firefox", snap="firefox"),
    BrowserChoice("edge", "Microsoft Edge", "chromium", "msedge"),
)
NONE_FOUND = ("Nenhum navegador compatível foi encontrado. Instale o Google Chrome (recomendado), o Chromium, o "
              "Mozilla Firefox ou o Microsoft Edge e tente novamente.")
SNAP_BIN = Path("/snap/bin")


def candidates(platform: Optional[str] = None) -> list[BrowserChoice]:
    platform = platform or sys.platform
    return [b for b in BROWSERS if platform in b.platforms]


def profile_dir(base: Path, choice: BrowserChoice) -> Path:
    if choice.snap and (SNAP_BIN / choice.snap).exists():
        return Path.home() / "snap" / choice.snap / "common" / "unispace-profile"
    return base if choice.key == "chrome" else base.with_name(f"browser-profile-{choice.key}")


def first_available(open_with: Callable[[BrowserChoice], object], platform: Optional[str] = None):
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
