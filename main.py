"""Ponto de entrada do UniSpace."""
from __future__ import annotations

import logging
import os
import sys


def _configure_playwright_for_frozen() -> None:
    # No executável, o Playwright usa o navegador instalado (Chrome, Firefox ou Edge); não precisa baixar navegadores.
    if getattr(sys, "frozen", False):
        os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "0")


def diagnose() -> int:
    """`UniSpace --diagnostico`: verifica navegador + Playwright abrindo a tela de login (sem credenciais)."""
    from playwright.sync_api import sync_playwright

    from app.automation import browsers
    from app.config import PORTAL_LOGIN_URL
    try:
        with sync_playwright() as p:
            def open_with(choice):
                kw = choice.launch_args
                kw.pop("args", None)
                return getattr(p, choice.engine).launch(headless=True, **kw)
            b, choice = browsers.first_available(open_with)
            pg = b.new_page()
            pg.goto(PORTAL_LOGIN_URL, wait_until="domcontentloaded", timeout=60_000)
            pg.locator("#username").wait_for(timeout=30_000)
            ok = pg.locator("#password").count() == 1
            b.close()
    except LookupError as e:
        print(f"FALHA: nenhum navegador compatível ({e})")
        return 2
    except Exception as e:  # noqa: BLE001
        print(f"FALHA: {type(e).__name__}: {str(e).splitlines()[0]}")
        return 2
    print(f"OK: {choice.label} iniciado e tela de login do portal encontrada." if ok else
          "FALHA: campo de senha ausente")
    return 0 if ok else 3


def main() -> int:
    _configure_playwright_for_frozen()
    if "--diagnostico" in sys.argv:
        return diagnose()
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication, QMessageBox

    from app.config import APP_NAME, DB_PATH, ensure_dirs, migrate_legacy_data, resource_path
    from app.database.db import Database, DatabaseError
    from app.services.credentials import CredentialStore
    from app.services.logging_setup import setup_logging
    from app.ui.context import AppContext
    from app.ui.main_window import MainWindow
    from app.ui.theme import apply_theme

    try:
        migrated = migrate_legacy_data()        # UniKanban -> UniSpace (pasta de dados)
    except OSError:
        migrated = False                        # pasta antiga em uso: tenta de novo na próxima abertura
    ensure_dirs()
    setup_logging()
    log = logging.getLogger("main")
    log.info("Iniciando %s", APP_NAME)
    if migrated:
        log.info("Dados do UniKanban migrados para a pasta do UniSpace.")

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    apply_theme(app)
    icon = resource_path("assets/icon.ico")
    if icon.exists():
        app.setWindowIcon(QIcon(str(icon)))

    try:
        db = Database(DB_PATH)
    except DatabaseError as e:
        QMessageBox.critical(None, APP_NAME, f"{e}\n\nPasta de dados: {DB_PATH.parent}")
        return 1

    def excepthook(t, v, tb):
        log.error("Erro não tratado", exc_info=(t, v, tb))
        QMessageBox.critical(None, APP_NAME, f"Ocorreu um erro inesperado: {v}\nOs dados salvos foram preservados.")

    sys.excepthook = excepthook
    creds = CredentialStore()
    creds.migrate_from()
    ctx = AppContext(db, creds)
    if ctx.dark_mode:
        apply_theme(app, dark=True)
    MainWindow(ctx).show()                      # a janela se registra em ctx.window (o modo noturno a recria)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
