"""Teste de integração com o portal real.

Executado somente quando as variáveis de ambiente UNIKANBAN_TEST_USER e UNIKANBAN_TEST_PASSWORD
estiverem definidas (as credenciais nunca ficam gravadas em arquivos).
"""
import os

import pytest

from app.database.db import Database
from app.services.credentials import Credentials
from app.services.updater import Updater

USER = os.environ.get("UNIKANBAN_TEST_USER")
PWD = os.environ.get("UNIKANBAN_TEST_PASSWORD")

pytestmark = pytest.mark.skipif(not (USER and PWD), reason="credenciais de teste não definidas no ambiente")


def test_full_update_against_real_portal(tmp_path):
    db = Database(tmp_path / "integ.db")
    steps = []
    up = Updater(db, Credentials(USER, PWD), headless=True, on_progress=lambda p: steps.append(p.step))
    r1 = up.run()
    print(r1.summary_text())
    assert not r1.errors, r1.errors
    assert r1.courses_processed, "nenhuma disciplina < 95% processada"
    assert r1.found == r1.added > 0
    for a in db.list_activities():
        assert a.name != "-" and a.course != "-"
        assert a.url and "/plataforma/course/" in a.url
    # segunda execução: nada novo, nada duplicado
    r2 = Updater(db, Credentials(USER, PWD), headless=True).run()
    assert not r2.errors, r2.errors
    assert r2.added == 0 and r2.unchanged == r2.found == r1.found
    assert len(db.list_activities()) == r1.added
    db.close()


def test_connection_ok(tmp_path):
    db = Database(tmp_path / "integ3.db")
    Updater(db, Credentials(USER, PWD), headless=True).test_connection()
    assert db.get_meta("last_auth_success")
    db.close()


@pytest.mark.skipif(not os.environ.get("UNIKANBAN_TEST_WRONG_PASSWORD"),
                    reason="desligado por padrão: tentativas com senha errada levam o portal a exigir "
                           "verificação humana (Cloudflare) na conta real")
def test_wrong_password_is_reported(tmp_path):
    from app.automation.portal import AutomationError
    db = Database(tmp_path / "integ2.db")
    with pytest.raises(AutomationError) as exc:
        Updater(db, Credentials(USER, PWD + "x-invalida"), headless=True).test_connection()
    assert "login" in str(exc.value).lower()
    assert PWD not in str(exc.value)
    assert db.get_meta("last_auth_success") is None
    db.close()
