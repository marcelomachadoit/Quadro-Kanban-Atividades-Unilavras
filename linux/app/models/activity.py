"""Modelos de dados: disciplinas, atividades coletadas e atividades persistidas."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from app.config import MISSING, TZ

STATUS_TODO = "todo"
STATUS_DOING = "doing"
STATUS_DONE = "done"
STATUSES = (STATUS_TODO, STATUS_DOING, STATUS_DONE)
STATUS_LABELS = {STATUS_TODO: "A fazer", STATUS_DOING: "Em andamento", STATUS_DONE: "Concluído"}

# Situação na última consulta ao portal
SEEN_FOUND = "encontrada"
SEEN_NOT_FOUND = "nao_encontrada"
SEEN_MANUAL = "manual"
SEEN_LABELS = {
    SEEN_FOUND: "Encontrada na última verificação",
    SEEN_NOT_FOUND: "Não encontrada na última verificação",
    SEEN_MANUAL: "Criada manualmente",
}

# Campos que o usuário pode personalizar (sobrepõem o valor do portal)
EDITABLE_FIELDS = ("name", "course", "due_at", "points")
FIELD_LABELS = {"name": "Nome", "course": "Disciplina", "due_at": "Prazo", "points": "Pontuação"}


@dataclass
class Course:
    name: str
    progress: Optional[float]          # None = não foi possível interpretar
    url: Optional[str] = None
    source_id: Optional[str] = None
    progress_raw: str = ""
    start_date: Optional[str] = None


@dataclass
class ScrapedActivity:
    """Atividade extraída do portal (antes da persistência)."""
    name: str
    course: str
    due_at: Optional[datetime] = None  # timezone-aware (America/Sao_Paulo)
    due_raw: str = ""
    points: Optional[str] = None       # valor total da atividade, ex.: "10 pontos"
    url: Optional[str] = None
    source_id: Optional[str] = None
    kind: str = ""
    due_ambiguous: bool = False

    def display(self, value):
        return value if value not in (None, "") else MISSING


def dt_to_iso(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=TZ)
    return dt.astimezone(TZ).isoformat(timespec="seconds")


def iso_to_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=TZ)
    return dt.astimezone(TZ)


@dataclass
class Activity:
    """Registro persistido. Valores do portal e personalizações ficam separados."""
    id: Optional[int] = None
    source_key: str = ""
    source_id: Optional[str] = None
    origin: str = "portal"             # "portal" | "manual"
    # dados do portal
    portal_name: Optional[str] = None
    portal_course: Optional[str] = None
    portal_due_at: Optional[str] = None
    portal_due_raw: Optional[str] = None
    portal_points: Optional[str] = None
    url: Optional[str] = None
    # personalizações do usuário (None = usar valor do portal)
    user_name: Optional[str] = None
    user_course: Optional[str] = None
    user_due_at: Optional[str] = None  # "" = usuário removeu o prazo explicitamente
    user_points: Optional[str] = None
    status: str = STATUS_TODO
    notes: str = ""
    position: float = 0.0
    first_seen: Optional[str] = None
    last_checked: Optional[str] = None
    last_seen_status: str = SEEN_FOUND
    deleted_at: Optional[str] = None
    conflicts: list = field(default_factory=list)
    due_ambiguous: bool = False
    updated_at: Optional[str] = None
    portal_completed: bool = False        # entregue/concluída segundo a Grade de Notas do portal
    portal_submitted_at: Optional[str] = None

    # ---- valores efetivos (personalizado > portal > "-") ----
    def _eff(self, f: str):
        u = getattr(self, f"user_{f}")
        return u if u is not None else getattr(self, f"portal_{f}")

    @property
    def name(self) -> str:
        return self._eff("name") or MISSING

    @property
    def course(self) -> str:
        return self._eff("course") or MISSING

    @property
    def points(self) -> str:
        return self._eff("points") or MISSING

    @property
    def due_at(self) -> Optional[datetime]:
        return iso_to_dt(self._eff("due_at"))

    @property
    def due_display(self) -> str:
        dt = self.due_at
        if dt is None:
            raw = self.portal_due_raw if self.user_due_at is None else None
            if raw and self.due_ambiguous:
                return f"{raw} (verificar)"
            return MISSING
        if dt.hour == 23 and dt.minute == 59 and dt.second == 59:
            return dt.strftime("%d/%m/%Y")
        return dt.strftime("%d/%m/%Y %H:%M")

    @property
    def is_exam(self) -> bool:
        """Provas aparecem só na agenda (categoria Prova), fora do quadro de atividades."""
        from app.services.rules import is_exam
        return is_exam(self.name)

    def is_overridden(self, f: str) -> bool:
        return getattr(self, f"user_{f}") is not None

    def conflicts_json(self) -> str:
        return json.dumps(self.conflicts, ensure_ascii=False)
