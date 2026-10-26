"""Interpretação dos dados da Sala de Aula Virtual (Plataforma A / Grupo A).

Estrutura observada na inspeção do portal real (out/2026):
* ``GET .../v1/plataforma/academic/courses/me`` -> ``{"courses": [{id, name, progress, startDate, ...}], "nextPage", "totalRows"}``
* ``GET .../v2/plataforma/content/academics-main/{id}/contents`` -> ``{"context": {...}, "topics": [árvore]}``
  Cada tópico tem ``title``, ``topicTypeId``, ``categoryTypeId``, ``hasDeadline``/``deadlineAt``
  (horário local de São Paulo, ex.: "2026-10-30 23:59:00" exibido como "Prazo de envio 30/10/2026 - 23:59")
  e ``hasGrade``/``grade.value`` (valor TOTAL da atividade, exibido como "Vale 4 pontos"), além de ``children``.
* Página da atividade: ``/plataforma/course/{courseId}/content/{topicId}``.

Todas as funções aqui são puras (sem navegador) para permitir testes com dados simulados.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Iterable, Optional

from app.config import TZ
from app.models.activity import Course, ScrapedActivity
from app.services import rules as R

log = logging.getLogger(__name__)

# categorias observadas: 1 seção, 2 arquivo, 4 página/link, 5 atividade/entrega, 7 encontro, 8 questionário, 9 externo
ASSESSMENT_CATEGORIES = {5, 8}
SECTION_TYPES = {1, 2}


@dataclass
class CourseScan:
    activities: list = field(default_factory=list)
    review: list = field(default_factory=list)
    skipped_expired: int = 0
    inspected_items: int = 0


# ------------------------------------------------------------------ disciplinas

def parse_courses_json(data: dict) -> tuple[list[Course], bool]:
    """Retorna (disciplinas, existe_proxima_pagina)."""
    courses = []
    for c in (data or {}).get("courses") or []:
        name = R.clean_text(c.get("name"))
        raw = c.get("progress")
        progress = None
        if c.get("useProgress", True) is not False and raw not in (None, ""):
            try:
                progress = float(str(raw).replace(",", "."))
                if not 0 <= progress <= 100:
                    progress = None
            except ValueError:
                progress = R.parse_percentage(str(raw))
        courses.append(Course(name=name or "-", progress=progress, source_id=str(c.get("id")) if c.get("id") else None,
                              progress_raw=str(raw) if raw is not None else "",
                              url=f"/plataforma/course/{c['id']}" if c.get("id") else None,
                              start_date=c.get("startDate")))
    return courses, bool((data or {}).get("nextPage"))


_COURSE_CARD_RE = re.compile(r"(\d{1,3}(?:[.,]\d+)?)\s*%\s*conclu", re.I)


def parse_course_card_text(name: str, text: str) -> Course:
    """Alternativa via DOM: texto do cartão da disciplina ("40% concluído")."""
    m = _COURSE_CARD_RE.findall(text or "")
    progress = float(m[0].replace(",", ".")) if len(m) == 1 else None
    return Course(name=R.clean_text(name), progress=progress, progress_raw=R.clean_text(text)[:120])


# ------------------------------------------------------------------ atividades

def parse_deadline(value: Optional[str]) -> Optional[datetime]:
    """deadlineAt vem sem fuso e representa o horário local de São Paulo."""
    if not value:
        return None
    pd = R.parse_datetime_br(value)
    return pd.dt


def _points(topic: dict) -> Optional[str]:
    if not topic.get("hasGrade"):
        return None
    v = (topic.get("grade") or {}).get("value")
    if v in (None, ""):
        return None
    try:
        f = float(str(v).replace(",", "."))
    except ValueError:
        return R.clean_text(str(v))   # preserva o formato original quando não é numérico
    s = f"{f:g}".replace(".", ",")
    return f"{s} ponto" if f == 1 else f"{s} pontos"


def _has_item_descendant(topic: dict) -> bool:
    for ch in topic.get("children") or []:
        if ch.get("hasDeadline") or ch.get("hasGrade") or _has_item_descendant(ch):
            return True
    return False


def _infer_year(pd: R.ParsedDate, course_start: Optional[date]) -> R.ParsedDate:
    """Datas sem ano no título (ex.: "Prova I: 12/11"): o ano é inferido pelo início da disciplina."""
    if pd.dt is None or not pd.ambiguous or course_start is None:
        return pd
    dt = pd.dt.replace(year=course_start.year)
    if dt.date() < course_start - timedelta(days=31):
        dt = dt.replace(year=course_start.year + 1)
    return R.ParsedDate(dt, pd.has_time, False, pd.raw)


def activity_url(base: str, course_id, topic_id) -> str:
    return f"{base.rstrip('/')}/plataforma/course/{course_id}/content/{topic_id}"


def parse_contents_json(data: dict, course_name: str, course_id, base_url: str,
                        course_start: Optional[str] = None, now: Optional[datetime] = None) -> CourseScan:
    now = now or datetime.now(TZ)
    ctx = (data or {}).get("context") or {}
    course_name = R.clean_text(ctx.get("academicMainName")) or course_name
    start = None
    for s in (course_start, ctx.get("academicMainStartAt")):
        if s:
            try:
                start = date.fromisoformat(str(s)[:10])
                break
            except ValueError:
                pass
    scan = CourseScan()

    def visit(topic: dict, parents: list[str]):
        scan.inspected_items += 1
        title = R.clean_text(topic.get("title"))
        tid = topic.get("id")
        cat = topic.get("categoryTypeId")
        ttype = topic.get("topicTypeId")
        has_item = bool(topic.get("hasDeadline") or topic.get("hasGrade"))
        candidate = None

        if has_item:
            assessment = cat in ASSESSMENT_CATEGORIES or bool(topic.get("hasGrade")) or R.looks_like_assessment(title)
            due_raw = topic.get("deadlineAt") if topic.get("hasDeadline") else None
            due_dt = parse_deadline(due_raw)
            pd = R.ParsedDate(due_dt, True, due_raw is not None and due_dt is None, due_raw or "")
            candidate = (assessment, pd, _points(topic))
        elif ttype in SECTION_TYPES and R.ASSESSMENT_WORDS.search(title) and not _has_item_descendant(topic):
            # seção que representa uma avaliação e só informa a data no título (ex.: "Prova I: 12/11")
            pd = _infer_year(R.extract_due(title, now) if R.DUE_LABEL_RE.search(title) else
                             R.parse_datetime_br(title, now), start)
            if pd.dt is not None:
                candidate = (True, pd, None)

        if candidate is not None:
            assessment, pd, pts = candidate
            decision = R.decide_inclusion(assessment, pd, pts, now)
            if decision.include:
                scan.activities.append(ScrapedActivity(
                    name=title or "-", course=course_name or "-", due_at=pd.dt, due_raw=pd.raw,
                    points=pts, url=activity_url(base_url, course_id, tid) if tid else None,
                    source_id=f"grupoa:{tid}" if tid else None, kind=f"tipo {ttype}/cat {cat}",
                    due_ambiguous=decision.needs_review))
                if decision.needs_review:
                    scan.review.append(f"{course_name} — {title}: {decision.reason}")
            elif decision.reason == "prazo expirado":
                scan.skipped_expired += 1
        for ch in topic.get("children") or []:
            visit(ch, parents + [title])

    for t in (data or {}).get("topics") or []:
        visit(t, [])
    log.info("Disciplina '%s': %s itens inspecionados, %s atividades vigentes, %s expiradas ignoradas",
             course_name, scan.inspected_items, len(scan.activities), scan.skipped_expired)
    return scan


def dedupe(items: Iterable[ScrapedActivity]) -> list[ScrapedActivity]:
    seen, out = set(), []
    for a in items:
        k = a.source_id or (R.normalize(a.course), R.normalize(a.name))
        if k not in seen:
            seen.add(k)
            out.append(a)
    return out
