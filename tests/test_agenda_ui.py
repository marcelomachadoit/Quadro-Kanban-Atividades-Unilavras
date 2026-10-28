"""Agenda, abas novas (Sobre, Eventos), modo noturno e migração do nome antigo (UniKanban -> UniSpace)."""
from datetime import datetime, timedelta

import pytest

from app.config import APP_AUTHOR_EMAIL, TZ
from app.models.agenda import AgendaItem
from app.services.credentials import Credentials
from tests.test_security_ui import mem_keyring  # noqa: F401 — fixture do cofre em memória


class _Creds:
    def username(self):
        return "aluno"

    def load(self):
        return Credentials("aluno", "x")


@pytest.fixture
def no_auto(monkeypatch):
    monkeypatch.setenv("UNISPACE_NO_AUTO_UPDATE", "1")


# ------------------------------------------------------------------ agenda: banco

def test_agenda_crud(db):
    today = datetime.now(TZ).date().isoformat()
    aid = db.add_agenda_item(AgendaItem(title="Prova de Cálculo", day=today, start_time="19:00", end_time="21:00",
                                        category="Prova", location="Sala 12"))
    db.add_agenda_item(AgendaItem(title="Estudar", day=today, category="Estudo"))
    items = db.list_agenda_items()
    assert [i.title for i in items] == ["Estudar", "Prova de Cálculo"]      # dia inteiro antes do horário
    assert items[1].time_range() == "19:00–21:00" and items[0].all_day
    db.update_agenda_item(aid, done=True, title="Prova de Cálculo I")
    it = next(i for i in db.list_agenda_items() if i.id == aid)
    assert it.done and it.title == "Prova de Cálculo I"
    with pytest.raises(ValueError):
        db.update_agenda_item(aid, id=3)
    db.delete_agenda_item(aid)
    assert [i.title for i in db.list_agenda_items()] == ["Estudar"]


# ------------------------------------------------------------------ agenda: interface

def test_agenda_page_merges_activities_and_filters(qapp, db):
    from app.models.activity import ScrapedActivity
    from app.services.sync import SyncService
    from app.ui.agenda_page import AgendaPage, EntryRow
    from app.ui.context import AppContext
    now = datetime.now(TZ)
    today = now.date()
    SyncService(db).apply([ScrapedActivity(name="Entrega BD", course="BD", source_id="a1",
                                           due_at=(now + timedelta(days=2)).replace(hour=10, minute=0))], ["BD"])
    db.add_agenda_item(AgendaItem(title="Aula prática", day=(today + timedelta(days=1)).isoformat(),
                                  start_time="08:00", category="Aula"))
    db.add_agenda_item(AgendaItem(title="Antigo", day=(today - timedelta(days=3)).isoformat(), done=True))
    page = AgendaPage(AppContext(db, _Creds()))
    kinds = [(r.entry.kind, r.entry.title) for r in page.findChildren(EntryRow)]
    assert kinds == [("own", "Aula prática"), ("activity", "Entrega BD")]
    page.show_linked.setChecked(False)
    assert [r.entry.title for r in page.findChildren(EntryRow)] == ["Aula prática"]
    page._set_filter("done")
    assert [r.entry.title for r in page.findChildren(EntryRow)] == ["Antigo"]
    opened = []
    page.open_activity.connect(opened.append)
    page._set_filter("upcoming")
    page.show_linked.setChecked(True)
    row = next(r for r in page.findChildren(EntryRow) if r.entry.kind == "activity")
    page._open(row.entry)
    assert opened == [row.entry.aid]


def test_agenda_toggle_done_and_undo(qapp, db):
    from app.ui.agenda_page import AgendaPage
    from app.ui.context import AppContext
    ctx = AppContext(db, _Creds())
    db.add_agenda_item(AgendaItem(title="Trabalho em grupo", day=datetime.now(TZ).date().isoformat()))
    page = AgendaPage(ctx)
    undo = []
    page.notify.connect(lambda m, a: undo.append(a))
    page.toggle_done(db.list_agenda_items()[0])
    assert db.list_agenda_items()[0].done
    undo[0]()
    assert not db.list_agenda_items()[0].done


def test_agenda_dialog_validates(qapp):
    from PySide6.QtCore import QTime
    from app.ui.agenda_page import AgendaDialog
    dlg = AgendaDialog()
    dlg._save()
    assert dlg.result_item is None and not dlg.error.isHidden()           # sem título
    dlg.title.setText("Revisão")
    dlg.start.setTime(QTime(10, 0))
    dlg.end.setTime(QTime(9, 0))
    dlg._save()
    assert dlg.result_item is None and "término" in dlg.error.text()
    dlg.all_day.setChecked(True)
    dlg._save()
    assert dlg.result_item.title == "Revisão" and dlg.result_item.start_time is None


def test_calendar_shows_agenda_items(qapp, db):
    from app.ui.calendar_page import CalendarPage
    from app.ui.context import AppContext
    today = datetime.now(TZ).date()
    db.add_agenda_item(AgendaItem(title="Consulta", day=today.isoformat(), start_time="15:00", category="Pessoal"))
    page = CalendarPage(AppContext(db, _Creds()))
    assert [i["title"] for i in page.day_items[today]] == ["Consulta"]


# ------------------------------------------------------------------ janela, abas e modo noturno

def test_nav_has_new_tabs_in_order(qapp, db, no_auto):
    from app.ui import main_window as MW
    from app.ui.context import AppContext
    w = MW.MainWindow(AppContext(db, _Creds()))
    names = [w.nav.button(i).text().strip() for i in range(len(w._nav_icons))]
    assert names == ["Início", "Quadro de Atividades", "Calendário", "Notas", "Eventos", "Agenda", "Sobre",
                     "Configurações"]
    w.go(MW.PAGE_ABOUT)
    assert w.stack.currentWidget() is w.about
    from PySide6.QtWidgets import QLabel
    assert any(APP_AUTHOR_EMAIL in lb.text() for lb in w.about.findChildren(QLabel))
    assert any("Marcelo Machado" in lb.text() for lb in w.about.findChildren(QLabel))


def test_home_update_runs_full_update(qapp, db, no_auto, monkeypatch):
    from app.ui import main_window as MW
    from app.ui.context import AppContext
    started = []
    monkeypatch.setattr(MW.FullWorker, "start", lambda self: started.append(self))
    w = MW.MainWindow(AppContext(db, _Creds()))
    w.home.update_btn.click()
    assert len(started) == 1 and isinstance(w._worker, MW.FullWorker)
    assert w.events.update_btn.text() == "Atualizando eventos…" and w.grades.update_btn.text() == "Atualizando notas…"


def test_full_finish_reports_grades_and_events(qapp, db, no_auto):
    from app.services.events import EventsReport
    from app.services.sync import SyncReport
    from app.services.weekly import FullReport
    from app.ui import main_window as MW
    from app.ui.context import AppContext
    w = MW.MainWindow(AppContext(db, _Creds()))
    w._finished(FullReport(activities=SyncReport(added=1), events=EventsReport(found=8)))
    assert w.toast.msg.text().startswith("Tudo atualizado · 1 nova") and "8 eventos" in w.toast.msg.text()
    w._finished(FullReport(activities=SyncReport(), events=EventsReport(errors=["sem internet"])))
    assert not w.banner_wrap.isHidden()                       # eventos falharam: aviso, mas não erro geral
    lines = w._extra_lines(FullReport(events=EventsReport(errors=["sem internet"])))
    assert any("sem internet" in x for x in lines)


def test_dark_mode_toggle_rebuilds_content_in_place(qapp, db, no_auto):
    from app.ui import main_window as MW
    from app.ui import theme
    from app.ui.context import AppContext
    ctx = AppContext(db, _Creds())
    w = MW.MainWindow(ctx, start_page=MW.PAGE_AGENDA)
    try:
        old_switch = w.dark_switch
        w.dark_switch.setChecked(True)
        assert ctx.dark_mode and w._fade is not None                       # tela anterior congelada por cima
        w._retheme()
        assert theme.is_dark() and theme.COLORS["bg"] == theme.DARK["bg"]
        assert theme.URGENCY_STYLE["atrasada"][1] == theme.DARK["danger_bg"]
        assert ctx.window is w and w._fade is None                         # mesma janela, só o conteúdo muda
        assert w.dark_switch is not old_switch and w.dark_switch.isChecked()
        assert w.stack.currentIndex() == MW.PAGE_AGENDA
        w.dark_switch.setChecked(False)
        w._retheme()
        assert not ctx.dark_mode and theme.COLORS["bg"] == theme.LIGHT["bg"]
        assert AppContext(db, _Creds()).dark_mode is False                  # preferência salva no banco
    finally:
        theme.apply_theme(qapp, dark=False)


def test_dark_mode_blocked_during_update(qapp, db, no_auto, monkeypatch):
    from app.ui import main_window as MW
    from app.ui.context import AppContext
    ctx = AppContext(db, _Creds())
    w = MW.MainWindow(ctx)
    monkeypatch.setattr(w, "update_running", lambda: True)
    w.dark_switch.setChecked(True)
    assert not w.dark_switch.isChecked() and not ctx.dark_mode


def test_palettes_have_same_tokens():
    from app.ui.theme import DARK, LIGHT
    assert set(LIGHT) == set(DARK)


# ------------------------------------------------------------------ migração do nome antigo

def test_legacy_data_folder_is_migrated(tmp_path, monkeypatch):
    import app.config as C
    old = tmp_path / "UniKanban"
    (old / "chrome-profile").mkdir(parents=True)
    (old / "unikanban.db").write_text("x")
    (old / "unikanban.db-wal").write_text("w")
    monkeypatch.delenv("UNISPACE_DATA_DIR", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(C, "DATA_DIR", tmp_path / "UniSpace")
    assert C.migrate_legacy_data() is True
    assert (tmp_path / "UniSpace" / "unispace.db").read_text() == "x"
    assert (tmp_path / "UniSpace" / "unispace.db-wal").exists() and (tmp_path / "UniSpace" / "chrome-profile").is_dir()
    assert not old.exists()
    assert C.migrate_legacy_data() is False                                # só uma vez


def test_legacy_credentials_are_migrated(mem_keyring):
    from app.services.credentials import LEGACY_SERVICE, CredentialStore
    CredentialStore(LEGACY_SERVICE).save("aluno", "segredo")
    new = CredentialStore()
    assert new.migrate_from() is True
    assert new.load() == Credentials("aluno", "segredo")
    assert CredentialStore(LEGACY_SERVICE).load() is None
    assert new.migrate_from() is False
