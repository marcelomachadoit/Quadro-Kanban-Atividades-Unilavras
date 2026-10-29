"""Tela inicial: boas-vindas/conexão, resumo do que importa e próximas entregas agrupadas."""
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLineEdit, QScrollArea, QVBoxLayout, QWidget)

from app.config import TZ
from app.models.activity import STATUS_DOING, STATUS_DONE, STATUS_TODO, iso_to_dt
from app.ui.board import due_key
from app.ui.format import (GROUP_ORDER, URG_OVERDUE, URG_SOON, course_color, friendly_due, greeting, group_label,
                           plural, points_short, relative_time, short_course, urgency)
from app.ui.icons import icon
from app.ui.theme import COLORS, URGENCY_STYLE
from app.ui.widgets import Dot, EmptyState, Pill, button, clear_layout, icon_button, icon_label, label


class Tile(QFrame):
    clicked = Signal()

    def __init__(self, icon_name: str, color: str, title: str, hint: str):
        super().__init__()
        self.setObjectName("Tile")
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(hint)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(2)
        top = QHBoxLayout()
        top.addWidget(icon_label(icon_name, color, 16))
        top.addStretch(1)
        top.addWidget(icon_label("chevron_right", COLORS["subtle"], 12))
        lay.addLayout(top)
        self.value = label("0", "TileValue")
        lay.addWidget(self.value)
        lay.addWidget(label(title, "Muted"))
        self.setAccessibleName(title)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clicked.emit()


class Onboarding(QFrame):
    """Primeiro uso: conectar a conta e já buscar as atividades."""
    connect_requested = Signal(str, str)

    def __init__(self):
        super().__init__()
        self.setObjectName("Panel")
        self.setFixedWidth(520)
        v = QVBoxLayout(self)
        v.setContentsMargins(32, 28, 32, 28)
        v.setSpacing(10)
        v.addWidget(icon_label("lock", COLORS["primary"], 26), 0, Qt.AlignLeft)
        v.addWidget(label("Conecte sua conta do portal", "H2"))
        v.addWidget(label("Use o mesmo usuário e senha do portal do aluno Unilavras. O UniSpace entra na "
                          "Sala de Aula Virtual, lê suas disciplinas e monta o quadro para você.", "Muted", wrap=True))
        v.addSpacing(6)
        v.addWidget(label("Usuário", "FieldLabel"))
        self.user = QLineEdit()
        self.user.setPlaceholderText("Seu usuário do portal")
        self.user.addAction(icon("user", COLORS["subtle"]), QLineEdit.LeadingPosition)
        v.addWidget(self.user)
        v.addWidget(label("Senha", "FieldLabel"))
        self.pwd = QLineEdit()
        self.pwd.setEchoMode(QLineEdit.Password)
        self.pwd.setPlaceholderText("Sua senha do portal")
        self.pwd.addAction(icon("lock", COLORS["subtle"]), QLineEdit.LeadingPosition)
        self._eye = self.pwd.addAction(icon("eye", COLORS["muted"]), QLineEdit.TrailingPosition)
        self._eye.setToolTip("Mostrar senha")
        self._eye.triggered.connect(self._toggle)
        v.addWidget(self.pwd)
        self.go = button("Conectar e buscar atividades", "Primary", "sync", on_click=self._submit)
        self.go.setMinimumHeight(40)
        v.addSpacing(6)
        v.addWidget(self.go)
        self.error = label("", wrap=True)
        self.error.setStyleSheet(f"color:{COLORS['danger']};")
        self.error.hide()
        v.addWidget(self.error)
        v.addSpacing(4)
        v.addWidget(label("🔒  A senha fica guardada no chaveiro do sistema (GNOME Keyring ou KWallet), nunca em arquivos. "
                          "O aplicativo apenas lê o portal: nada é enviado ou alterado lá.", "Small", wrap=True))
        self.pwd.returnPressed.connect(self._submit)
        self.user.returnPressed.connect(lambda: self.pwd.setFocus())

    def _toggle(self) -> None:
        hidden = self.pwd.echoMode() == QLineEdit.Password
        self.pwd.setEchoMode(QLineEdit.Normal if hidden else QLineEdit.Password)
        self._eye.setIcon(icon("eye_off" if hidden else "eye", COLORS["muted"]))
        self._eye.setToolTip("Ocultar senha" if hidden else "Mostrar senha")

    def _submit(self) -> None:
        u, p = self.user.text().strip(), self.pwd.text()
        if not u or not p:
            self.error.setText("Preencha usuário e senha.")
            self.error.show()
            return
        self.error.hide()
        self.connect_requested.emit(u, p)


class UpcomingRow(QFrame):
    clicked = Signal(int)
    done = Signal(int)

    def __init__(self, a, now: datetime):
        super().__init__()
        self.setObjectName("Row")
        self.setCursor(Qt.PointingHandCursor)
        self.aid = a.id
        h = QHBoxLayout(self)
        h.setContentsMargins(10, 8, 6, 8)
        h.setSpacing(10)
        h.addWidget(Dot(course_color(a.course), 10))
        tv = QVBoxLayout()
        tv.setSpacing(1)
        tv.addWidget(label(a.name, "H3", wrap=True))
        tv.addWidget(label(short_course(a.course), "Small"))
        h.addLayout(tv, 1)
        u = urgency(a, now)
        fg, bg, ic = URGENCY_STYLE[u]
        if u in (URG_SOON, URG_OVERDUE):
            h.addWidget(Pill(friendly_due(a.due_at, now), fg, bg, ic))
        else:
            h.addWidget(label(friendly_due(a.due_at, now), "Muted"))
        pts = points_short(a.points)
        p = label(pts or "", "Small")
        p.setFixedWidth(48)
        p.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        h.addWidget(p)
        h.addWidget(icon_button("circle", "Marcar como concluída", lambda: self.done.emit(a.id), COLORS["subtle"]))

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clicked.emit(self.aid)


class HomePage(QWidget):
    request_update = Signal()
    go_board = Signal(str)            # filtro rápido: "", "urgentes", "pendentes"
    open_activity = Signal(int)
    mark_done = Signal(int)
    connect_requested = Signal(str, str)

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.setObjectName("Page")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        body.setObjectName("Page")
        scroll.setWidget(body)
        outer.addWidget(scroll)
        lay = QVBoxLayout(body)
        lay.setContentsMargins(32, 26, 32, 28)
        lay.setSpacing(18)

        head = QHBoxLayout()
        tv = QVBoxLayout()
        tv.setSpacing(2)
        self.hello = label("", "H1")
        self.summary = label("", "Muted", wrap=True)
        tv.addWidget(self.hello)
        tv.addWidget(self.summary)
        head.addLayout(tv, 1)
        rv = QVBoxLayout()
        rv.setSpacing(4)
        self.update_btn = button("Atualizar agora", "Primary", "sync",
                                 tip="Atualizar tudo: atividades, notas e eventos (F5)",
                                 on_click=self.request_update.emit)
        self.update_btn.setMinimumHeight(38)
        self.last = label("", "Small")
        self.last.setAlignment(Qt.AlignRight)
        rv.addWidget(self.update_btn)
        rv.addWidget(self.last)
        head.addLayout(rv)
        lay.addLayout(head)

        self.onboarding = Onboarding()
        self.onboarding.connect_requested.connect(self.connect_requested.emit)
        self.onb_wrap = QWidget()
        ow = QHBoxLayout(self.onb_wrap)
        ow.setContentsMargins(0, 10, 0, 0)
        ow.addWidget(self.onboarding)
        ow.addStretch(1)
        lay.addWidget(self.onb_wrap)

        self.main = QWidget()
        mv = QVBoxLayout(self.main)
        mv.setContentsMargins(0, 0, 0, 0)
        mv.setSpacing(18)
        grid = QGridLayout()
        grid.setSpacing(12)
        self.t_soon = Tile("clock", COLORS["warn"], "Vencem em até 48 h", "Ver só as atividades urgentes")
        self.t_todo = Tile("circle", COLORS["status_todo"], "A fazer", "Abrir o quadro")
        self.t_doing = Tile("sync", COLORS["primary"], "Em andamento", "Abrir o quadro")
        self.t_done = Tile("check_circle", COLORS["ok"], "Concluídas", "Abrir o quadro")
        self.t_soon.clicked.connect(lambda: self.go_board.emit("urgentes"))
        for t in (self.t_todo, self.t_doing, self.t_done):
            t.clicked.connect(lambda: self.go_board.emit(""))
        for i, t in enumerate((self.t_soon, self.t_todo, self.t_doing, self.t_done)):
            grid.addWidget(t, 0, i)
        mv.addLayout(grid)

        panel = QFrame()
        panel.setObjectName("Panel")
        pl = QVBoxLayout(panel)
        pl.setContentsMargins(20, 16, 20, 14)
        pl.setSpacing(4)
        ph = QHBoxLayout()
        ph.addWidget(label("Próximas entregas", "H2"))
        ph.addStretch(1)
        ph.addWidget(button("Ver no quadro", "Link", on_click=lambda: self.go_board.emit("pendentes")))
        pl.addLayout(ph)
        self.upcoming = QVBoxLayout()
        self.upcoming.setSpacing(0)
        pl.addLayout(self.upcoming)
        mv.addWidget(panel)
        mv.addStretch(1)
        lay.addWidget(self.main)
        lay.addStretch(1)

        ctx.data_changed.connect(self.refresh)
        self.refresh()

    def refresh(self, *_):
        now = datetime.now(TZ)
        has_creds = bool(self.ctx.creds.username())
        acts = [a for a in self.ctx.db.list_activities() if not a.is_exam]         # provas ficam na agenda
        first_use = not has_creds and not acts
        self.onb_wrap.setVisible(first_use)
        self.main.setVisible(not first_use)
        self.update_btn.setVisible(not first_use)
        last = iso_to_dt(self.ctx.db.get_meta("last_update"))
        self.last.setText(f"Atualizado {relative_time(last, now)}" if last else "")

        pending = [a for a in acts if a.status != STATUS_DONE]
        urgent = [a for a in pending if urgency(a, now) in (URG_SOON, URG_OVERDUE)]
        week = [a for a in pending if a.due_at and 0 <= (a.due_at - now).total_seconds() <= 7 * 86400]
        self.hello.setText(f"{greeting(now)}! 👋" if not first_use else "Boas-vindas ao UniSpace 👋")
        if first_use:
            self.summary.setText("Suas atividades da Sala de Aula Virtual em um quadro simples e organizado.")
        elif not acts:
            self.summary.setText("Nenhuma atividade ainda. Clique em \"Atualizar agora\" para buscar no portal.")
        elif urgent:
            self.summary.setText(f"Atenção: {plural(len(urgent), 'entrega vence', 'entregas vencem')} nas próximas "
                                 f"48 horas. Você tem {plural(len(pending), 'atividade pendente', 'atividades pendentes')}.")
        elif week:
            self.summary.setText(f"{plural(len(week), 'entrega', 'entregas')} nesta semana · "
                                 f"{plural(len(pending), 'atividade pendente', 'atividades pendentes')} no total.")
        elif pending:
            self.summary.setText(f"Nada vence nos próximos dias. {plural(len(pending), 'atividade pendente', 'atividades pendentes')}.")
        else:
            self.summary.setText("Tudo em dia! Nenhuma atividade pendente. 🎉")

        self.t_soon.value.setText(str(len(urgent)))
        self.t_todo.value.setText(str(sum(a.status == STATUS_TODO for a in acts)))
        self.t_doing.value.setText(str(sum(a.status == STATUS_DOING for a in acts)))
        self.t_done.value.setText(str(sum(a.status == STATUS_DONE for a in acts)))

        self._clear(self.upcoming)
        shown = sorted(pending, key=due_key)
        if not shown:
            self.upcoming.addWidget(EmptyState("check_circle", "Tudo em dia!" if acts else "Nada por aqui ainda",
                                               "Nenhuma entrega pendente." if acts else
                                               "Clique em \"Atualizar agora\" para buscar suas atividades."))
            return
        groups: dict[str, list] = {}
        for a in shown:
            groups.setdefault(group_label(a, now), []).append(a)
        count = 0
        for g in GROUP_ORDER:
            if g not in groups or count >= 12:
                continue
            sec = label(g.upper(), "Section")
            sec.setContentsMargins(10, 12, 0, 4)
            if g == "Atrasadas":
                sec.setStyleSheet(f"color:{COLORS['danger']};")
            self.upcoming.addWidget(sec)
            for a in groups[g]:
                if count >= 12:
                    break
                row = UpcomingRow(a, now)
                row.clicked.connect(self.open_activity.emit)
                row.done.connect(self.mark_done.emit)
                self.upcoming.addWidget(row)
                count += 1
        if len(shown) > count:
            more = button(f"Ver mais {len(shown) - count} no quadro", "Link",
                          on_click=lambda: self.go_board.emit("pendentes"))
            self.upcoming.addWidget(more, 0, Qt.AlignLeft)

    @staticmethod
    def _clear(layout) -> None:
        clear_layout(layout)

    def set_updating(self, running: bool) -> None:
        self.update_btn.setEnabled(not running)
        self.update_btn.setText("Atualizando…" if running else "Atualizar agora")
        self.onboarding.go.setEnabled(not running)
        self.onboarding.go.setText("Conectando…" if running else "Conectar e buscar atividades")
