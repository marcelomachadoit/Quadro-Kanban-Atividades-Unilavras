"""Componentes reutilizáveis: notificação (toast), faixa de aviso, barra de carregamento, pílulas e estados vazios."""
from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, Qt, QTimer, Signal
from PySide6.QtWidgets import (QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QProgressBar, QPushButton,
                               QSizePolicy, QVBoxLayout, QWidget)

from app.ui.icons import glyph, glyph_css, icon, icon_font
from app.ui.theme import COLORS, pill_css


def label(text: str = "", obj: str = "", wrap: bool = False) -> QLabel:
    lb = QLabel(text)
    if obj:
        lb.setObjectName(obj)
    lb.setWordWrap(wrap)
    return lb


def icon_label(name: str, color: str = COLORS["muted"], px: int = 14) -> QLabel:
    lb = QLabel(glyph(name))
    lb.setStyleSheet(glyph_css(px, color))
    lb.setFixedWidth(px + 4)
    lb.setAlignment(Qt.AlignCenter)
    return lb


def button(text: str, obj: str = "", icon_name: str = "", icon_color: Optional[str] = None,
           tip: str = "", on_click: Optional[Callable] = None) -> QPushButton:
    b = QPushButton(text)
    if obj:
        b.setObjectName(obj)
    if icon_name:
        color = icon_color or ("#FFFFFF" if obj == "Primary" else COLORS["text_2"])
        b.setIcon(icon(icon_name, color))
    if tip:
        b.setToolTip(tip)
    b.setCursor(Qt.PointingHandCursor)
    if on_click:
        b.clicked.connect(on_click)
    return b


def icon_button(name: str, tip: str, on_click: Optional[Callable] = None, color: str = COLORS["muted"],
                size: int = 16) -> QPushButton:
    b = QPushButton()
    b.setObjectName("Icon")
    b.setIcon(icon(name, color, size))
    b.setToolTip(tip)
    b.setAccessibleName(tip)
    b.setCursor(Qt.PointingHandCursor)
    b.setFixedSize(size + 12, size + 12)
    if on_click:
        b.clicked.connect(on_click)
    return b


class Pill(QLabel):
    def __init__(self, text: str, fg: str, bg: str, icon_name: str = "", tip: str = ""):
        super().__init__()
        self.setObjectName("Pill")
        g = glyph(icon_name) if icon_name else ""
        if g:
            # glifo na fonte de ícones + texto na fonte normal
            self.setTextFormat(Qt.RichText)
            fam = icon_font().family()
            self.setText(f"<span style=\"font-family:'{fam}';font-size:8pt\">{g}</span>&nbsp; {text}")
        else:
            self.setText(text)
        self.setStyleSheet(pill_css(fg, bg))
        self.setAccessibleName(text)
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        if tip:
            self.setToolTip(tip)


class Dot(QLabel):
    def __init__(self, color: str, size: int = 8):
        super().__init__()
        self.setFixedSize(size, size)
        self.setStyleSheet(f"background:{color};border-radius:{size // 2}px;")


class EmptyState(QWidget):
    def __init__(self, icon_name: str, title: str, text: str = "", action: Optional[QPushButton] = None):
        super().__init__()
        v = QVBoxLayout(self)
        v.setContentsMargins(16, 28, 16, 28)
        v.setSpacing(6)
        v.setAlignment(Qt.AlignCenter)
        ic = icon_label(icon_name, COLORS["subtle"], 28)
        ic.setFixedWidth(40)
        v.addWidget(ic, 0, Qt.AlignHCenter)
        t = label(title, "H3")
        t.setAlignment(Qt.AlignCenter)
        v.addWidget(t)
        if text:
            s = label(text, "Muted", wrap=True)
            s.setAlignment(Qt.AlignCenter)
            v.addWidget(s)
        if action:
            v.addSpacing(6)
            v.addWidget(action, 0, Qt.AlignHCenter)


# ---------------------------------------------------------------------- faixa de aviso (erros persistentes)

class Banner(QFrame):
    """Aviso persistente no topo do conteúdo, com até duas ações."""

    KINDS = {
        "error": (COLORS["danger_bg"], COLORS["danger_text"], "#FECACA", "error"),
        "warn": (COLORS["warn_bg"], COLORS["warn_text"], "#FDE68A", "warning"),
        "info": (COLORS["info_bg"], COLORS["info_text"], "#BFDBFE", "info"),
        "ok": (COLORS["ok_bg"], COLORS["ok_text"], "#A7F3D0", "check_circle"),
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Banner")
        self.lay = QHBoxLayout(self)
        self.lay.setContentsMargins(14, 10, 10, 10)
        self.lay.setSpacing(10)
        self.ic = QLabel()
        self.ic.setAlignment(Qt.AlignTop)
        texts = QVBoxLayout()
        texts.setSpacing(2)
        self.title = label("", "H3")
        self.text = label("", wrap=True)
        texts.addWidget(self.title)
        texts.addWidget(self.text)
        self.actions = QHBoxLayout()
        self.actions.setSpacing(6)
        self.close_btn = icon_button("close", "Fechar aviso", self.hide, size=12)
        self.lay.addWidget(self.ic)
        self.lay.addLayout(texts, 1)
        self.lay.addLayout(self.actions)
        self.lay.addWidget(self.close_btn, 0, Qt.AlignTop)
        self.hide()

    def show_message(self, kind: str, title: str, text: str = "",
                     actions: tuple[tuple[str, Callable], ...] = ()) -> None:
        bg, fg, border, ic = self.KINDS[kind]
        self.setStyleSheet(f"QFrame#Banner {{ background:{bg}; border:1px solid {border}; }}"
                           f"QFrame#Banner QLabel {{ color:{fg}; background: transparent; }}")
        self.ic.setText(glyph(ic))
        self.ic.setStyleSheet(glyph_css(16, fg))
        self.title.setText(title)
        self.text.setText(text)
        self.text.setVisible(bool(text))
        while self.actions.count():
            w = self.actions.takeAt(0).widget()
            if w:
                w.deleteLater()
        for i, (txt, fn) in enumerate(actions):
            b = button(txt, "Primary" if i == 0 else "", on_click=fn)
            self.actions.addWidget(b, 0, Qt.AlignVCenter)
        self.show()


# ---------------------------------------------------------------------- notificação temporária

class Toast(QFrame):
    """Notificação discreta no rodapé, some sozinha; pode ter uma ação (ex.: "Desfazer", "Ver resumo")."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("Toast")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 10, 10, 10)
        lay.setSpacing(12)
        self.ic = QLabel()
        self.msg = QLabel()
        self.action = QPushButton()
        self.action.setCursor(Qt.PointingHandCursor)
        self.action.clicked.connect(self._on_action)
        lay.addWidget(self.ic)
        lay.addWidget(self.msg)
        lay.addWidget(self.action)
        self._fn: Optional[Callable] = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._fade_out)
        self._effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._effect)
        self._anim = QPropertyAnimation(self._effect, b"opacity", self)
        self._anim.setDuration(180)
        self._anim.finished.connect(lambda: self.hide() if self._effect.opacity() < 0.05 else None)
        self.hide()

    def show_message(self, text: str, action_text: str = "", action: Optional[Callable] = None,
                     icon_name: str = "check_circle", ms: int = 5000) -> None:
        self.ic.setText(glyph(icon_name))
        self.ic.setStyleSheet(glyph_css(14, "#86EFAC" if icon_name == "check_circle" else
                                        ("#FCA5A5" if icon_name in ("error", "warning") else "#93C5FD")))
        self.msg.setText(text)
        self._fn = action
        self.action.setText(action_text)
        self.action.setVisible(bool(action_text))
        self.adjustSize()
        self.reposition()
        self._anim.stop()
        self._effect.setOpacity(1.0)
        self.show()
        self.raise_()
        self._timer.start(ms)

    def reposition(self) -> None:
        p = self.parentWidget()
        if p:
            self.adjustSize()
            self.move(QPoint((p.width() - self.width()) // 2, p.height() - self.height() - 24))

    def _on_action(self) -> None:
        fn = self._fn
        self.hide()
        if fn:
            fn()

    def _fade_out(self) -> None:
        self._anim.setStartValue(1.0)
        self._anim.setEndValue(0.0)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.start()


# ---------------------------------------------------------------------- barra de carregamento

class LoadingBar(QFrame):
    """Barra discreta "Carregando dados…" exibida no topo da janela durante a atualização."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("LoadingBar")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(28, 10, 20, 10)
        lay.setSpacing(14)
        self.spinner = icon_label("sync", COLORS["primary"], 16)
        texts = QVBoxLayout()
        texts.setSpacing(0)
        self.title = label("Carregando dados do portal…", "H3")
        self.detail = label("Conectando", "Small")
        texts.addWidget(self.title)
        texts.addWidget(self.detail)
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(6)
        self.bar.setRange(0, 0)
        self.cancel_btn = button("Interromper", "Ghost", "close")
        lay.addWidget(self.spinner)
        lay.addLayout(texts, 2)
        lay.addWidget(self.bar, 3)
        lay.addWidget(self.cancel_btn)
        self.manual = label("", wrap=True)
        self.manual.setStyleSheet(f"background:{COLORS['info_bg']};color:{COLORS['info_text']};border-radius:8px;"
                                  "padding:8px;")
        self.manual.hide()
        lay.addWidget(self.manual, 3)
        self.hide()

    def start(self, title: str = "Carregando dados do portal…") -> None:
        self.title.setText(title)
        self.bar.setRange(0, 0)
        self.detail.setText("Conectando ao portal")
        self.cancel_btn.setEnabled(True)
        self.cancel_btn.setText("Interromper")
        self.manual.hide()
        self.show()

    def set_progress(self, p) -> None:
        parts = [p.step]
        if p.course:
            from app.ui.format import short_course
            parts.append(short_course(p.course))
        if p.courses_total:
            parts.append(f"{p.courses_done}/{p.courses_total} disciplinas · {p.activities_found} atividades")
            self.bar.setRange(0, p.courses_total)
            self.bar.setValue(p.courses_done)
        self.detail.setText("  ·  ".join(x for x in parts if x))
        self.manual.setText(p.manual_message or "")
        self.manual.setVisible(bool(p.manual_message))

    def set_cancelling(self) -> None:
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.setText("Interrompendo…")


class Divider(QFrame):
    def __init__(self):
        super().__init__()
        self.setFixedHeight(1)
        self.setStyleSheet(f"background:{COLORS['border']};")


def clear_layout(layout) -> None:
    """Esvazia um layout escondendo os widgets na hora (deleteLater sozinho deixa "fantasmas" na tela)."""
    while layout.count():
        it = layout.takeAt(0)
        w = it.widget()
        if w is not None:
            w.hide()
            w.setParent(None)
            w.deleteLater()
        elif it.layout() is not None:
            clear_layout(it.layout())


class NotificationCard(QFrame):
    """Cartão de notificação fixo no canto inferior direito enquanto uma tarefa automática roda."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("NotificationCard")
        self.setStyleSheet(f"QFrame#NotificationCard {{ background:white; border:1px solid {COLORS['border']};"
                           f" border-left:4px solid {COLORS['primary']}; border-radius:12px; }}"
                           "QFrame#NotificationCard QLabel { background: transparent; border: none; }")
        self.setFixedWidth(380)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 12, 12, 12)
        lay.setSpacing(12)
        self.ic = icon_label("sync", COLORS["primary"], 20)
        lay.addWidget(self.ic, 0, Qt.AlignTop)
        v = QVBoxLayout()
        v.setSpacing(2)
        self.title = label("", "H3", wrap=True)
        self.detail = label("", "Small", wrap=True)
        self.hint = label("Você pode continuar usando o aplicativo.", "Small", wrap=True)
        v.addWidget(self.title)
        v.addWidget(self.detail)
        v.addWidget(self.hint)
        lay.addLayout(v, 1)
        self.cancel_btn = icon_button("close", "Interromper", size=12)
        lay.addWidget(self.cancel_btn, 0, Qt.AlignTop)
        try:
            from PySide6.QtWidgets import QGraphicsDropShadowEffect
            from PySide6.QtGui import QColor
            sh = QGraphicsDropShadowEffect(self)
            sh.setBlurRadius(28)
            sh.setOffset(0, 6)
            sh.setColor(QColor(15, 23, 42, 40))
            self.setGraphicsEffect(sh)
        except Exception:  # noqa: BLE001
            pass
        self.hide()

    def show_message(self, title: str, detail: str = "") -> None:
        self.title.setText(title)
        self.detail.setText(detail)
        self.detail.setVisible(bool(detail))
        self.adjustSize()
        self.reposition()
        self.show()
        self.raise_()

    def set_detail(self, detail: str) -> None:
        self.detail.setText(detail)
        self.detail.setVisible(bool(detail))
        self.adjustSize()
        self.reposition()

    def reposition(self) -> None:
        p = self.parentWidget()
        if p:
            self.adjustSize()
            self.move(p.width() - self.width() - 24, p.height() - self.height() - 24)
