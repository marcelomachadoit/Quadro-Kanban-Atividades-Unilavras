"""Atualização semanal automática: atividades + notas/AVIN + encontros, uma vez por semana (a partir de segunda).

Regra: ao abrir o aplicativo, se a atualização automática desta semana (que começa na segunda-feira) ainda não foi
feita, ela roda. Se o usuário não abriu o app na segunda, ela roda no primeiro dia em que ele abrir naquela semana.
Em caso de falha, tenta de novo em outra abertura, mas no máximo uma tentativa por dia (evita várias tentativas de
login seguidas, que levam o portal a pedir verificação humana).
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Callable, Optional

from app.automation.portal import AutomationError, Cancelled, PortalClient, PortalLabels
from app.config import BROWSER_PROFILE_DIR, TZ
from app.database.db import Database
from app.models.activity import dt_to_iso
from app.services.credentials import Credentials
from app.services.grades_updater import GradesReport, GradesUpdater
from app.services.sync import SyncReport
from app.services.updater import Progress, Updater

log = logging.getLogger(__name__)

META_WEEKLY_RUN = "weekly_last_run"          # data (AAAA-MM-DD) da última atualização semanal bem-sucedida
META_WEEKLY_ATTEMPT = "weekly_last_attempt"  # data da última tentativa (sucesso ou falha)


def week_start(d: date) -> date:
    """Segunda-feira da semana de ``d``."""
    return d - timedelta(days=d.weekday())


def is_weekly_due(today: date, last_run: Optional[str], last_attempt: Optional[str]) -> bool:
    if last_attempt == today.isoformat():
        return False                         # já tentou hoje (com sucesso ou não)
    if not last_run:
        return True
    try:
        return date.fromisoformat(last_run) < week_start(today)
    except ValueError:
        return True


@dataclass
class WeeklyReport:
    activities: SyncReport = field(default_factory=SyncReport)
    grades: GradesReport = field(default_factory=GradesReport)
    errors: list = field(default_factory=list)
    cancelled: bool = False

    @property
    def ok(self) -> bool:
        return not (self.errors or self.activities.errors or self.grades.errors or self.cancelled
                    or self.activities.cancelled or self.grades.cancelled)

    def summary_text(self) -> str:
        parts = ["ATIVIDADES", self.activities.summary_text(), "", "NOTAS", self.grades.summary_text()]
        parts += [f"Erro: {e}" for e in self.errors]
        return "\n".join(parts)


class WeeklyUpdater:
    def __init__(self, db: Database, creds: Credentials, headless: bool = True,
                 labels: Optional[PortalLabels] = None, cancel: Optional[threading.Event] = None,
                 on_progress: Optional[Callable[[Progress], None]] = None,
                 client_factory: Optional[Callable[..., PortalClient]] = None, today: Optional[date] = None):
        self.db = db
        self.creds = creds
        self.headless = headless
        self.labels = labels or PortalLabels()
        self.cancel = cancel or threading.Event()
        self.on_progress = on_progress or (lambda p: None)
        self.client_factory = client_factory or PortalClient
        self.today = today or datetime.now(TZ).date()

    def run(self) -> WeeklyReport:
        report = WeeklyReport()
        self.db.set_meta(META_WEEKLY_ATTEMPT, self.today.isoformat())
        common = dict(headless=self.headless, labels=self.labels, cancel=self.cancel, on_progress=self.on_progress,
                      client_factory=self.client_factory)
        try:
            with self.client_factory(profile_dir=BROWSER_PROFILE_DIR, headless=self.headless, labels=self.labels,
                                     cancel=self.cancel,
                                     on_step=lambda s: self.on_progress(Progress(step=s)),
                                     on_manual=lambda m: self.on_progress(Progress(step="Aguardando verificação",
                                                                                   manual_message=m))) as c:
                self.on_progress(Progress(step="Validando credenciais"))
                c.login(self.creds)                     # um único login para tudo
                self.db.set_meta("last_auth_success", dt_to_iso(datetime.now(TZ)))
                report.activities = Updater(self.db, self.creds, **common).run(client=c)
                if not (report.activities.cancelled or self.cancel.is_set()):
                    report.grades = GradesUpdater(self.db, self.creds, **common).run(client=c)
        except Cancelled:
            report.cancelled = True
        except AutomationError as e:
            report.errors.append(str(e))
            log.error("Atualização semanal interrompida: %s", e)
        except Exception as e:  # noqa: BLE001
            report.errors.append(f"Erro inesperado na atualização semanal: {type(e).__name__}")
            log.exception("Erro inesperado na atualização semanal")
        if report.ok:
            self.db.set_meta(META_WEEKLY_RUN, self.today.isoformat())
            log.info("Atualização semanal concluída.")
        return report
