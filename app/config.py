"""Configurações globais e caminhos do aplicativo."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

APP_NAME = "UniSpace"
APP_TITLE = "UniSpace — Unilavras"
APP_VERSION = "1.1.0"
APP_AUTHOR = "Marcelo Machado"
APP_AUTHOR_EMAIL = "marcelomachadoit@gmail.com"
LEGACY_APP_NAME = "UniKanban"   # nome antigo: pasta de dados e cofre são migrados na primeira abertura

TZ = ZoneInfo("America/Sao_Paulo")

PORTAL_LOGIN_URL = "https://novoportal.unilavras.edu.br/sessions/login"
PORTAL_HOST = "novoportal.unilavras.edu.br"
EVENTS_URL = "https://eventos.unilavras.edu.br/"   # aba "Eventos > Inscrição" do portal (página pública)

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


def _local_appdata() -> Path:
    return Path(os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local"))


def _data_dir() -> Path:
    override = os.environ.get("UNISPACE_DATA_DIR")
    if override:
        return Path(override)
    return _local_appdata() / APP_NAME


DATA_DIR = _data_dir()
DB_PATH = DATA_DIR / "unispace.db"
LOG_DIR = DATA_DIR / "logs"
BROWSER_PROFILE_DIR = DATA_DIR / "chrome-profile"
DIAG_DIR = DATA_DIR / "diagnostico"


def migrate_legacy_data() -> bool:
    """Leva os dados do UniKanban (nome antigo) para a pasta do UniSpace. Só age se a pasta nova ainda não existe."""
    if os.environ.get("UNISPACE_DATA_DIR"):
        return False
    old = _local_appdata() / LEGACY_APP_NAME
    if DATA_DIR.exists() or not old.is_dir():
        return False
    old.rename(DATA_DIR)
    for suffix in ("", "-wal", "-shm"):
        f = DATA_DIR / f"unikanban.db{suffix}"
        if f.exists():
            f.rename(DATA_DIR / f"unispace.db{suffix}")
    return True


def ensure_dirs() -> None:
    for d in (DATA_DIR, LOG_DIR, BROWSER_PROFILE_DIR, DIAG_DIR):
        d.mkdir(parents=True, exist_ok=True)


def resource_path(rel: str) -> Path:
    """Caminho de recurso empacotado (funciona também dentro do executável PyInstaller)."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / rel
