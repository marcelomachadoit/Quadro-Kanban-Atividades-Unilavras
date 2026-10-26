"""Painel lateral da atividade: ver, editar, criar, resolver divergências, abrir no portal e excluir."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from PySide6.QtCore import QDateTime, Qt, QTimeZone, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QDateTimeEdit, QFrame, QHBoxLayout, QLineEdit,
                               QMessageBox, QPlainTextEdit, QPushButton, QScrollArea, QVBoxLayout, QWidget)

from app.config import MISSING, TZ
from app.models.activity import (FIELD_LABELS, SEEN_NOT_FOUND, STATUS_LABELS, STATUS_TODO, STATUSES, Activity,
                                 iso_to_dt)
from app.services.sync import apply_user_edit, resolve_conflict
from app.ui.format import course_color, due_pill_text, friendly_due, relative_time, short_course, urgency
from app.ui.theme import COLORS, URGENCY_STYLE
from app.ui.widgets import Divider, Dot, Pill, button, clear_layout, icon_button, label


def _qdt(dt: datetime) -> QDateTime:
    return QDateTime.fromSecsSinceEpoch(int(dt.timestamp()), QTimeZone(b"America/Sao_Paulo"))


def _pydt(q: QDateTime) -> datetime:
    return datetime.fromtimestamp(q.toSecsSinceEpoch(), TZ).replace(second=0)


def _fmt_value(field: str, value) -> str:
    if value is None:
        return MISSING
    if field == "due_at":
        dt = iso_to_dt(value) if value else None
        return friendly_due(dt) if dt else "sem prazo"
    return value or MISSING


class ActivityPanel(QFrame):
    changed = Signal(str)     # mensagem para o toast
    closed = Signal()

    WIDTH = 420

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.setObjectName("Drawer")
        self.setFixedWidth(self.WIDTH)
        self.a: Optional[Activity] = None
        self._loading = False
        self._dirty = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        head = QHBoxLayout()
        head.setContentsMargins(22, 16, 14, 8)
        self.course_dot = Dot(COLORS["subtle"], 10)
        self.course_lbl = label("", "Small")
        head.addWidget(self.course_dot)
        head.addSpacing(4)
        head.addWidget(self.course_lbl, 1)
        head.addWidget(icon_button("close", "Fechar (Esc)", self.request_close))
        outer.addLayout(head)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        body = QWidget()
        self.v = QVBoxLayout(body)
        self.v.setContentsMargins(22, 0, 22, 16)
        self.v.setSpacing(8)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

        self.name = QPlainTextEdit()
        self.name.setPlaceholderText("Nome da atividade")
        self.name.setFixedHeight(64)
        self.name.setStyleSheet("QPlainTextEdit { font-size: 13pt; font-weight: 700; border: 1px solid transparent; "
                                "padding: 2px; } QPlainTextEdit:hover { border-color: #E2E8F0; } "
                                "QPlainTextEdit:focus { border-color: #2563EB; }")
        self.name.setTabChangesFocus(True)
        self.v.addWidget(self.name)
        self.pills = QHBoxLayout()
        self.pills.setSpacing(6)
        self.v.addLayout(self.pills)
        self.v.addSpacing(6)

        # status como controle segmentado
        self.v.addWidget(label("Status", "FieldLabel"))
        seg = QHBoxLayout()
        seg.setSpacing(0)
        self.status_group = QButtonGroup(self)
        self.status_btns = {}
        for i, s in enumerate(STATUSES):
            b = QPushButton(STATUS_LABELS[s])
            b.setObjectName("Seg")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            radius = "border-top-left-radius:8px;border-bottom-left-radius:8px;" if i == 0 else (
                "border-top-right-radius:8px;border-bottom-right-radius:8px;" if i == len(STATUSES) - 1 else "")
            b.setStyleSheet(f"QPushButton#Seg {{ {radius} }}")
            self.status_group.addButton(b, i)
            self.status_btns[s] = b
            seg.addWidget(b, 1)
        self.status_group.idClicked.connect(lambda *_: self._mark_dirty())
        self.v.addLayout(seg)

        self.v.addWidget(label("Disciplina", "FieldLabel"))
        self.course = QComboBox()
        self.course.setEditable(True)
        self.course.lineEdit().setPlaceholderText("Escolha ou digite")
        self.v.addWidget(self.course)

        self.v.addWidget(label("Prazo de entrega", "FieldLabel"))
        due_row = QHBoxLayout()
        self.due = QDateTimeEdit()
        self.due.setCalendarPopup(True)
        self.due.setDisplayFormat("dd/MM/yyyy  HH:mm")
        self.no_due = QCheckBox("Sem prazo")
        due_row.addWidget(self.due, 1)
        due_row.addWidget(self.no_due)
        self.v.addLayout(due_row)
        self.due_hint = label("", "Small")
        self.v.addWidget(self.due_hint)

        self.v.addWidget(label("Pontuação", "FieldLabel"))
        self.points = QLineEdit()
        self.points.setPlaceholderText("ex.: 10 pontos")
        self.v.addWidget(self.points)

        self.overrides = QVBoxLayout()
        self.overrides.setSpacing(4)
        self.v.addLayout(self.overrides)

        self.v.addWidget(label("Minhas observações", "FieldLabel"))
        self.notes = QPlainTextEdit()
        self.notes.setPlaceholderText("Anotações pessoais (só ficam neste computador)")
        self.notes.setMinimumHeight(96)
        self.v.addWidget(self.notes)

        self.conflicts = QVBoxLayout()
        self.conflicts.setSpacing(8)
        self.v.addLayout(self.conflicts)

        self.info_box = QVBoxLayout()
        self.info_box.setSpacing(4)
        self.v.addSpacing(6)
        self.v.addWidget(Divider())
        self.v.addSpacing(4)
        self.v.addLayout(self.info_box)
        self.v.addStretch(1)

        # rodapé de ações
        foot = QFrame()
        foot.setStyleSheet(f"QFrame {{ border-top: 1px solid {COLORS['border']}; background: white; }}")
        fl = QHBoxLayout(foot)
        fl.setContentsMargins(18, 12, 18, 12)
        self.open_btn = button("Abrir no portal", "", "open", tip="Abrir a página da atividade no navegador",
                               on_click=self._open_portal)
        self.delete_btn = button("", "Danger", "delete", COLORS["danger"], tip="Excluir do quadro",
                                 on_click=self._delete)
        self.discard_btn = button("Descartar", "Ghost", on_click=self._discard)
        self.save_btn = button("Salvar", "Primary", "save", on_click=self.save)
        fl.addWidget(self.delete_btn)
        fl.addWidget(self.open_btn)
        fl.addStretch(1)
        fl.addWidget(self.discard_btn)
        fl.addWidget(self.save_btn)
        outer.addWidget(foot)

        for w in (self.course.lineEdit(), self.points):
            w.textEdited.connect(lambda *_: self._mark_dirty())
        self.course.currentIndexChanged.connect(lambda *_: self._mark_dirty())
        self.name.textChanged.connect(self._mark_dirty)
        self.notes.textChanged.connect(self._mark_dirty)
        self.due.dateTimeChanged.connect(self._due_changed)
        self.no_due.toggled.connect(self._due_toggled)
        self._due_touched = False
        self._orig_due: Optional[datetime] = None
        self._set_dirty(False)
        self.hide()

    # ------------------------------------------------------------------ abrir
    def open_activity(self, aid: int) -> bool:
        if not self.confirm_discard():
            return False
        a = self.ctx.db.get(aid)
        if a is None:
            return False
        self.a = a
        self._fill(a)
        self.show()
        return True

    def open_new(self, status: str = STATUS_TODO) -> bool:
        if not self.confirm_discard():
            return False
        self.a = None
        self._fill(None, status)
        self.show()
        self.name.setFocus()
        return True

    def _fill(self, a: Optional[Activity], status: str = STATUS_TODO) -> None:
        self._loading = True
        courses = sorted({x.course for x in self.ctx.db.list_activities() if x.course != MISSING},
                         key=lambda s: short_course(s).lower())
        self.course.clear()
        self.course.addItems(courses)
        name = a.name if a and a.name != MISSING else ""
        self.name.setPlainText(name)
        self.course.setCurrentText(a.course if a and a.course != MISSING else "")
        self._orig_due = a.due_at if a else None
        self._due_touched = False
        self.no_due.setChecked(a is not None and self._orig_due is None)
        self.due.setDateTime(_qdt(self._orig_due or datetime.now(TZ).replace(hour=23, minute=59, second=0)))
        self.due.setEnabled(not self.no_due.isChecked())
        self.points.setText(a.points if a and a.points != MISSING else "")
        self.notes.setPlainText(a.notes if a else "")
        self.status_btns[a.status if a else status].setChecked(True)

        color = course_color(a.course) if a else COLORS["subtle"]
        self.course_dot.setStyleSheet(f"background:{color};border-radius:5px;")
        self.course_lbl.setText(short_course(a.course) if a else "Nova atividade")
        self.course_lbl.setToolTip(a.course if a else "")

        self._clear(self.pills)
        self._clear(self.overrides)
        self._clear(self.conflicts)
        self._clear(self.info_box)
        if a:
            u = urgency(a)
            fg, bg, ic = URGENCY_STYLE[u]
            self.pills.addWidget(Pill(due_pill_text(a), fg, bg, ic))
            if a.last_seen_status == SEEN_NOT_FOUND:
                self.pills.addWidget(Pill("Não encontrada no portal", COLORS["neutral_text"], COLORS["neutral_bg"],
                                          "help", "Não apareceu na última verificação do portal"))
            if a.due_ambiguous:
                self.pills.addWidget(Pill("Conferir prazo", COLORS["warn_text"], COLORS["warn_bg"], "warning",
                                          "O prazo não pôde ser lido com segurança"))
            self.pills.addStretch(1)
            for f in ("name", "course", "due_at", "points"):
                if a.origin == "portal" and a.is_overridden(f) and not any(c.get("field") == f for c in a.conflicts):
                    self.overrides.addWidget(self._override_row(f))
            for c in a.conflicts:
                self.conflicts.addWidget(self._conflict_box(c))
            self._info_rows(a)
        self.open_btn.setVisible(bool(a and a.url))
        self.delete_btn.setVisible(a is not None)
        self._update_due_hint()
        self._loading = False
        self._set_dirty(a is None)

    def _info_rows(self, a: Activity) -> None:
        rows = [("Origem", "Sala de Aula Virtual" if a.origin == "portal" else "Criada por você")]
        if a.origin == "portal":
            rows.append(("Verificada", relative_time(iso_to_dt(a.last_checked))))
        rows.append(("Adicionada", relative_time(iso_to_dt(a.first_seen))))
        for k, val in rows:
            r = QHBoxLayout()
            r.addWidget(label(k, "Small"))
            r.addStretch(1)
            r.addWidget(label(val, "Small"))
            self.info_box.addLayout(r)

    def _override_row(self, f: str) -> QWidget:
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(label(f"{FIELD_LABELS[f]} editado por você · no portal: "
                          f"{_fmt_value(f, getattr(self.a, 'portal_' + f))}", "Small", wrap=True), 1)
        b = button("Usar do portal", "Link", on_click=lambda: self._use_portal(f))
        h.addWidget(b)
        return w

    def _conflict_box(self, c: dict) -> QFrame:
        f = c.get("field")
        box = QFrame()
        box.setStyleSheet(f"QFrame {{ background:{COLORS['warn_bg']}; border:1px solid #FDE68A; border-radius:10px; }}"
                          f"QLabel {{ color:{COLORS['warn_text']}; border:none; background:transparent; }}")
        v = QVBoxLayout(box)
        v.setContentsMargins(12, 10, 12, 10)
        v.addWidget(label(f"O portal mudou {FIELD_LABELS.get(f, f).lower()}", "H3"))
        v.addWidget(label(f"Você tinha alterado para <b>{_fmt_value(f, c.get('user_value'))}</b>. "
                          f"O portal agora informa <b>{_fmt_value(f, c.get('portal_new'))}</b>.", wrap=True))
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(button("Manter o meu", on_click=lambda: self._resolve(f, False)))
        row.addWidget(button("Usar do portal", "Primary", on_click=lambda: self._resolve(f, True)))
        v.addLayout(row)
        return box

    @staticmethod
    def _clear(layout) -> None:
        clear_layout(layout)

    # ------------------------------------------------------------------ estado de edição
    def _mark_dirty(self) -> None:
        if not self._loading:
            self._set_dirty(True)

    def _set_dirty(self, d: bool) -> None:
        self._dirty = d
        self.save_btn.setEnabled(d)
        self.discard_btn.setVisible(d and self.a is not None)
        self.save_btn.setText("Criar atividade" if self.a is None else "Salvar")

    def _due_changed(self, *_):
        if not self._loading:
            self._due_touched = True
            self._mark_dirty()
        self._update_due_hint()

    def _due_toggled(self, checked: bool) -> None:
        self.due.setEnabled(not checked)
        self._mark_dirty()
        self._update_due_hint()

    def _update_due_hint(self) -> None:
        dt = self._due_value()
        self.due_hint.setText(friendly_due(dt) if dt else "Sem prazo definido")

    def _due_value(self) -> Optional[datetime]:
        if self.no_due.isChecked():
            return None
        if not self._due_touched and self._orig_due is not None:
            return self._orig_due              # preserva horário original (ex.: 23:59:59)
        return _pydt(self.due.dateTime())

    def confirm_discard(self) -> bool:
        if not (self.isVisible() and self._dirty and (self.a is not None or self.name.toPlainText().strip())):
            return True
        r = QMessageBox.question(self, "Alterações não salvas", "Salvar as alterações desta atividade?",
                                 QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Save)
        if r == QMessageBox.Save:
            return self.save()
        return r == QMessageBox.Discard

    def request_close(self) -> None:
        if self.confirm_discard():
            self._dirty = False
            self.hide()
            self.closed.emit()

    # ------------------------------------------------------------------ ações
    def save(self) -> bool:
        name = " ".join(self.name.toPlainText().split())
        if not name:
            QMessageBox.warning(self, "Falta o nome", "Dê um nome para a atividade.")
            self.name.setFocus()
            return False
        status = STATUSES[self.status_group.checkedId()]
        try:
            if self.a is None:
                aid = self.ctx.db.create_manual(name, self.course.currentText().strip(), self._due_value(),
                                                self.points.text().strip(), status, self.notes.toPlainText())
                msg = "Atividade criada"
            else:
                apply_user_edit(self.ctx.db, self.a.id, name, self.course.currentText(), self._due_value(),
                                self.points.text(), status, self.notes.toPlainText())
                aid = self.a.id
                msg = "Alterações salvas"
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "Não foi possível salvar", str(e))
            return False
        self.a = self.ctx.db.get(aid)
        self._fill(self.a)
        self.ctx.data_changed.emit()
        self.changed.emit(msg)
        return True

    def _discard(self) -> None:
        self._fill(self.a)

    def _use_portal(self, f: str) -> None:
        self.ctx.db.update_fields(self.a.id, **{f"user_{f}": None})
        self._after_external_change("Valor do portal restaurado")

    def _resolve(self, f: str, accept_portal: bool) -> None:
        resolve_conflict(self.ctx.db, self.a.id, f, accept_portal)
        self._after_external_change("Divergência resolvida")

    def _after_external_change(self, msg: str) -> None:
        self.a = self.ctx.db.get(self.a.id)
        self._fill(self.a)
        self.ctx.data_changed.emit()
        self.changed.emit(msg)

    def _open_portal(self) -> None:
        if self.a and self.a.url:
            QDesktopServices.openUrl(QUrl(self.a.url))

    def _delete(self) -> None:
        if not self.a:
            return
        hint = ("Se ela ainda existir no portal, voltará ao quadro na próxima atualização."
                if self.a.origin == "portal" else "Você poderá restaurá-la em \"Excluídas\".")
        if QMessageBox.question(self, "Excluir atividade", f"Excluir \"{self.a.name}\" do quadro?\n\n{hint}") \
                != QMessageBox.Yes:
            return
        aid = self.a.id
        self.ctx.db.soft_delete(aid)
        self._dirty = False
        self.hide()
        self.closed.emit()
        self.ctx.data_changed.emit()
        self.changed.emit("Atividade excluída")
