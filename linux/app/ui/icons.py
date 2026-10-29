"""Ícones da fonte Material Icons Outlined (Apache 2.0), embutida em assets/fonts: as fontes Segoe do Windows
não existem no Linux e não podem ser redistribuídas."""
from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QIcon, QPainter, QPixmap

GLYPHS = {
    "home": "", "board": "", "settings": "", "sync": "", "add": "",
    "search": "", "delete": "", "edit": "", "open": "", "check": "",
    "more": "", "filter": "", "clock": "", "calendar": "", "info": "",
    "warning": "", "list": "", "close": "", "eye": "", "eye_off": "",
    "save": "", "trophy": "", "restore": "", "download": "", "upload": "",
    "folder": "", "lock": "", "user": "", "chevron_down": "", "chevron_right": "", "chevron_left": "",
    "circle": "", "check_circle": "", "help": "", "globe": "", "error": "",
    "trash": "", "star": "", "education": "",
    "moon": "", "sun": "", "event": "", "agenda": "", "pin": "",
    "mail": "",
}

ICON_FONT = "assets/fonts/MaterialIconsOutlined-Regular.otf"


@lru_cache(maxsize=1)
def icon_family() -> str:
    from app.config import resource_path
    fid = QFontDatabase.addApplicationFont(str(resource_path(ICON_FONT)))
    fams = QFontDatabase.applicationFontFamilies(fid) if fid >= 0 else []
    return fams[0] if fams else ""


def glyph(name: str) -> str:
    return GLYPHS.get(name, "")


def icon_font(px: int = 14) -> QFont:
    f = QFont(icon_family())
    f.setPixelSize(px)
    return f


@lru_cache(maxsize=256)
def icon(name: str, color: str = "#334155", size: int = 16) -> QIcon:
    pm = QPixmap(size * 2, size * 2)
    pm.setDevicePixelRatio(2.0)
    pm.fill(Qt.transparent)
    if name == "dot":
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(color))
        d = size * 0.62
        p.drawEllipse(QRectF((size - d) / 2, (size - d) / 2, d, d))
        p.end()
    elif icon_family() and name in GLYPHS:
        p = QPainter(pm)
        p.setRenderHint(QPainter.TextAntialiasing)
        p.setPen(QColor(color))
        p.setFont(icon_font(int(size * 0.85)))
        p.drawText(QRectF(0, 0, size, size), Qt.AlignCenter, GLYPHS[name])
        p.end()
    return QIcon(pm)


def glyph_css(px: int, color: str) -> str:
    """CSS para rótulos com glifo: a folha de estilos global sobrescreve setFont, então a fonte vai no CSS."""
    return f"font-family:'{icon_family()}'; font-size:{px}px; color:{color}; background:transparent;"
