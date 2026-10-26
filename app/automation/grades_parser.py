"""Interpretação das notas (sem navegador, testável com dados simulados).

Estrutura observada no portal real (out/2026):
* Plataforma A — ``GET .../v2/plataforma/grades/courses/{id}/me`` (página "Grade de Notas", ``/plataforma/my-grades/{id}``):
  ``{"name", "finalGrade": {"value"}, "gradeCategories": [{"name", "value", "gradeBooks": [{"name", "value",
  "deadlineAt", "submittedAt", "isCompleted", "isRevised", "isDeadlineExpired", "topicTypeId"}]}]}``.
  ``value`` do gradeBook é a nota OBTIDA; quanto a atividade vale vem do conteúdo da disciplina (``grade.value``).
* AVIN — ``avalia.grupoa.com.br``: tabela ``/ResultadoAluno/Tabela/?apenasAvaliacoesVigentes=false&
  apenasResultadosDisponiveis=true`` (linhas: código, nome, período, link "Visualizar Resultados") e respostas em
  ``/ResultadoAluno/FormularioRespostas?idAlunoAvaliacao={id}``: ``<a class="btn btn-app correta">`` com o número da
  questão em ``<span class="badge">`` e a alternativa marcada. Verde = classe ``correta``.
"""
from __future__ import annotations

import re
from datetime import date
from html import unescape
from html.parser import HTMLParser
from typing import Optional

from app.models.activity import Course, dt_to_iso
from app.models.grades import (Q_ANNULLED, Q_BLANK, Q_CORRECT, Q_DOUBLE, Q_WAIVED, Q_WRONG, AvinQuestion, AvinResult,
                               CourseGrade, GradeCategory, GradeItem)
from app.services import rules as R

Q_STATES = (Q_CORRECT, Q_WRONG, Q_DOUBLE, Q_BLANK, Q_ANNULLED, Q_WAIVED)


def _num(v) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        return float(str(v).replace(",", "."))
    except ValueError:
        return None


def _iso(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    return dt_to_iso(R.parse_datetime_br(str(value)[:19]).dt)


def max_points_from_contents(contents: Optional[dict]) -> dict[str, float]:
    """Mapa nome normalizado -> quanto a atividade vale (``grade.value`` dos tópicos com nota)."""
    out: dict[str, float] = {}

    def walk(ts):
        for t in ts or []:
            if t.get("hasGrade"):
                v = _num((t.get("grade") or {}).get("value"))
                if v is not None:
                    out.setdefault(R.normalize(t.get("title")), v)
            walk(t.get("children"))
    walk((contents or {}).get("topics"))
    return out


def parse_course_grades(data: dict, course: Course, contents: Optional[dict] = None,
                        today: Optional[date] = None, base_url: str = "") -> CourseGrade:
    today = today or date.today()
    maxes = max_points_from_contents(contents)
    cats = []
    for c in (data or {}).get("gradeCategories") or []:
        items = []
        for g in c.get("gradeBooks") or []:
            name = R.clean_text(g.get("name")) or "-"
            items.append(GradeItem(
                name=name, value=_num(g.get("value")), max_value=maxes.get(R.normalize(name)),
                deadline=_iso(g.get("deadlineAt")), submitted_at=_iso(g.get("submittedAt")),
                completed=bool(g.get("isCompleted")), revised=bool(g.get("isRevised")),
                deadline_expired=bool(g.get("isDeadlineExpired"))))
        cats.append(GradeCategory(name=R.clean_text(c.get("name")) or "-", value=_num(c.get("value")), items=items))
    fg = (data or {}).get("finalGrade") or {}
    final = _num(fg.get("value")) if fg.get("isVisible", True) else None
    ctx = (contents or {}).get("context") or {}
    expired = bool(ctx.get("isAcademicMainExpired"))
    completed = (course.progress is not None and course.progress >= 100) or expired
    return CourseGrade(course_id=str(course.source_id), name=R.clean_text((data or {}).get("name")) or course.name,
                       start_date=course.start_date or ctx.get("academicMainStartAt"), progress=course.progress,
                       completed=completed, final=final, categories=cats,
                       url=f"{base_url}/plataforma/my-grades/{course.source_id}" if base_url else None)


# ---------------------------------------------------------------------- HTML do AVIN

class _TableParser(HTMLParser):
    """Extrai as linhas da tabela de resultados: células de texto e links."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows: list[dict] = []
        self._in_tbody = False
        self._row: Optional[dict] = None
        self._cell: Optional[list] = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "tbody":
            self._in_tbody = True
        elif tag == "tr" and self._in_tbody:
            self._row = {"cells": [], "links": []}
        elif tag == "td" and self._row is not None:
            self._cell = []
        elif tag == "a" and self._row is not None and a.get("href"):
            self._row["links"].append(a["href"])

    def handle_endtag(self, tag):
        if tag == "td" and self._row is not None and self._cell is not None:
            self._row["cells"].append(R.clean_text("".join(self._cell)))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self.rows.append(self._row)
            self._row = None
        elif tag == "tbody":
            self._in_tbody = False

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


def parse_avin_table(html: str, only_avin: bool = True) -> list[dict]:
    """Linhas com resultado disponível: {"id", "name", "period", "start", "results_href"}."""
    p = _TableParser()
    p.feed(html or "")
    out = []
    for r in p.rows:
        cells = r["cells"]
        href = next((h for h in r["links"] if "VisualizarResultados" in h), None)
        if len(cells) < 3 or not href:
            continue
        m = re.search(r"idAlunoAvaliacao=(\d+)", href)
        name = cells[1]
        if only_avin and not re.search(r"\bavin\b", R.normalize(name)):
            continue
        start = R.parse_datetime_br(cells[2].split(" a ")[0])
        out.append({"id": m[1] if m else cells[0], "name": name, "period": cells[2],
                    "start": dt_to_iso(start.dt), "results_href": unescape(href)})
    return out


class _AnswersParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.questions: list[AvinQuestion] = []
        self._cur: Optional[dict] = None
        self._in_badge = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = (a.get("class") or "").split()
        if tag == "a" and "btn-app" in cls:
            state = next((s for s in Q_STATES if s in cls), None)
            self._cur = {"state": state, "num": "", "text": ""}
        elif tag == "span" and self._cur is not None and "badge" in cls:
            self._in_badge = True

    def handle_endtag(self, tag):
        if tag == "span":
            self._in_badge = False
        elif tag == "a" and self._cur is not None:
            num = re.sub(r"\D", "", self._cur["num"])
            if num and self._cur["state"]:
                self.questions.append(AvinQuestion(number=int(num), answer=R.clean_text(self._cur["text"]),
                                                   state=self._cur["state"]))
            self._cur = None

    def handle_data(self, data):
        if self._cur is not None:
            self._cur["num" if self._in_badge else "text"] += data


def parse_avin_answers(html: str) -> list[AvinQuestion]:
    p = _AnswersParser()
    p.feed(html or "")
    return sorted(p.questions, key=lambda q: q.number)


def build_avin(row: dict, answers_html: str, base_url: str = "") -> AvinResult:
    return AvinResult(avin_id=str(row["id"]), name=row["name"], period=row["period"], start=row.get("start"),
                      questions=parse_avin_answers(answers_html),
                      url=f"{base_url}{row['results_href']}" if base_url else row["results_href"])
