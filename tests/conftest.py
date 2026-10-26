import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("UNIKANBAN_DATA_DIR", tempfile.mkdtemp(prefix="unikanban-test-"))

from app.config import TZ  # noqa: E402
from app.database.db import Database  # noqa: E402

NOW = datetime(2026, 10, 26, 14, 0, tzinfo=TZ)


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
