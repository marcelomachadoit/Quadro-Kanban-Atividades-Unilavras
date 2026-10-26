"""Quadro Kanban (arrastar e soltar) e lista, com busca, filtros por disciplina e ordenação."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from PySide6.QtCore import QMimeData, QPoint, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QDrag, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QButtonGroup, QComboBox, QFrame, QHBoxLayout, QHeaderView, QLabel,
                               QLineEdit, QMenu, QPushButton, QScrollArea, QSizePolicy, QStackedWidget, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from app.config import MISSING, TZ
from app.models.activity import SEEN_NOT_FOUND, STATUS_DONE, STATUS_LABELS, STATUS_TODO, STATUSES, Activity
from app.services import rules as R
from app.ui.format import (URG_DONE, URG_OVERDUE, URG_SOON, URGENCY_LABEL, course_color, due_pill_text, plural,
                           points_short, short_course, urgency)
from app.ui.icons import icon
from app.ui.theme import COLORS, STATUS_COLORS, URGENCY_STYLE
from app.ui.widgets import Dot, EmptyState, Pill, button, clear_layout, icon_button, icon_label, label

MIME = "application/x-unikanban-activity"
SORT_DUE, SORT_MANUAL, SORT_NAME = "due", "manual", "name"


def due_key(a: Activity):
    dt = a.due_at
    return (0, dt.timestamp()) if dt else (1, 0.0)     # sem prazo vai depois dos prazos conhecidos


# ---------------------------------------------------------------------- cartão

class Card(QFrame):
    clicked = Signal(int)
    toggle_done = Signal(int)
    context = Signal(int, QPoint)

    def __init__(self, a: Activity, now: datetime, selected: bool = False, parent=None):
        super().__init__(parent)
        self.a = a
        self.setObjectName("KCard")
        self.setProperty("selected", selected)
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        self._press: Optional[QPoint] = None
        self._dragged = False
        u = urgency(a, now)
        color = course_color(a.course)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        stripe = QFrame()
        stripe.setFixedWidth(4)
        stripe.setStyleSheet(f"background:{color};border-top-left-radius:10px;border-bottom-left-radius:10px;")
        outer.addWidget(stripe)
        body = QVBoxLayout()
        body.setContentsMargins(12, 10, 10, 10)
        body.setSpacing(6)
        outer.addLayout(body, 1)

        top = QHBoxLayout()
        top.setSpacing(6)
        course = label(short_course(a.course), "Small")
        course.setStyleSheet(f"color:{color};font-weight:600;")
        course.setToolTip(a.course)
        top.addWidget(course, 1)
        if a.conflicts:
            top.addWidget(self._badge("warning", COLORS["warn"], "O portal mudou um campo que você editou — "
                                                                  "abra para revisar"))
        if a.last_seen_status == SEEN_NOT_FOUND:
            top.addWidget(self._badge("help", COLORS["subtle"], "Não apareceu na última verificação do portal"))
        done = a.status == STATUS_DONE
        self.done_btn = icon_button("check_circle" if done else "circle",
                                    "Reabrir atividade" if done else "Marcar como concluída",
                                    lambda: self.toggle_done.emit(a.id),
                                    COLORS["ok"] if done else COLORS["subtle"], 16)
        top.addWidget(self.done_btn)
        body.addLayout(top)

        title = label(a.name, "CardTitle", wrap=True)
        if done:
            title.setStyleSheet(f"color:{COLORS['muted']};text-decoration: line-through;")
        body.addWidget(title)

        bottom = QHBoxLayout()
        bottom.setSpacing(6)
        fg, bg, ic = URGENCY_STYLE[u]
        bottom.addWidget(Pill(due_pill_text(a, now), fg, bg, ic, URGENCY_LABEL[u]))
        bottom.addStretch(1)
        pts = points_short(a.points)
        if pts:
            p = label(pts, "Small")
            p.setToolTip(f"Vale {a.points}")
            bottom.addWidget(p)
        if a.notes:
            bottom.addWidget(self._badge("edit", COLORS["subtle"], a.notes[:200]))
        body.addLayout(bottom)
        self.setAccessibleName(f"{a.name}, {short_course(a.course)}, {due_pill_text(a, now)}")

    @staticmethod
    def _badge(name: str, color: str, tip: str) -> QLabel:
        b = icon_label(name, color, 13)
        b.setToolTip(tip)
        return b

    def contextMenuEvent(self, e):
        self.context.emit(self.a.id, e.globalPos())

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._press = e.position().toPoint()
            self._dragged = False
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self._press is not None and not self._dragged:
            self.clicked.emit(self.a.id)
        self._press = None
        super().mouseReleaseEvent(e)

    def mouseMoveEvent(self, e):
        if not (e.buttons() & Qt.LeftButton) or self._press is None:
            return
        if (e.position().toPoint() - self._press).manhattanLength() < 8:
            return
        self._dragged = True
        drag = QDrag(self)
        md = QMimeData()
        md.setData(MIME, str(self.a.id).encode())
        drag.setMimeData(md)
        pm = QPixmap(self.size())
        pm.fill(Qt.transparent)
        self.render(pm)
        drag.setPixmap(pm)
        drag.setHotSpot(self._press)
        self.setCursor(Qt.ClosedHandCursor)
        drag.exec(Qt.MoveAction)
        self.setCursor(Qt.PointingHandCursor)
        self._press = None


# ---------------------------------------------------------------------- coluna

class Column(QFrame):
    dropped = Signal(int, str, int)   # id, status, índice
    add_clicked = Signal(str)

    def __init__(self, status: str, parent=None):
        super().__init__(parent)
        self.status = status
        self.setObjectName("Column")
        self.setAcceptDrops(True)
        self.setMinimumWidth(280)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 12, 6, 10)
        lay.setSpacing(8)
        head = QHBoxLayout()
        head.setContentsMargins(4, 0, 4, 0)
        head.addWidget(Dot(STATUS_COLORS[status], 9))
        head.addSpacing(2)
        self.title = label(STATUS_LABELS[status], "ColumnTitle")
        self.count = label("0", "Count")
        head.addWidget(self.title)
        head.addWidget(self.count)
        head.addStretch(1)
        head.addWidget(icon_button("add", f"Nova atividade em \"{STATUS_LABELS[status]}\"",
                                   lambda: self.add_clicked.emit(status)))
        lay.addLayout(head)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.inner = QWidget()
        self.vbox = QVBoxLayout(self.inner)
        self.vbox.setContentsMargins(0, 2, 4, 2)
        self.vbox.setSpacing(8)
        self.vbox.addStretch(1)
        self.scroll.setWidget(self.inner)
        lay.addWidget(self.scroll, 1)
        self._indicator = QFrame(self.inner)
        self._indicator.setFixedHeight(3)
        self._indicator.setStyleSheet(f"background:{COLORS['primary']};border-radius:1px;")
        self._indicator.hide()

    def set_cards(self, cards: list[Card], empty_text: str) -> None:
        while self.vbox.count() > 1:
            w = self.vbox.takeAt(0).widget()
            if w:
                w.hide()
                w.setParent(None)
                w.deleteLater()
        for c in cards:
            self.vbox.insertWidget(self.vbox.count() - 1, c)
        self.count.setText(str(len(cards)))
        if not cards:
            e = label(empty_text, "Muted", wrap=True)
            e.setAlignment(Qt.AlignCenter)
            e.setStyleSheet(f"color:{COLORS['subtle']};padding:22px 10px;border:1.5px dashed {COLORS['border_strong']};"
                            "border-radius:10px;")
            self.vbox.insertWidget(0, e)

    def _cards(self) -> list[Card]:
        return [self.vbox.itemAt(i).widget() for i in range(self.vbox.count())
                if isinstance(self.vbox.itemAt(i).widget(), Card)]

    def _index_at(self, pos_in_col: QPoint) -> int:
        y = self.inner.mapFrom(self, pos_in_col).y()
        for i, c in enumerate(self._cards()):
            if y < c.geometry().center().y():
                return i
        return len(self._cards())

    def _set_target(self, on: bool) -> None:
        self.setProperty("dropTarget", on)
        self.style().unpolish(self)
        self.style().polish(self)

    def dragEnterEvent(self, e):
        if e.mimeData().hasFormat(MIME):
            e.acceptProposedAction()
            self._set_target(True)

    def dragMoveEvent(self, e):
        if e.mimeData().hasFormat(MIME):
            e.acceptProposedAction()
            idx = self._index_at(e.position().toPoint())
            cards = self._cards()
            y = cards[idx].geometry().top() - 5 if idx < len(cards) else (
                cards[-1].geometry().bottom() + 3 if cards else 4)
            self._indicator.setGeometry(0, max(0, y), self.inner.width() - 4, 3)
            self._indicator.show()
            self._indicator.raise_()

    def dragLeaveEvent(self, e):
        self._set_target(False)
        self._indicator.hide()

    def dropEvent(self, e):
        self._set_target(False)
        self._indicator.hide()
        if not e.mimeData().hasFormat(MIME):
            return
        aid = int(bytes(e.mimeData().data(MIME)).decode())
        idx = self._index_at(e.position().toPoint())
        e.acceptProposedAction()
        # adia para depois do término do arraste (o cartão de origem será recriado)
        QTimer.singleShot(0, lambda: self.dropped.emit(aid, self.status, idx))


# ---------------------------------------------------------------------- lista

class _SortItem(QTableWidgetItem):
    def __lt__(self, other):
        a, b = self.data(Qt.UserRole), other.data(Qt.UserRole)
        if a is not None and b is not None:
            return a < b
        return super().__lt__(other)


TABLE_COLS = ["Atividade", "Disciplina", "Prazo", "Pontos", "Status", "Situação"]


# ---------------------------------------------------------------------- página

class BoardPage(QWidget):
    open_activity = Signal(int)
    new_activity = Signal(str)
    notify = Signal(str, object)      # mensagem, ação "Desfazer" (callable) ou None

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.setObjectName("Page")
        self.selected_id: Optional[int] = None
        self._course: Optional[str] = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 22, 28, 18)
        lay.setSpacing(12)

        head = QHBoxLayout()
        head.setSpacing(10)
        tv = QVBoxLayout()
        tv.setSpacing(0)
        tv.addWidget(label("Quadro", "H1"))
        self.subtitle = label("", "Muted")
        tv.addWidget(self.subtitle)
        head.addLayout(tv)
        head.addStretch(1)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Buscar atividade  (Ctrl+F)")
        self.search.setClearButtonEnabled(True)
        self.search.addAction(icon("search", COLORS["subtle"]), QLineEdit.LeadingPosition)
        self.search.setFixedWidth(280)
        self.search.textChanged.connect(self._debounced)
        head.addWidget(self.search)
        seg = QHBoxLayout()
        seg.setSpacing(0)
        self.view_group = QButtonGroup(self)
        for i, (ic, tip) in enumerate((("board", "Ver como quadro"), ("list", "Ver como lista"))):
            b = QPushButton()
            b.setObjectName("Seg")
            b.setIcon(icon(ic, COLORS["text_2"]))
            b.setToolTip(tip)
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet("QPushButton#Seg { border-top-left-radius:8px; border-bottom-left-radius:8px; }" if i == 0
                            else "QPushButton#Seg { border-top-right-radius:8px; border-bottom-right-radius:8px; }")
            self.view_group.addButton(b, i)
            seg.addWidget(b)
        self.view_group.button(0).setChecked(True)
        self.view_group.idClicked.connect(self._set_view)
        head.addLayout(seg)
        head.addWidget(button("Nova atividade", "Primary", "add", tip="Criar atividade (Ctrl+N)",
                              on_click=lambda: self.new_activity.emit(STATUS_TODO)))
        lay.addLayout(head)

        # filtros: disciplinas (chips) + alternâncias rápidas
        frow = QHBoxLayout()
        frow.setSpacing(6)
        chips_holder = QWidget()
        self.chips_box = QHBoxLayout(chips_holder)
        self.chips_box.setContentsMargins(0, 0, 0, 0)
        self.chips_box.setSpacing(6)
        self.chips_scroll = QScrollArea()
        self.chips_scroll.setWidget(chips_holder)
        self.chips_scroll.setWidgetResizable(True)
        self.chips_scroll.setFixedHeight(44)
        self.chips_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        frow.addWidget(self.chips_scroll, 1)
        self.urgent_only = self._chip("Só urgentes", "Prazos nas próximas 48 horas ou encerrados")
        self.hide_done = self._chip("Ocultar concluídas")
        self.urgent_only.toggled.connect(self.refresh)
        self.hide_done.toggled.connect(self.refresh)
        frow.addWidget(self.urgent_only)
        frow.addWidget(self.hide_done)
        self.sort = QComboBox()
        self.sort.addItem("Ordenar por prazo", SORT_DUE)
        self.sort.addItem("Ordem manual", SORT_MANUAL)
        self.sort.addItem("Ordenar por nome", SORT_NAME)
        self.sort.setToolTip("Ordem dos cartões em cada coluna")
        self.sort.currentIndexChanged.connect(self.refresh)
        frow.addWidget(self.sort)
        self.trash_btn = button("Excluídas", "Ghost", "delete", tip="Ver e restaurar atividades excluídas",
                                on_click=self.open_trash)
        frow.addWidget(self.trash_btn)
        lay.addLayout(frow)
        self.course_group = QButtonGroup(self)
        self.course_group.setExclusive(True)

        self.stack = QStackedWidget()
        kan = QWidget()
        kl = QHBoxLayout(kan)
        kl.setContentsMargins(0, 0, 0, 0)
        kl.setSpacing(12)
        self.columns: dict[str, Column] = {}
        for s in STATUSES:
            col = Column(s)
            col.dropped.connect(self._on_drop)
            col.add_clicked.connect(self.new_activity.emit)
            self.columns[s] = col
            kl.addWidget(col, 1)
        self.stack.addWidget(kan)

        self.table = QTableWidget(0, len(TABLE_COLS))
        self.table.setHorizontalHeaderLabels(TABLE_COLS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.setSortingEnabled(True)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(40)
        self.table.setWordWrap(False)
        self.table.setFocusPolicy(Qt.NoFocus)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        hh.setSortIndicator(-1, Qt.AscendingOrder)
        self.table.cellClicked.connect(lambda r, c: self.open_activity.emit(self.table.item(r, 0).data(Qt.UserRole + 1)))
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(
            lambda pos: self._menu(self.table.item(self.table.indexAt(pos).row(), 0).data(Qt.UserRole + 1),
                                   self.table.viewport().mapToGlobal(pos)) if self.table.indexAt(pos).isValid() else None)
        self.list_empty = EmptyState("search", "Nada encontrado", "Ajuste a busca ou os filtros.")
        lw = QWidget()
        lv = QVBoxLayout(lw)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.addWidget(self.table)
        lv.addWidget(self.list_empty)
        self.stack.addWidget(lw)
        lay.addWidget(self.stack, 1)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(180)
        self._timer.timeout.connect(self.refresh)
        ctx.data_changed.connect(self.refresh)
        self.refresh()

    # ------------------------------------------------------------------ filtros
    def _chip(self, text: str, tip: str = "") -> QPushButton:
        b = QPushButton(text)
        b.setObjectName("Chip")
        b.setCheckable(True)
        b.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        b.setCursor(Qt.PointingHandCursor)
        if tip:
            b.setToolTip(tip)
        return b

    def _refresh_chips(self, acts: list[Activity]) -> None:
        courses = sorted({a.course for a in acts if a.course != MISSING}, key=lambda c: short_course(c).lower())
        if self._course not in courses:
            self._course = None
        for b in self.course_group.buttons():
            self.course_group.removeButton(b)
        clear_layout(self.chips_box)
        for name in [None] + courses:
            b = self._chip("Todas" if name is None else short_course(name), name or "Todas as disciplinas")
            if name:
                b.setIcon(icon("dot", course_color(name), 14))
            b.setChecked(name == self._course)
            b.clicked.connect(lambda _=False, n=name: self._select_course(n))
            self.course_group.addButton(b)
            self.chips_box.addWidget(b)
        self.chips_box.addStretch(1)

    def _select_course(self, name: Optional[str]) -> None:
        self._course = name
        self.refresh()

    def set_quick_filter(self, urgent: bool = False, hide_done: bool = False) -> None:
        for chip, val in ((self.urgent_only, urgent), (self.hide_done, hide_done)):
            chip.blockSignals(True)
            chip.setChecked(val)
            chip.blockSignals(False)
        self._course = None
        self.search.clear()
        self.refresh()

    def focus_search(self) -> None:
        self.search.setFocus()
        self.search.selectAll()

    def _debounced(self, *_):
        self._timer.start()

    def _set_view(self, i: int) -> None:
        self.stack.setCurrentIndex(i)

    def _filtered(self, acts: list[Activity], now: datetime) -> list[Activity]:
        q = R.normalize(self.search.text())
        out = []
        for a in acts:
            if q and q not in R.normalize(a.name) and q not in R.normalize(a.course):
                continue
            if self._course and a.course != self._course:
                continue
            if self.hide_done.isChecked() and a.status == STATUS_DONE:
                continue
            if self.urgent_only.isChecked() and urgency(a, now) not in (URG_SOON, URG_OVERDUE):
                continue
            out.append(a)
        mode = self.sort.currentData() or SORT_DUE
        if mode == SORT_DUE:
            out.sort(key=lambda a: (due_key(a), R.normalize(a.name)))
        elif mode == SORT_NAME:
            out.sort(key=lambda a: R.normalize(a.name))
        else:
            out.sort(key=lambda a: (a.position, a.id))
        return out

    # ------------------------------------------------------------------ renderização
    def refresh(self, *_):
        all_acts = self.ctx.db.list_activities()
        now = datetime.now(TZ)
        self._refresh_chips(all_acts)
        acts = self._filtered(all_acts, now)
        pending = sum(a.status != STATUS_DONE for a in all_acts)
        filt = len(acts) != len(all_acts)
        self.subtitle.setText((f"Mostrando {len(acts)} de {len(all_acts)} · " if filt else "")
                              + plural(pending, "atividade pendente", "atividades pendentes"))
        trashed = len(self.ctx.db.list_activities(only_deleted=True))
        self.trash_btn.setText(f"Excluídas ({trashed})" if trashed else "Excluídas")
        by = {s: [] for s in STATUSES}
        for a in acts:
            by.setdefault(a.status, []).append(a)
        empty_texts = {
            "todo": "Nada por aqui. Arraste um cartão ou use + para criar.",
            "doing": "Arraste para cá o que você começou a fazer.",
            "done": "Arraste para cá ou clique no ○ do cartão para concluir.",
        }
        if filt:
            empty_texts = {s: "Nenhuma atividade com estes filtros." for s in STATUSES}
        for s, col in self.columns.items():
            cards = []
            for a in by[s]:
                c = Card(a, now, a.id == self.selected_id)
                c.clicked.connect(self.open_activity.emit)
                c.toggle_done.connect(self.toggle_done)
                c.context.connect(self._menu)
                cards.append(c)
            col.set_cards(cards, empty_texts[s])
        self._fill_table(acts, now)

    def _fill_table(self, acts: list[Activity], now: datetime) -> None:
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(acts))
        for r, a in enumerate(acts):
            u = urgency(a, now)
            situ = "Divergência" if a.conflicts else (
                "Não encontrada" if a.last_seen_status == SEEN_NOT_FOUND else ("Criada por você" if a.origin == "manual"
                                                                               else "OK"))
            vals = [
                (a.name, R.normalize(a.name)),
                (short_course(a.course), R.normalize(a.course)),
                (due_pill_text(a, now), due_key(a)),
                (points_short(a.points) or "—", None),
                (STATUS_LABELS.get(a.status, a.status), STATUSES.index(a.status)),
                (situ, None),
            ]
            for c, (text, key) in enumerate(vals):
                it = _SortItem(text)
                if key is not None:
                    it.setData(Qt.UserRole, key)
                if c == 0:
                    it.setData(Qt.UserRole + 1, a.id)
                    it.setToolTip(a.name)
                if c == 1:
                    it.setIcon(icon("dot", course_color(a.course), 14))
                    it.setToolTip(a.course)
                if c == 2:
                    it.setIcon(icon(URGENCY_STYLE[u][2], URGENCY_STYLE[u][0], 14))
                    it.setToolTip(URGENCY_LABEL[u])
                if c == 4:
                    it.setIcon(icon("dot", STATUS_COLORS[a.status], 14))
                self.table.setItem(r, c, it)
        self.table.setSortingEnabled(True)
        self.table.setVisible(bool(acts))
        self.list_empty.setVisible(not acts)

    # ------------------------------------------------------------------ ações
    def _menu(self, aid: int, global_pos: QPoint) -> None:
        a = self.ctx.db.get(aid)
        if not a:
            return
        m = QMenu(self)
        m.addAction(icon("info"), "Abrir detalhes", lambda: self.open_activity.emit(aid))
        if a.url:
            m.addAction(icon("open"), "Abrir no portal", lambda: QDesktopServices.openUrl(QUrl(a.url)))
        m.addSeparator()
        for s in STATUSES:
            if s != a.status:
                m.addAction(icon("dot", STATUS_COLORS[s], 14), f"Mover para {STATUS_LABELS[s]}",
                            lambda s=s: self.move_to(aid, s))
        m.addSeparator()
        m.addAction(icon("delete", COLORS["danger"]), "Excluir…", lambda: self.delete(aid))
        m.exec(global_pos)

    def toggle_done(self, aid: int) -> None:
        a = self.ctx.db.get(aid)
        if not a:
            return
        prev = a.status
        new = STATUS_TODO if prev == STATUS_DONE else STATUS_DONE
        self.move_to(aid, new, notify=False)
        self.notify.emit("Atividade concluída 🎉" if new == STATUS_DONE else "Atividade reaberta",
                         lambda: self.move_to(aid, prev, notify=False))

    def move_to(self, aid: int, status: str, notify: bool = True) -> None:
        self.ctx.db.update_fields(aid, status=status, position=self.ctx.db.next_position(status))
        self.ctx.data_changed.emit()
        if notify:
            self.notify.emit(f"Movida para {STATUS_LABELS[status]}", None)

    def delete(self, aid: int) -> None:
        from PySide6.QtWidgets import QMessageBox
        a = self.ctx.db.get(aid)
        if not a:
            return
        hint = ("Se ela ainda existir no portal, voltará ao quadro na próxima atualização."
                if a.origin == "portal" else "Você poderá restaurá-la em \"Excluídas\".")
        if QMessageBox.question(self, "Excluir atividade", f"Excluir \"{a.name}\" do quadro?\n\n{hint}") \
                == QMessageBox.Yes:
            self.ctx.db.soft_delete(aid)
            self.ctx.data_changed.emit()
            self.notify.emit("Atividade excluída", lambda: (self.ctx.db.restore(aid), self.ctx.data_changed.emit()))

    def _on_drop(self, aid: int, status: str, idx: int) -> None:
        a = self.ctx.db.get(aid)
        col = self.columns[status]
        ids = [c.a.id for c in col._cards() if c.a.id != aid]
        idx = min(idx, len(ids))
        ids.insert(idx, aid)
        self.ctx.db.set_positions(ids, status)
        self.ctx.data_changed.emit()
        if a and a.status != status:
            prev = a.status
            self.notify.emit(f"Movida para {STATUS_LABELS[status]}", lambda: self.move_to(aid, prev, notify=False))

    def open_trash(self) -> None:
        from app.ui.dialogs import TrashDialog
        TrashDialog(self.ctx, self).exec()
        self.ctx.data_changed.emit()
