"""Fluxo completo com cliente simulado: seleção < 95%, falhas de conexão (14), sessão expirada (14), cancelamento."""
import threading
from datetime import datetime
from unittest import mock

import pytest

from app.automation import parser as P
from app.automation.portal import AutomationError, PortalClient
from app.config import TZ
from app.services.credentials import Credentials
from app.services.updater import Updater
from tests.fakes import CONTENTS, COURSES, factory

NOW = datetime(2026, 10, 26, 14, 0, tzinfo=TZ)
CREDS = Credentials("aluno", "segredo-123")


@pytest.fixture(autouse=True)
def fixed_now():
    real = P.parse_contents_json

    def patched(*a, **kw):
        kw.setdefault("now", NOW)
        return real(*a, **kw)
    with mock.patch.object(P, "parse_contents_json", patched):
        yield


def run(db, **behaviour):
    f = factory(**behaviour)
    cancel = threading.Event()
    r = Updater(db, CREDS, headless=True, cancel=cancel, client_factory=f).run()
    return r, f.holder.get("client")


def test_course_selection_and_extraction(db):
    r, client = run(db)
    assert client.calls == ["1", "2"]                          # 40% e 94% processadas
    assert any("Algoritmos" in s for s in r.courses_skipped)   # 95% ignorada
    assert any("Cálculo" in s for s in r.courses_skipped)      # 100% ignorada
    assert r.courses_unknown == ["Ética"]                      # percentual ausente: não presumido
    names = {a.name: a for a in db.list_activities()}
    assert set(names) == {"Questionário do Módulo 3", "Trabalho prático", "Prova I: 12/11", "Desafio"}
    assert "Lista de exercícios 1" not in names                # prazo expirado
    q = names["Questionário do Módulo 3"]
    assert q.due_display == "-" and q.points == "10 pontos" and q.course == "Banco de Dados"
    assert names["Prova I: 12/11"].due_at == datetime(2026, 11, 12, 23, 59, 59, tzinfo=TZ)
    assert names["Trabalho prático"].url.endswith("/plataforma/course/1/content/14")
    assert db.get_meta("last_update") and db.get_meta("last_auth_success")


def test_second_run_is_incremental(db):
    run(db)
    r, _ = run(db)
    assert (r.found, r.added, r.unchanged) == (4, 0, 4)
    assert len(db.list_activities()) == 4


def test_login_failure_preserves_data(db):
    run(db)
    before = [(a.id, a.status) for a in db.list_activities()]
    r, _ = run(db, login_fail=True)
    assert r.errors and "login" in r.errors[0].lower()
    assert [(a.id, a.status) for a in db.list_activities()] == before


def test_structure_change_reported(db):
    r, _ = run(db, structure=True)
    assert r.errors and "Sala de Aula Virtual" in r.errors[0]


def test_connection_failure_in_one_course_continues(db):
    r, _ = run(db, fail="1")
    assert r.courses_failed and r.courses_failed[0][0] == "Banco de Dados"
    assert r.courses_processed == ["Redes"]
    assert [a.name for a in db.list_activities()] == ["Desafio"]


def test_failed_course_does_not_mark_activities_missing(db):
    run(db)
    run(db, fail="1")
    assert all(a.last_seen_status == "encontrada" for a in db.list_activities())


def test_session_expired_reauthenticates(db):
    r, client = run(db, expire_once="1")
    assert client.logins == 2
    assert not r.errors and "Banco de Dados" in r.courses_processed


def test_cancel_keeps_already_saved_data(db):
    r, _ = run(db, cancel_after="1")
    assert r.cancelled
    assert {a.course for a in db.list_activities()} == {"Banco de Dados"}   # 1ª disciplina salva


def test_retry_gives_up_after_limit(tmp_path):
    from playwright.sync_api import TimeoutError as PWTimeout
    c = PortalClient(tmp_path)
    calls = []

    def boom():
        calls.append(1)
        raise PWTimeout("Timeout 45000ms exceeded")
    with pytest.raises(AutomationError) as e:
        c._retry("Abrir o portal", boom)
    assert len(calls) == 3 and "conexão" in str(e.value)


def test_retry_recovers_from_transient_error(tmp_path):
    from playwright.sync_api import Error as PWError
    c = PortalClient(tmp_path)
    attempts = iter([PWError("net::ERR_CONNECTION_RESET"), "ok"])

    def flaky():
        v = next(attempts)
        if isinstance(v, Exception):
            raise v
        return v
    assert c._retry("x", flaky) == "ok"


def test_parser_pagination_flag_and_fallback():
    cs, nxt = P.parse_courses_json({**COURSES, "nextPage": True})
    assert nxt and len(cs) == 5
    card = P.parse_course_card_text("Redes", "Redes\nInício: 05/10/2026\n94% concluído")
    assert card.progress == 94.0
    assert P.parse_course_card_text("X", "sem dados").progress is None


def test_parser_skips_section_with_graded_child():
    data = CONTENTS["1"]
    scan = P.parse_contents_json(data, "Banco de Dados", 1, "https://x", now=NOW)
    assert "Ciclo I" not in [a.name for a in scan.activities]
    assert scan.skipped_expired == 1
