"""Aba Notas: disciplinas (Grade de Notas) e AVINs em ordem cronológica, com detalhes expansíveis."""
from __future__ import annotations

import re
from typing import Optional

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QScrollArea, QVBoxLayout, QWidget

from app.models.activity import iso_to_dt
from app.models.grades import (AVIN_POINTS_PER_QUESTION, Q_ANNULLED, Q_BLANK, Q_CORRECT, Q_DOUBLE, Q_LABELS, Q_WAIVED,
                               Q_WRONG, AvinResult, CourseGrade, GradeItem, apply_module_rule, assign_avins,
                               course_total, fmt_num, module_numbers, portal_has_avin)
from app.services.grades_updater import META_LAST_GRADES
from app.ui.format import course_color, plural, relative_time, short_course
from app.ui.theme import COLORS
from app.ui.widgets import Dot, EmptyState, Pill, button, clear_layout, icon_label, label


def q_style() -> dict:
    """(texto, fundo, símbolo) por situação da questão — símbolo garante leitura sem depender da cor."""
    return {
        Q_CORRECT: (COLORS["ok_text"], COLORS["ok_bg"], "✓"),
        Q_WRONG: (COLORS["danger_text"], COLORS["danger_bg"], "✗"),
        Q_DOUBLE: (COLORS["violet_text"], COLORS["violet_bg"], "≡"),
        Q_BLANK: (COLORS["neutral_text"], COLORS["neutral_bg"], "–"),
        Q_ANNULLED: (COLORS["warn_text"], COLORS["warn_bg"], "Ø"),
        Q_WAIVED: (COLORS["neutral_text"], COLORS["neutral_bg"], "•"),
    }


def short_avin(name: str) -> str:
    """"AVIN EAD 1° módulo - 2026/2 - Curso Superior de ..." -> "AVIN EAD 1° módulo - 2026/2"."""
    return re.split(r"\s+-\s+Curso\b", name or "", maxsplit=1)[0].strip() or name


def _date(iso: Optional[str], with_time: bool = False) -> str:
    dt = iso_to_dt(iso) if iso and "T" in iso else None
    if dt:
        return dt.strftime("%d/%m/%Y %H:%M" if with_time else "%d/%m/%Y")
    if iso and re.fullmatch(r"\d{4}-\d{2}-\d{2}", iso):
        y, m, d = iso.split("-")
        return f"{d}/{m}/{y}"
    return "-"


class GradeCard(QFrame):
    toggled = Signal(str, bool)

    def __init__(self, key: str, expanded: bool):
        super().__init__()
        self.key = key
        self.setObjectName("Panel")
        self.v = QVBoxLayout(self)
        self.v.setContentsMargins(0, 0, 0, 0)
        self.v.setSpacing(0)
        self.head = QFrame()
        self.head.setObjectName("Row")
        self.head.setCursor(Qt.PointingHandCursor)
        self.head.mouseReleaseEvent = lambda e: self.set_expanded(not self.body.isVisible(), emit=True) \
            if e.button() == Qt.LeftButton else None
        self.h = QHBoxLayout(self.head)
        self.h.setContentsMargins(18, 14, 18, 14)
        self.h.setSpacing(12)
        self.chev = icon_label("chevron_right", COLORS["muted"], 12)
        self.h.addWidget(self.chev)
        self.v.addWidget(self.head)
        self.body = QWidget()
        self.bv = QVBoxLayout(self.body)
        self.bv.setContentsMargins(46, 0, 22, 16)
        self.bv.setSpacing(4)
        self.v.addWidget(self.body)
        self.set_expanded(expanded)

    def set_expanded(self, on: bool, emit: bool = False) -> None:
        self.body.setVisible(on)
        from app.ui.icons import glyph
        self.chev.setText(glyph("chevron_down" if on else "chevron_right"))
        self.head.setToolTip("Ocultar notas" if on else "Ver as notas de cada atividade")
        if emit:
            self.toggled.emit(self.key, on)

    def add_header(self, color: str, title: str, subtitle: str, pill: Pill, grade: str, grade_caption: str) -> None:
        self.h.addWidget(Dot(color, 10))
        tv = QVBoxLayout()
        tv.setSpacing(1)
        tv.addWidget(label(title, "H3", wrap=True))
        tv.addWidget(label(subtitle, "Small"))
        self.h.addLayout(tv, 1)
        self.h.addWidget(pill)
        gv = QVBoxLayout()
        gv.setSpacing(0)
        g = label(grade, "TileValue")
        g.setAlignment(Qt.AlignRight)
        c = label(grade_caption, "Small")
        c.setAlignment(Qt.AlignRight)
        gv.addWidget(g)
        gv.addWidget(c)
        wrap = QWidget()
        wrap.setLayout(gv)
        wrap.setMinimumWidth(110)
        self.h.addWidget(wrap)


class GradesPage(QWidget):
    request_update = Signal()

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.setObjectName("Page")
        self.expanded: set[str] = set()
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
        lay.setSpacing(14)

        head = QHBoxLayout()
        tv = QVBoxLayout()
        tv.setSpacing(2)
        tv.addWidget(label("Notas", "H1"))
        self.subtitle = label("", "Muted")
        tv.addWidget(self.subtitle)
        head.addLayout(tv, 1)
        rv = QVBoxLayout()
        rv.setSpacing(4)
        self.update_btn = button("Atualizar notas", "Primary", "sync",
                                 tip="Buscar suas notas no portal (só as notas, sem mexer no quadro)",
                                 on_click=self.request_update.emit)
        self.update_btn.setMinimumHeight(38)
        self.last = label("", "Small")
        self.last.setAlignment(Qt.AlignRight)
        rv.addWidget(self.update_btn)
        rv.addWidget(self.last)
        head.addLayout(rv)
        lay.addLayout(head)

        self.list = QVBoxLayout()
        self.list.setSpacing(10)
        lay.addLayout(self.list)
        lay.addStretch(1)
        ctx.data_changed.connect(self.refresh)
        self.refresh()

    # ------------------------------------------------------------------
    def refresh(self, *_):
        clear_layout(self.list)
        snaps = self.ctx.db.list_grade_snapshots()
        last = iso_to_dt(self.ctx.db.get_meta(META_LAST_GRADES))
        self.last.setText(f"Atualizado {relative_time(last)}" if last else "")
        courses = [CourseGrade.from_dict(p) for k, p, _ in snaps if k == "course"]
        avins = [AvinResult.from_dict(p) for k, p, _ in snaps if k == "avin"]
        if not snaps:
            self.subtitle.setText("Suas notas da Sala de Aula Virtual e do AVIN, em ordem cronológica.")
            self.list.addWidget(EmptyState("trophy", "Nenhuma nota ainda",
                                           "Clique em \"Atualizar notas\" para buscar suas notas no portal.",
                                           button("Atualizar notas", "Primary", "sync",
                                                  on_click=self.request_update.emit)))
            return
        apply_module_rule(courses)              # módulo novo iniciado => anteriores concluídos
        modules = module_numbers(courses)
        avins_by_course, orphans = assign_avins(courses, avins)   # AVIN é nota de cada matéria do módulo
        done = sum(c.completed for c in courses)
        self.subtitle.setText(f"{plural(len(courses), 'matéria', 'matérias')} · {done} "
                              f"{'concluída' if done == 1 else 'concluídas'} · ordem cronológica pela data de início")
        for cg in courses:                      # já vêm em ordem cronológica
            self.list.addWidget(self._course_card(cg, modules.get(cg.course_id),
                                                  avins_by_course.get(cg.course_id, [])))
        for av in orphans:
            self.list.addWidget(label(f"O resultado \"{short_avin(av.name)}\" ({fmt_num(av.score)}) não foi somado: "
                                      "nenhuma matéria tinha começado antes da data da prova.", "Small", wrap=True))

    def _toggle(self, key: str, on: bool) -> None:
        (self.expanded.add if on else self.expanded.discard)(key)

    # ------------------------------------------------------------------ disciplina
    def _course_card(self, cg: CourseGrade, module: Optional[int] = None,
                     avins: Optional[list] = None) -> GradeCard:
        avins = avins or []
        counted = bool(avins) and not portal_has_avin(cg)
        card = GradeCard(cg.key, cg.key in self.expanded)
        card.toggled.connect(self._toggle)
        if cg.completed:
            pill = Pill("Matéria concluída", COLORS["ok_text"], COLORS["ok_bg"], "check_circle")
            caption = "nota total"
        else:
            pill = Pill("Em andamento", COLORS["primary_text"], COLORS["primary_soft"], "sync")
            caption = "nota atual"
        prog = f" · {fmt_num(cg.progress)}% concluído" if cg.progress is not None else ""
        mod = f"Módulo {module} · " if module else ""
        if counted:
            caption += " · com AVIN"
        card.add_header(course_color(cg.name), short_course(cg.name), f"{mod}Início {_date(cg.start_date)}{prog}", pill,
                        fmt_num(course_total(cg, avins)), caption)
        b = card.bv
        has_items = False
        for cat in cg.categories:
            if not cat.items:
                continue
            has_items = True
            mx = f" de {fmt_num(cat.max_value)}" if cat.max_value is not None else ""
            sec = label(f"{cat.name.upper()}  ·  {fmt_num(cat.value)}{mx}", "Section")
            sec.setContentsMargins(0, 10, 0, 4)
            b.addWidget(sec)
            for it in cat.items:
                b.addWidget(self._item_row(it))
        if not has_items and not avins:
            b.addWidget(label("Nenhuma atividade com nota nesta disciplina ainda.", "Muted"))
        for av in avins:
            self._avin_section(b, av, counted)
        foot = QHBoxLayout()
        foot.setContentsMargins(0, 8, 0, 0)
        if counted:
            expl = (f"Nota final = {fmt_num(cg.final)} (atividades no portal) + "
                    + " + ".join(fmt_num(a.score) for a in avins) + f" (AVIN) = {fmt_num(course_total(cg, avins))}.")
        elif avins:
            expl = "O AVIN já aparece na Grade de Notas do portal, então não foi somado de novo."
        else:
            expl = "A nota da disciplina é a soma das categorias, como mostra o portal."
        foot.addWidget(label(expl, "Small", wrap=True), 1)
        if cg.url:
            foot.addWidget(button("Ver no portal", "Link", on_click=lambda: QDesktopServices.openUrl(QUrl(cg.url))))
        b.addLayout(foot)
        return card

    @staticmethod
    def _item_row(it: GradeItem) -> QWidget:
        w = QFrame()
        w.setObjectName("Row")
        h = QHBoxLayout(w)
        h.setContentsMargins(8, 6, 8, 6)
        h.setSpacing(12)
        h.addWidget(label(it.name, wrap=True), 1)
        when = _date(it.submitted_at) if it.submitted_at else (f"prazo {_date(it.deadline)}" if it.deadline else "")
        d = label(when, "Small")
        d.setMinimumWidth(96)
        h.addWidget(d)
        st = it.status
        colors = {"Corrigida": (COLORS["ok_text"], COLORS["ok_bg"]),
                  "Aguardando correção": (COLORS["primary_text"], COLORS["primary_soft"]),
                  "Não entregue": (COLORS["danger_text"], COLORS["danger_bg"]),
                  "Pendente": (COLORS["neutral_text"], COLORS["neutral_bg"])}[st]
        p = Pill(st, *colors)
        p.setMinimumWidth(150)
        p.setAlignment(Qt.AlignCenter)
        h.addWidget(p)
        val = fmt_num(it.value) if it.value is not None else "—"
        mx = f" / {fmt_num(it.max_value)}" if it.max_value is not None else ""
        g = label(f"<b>{val}</b><span style='color:{COLORS['muted']}'>{mx}</span>")
        g.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        g.setMinimumWidth(70)
        h.addWidget(g)
        return w

    # ------------------------------------------------------------------ AVIN (dentro da matéria)
    def _avin_section(self, b: QVBoxLayout, av: AvinResult, counted: bool) -> None:
        sec = label(f"AVIN DO MÓDULO  ·  {fmt_num(av.score)} de {fmt_num(av.max_score)}"
                    + ("" if counted else "  (não somado)"), "Section")
        sec.setContentsMargins(0, 12, 0, 4)
        sec.setStyleSheet(f"color:{COLORS['violet']};")
        b.addWidget(sec)
        b.addWidget(label(f"{short_avin(av.name)} · prova em {_date(av.start, True)}", "Small"))
        b.addWidget(label(f"<b>{av.correct}</b> {'acerto' if av.correct == 1 else 'acertos'} × "
                          f"{fmt_num(AVIN_POINTS_PER_QUESTION)} = <b>{fmt_num(av.score)}</b> de "
                          f"{fmt_num(av.max_score)} pontos ({len(av.questions)} questões)"))
        many = {Q_WRONG: "Erros", Q_BLANK: "Em branco", Q_DOUBLE: "Marcações duplas", Q_ANNULLED: "Anuladas",
                Q_WAIVED: "Dispensadas"}
        others = [f"{Q_LABELS[s] if av.count(s) == 1 else many[s]}: {av.count(s)}"
                  for s in (Q_WRONG, Q_BLANK, Q_DOUBLE, Q_ANNULLED, Q_WAIVED) if av.count(s)]
        if others:
            b.addWidget(label(" · ".join(others), "Small"))
        if av.count(Q_ANNULLED):
            b.addWidget(label("Questões anuladas não entram na conta: só as marcadas em verde (corretas) valem "
                              f"{fmt_num(AVIN_POINTS_PER_QUESTION)}.", "Small", wrap=True))
        grid = QGridLayout()
        grid.setSpacing(6)
        grid.setContentsMargins(0, 8, 0, 4)
        styles = q_style()
        for i, q in enumerate(av.questions):
            fg, bg, sym = styles.get(q.state, styles[Q_BLANK])
            cell = label(f"{sym}  {q.number}. {q.answer}")
            cell.setAlignment(Qt.AlignCenter)
            cell.setMinimumWidth(78)
            cell.setStyleSheet(f"color:{fg};background:{bg};border-radius:8px;padding:6px 4px;font-weight:600;")
            cell.setToolTip(f"Questão {q.number}: {Q_LABELS.get(q.state, q.state)} (marcou {q.answer or '—'})")
            grid.addWidget(cell, i // 10, i % 10)
        b.addLayout(grid)
        legend = QHBoxLayout()
        for s in (Q_CORRECT, Q_WRONG):
            fg, bg, sym = q_style()[s]
            legend.addWidget(label(f"<span style='color:{fg}'>{sym}</span> {Q_LABELS[s]}", "Small"))
        legend.addStretch(1)
        b.addLayout(legend)

    def set_updating(self, running: bool) -> None:
        self.update_btn.setEnabled(not running)
        self.update_btn.setText("Atualizando notas…" if running else "Atualizar notas")
