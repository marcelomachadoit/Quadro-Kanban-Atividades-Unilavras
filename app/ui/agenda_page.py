"""Aba Agenda: compromissos pessoais (aulas, provas, estudos…) junto com entregas, encontros virtuais e eventos."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Callable, Optional

from PySide6.QtCore import QDate, Qt, QTime, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QDateEdit, QDialog, QFormLayout, QFrame,
                               QHBoxLayout, QLineEdit, QMessageBox, QPlainTextEdit, QScrollArea, QTimeEdit,
                               QVBoxLayout, QWidget)

from app.config import TZ
from app.models.activity import STATUS_DONE
from app.models.agenda import CATEGORIES, DEFAULT_CATEGORY, AgendaItem
from app.models.meetings import CourseInfo, avin_days, completed_ids, occurrences
from app.ui.calendar_page import MONTHS, WEEKDAY_FULL
from app.ui.events_page import agenda_key
from app.ui.format import category_color, course_color, plural, short_course
from app.ui.theme import COLORS
from app.ui.widgets import EmptyState, Pill, button, clear_layout, icon_button, label

META_SHOW_LINKED = "agenda_show_linked"
LINKED_DAYS = 60                   # quanto à frente mostrar entregas, encontros e eventos
FILTERS = (("upcoming", "Próximos"), ("done", "Concluídos"), ("all", "Todos"))
AVIN_SUBTITLE = "Avaliação integrada do módulo (data do Planograma) · "


def day_title(d: date, today: date) -> str:
    rel = {today: "Hoje", today + timedelta(days=1): "Amanhã", today - timedelta(days=1): "Ontem"}.get(d)
    full = f"{WEEKDAY_FULL[d.weekday()]}, {d.day} de {MONTHS[d.month - 1]}" + (f" de {d.year}" if d.year != today.year else "")
    return f"{rel} · {full}" if rel else full.capitalize()


@dataclass
class Entry:
    """Linha da agenda: um compromisso próprio ou um item ligado (entrega, encontro, evento) somente leitura."""
    day: date
    time: Optional[str]
    title: str
    subtitle: str
    kind: str                        # "own" | "activity" | "exam" | "meeting" | "event"
    color: str
    done: bool = False
    item: Optional[AgendaItem] = None
    aid: Optional[int] = None
    url: Optional[str] = None

    def sort_key(self) -> tuple:
        return self.day, self.time or "", 0 if self.kind == "own" else 1, self.title.lower()


KIND_LABEL = {"activity": "Entrega", "exam": "Prova", "meeting": "Encontro virtual", "event": "Evento"}


# ---------------------------------------------------------------------- diálogo de compromisso

class AgendaDialog(QDialog):
    def __init__(self, item: Optional[AgendaItem] = None, day: Optional[date] = None, parent=None):
        super().__init__(parent)
        self.item = item
        self.setWindowTitle("Editar compromisso" if item else "Novo compromisso")
        self.setMinimumWidth(460)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 20, 22, 16)
        lay.setSpacing(10)
        lay.addWidget(label(self.windowTitle(), "H2"))
        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.title = QLineEdit(item.title if item else "")
        self.title.setPlaceholderText("Ex.: Prova de Cálculo, estudar para o AVIN")
        form.addRow(label("Título", "FieldLabel"), self.title)
        d = item.date if item else (day or datetime.now(TZ).date())
        self.date = QDateEdit(QDate(d.year, d.month, d.day))
        self.date.setCalendarPopup(True)
        self.date.setDisplayFormat("dd/MM/yyyy")
        form.addRow(label("Data", "FieldLabel"), self.date)
        self.all_day = QCheckBox("Dia inteiro (sem horário)")
        self.all_day.setChecked(bool(item and item.all_day))
        form.addRow(label("", "FieldLabel"), self.all_day)
        times = QHBoxLayout()
        self.start = QTimeEdit(self._qtime(item.start_time if item else None, QTime(8, 0)))
        self.end = QTimeEdit(self._qtime(item.end_time if item else None, self.start.time().addSecs(3600)))
        self.has_end = QCheckBox("Término")
        self.has_end.setChecked(bool(item and item.end_time) or not item)
        for t in (self.start, self.end):
            t.setDisplayFormat("HH:mm")
        times.addWidget(self.start)
        times.addSpacing(10)
        times.addWidget(self.has_end)
        times.addWidget(self.end)
        times.addStretch(1)
        self.times_lbl = label("Horário", "FieldLabel")
        form.addRow(self.times_lbl, times)
        self.category = QComboBox()
        self.category.addItems(CATEGORIES)
        self.category.setCurrentText(item.category if item else DEFAULT_CATEGORY)
        form.addRow(label("Categoria", "FieldLabel"), self.category)
        self.location = QLineEdit(item.location if item else "")
        self.location.setPlaceholderText("Sala, prédio, link da aula… (opcional)")
        form.addRow(label("Local", "FieldLabel"), self.location)
        self.notes = QPlainTextEdit(item.notes if item else "")
        self.notes.setPlaceholderText("Anotações (opcional)")
        self.notes.setFixedHeight(90)
        form.addRow(label("Notas", "FieldLabel"), self.notes)
        lay.addLayout(form)
        self.error = label("", wrap=True)
        self.error.setStyleSheet(f"color:{COLORS['danger']};")
        self.error.hide()
        lay.addWidget(self.error)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(button("Cancelar", "Ghost", on_click=self.reject))
        row.addWidget(button("Salvar", "Primary", "save", on_click=self._save))
        lay.addLayout(row)
        self.all_day.toggled.connect(self._sync)
        self.has_end.toggled.connect(self._sync)
        self.title.returnPressed.connect(self._save)
        self._sync()
        self.result_item: Optional[AgendaItem] = None

    @staticmethod
    def _qtime(hhmm: Optional[str], default: QTime) -> QTime:
        t = QTime.fromString(hhmm or "", "HH:mm")
        return t if t.isValid() else default

    def _sync(self) -> None:
        timed = not self.all_day.isChecked()
        for w in (self.start, self.has_end, self.times_lbl):
            w.setEnabled(timed)
        self.end.setEnabled(timed and self.has_end.isChecked())

    def _save(self) -> None:
        title = self.title.text().strip()
        if not title:
            self.error.setText("Dê um título ao compromisso.")
            self.error.show()
            return
        timed = not self.all_day.isChecked()
        start = self.start.time().toString("HH:mm") if timed else None
        end = self.end.time().toString("HH:mm") if timed and self.has_end.isChecked() else None
        if start and end and end <= start:
            self.error.setText("O término precisa ser depois do início.")
            self.error.show()
            return
        base = self.item or AgendaItem(title="", day="")
        self.result_item = AgendaItem(id=base.id, title=title, day=self.date.date().toString("yyyy-MM-dd"),
                                      start_time=start, end_time=end, location=self.location.text().strip(),
                                      category=self.category.currentText(), notes=self.notes.toPlainText().strip(),
                                      done=base.done, source_key=base.source_key)
        self.accept()


# ---------------------------------------------------------------------- linha da agenda

class EntryRow(QFrame):
    def __init__(self, e: Entry, on_open: Callable, on_toggle: Optional[Callable] = None,
                 on_edit: Optional[Callable] = None, on_delete: Optional[Callable] = None):
        super().__init__()
        self.setObjectName("Row")
        self.entry = e
        self._on_open = on_open
        self.setCursor(Qt.PointingHandCursor)
        h = QHBoxLayout(self)
        h.setContentsMargins(10, 8, 6, 8)
        h.setSpacing(10)
        t = label(e.time or "—", "H3")
        t.setFixedWidth(46)
        h.addWidget(t, 0, Qt.AlignTop)
        bar = QFrame()
        bar.setFixedWidth(4)
        bar.setStyleSheet(f"background:{e.color}; border-radius:2px;")
        h.addWidget(bar)
        tv = QVBoxLayout()
        tv.setSpacing(1)
        title = label(e.title, "H3", wrap=True)
        if e.done:
            title.setStyleSheet(f"color:{COLORS['subtle']}; text-decoration: line-through;")
        tv.addWidget(title)
        if e.subtitle:
            tv.addWidget(label(e.subtitle, "Small", wrap=True))
        h.addLayout(tv, 1)
        if e.kind == "own":
            h.addWidget(Pill(e.item.category, COLORS["neutral_text"], COLORS["neutral_bg"]), 0, Qt.AlignVCenter)
            h.addWidget(icon_button("check_circle" if e.done else "circle",
                                    "Marcar como pendente" if e.done else "Marcar como concluído", on_toggle,
                                    COLORS["ok"] if e.done else COLORS["subtle"]))
            h.addWidget(icon_button("edit", "Editar", on_edit))
            h.addWidget(icon_button("delete", "Excluir", on_delete, COLORS["danger"]))
            self.setToolTip(e.item.notes[:600] if e.item.notes else "Clique para editar")
        else:
            fg, bg = {"meeting": (COLORS["violet_text"], COLORS["violet_bg"]),
                      "event": (COLORS["violet_text"], COLORS["violet_bg"]),
                      "exam": (COLORS["danger_text"], COLORS["danger_bg"])}.get(
                e.kind, (COLORS["primary_text"], COLORS["primary_soft"]))
            h.addWidget(Pill(KIND_LABEL[e.kind], fg, bg), 0, Qt.AlignVCenter)
            self.setToolTip({"activity": "Abrir a atividade", "event": "Abrir a página do evento"}.get(
                e.kind, "Abrir a prova" if e.aid is not None else ""))
            if e.kind == "meeting" or (e.kind == "exam" and e.aid is None):
                self.setCursor(Qt.ArrowCursor)

    def mouseReleaseEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self._on_open(self.entry)


# ---------------------------------------------------------------------- página

class AgendaPage(QWidget):
    open_activity = Signal(int)
    notify = Signal(str, object)

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.setObjectName("Page")
        self._filter = "upcoming"
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        body = QWidget()
        body.setObjectName("Page")
        body.setMaximumWidth(1100)
        scroll.setWidget(body)
        outer.addWidget(scroll)
        lay = QVBoxLayout(body)
        lay.setContentsMargins(32, 26, 32, 28)
        lay.setSpacing(14)

        head = QHBoxLayout()
        tv = QVBoxLayout()
        tv.setSpacing(2)
        tv.addWidget(label("Agenda", "H1"))
        self.subtitle = label("", "Muted", wrap=True)
        tv.addWidget(self.subtitle)
        head.addLayout(tv, 1)
        self.new_btn = button("Novo compromisso", "Primary", "add", on_click=lambda: self.new_item())
        self.new_btn.setMinimumHeight(38)
        head.addWidget(self.new_btn, 0, Qt.AlignTop)
        lay.addLayout(head)

        bar = QHBoxLayout()
        bar.setSpacing(6)
        self.filters = QButtonGroup(self)
        for key, text in FILTERS:
            b = button(text, "Chip")
            b.setCheckable(True)
            b.setChecked(key == self._filter)
            b.clicked.connect(lambda _=False, k=key: self._set_filter(k))
            self.filters.addButton(b)
            bar.addWidget(b)
        bar.addSpacing(12)
        self.show_linked = QCheckBox("Mostrar entregas, encontros virtuais e eventos")
        self.show_linked.setChecked(self.ctx.db.get_meta(META_SHOW_LINKED, "1") == "1")
        self.show_linked.toggled.connect(self._toggle_linked)
        bar.addWidget(self.show_linked)
        bar.addStretch(1)
        lay.addLayout(bar)

        self.panel = QFrame()
        self.panel.setObjectName("Panel")
        self.list = QVBoxLayout(self.panel)
        self.list.setContentsMargins(16, 10, 16, 12)
        self.list.setSpacing(0)
        lay.addWidget(self.panel)
        lay.addStretch(1)
        for sig in (ctx.agenda_changed, ctx.data_changed, ctx.events_changed):
            sig.connect(self.refresh)
        self.refresh()

    # ------------------------------------------------------------------ filtros
    def _set_filter(self, key: str) -> None:
        self._filter = key
        self.refresh()

    def _toggle_linked(self, on: bool) -> None:
        self.ctx.db.set_meta(META_SHOW_LINKED, "1" if on else "0")
        self.refresh()

    # ------------------------------------------------------------------ dados
    def own_entries(self) -> list[Entry]:
        out = []
        for it in self.ctx.db.list_agenda_items():
            sub = " · ".join(x for x in (it.time_range() if it.end_time or it.all_day else "", it.location) if x)
            out.append(Entry(day=it.date, time=it.start_time, title=it.title, subtitle=sub, kind="own",
                             color=category_color(it.category), done=it.done, item=it))
        return out

    def exam_entries(self, first: date, last: date) -> list[Entry]:
        """Provas da Sala de Aula Virtual e AVIN do Planograma: sempre visíveis, já que não ficam no quadro."""
        out: list[Entry] = []
        for a in self.ctx.db.list_activities():
            if not a.is_exam or a.due_at is None or not first <= a.due_at.date() <= last:
                continue
            dt = a.due_at
            date_only = (dt.hour, dt.minute, dt.second) == (23, 59, 59)
            out.append(Entry(day=dt.date(), time=None if date_only else f"{dt:%H:%M}", title=a.name,
                             subtitle=short_course(a.course), kind="exam", color=category_color("Prova"),
                             done=a.status == STATUS_DONE, aid=a.id))
        infos = [CourseInfo.from_dict(d) for d in self.ctx.db.list_course_info()]
        for d, courses in avin_days(infos, first, last).items():
            out.append(Entry(day=d, time=None, title="AVIN", subtitle=AVIN_SUBTITLE + ", ".join(map(short_course, courses)),
                             kind="exam", color=category_color("Prova")))
        return out

    def linked_entries(self, first: date, last: date) -> list[Entry]:
        out: list[Entry] = []
        for a in self.ctx.db.list_activities():
            if a.is_exam or a.due_at is None or not first <= a.due_at.date() <= last:
                continue
            dt = a.due_at
            date_only = (dt.hour, dt.minute, dt.second) == (23, 59, 59)
            out.append(Entry(day=dt.date(), time=None if date_only else f"{dt:%H:%M}", title=a.name,
                             subtitle=short_course(a.course), kind="activity", color=course_color(a.course),
                             done=a.status == STATUS_DONE, aid=a.id))
        infos = [CourseInfo.from_dict(d) for d in self.ctx.db.list_course_info()]
        done = completed_ids(infos, first)
        for info in infos:
            if info.course_id in done:
                continue
            for d, m in occurrences(info, first, last):
                out.append(Entry(day=d, time=m.time, title=f"Encontro virtual · {short_course(info.name)}",
                                 subtitle=m.title or m.describe(), kind="meeting", color=course_color(info.name)))
        mine = self.ctx.db.agenda_source_keys()
        for ev in self.ctx.db.list_portal_events(from_day=first.isoformat()):
            if ev.day and ev.day <= last and agenda_key(ev) not in mine:     # já na agenda: aparece como próprio
                out.append(Entry(day=ev.day, time=ev.time, title=ev.title, subtitle=ev.location or "",
                                 kind="event", color=COLORS["violet"], url=ev.url))
        return out

    def entries(self, today: date) -> list[Entry]:
        own = self.own_entries()
        if self._filter == "upcoming":
            items = [e for e in own if e.day >= today and not e.done]
        elif self._filter == "done":
            items = [e for e in own if e.done]
        else:
            items = own
        if self._filter != "done":
            last = today + timedelta(days=LINKED_DAYS)
            extra = self.exam_entries(today, last)
            if self.show_linked.isChecked():
                extra += self.linked_entries(today, last)
            items += [e for e in extra if self._filter == "all" or not e.done]
        return sorted(items, key=Entry.sort_key, reverse=self._filter == "done")

    def refresh(self, *_):
        today = datetime.now(TZ).date()
        own = self.ctx.db.list_agenda_items()
        pending = [i for i in own if i.date >= today and not i.done]
        week = [i for i in pending if i.date <= today + timedelta(days=6)]
        self.subtitle.setText(
            (f"{plural(len(pending), 'compromisso pendente', 'compromissos pendentes')} · {len(week)} nos próximos "
             "7 dias" if pending else "Organize aulas, provas, estudos e eventos em um só lugar."))
        clear_layout(self.list)
        items = self.entries(today)
        if not items:
            msg = {"upcoming": ("Nada agendado por enquanto", "Crie um compromisso ou adicione um evento pela aba "
                                                              "Eventos."),
                   "done": ("Nenhum compromisso concluído", "Os compromissos marcados como concluídos aparecem aqui."),
                   "all": ("Sua agenda está vazia", "Crie seu primeiro compromisso.")}[self._filter]
            self.list.addWidget(EmptyState("agenda", msg[0], msg[1],
                                           button("Novo compromisso", "Primary", "add", on_click=lambda: self.new_item())))
            return
        current = None
        for e in items:
            if e.day != current:
                current = e.day
                sec = label(day_title(e.day, today).upper(), "Section")
                sec.setContentsMargins(10, 12, 0, 4)
                if e.day == today:
                    sec.setStyleSheet(f"color:{COLORS['primary']};")
                self.list.addWidget(sec)
            if e.kind == "own":
                it = e.item
                row = EntryRow(e, self._open, on_toggle=lambda _=False, i=it: self.toggle_done(i),
                               on_edit=lambda _=False, i=it: self.edit_item(i),
                               on_delete=lambda _=False, i=it: self.delete_item(i))
            else:
                row = EntryRow(e, self._open)
            self.list.addWidget(row)

    # ------------------------------------------------------------------ ações
    def _open(self, e: Entry) -> None:
        if e.kind == "own":
            self.edit_item(e.item)
        elif e.kind in ("activity", "exam") and e.aid is not None:
            self.open_activity.emit(e.aid)
        elif e.kind == "event" and e.url:
            QDesktopServices.openUrl(QUrl(e.url))

    def new_item(self, day: Optional[date] = None) -> None:
        dlg = AgendaDialog(day=day, parent=self)
        if dlg.exec() and dlg.result_item:
            self.ctx.db.add_agenda_item(dlg.result_item)
            self.ctx.agenda_changed.emit()
            self.notify.emit("Compromisso criado", None)

    def edit_item(self, item: AgendaItem) -> None:
        dlg = AgendaDialog(item, parent=self)
        if dlg.exec() and dlg.result_item:
            r = dlg.result_item
            self.ctx.db.update_agenda_item(item.id, title=r.title, day=r.day, start_time=r.start_time,
                                           end_time=r.end_time, location=r.location, category=r.category,
                                           notes=r.notes)
            self.ctx.agenda_changed.emit()
            self.notify.emit("Compromisso salvo", None)

    def toggle_done(self, item: AgendaItem) -> None:
        self.ctx.db.update_agenda_item(item.id, done=not item.done)
        self.ctx.agenda_changed.emit()
        if not item.done:
            self.notify.emit("Compromisso concluído", lambda: (self.ctx.db.update_agenda_item(item.id, done=False),
                                                               self.ctx.agenda_changed.emit()))

    def delete_item(self, item: AgendaItem) -> None:
        if QMessageBox.question(self, "Excluir compromisso", f"Excluir \"{item.title}\" da agenda?") != QMessageBox.Yes:
            return
        self.ctx.db.delete_agenda_item(item.id)
        self.ctx.agenda_changed.emit()
        self.notify.emit("Compromisso excluído", lambda: (self.ctx.db.add_agenda_item(item),
                                                          self.ctx.agenda_changed.emit()))
