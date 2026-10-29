"""Notas: Grade de Notas (Plataforma A), AVIN (acertos × 1,25), ordem cronológica, atualização só de notas e aba."""
import os
from datetime import date

import pytest

from app.automation import grades_parser as G
from app.models.activity import Course
from app.models.grades import AvinResult, CourseGrade, fmt_num
from app.services.credentials import Credentials
from app.services.grades_updater import GradesUpdater
from tests.fakes import FakeClient, contents, topic

GRADES_ALG = {
    "academicMainId": 3, "name": "Algoritmos (GRDESISL232)", "finalGrade": {"value": 70.8, "isVisible": True},
    "gradeCategories": [
        {"name": "Atividades avaliativas", "value": 36.8, "gradeBooks": [
            {"name": "Atividade Teórica - Ciclo 1", "value": 2, "deadlineAt": "2026-08-20 23:30:00",
             "submittedAt": "2026-08-11 20:32:48.024", "isCompleted": True, "isRevised": True,
             "isDeadlineExpired": True},
            {"name": "P1", "value": 19.8, "deadlineAt": None, "submittedAt": None, "isCompleted": False,
             "isRevised": True, "isDeadlineExpired": False},
            {"name": "Atividade presencial", "value": None, "deadlineAt": "2026-09-10 20:30:00", "submittedAt": None,
             "isCompleted": False, "isRevised": False, "isDeadlineExpired": True},
        ]},
        {"name": "Atividades práticas", "value": 34, "gradeBooks": [
            {"name": "Trabalho prático", "value": 15, "deadlineAt": "2026-10-02 23:59:00",
             "submittedAt": "2026-09-24 15:01:59", "isCompleted": True, "isRevised": True, "isDeadlineExpired": True},
        ]},
    ]}
CONTENTS_ALG = contents(3, "Algoritmos (GRDESISL232)", [
    topic(1, "Ciclo I", 1, 1, children=[topic(11, "Atividade Teórica - Ciclo 1", 15, 8, grade=2)]),
    topic(2, "Prova I", 1, 1, children=[topic(21, "P1", 8, 5, grade=20)]),
    topic(3, "Trabalho prático", 8, 5, grade=15),
], start="2026-06-11")
GRADES_FE = {"name": "Front-End II (GRDESISL236)", "finalGrade": {"value": 0, "isVisible": True},
             "gradeCategories": [{"name": "Atividades avaliativas", "value": None, "gradeBooks": [
                 {"name": "Lista 1", "value": None, "deadlineAt": "2026-10-23 23:59:00",
                  "submittedAt": "2026-10-20 10:00:00", "isCompleted": True, "isRevised": False,
                  "isDeadlineExpired": True}]}]}

AVIN_TABLE = """<div class="table-responsive"><table class="table table-striped" id="tabelaResultadosAluno"><thead><tr>
<th>Código</th><th>Nome</th><th>Período</th><th>Resultados</th><th>Resumo de recursos</th></tr></thead><tbody>
<tr><td>46671646</td><td>AVIN EAD 1&#xB0; m&#xF3;dulo - 2026/2 - Curso Superior de Tecnologia em ADS - 1&#xBA; PER&#xCD;ODO</td>
<td data-sort="1">30/09/2026 19:00 a 30/09/2026 22:00</td><td><a href="/ResultadoAluno/VisualizarResultados?idAlunoAvaliacao=46671646"
class="btn btn-success">Visualizar Resultados</a></td><td><a href="/SolicitarRecursoQuestao/RecursosRegistrados?idAlunoAvaliacao=46671646"
class="btn btn-success">Visualizar Recursos Registrados</a></td></tr>
<tr><td>45813569</td><td>P1 ADS - 1&#xB0; m&#xF3;dulo 2026/2</td><td>03/09/2026 19:00 a 03/09/2026 22:00</td>
<td><a href="/ResultadoAluno/VisualizarResultados?idAlunoAvaliacao=45813569" class="btn btn-success">Visualizar Resultados</a></td>
<td><span class="btn btn-dark" disabled="disabled">Não disponível</span></td></tr></tbody></table></div>"""


def answers_html(states):
    out = ['<div class="x_content numQuestoes">']
    for i, (st, alt) in enumerate(states, 1):
        out.append(f'<a class="btn btn-app {st}" onClick=alertaForaPeriodo() title="Visualizar questão">'
                   f'<span class="badge bg-darkblue-3"> {i}</span> {alt} </a>')
    out.append('</div><p><i class="fa fa-square color-correta"></i> Questão Marcada Corretamente</p>')
    return "".join(out)


ANSWERS = answers_html([("correta", "B")] * 4 + [("incorreta", "B")] + [("correta", "E")] * 3 + [("incorreta", "C")]
                       + [("correta", "A")] * 2 + [("incorreta", "E")] + [("correta", "B")] * 7 + [("anulada", "A")])


# ------------------------------------------------------------------ interpretação

def test_course_grades_obtained_vs_max_and_status():
    co = Course(name="Algoritmos", progress=96.0, source_id="3", start_date="2026-06-11")
    cg = G.parse_course_grades(GRADES_ALG, co, CONTENTS_ALG, base_url="https://x")
    assert cg.final == 70.8 and not cg.completed                     # 96% => em andamento
    av = cg.categories[0]
    assert (av.name, av.value) == ("Atividades avaliativas", 36.8)
    t1, p1, pres = av.items
    assert (t1.value, t1.max_value, t1.status) == (2, 2, "Corrigida")
    assert (p1.value, p1.max_value) == (19.8, 20)                    # nota obtida × quanto vale
    assert pres.value is None and pres.status == "Não entregue"
    assert t1.submitted_at.startswith("2026-08-11T20:32")
    assert cg.url == "https://x/plataforma/my-grades/3"


def test_course_completed_and_awaiting_grading():
    done = G.parse_course_grades(GRADES_FE, Course(name="FE", progress=100.0, source_id="9"), None)
    assert done.completed
    assert done.categories[0].items[0].status == "Aguardando correção"
    assert done.final == 0


def test_avin_table_only_avin_rows_with_results():
    rows = G.parse_avin_table(AVIN_TABLE)
    assert len(rows) == 1                                            # a P1 não é AVIN
    r = rows[0]
    assert r["id"] == "46671646" and r["name"].startswith("AVIN EAD 1° módulo")
    assert r["start"] == "2026-09-30T19:00:00-03:00"
    assert len(G.parse_avin_table(AVIN_TABLE, only_avin=False)) == 2


def test_avin_score_is_green_count_times_1_25():
    av = G.build_avin(G.parse_avin_table(AVIN_TABLE)[0], ANSWERS, "https://avalia")
    assert len(av.questions) == 20
    assert av.correct == 16                                          # só as verdes contam
    assert av.score == 16 * 1.25 == 20.0
    assert av.max_score == 25.0
    assert av.count("incorreta") == 3 and av.count("anulada") == 1
    assert [q.number for q in av.questions if q.state == "incorreta"] == [5, 9, 12]
    assert av.questions[0].answer == "B"
    assert fmt_num(17 * 1.25) == "21,25"


def test_fmt_num():
    assert (fmt_num(70.8), fmt_num(4.0), fmt_num(None), fmt_num(36.75)) == ("70,8", "4", "-", "36,75")


# ------------------------------------------------------------------ persistência e ordem cronológica

def test_snapshots_persist_in_chronological_order(db_path):
    from app.database.db import Database
    d = Database(db_path)
    late = CourseGrade("2", "Front-End II", "2026-10-05", 40.0, False, 0.0)
    early = CourseGrade("1", "Algoritmos", "2026-06-11", 96.0, False, 70.8)
    avin = AvinResult("9", "AVIN EAD 1° módulo", "30/09/2026", "2026-09-30T19:00:00-03:00")
    for x, kind, key in ((late, "course", late.start_date), (avin, "avin", avin.start), (early, "course", early.start_date)):
        d.save_grade_snapshot(x.key, kind, x.to_dict(), key)
    d.save_grade_snapshot(early.key, "course", {**early.to_dict(), "final": 72.0}, early.start_date)   # atualiza
    d.close()
    d2 = Database(db_path)                                           # reinício
    snaps = d2.list_grade_snapshots()
    assert [p.get("name") for _, p, _ in snaps] == ["Algoritmos", "AVIN EAD 1° módulo", "Front-End II"]
    assert CourseGrade.from_dict(snaps[0][1]).final == 72.0
    d2.close()


# ------------------------------------------------------------------ atualização somente das notas

class GradesFake(FakeClient):
    avin_base = "https://avalia.grupoa.com.br"

    def course_contents(self, course):
        return CONTENTS_ALG if course.source_id == "1" else {"topics": []}

    def course_grades(self, course):
        if self.b.get("grade_fail") == course.source_id:
            from app.automation.portal import AutomationError
            raise AutomationError("o portal não respondeu")
        return GRADES_ALG if course.source_id == "1" else GRADES_FE

    def open_avin(self):
        if self.b.get("avin_fail"):
            from app.automation.portal import StructureChanged
            raise StructureChanged("Não encontrei a opção \"AVIN\" no portal.")

    def avin_results_table(self):
        return AVIN_TABLE

    def avin_answers(self, href, avin_id):
        return ANSWERS


def _run(db, **b):
    return GradesUpdater(db, Credentials("u", "p"), client_factory=lambda **kw: GradesFake(behaviour=b, **kw)).run()


def test_grades_update_reads_all_courses_and_avin(db):
    r = _run(db)
    assert not r.errors and len(r.courses_ok) == 5                   # todas as matérias, inclusive >= 95%
    assert r.avins == [(r.avins[0][0], "20 de 25")]
    kinds = [k for k, _, _ in db.list_grade_snapshots()]
    assert kinds.count("course") == 5 and kinds.count("avin") == 1
    assert db.get_meta("last_grades_update")
    assert db.list_activities() == []                                # não mexe no quadro


def test_grades_update_partial_failures_are_reported(db):
    r = _run(db, grade_fail="2", avin_fail=True)
    assert [c for c, _ in r.courses_failed] == ["Redes"]
    assert "AVIN" in r.avin_error
    assert "Não foi possível ler o AVIN" in r.summary_text()


def test_grades_update_login_failure(db):
    r = _run(db, login_fail=True)
    assert r.errors and db.list_grade_snapshots() == []


# ------------------------------------------------------------------ aba Notas

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


def test_grades_page_cards_status_and_dropdown(qapp, db):
    from app.ui.context import AppContext
    from app.ui.grades_page import GradeCard, GradesPage, short_avin
    _run(db)
    page = GradesPage(AppContext(db, _Creds()))
    cards = [page.list.itemAt(i).widget() for i in range(page.list.count())]
    cards = [c for c in cards if isinstance(c, GradeCard)]
    assert len(cards) == 5                                           # AVIN não é um cartão próprio
    assert not any(c.key.startswith("avin:") for c in cards)

    def texts(w):
        from PySide6.QtWidgets import QLabel
        return " | ".join(l.text() for l in w.findChildren(QLabel))
    joined = [texts(c.head) for c in cards]
    assert any("Matéria concluída" in t for t in joined) and any("Em andamento" in t for t in joined)
    assert any("70,8" in t and "nota atual" in t for t in joined)        # módulo atual: em andamento, sem AVIN
    # disciplinas do módulo anterior (início 11/06) ficam concluídas mesmo abaixo de 100%
    prev = [t for t in joined if "Módulo 1" in t]
    assert len(prev) == 3 and all("Matéria concluída" in t and "nota total" in t for t in prev)
    assert all("Em andamento" in t for t in joined if "Módulo 2" in t)
    # AVIN de 30/09 pertence ao módulo de 11/06: soma 20 (16 × 1,25) à nota de cada matéria desse módulo
    assert all("| 20 |" in t and "com AVIN" in t for t in prev)
    assert not any("com AVIN" in t for t in joined if "Módulo 2" in t)
    card = next(c for c in cards if "Módulo 1" in texts(c.head))
    assert card.body.isHidden()                                      # recolhido por padrão
    card.set_expanded(True, emit=True)
    body = texts(card.body)
    assert "AVIN DO MÓDULO" in body and "16" in body and "1,25" in body and "= 20" in body
    page.refresh()                                                   # expansão é lembrada
    again = next(page.list.itemAt(i).widget() for i in range(page.list.count())
                 if getattr(page.list.itemAt(i).widget(), "key", "") == card.key)
    assert not again.body.isHidden()
    assert short_avin("AVIN EAD 1° módulo - 2026/2 - Curso Superior de X") == "AVIN EAD 1° módulo - 2026/2"


def test_grades_page_empty_state(qapp, db):
    from app.ui.context import AppContext
    from app.ui.grades_page import GradesPage
    page = GradesPage(AppContext(db, _Creds()))
    assert "Nenhuma nota" in page.list.itemAt(0).widget().findChildren(__import__("PySide6.QtWidgets",
                                                                                   fromlist=["QLabel"]).QLabel)[1].text()


# ------------------------------------------------------------------ regra dos módulos

def _cg(cid, start, progress):
    return CourseGrade(cid, f"Matéria {cid}", start, progress, progress >= 100, 50.0)


def test_previous_module_always_completed_when_new_module_started():
    from app.models.grades import apply_module_rule, module_numbers
    cs = [_cg("a", "2026-06-11", 96.0), _cg("b", "2026-06-11", 99.0), _cg("c", "2026-06-11", 100.0),
          _cg("d", "2026-10-05", 40.0), _cg("e", "2026-10-05", 35.0)]
    apply_module_rule(cs, today=date(2026, 10, 26))
    assert [c.completed for c in cs] == [True, True, True, False, False]
    assert module_numbers(cs) == {"a": 1, "b": 1, "c": 1, "d": 2, "e": 2}


def test_module_rule_ignores_module_not_started_yet():
    from app.models.grades import apply_module_rule
    cs = [_cg("a", "2026-06-11", 96.0), _cg("d", "2026-10-05", 0.0)]
    apply_module_rule(cs, today=date(2026, 9, 1))          # módulo 2 ainda "em breve"
    assert [c.completed for c in cs] == [False, False]


def test_module_rule_three_modules_and_single_module():
    from app.models.grades import apply_module_rule
    cs = [_cg("a", "2026-02-01", 50.0), _cg("b", "2026-06-11", 50.0), _cg("c", "2026-10-05", 50.0)]
    apply_module_rule(cs, today=date(2026, 10, 26))
    assert [c.completed for c in cs] == [True, True, False]
    only = [_cg("x", "2026-10-05", 50.0)]
    assert not apply_module_rule(only, today=date(2026, 10, 26))[0].completed


# ------------------------------------------------------------------ AVIN dentro das matérias do módulo

def _avin(aid, start, correct, total=20):
    from app.models.grades import AvinQuestion
    qs = [AvinQuestion(i + 1, "A", "correta" if i < correct else "incorreta") for i in range(total)]
    return AvinResult(aid, f"AVIN {aid}", "", start, qs)


def test_avin_assigned_to_module_by_date_and_summed():
    from app.models.grades import assign_avins, course_total
    m1 = [_cg("a", "2026-06-11", 96.0), _cg("b", "2026-06-11", 100.0)]
    m2 = [_cg("c", "2026-10-05", 40.0)]
    av1 = _avin("1", "2026-09-30T19:00:00-03:00", 17)                 # prova antes do módulo 2 começar
    av2 = _avin("2", "2026-12-10T19:00:00-03:00", 10)
    by, orphans = assign_avins(m1 + m2, [av2, av1])
    assert [a.avin_id for a in by["a"]] == ["1"] and [a.avin_id for a in by["b"]] == ["1"]
    assert [a.avin_id for a in by["c"]] == ["2"] and orphans == []
    assert course_total(m1[0], by["a"]) == 50.0 + 21.25               # sempre somado à nota final
    assert course_total(m2[0], by["c"]) == 50.0 + 12.5


def test_avin_not_double_counted_when_portal_already_has_it():
    from app.models.grades import GradeCategory, GradeItem, course_total, portal_has_avin
    cg = _cg("a", "2026-06-11", 96.0)
    cg.categories = [GradeCategory("Avaliações", 21.25, [GradeItem("AVIN 1º módulo", 21.25)])]
    assert portal_has_avin(cg)
    assert course_total(cg, [_avin("1", "2026-09-30T19:00:00-03:00", 17)]) == 50.0


def test_avin_before_any_course_is_orphan():
    from app.models.grades import assign_avins, course_total
    cs = [_cg("a", "2026-06-11", 96.0)]
    by, orphans = assign_avins(cs, [_avin("0", "2026-05-01T19:00:00-03:00", 5)])
    assert by == {} and [o.avin_id for o in orphans] == ["0"]
    assert course_total(cs[0], []) == 50.0
