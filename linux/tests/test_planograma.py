"""Provas fora do quadro (só na agenda, categoria Prova) e data do AVIN lida do Planograma da disciplina."""
import threading
from datetime import date, datetime, timedelta

import pytest

from app.automation import planograma as PL
from app.config import TZ
from app.models.activity import ScrapedActivity
from app.services import rules as R
from app.services.credentials import Credentials
from app.services.sync import SyncService
from app.services.updater import Updater
from tests.fakes import CONTENTS, PLANOGRAMA_PDF_URL, factory, planograma_topic_json

# texto como o QtPdf extrai do quadro "Fique ligado!" do Planograma real
PLANOGRAMA_TEXT = """Data Fique ligado!
05/10/2026 Inicio do Módulo 2
12/11/2026 Prova 1
a definir Prova 1 - 2º chamada
02/12/2026 AVIN
a definir AVIN - 2º chamada
15/12/2026 Resultado final
PLANOGRAMA"""


def make_pdf(lines: list[str]) -> bytes:
    """PDF mínimo e válido (fonte Helvetica padrão, sem embutir), para exercitar a mesma extração usada com o
    arquivo do portal. O QPdfWriter não serve aqui: na plataforma offscreen dos testes não há fontes."""
    def esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream = "BT /F1 12 Tf 72 760 Td 16 TL " + " ".join(f"({esc(t)}) Tj T*" for t in lines) + " ET"
    stream_b = stream.encode("cp1252")
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
            b"/Resources << /Font << /F1 5 0 R >> >> >>",
            b"<< /Length %d >>\nstream\n" % len(stream_b) + stream_b + b"\nendstream",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"]
    out, offsets = bytearray(b"%PDF-1.4\n"), []
    for i, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    return bytes(out)


# ------------------------------------------------------------------ regras

@pytest.mark.parametrize("name, exam", [
    ("Prova I: 12/11", True), ("PROVA 2 - 2ª chamada", True), ("Exame especial", True),
    ("Atividades Práticas Avaliativas – JavaScript", False), ("Desafio - Ciclo 2", False),
    ("Aprovação do projeto", False), ("Provas anteriores (material)", False),
])
def test_is_exam(name, exam):
    assert R.is_exam(name) is exam


def test_parse_avin_date_ignores_second_call():
    assert PL.parse_avin_date(PLANOGRAMA_TEXT) == date(2026, 12, 2)
    assert PL.parse_avin_date("10/12/2026 AVIN - 2º chamada\n02/12/2026 AVIN") == date(2026, 12, 2)
    assert PL.parse_avin_date("a definir AVIN\n12/11/2026 Prova 1") is None
    assert PL.parse_avin_date("") is None


def test_find_planograma_topic_and_pdf_url():
    t = PL.find_planograma_topic(CONTENTS["1"])
    assert t["id"] == 9 and PL.topic_revision(t) == "9@2026-10-18 13:16:45.651091+00"
    assert PL.find_planograma_topic(CONTENTS["2"]) is None
    assert PL.pdf_url(planograma_topic_json()) == PLANOGRAMA_PDF_URL
    assert PL.pdf_url({"topics": {"content": {"html": "<p>sem arquivo</p>"}}}) is None


def test_pdf_text_reads_generated_pdf(qapp):
    text = PL.pdf_text(make_pdf(["12/11/2026 Prova 1", "02/12/2026 AVIN", "a definir AVIN - 2º chamada"]))
    assert PL.parse_avin_date(text) == date(2026, 12, 2)
    with pytest.raises(ValueError):
        PL.pdf_text(b"isto nao e um pdf")


# ------------------------------------------------------------------ atualização

def _run(db, **behaviour):
    f = factory(**behaviour)
    Updater(db, Credentials("aluno", "x"), headless=True, cancel=threading.Event(), client_factory=f).run()
    return f.holder["client"]


def _avin(db, course_id="1"):
    return next(i for i in db.list_course_info() if i["course_id"] == course_id)


def test_update_reads_avin_once_per_planograma_version(qapp, db):
    pdf = make_pdf(["02/12/2026 AVIN"])
    c = _run(db, pdf=pdf)
    assert c.planograma_calls == ["topic:9", "download"]          # só Banco de Dados tem Planograma
    assert _avin(db)["avin_date"] == "2026-12-02" and _avin(db, "2")["avin_date"] is None
    c = _run(db, pdf=pdf)
    assert c.planograma_calls == []                                # mesma versão do documento: não baixa de novo
    CONTENTS["1"]["topics"][0]["children"][0]["modifiedAt"] = "2026-11-01 10:00:00+00"
    try:
        c = _run(db, pdf=make_pdf(["09/12/2026 AVIN"]))
        assert c.planograma_calls == ["topic:9", "download"] and _avin(db)["avin_date"] == "2026-12-09"
    finally:
        CONTENTS["1"]["topics"][0]["children"][0]["modifiedAt"] = "2026-10-18 13:16:45.651091+00"


def test_planograma_failure_does_not_break_update(db):
    _run(db)                                                       # download falha (sem "pdf")
    assert _avin(db)["avin_date"] is None and _avin(db)["planograma_rev"] is None    # tenta de novo na próxima
    assert {a.name for a in db.list_activities()} >= {"Trabalho prático", "Prova I: 12/11"}


def test_course_info_migration_adds_avin_columns(db_path):
    import sqlite3
    from app.database.db import Database
    con = sqlite3.connect(db_path)
    con.execute("CREATE TABLE course_info (course_id TEXT PRIMARY KEY, name TEXT NOT NULL, start_date TEXT, "
                "progress REAL, meetings TEXT, updated_at TEXT)")
    con.execute("INSERT INTO course_info(course_id, name) VALUES('7', 'Antiga')")
    con.commit()
    con.close()
    d = Database(db_path)
    try:
        assert d.list_course_info()[0]["avin_date"] is None
        d.save_course_avin("7", "2026-12-02", "rev")
        assert d.list_course_info()[0]["avin_date"] == "2026-12-02"
    finally:
        d.close()


# ------------------------------------------------------------------ interface

class _Creds:
    def username(self):
        return "aluno"

    def load(self):
        return Credentials("aluno", "x")


def _seed(db):
    now = datetime.now(TZ)
    exam_day = (now + timedelta(days=5)).replace(hour=23, minute=59, second=59, microsecond=0)
    SyncService(db).apply([
        ScrapedActivity(name="Prova I: 12/11", course="Banco de Dados", source_id="p1", due_at=exam_day),
        ScrapedActivity(name="Trabalho prático", course="Banco de Dados", source_id="t1",
                        due_at=(now + timedelta(days=3)).replace(hour=10, minute=0)),
    ], ["Banco de Dados"])
    start = (now - timedelta(days=20)).date().isoformat()
    avin = (now + timedelta(days=10)).date()
    for cid, name in (("1", "Banco de Dados"), ("2", "Redes")):
        db.save_course_info(cid, name, start, 40.0)
        db.save_course_avin(cid, avin.isoformat(), "r")
    return exam_day.date(), avin


def test_exams_leave_board_and_home(qapp, db):
    from app.ui.board import BoardPage, Card
    from app.ui.context import AppContext
    from app.ui.home import HomePage
    _seed(db)
    ctx = AppContext(db, _Creds())
    board = BoardPage(ctx)
    assert [c.a.name for c in board.findChildren(Card)] == ["Trabalho prático"]
    home = HomePage(ctx)
    assert home.t_todo.value.text() == "1"


def test_agenda_shows_exams_and_avin_as_prova(qapp, db):
    from app.ui.agenda_page import AgendaPage, EntryRow
    from app.ui.context import AppContext
    from app.ui.widgets import Pill
    exam_day, avin = _seed(db)
    db.set_meta("agenda_show_linked", "0")                         # provas aparecem mesmo sem os itens ligados
    page = AgendaPage(AppContext(db, _Creds()))
    rows = {r.entry.title: r for r in page.findChildren(EntryRow)}
    assert set(rows) == {"Prova I: 12/11", "AVIN"}
    for r in rows.values():
        assert r.entry.kind == "exam" and [p.text() for p in r.findChildren(Pill)] == ["Prova"]
    assert rows["Prova I: 12/11"].entry.day == exam_day and rows["Prova I: 12/11"].entry.aid is not None
    assert rows["AVIN"].entry.day == avin and "Banco de Dados, Redes" in rows["AVIN"].entry.subtitle  # uma só
