"""Janela principal: navegação lateral, painel da atividade, notificações e atualização em segundo plano."""
from __future__ import annotations

import logging
import os
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
from app.ui.calendar_page import CalendarPage
from app.ui.dialogs import ReportDialog
from app.ui.drawer import ActivityPanel
from app.ui.grades_page import GradesPage
from app.ui.format import plural, relative_time
from app.ui.home import HomePage
from app.ui.icons import icon
from app.ui.settings_page import SettingsPage
from app.ui.theme import COLORS
from app.ui.widgets import Banner, LoadingBar, NotificationCard, Toast, button, label
from app.ui.workers import GradesWorker, UpdateWorker, WeeklyWorker

log = logging.getLogger(__name__)

PAGE_HOME, PAGE_BOARD, PAGE_CALENDAR, PAGE_GRADES, PAGE_SETTINGS = 0, 1, 2, 3, 4


class MainWindow(QMainWindow):
    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self.setWindowTitle(APP_TITLE)
        self.resize(1400, 880)
        self.setMinimumSize(1080, 660)
        self._worker: UpdateWorker | None = None
        self._gworker: GradesWorker | None = None
        self._wworker: WeeklyWorker | None = None
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
        self.calendar = CalendarPage(ctx)
        self.grades = GradesPage(ctx)
        self.settings = SettingsPage(ctx, main_window=self)
        for p in (self.home, self.board, self.calendar, self.grades, self.settings):
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
        self.notif = NotificationCard(self.content)
        self.notif.cancel_btn.clicked.connect(self._cancel)

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
        self.grades.request_update.connect(self.start_grades_update)
        self.calendar.open_activity.connect(self.open_activity)
        self.panel.changed.connect(lambda m: self.notify(m, None))
        self.panel.closed.connect(self._panel_closed)
        ctx.data_changed.connect(self._refresh_sync_card)

        # atalhos
        for keys, fn in (("F5", self._f5), ("Ctrl+N", lambda: self.new_activity(STATUS_TODO)),
                         ("Ctrl+F", self._focus_search), ("Escape", self.panel.request_close),
                         ("Ctrl+1", lambda: self.go(PAGE_HOME)), ("Ctrl+2", lambda: self.go(PAGE_BOARD)),
                         ("Ctrl+3", lambda: self.go(PAGE_CALENDAR)), ("Ctrl+4", lambda: self.go(PAGE_GRADES)),
                         ("Ctrl+5", lambda: self.go(PAGE_SETTINGS))):
            QShortcut(QKeySequence(keys), self, activated=fn)

        # textos relativos ("há 5 min") se mantêm corretos
        self._tick = QTimer(self)
        self._tick.timeout.connect(self._refresh_sync_card)
        self._tick.start(60_000)
        self._refresh_sync_card()
        self.go(PAGE_HOME)
        # atualização semanal automática: verificada logo após a janela abrir
        QTimer.singleShot(1500, self.maybe_weekly_update)

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
                           ("calendar", "Calendário", "Ctrl+3"), ("education", "Notas", "Ctrl+4"),
                           ("settings", "Configurações", "Ctrl+5"))
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
        if i in (PAGE_SETTINGS, PAGE_GRADES):
            self.panel.request_close()

    def _f5(self) -> None:
        """F5 atualiza o que está na tela: notas na aba Notas, atividades nas demais."""
        if self.stack.currentIndex() == PAGE_GRADES:
            self.start_grades_update()
        else:
            self.start_update()

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
        if self.stack.currentIndex() in (PAGE_SETTINGS, PAGE_GRADES):
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
        self.notif.raise_()

    def eventFilter(self, obj, e):
        if obj is self.stack and e.type() in (QEvent.Resize, QEvent.Move):
            self._place_panel()
        return super().eventFilter(obj, e)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.toast.isVisible():
            self.toast.reposition()
        if self.notif.isVisible():
            self.notif.reposition()

    # ------------------------------------------------------------------ atualização
    def update_running(self) -> bool:
        """Há alguma automação em andamento (atividades ou notas)?"""
        return any(w is not None and w.isRunning() for w in (self._worker, self._gworker, self._wworker))

    def _load_creds(self, purpose: str):
        try:
            creds = self.ctx.creds.load()
        except CredentialError as e:
            self._show_banner("error", "Não foi possível ler sua senha", str(e))
            return None
        if not creds:
            self.go(PAGE_SETTINGS if self.ctx.db.list_activities() else PAGE_HOME)
            self._show_banner("info", "Conecte sua conta do portal",
                              f"Informe seu usuário e senha para buscar {purpose}.")
        return creds

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
            self._busy_toast()
            return
        creds = self._load_creds("as atividades")
        if not creds:
            return
        self.banner_wrap.hide()
        self._worker = UpdateWorker(self.ctx, creds, self)
        self._worker.progress.connect(self.loading.set_progress)
        self._worker.finished_report.connect(self._finished)
        self._set_running(True)
        self.loading.start()
        self._worker.start()

    def _busy_toast(self) -> None:
        self.toast.show_message("Aguarde: já existe uma atualização em andamento", icon_name="info")

    def start_grades_update(self) -> None:
        if self.update_running():
            self._busy_toast()
            return
        creds = self._load_creds("suas notas")
        if not creds:
            return
        self.banner_wrap.hide()
        self._gworker = GradesWorker(self.ctx, creds, self)
        self._gworker.progress.connect(self.loading.set_progress)
        self._gworker.finished_report.connect(self._grades_finished)
        self._set_running(True)
        self.grades.set_updating(True)
        self.loading.start("Carregando notas do portal…")
        self._gworker.start()

    def _grades_finished(self, report) -> None:
        self._set_running(False)
        self.grades.set_updating(False)
        self.loading.hide()
        self.grades.refresh()
        self.settings._refresh_auth()
        from PySide6.QtWidgets import QMessageBox as _MB
        details = ("Ver detalhes", lambda: _MB.information(self, "Notas", report.summary_text()))
        if report.errors:
            self._error_banner(report.errors[0], details, "Não foi possível atualizar as notas")
            return
        if report.cancelled:
            self.toast.show_message("Leitura de notas interrompida · o que já foi lido foi salvo", details[0],
                                    details[1], "warning")
            return
        if report.courses_failed or report.avin_error:
            self._show_banner("warn", "Notas atualizadas, mas algo não pôde ser lido",
                              "Veja os detalhes para saber quais disciplinas ou resultados do AVIN faltaram.",
                              (details,))
        msg = (f"Notas atualizadas · {plural(len(report.courses_ok), 'matéria', 'matérias')}"
               + (f", {plural(len(report.avins), 'AVIN', 'AVINs')}" if report.avins else ""))
        self.toast.show_message(msg, details[0], details[1], ms=7000)

    # ------------------------------------------------------------------ atualização semanal automática
    def maybe_weekly_update(self) -> bool:
        """Roda tudo uma vez por semana (a partir de segunda); se o usuário pulou a segunda, roda no dia em que abrir."""
        from app.services.weekly import META_WEEKLY_ATTEMPT, META_WEEKLY_RUN, is_weekly_due
        if os.environ.get("UNIKANBAN_NO_AUTO_UPDATE") == "1":   # usado só em testes e verificações do executável
            return False
        if self.update_running():
            return False
        try:
            creds = self.ctx.creds.load()
        except Exception:  # noqa: BLE001 — sem acesso ao cofre: não incomoda o usuário na abertura
            return False
        if not creds:
            return False
        today = datetime.now(TZ).date()
        if not is_weekly_due(today, self.ctx.db.get_meta(META_WEEKLY_RUN), self.ctx.db.get_meta(META_WEEKLY_ATTEMPT)):
            return False
        log.info("Iniciando atualização semanal automática.")
        self.banner_wrap.hide()
        self._wworker = WeeklyWorker(self.ctx, creds, self)
        self._wworker.progress.connect(self._weekly_progress)
        self._wworker.finished_report.connect(self._weekly_finished)
        self._set_running(True)
        self.grades.set_updating(True)
        self.loading.start("Atualização semanal dos dados…")
        self.notif.show_message("Atualização de dados semanal em andamento", "Conectando ao portal")
        self._wworker.start()
        return True

    def _weekly_progress(self, p) -> None:
        self.loading.set_progress(p)
        from app.ui.format import short_course
        self.notif.set_detail(" · ".join(x for x in (p.step, short_course(p.course) if p.course else "") if x))

    def _weekly_finished(self, report) -> None:
        self._set_running(False)
        self.grades.set_updating(False)
        self.loading.hide()
        self.notif.hide()
        self.ctx.data_changed.emit()
        self.grades.refresh()
        self.settings._refresh_auth()
        details = ("Ver detalhes", lambda: QMessageBox.information(self, "Atualização semanal", report.summary_text()))
        errors = report.errors or report.activities.errors or report.grades.errors
        if errors:
            self._error_banner(errors[0], details, "A atualização semanal não foi concluída")
            return
        if report.cancelled or report.activities.cancelled or report.grades.cancelled:
            self.toast.show_message("Atualização semanal interrompida · ela será tentada de novo outro dia",
                                    details[0], details[1], "warning")
            return
        a = report.activities
        new = a.added + a.restored
        msg = (f"Atualização semanal concluída · {plural(new, 'atividade nova', 'atividades novas')} · "
               f"notas de {plural(len(report.grades.courses_ok), 'matéria', 'matérias')}")
        self.toast.show_message(msg, details[0], details[1], ms=8000)

    def _cancel(self) -> None:
        for w in (self._worker, self._gworker, self._wworker):
            if w is not None and w.isRunning():
                w.cancel()
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
            self._error_banner(report.errors[0], details, "Não foi possível atualizar")
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
        if report.auto_completed:
            parts.append(plural(len(report.auto_completed), "já entregue movida para Concluído",
                                "já entregues movidas para Concluído"))
        msg = "Tudo atualizado · " + (", ".join(parts) if parts else "nenhuma novidade")
        if report.conflicts or report.courses_failed or report.review:
            self._show_banner("warn", "Atualizado, mas alguns itens precisam da sua atenção",
                              "Veja os detalhes para revisar divergências ou disciplinas não verificadas.",
                              (details,))
        self.toast.show_message(msg, details[0], details[1], ms=7000)

    def _error_banner(self, err: str, details, generic_title: str) -> None:
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
            self._show_banner("error", generic_title,
                              first_line + " Seus dados locais foram preservados.", (details,))

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
            for w in (self._worker, self._gworker, self._wworker):
                if w is not None and w.isRunning():
                    w.cancel()
                    w.wait(30_000)
        try:
            self.ctx.db.close()
        except Exception:  # noqa: BLE001
            pass
        e.accept()
