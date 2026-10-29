"""Identidade visual: tokens de cor (modo claro e noturno), tipografia e folha de estilos Qt.

``COLORS``, ``URGENCY_STYLE`` e ``STATUS_COLORS`` são alterados no lugar quando o modo muda; por isso as telas devem
ler as cores na hora de montar os widgets (o conteúdo da janela é remontado ao trocar o modo).
"""

LIGHT = {
    "bg": "#F5F6F8",
    "surface": "#FFFFFF",
    "surface_alt": "#F8FAFC",
    "sidebar": "#FFFFFF",
    "text": "#0F172A",
    "text_2": "#334155",
    "muted": "#64748B",
    "subtle": "#94A3B8",
    "border": "#E2E8F0",
    "border_strong": "#CBD5E1",
    "primary": "#2563EB",
    "primary_hover": "#1D4ED8",
    "primary_soft": "#EFF6FF",
    "primary_text": "#1E40AF",
    "primary_border": "#BFDBFE",
    "primary_disabled": "#93C5FD",
    "on_primary": "#FFFFFF",
    "column": "#EEF1F5",
    "drop_bg": "#E0EAFF",
    "chip_on_bg": "#0F172A", "chip_on_text": "#FFFFFF",
    "toast_bg": "#0F172A", "toast_text": "#FFFFFF", "toast_link": "#93C5FD",
    "danger": "#DC2626", "danger_bg": "#FEF2F2", "danger_text": "#991B1B", "danger_border": "#FECACA",
    "warn": "#D97706", "warn_bg": "#FFFBEB", "warn_text": "#92400E", "warn_border": "#FDE68A",
    "ok": "#059669", "ok_bg": "#ECFDF5", "ok_text": "#065F46", "ok_border": "#A7F3D0",
    "info_bg": "#EFF6FF", "info_text": "#1E40AF", "info_border": "#BFDBFE",
    "neutral_bg": "#F1F5F9", "neutral_text": "#475569",
    "violet": "#7C3AED", "violet_bg": "#F3E8FF", "violet_text": "#6B21A8",
    "status_todo": "#94A3B8",
}

DARK = {
    "bg": "#0B1120",
    "surface": "#141C2B",
    "surface_alt": "#1A2436",
    "sidebar": "#101827",
    "text": "#E5E9F0",
    "text_2": "#CBD5E1",
    "muted": "#94A3B8",
    "subtle": "#6B7A90",
    "border": "#243045",
    "border_strong": "#33425B",
    "primary": "#3B82F6",
    "primary_hover": "#2563EB",
    "primary_soft": "#1B2A4A",
    "primary_text": "#A5C8FF",
    "primary_border": "#2C4A80",
    "primary_disabled": "#2B4675",
    "on_primary": "#FFFFFF",
    "column": "#101826",
    "drop_bg": "#1B2A4A",
    "chip_on_bg": "#E5E9F0", "chip_on_text": "#0B1120",
    "toast_bg": "#E5E9F0", "toast_text": "#0B1120", "toast_link": "#1D4ED8",
    "danger": "#F87171", "danger_bg": "#3A1A20", "danger_text": "#FCA5A5", "danger_border": "#5B2530",
    "warn": "#FBBF24", "warn_bg": "#352812", "warn_text": "#FCD34D", "warn_border": "#5A4317",
    "ok": "#34D399", "ok_bg": "#0F2C25", "ok_text": "#6EE7B7", "ok_border": "#1D4D40",
    "info_bg": "#1B2A4A", "info_text": "#A5C8FF", "info_border": "#2C4A80",
    "neutral_bg": "#1E293B", "neutral_text": "#CBD5E1",
    "violet": "#A78BFA", "violet_bg": "#2A1F45", "violet_text": "#D8B4FE",
    "status_todo": "#7C8BA1",
}

COLORS: dict[str, str] = dict(LIGHT)
URGENCY_STYLE: dict[str, tuple[str, str, str]] = {}   # urgência -> (texto, fundo, ícone)
STATUS_COLORS: dict[str, str] = {}
_state = {"dark": False}


def _derive() -> None:
    c = COLORS
    URGENCY_STYLE.clear()
    URGENCY_STYLE.update({
        "atrasada": (c["danger_text"], c["danger_bg"], "warning"),
        "urgente": (c["warn_text"], c["warn_bg"], "clock"),
        "semana": (c["primary_text"], c["primary_soft"], "calendar"),
        "depois": (c["neutral_text"], c["neutral_bg"], "calendar"),
        "sem_prazo": (c["neutral_text"], c["neutral_bg"], "calendar"),
        "concluida": (c["ok_text"], c["ok_bg"], "check"),
    })
    STATUS_COLORS.clear()
    STATUS_COLORS.update({"todo": c["status_todo"], "doing": c["primary"], "done": c["ok"]})


_derive()


def set_dark(dark: bool) -> None:
    """Troca a paleta no lugar (todos os módulos que importaram COLORS passam a ver as novas cores)."""
    _state["dark"] = bool(dark)
    COLORS.clear()
    COLORS.update(DARK if dark else LIGHT)
    _derive()


def is_dark() -> bool:
    return _state["dark"]


def build_style() -> str:
    C = COLORS
    return f"""
* {{ font-family: "Noto Sans", "Cantarell", "Ubuntu", "DejaVu Sans", sans-serif; font-size: 10pt; color: {C['text']}; }}
QMainWindow, QWidget#Page, QWidget#Content {{ background: {C['bg']}; }}
QDialog, QMessageBox {{ background: {C['bg']}; }}

/* barra lateral */
QWidget#Sidebar {{ background: {C['sidebar']}; border-right: 1px solid {C['border']}; }}
QLabel#Brand {{ font-size: 13pt; font-weight: 700; }}
QLabel#BrandSub {{ color: {C['muted']}; font-size: 8.5pt; }}
QPushButton#Nav {{ background: transparent; border: none; text-align: left; padding: 9px 12px; border-radius: 8px;
    color: {C['text_2']}; font-size: 10pt; }}
QPushButton#Nav:hover {{ background: {C['surface_alt']}; }}
QPushButton#Nav:checked {{ background: {C['primary_soft']}; color: {C['primary_text']}; font-weight: 600; }}
QFrame#SyncCard {{ background: {C['surface_alt']}; border: 1px solid {C['border']}; border-radius: 10px; }}
QFrame#ThemeRow {{ background: transparent; border-radius: 8px; }}
QFrame#ThemeRow:hover {{ background: {C['surface_alt']}; }}

/* tipografia */
QLabel#H1 {{ font-size: 19pt; font-weight: 700; }}
QLabel#H2 {{ font-size: 12.5pt; font-weight: 600; }}
QLabel#H3 {{ font-size: 10.5pt; font-weight: 600; }}
QLabel#Muted {{ color: {C['muted']}; }}
QLabel#Small {{ color: {C['muted']}; font-size: 8.5pt; }}
QLabel#Section {{ color: {C['muted']}; font-size: 8.5pt; font-weight: 700; letter-spacing: 0.5px; }}
QLabel {{ background: transparent; }}

/* superfícies */
QFrame#Panel {{ background: {C['surface']}; border: 1px solid {C['border']}; border-radius: 12px; }}
QFrame#Tile {{ background: {C['surface']}; border: 1px solid {C['border']}; border-radius: 12px; }}
QFrame#Tile:hover {{ border-color: {C['border_strong']}; background: {C['surface_alt']}; }}
QLabel#TileValue {{ font-size: 20pt; font-weight: 700; }}
QFrame#Row {{ background: transparent; border-radius: 8px; }}
QFrame#Row:hover {{ background: {C['surface_alt']}; }}

/* botões */
QPushButton {{ background: {C['surface']}; border: 1px solid {C['border']}; border-radius: 8px; padding: 7px 14px;
    color: {C['text_2']}; }}
QPushButton:hover {{ border-color: {C['border_strong']}; background: {C['surface_alt']}; }}
QPushButton:pressed {{ background: {C['border']}; }}
QPushButton:disabled {{ color: {C['subtle']}; background: {C['surface_alt']}; }}
QPushButton:focus {{ border-color: {C['primary']}; }}
QPushButton#Primary {{ background: {C['primary']}; color: {C['on_primary']}; border: none; font-weight: 600; padding: 8px 16px; }}
QPushButton#Primary:hover {{ background: {C['primary_hover']}; }}
QPushButton#Primary:disabled {{ background: {C['primary_disabled']}; color: {C['on_primary']}; }}
QPushButton#Danger {{ color: {C['danger']}; }}
QPushButton#Danger:hover {{ background: {C['danger_bg']}; border-color: {C['danger_border']}; }}
QPushButton#Ghost {{ background: transparent; border: none; padding: 6px 8px; color: {C['text_2']}; }}
QPushButton#Ghost:hover {{ background: {C['neutral_bg']}; }}
QPushButton#Link {{ background: transparent; border: none; padding: 2px 4px; color: {C['primary']}; font-weight: 600; }}
QPushButton#Link:hover {{ color: {C['primary_hover']}; text-decoration: underline; }}
QPushButton#Icon {{ background: transparent; border: none; border-radius: 6px; padding: 4px; }}
QPushButton#Icon:hover {{ background: {C['neutral_bg']}; }}
QPushButton#Chip {{ background: {C['surface']}; border: 1px solid {C['border']}; border-radius: 15px; padding: 5px 12px;
    color: {C['text_2']}; }}
QPushButton#Chip:hover {{ border-color: {C['border_strong']}; }}
QPushButton#Chip:checked {{ background: {C['chip_on_bg']}; border-color: {C['chip_on_bg']}; color: {C['chip_on_text']}; }}
QPushButton#Seg {{ border-radius: 0; padding: 6px 12px; }}
QPushButton#Seg:checked {{ background: {C['primary_soft']}; color: {C['primary_text']}; border-color: {C['primary_border']}; font-weight: 600; }}

/* campos */
QLineEdit, QComboBox, QDateTimeEdit, QDateEdit, QTimeEdit, QPlainTextEdit {{ background: {C['surface']};
    border: 1px solid {C['border']}; border-radius: 8px; padding: 7px 9px; selection-background-color: {C['primary']}; }}
QLineEdit:hover, QComboBox:hover, QDateTimeEdit:hover, QPlainTextEdit:hover {{ border-color: {C['border_strong']}; }}
QLineEdit:focus, QComboBox:focus, QDateTimeEdit:focus, QPlainTextEdit:focus {{ border: 1px solid {C['primary']}; }}
QLineEdit:disabled, QDateTimeEdit:disabled {{ background: {C['surface_alt']}; color: {C['subtle']}; }}
QComboBox::drop-down, QDateTimeEdit::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{ background: {C['surface']}; border: 1px solid {C['border']};
    selection-background-color: {C['primary_soft']}; selection-color: {C['text']}; padding: 4px; outline: none; }}
QCalendarWidget QWidget {{ alternate-background-color: {C['surface_alt']}; }}
QCalendarWidget QAbstractItemView {{ background: {C['surface']}; selection-background-color: {C['primary']};
    selection-color: {C['on_primary']}; }}
QCalendarWidget QToolButton {{ background: transparent; border: none; padding: 4px 8px; }}
QLabel#FieldLabel {{ color: {C['text_2']}; font-weight: 600; font-size: 9pt; }}

/* quadro de atividades */
QFrame#Column {{ background: {C['column']}; border-radius: 14px; }}
QFrame#Column[dropTarget="true"] {{ background: {C['drop_bg']}; border: 2px dashed {C['primary']}; }}
QLabel#ColumnTitle {{ font-weight: 700; font-size: 10.5pt; }}
QLabel#Count {{ background: {C['surface']}; border-radius: 9px; padding: 1px 8px; color: {C['muted']}; font-size: 8.5pt;
    font-weight: 600; }}
QFrame#KCard {{ background: {C['surface']}; border: 1px solid {C['border']}; border-radius: 10px; }}
QFrame#KCard:hover {{ border-color: {C['border_strong']}; }}
QFrame#KCard[selected="true"] {{ border: 2px solid {C['primary']}; }}
QLabel#CardTitle {{ font-weight: 600; font-size: 10pt; color: {C['text']}; }}
QLabel#Pill {{ border-radius: 9px; padding: 2px 8px; font-size: 8.5pt; font-weight: 600; }}

/* painel lateral (detalhes) */
QFrame#Drawer {{ background: {C['surface']}; border-left: 1px solid {C['border']}; }}

/* avisos */
QFrame#Banner {{ border-radius: 10px; }}
QFrame#Toast {{ background: {C['toast_bg']}; border-radius: 10px; }}
QFrame#Toast QLabel {{ color: {C['toast_text']}; }}
QFrame#Toast QPushButton {{ background: transparent; border: none; color: {C['toast_link']}; font-weight: 700; padding: 4px 6px; }}
QFrame#LoadingBar {{ background: {C['surface']}; border-bottom: 1px solid {C['border']}; }}

/* listas e tabelas */
QScrollArea {{ border: none; background: transparent; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QTableView {{ background: {C['surface']}; border: 1px solid {C['border']}; border-radius: 12px; gridline-color: transparent;
    selection-background-color: {C['primary_soft']}; selection-color: {C['text']}; }}
QTableView::item {{ padding: 6px 8px; border-bottom: 1px solid {C['neutral_bg']}; }}
QHeaderView::section {{ background: {C['surface']}; border: none; border-bottom: 1px solid {C['border']}; padding: 10px 8px;
    font-weight: 700; color: {C['muted']}; font-size: 8.5pt; }}
QListWidget {{ background: {C['surface']}; border: 1px solid {C['border']}; border-radius: 10px; padding: 4px; }}
QListWidget::item {{ padding: 8px; border-radius: 6px; }}
QListWidget::item:selected {{ background: {C['primary_soft']}; color: {C['text']}; }}
QProgressBar {{ border: none; background: {C['neutral_bg']}; border-radius: 3px; }}
QProgressBar::chunk {{ background: {C['primary']}; border-radius: 3px; }}
QCheckBox {{ spacing: 8px; color: {C['text_2']}; background: transparent; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border: 1.5px solid {C['subtle']}; border-radius: 4px; background: {C['surface']}; }}
QCheckBox::indicator:hover {{ border-color: {C['primary']}; }}
QCheckBox::indicator:checked {{ background: {C['primary']}; border-color: {C['primary']}; image: url(__CHECK__); }}
QCheckBox#Switch::indicator {{ width: 34px; height: 18px; border-radius: 9px; border: none; image: none;
    background: {C['border_strong']}; }}
QCheckBox#Switch::indicator:checked {{ background: {C['primary']}; image: url(__KNOB_ON__); }}
QCheckBox#Switch::indicator:unchecked {{ image: url(__KNOB_OFF__); }}
QToolTip {{ background: {C['toast_bg']}; color: {C['toast_text']}; border: none; padding: 6px 8px; border-radius: 6px; }}
QMenu {{ background: {C['surface']}; border: 1px solid {C['border']}; border-radius: 10px; padding: 5px; }}
QMenu::item {{ padding: 7px 22px 7px 12px; border-radius: 6px; }}
QMenu::item:selected {{ background: {C['primary_soft']}; color: {C['text']}; }}
QMenu::separator {{ height: 1px; background: {C['border']}; margin: 4px 6px; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {C['border_strong']}; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {C['subtle']}; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {C['border_strong']}; border-radius: 4px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
"""


def pill_css(fg: str, bg: str) -> str:
    return f"color:{fg};background:{bg};"


def apply_theme(app, dark: bool | None = None) -> None:
    """Paleta explícita (clara ou noturna): não depende do tema do sistema, então os diálogos ficam sempre legíveis."""
    from PySide6.QtGui import QColor, QPalette

    from app.config import resource_path
    if dark is not None:
        set_dark(dark)
    C = COLORS
    app.setStyle("Fusion")
    p = QPalette()
    roles = {QPalette.Window: C["bg"], QPalette.WindowText: C["text"], QPalette.Base: C["surface"],
             QPalette.AlternateBase: C["surface_alt"], QPalette.Text: C["text"], QPalette.Button: C["surface"],
             QPalette.ButtonText: C["text"], QPalette.Highlight: C["primary"], QPalette.HighlightedText: "#FFFFFF",
             QPalette.ToolTipBase: C["toast_bg"], QPalette.ToolTipText: C["toast_text"],
             QPalette.PlaceholderText: C["subtle"], QPalette.Link: C["primary"], QPalette.BrightText: C["text"]}
    for role, color in roles.items():
        p.setColor(role, QColor(color))
    p.setColor(QPalette.Disabled, QPalette.Text, QColor(C["subtle"]))
    p.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(C["subtle"]))
    app.setPalette(p)
    style = build_style().replace("__CHECK__", resource_path("assets/check.svg").as_posix())
    style = style.replace("__KNOB_ON__", resource_path("assets/knob_on.svg").as_posix())
    style = style.replace("__KNOB_OFF__", resource_path("assets/knob_off.svg").as_posix())
    app.setStyleSheet(style)
