"""Aba Calendário: encontros virtuais das matérias ativas e calendário mensal com atividades e compromissos."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QDialog, QFrame, QGridLayout, QHBoxLayout, QPushButton, QScrollArea, QSizePolicy,
                               QVBoxLayout, QWidget)

from app.config import TZ
from app.models.activity import STATUS_DONE, Activity
from app.models.meetings import CourseInfo, avin_days, completed_ids, next_meeting, occurrences
from app.ui.format import category_color, course_color, short_course
from app.ui.theme import COLORS
from app.ui.widgets import Dot, button, clear_layout, icon_button, icon_label, label

WEEKDAY_FULL = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]
MONTHS = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro",
          "novembro", "dezembro"]
WEEK_HEAD = ["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"]
WD_SHORT = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
MAX_PER_DAY = 3
DAY_MIN_HEIGHT = 136      # número do dia + 3 itens + "+N mais"


def month_grid(year: int, month: int) -> list[date]:
    """42 dias (6 semanas, domingo a sábado) que cobrem o mês."""
    first = date(year, month, 1)
    start = first - timedelta(days=(first.weekday() + 1) % 7)
    return [start + timedelta(days=i) for i in range(42)]


def _short(text: str, n: int = 26) -> str:
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def _fmt_next(d: date, time: Optional[str], today: date) -> str:
    when = "Hoje" if d == today else ("Amanhã" if d == today + timedelta(days=1) else f"{WD_SHORT[d.weekday()]}, {d:%d/%m}")
    return when + (f" às {time}" if time else "")


class ElidedButton(QPushButton):
    """Botão que mostra o texto inteiro quando cabe e usa "…" só quando a célula é estreita."""

    def __init__(self, text: str):
        super().__init__(text)
        self.full_text = text

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.setText(self.fontMetrics().elidedText(self.full_text, Qt.ElideRight, max(20, self.width() - 16)))


class MeetingBox(QFrame):
    def __init__(self, info: CourseInfo, now: datetime):
        super().__init__()
        self.setObjectName("Panel")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        v = QVBoxLayout(self)
        v.setContentsMargins(16, 12, 16, 12)
        v.setSpacing(4)
        h = QHBoxLayout()
        h.addWidget(Dot(course_color(info.name), 10))
        t = label(short_course(info.name), "H3", wrap=True)
        t.setToolTip(info.name)
        h.addWidget(t, 1)
        h.addWidget(icon_label("calendar", COLORS["violet"], 14))
        v.addLayout(h)
        weekly = [m for m in info.meetings if m.kind == "weekly"]
        today = now.date()
        dated = [m for m in info.meetings if m.kind == "date" and m.date and m.date >= today.isoformat()]
        if not weekly and not dated:
            v.addWidget(label("Nenhum encontro virtual informado no portal.", "Small", wrap=True))
            return
        for m in weekly:
            v.addWidget(label(f"🎥  {m.describe()}"))
        for m in sorted(dated, key=lambda x: x.date)[:3]:
            v.addWidget(label(f"🎥  {m.describe()}  ·  {_short(m.title, 40)}", "Small", wrap=True))
        nxt = next_meeting(info, now.replace(tzinfo=None))
        if nxt:
            d, m = nxt
            p = label(f"Próximo: <b>{_fmt_next(d, m.time, today)}</b>")
            p.setStyleSheet(f"color:{COLORS['violet']};")
            v.addWidget(p)


class DayCell(QFrame):
    open_day = Signal(object)        # date

    def __init__(self, day: date, in_month: bool, is_today: bool):
        super().__init__()
        self.day = day
        self.setObjectName("DayCell")
        bg = COLORS["surface"] if in_month else COLORS["surface_alt"]
        border = COLORS["primary"] if is_today else COLORS["border"]
        self.setStyleSheet(f"QFrame#DayCell {{ background:{bg}; border:1px solid {border}; border-radius:8px; }}")
        self.setMinimumHeight(DAY_MIN_HEIGHT)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.v = QVBoxLayout(self)
        self.v.setContentsMargins(6, 4, 6, 4)
        self.v.setSpacing(3)
        n = QPushButton(str(day.day))
        n.setCursor(Qt.PointingHandCursor)
        n.setToolTip("Ver tudo deste dia")
        n.clicked.connect(lambda: self.open_day.emit(self.day))
        if is_today:
            n.setStyleSheet(f"QPushButton {{ background:{COLORS['primary']}; color:{COLORS['on_primary']}; border:none; "
                            "border-radius:10px; padding:1px 7px; font-weight:700; }")
        else:
            n.setStyleSheet(f"QPushButton {{ background:transparent; border:none; padding:1px 4px; font-weight:600; "
                            f"color:{COLORS['text'] if in_month else COLORS['subtle']}; }}"
                            f"QPushButton:hover {{ background:{COLORS['neutral_bg']}; border-radius:8px; }}")
        top = QHBoxLayout()
        top.addWidget(n)
        top.addStretch(1)
        self.v.addLayout(top)
        self.v.addStretch(1)
        self._count = 0
        self._overflow: list[str] = []

    def add_chip(self, w: QWidget, tip: str) -> None:
        if self._count < MAX_PER_DAY:
            self.v.insertWidget(self.v.count() - 1, w)
        else:
            w.deleteLater()
            self._overflow.append(tip)
        self._count += 1

    def finish(self) -> None:
        if self._overflow:
            more = QPushButton(f"+{len(self._overflow)} mais")
            more.setObjectName("Link")
            more.setCursor(Qt.PointingHandCursor)
            more.setToolTip("Clique para ver todos os itens deste dia")
            more.setStyleSheet("QPushButton { text-align:left; padding:0 4px; font-size:8.5pt; }")
            more.clicked.connect(lambda: self.open_day.emit(self.day))
            self.v.insertWidget(self.v.count() - 1, more)


class DayDialog(QDialog):
    """Todos os itens de um dia (atividades, encontros e compromissos da agenda), em ordem de horário."""
    open_activity = Signal(int)

    def __init__(self, day: date, items: list[dict], parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{day:%d/%m/%Y}")
        self.setMinimumWidth(460)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 20, 22, 16)
        lay.setSpacing(8)
        lay.addWidget(label(f"{WEEKDAY_FULL[day.weekday()].capitalize()}, {day.day} de {MONTHS[day.month - 1]}", "H2"))
        acts = sum(1 for i in items if not i["meeting"] and i["aid"] is not None)
        meets = sum(1 for i in items if i["meeting"])
        own = len(items) - acts - meets
        lay.addWidget(label(" · ".join(x for x in (
            f"{acts} {'atividade' if acts == 1 else 'atividades'}" if acts else "",
            f"{meets} {'encontro virtual' if meets == 1 else 'encontros virtuais'}" if meets else "",
            f"{own} {'compromisso' if own == 1 else 'compromissos'}" if own else "") if x)
            or "Nada neste dia.", "Muted"))
        for it in items:
            lay.addWidget(self._row(it))
        lay.addStretch(1)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(button("Fechar", "Primary", on_click=self.accept))
        lay.addLayout(row)

    def _row(self, it: dict) -> QWidget:
        w = QPushButton()
        opens = not it["meeting"] and it["aid"] is not None
        w.setCursor(Qt.PointingHandCursor if opens else Qt.ArrowCursor)
        bg = COLORS["violet_bg"] if it["meeting"] else COLORS["surface"]
        w.setStyleSheet(f"QPushButton {{ text-align:left; background:{bg}; border:1px solid {COLORS['border']};"
                        f" border-left:4px solid {it['color']}; border-radius:8px; padding:0; }}"
                        f"QPushButton:hover {{ border-color:{COLORS['border_strong']}; }}")
        h = QHBoxLayout(w)
        h.setContentsMargins(12, 8, 12, 8)
        t = label(it["time"] or "—", "H3")
        t.setFixedWidth(46)
        h.addWidget(t)
        v = QVBoxLayout()
        v.setSpacing(0)
        title = label(it["title"], wrap=True)
        if it["done"]:
            title.setStyleSheet(f"text-decoration: line-through; color:{COLORS['subtle']};")
        v.addWidget(title)
        v.addWidget(label(it["subtitle"], "Small", wrap=True))
        h.addLayout(v, 1)
        if opens:
            h.addWidget(icon_label("chevron_right", COLORS["subtle"], 12))
            w.clicked.connect(lambda: (self.open_activity.emit(it["aid"]), self.accept()))
        w.setMinimumHeight(52)
        w.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        w.setToolTip("Abrir a atividade" if opens else it["subtitle"])
        return w


class CalendarPage(QWidget):
    open_activity = Signal(int)

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.setObjectName("Page")
        today = datetime.now(TZ).date()
        self.year, self.month = today.year, today.month
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        body.setObjectName("Page")
        scroll.setWidget(body)
        outer.addWidget(scroll)
        lay = QVBoxLayout(body)
        lay.setContentsMargins(28, 22, 28, 24)
        lay.setSpacing(14)

        head = QHBoxLayout()
        tv = QVBoxLayout()
        tv.setSpacing(0)
        tv.addWidget(label("Calendário", "H1"))
        tv.addWidget(label("Prazos das atividades, encontros virtuais das matérias em andamento e compromissos da sua "
                           "agenda.", "Muted"))
        head.addLayout(tv, 1)
        lay.addLayout(head)

        sec = label("ENCONTROS VIRTUAIS", "Section")
        lay.addWidget(sec)
        self.meet_grid = QGridLayout()
        self.meet_grid.setSpacing(10)
        lay.addLayout(self.meet_grid)

        nav = QHBoxLayout()
        nav.setSpacing(6)
        nav.addWidget(icon_button("chevron_left", "Mês anterior", lambda: self.shift(-1), COLORS["text_2"]))
        self.month_lbl = label("", "H2")
        nav.addWidget(self.month_lbl)
        nav.addWidget(icon_button("chevron_right", "Próximo mês", lambda: self.shift(1), COLORS["text_2"]))
        nav.addSpacing(8)
        nav.addWidget(button("Hoje", "", on_click=self.go_today))
        nav.addStretch(1)
        legend = label(f"<span style='background:{COLORS['violet_bg']};color:{COLORS['violet']}'>&nbsp;■&nbsp;</span> Encontro "
                       f"virtual (fundo lilás) &nbsp;&nbsp; "
                       f"<span style='color:{COLORS['primary']}'>▌</span> Atividade · a barra tem a cor da matéria "
                       "&nbsp;&nbsp; "
                       "<s>riscada</s> = concluída", "Small")
        nav.addWidget(legend)
        lay.addSpacing(6)
        lay.addLayout(nav)

        self.grid = QGridLayout()
        self.grid.setSpacing(6)
        for i, d in enumerate(WEEK_HEAD):
            h = label(d.upper(), "Section")
            h.setAlignment(Qt.AlignCenter)
            self.grid.addWidget(h, 0, i)
        for c in range(7):
            self.grid.setColumnStretch(c, 1)
        for r in range(1, 7):                    # 6 semanas; altura mínima garantida por linha
            self.grid.setRowMinimumHeight(r, DAY_MIN_HEIGHT)
        lay.addLayout(self.grid)
        lay.addStretch(1)
        ctx.data_changed.connect(self.refresh)
        ctx.agenda_changed.connect(self.refresh)
        self.refresh()

    def open_day(self, d: date) -> None:
        items = sorted(self.day_items.get(d, []), key=lambda i: i["sort"])
        dlg = DayDialog(d, items, self)
        dlg.open_activity.connect(self.open_activity.emit)
        dlg.exec()

    # ------------------------------------------------------------------ navegação
    def shift(self, delta: int) -> None:
        m = self.month - 1 + delta
        self.year, self.month = self.year + m // 12, m % 12 + 1
        self.refresh()

    def go_today(self) -> None:
        t = datetime.now(TZ).date()
        self.year, self.month = t.year, t.month
        self.refresh()

    # ------------------------------------------------------------------ dados
    def active_courses(self, today: date) -> list[CourseInfo]:
        infos = [CourseInfo.from_dict(d) for d in self.ctx.db.list_course_info()]
        done = completed_ids(infos, today)
        return [c for c in infos if c.course_id not in done]

    def refresh(self, *_):
        now = datetime.now(TZ)
        today = now.date()
        self.month_lbl.setText(f"{MONTHS[self.month - 1].capitalize()} de {self.year}")
        active = self.active_courses(today)

        clear_layout(self.meet_grid)
        if not active:
            self.meet_grid.addWidget(label("Os encontros aparecem aqui depois de atualizar os dados do portal. "
                                           "Matérias já concluídas não são mostradas.", "Muted", wrap=True), 0, 0)
        for i, info in enumerate(active):
            self.meet_grid.addWidget(MeetingBox(info, now), i // 3, i % 3, Qt.AlignTop)

        # limpa as células (mantém o cabeçalho dos dias da semana na linha 0)
        for i in reversed(range(self.grid.count())):
            item = self.grid.itemAt(i)
            r, _c, _rs, _cs = self.grid.getItemPosition(i)
            if r > 0 and item.widget():
                w = item.widget()
                self.grid.removeWidget(w)
                w.hide()
                w.setParent(None)
                w.deleteLater()
        days = month_grid(self.year, self.month)
        cells: dict[date, DayCell] = {}
        self.day_items: dict[date, list[dict]] = {}
        for i, d in enumerate(days):
            cell = DayCell(d, d.month == self.month, d == today)
            cell.open_day.connect(self.open_day)
            cells[d] = cell
            self.grid.addWidget(cell, 1 + i // 7, i % 7)

        first, last = days[0], days[-1]
        per_day: dict[date, list] = {}             # (horário, ordem, widget, dica) — ordenado por horário
        for info in active:
            for d, m in occurrences(info, first, last):
                if d in cells:
                    txt = f"{m.time + ' · ' if m.time else ''}{short_course(info.name)}"
                    tip = f"Encontro virtual — {info.name}\n{m.describe()}"
                    chip = self._chip(txt, course_color(info.name), tip, meeting=True)
                    chip.clicked.connect(lambda _=False, day=d: self.open_day(day))
                    per_day.setdefault(d, []).append((m.time or "00:00", 0, chip, tip))
                    self.day_items.setdefault(d, []).append(dict(
                        sort=(m.time or "00:00", 0), time=m.time, title=f"Encontro virtual · {short_course(info.name)}",
                        subtitle=m.describe(), color=course_color(info.name), meeting=True, done=False, aid=None))
        for a in self.ctx.db.list_activities():
            if a.due_at is None or a.due_at.date() not in cells:
                continue
            dt = a.due_at
            date_only = (dt.hour, dt.minute, dt.second) == (23, 59, 59)
            hhmm = "" if date_only else f"{dt:%H:%M} "
            color = category_color("Prova") if a.is_exam else course_color(a.course)
            tip = (f"Prova — {a.name}\n{a.course}\nData: {a.due_display}" if a.is_exam else
                   f"{a.name}\n{a.course}\nPrazo: {a.due_display} · {a.points}")
            chip = self._chip(f"{hhmm}{a.name}", color, tip, done=a.status == STATUS_DONE)
            chip.clicked.connect(lambda _=False, aid=a.id: self.open_activity.emit(aid))
            per_day.setdefault(dt.date(), []).append(("23:59" if date_only else f"{dt:%H:%M}", 1, chip, tip))
            self.day_items.setdefault(dt.date(), []).append(dict(
                sort=("23:59" if date_only else f"{dt:%H:%M}", 1), time=None if date_only else f"{dt:%H:%M}",
                title=a.name, subtitle=(f"Prova · {short_course(a.course)}" if a.is_exam else
                                        f"{short_course(a.course)} · {a.points}" if a.points != "-" else
                                        short_course(a.course)),
                color=color, meeting=False, done=a.status == STATUS_DONE, aid=a.id))
        for d, courses in avin_days(active, first, last).items():
            if d not in cells:
                continue
            tip = "AVIN — avaliação integrada do módulo\n" + "\n".join(courses)
            chip = self._chip("AVIN", category_color("Prova"), tip, meeting=True, agenda=True)
            chip.clicked.connect(lambda _=False, day=d: self.open_day(day))
            per_day.setdefault(d, []).append(("00:00", 1, chip, tip))
            self.day_items.setdefault(d, []).append(dict(
                sort=("00:00", 1), time=None, title="AVIN", subtitle="Prova · " + ", ".join(map(short_course, courses)),
                color=category_color("Prova"), meeting=False, done=False, aid=None))
        for it in self.ctx.db.list_agenda_items():
            d = it.date
            if d not in cells:
                continue
            tip = "\n".join(x for x in (f"Agenda — {it.title}", f"{it.time_range()} · {it.category}", it.location) if x)
            chip = self._chip(f"{it.start_time + ' ' if it.start_time else ''}{it.title}",
                              category_color(it.category), tip, meeting=True, done=it.done, agenda=True)
            chip.clicked.connect(lambda _=False, day=d: self.open_day(day))
            per_day.setdefault(d, []).append((it.start_time or "00:00", 2, chip, tip))
            self.day_items.setdefault(d, []).append(dict(
                sort=(it.start_time or "00:00", 2), time=it.start_time, title=it.title,
                subtitle=" · ".join(x for x in (f"Agenda · {it.category}", it.location) if x),
                color=category_color(it.category), meeting=False, done=it.done, aid=None))
        for d, items in per_day.items():
            for _t, _o, chip, tip in sorted(items, key=lambda x: (x[0], x[1])):
                cells[d].add_chip(chip, tip)
        for c in cells.values():
            c.finish()

    @staticmethod
    def _chip(text: str, color: str, tip: str, meeting: bool = False, done: bool = False,
              agenda: bool = False) -> "ElidedButton":
        b = ElidedButton(text)
        b.setToolTip(tip)
        b.setCursor(Qt.ArrowCursor if meeting else Qt.PointingHandCursor)
        bg = COLORS["violet_bg"] if meeting and not agenda else COLORS["surface"]
        deco = f"text-decoration: line-through; color:{COLORS['subtle']};" if done else f"color:{COLORS['text_2']};"
        b.setStyleSheet(f"QPushButton {{ text-align:left; padding:2px 6px; border:none; border-left:3px solid {color};"
                        f" border-radius:4px; background:{bg}; font-size:8.5pt; {deco} }}"
                        f"QPushButton:hover {{ background:{COLORS['neutral_bg']}; }}")
        b.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        b.setFixedHeight(22)
        return b
