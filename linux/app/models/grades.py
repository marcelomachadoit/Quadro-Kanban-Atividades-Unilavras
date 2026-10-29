"""Modelos de notas: disciplinas (Grade de Notas da Plataforma A) e resultados do AVIN."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Optional

AVIN_POINTS_PER_QUESTION = 1.25

# situação de cada questão no AVIN (classes CSS do portal avalia.grupoa.com.br)
Q_CORRECT, Q_WRONG, Q_DOUBLE, Q_BLANK, Q_ANNULLED, Q_WAIVED = (
    "correta", "incorreta", "dupla", "branco", "anulada", "dispensada")
Q_LABELS = {
    Q_CORRECT: "Acerto", Q_WRONG: "Erro", Q_DOUBLE: "Marcação dupla", Q_BLANK: "Em branco",
    Q_ANNULLED: "Anulada", Q_WAIVED: "Dispensada",
}


@dataclass
class GradeItem:
    name: str
    value: Optional[float]           # nota obtida (None = ainda sem nota)
    max_value: Optional[float] = None  # quanto a atividade vale, quando conhecido
    deadline: Optional[str] = None   # ISO
    submitted_at: Optional[str] = None
    completed: bool = False
    revised: bool = False
    deadline_expired: bool = False

    @property
    def status(self) -> str:
        if self.value is not None:
            return "Corrigida"
        if self.completed:
            return "Aguardando correção"
        if self.deadline_expired:
            return "Não entregue"
        return "Pendente"


@dataclass
class GradeCategory:
    name: str
    value: Optional[float]
    items: list = field(default_factory=list)   # list[GradeItem]

    @property
    def max_value(self) -> Optional[float]:
        vals = [i.max_value for i in self.items if i.max_value is not None]
        return sum(vals) if vals else None


@dataclass
class CourseGrade:
    course_id: str
    name: str
    start_date: Optional[str]        # AAAA-MM-DD
    progress: Optional[float]
    completed: bool
    final: Optional[float]
    categories: list = field(default_factory=list)   # list[GradeCategory]
    url: Optional[str] = None

    @property
    def key(self) -> str:
        return f"course:{self.course_id}"

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "CourseGrade":
        cats = [GradeCategory(name=c["name"], value=c.get("value"),
                              items=[GradeItem(**i) for i in c.get("items", [])]) for c in d.get("categories", [])]
        return CourseGrade(**{**d, "categories": cats})


@dataclass
class AvinQuestion:
    number: int
    answer: str
    state: str


@dataclass
class AvinResult:
    avin_id: str
    name: str
    period: str
    start: Optional[str]             # ISO (início da prova)
    questions: list = field(default_factory=list)    # list[AvinQuestion]
    url: Optional[str] = None

    @property
    def key(self) -> str:
        return f"avin:{self.avin_id}"

    @property
    def correct(self) -> int:
        return sum(q.state == Q_CORRECT for q in self.questions)

    @property
    def score(self) -> float:
        """Regra definida pelo usuário: cada questão marcada em verde (correta) vale 1,25."""
        return self.correct * AVIN_POINTS_PER_QUESTION

    @property
    def max_score(self) -> float:
        return len(self.questions) * AVIN_POINTS_PER_QUESTION

    def count(self, state: str) -> int:
        return sum(q.state == state for q in self.questions)

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "AvinResult":
        return AvinResult(**{**d, "questions": [AvinQuestion(**q) for q in d.get("questions", [])]})


def module_numbers(courses: list["CourseGrade"]) -> dict[str, int]:
    """Módulo de cada disciplina, definido pela data de início: 1ª data = módulo 1, 2ª data = módulo 2..."""
    starts = sorted({c.start_date for c in courses if c.start_date})
    return {c.course_id: starts.index(c.start_date) + 1 for c in courses if c.start_date}


def apply_module_rule(courses: list["CourseGrade"], today: Optional["date"] = None) -> list["CourseGrade"]:
    """Quando um módulo novo já começou, todas as disciplinas dos módulos anteriores ficam concluídas.

    Só conta como "módulo novo disponível" uma data de início que já chegou (disciplinas "em breve" não contam).
    """
    from datetime import date as _date
    today = today or _date.today()
    started = sorted({c.start_date for c in courses if c.start_date and c.start_date <= today.isoformat()})
    if len(started) < 2:
        return courses
    current = started[-1]
    for c in courses:
        if c.start_date and c.start_date < current:
            c.completed = True
    return courses


def avin_module_start(avin: "AvinResult", courses: list["CourseGrade"]) -> Optional[str]:
    """Data de início do módulo do AVIN: o módulo mais recente que já tinha começado no dia da prova."""
    if not avin.start:
        return None
    day = avin.start[:10]
    starts = sorted({c.start_date for c in courses if c.start_date and c.start_date <= day})
    return starts[-1] if starts else None


def assign_avins(courses: list["CourseGrade"], avins: list["AvinResult"]) -> tuple[dict, list]:
    """Associa cada AVIN às disciplinas do seu módulo.

    Retorna ({course_id: [AvinResult, ...]}, [AVINs sem módulo correspondente]).
    """
    by_course: dict[str, list] = {}
    orphans = []
    for av in sorted(avins, key=lambda a: a.start or ""):
        start = avin_module_start(av, courses)
        if start is None:
            orphans.append(av)
            continue
        for c in courses:
            if c.start_date == start:
                by_course.setdefault(c.course_id, []).append(av)
    return by_course, orphans


def portal_has_avin(cg: "CourseGrade") -> bool:
    """O portal já lançou o AVIN na Grade de Notas da disciplina? (evita somar duas vezes)"""
    import re as _re
    return any(_re.search(r"\bavin\b", i.name, _re.I) and i.value is not None
               for cat in cg.categories for i in cat.items)


def course_total(cg: "CourseGrade", avins: list["AvinResult"]) -> Optional[float]:
    """Nota final da disciplina = nota do portal + AVIN(s) do módulo (sempre somados)."""
    if cg.final is None and not avins:
        return None
    extra = 0.0 if portal_has_avin(cg) else sum(a.score for a in avins)
    return round((cg.final or 0.0) + extra, 2)


def fmt_num(v: Optional[float]) -> str:
    """70.8 -> "70,8"; 21.25 -> "21,25"; 4.0 -> "4"; None -> "-"."""
    if v is None:
        return "-"
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return s.replace(".", ",")
