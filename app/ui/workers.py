"""Execução da automação em segundo plano (a interface nunca congela)."""
from __future__ import annotations

import logging
import threading

from PySide6.QtCore import QThread, Signal

from app.automation.portal import AutomationError
from app.services.credentials import Credentials
from app.services.updater import Progress, Updater

log = logging.getLogger(__name__)


class UpdateWorker(QThread):
    progress = Signal(object)    # Progress
    finished_report = Signal(object)

    def __init__(self, ctx, creds: Credentials, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.creds = creds
        self.cancel_event = threading.Event()

    def cancel(self) -> None:
        self.cancel_event.set()

    def run(self) -> None:
        up = Updater(self.ctx.db, self.creds, headless=not self.ctx.show_browser, labels=self.ctx.labels(),
                     cancel=self.cancel_event, on_progress=self.progress.emit)
        self.finished_report.emit(up.run())


class TestConnectionWorker(QThread):
    done = Signal(bool, str)

    def __init__(self, ctx, creds: Credentials, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.creds = creds
        self.cancel_event = threading.Event()

    def run(self) -> None:
        try:
            Updater(self.ctx.db, self.creds, headless=not self.ctx.show_browser, labels=self.ctx.labels(),
                    cancel=self.cancel_event).test_connection()
            self.done.emit(True, "Conexão realizada com sucesso. Usuário e senha válidos.")
        except AutomationError as e:
            self.done.emit(False, str(e))
        except Exception as e:  # noqa: BLE001
            log.exception("Falha no teste de conexão")
            self.done.emit(False, f"Erro inesperado: {type(e).__name__}")
