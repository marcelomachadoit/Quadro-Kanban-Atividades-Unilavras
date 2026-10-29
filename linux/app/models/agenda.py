"""Agenda pessoal: compromissos criados pelo aluno (aulas, provas, estudos, eventos…)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Optional

CATEGORIES = ["Aula", "Prova", "Estudo", "Trabalho", "Evento", "Pessoal", "Outro"]
DEFAULT_CATEGORY = "Outro"


@dataclass
class AgendaItem:
    title: str
    day: str                          # AAAA-MM-DD
    start_time: Optional[str] = None  # "HH:MM"; vazio = dia inteiro
    end_time: Optional[str] = None
    location: str = ""
    category: str = DEFAULT_CATEGORY
    notes: str = ""
    done: bool = False
    source_key: Optional[str] = None  # "evento:<chave>" quando veio da aba Eventos
    id: Optional[int] = None

    @property
    def date(self) -> date:
        return date.fromisoformat(self.day)

    @property
    def all_day(self) -> bool:
        return not self.start_time

    def starts_at(self) -> datetime:
        t = time.fromisoformat(self.start_time) if self.start_time else time(0, 0)
        return datetime.combine(self.date, t)

    def time_range(self) -> str:
        if not self.start_time:
            return "Dia inteiro"
        return f"{self.start_time}–{self.end_time}" if self.end_time else self.start_time

    def sort_key(self) -> tuple:
        return self.day, self.start_time or "", self.title.lower()
