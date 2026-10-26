"""Atualização semanal automática e "+N mais" do calendário."""
import os
from datetime import date, datetime, timedelta

import pytest

from app.config import TZ
from app.services.credentials import Credentials
from app.services.weekly import (META_WEEKLY_ATTEMPT, META_WEEKLY_RUN, WeeklyUpdater, is_weekly_due, week_start)

MON, TUE, WED, SUN = date(2026, 10, 26), date(2026, 10, 27), date(2026, 10, 28), date(2026, 11, 1)


def test_week_starts_on_monday():
    assert week_start(MON) == MON and week_start(WED) == MON and week_start(SUN) == MON
    assert week_start(date(2026, 11, 2)) == date(2026, 11, 2)


def test_first_open_on_monday_runs_once():
    assert is_weekly_due(MON, last_run="2026-10-19", last_attempt="2026-10-19")      # semana passada
    assert not is_weekly_due(MON, last_run=MON.isoformat(), last_attempt=MON.isoformat())  # 2ª abertura no dia


def test_skipped_monday_runs_on_wednesday_then_not_again_that_week():
    assert is_weekly_due(WED, last_run="2026-10-19", last_attempt="2026-10-19")
    assert not is_weekly_due(SUN, last_run=WED.isoformat(), last_attempt=WED.isoformat())
    assert is_weekly_due(date(2026, 11, 2), last_run=WED.isoformat(), last_attempt=WED.isoformat())


def test_never_ran_and_failure_retries_only_on_another_day():
    assert is_weekly_due(TUE, None, None)
    assert not is_weekly_due(TUE, last_run="2026-10-19", last_attempt=TUE.isoformat())  # falhou hoje
    assert is_weekly_due(WED, last_run="2026-10-19", last_attempt=TUE.isoformat())      # tenta amanhã


def test_weekly_runs_everything_with_a_single_login(db):
    from tests.test_grades import GradesFake
    made = []

    def factory(**kw):
        c = GradesFake(behaviour={}, **kw)
        made.append(c)
        return c
    r = WeeklyUpdater(db, Credentials("u", "p"), client_factory=factory, today=WED).run()
    assert r.ok
    assert len(made) == 1 and made[0].logins == 1                 # um navegador, um login
    assert r.activities.found > 0 and len(r.grades.courses_ok) == 5
    assert db.list_activities() and db.list_grade_snapshots() and db.list_course_info()
    assert db.get_meta(META_WEEKLY_RUN) == WED.isoformat() == db.get_meta(META_WEEKLY_ATTEMPT)


def test_weekly_failure_records_attempt_but_not_run(db):
    from tests.test_grades import GradesFake
    r = WeeklyUpdater(db, Credentials("u", "p"), today=WED,
                      client_factory=lambda **kw: GradesFake(behaviour={"login_fail": True}, **kw)).run()
    assert not r.ok and r.errors
    assert db.get_meta(META_WEEKLY_ATTEMPT) == WED.isoformat() and db.get_meta(META_WEEKLY_RUN) is None


# ------------------------------------------------------------------ interface

@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from app.ui.theme import apply_theme
    apply_theme(app)
    return app


class _Creds:
    def __init__(self, ok=True):
        self.ok = ok

    def username(self):
        return "aluno" if self.ok else None

    def load(self):
        return Credentials("aluno", "x") if self.ok else None


def test_main_window_starts_weekly_and_shows_card(qapp, db, monkeypatch):
    from app.services.sync import SyncReport
    from app.services.weekly import WeeklyReport
    from app.ui import main_window as MW
    from app.ui.context import AppContext
    monkeypatch.delenv("UNIKANBAN_NO_AUTO_UPDATE", raising=False)
    monkeypatch.setattr(MW.WeeklyWorker, "start", lambda self: None)      # não abre navegador no teste
    w = MW.MainWindow(AppContext(db, _Creds()))
    w.show()
    assert w.maybe_weekly_update() is True
    assert not w.notif.isHidden()
    assert w.notif.title.text() == "Atualização de dados semanal em andamento"
    assert not w.loading.isHidden()
    rep = WeeklyReport(activities=SyncReport(added=2))
    w._weekly_finished(rep)
    assert w.notif.isHidden() and w.loading.isHidden()
    assert "Atualização semanal concluída" in w.toast.msg.text()
    # sem conta salva: nunca dispara
    w2 = MW.MainWindow(AppContext(db, _Creds(ok=False)))
    assert w2.maybe_weekly_update() is False


def test_weekly_not_started_when_already_done_this_week(qapp, db, monkeypatch):
    from app.ui import main_window as MW
    from app.ui.context import AppContext
    today = datetime.now(TZ).date()
    db.set_meta(META_WEEKLY_RUN, today.isoformat())
    monkeypatch.setattr(MW.WeeklyWorker, "start", lambda self: None)
    w = MW.MainWindow(AppContext(db, _Creds()))
    assert w.maybe_weekly_update() is False and w.notif.isHidden()


def test_calendar_more_items_open_day_dialog(qapp, db):
    from PySide6.QtWidgets import QPushButton
    from app.models.activity import ScrapedActivity
    from app.services.sync import SyncService
    from app.ui.calendar_page import CalendarPage, DayCell, DayDialog
    from app.ui.context import AppContext
    day = datetime.now(TZ).replace(hour=10, minute=0, second=0, microsecond=0)
    SyncService(db).apply([ScrapedActivity(name=f"Atividade {i}", course="BD", source_id=f"x{i}",
                                           due_at=day + timedelta(hours=i)) for i in range(5)], ["BD"])
    page = CalendarPage(AppContext(db, _Creds()))
    cell = next(c for c in page.findChildren(DayCell) if c.day == day.date())
    more = [b for b in cell.findChildren(QPushButton) if b.text().endswith("mais")]
    assert [b.text() for b in more] == ["+2 mais"]
    items = sorted(page.day_items[day.date()], key=lambda i: i["sort"])
    assert [i["title"] for i in items] == [f"Atividade {i}" for i in range(5)]   # todos, em ordem de horário
    dlg = DayDialog(day.date(), items)
    rows = [b for b in dlg.findChildren(QPushButton) if b.text() == ""]
    assert len(rows) == 5
    opened = []
    dlg.open_activity.connect(opened.append)
    rows[4].click()
    assert opened == [items[4]["aid"]]


def test_auto_update_can_be_disabled_for_tests(qapp, db, monkeypatch):
    from app.ui import main_window as MW
    from app.ui.context import AppContext
    monkeypatch.setenv("UNIKANBAN_NO_AUTO_UPDATE", "1")
    monkeypatch.setattr(MW.WeeklyWorker, "start", lambda self: (_ for _ in ()).throw(AssertionError("não deveria")))
    assert MW.MainWindow(AppContext(db, _Creds())).maybe_weekly_update() is False
