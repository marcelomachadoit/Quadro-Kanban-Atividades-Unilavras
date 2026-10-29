"""Calendário: encontros virtuais (títulos reais observados no portal), recorrência, matérias ativas e a aba."""
import os
from datetime import date, datetime

import pytest

from app.automation.meetings_parser import extract_meetings, parse_meeting_text
from app.config import TZ
from app.models.meetings import CourseInfo, Meeting, completed_ids, next_meeting, occurrences
from tests.fakes import contents, topic


def test_parse_real_titles():
    m = parse_meeting_text("Encontro Virtual – Terça-feira às 21h")
    assert [(x.kind, x.weekday, x.time) for x in m] == [("weekly", 1, "21:00")]
    m = parse_meeting_text("Encontro Virtual – Segunda-feira às 20h30min")
    assert [(x.weekday, x.time) for x in m] == [(0, "20:30")]
    m = parse_meeting_text("Encontro Virtual – 19/10", date(2026, 10, 5))
    assert [(x.kind, x.date, x.time) for x in m] == [("date", "2026-10-19", None)]
    m = parse_meeting_text("Encontro Virtual – Correção da P1 - 14/09", date(2026, 6, 11))
    assert m[0].date == "2026-09-14"
    assert parse_meeting_text("Encontro Virtual – Revisão para a P1") == []   # sem dia nem data
    assert parse_meeting_text("Aula 03 - Python_ Conjuntos e Dicionários") == []
    two = parse_meeting_text("Encontros virtuais às terças e quintas-feiras, 19h")
    assert sorted(x.weekday for x in two) == [1, 3] and all(x.time == "19:00" for x in two)


def test_extract_meetings_from_contents_dedupes_and_uses_description():
    data = contents(5, "Estruturas de Dados (GRDESISL235)", [
        topic(1, "Encontro Virtual – Segunda-feira às 20h30min", 2, 1, children=[topic(2, "Encontro Virtual ", 19, 7)]),
        topic(3, "Ciclo II: de 19/10 a 30/10", 1, 1, children=[topic(4, "Encontro Virtual – 19/10", 7, 4)]),
    ], start="2026-10-05")
    ms = extract_meetings(data)
    assert [(m.kind, m.weekday, m.date, m.time) for m in ms] == [("weekly", 0, None, "20:30"),
                                                                  ("date", None, "2026-10-19", None)]
    # caso real: a descrição interna citava outro horário; o título da seção prevalece
    conflict = contents(5, "ED", [topic(1, "Encontro Virtual – Segunda-feira às 20h30min", 2, 1,
                                        children=[topic(2, "Encontro Virtual ", 19, 7)])])
    conflict["topics"][0]["children"][0]["content"] = {"description": "segunda-feira, a partir das 20h20"}
    assert [(m.weekday, m.time) for m in extract_meetings(conflict)] == [(0, "20:30")]
    generic = contents(6, "X", [topic(7, "Encontro Virtual", 19, 7)])
    generic["topics"][0]["content"] = {"description": "<p>Nossos encontros acontecem <b>todas as quartas-feiras, "
                                                      "às 19h</b>.</p>"}
    assert [(m.weekday, m.time) for m in extract_meetings(generic)] == [(2, "19:00")]


def test_occurrences_weekly_from_course_start_and_dated_without_duplicate():
    info = CourseInfo("5", "ED", "2026-10-05", 41.0,
                      [Meeting("weekly", weekday=0, time="20:30"), Meeting("date", date="2026-10-19"),
                       Meeting("date", date="2026-10-22", time="19:00")])
    occ = occurrences(info, date(2026, 9, 27), date(2026, 11, 7))
    days = [d for d, _ in occ]
    assert date(2026, 9, 28) not in days                     # antes do início da disciplina
    assert days.count(date(2026, 10, 19)) == 1                # data avulsa coincide com a semanal
    assert date(2026, 10, 22) in days and date(2026, 11, 2) in days
    d, m = next_meeting(info, datetime(2026, 10, 26, 21, 0))  # segunda às 21h: o de hoje (20:30) já passou
    assert d == date(2026, 11, 2)
    d, m = next_meeting(info, datetime(2026, 10, 26, 14, 0))
    assert d == date(2026, 10, 26) and m.time == "20:30"


def test_completed_courses_hidden_by_module_rule():
    infos = [CourseInfo("1", "Alg", "2026-06-11", 96.0), CourseInfo("2", "APS", "2026-06-11", 100.0),
             CourseInfo("3", "FE2", "2026-10-05", 60.0), CourseInfo("4", "UX", "2026-10-05", 100.0)]
    assert completed_ids(infos, date(2026, 10, 26)) == {"1", "2", "4"}
    assert completed_ids(infos, date(2026, 9, 1)) == {"2", "4"}  # módulo 2 ainda não começou


def test_course_info_upsert_keeps_meetings(db):
    db.save_course_info("5", "ED", "2026-10-05", 40.0, [{"kind": "weekly", "weekday": 0, "time": "20:30",
                                                         "date": None, "title": "x"}])
    db.save_course_info("5", "ED", "2026-10-05", 41.0)                       # só progresso
    row = db.list_course_info()[0]
    assert row["progress"] == 41.0 and row["meetings"][0]["time"] == "20:30"
    db.save_course_info("5", "ED", "2026-10-05", 41.0, [])                   # leitura nova sem encontros
    assert db.list_course_info()[0]["meetings"] == []


def test_activity_update_saves_course_info_and_meetings(db):
    from app.services.credentials import Credentials
    from app.services.updater import Updater
    from tests import fakes
    fakes.CONTENTS["1"]["topics"].append(topic(99, "Encontro Virtual – Terça-feira às 21h", 2, 1))
    try:
        Updater(db, Credentials("u", "p"), client_factory=fakes.factory()).run()
    finally:
        fakes.CONTENTS["1"]["topics"].pop()
    infos = {r["course_id"]: r for r in db.list_course_info()}
    assert set(infos) == {"1", "2", "3", "4", "5"}                           # todas as disciplinas
    assert infos["1"]["meetings"][0]["weekday"] == 1 and infos["3"]["meetings"] == []


# ------------------------------------------------------------------ aba

@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from app.ui.theme import apply_theme
    apply_theme(app)
    return app


class _Creds:
    def username(self):
        return "aluno"

    def load(self):
        return None


def test_calendar_page_shows_activities_and_active_meetings(qapp, db):
    from PySide6.QtWidgets import QLabel, QPushButton
    from app.models.activity import ScrapedActivity
    from app.services.sync import SyncService
    from app.ui.calendar_page import CalendarPage, MeetingBox, month_grid
    from app.ui.context import AppContext
    today = datetime.now(TZ)
    SyncService(db).apply([ScrapedActivity(name="Lista de Exercícios", course="ED", source_id="a",
                                           due_at=today.replace(hour=23, minute=0, second=0, microsecond=0))], ["ED"])
    start_now = today.date().replace(day=1).isoformat()
    db.save_course_info("5", "ED", start_now, 40.0, [{"kind": "weekly", "weekday": today.weekday(), "time": "20:30",
                                                      "date": None, "title": "Encontro Virtual"}])
    db.save_course_info("1", "Algoritmos", "2000-01-01", 96.0,                 # módulo anterior => concluída
                        [{"kind": "weekly", "weekday": 1, "time": "19:00", "date": None, "title": "x"}])
    page = CalendarPage(AppContext(db, _Creds()))
    boxes = [page.meet_grid.itemAt(i).widget() for i in range(page.meet_grid.count())]
    boxes = [b for b in boxes if isinstance(b, MeetingBox)]
    assert len(boxes) == 1                                                   # concluída não aparece
    box_text = " ".join(l.text() for l in boxes[0].findChildren(QLabel))
    assert "Toda" in box_text and "20:30" in box_text and "Próximo" in box_text
    from app.ui.calendar_page import ElidedButton
    chips = [b.full_text for b in page.findChildren(ElidedButton)]
    assert any("Lista de Exercícios" in t for t in chips)
    meetings = [b for b in page.findChildren(ElidedButton) if b.toolTip().startswith("Encontro virtual")]
    assert meetings and all(b.full_text == "20:30 · ED" for b in meetings)
    assert not any("Algoritmos" in t for t in chips)
    opened = []
    page.open_activity.connect(opened.append)
    next(b for b in page.findChildren(ElidedButton) if "Lista de" in b.full_text).click()
    assert opened == [db.list_activities()[0].id]
    page.shift(1)
    page.shift(-13)
    page.go_today()
    assert (page.year, page.month) == (today.year, today.month)
    g = month_grid(2026, 10)
    assert g[0] == date(2026, 9, 27) and g[0].weekday() == 6 and len(g) == 42   # começa no domingo


def test_course_colors_are_distinct_for_registered_courses():
    from app.ui import format as F
    F._ASSIGNED.clear()
    names = ["Desenvolvimento Front-End II (GRDESISL236)", "Estruturas de Dados (GRDESISL235)",
             "User Experience (GRDESISL237)", "Algoritmos e Programação (GRDESISL232)"]
    F.register_courses(names)
    colors = [F.course_color(n) for n in names]
    assert len(set(colors)) == len(names)
    assert F.course_color("User Experience") == colors[2]      # mesmo curso com ou sem código = mesma cor
    F._ASSIGNED.clear()
