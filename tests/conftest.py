import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("UNISPACE_DATA_DIR", tempfile.mkdtemp(prefix="unispace-test-"))

from app.config import TZ  # noqa: E402
from app.database.db import Database  # noqa: E402

NOW = datetime(2026, 10, 26, 14, 0, tzinfo=TZ)


@pytest.fixture(scope="session")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from app.ui.theme import apply_theme
    apply_theme(app, dark=False)
    return app


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Os testes nunca acessam a internet: a leitura de eventos usa páginas falsas."""
    from app.services import events

    def blocked(url):
        raise OSError(f"rede desativada nos testes: {url}")
    monkeypatch.setattr(events, "fetch_url", blocked)


@pytest.fixture
def now():
    return NOW


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "teste.db"


@pytest.fixture
def db(db_path):
    d = Database(db_path)
    yield d
    d.close()
