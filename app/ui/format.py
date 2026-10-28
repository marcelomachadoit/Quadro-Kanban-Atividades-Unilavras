"""Formatação voltada ao usuário (pura, sem Qt): datas em linguagem natural, nomes curtos e cores por disciplina."""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta
from typing import Optional

from app.config import MISSING, SOON_HOURS, TZ
from app.models.activity import STATUS_DONE, Activity
from app.services.rules import normalize

WEEKDAYS = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]

# níveis de urgência (do mais ao menos urgente)
URG_OVERDUE, URG_SOON, URG_WEEK, URG_LATER, URG_NONE, URG_DONE = "atrasada", "urgente", "semana", "depois", "sem_prazo", "concluida"

COURSE_PALETTE = ["#2563EB", "#0D9488", "#7C3AED", "#DB2777", "#EA580C", "#059669", "#4F46E5", "#B45309", "#0891B2",
                  "#9333EA"]

CATEGORY_COLORS = {"Aula": "#2563EB", "Prova": "#DC2626", "Estudo": "#059669", "Trabalho": "#D97706",
                   "Evento": "#7C3AED", "Pessoal": "#DB2777"}     # cor de destaque das categorias da agenda

_CODE_RE = re.compile(r"\s*\(([A-Z]{2,}[A-Z0-9]*\d+[A-Z0-9]*)\)\s*$")


def short_course(name: Optional[str]) -> str:
    """"Estruturas de Dados (GRDESISL235)" -> "Estruturas de Dados"."""
    if not name or name == MISSING:
        return MISSING
    return _CODE_RE.sub("", name).strip() or name


_ASSIGNED: dict[str, str] = {}


def register_courses(names: list[str]) -> None:
    """Dá a cada disciplina uma cor diferente, na ordem recebida (chamada com a lista ordenada por início)."""
    used = set(_ASSIGNED.values())
    for n in names:
        k = normalize(short_course(n))
        if not k or k in _ASSIGNED:
            continue
        free = [c for c in COURSE_PALETTE if c not in used]
        _ASSIGNED[k] = free[0] if free else COURSE_PALETTE[len(_ASSIGNED) % len(COURSE_PALETTE)]
        used.add(_ASSIGNED[k])


def category_color(category: str) -> str:
    return CATEGORY_COLORS.get(category, "#64748B")


def course_color(name: Optional[str]) -> str:
    if not name or name == MISSING:
        return "#64748B"
    k = normalize(short_course(name))
    if k in _ASSIGNED:
        return _ASSIGNED[k]
    h = int(hashlib.md5(k.encode()).hexdigest(), 16)
    return COURSE_PALETTE[h % len(COURSE_PALETTE)]


def _has_time(dt: datetime) -> bool:
    return not (dt.hour == 23 and dt.minute == 59 and dt.second == 59)


def _time(dt: datetime) -> str:
    return f", {dt:%H:%M}" if _has_time(dt) else ""


def friendly_due(dt: Optional[datetime], now: Optional[datetime] = None) -> str:
    """Prazo em linguagem natural: "Hoje, 23:59", "Amanhã", "Sex, 30/10, 23:30", "12/11/2027"."""
    if dt is None:
        return "Sem prazo"
    now = now or datetime.now(TZ)
    days = (dt.date() - now.date()).days
    if days == 0:
        return "Hoje" + _time(dt)
    if days == 1:
        return "Amanhã" + _time(dt)
    if days == -1:
        return "Ontem" + _time(dt)
    if 1 < days < 7:
        return f"{WEEKDAYS[dt.weekday()]}, {dt:%d/%m}" + _time(dt)
    if dt.year == now.year:
        return f"{dt:%d/%m}" + _time(dt)
    return f"{dt:%d/%m/%Y}" + _time(dt)


def urgency(a: Activity, now: Optional[datetime] = None) -> str:
    if a.status == STATUS_DONE:
        return URG_DONE
    dt = a.due_at
    if dt is None:
        return URG_NONE
    now = now or datetime.now(TZ)
    if dt < now:
        return URG_OVERDUE
    if dt - now <= timedelta(hours=SOON_HOURS):
        return URG_SOON
    if (dt.date() - now.date()).days < 7:
        return URG_WEEK
    return URG_LATER


# rótulo acessível (texto, não apenas cor) para cada nível
URGENCY_LABEL = {
    URG_OVERDUE: "Prazo encerrado",
    URG_SOON: "Vence em breve",
    URG_WEEK: "Esta semana",
    URG_LATER: "No prazo",
    URG_NONE: "Sem prazo informado",
    URG_DONE: "Concluída",
}


def due_pill_text(a: Activity, now: Optional[datetime] = None) -> str:
    u = urgency(a, now)
    if u == URG_DONE:
        return "Concluída"
    if u == URG_NONE:
        return "Sem prazo"
    if u == URG_OVERDUE:
        return f"Encerrado · {friendly_due(a.due_at, now)}"
    if u == URG_SOON:
        now = now or datetime.now(TZ)
        hours = int((a.due_at - now).total_seconds() // 3600)
        left = "menos de 1 h" if hours < 1 else f"{hours} h"
        return f"{friendly_due(a.due_at, now)} · faltam {left}"
    return friendly_due(a.due_at, now)


def points_short(points: str) -> str:
    """"10 pontos" -> "10 pts"; "-" -> ""."""
    if not points or points == MISSING:
        return ""
    m = re.fullmatch(r"(.+?)\s*pontos?", points.strip())
    if not m:
        return points
    return f"{m[1]} pt" if m[1] == "1" else f"{m[1]} pts"


def group_label(a: Activity, now: Optional[datetime] = None) -> str:
    """Agrupamento da tela inicial."""
    now = now or datetime.now(TZ)
    dt = a.due_at
    if dt is None:
        return "Sem prazo"
    days = (dt.date() - now.date()).days
    if dt < now:
        return "Atrasadas"
    if days == 0:
        return "Hoje"
    if days == 1:
        return "Amanhã"
    if days < 7:
        return "Esta semana"
    return "Mais adiante"


GROUP_ORDER = ["Atrasadas", "Hoje", "Amanhã", "Esta semana", "Mais adiante", "Sem prazo"]


def greeting(now: Optional[datetime] = None) -> str:
    h = (now or datetime.now(TZ)).hour
    return "Bom dia" if 5 <= h < 12 else ("Boa tarde" if 12 <= h < 18 else "Boa noite")


def relative_time(dt: Optional[datetime], now: Optional[datetime] = None) -> str:
    """"agora mesmo", "há 5 min", "há 2 h", "ontem às 14:00", "26/10 às 14:00"."""
    if dt is None:
        return "nunca"
    now = now or datetime.now(TZ)
    secs = (now - dt).total_seconds()
    if secs < 60:
        return "agora mesmo"
    if secs < 3600:
        return f"há {int(secs // 60)} min"
    if dt.date() == now.date():
        return f"há {int(secs // 3600)} h"
    if (now.date() - dt.date()).days == 1:
        return f"ontem às {dt:%H:%M}"
    return f"{dt:%d/%m} às {dt:%H:%M}"


def plural(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"
