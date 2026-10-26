"""Configurações globais e caminhos do aplicativo."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

APP_NAME = "UniKanban"
APP_TITLE = "UniKanban — Tarefas Unilavras"
APP_VERSION = "1.0.0"

TZ = ZoneInfo("America/Sao_Paulo")

PORTAL_LOGIN_URL = "https://novoportal.unilavras.edu.br/sessions/login"
PORTAL_HOST = "novoportal.unilavras.edu.br"

# Regras de negócio
COMPLETION_THRESHOLD = 95.0     # processar somente disciplinas com conclusão < 95%
SOON_HOURS = 48                 # "prazo próximo"
MISSING = "-"                   # valor usado para campos ausentes

# Limites da automação
NAV_TIMEOUT_MS = 45_000
ACTION_TIMEOUT_MS = 20_000
MAX_RETRIES = 3
MANUAL_AUTH_TIMEOUT_S = 300     # tempo para o usuário concluir CAPTCHA / 2FA no navegador
MAX_PAGES_PER_COURSE = 60       # trava de segurança contra loops de navegação
POLITE_DELAY_MS = 600           # pausa curta entre páginas para não sobrecarregar o portal


def _data_dir() -> Path:
    override = os.environ.get("UNIKANBAN_DATA_DIR")
    if override:
        return Path(override)
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / APP_NAME


DATA_DIR = _data_dir()
DB_PATH = DATA_DIR / "unikanban.db"
LOG_DIR = DATA_DIR / "logs"
BROWSER_PROFILE_DIR = DATA_DIR / "chrome-profile"
DIAG_DIR = DATA_DIR / "diagnostico"


def ensure_dirs() -> None:
    for d in (DATA_DIR, LOG_DIR, BROWSER_PROFILE_DIR, DIAG_DIR):
        d.mkdir(parents=True, exist_ok=True)


def resource_path(rel: str) -> Path:
    """Caminho de recurso empacotado (funciona também dentro do executável PyInstaller)."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / rel
