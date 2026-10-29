"""Aba Eventos: próximos eventos da Unilavras (portal > Eventos > Inscrição), com inscrição e envio para a agenda."""
from __future__ import annotations

from datetime import datetime, timedelta

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QButtonGroup, QFrame, QHBoxLayout, QLineEdit, QScrollArea, QVBoxLayout, QWidget

from app.config import EVENTS_URL, TZ
from app.models.activity import iso_to_dt
from app.models.agenda import AgendaItem
from app.models.events import PortalEvent
from app.services.events import META_LAST_EVENTS
from app.ui.calendar_page import MONTHS, WEEKDAY_FULL
from app.ui.format import plural, relative_time
from app.ui.icons import icon
from app.ui.theme import COLORS
from app.ui.widgets import EmptyState, Pill, button, clear_layout, icon_label, label

MONTHS_SHORT = [m[:3].upper() for m in MONTHS]
NEW_DAYS = 3                       # selo "Novo" para eventos vistos pela primeira vez há poucos dias
FILTERS = (("all", "Todos"), ("week", "Próximos 7 dias"), ("month", "Próximos 30 dias"))


def agenda_key(ev: PortalEvent) -> str:
    return f"evento:{ev.key}"


def event_to_agenda(ev: PortalEvent) -> AgendaItem:
    end = iso_to_dt(ev.end_at)
    start = ev.time
    return AgendaItem(title=ev.title, day=ev.date, start_time=start,
                      end_time=f"{end:%H:%M}" if start and end and end.date() == ev.day and end > ev.start else None,
                      location=ev.location or "", category="Evento",
                      notes="\n".join(x for x in (ev.description or "", ev.url or "") if x),
                      source_key=agenda_key(ev))


class EventCard(QFrame):
    add_to_agenda = Signal(object)          # PortalEvent

    def __init__(self, ev: PortalEvent, in_agenda: bool, now: datetime):
        super().__init__()
        self.setObjectName("Panel")
        self.ev = ev
        h = QHBoxLayout(self)
        h.setContentsMargins(16, 14, 16, 14)
        h.setSpacing(14)

        day = ev.day
        badge = QFrame()
        badge.setFixedSize(58, 64)
        badge.setStyleSheet(f"QFrame {{ background:{COLORS['primary_soft']}; border-radius:10px; }}")
        bv = QVBoxLayout(badge)
        bv.setContentsMargins(0, 6, 0, 6)
        bv.setSpacing(0)
        d = label(str(day.day), "TileValue")
        d.setStyleSheet(f"color:{COLORS['primary_text']}; font-size:18pt;")
        m = label(MONTHS_SHORT[day.month - 1], "Section")
        m.setStyleSheet(f"color:{COLORS['primary_text']};")
        for w in (d, m):
            w.setAlignment(Qt.AlignCenter)
            bv.addWidget(w)
        h.addWidget(badge, 0, Qt.AlignTop)

        v = QVBoxLayout()
        v.setSpacing(4)
        top = QHBoxLayout()
        top.setSpacing(6)
        title = label(ev.title, "H3", wrap=True)
        title.setToolTip(ev.title)
        top.addWidget(title, 1)
        seen = iso_to_dt(ev.first_seen)
        if seen and now - seen <= timedelta(days=NEW_DAYS):
            top.addWidget(Pill("Novo", COLORS["ok_text"], COLORS["ok_bg"]), 0, Qt.AlignTop)
        v.addLayout(top)
        when = f"{WEEKDAY_FULL[day.weekday()].capitalize()}, {day.day} de {MONTHS[day.month - 1]}"
        if ev.time:
            when += f" · {ev.time}"
        info = QHBoxLayout()
        info.setSpacing(4)
        info.addWidget(icon_label("calendar", COLORS["muted"], 12))
        info.addWidget(label(when, "Muted"))
        if ev.location:
            info.addSpacing(10)
            info.addWidget(icon_label("pin", COLORS["muted"], 12))
            loc = label(ev.location, "Muted", wrap=True)
            loc.setToolTip(ev.location)
            info.addWidget(loc, 1)
        else:
            info.addStretch(1)
        v.addLayout(info)
        if ev.description:
            desc = ev.description if len(ev.description) <= 220 else ev.description[:219].rstrip() + "…"
            dl = label(desc, "Small", wrap=True)
            dl.setToolTip(ev.description[:1200])
            v.addWidget(dl)
        acts = QHBoxLayout()
        acts.setSpacing(8)
        if ev.url:
            acts.addWidget(button("Saiba mais e inscrição", "Primary", "open", tip=ev.url,
                                  on_click=lambda: QDesktopServices.openUrl(QUrl(ev.url))))
        self.agenda_btn = button("Na agenda" if in_agenda else "Adicionar à agenda", "",
                                 "check" if in_agenda else "add",
                                 COLORS["ok"] if in_agenda else None,
                                 tip="Já está na sua agenda" if in_agenda else "Criar um compromisso na aba Agenda",
                                 on_click=lambda: self.add_to_agenda.emit(self.ev))
        self.agenda_btn.setEnabled(not in_agenda)
        acts.addWidget(self.agenda_btn)
        acts.addStretch(1)
        v.addLayout(acts)
        h.addLayout(v, 1)


class EventsPage(QWidget):
    request_update = Signal()
    notify = Signal(str, object)

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.setObjectName("Page")
        self._filter = "all"
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
        tv.addWidget(label("Eventos", "H1"))
        self.subtitle = label("", "Muted", wrap=True)
        tv.addWidget(self.subtitle)
        head.addLayout(tv, 1)
        rv = QVBoxLayout()
        rv.setSpacing(4)
        self.update_btn = button("Atualizar eventos", "Primary", "sync",
                                 tip="Buscar os eventos na página da Unilavras (não precisa de login)",
                                 on_click=self.request_update.emit)
        self.update_btn.setMinimumHeight(38)
        self.last = label("", "Small")
        self.last.setAlignment(Qt.AlignRight)
        rv.addWidget(self.update_btn)
        rv.addWidget(self.last)
        head.addLayout(rv)
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
        bar.addSpacing(8)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Buscar evento")
        self.search.setClearButtonEnabled(True)
        self.search.addAction(icon("search", COLORS["subtle"]), QLineEdit.LeadingPosition)
        self.search.setFixedWidth(260)
        self.search.textChanged.connect(self.refresh)
        bar.addWidget(self.search)
        bar.addStretch(1)
        bar.addWidget(button("Abrir site de eventos", "Link",
                             on_click=lambda: QDesktopServices.openUrl(QUrl(EVENTS_URL))))
        lay.addLayout(bar)

        self.list = QVBoxLayout()
        self.list.setSpacing(12)
        lay.addLayout(self.list)
        lay.addStretch(1)
        ctx.events_changed.connect(self.refresh)
        ctx.agenda_changed.connect(self.refresh)
        self.refresh()

    def _set_filter(self, key: str) -> None:
        self._filter = key
        self.refresh()

    def visible_events(self, now: datetime) -> list[PortalEvent]:
        today = now.date()
        events = self.ctx.db.list_portal_events(from_day=today.isoformat())
        if self._filter != "all":
            limit = today + timedelta(days=7 if self._filter == "week" else 30)
            events = [e for e in events if e.day and e.day <= limit]
        q = self.search.text().strip().lower()
        if q:
            events = [e for e in events if q in f"{e.title} {e.location or ''} {e.description or ''}".lower()]
        return events

    def refresh(self, *_):
        now = datetime.now(TZ)
        last = iso_to_dt(self.ctx.db.get_meta(META_LAST_EVENTS))
        self.last.setText(f"Atualizado {relative_time(last, now)}" if last else "")
        upcoming = self.ctx.db.list_portal_events(from_day=now.date().isoformat())
        self.subtitle.setText(
            f"{plural(len(upcoming), 'evento futuro', 'eventos futuros')} da Unilavras · palestras, visitas técnicas "
            "e outros eventos com inscrição pelo portal." if upcoming else
            "Palestras, visitas técnicas e outros eventos da Unilavras (portal > Eventos > Inscrição).")
        clear_layout(self.list)
        shown = self.visible_events(now)
        if not shown:
            if upcoming:
                empty = EmptyState("search", "Nenhum evento com esse filtro", "Tente outro período ou outra busca.")
            elif last:
                empty = EmptyState("event", "Nenhum evento futuro no momento",
                                   "Novos eventos aparecem aqui quando a Unilavras os publicar.")
            else:
                empty = EmptyState("event", "Nenhum evento carregado ainda",
                                   "Clique em \"Atualizar eventos\" para buscar os próximos eventos da Unilavras.",
                                   button("Atualizar eventos", "Primary", "sync", on_click=self.request_update.emit))
            self.list.addWidget(empty)
            return
        in_agenda = self.ctx.db.agenda_source_keys()
        for ev in shown:
            card = EventCard(ev, agenda_key(ev) in in_agenda, now)
            card.add_to_agenda.connect(self.add_to_agenda)
            self.list.addWidget(card)

    def add_to_agenda(self, ev: PortalEvent) -> None:
        if agenda_key(ev) in self.ctx.db.agenda_source_keys():
            return
        self.ctx.db.add_agenda_item(event_to_agenda(ev))
        self.ctx.agenda_changed.emit()
        self.notify.emit("Evento adicionado à agenda", None)

    def set_updating(self, running: bool) -> None:
        self.update_btn.setEnabled(not running)
        self.update_btn.setText("Atualizando eventos…" if running else "Atualizar eventos")
