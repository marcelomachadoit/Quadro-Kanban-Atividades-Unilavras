"""Eventos da Unilavras (página "Eventos > Inscrição" do portal)."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
from typing import Optional

from app.models.activity import iso_to_dt


@dataclass
class PortalEvent:
    key: str                          # endereço da inscrição (ou título + data quando não há link)
    title: str
    date: str                         # AAAA-MM-DD (data exibida na lista de eventos)
    url: Optional[str] = None
    start_at: Optional[str] = None    # ISO com horário, quando a página do evento informa
    end_at: Optional[str] = None
    location: Optional[str] = None
    description: Optional[str] = None
    first_seen: Optional[str] = None

    @property
    def day(self) -> Optional[date]:
        try:
            return date.fromisoformat(self.date)
        except (TypeError, ValueError):
            return None

    @property
    def start(self) -> Optional[datetime]:
        return iso_to_dt(self.start_at)

    @property
    def time(self) -> Optional[str]:
        """"HH:MM" de início, só quando cai no mesmo dia da lista (evita horários de páginas desatualizadas)."""
        s = self.start
        if s and self.day and s.date() == self.day and (s.hour, s.minute) != (0, 0):
            return f"{s:%H:%M}"
        return None

    def is_upcoming(self, today: date) -> bool:
        return self.day is not None and self.day >= today

    def to_dict(self) -> dict:
        return asdict(self)
