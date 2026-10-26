"""Janela principal: navegação lateral, painel da atividade, notificações e atualização em segundo plano."""
from __future__ import annotations

import logging
from datetime import datetime

from PySide6.QtCore import QEvent, Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (QButtonGroup, QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QMainWindow,
                               QMessageBox, QPushButton,
                               QStackedWidget, QVBoxLayout, QWidget)

from app.config import APP_NAME, APP_TITLE, APP_VERSION, PORTAL_LOGIN_URL, TZ, resource_path
from app.models.activity import STATUS_TODO, iso_to_dt
from app.services.credentials import CredentialError
from app.ui.board import BoardPage
from app.ui.dialogs import ReportDialog
from app.ui.drawer import ActivityPanel
from app.ui.format import plural, relative_time
from app.ui.home import HomePage
from app.ui.icons import icon
from app.ui.settings_page import SettingsPage
from app.ui.theme import COLORS
from app.ui.widgets import Banner, LoadingBar, Toast, button, label
from app.ui.workers import UpdateWorker

log = logging.getLogger(__name__)

PAGE_HOME, PAGE_BOARD, PAGE_SETTINGS = 0, 1, 2


class MainWindow(QMainWindow):
    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self.setWindowTitle(APP_TITLE)
        self.resize(1400, 880)
        self.setMinimumSize(1080, 660)
        self._worker: UpdateWorker | None = None
        self._last_report = None

        root = QWidget()
        h = QHBoxLayout(root)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        h.addWidget(self._build_sidebar())

        self.content = QWidget()
        self.content.setObjectName("Content")
        cv = QVBoxLayout(self.content)
        cv.setContentsMargins(0, 0, 0, 0)
        cv.setSpacing(0)
        self.loading = LoadingBar()
        self.loading.cancel_btn.clicked.connect(self._cancel)
        cv.addWidget(self.loading)
        self.banner = Banner()
        bw = QWidget()
        bl = QVBoxLayout(bw)
        bl.setContentsMargins(28, 14, 28, 0)
        bl.addWidget(self.banner)
        self.banner_wrap = bw
        bw.hide()
        self.banner.close_btn.clicked.connect(bw.hide)
        cv.addWidget(bw)

        self.stack = QStackedWidget()
        self.home = HomePage(ctx)
        self.board = BoardPage(ctx)
        self.settings = SettingsPage(ctx, main_window=self)
        for p in (self.home, self.board, self.settings):
            self.stack.addWidget(p)
        cv.addWidget(self.stack, 1)
        h.addWidget(self.content, 1)
        self.setCentralWidget(root)

        # painel da atividade flutua sobre o conteúdo (não espreme o quadro)
        self.panel = ActivityPanel(ctx, self.content)
        shadow = QGraphicsDropShadowEffect(self.panel)
        shadow.setBlurRadius(36)
        shadow.setOffset(-6, 0)
        shadow.setColor(QColor(15, 23, 42, 45))
        self.panel.setGraphicsEffect(shadow)
        self.stack.installEventFilter(self)
        self.toast = Toast(self.content)

        # sinais
        self.home.request_update.connect(self.start_update)
        self.home.go_board.connect(self._go_board)
        self.home.open_activity.connect(self.open_activity)
        self.home.mark_done.connect(self.board.toggle_done)
        self.home.connect_requested.connect(self._connect_and_update)
        self.board.open_activity.connect(self.open_activity)
        self.board.new_activity.connect(self.new_activity)
        self.board.notify.connect(self.notify)
        self.settings.notify.connect(self.notify)
        self.panel.changed.connect(lambda m: self.notify(m, None))
        self.panel.closed.connect(self._panel_closed)
        ctx.data_changed.connect(self._refresh_sync_card)

        # atalhos
        for keys, fn in (("F5", self.start_update), ("Ctrl+N", lambda: self.new_activity(STATUS_TODO)),
                         ("Ctrl+F", self._focus_search), ("Escape", self.panel.request_close),
                         ("Ctrl+1", lambda: self.go(PAGE_HOME)), ("Ctrl+2", lambda: self.go(PAGE_BOARD)),
                         ("Ctrl+3", lambda: self.go(PAGE_SETTINGS))):
            QShortcut(QKeySequence(keys), self, activated=fn)

        # textos relativos ("há 5 min") se mantêm corretos
        self._tick = QTimer(self)
        self._tick.timeout.connect(self._refresh_sync_card)
        self._tick.start(60_000)
        self._refresh_sync_card()
        self.go(PAGE_HOME)

    # ------------------------------------------------------------------ barra lateral
    def _build_sidebar(self) -> QWidget:
        side = QWidget()
        side.setObjectName("Sidebar")
        side.setFixedWidth(236)
        sv = QVBoxLayout(side)
        sv.setContentsMargins(16, 20, 16, 16)
        sv.setSpacing(4)
        brand = QHBoxLayout()
        logo = QLabel()
        pm = QPixmap(str(resource_path("assets/icon.png")))
        if not pm.isNull():
            logo.setPixmap(pm.scaled(34, 34, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        brand.addWidget(logo)
        bt = QVBoxLayout()
        bt.setSpacing(0)
        bt.addWidget(label(APP_NAME, "Brand"))
        bt.addWidget(label("Tarefas Unilavras", "BrandSub"))
        brand.addLayout(bt, 1)
        sv.addLayout(brand)
        sv.addSpacing(22)

        self.nav = QButtonGroup(self)
        self.nav.setExclusive(True)
        self._nav_icons = (("home", "Início", "Ctrl+1"), ("board", "Quadro", "Ctrl+2"),
                           ("settings", "Configurações", "Ctrl+3"))
        for i, (ic, text, keys) in enumerate(self._nav_icons):
            b = QPushButton(f"  {text}")
            b.setObjectName("Nav")
            b.setCheckable(True)
            b.setIcon(icon(ic, COLORS["text_2"], 18))
            b.setToolTip(f"{text} ({keys})")
            b.clicked.connect(lambda _=False, i=i: self.go(i))
            self.nav.addButton(b, i)
            sv.addWidget(b)
        sv.addStretch(1)

        card = QFrame()
        card.setObjectName("SyncCard")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(12, 12, 12, 12)
        cl.setSpacing(6)
        self.sync_title = label("", "H3")
        self.sync_sub = label("", "Small", wrap=True)
        self.sync_btn = button("Atualizar agora", "Primary", "sync", tip="Buscar novidades no portal (F5)",
                               on_click=self.start_update)
        cl.addWidget(self.sync_title)
        cl.addWidget(self.sync_sub)
        cl.addWidget(self.sync_btn)
        sv.addWidget(card)
        sv.addSpacing(6)
        sv.addWidget(label(f"Versão {APP_VERSION} · dados salvos neste computador", "Small", wrap=True))
        return side

    def _refresh_sync_card(self, *_):
        last = iso_to_dt(self.ctx.db.get_meta("last_update"))
        if self.update_running():
            return
        self.sync_title.setText("Atualizado" if last else "Ainda não atualizado")
        self.sync_sub.setText(relative_time(last).capitalize() if last else "Busque suas atividades no portal.")
        if self.stack.currentWidget() is self.home:
            self.home.last.setText(f"Atualizado {relative_time(last)}" if last else "")

    # ------------------------------------------------------------------ navegação
    def go(self, i: int) -> None:
        self.nav.button(i).setChecked(True)
        self.stack.setCurrentIndex(i)
        if i == PAGE_SETTINGS:
            self.panel.request_close()

    def _go_board(self, flt: str) -> None:
        self.board.set_quick_filter(urgent=flt == "urgentes", hide_done=flt == "pendentes")
        self.go(PAGE_BOARD)

    def _focus_search(self) -> None:
        self.go(PAGE_BOARD)
        self.board.focus_search()

    def open_activity(self, aid: int) -> None:
        if self.panel.open_activity(aid):
            self._place_panel()
            self.board.selected_id = aid
            self.board.refresh()

    def new_activity(self, status: str) -> None:
        if self.stack.currentIndex() == PAGE_SETTINGS:
            self.go(PAGE_BOARD)
        if self.panel.open_new(status):
            self._place_panel()
            self.board.selected_id = None
            self.board.refresh()

    def _panel_closed(self) -> None:
        self.board.selected_id = None
        self.board.refresh()

    def notify(self, msg: str, action=None) -> None:
        if callable(action):
            self.toast.show_message(msg, "Desfazer", action)
        elif isinstance(action, tuple):
            self.toast.show_message(msg, action[0], action[1])
        else:
            self.toast.show_message(msg)

    def _place_panel(self) -> None:
        g = self.stack.geometry()
        self.panel.setGeometry(self.content.width() - self.panel.WIDTH, g.top(), self.panel.WIDTH, g.height())
        self.panel.raise_()
        self.toast.raise_()

    def eventFilter(self, obj, e):
        if obj is self.stack and e.type() in (QEvent.Resize, QEvent.Move):
            self._place_panel()
        return super().eventFilter(obj, e)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.toast.isVisible():
            self.toast.reposition()

    # ------------------------------------------------------------------ atualização
    def update_running(self) -> bool:
        return self._worker is not None and self._worker.isRunning()

    def _connect_and_update(self, user: str, pwd: str) -> None:
        try:
            self.ctx.creds.save(user, pwd)
        except CredentialError as e:
            self.onboarding_error(str(e))
            return
        self.settings.load()
        self.start_update()

    def onboarding_error(self, msg: str) -> None:
        self.home.onboarding.error.setText(msg)
        self.home.onboarding.error.show()

    def start_update(self) -> None:
        if self.update_running():
            return
        try:
            creds = self.ctx.creds.load()
        except CredentialError as e:
            self._show_banner("error", "Não foi possível ler sua senha", str(e))
            return
        if not creds:
            self.go(PAGE_SETTINGS if self.ctx.db.list_activities() else PAGE_HOME)
            self._show_banner("info", "Conecte sua conta do portal",
                              "Informe seu usuário e senha para buscar as atividades.")
            return
        self.banner_wrap.hide()
        self._worker = UpdateWorker(self.ctx, creds, self)
        self._worker.progress.connect(self.loading.set_progress)
        self._worker.finished_report.connect(self._finished)
        self._set_running(True)
        self.loading.start()
        self._worker.start()

    def _cancel(self) -> None:
        if self.update_running():
            self._worker.cancel()
            self.loading.set_cancelling()

    def _finished(self, report) -> None:
        self._last_report = report
        self._set_running(False)
        self.loading.hide()
        self.ctx.data_changed.emit()
        self.settings._refresh_auth()
        self.ctx.update_finished.emit(report)
        details = ("Ver detalhes", lambda: ReportDialog(report, self).exec())
        if report.errors:
            err = report.errors[0]
            first_line = err.split("\n")[0]
            if "verificação de segurança" in err:
                self._show_banner("warn", "O portal pediu uma verificação de segurança",
                                  "Isso acontece depois de várias tentativas seguidas — suas credenciais estão "
                                  "corretas. Entre uma vez pelo seu navegador, conclua a verificação e tente de novo "
                                  "em alguns minutos.",
                                  (("Abrir portal no navegador",
                                    lambda: QDesktopServices.openUrl(QUrl(PORTAL_LOGIN_URL))), details))
            elif "recusou o login" in err:
                if self.home.onb_wrap.isVisible():
                    self.onboarding_error("Usuário ou senha não aceitos pelo portal. Confira e tente de novo.")
                self._show_banner("error", "O portal não aceitou o login", first_line,
                                  (("Revisar conta", lambda: self.go(PAGE_SETTINGS)), details))
            else:
                self._show_banner("error", "Não foi possível atualizar",
                                  first_line + " Seus dados locais foram preservados.", (details,))
            return
        if report.cancelled:
            self.toast.show_message("Atualização interrompida · o que já foi lido foi salvo", details[0], details[1],
                                    "warning")
            return
        new = report.added + report.restored
        parts = []
        if new:
            parts.append(plural(new, "nova", "novas"))
        if report.updated:
            parts.append(plural(report.updated, "alterada", "alteradas"))
        msg = "Tudo atualizado · " + (", ".join(parts) if parts else "nenhuma novidade")
        if report.conflicts or report.courses_failed or report.review:
            self._show_banner("warn", "Atualizado, mas alguns itens precisam da sua atenção",
                              "Veja os detalhes para revisar divergências ou disciplinas não verificadas.",
                              (details,))
        self.toast.show_message(msg, details[0], details[1], ms=7000)

    def _show_banner(self, kind: str, title: str, text: str = "", actions=()) -> None:
        self.banner.show_message(kind, title, text, actions)
        self.banner_wrap.show()

    def _set_running(self, running: bool) -> None:
        self.home.set_updating(running)
        self.sync_btn.setEnabled(not running)
        self.sync_btn.setText("Atualizando…" if running else "Atualizar agora")
        if running:
            self.sync_title.setText("Atualizando…")
            self.sync_sub.setText("Você pode continuar usando o quadro.")
        else:
            self._refresh_sync_card()

    def closeEvent(self, e):
        if not self.panel.confirm_discard():
            e.ignore()
            return
        if self.update_running():
            if QMessageBox.question(self, "Atualização em andamento",
                                    "Uma atualização está em andamento. Interromper e sair?\n"
                                    "O que já foi lido fica salvo.") != QMessageBox.Yes:
                e.ignore()
                return
            self._worker.cancel()
            self._worker.wait(30_000)
        try:
            self.ctx.db.close()
        except Exception:  # noqa: BLE001
            pass
        e.accept()
