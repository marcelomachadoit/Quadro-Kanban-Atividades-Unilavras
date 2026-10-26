"""Encontros virtuais das disciplinas e informações básicas de cada disciplina (para o calendário)."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from typing import Optional

WEEKDAY_NAMES = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]
WEEKDAY_PLURAL = ["segundas", "terças", "quartas", "quintas", "sextas", "sábados", "domingos"]


@dataclass
class Meeting:
    kind: str                      # "weekly" (toda semana) | "date" (data específica)
    weekday: Optional[int] = None  # 0 = segunda ... 6 = domingo
    date: Optional[str] = None     # AAAA-MM-DD
    time: Optional[str] = None     # HH:MM
    title: str = ""

    def describe(self) -> str:
        t = f" às {self.time}" if self.time else ""
        if self.kind == "weekly" and self.weekday is not None:
            return f"Toda {WEEKDAY_NAMES[self.weekday]}{t}" if self.weekday < 5 else f"Todo {WEEKDAY_NAMES[self.weekday]}{t}"
        if self.date:
            y, m, d = self.date.split("-")
            return f"{d}/{m}{t}"
        return self.title


@dataclass
class CourseInfo:
    course_id: str
    name: str
    start_date: Optional[str]
    progress: Optional[float]
    meetings: list = field(default_factory=list)    # list[Meeting]

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "CourseInfo":
        return CourseInfo(**{**d, "meetings": [Meeting(**m) for m in d.get("meetings") or []]})


def occurrences(info: CourseInfo, first: date, last: date) -> list[tuple[date, Meeting]]:
    """Datas de encontro entre ``first`` e ``last`` (inclusive). Semanais só a partir do início da disciplina."""
    start = date.fromisoformat(info.start_date) if info.start_date else first
    out: dict[date, Meeting] = {}
    for m in info.meetings:
        if m.kind == "weekly" and m.weekday is not None:
            d = max(first, start)
            d += timedelta(days=(m.weekday - d.weekday()) % 7)
            while d <= last:
                out.setdefault(d, m)
                d += timedelta(days=7)
    for m in info.meetings:
        if m.kind == "date" and m.date:
            d = date.fromisoformat(m.date)
            if first <= d <= last and d not in out:      # o encontro semanal do mesmo dia já cobre a data
                out[d] = m
    return sorted(out.items(), key=lambda x: x[0])


def next_meeting(info: CourseInfo, now: Optional[datetime] = None) -> Optional[tuple[date, Meeting]]:
    now = now or datetime.now()
    today = now.date()
    for d, m in occurrences(info, today, today + timedelta(days=60)):
        if d == today and m.time and m.time < now.strftime("%H:%M"):
            continue                                     # encontro de hoje já passou
        return d, m
    return None


def completed_ids(courses: list[CourseInfo], today: Optional[date] = None) -> set[str]:
    """Mesma regra da aba Notas: 100% concluída, ou de um módulo anterior a um módulo que já começou."""
    today = today or date.today()
    started = sorted({c.start_date for c in courses if c.start_date and c.start_date <= today.isoformat()})
    current = started[-1] if len(started) >= 2 else None
    return {c.course_id for c in courses
            if (c.progress is not None and c.progress >= 100) or (current and c.start_date and c.start_date < current)}
