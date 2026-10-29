"""Janela principal: navegação lateral, painel da atividade, notificações e atualização em segundo plano."""
from __future__ import annotations

import logging
import os
from datetime import datetime

import shiboken6
from PySide6.QtCore import QEasingCurve, QEvent, QPropertyAnimation, Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (QApplication, QButtonGroup, QCheckBox, QFrame, QGraphicsDropShadowEffect,
                               QGraphicsOpacityEffect, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPushButton,
                               QStackedWidget, QVBoxLayout, QWidget)

from app.config import APP_NAME, APP_TITLE, APP_VERSION, PORTAL_LOGIN_URL, TZ, resource_path
from app.models.activity import STATUS_TODO, iso_to_dt
from app.services.credentials import CredentialError
from app.ui.about_page import AboutPage
from app.ui.agenda_page import AgendaPage
from app.ui.board import BoardPage
from app.ui.calendar_page import CalendarPage
from app.ui.dialogs import ReportDialog
from app.ui.drawer import ActivityPanel
from app.ui.events_page import EventsPage
from app.ui.grades_page import GradesPage
from app.ui.format import plural, relative_time
from app.ui.home import HomePage
from app.ui.icons import icon
from app.ui.settings_page import SettingsPage
from app.ui.theme import COLORS, apply_theme
from app.ui.widgets import Banner, LoadingBar, NotificationCard, Toast, button, icon_label, label
from app.ui.workers import EventsWorker, FullWorker, GradesWorker

log = logging.getLogger(__name__)

(PAGE_HOME, PAGE_BOARD, PAGE_CALENDAR, PAGE_GRADES, PAGE_EVENTS, PAGE_AGENDA, PAGE_ABOUT,
 PAGE_SETTINGS) = range(8)
NO_DRAWER_PAGES = (PAGE_GRADES, PAGE_EVENTS, PAGE_ABOUT, PAGE_SETTINGS)   # páginas sem o painel da atividade


class MainWindow(QMainWindow):
    def __init__(self, ctx, start_page: int = PAGE_HOME, auto_update: bool = True):
        super().__init__()
        self.ctx = ctx
        ctx.window = self
        self.setWindowTitle(APP_TITLE)
        self.resize(1400, 880)
        self.setMinimumSize(1080, 660)
        self._worker: FullWorker | None = None         # "Atualizar agora": atividades + notas + eventos
        self._gworker: GradesWorker | None = None
        self._wworker: FullWorker | None = None        # atualização semanal automática
        self._eworker: EventsWorker | None = None
        self._last_report = None
        self._fade: QLabel | None = None               # imagem da tela anterior durante a troca de tema

        self._build_ui(start_page)
        ctx.data_changed.connect(self._refresh_sync_card)
        if auto_update:
            # atualização semanal automática: verificada logo após a janela abrir
            QTimer.singleShot(1500, self.maybe_weekly_update)

    def _build_ui(self, start_page: int) -> None:
        """Monta todo o conteúdo da janela; chamado de novo ao trocar o tema, pois as cores entram na montagem."""
        ctx = self.ctx
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
        self.events = EventsPage(ctx)
        self.agenda = AgendaPage(ctx)
        self.about = AboutPage(ctx)
        self.settings = SettingsPage(ctx, main_window=self)
        for p in (self.home, self.board, self.calendar, self.grades, self.events, self.agenda, self.about,
                  self.settings):
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
        self.events.request_update.connect(self.start_events_update)
        self.events.notify.connect(self.notify)
        self.agenda.open_activity.connect(self.open_activity)
        self.agenda.notify.connect(self.notify)
        self.calendar.open_activity.connect(self.open_activity)
        self.panel.changed.connect(lambda m: self.notify(m, None))
        self.panel.closed.connect(self._panel_closed)

        # atalhos e timer pertencem ao conteúdo: somem junto com ele quando o tema é trocado
        for keys, fn in (("F5", self._f5), ("Ctrl+N", self._new_shortcut),
                         ("Ctrl+F", self._focus_search), ("Escape", self.panel.request_close)):
            QShortcut(QKeySequence(keys), root, activated=fn)
        for i in range(len(self._nav_icons)):
            QShortcut(QKeySequence(f"Ctrl+{i + 1}"), root, activated=lambda i=i: self.go(i))

        # textos relativos ("há 5 min") se mantêm corretos
        self._tick = QTimer(root)
        self._tick.timeout.connect(self._refresh_sync_card)
        self._tick.start(60_000)
        self._refresh_sync_card()
        self.go(start_page)

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
        bt.addWidget(label("Seu espaço na Unilavras", "BrandSub"))
        brand.addLayout(bt, 1)
        sv.addLayout(brand)
        sv.addSpacing(22)

        self.nav = QButtonGroup(side)
        self.nav.setExclusive(True)
        self._nav_icons = (("home", "Início"), ("board", "Quadro de Atividades"), ("calendar", "Calendário"),
                           ("education", "Notas"), ("event", "Eventos"), ("agenda", "Agenda"), ("info", "Sobre"),
                           ("settings", "Configurações"))
        for i, (ic, text) in enumerate(self._nav_icons):
            b = QPushButton(f"  {text}")
            b.setObjectName("Nav")
            b.setCheckable(True)
            b.setIcon(icon(ic, COLORS["text_2"], 18))
            b.setToolTip(f"{text} (Ctrl+{i + 1})")
            b.clicked.connect(lambda _=False, i=i: self.go(i))
            self.nav.addButton(b, i)
            sv.addWidget(b)
        sv.addStretch(1)

        # modo noturno (logo acima do cartão de atualização)
        dark = self.ctx.dark_mode
        row = QFrame()
        row.setObjectName("ThemeRow")
        rl = QHBoxLayout(row)
        rl.setContentsMargins(12, 6, 8, 6)
        rl.setSpacing(10)
        rl.addWidget(icon_label("moon" if dark else "sun", COLORS["text_2"], 16))
        rl.addWidget(label("Modo noturno"), 1)
        self.dark_switch = QCheckBox()
        self.dark_switch.setObjectName("Switch")
        self.dark_switch.setCursor(Qt.PointingHandCursor)
        self.dark_switch.setToolTip("Alternar entre o tema claro e o escuro")
        self.dark_switch.setAccessibleName("Modo noturno")
        self.dark_switch.setChecked(dark)
        self.dark_switch.toggled.connect(self.set_dark_mode)
        rl.addWidget(self.dark_switch)
        sv.addWidget(row)
        sv.addSpacing(6)

        card = QFrame()
        card.setObjectName("SyncCard")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(12, 12, 12, 12)
        cl.setSpacing(6)
        self.sync_title = label("", "H3")
        self.sync_sub = label("", "Small", wrap=True)
        self.sync_btn = button("Atualizar agora", "Primary", "sync",
                               tip="Atualizar tudo: atividades, notas e eventos (F5)", on_click=self.start_update)
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
        self.sync_sub.setText(relative_time(last).capitalize() if last else "Busque seus dados no portal.")
        if self.stack.currentWidget() is self.home:
            self.home.last.setText(f"Atualizado {relative_time(last)}" if last else "")

    # ------------------------------------------------------------------ modo noturno
    def set_dark_mode(self, on: bool) -> None:
        if on == self.ctx.dark_mode:
            return
        busy = self.update_running()
        if busy or not self.panel.confirm_discard():
            if busy:
                self.toast.show_message("Aguarde a atualização terminar para trocar o tema", icon_name="info")
            self.dark_switch.blockSignals(True)
            self.dark_switch.setChecked(not on)
            self.dark_switch.blockSignals(False)
            return
        # a tela atual fica congelada por cima enquanto o conteúdo é remontado, e depois esmaece
        self._fade = QLabel(self)
        self._fade.setPixmap(self.grab())
        self._fade.setGeometry(self.rect())
        self._fade.show()
        self.ctx.dark_mode = on
        QTimer.singleShot(0, self._retheme)          # fora do sinal do botão, que é remontado junto

    def _retheme(self) -> None:
        """As cores são aplicadas na montagem dos widgets: remonta o conteúdo na mesma janela e na mesma aba."""
        page = self.stack.currentIndex()
        # o conteúdo antigo é destruído antes de trocar a folha de estilos: restilizá-lo à toa custava segundos
        shiboken6.delete(self.takeCentralWidget())
        apply_theme(QApplication.instance(), dark=self.ctx.dark_mode)
        self._build_ui(page)
        snap, self._fade = self._fade, None
        if snap is None:
            return
        snap.raise_()
        fx = QGraphicsOpacityEffect(snap)
        snap.setGraphicsEffect(fx)
        anim = QPropertyAnimation(fx, b"opacity", snap)
        anim.setDuration(260)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.finished.connect(snap.deleteLater)
        anim.start()

    # ------------------------------------------------------------------ navegação
    def go(self, i: int) -> None:
        self.nav.button(i).setChecked(True)
        self.stack.setCurrentIndex(i)
        if i in NO_DRAWER_PAGES:
            self.panel.request_close()

    def _f5(self) -> None:
        """F5 atualiza o que está na tela: só notas na aba Notas, só eventos na aba Eventos e tudo nas demais."""
        page = self.stack.currentIndex()
        if page == PAGE_GRADES:
            self.start_grades_update()
        elif page == PAGE_EVENTS:
            self.start_events_update()
        else:
            self.start_update()

    def _new_shortcut(self) -> None:
        if self.stack.currentIndex() == PAGE_AGENDA:
            self.agenda.new_item()
        else:
            self.new_activity(STATUS_TODO)

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
        if self.stack.currentIndex() in NO_DRAWER_PAGES:
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
    def _workers(self):
        return self._worker, self._gworker, self._wworker, self._eworker

    def update_running(self) -> bool:
        """Há alguma automação em andamento (atualização completa, notas ou eventos)?"""
        return any(w is not None and w.isRunning() for w in self._workers())

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
        """"Atualizar agora": atividades, notas/AVIN, encontros e eventos com um único login."""
        if self.update_running():
            self._busy_toast()
            return
        creds = self._load_creds("seus dados")
        if not creds:
            return
        self.banner_wrap.hide()
        self._worker = FullWorker(self.ctx, creds, self)
        self._worker.progress.connect(self.loading.set_progress)
        self._worker.finished_report.connect(self._finished)
        self._set_running(True)
        self.loading.start("Atualizando atividades, notas e eventos…")
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
        self.loading.start("Carregando notas do portal…")
        self._gworker.start()

    def _grades_finished(self, report) -> None:
        self._set_running(False)
        self.loading.hide()
        self.grades.refresh()
        self.settings._refresh_auth()
        details = ("Ver detalhes", lambda: QMessageBox.information(self, "Notas", report.summary_text()))
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

    def start_events_update(self) -> None:
        """Só os eventos: página pública da Unilavras, sem login e sem abrir o navegador."""
        if self.update_running():
            self._busy_toast()
            return
        self.banner_wrap.hide()
        self._eworker = EventsWorker(self.ctx, self)
        self._eworker.progress.connect(self.loading.set_progress)
        self._eworker.finished_report.connect(self._events_finished)
        self._set_running(True)
        self.loading.start("Carregando eventos da Unilavras…")
        self._eworker.start()

    def _events_finished(self, report) -> None:
        self._set_running(False)
        self.loading.hide()
        self.ctx.events_changed.emit()
        details = ("Ver detalhes", lambda: QMessageBox.information(self, "Eventos", report.summary_text()))
        if report.errors:
            self._show_banner("error", "Não foi possível atualizar os eventos", report.errors[0], (details,))
            return
        if report.cancelled:
            self.toast.show_message("Leitura de eventos interrompida", icon_name="warning")
            return
        msg = f"Eventos atualizados · {plural(report.found, 'evento', 'eventos')}"
        if report.new:
            msg += f", {plural(report.new, 'novo', 'novos')}"
        self.toast.show_message(msg, details[0], details[1], ms=6000)

    # ------------------------------------------------------------------ atualização semanal automática
    def maybe_weekly_update(self) -> bool:
        """Roda tudo uma vez por semana (a partir de segunda); se o usuário pulou a segunda, roda no dia em que abrir."""
        from app.services.weekly import META_WEEKLY_ATTEMPT, META_WEEKLY_RUN, is_weekly_due
        if os.environ.get("UNISPACE_NO_AUTO_UPDATE") == "1":   # usado só em testes e verificações do executável
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
        self._wworker = FullWorker(self.ctx, creds, self)
        self._wworker.progress.connect(self._weekly_progress)
        self._wworker.finished_report.connect(self._weekly_finished)
        self._set_running(True)
        self.loading.start("Atualização semanal dos dados…")
        self.notif.show_message("Atualização de dados semanal em andamento", "Conectando ao portal")
        self._wworker.start()
        return True

    def _weekly_progress(self, p) -> None:
        self.loading.set_progress(p)
        from app.ui.format import short_course
        self.notif.set_detail(" · ".join(x for x in (p.step, short_course(p.course) if p.course else "") if x))

    def _weekly_finished(self, report) -> None:
        self.notif.hide()
        self._full_done(report, weekly=True)

    def _finished(self, report) -> None:
        self._full_done(report, weekly=False)

    def _full_done(self, report, weekly: bool) -> None:
        a = report.activities
        self._last_report = a
        self._set_running(False)
        self.loading.hide()
        self.ctx.data_changed.emit()
        self.ctx.events_changed.emit()
        self.settings._refresh_auth()
        self.ctx.update_finished.emit(a)
        details = ("Ver detalhes", lambda: ReportDialog(a, self, self._extra_lines(report)).exec())
        errors = report.errors or a.errors or report.grades.errors
        if errors:
            self._error_banner(errors[0], details,
                               "A atualização semanal não foi concluída" if weekly else "Não foi possível atualizar")
            return
        if report.cancelled or a.cancelled or report.grades.cancelled:
            self.toast.show_message("Atualização semanal interrompida · ela será tentada de novo outro dia" if weekly
                                    else "Atualização interrompida · o que já foi lido foi salvo",
                                    details[0], details[1], "warning")
            return
        new = a.added + a.restored
        if weekly:
            parts = [plural(new, "atividade nova", "atividades novas")]
        else:
            parts = [plural(new, "nova", "novas")] if new else []
            if a.updated:
                parts.append(plural(a.updated, "alterada", "alteradas"))
            if a.auto_completed:
                parts.append(plural(len(a.auto_completed), "já entregue movida para Concluído",
                                    "já entregues movidas para Concluído"))
            if not parts:
                parts.append("nenhuma atividade nova")
        parts.append(f"notas de {plural(len(report.grades.courses_ok), 'matéria', 'matérias')}")
        if not report.events.errors:
            parts.append(plural(report.events.found, "evento", "eventos"))
        msg = ("Atualização semanal concluída · " if weekly else "Tudo atualizado · ") + ", ".join(parts)
        g, ev = report.grades, report.events
        if a.conflicts or a.courses_failed or a.review or g.courses_failed or g.avin_error or ev.errors:
            self._show_banner("warn", "Atualizado, mas alguns itens precisam da sua atenção",
                              "Veja os detalhes para revisar divergências ou o que não pôde ser lido.", (details,))
        self.toast.show_message(msg, details[0], details[1], ms=8000)

    @staticmethod
    def _extra_lines(report) -> list[str]:
        g, ev = report.grades, report.events
        lines = [f"<b>Notas:</b> {plural(len(g.courses_ok), 'matéria atualizada', 'matérias atualizadas')}"]
        lines += [f"AVIN — {name}: {score}" for name, score in g.avins]
        lines += [f"Não foi possível ler as notas de {c}: {why}" for c, why in g.courses_failed]
        if g.avin_error:
            lines.append(f"Não foi possível ler o AVIN: {g.avin_error}")
        if ev.errors:
            lines.append(f"<b>Eventos:</b> {ev.errors[0]}")
        else:
            lines.append(f"<b>Eventos:</b> {plural(ev.found, 'evento', 'eventos')}"
                         + (f" ({plural(ev.new, 'novo', 'novos')})" if ev.new else ""))
        return lines

    def _cancel(self) -> None:
        for w in self._workers():
            if w is not None and w.isRunning():
                w.cancel()
                self.loading.set_cancelling()

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
        self.grades.set_updating(running)
        self.events.set_updating(running)
        self.sync_btn.setEnabled(not running)
        self.sync_btn.setText("Atualizando…" if running else "Atualizar agora")
        self.dark_switch.setEnabled(not running)
        if running:
            self.sync_title.setText("Atualizando…")
            self.sync_sub.setText("Você pode continuar usando o aplicativo.")
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
            for w in self._workers():
                if w is not None and w.isRunning():
                    w.cancel()
                    w.wait(30_000)
        try:
            self.ctx.db.close()
        except Exception:  # noqa: BLE001
            pass
        e.accept()
