"""Atualização da aba Eventos: lê a página pública de eventos da Unilavras (não precisa de login nem do navegador)."""
from __future__ import annotations

import logging
import threading
import time
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Optional

from app.automation import events_parser as E
from app.config import APP_NAME, APP_VERSION, EVENTS_URL, TZ
from app.database.db import Database
from app.models.activity import dt_to_iso
from app.models.events import PortalEvent

log = logging.getLogger(__name__)

META_LAST_EVENTS = "last_events_update"
FETCH_TIMEOUT_S = 20
DETAIL_DELAY_S = 0.3          # pausa curta entre páginas de eventos
MAX_DETAILS = 60


def fetch_url(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": f"Mozilla/5.0 ({APP_NAME}/{APP_VERSION})",
                                               "Accept-Language": "pt-BR,pt;q=0.9"})
    with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT_S) as r:       # noqa: S310 — só http(s) fixos/da lista
        raw = r.read()
        charset = r.headers.get_content_charset() or "utf-8"
    try:
        return raw.decode(charset)
    except (LookupError, UnicodeDecodeError):
        return raw.decode("latin-1")


@dataclass
class EventsReport:
    found: int = 0
    new: int = 0
    details_failed: int = 0
    errors: list = field(default_factory=list)
    cancelled: bool = False

    def summary_text(self) -> str:
        lines = [f"Eventos encontrados: {self.found}", f"Novos desde a última leitura: {self.new}"]
        if self.details_failed:
            lines.append(f"Eventos sem detalhes (horário/local): {self.details_failed}")
        lines += [f"Erro: {e}" for e in self.errors]
        if self.cancelled:
            lines.append("A leitura de eventos foi interrompida.")
        return "\n".join(lines)


class EventsUpdater:
    def __init__(self, db: Database, fetch: Optional[Callable[[str], str]] = None,
                 cancel: Optional[threading.Event] = None, on_step: Optional[Callable[[str], None]] = None,
                 delay_s: float = DETAIL_DELAY_S):
        self.db = db
        self.fetch = fetch or fetch_url
        self.cancel = cancel or threading.Event()
        self.on_step = on_step or (lambda s: None)
        self.delay_s = delay_s

    def run(self) -> EventsReport:
        report = EventsReport()
        try:
            self.on_step("Lendo os eventos da Unilavras")
            events = E.parse_events_list(self.fetch(EVENTS_URL))
        except Exception as e:  # noqa: BLE001 — rede/site fora do ar: mantém os eventos já salvos
            report.errors.append("Não foi possível abrir a página de eventos da Unilavras. Verifique sua conexão. "
                                 f"Detalhe: {type(e).__name__}")
            log.warning("Falha ao ler a lista de eventos: %s", e)
            return report
        known = {e.key: e for e in self.db.list_portal_events()}
        for i, ev in enumerate(events[:MAX_DETAILS]):
            if self.cancel.is_set():
                report.cancelled = True
                return report                          # não substitui a lista com dados pela metade
            old = known.get(ev.key)
            if old and old.date == ev.date and (old.start_at or old.description):
                self._reuse(ev, old)                   # já detalhado antes: evita abrir a página de novo
                continue
            if not ev.url:
                continue
            self.on_step(f"Lendo detalhes dos eventos ({i + 1}/{len(events)})")
            try:
                E.merge_details(ev, E.parse_event_details(self.fetch(ev.url)))
            except Exception as e:  # noqa: BLE001
                report.details_failed += 1
                log.info("Detalhes indisponíveis para %s: %s", ev.url, type(e).__name__)
            if self.delay_s:
                time.sleep(self.delay_s)
        report.found = len(events)
        report.new = sum(1 for e in events if e.key not in known)
        self.db.replace_portal_events(events)
        self.db.set_meta(META_LAST_EVENTS, dt_to_iso(datetime.now(TZ)))
        log.info("Eventos lidos: %s (%s novos)", report.found, report.new)
        return report

    @staticmethod
    def _reuse(ev: PortalEvent, old: PortalEvent) -> None:
        if E.is_truncated(ev.title) and not E.is_truncated(old.title):
            ev.title = old.title
        ev.start_at, ev.end_at = old.start_at, old.end_at
        ev.location, ev.description = old.location, old.description
