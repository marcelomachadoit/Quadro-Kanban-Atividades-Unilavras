"""Encontros virtuais a partir do conteúdo da disciplina (sem navegador, testável).

Observado no portal real (out/2026): cada disciplina tem uma seção com o título do encontro semanal, por exemplo
"Encontro Virtual – Terça-feira às 21h", "Encontro Virtual – Segunda-feira às 20h30min", e itens com data específica
dentro dos ciclos, como "Encontro Virtual – 19/10" ou "Encontro Virtual – Correção da P1 - 14/09".
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from html import unescape
from typing import Optional

from app.models.meetings import Meeting
from app.services import rules as R

_MEETING_RE = re.compile(r"\bencontros?\s+virtua(l|is)\b|\bmeet\b|\baula\s+(ao\s+vivo|online)\b")
WEEKDAYS = [("segunda", 0), ("terca", 1), ("quarta", 2), ("quinta", 3), ("sexta", 4), ("sabado", 5), ("domingo", 6)]
_TIME_RE = re.compile(r"\b(\d{1,2})\s*(?:h|:)\s*(\d{2})?\s*(?:min)?\b")
_DATE_RE = re.compile(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b")


def _text(html: Optional[str]) -> str:
    return R.clean_text(unescape(re.sub(r"<[^>]+>", " ", html or "")))


def _time(t: str) -> Optional[str]:
    m = _TIME_RE.search(t)
    if not m:
        return None
    h, mi = int(m[1]), int(m[2] or 0)
    return f"{h:02d}:{mi:02d}" if h < 24 and mi < 60 else None


def _weekdays(norm: str) -> list[int]:
    return [d for name, d in WEEKDAYS if re.search(rf"\b{name}s?(-feiras?)?\b", norm)]


def parse_meeting_text(title: str, course_start: Optional[date] = None) -> list[Meeting]:
    """Interpreta um título/descrição de encontro virtual. Retorna encontros semanais e/ou com data."""
    norm = R.normalize(title)
    if not _MEETING_RE.search(norm):
        return []
    out: list[Meeting] = []
    tm = _time(norm.replace("–", " "))
    for wd in _weekdays(norm):
        out.append(Meeting(kind="weekly", weekday=wd, time=tm, title=R.clean_text(title)))
    for m in _DATE_RE.finditer(norm):
        d, mo = int(m[1]), int(m[2])
        if not (1 <= d <= 31 and 1 <= mo <= 12):
            continue
        if m[3]:
            y = int(m[3]) + (2000 if len(m[3]) == 2 else 0)
        else:
            base = course_start or date.today()
            y = base.year
            try:
                if date(y, mo, d) < base - timedelta(days=31):
                    y += 1
            except ValueError:
                continue
        try:
            out.append(Meeting(kind="date", date=date(y, mo, d).isoformat(), time=tm, title=R.clean_text(title)))
        except ValueError:
            continue
    return out


def extract_meetings(contents: Optional[dict], course_start: Optional[str] = None) -> list[Meeting]:
    """Percorre a árvore de tópicos e junta os encontros virtuais (títulos e descrições), sem repetições."""
    start = None
    ctx = (contents or {}).get("context") or {}
    for s in (course_start, ctx.get("academicMainStartAt")):
        if s:
            try:
                start = date.fromisoformat(str(s)[:10])
                break
            except ValueError:
                pass
    found: list[Meeting] = []

    def walk(ts):
        for t in ts or []:
            title = t.get("title") or ""
            ms = parse_meeting_text(title, start)
            if not any(m.kind == "weekly" for m in ms) and _MEETING_RE.search(R.normalize(title)):
                desc = (t.get("content") or {}).get("description") if isinstance(t.get("content"), dict) else None
                if desc:   # título genérico ("Encontro Virtual"): procura o dia/horário na descrição
                    ms += [m for m in parse_meeting_text("encontro virtual " + _text(desc)[:400], start)
                           if m.kind == "weekly"]
            found.extend(ms)
            walk(t.get("children"))
    walk((contents or {}).get("topics"))

    # um horário por dia da semana: vale o primeiro encontrado (títulos das seções vêm antes das descrições);
    # entre os candidatos do mesmo dia, prefere o que informa horário
    out, seen = [], set()
    weekly: dict[int, Meeting] = {}
    for m in found:
        if m.kind == "weekly":
            cur = weekly.get(m.weekday)
            if cur is None or (cur.time is None and m.time):
                weekly[m.weekday] = m
    out.extend(weekly[d] for d in sorted(weekly))
    for m in found:
        if m.kind == "date" and (m.date, m.time) not in seen:
            seen.add((m.date, m.time))
            out.append(m)
    return out
