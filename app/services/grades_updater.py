"""Atualização somente das notas: Grade de Notas de todas as disciplinas + resultados do AVIN."""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Optional

from app.automation import grades_parser as G
from app.automation.portal import (AutomationError, Cancelled, HumanVerificationRequired, LoginFailed, PortalClient,
                                   PortalLabels, SessionExpired)
from app.config import BROWSER_PROFILE_DIR, DIAG_DIR, TZ
from app.database.db import Database
from app.models.activity import dt_to_iso
from app.models.grades import fmt_num
from app.services.credentials import Credentials
from app.services.updater import Progress, load_courses, save_course_meetings, save_courses_info

log = logging.getLogger(__name__)

META_LAST_GRADES = "last_grades_update"


@dataclass
class GradesReport:
    courses_ok: list = field(default_factory=list)
    courses_failed: list = field(default_factory=list)   # (disciplina, motivo)
    avins: list = field(default_factory=list)            # (nome, nota)
    avin_error: Optional[str] = None
    errors: list = field(default_factory=list)
    cancelled: bool = False

    def summary_text(self) -> str:
        lines = [f"Disciplinas com notas atualizadas: {len(self.courses_ok)}"]
        for name, score in self.avins:
            lines.append(f"AVIN — {name}: {score}")
        if not self.avins and not self.avin_error:
            lines.append("Nenhum resultado de AVIN disponível.")
        if self.avin_error:
            lines.append(f"Não foi possível ler o AVIN: {self.avin_error}")
        for c, why in self.courses_failed:
            lines.append(f"Não foi possível ler as notas de {c}: {why}")
        for e in self.errors:
            lines.append(f"Erro: {e}")
        if self.cancelled:
            lines.append("A atualização foi interrompida. As notas já lidas foram salvas.")
        return "\n".join(lines)


class GradesUpdater:
    """Executa a leitura das notas. Deve rodar fora da thread da interface."""

    def __init__(self, db: Database, creds: Credentials, headless: bool = True,
                 labels: Optional[PortalLabels] = None, cancel: Optional[threading.Event] = None,
                 on_progress: Optional[Callable[[Progress], None]] = None,
                 client_factory: Optional[Callable[..., PortalClient]] = None):
        self.db = db
        self.creds = creds
        self.headless = headless
        self.labels = labels or PortalLabels()
        self.cancel = cancel or threading.Event()
        self.on_progress = on_progress or (lambda p: None)
        self.client_factory = client_factory or PortalClient
        self.progress = Progress()

    def _emit(self, **kw) -> None:
        for k, v in kw.items():
            setattr(self.progress, k, v)
        self.on_progress(Progress(**vars(self.progress)))

    def run(self, client: Optional[PortalClient] = None) -> GradesReport:
        """``client`` já autenticado permite reaproveitar a sessão (atualização semanal: um único login)."""
        report = GradesReport()
        try:
            if client is None:
                with self.client_factory(profile_dir=BROWSER_PROFILE_DIR, headless=self.headless, labels=self.labels,
                                         cancel=self.cancel, on_step=lambda s: self._emit(step=s),
                                         on_manual=lambda m: self._emit(manual_message=m)) as c:
                    self._emit(step="Validando credenciais")
                    c.login(self.creds)
                    self.db.set_meta("last_auth_success", dt_to_iso(datetime.now(TZ)))
                    self._session(c, report)
            else:
                self._session(client, report)
            self.db.set_meta(META_LAST_GRADES, dt_to_iso(datetime.now(TZ)))
        except Cancelled:
            report.cancelled = True
        except AutomationError as e:
            report.errors.append(str(e))
            log.error("Atualização de notas interrompida: %s", e)
        except Exception as e:  # noqa: BLE001 — nunca derrubar a aplicação
            report.errors.append("Erro inesperado ao ler as notas. Os dados locais foram preservados. "
                                 f"Detalhe: {type(e).__name__}")
            log.exception("Erro inesperado na atualização de notas")
        return report

    def _session(self, c: PortalClient, report: GradesReport) -> None:
        c.open_classroom()
        courses = [co for co in load_courses(c) if co.source_id]
        save_courses_info(self.db, courses)
        self._emit(step="Lendo as notas", courses_total=len(courses) + 1, courses_done=0)
        for i, co in enumerate(courses, 1):
            c.check_cancel()
            self._emit(step="Lendo as notas", course=co.name)
            self._course(c, co, report)
            self._emit(courses_done=i, activities_found=len(report.courses_ok))
        self._emit(step="Lendo os resultados do AVIN", course="")
        self._avin(c, report)
        self._emit(courses_done=len(courses) + 1)

    def _course(self, c: PortalClient, co, report: GradesReport) -> None:
        for attempt in (1, 2):
            try:
                contents = c.course_contents(co)       # para saber quanto cada atividade vale
                save_course_meetings(self.db, co, contents)
                data = c.course_grades(co)
                cg = G.parse_course_grades(data, co, contents, base_url=c.lxp_base)
                self.db.save_grade_snapshot(cg.key, "course", cg.to_dict(), cg.start_date)
                report.courses_ok.append(cg.name)
                log.info("Notas lidas: %s (nota %s)", cg.name, fmt_num(cg.final))
                return
            except SessionExpired:
                if attempt == 2:
                    raise
                c.login(self.creds)
                c.open_classroom()
            except (Cancelled, LoginFailed, HumanVerificationRequired):
                raise
            except AutomationError as e:
                report.courses_failed.append((co.name, str(e)))
                c.save_diagnostic(DIAG_DIR, f"falha-notas-{co.source_id}")
                return
            except Exception as e:  # noqa: BLE001
                report.courses_failed.append((co.name, type(e).__name__))
                log.exception("Erro ao ler notas de %s", co.name)
                return

    def _avin(self, c: PortalClient, report: GradesReport) -> None:
        try:
            c.open_avin()
            rows = G.parse_avin_table(c.avin_results_table())
            for row in rows:
                c.check_cancel()
                self._emit(course=row["name"])
                av = G.build_avin(row, c.avin_answers(row["results_href"], row["id"]), c.avin_base)
                if not av.questions:
                    log.warning("AVIN %s sem questões legíveis", row["id"])
                    continue
                self.db.save_grade_snapshot(av.key, "avin", av.to_dict(), av.start)
                report.avins.append((av.name, f"{fmt_num(av.score)} de {fmt_num(av.max_score)}"))
                log.info("AVIN lido: %s acertos de %s", av.correct, len(av.questions))
        except (Cancelled, LoginFailed, HumanVerificationRequired):
            raise
        except AutomationError as e:
            report.avin_error = str(e)
            c.save_diagnostic(DIAG_DIR, "falha-avin")
        except Exception as e:  # noqa: BLE001
            report.avin_error = type(e).__name__
            log.exception("Erro ao ler o AVIN")
