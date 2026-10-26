"""Atualização incremental: compara dados coletados com o banco local sem apagar trabalho manual."""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable, Optional

from app.config import TZ
from app.database.db import Database
from app.models.activity import (
    FIELD_LABELS, SEEN_FOUND, SEEN_NOT_FOUND, STATUS_TODO, Activity, ScrapedActivity, dt_to_iso, iso_to_dt,
)
from app.services.rules import make_source_key, normalize

log = logging.getLogger(__name__)


@dataclass
class SyncReport:
    found: int = 0
    added: int = 0
    updated: int = 0
    unchanged: int = 0
    not_found: int = 0
    restored: int = 0                                     # excluídas pelo usuário e reinseridas por estarem no portal
    added_names: list = field(default_factory=list)
    due_changes: list = field(default_factory=list)       # (atividade, prazo antigo, prazo novo)
    conflicts: list = field(default_factory=list)         # (atividade, campo)
    review: list = field(default_factory=list)            # textos de datas a verificar
    courses_processed: list = field(default_factory=list)
    courses_skipped: list = field(default_factory=list)   # >= 95%
    courses_unknown: list = field(default_factory=list)   # percentual não interpretável
    courses_failed: list = field(default_factory=list)    # (disciplina, motivo)
    errors: list = field(default_factory=list)
    cancelled: bool = False

    def as_dict(self) -> dict:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}

    def summary_text(self) -> str:
        lines = [
            f"Atividades encontradas: {self.found}",
            f"Adicionadas: {self.added}   Atualizadas: {self.updated}   Sem alterações: {self.unchanged}",
        ]
        if self.restored:
            lines.append(f"Reinseridas no quadro (tinham sido excluídas e continuam no portal): {self.restored}")
        if self.not_found:
            lines.append(f"Não encontradas nesta verificação (mantidas no quadro): {self.not_found}")
        if self.courses_processed:
            lines.append(f"Disciplinas analisadas (< 95%): {len(self.courses_processed)}")
        if self.courses_skipped:
            lines.append(f"Disciplinas ignoradas (≥ 95%): {len(self.courses_skipped)}")
        for d, old, new in self.due_changes:
            lines.append(f"Prazo alterado no portal — {d}: {old} → {new}")
        for d, f in self.conflicts:
            lines.append(f"Divergência para revisão — {d}: {FIELD_LABELS.get(f, f)} editado por você e alterado no portal")
        for c in self.courses_unknown:
            lines.append(f"Percentual de conclusão não identificado (não processada): {c}")
        for c, why in self.courses_failed:
            lines.append(f"Não foi possível verificar a disciplina {c}: {why}")
        for r in self.review:
            lines.append(f"Verificar data: {r}")
        for e in self.errors:
            lines.append(f"Erro: {e}")
        if self.cancelled:
            lines.append("A atualização foi interrompida pelo usuário. Os dados já coletados foram salvos.")
        return "\n".join(lines)


def _fmt_due(iso: Optional[str]) -> str:
    dt = iso_to_dt(iso)
    return dt.strftime("%d/%m/%Y %H:%M") if dt else "-"


def _portal_values(s: ScrapedActivity) -> dict:
    return {
        "name": s.name or None,
        "course": s.course or None,
        "due_at": dt_to_iso(s.due_at),
        "points": s.points or None,
    }


def _hash(values: dict, url: Optional[str], raw: str) -> str:
    basis = "|".join(str(values[k]) for k in sorted(values)) + f"|{url}|{raw}"
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()


class SyncService:
    def __init__(self, db: Database):
        self.db = db

    def apply(self, scraped: Iterable[ScrapedActivity], processed_courses: Iterable[str],
              report: Optional[SyncReport] = None, now: Optional[datetime] = None) -> SyncReport:
        """Mescla as atividades coletadas no banco local.

        ``processed_courses``: disciplinas inspecionadas COM SUCESSO. Somente atividades dessas
        disciplinas podem ser marcadas como "não encontradas" — falhas de coleta nunca afetam registros.
        """
        report = report or SyncReport()
        now_s = dt_to_iso(now or datetime.now(TZ))
        seen_keys: set[str] = set()
        items = list(scraped)

        with self.db.transaction() as conn:
            for s in items:
                key = make_source_key(s.course, s.name, s.source_id, s.url)
                if key in seen_keys:
                    continue          # duplicata dentro da mesma coleta
                seen_keys.add(key)
                report.found += 1
                existing = self.db.get_by_key(key)
                if existing is None and (s.source_id or s.url):
                    # registro antigo pode ter sido salvo sem identificador; evita duplicar
                    legacy = self.db.get_by_key(make_source_key(s.course, s.name))
                    if legacy is not None:
                        conn.execute("UPDATE activities SET source_key=? WHERE id=?", (key, legacy.id))
                        existing = self.db.get_by_key(key)
                vals = _portal_values(s)
                h = _hash(vals, s.url, s.due_raw)
                if existing is None:
                    self._insert(conn, key, s, vals, h, now_s)
                    report.added += 1
                    report.added_names.append(s.name)
                else:
                    if existing.deleted_at:
                        # excluída no quadro, mas ainda existe no portal: volta para o quadro na atualização
                        self.db.update_fields(existing.id, conn=conn, deleted_at=None)
                        report.restored += 1
                    changed = self._update(conn, existing, s, vals, h, now_s, report)
                    if changed:
                        report.updated += 1
                    else:
                        report.unchanged += 1
                if s.due_ambiguous:
                    report.review.append(f"{s.course} — {s.name}: \"{s.due_raw}\"")

            processed_norm = {normalize(c) for c in processed_courses}
            for a in self.db.list_activities(include_deleted=False):
                if a.origin != "portal" or a.source_key in seen_keys:
                    continue
                if normalize(a.portal_course) in processed_norm and a.last_seen_status != SEEN_NOT_FOUND:
                    self.db.update_fields(a.id, conn=conn, last_seen_status=SEEN_NOT_FOUND, last_checked=now_s)
                    report.not_found += 1
        log.info("Sincronização: encontradas=%s adicionadas=%s atualizadas=%s inalteradas=%s nao_encontradas=%s",
                 report.found, report.added, report.updated, report.unchanged, report.not_found)
        return report

    # ------------------------------------------------------------------
    def _insert(self, conn, key, s: ScrapedActivity, vals, h, now_s) -> None:
        a = Activity(
            source_key=key, source_id=s.source_id, origin="portal",
            portal_name=vals["name"], portal_course=vals["course"], portal_due_at=vals["due_at"],
            portal_due_raw=s.due_raw or None, portal_points=vals["points"], url=s.url,
            status=STATUS_TODO, first_seen=now_s, last_checked=now_s, last_seen_status=SEEN_FOUND,
            due_ambiguous=s.due_ambiguous, position=self.db.next_position(STATUS_TODO),
        )
        self.db.insert(a, conn=conn, portal_hash=h)

    def _update(self, conn, a: Activity, s: ScrapedActivity, vals, h, now_s, report: SyncReport) -> bool:
        fields: dict = {"last_checked": now_s, "last_seen_status": SEEN_FOUND}
        old_hash = self.db.portal_hash(a.source_key)
        if old_hash == h:
            self.db.update_fields(a.id, conn=conn, **fields)
            return False

        conflicts = [c for c in a.conflicts]
        label = a.name
        any_change = False
        for f in ("name", "course", "due_at", "points"):
            old = getattr(a, f"portal_{f}")
            new = vals[f]
            if old == new:
                continue
            any_change = True
            fields[f"portal_{f}"] = new
            user_val = getattr(a, f"user_{f}")
            if f == "due_at":
                report.due_changes.append((label, _fmt_due(old), _fmt_due(new)))
            if user_val is not None and user_val != new:
                # o usuário editou este campo: preserva a edição e registra a divergência
                conflicts = [c for c in conflicts if c.get("field") != f]
                conflicts.append({"field": f, "portal_old": old, "portal_new": new,
                                  "user_value": user_val, "detected_at": now_s})
                report.conflicts.append((label, f))
            elif user_val is not None and user_val == new:
                # o portal passou a coincidir com a edição: a personalização deixa de ser necessária
                fields[f"user_{f}"] = None
                conflicts = [c for c in conflicts if c.get("field") != f]
        if s.url and s.url != a.url:
            fields["url"] = s.url
            any_change = True
        if (s.due_raw or None) != a.portal_due_raw:
            fields["portal_due_raw"] = s.due_raw or None
        if s.source_id and s.source_id != a.source_id:
            fields["source_id"] = s.source_id
        fields["due_ambiguous"] = s.due_ambiguous
        fields["conflicts"] = conflicts
        fields["portal_hash"] = h
        self.db.update_fields(a.id, conn=conn, **fields)
        return any_change


# ---------------------------------------------------------------------- edição manual

def apply_user_edit(db: Database, activity_id: int, name: str, course: str, due_at: Optional[datetime],
                    points: str, status: str, notes: str) -> None:
    """Grava edições do usuário como personalizações, mantendo o valor do portal intacto."""
    a = db.get(activity_id)
    if a is None:
        return
    new = {"name": name.strip() or None, "course": course.strip() or None,
           "due_at": dt_to_iso(due_at), "points": points.strip() or None}
    fields: dict = {"status": status, "notes": notes}
    for f, v in new.items():
        portal_v = getattr(a, f"portal_{f}")
        current = getattr(a, f"_eff")(f)
        if v == current:
            continue                      # campo não foi alterado nesta edição
        if a.origin == "portal" and v == portal_v:
            fields[f"user_{f}"] = None    # voltou ao valor do portal
        else:
            # "" registra explicitamente "sem valor" para não cair de volta no valor do portal
            fields[f"user_{f}"] = v if v is not None else ("" if a.origin == "portal" and portal_v else None)
    if status != a.status:
        fields["position"] = db.next_position(status)
    db.update_fields(activity_id, **fields)


def resolve_conflict(db: Database, activity_id: int, field_name: str, accept_portal: bool) -> None:
    a = db.get(activity_id)
    if a is None:
        return
    conflicts = [c for c in a.conflicts if c.get("field") != field_name]
    fields = {"conflicts": conflicts}
    if accept_portal:
        fields[f"user_{field_name}"] = None
    db.update_fields(activity_id, **fields)
