"""Estado compartilhado entre as telas."""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from app.automation.portal import PortalLabels
from app.config import DB_PATH
from app.database.db import Database
from app.services.credentials import CredentialStore


class AppContext(QObject):
    data_changed = Signal()          # atividades alteradas -> telas recarregam
    update_finished = Signal(object)  # SyncReport

    def __init__(self, db: Database, creds: CredentialStore | None = None):
        super().__init__()
        self.db = db
        self.creds = creds or CredentialStore()

    # preferências (não sensíveis) ficam na tabela meta
    @property
    def show_browser(self) -> bool:
        # padrão: navegador oculto; a janela só é útil para login Microsoft 365 ou verificação em duas etapas
        return self.db.get_meta("show_browser", "0") == "1"

    @show_browser.setter
    def show_browser(self, v: bool) -> None:
        self.db.set_meta("show_browser", "1" if v else "0")

    def labels(self) -> PortalLabels:
        d = PortalLabels()
        return PortalLabels(classroom_tile=self.db.get_meta("label_classroom", d.classroom_tile) or d.classroom_tile,
                            courses_menu=self.db.get_meta("label_courses", d.courses_menu) or d.courses_menu)

    def reopen_db(self) -> None:
        try:
            self.db.close()
        except Exception:  # noqa: BLE001
            pass
        self.db = Database(DB_PATH)
        self.data_changed.emit()
