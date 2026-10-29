"""Segurança (logs sem segredos, cofre de credenciais) e interface (quadro, edição, persistência)."""
import logging
import os

import keyring
import pytest
from keyring.backend import KeyringBackend

from app.services.credentials import CredentialStore
from app.services.logging_setup import RedactingFilter, redact, register_secret


class MemoryKeyring(KeyringBackend):
    priority = 1

    def __init__(self):
        super().__init__()
        self.data = {}

    def set_password(self, s, u, p):
        self.data[(s, u)] = p

    def get_password(self, s, u):
        return self.data.get((s, u))

    def delete_password(self, s, u):
        from keyring.errors import PasswordDeleteError
        if (s, u) not in self.data:
            raise PasswordDeleteError()
        del self.data[(s, u)]


@pytest.fixture
def mem_keyring():
    old = keyring.get_keyring()
    kr = MemoryKeyring()
    keyring.set_keyring(kr)
    yield kr
    keyring.set_keyring(old)


def test_credentials_saved_in_vault_and_editable(mem_keyring, db_path):
    st = CredentialStore("teste")
    st.save("aluno1", "senha-a")
    assert st.load().password == "senha-a"
    st.save("aluno2", "senha-b")                       # troca de usuário e senha
    c = st.load()
    assert (c.username, c.password) == ("aluno2", "senha-b")
    assert ("teste", "aluno1") not in mem_keyring.data
    st.clear()
    assert st.load() is None


def test_password_never_in_database_file(mem_keyring, db):
    CredentialStore("teste").save("aluno", "SenhaSuperSecreta!9")
    db.set_meta("show_browser", "1")
    db.close()
    raw = open(db.path, "rb").read()
    assert b"SenhaSuperSecreta" not in raw


def test_log_redaction(caplog):
    register_secret("Minh@Senha123")
    assert "Minh@Senha123" not in redact("erro com Minh@Senha123 no meio")
    assert "abc.def" not in redact("Authorization: Bearer abcdefghijkl.mnopqrstu.vwxyz12345")
    assert "XYZ123456789" not in redact("https://x/plataforma/?tokenId=XYZ123456789")
    assert "123" not in redact('{"password": "123456"}')
    rec = logging.LogRecord("t", logging.INFO, "", 0, "login com senha=%s", ("Minh@Senha123",), None)
    RedactingFilter().filter(rec)
    assert "Minh@Senha123" not in rec.getMessage()


# ---------------------------------------------------------------- interface (Qt offscreen)

@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from app.ui.theme import apply_theme
    apply_theme(app)
    yield app


class _Creds:
    def username(self):
        return "aluno"

    def load(self):
        return None


def _seed(db):
    from app.models.activity import ScrapedActivity
    from app.services.sync import SyncService
    SyncService(db).apply([ScrapedActivity(name=f"Atividade {i}", course="BD", points="2 pontos", source_id=str(i))
                           for i in range(3)], ["BD"])


def test_board_drag_drop_search_filter(qapp, db):
    from app.ui.board import BoardPage
    from app.ui.context import AppContext
    _seed(db)
    ctx = AppContext(db, _Creds())
    page = BoardPage(ctx)
    assert page.columns["todo"].count.text() == "3"
    aid = db.list_activities()[0].id
    page._on_drop(aid, "doing", 0)                     # simula soltar o cartão na coluna "Em andamento"
    assert db.get(aid).status == "doing"
    assert page.columns["doing"].count.text() == "1"
    page.search.setText("atividade 2")
    page.refresh()
    assert sum(int(c.count.text()) for c in page.columns.values()) == 1
    page.search.setText("")
    page.hide_done.setChecked(True)
    db.update_fields(aid, status="done")
    page.refresh()
    assert page.columns["done"].count.text() == "0"
    assert page.table.rowCount() == 2


def test_quick_complete_with_undo(qapp, db):
    from app.ui.board import BoardPage
    from app.ui.context import AppContext
    _seed(db)
    page = BoardPage(AppContext(db, _Creds()))
    notes = []
    page.notify.connect(lambda msg, undo: notes.append((msg, undo)))
    aid = db.list_activities()[0].id
    page.toggle_done(aid)
    assert db.get(aid).status == "done"
    msg, undo = notes[-1]
    assert "concluída" in msg.lower() and callable(undo)
    undo()
    assert db.get(aid).status == "todo"


def test_course_chip_filters(qapp, db):
    from app.models.activity import ScrapedActivity
    from app.services.sync import SyncService
    from app.ui.board import BoardPage
    from app.ui.context import AppContext
    _seed(db)
    SyncService(db).apply([ScrapedActivity(name="Outra", course="Redes (GRDESISL999)", points="1 ponto",
                                           source_id="x")], ["Redes (GRDESISL999)"])
    page = BoardPage(AppContext(db, _Creds()))
    assert [b.text() for b in page.course_group.buttons()] == ["Todas", "BD", "Redes"]   # sem o código
    page._select_course("Redes (GRDESISL999)")
    assert page.columns["todo"].count.text() == "1"


def test_panel_saves_override_and_home_counts(qapp, db):
    from app.ui.context import AppContext
    from app.ui.drawer import ActivityPanel
    from app.ui.home import HomePage
    _seed(db)
    ctx = AppContext(db, _Creds())
    a = db.list_activities()[0]
    panel = ActivityPanel(ctx)
    assert panel.open_activity(a.id)
    assert not panel.save_btn.isEnabled()                   # nada alterado ainda
    panel.points.setText("5 pontos")
    panel._mark_dirty()
    panel.notes.setPlainText("minha nota")
    assert panel.save_btn.isEnabled()
    assert panel.save()
    a2 = db.get(a.id)
    assert a2.points == "5 pontos" and a2.portal_points == "2 pontos" and a2.notes == "minha nota"
    assert a2.name == a.name and a2.user_name is None      # campo não alterado continua vindo do portal
    assert a2.due_at is None and a2.user_due_at is None     # "sem prazo" do portal não virou edição
    home = HomePage(ctx)
    assert home.t_todo.value.text() == "3" and home.t_done.value.text() == "0"


def test_panel_creates_manual_activity(qapp, db):
    from app.ui.context import AppContext
    from app.ui.drawer import ActivityPanel
    panel = ActivityPanel(AppContext(db, _Creds()))
    panel.open_new("doing")
    panel.name.setPlainText("Estudar para a prova")
    panel.no_due.setChecked(True)
    assert panel.save()
    a = db.list_activities()[0]
    assert (a.name, a.status, a.origin, a.due_at) == ("Estudar para a prova", "doing", "manual", None)


def test_main_window_builds_and_onboarding(qapp, db):
    from app.ui.context import AppContext
    from app.ui.main_window import MainWindow

    class NoCreds:
        def username(self):
            return None

        def load(self):
            return None
    w = MainWindow(AppContext(db, NoCreds()))
    assert not w.home.onb_wrap.isHidden()            # primeiro uso: tela de conexão
    w.start_update()                                 # sem conta: avisa em vez de falhar
    assert not w.banner_wrap.isHidden()


def test_browser_hidden_by_default_and_loading_bar(qapp, db):
    from app.services.updater import Progress
    from app.ui.context import AppContext
    from app.ui.widgets import LoadingBar
    ctx = AppContext(db, _Creds())
    assert ctx.show_browser is False                 # Chrome roda em segundo plano por padrão
    ctx.show_browser = True
    assert ctx.show_browser is True
    bar = LoadingBar()
    bar.start()
    bar.set_progress(Progress(step="Analisando atividades", course="BD", courses_done=1, courses_total=3,
                              activities_found=4))
    assert "1/3 disciplinas" in bar.detail.text() and bar.bar.maximum() == 3
