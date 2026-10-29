"""Detecção do resultado do login com páginas simuladas (Chrome local, sem acessar o portal).

Reproduz o DOM observado no portal real em out/2026: mensagem "Conclua a verificação de segurança antes de
continuar." seguida do widget Turnstile com ".turnstile-help" ("Não foi possível concluir a verificação neste
navegador"), além do erro comum de credenciais.
"""
import pytest

from app.automation.portal import HumanVerificationRequired, PortalClient
from app.services.updater import Updater
from app.services.credentials import Credentials
from tests.fakes import FakeClient

SNACK = '<div class="mat-mdc-snack-bar-label">{}</div>'
HELP = ('<section class="turnstile-widget"><div class="turnstile-help">Não foi possível concluir a verificação '
        'neste navegador.</div></section>')


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    c = PortalClient(tmp_path_factory.mktemp("perfil"), headless=True)
    try:
        c.start()
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"Chrome indisponível: {e}")
    yield c
    c.close()


def _outcome(client, html, delayed_html=None, seconds=3):
    p = client.portal
    p.set_content(f"<body>{html}</body>")
    if delayed_html:
        p.evaluate("h => setTimeout(() => document.body.insertAdjacentHTML('beforeend', h), 600)", delayed_html)
    return client._wait_login_outcome(p, seconds)


def test_wrong_credentials_detected(client):
    assert _outcome(client, SNACK.format("Usuário ou senha inválidos!")) == "erro:Usuário ou senha inválidos!"


def test_verification_message_is_not_wrong_password(client):
    # mensagem de verificação + widget que informa bloqueio => "bloqueado", nunca "erro de credenciais"
    r = _outcome(client, SNACK.format("Conclua a verificação de segurança antes de continuar."), HELP)
    assert r == "bloqueado"


def test_verification_pending_waits_for_human(client):
    r = _outcome(client, SNACK.format("Conclua a verificação de segurança antes de continuar."), seconds=2)
    assert r == "manual"


def test_manual_wait_aborts_when_widget_blocked(client):
    client.portal.set_content(f"<body>{HELP}</body>")
    with pytest.raises(HumanVerificationRequired):
        client._wait_logged_in(client.portal, 2)


def test_updater_reports_verification_clearly(db):
    class Blocked(FakeClient):
        def login(self, creds):
            from app.automation.portal import VERIFICATION_GUIDE
            raise HumanVerificationRequired(VERIFICATION_GUIDE)

    r = Updater(db, Credentials("u", "p"), client_factory=lambda **kw: Blocked(**kw)).run()
    assert r.errors and "NÃO foram recusadas" in r.errors[0]
    assert "Abrir portal no navegador" in r.errors[0]
