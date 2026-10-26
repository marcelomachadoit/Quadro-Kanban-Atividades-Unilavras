"""Identidade visual: tokens de cor, tipografia e folha de estilos Qt."""

COLORS = {
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
    "column": "#EEF1F5",
    "danger": "#DC2626", "danger_bg": "#FEF2F2", "danger_text": "#991B1B",
    "warn": "#D97706", "warn_bg": "#FFFBEB", "warn_text": "#92400E",
    "ok": "#059669", "ok_bg": "#ECFDF5", "ok_text": "#065F46",
    "info_bg": "#EFF6FF", "info_text": "#1E40AF",
    "neutral_bg": "#F1F5F9", "neutral_text": "#475569",
}

# urgência -> (texto, fundo, ícone)
URGENCY_STYLE = {
    "atrasada": (COLORS["danger_text"], COLORS["danger_bg"], "warning"),
    "urgente": (COLORS["warn_text"], COLORS["warn_bg"], "clock"),
    "semana": (COLORS["primary_text"], COLORS["primary_soft"], "calendar"),
    "depois": (COLORS["neutral_text"], COLORS["neutral_bg"], "calendar"),
    "sem_prazo": (COLORS["neutral_text"], COLORS["neutral_bg"], "calendar"),
    "concluida": (COLORS["ok_text"], COLORS["ok_bg"], "check"),
}

STATUS_COLORS = {"todo": "#94A3B8", "doing": COLORS["primary"], "done": COLORS["ok"]}

C = COLORS
STYLE = f"""
* {{ font-family: "Segoe UI Variable Text", "Segoe UI", sans-serif; font-size: 10pt; color: {C['text']}; }}
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

/* tipografia */
QLabel#H1 {{ font-size: 19pt; font-weight: 700; }}
QLabel#H2 {{ font-size: 12.5pt; font-weight: 600; }}
QLabel#H3 {{ font-size: 10.5pt; font-weight: 600; }}
QLabel#Muted {{ color: {C['muted']}; }}
QLabel#Small {{ color: {C['muted']}; font-size: 8.5pt; }}
QLabel#Section {{ color: {C['muted']}; font-size: 8.5pt; font-weight: 700; letter-spacing: 0.5px; }}

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
QPushButton#Primary {{ background: {C['primary']}; color: white; border: none; font-weight: 600; padding: 8px 16px; }}
QPushButton#Primary:hover {{ background: {C['primary_hover']}; }}
QPushButton#Primary:disabled {{ background: #93C5FD; color: white; }}
QPushButton#Danger {{ color: {C['danger']}; }}
QPushButton#Danger:hover {{ background: {C['danger_bg']}; border-color: #FECACA; }}
QPushButton#Ghost {{ background: transparent; border: none; padding: 6px 8px; color: {C['text_2']}; }}
QPushButton#Ghost:hover {{ background: {C['neutral_bg']}; }}
QPushButton#Link {{ background: transparent; border: none; padding: 2px 4px; color: {C['primary']}; font-weight: 600; }}
QPushButton#Link:hover {{ color: {C['primary_hover']}; text-decoration: underline; }}
QPushButton#Icon {{ background: transparent; border: none; border-radius: 6px; padding: 4px; }}
QPushButton#Icon:hover {{ background: {C['neutral_bg']}; }}
QPushButton#Chip {{ background: {C['surface']}; border: 1px solid {C['border']}; border-radius: 15px; padding: 5px 12px;
    color: {C['text_2']}; }}
QPushButton#Chip:hover {{ border-color: {C['border_strong']}; }}
QPushButton#Chip:checked {{ background: {C['text']}; border-color: {C['text']}; color: white; }}
QPushButton#Seg {{ border-radius: 0; padding: 6px 12px; }}
QPushButton#Seg:checked {{ background: {C['primary_soft']}; color: {C['primary_text']}; border-color: #BFDBFE; font-weight: 600; }}

/* campos */
QLineEdit, QComboBox, QDateTimeEdit, QPlainTextEdit {{ background: white; border: 1px solid {C['border']};
    border-radius: 8px; padding: 7px 9px; selection-background-color: {C['primary']}; }}
QLineEdit:hover, QComboBox:hover, QDateTimeEdit:hover, QPlainTextEdit:hover {{ border-color: {C['border_strong']}; }}
QLineEdit:focus, QComboBox:focus, QDateTimeEdit:focus, QPlainTextEdit:focus {{ border: 1px solid {C['primary']}; }}
QLineEdit:disabled, QDateTimeEdit:disabled {{ background: {C['surface_alt']}; color: {C['subtle']}; }}
QComboBox::drop-down, QDateTimeEdit::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{ background: white; border: 1px solid {C['border']}; selection-background-color: {C['primary_soft']};
    selection-color: {C['text']}; padding: 4px; outline: none; }}
QLabel#FieldLabel {{ color: {C['text_2']}; font-weight: 600; font-size: 9pt; }}

/* kanban */
QFrame#Column {{ background: {C['column']}; border-radius: 14px; }}
QFrame#Column[dropTarget="true"] {{ background: #E0EAFF; border: 2px dashed {C['primary']}; }}
QLabel#ColumnTitle {{ font-weight: 700; font-size: 10.5pt; }}
QLabel#Count {{ background: white; border-radius: 9px; padding: 1px 8px; color: {C['muted']}; font-size: 8.5pt;
    font-weight: 600; }}
QFrame#KCard {{ background: white; border: 1px solid {C['border']}; border-radius: 10px; }}
QFrame#KCard:hover {{ border-color: {C['border_strong']}; }}
QFrame#KCard[selected="true"] {{ border: 2px solid {C['primary']}; }}
QLabel#CardTitle {{ font-weight: 600; font-size: 10pt; color: {C['text']}; }}
QLabel#Pill {{ border-radius: 9px; padding: 2px 8px; font-size: 8.5pt; font-weight: 600; }}

/* painel lateral (detalhes) */
QFrame#Drawer {{ background: white; border-left: 1px solid {C['border']}; }}

/* avisos */
QFrame#Banner {{ border-radius: 10px; }}
QFrame#Toast {{ background: {C['text']}; border-radius: 10px; }}
QFrame#Toast QLabel {{ color: white; }}
QFrame#Toast QPushButton {{ background: transparent; border: none; color: #93C5FD; font-weight: 700; padding: 4px 6px; }}
QFrame#LoadingBar {{ background: white; border-bottom: 1px solid {C['border']}; }}

/* listas e tabelas */
QScrollArea {{ border: none; background: transparent; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QTableView {{ background: white; border: 1px solid {C['border']}; border-radius: 12px; gridline-color: transparent;
    selection-background-color: {C['primary_soft']}; selection-color: {C['text']}; }}
QTableView::item {{ padding: 6px 8px; border-bottom: 1px solid {C['neutral_bg']}; }}
QHeaderView::section {{ background: white; border: none; border-bottom: 1px solid {C['border']}; padding: 10px 8px;
    font-weight: 700; color: {C['muted']}; font-size: 8.5pt; }}
QListWidget {{ background: white; border: 1px solid {C['border']}; border-radius: 10px; padding: 4px; }}
QListWidget::item {{ padding: 8px; border-radius: 6px; }}
QListWidget::item:selected {{ background: {C['primary_soft']}; color: {C['text']}; }}
QProgressBar {{ border: none; background: {C['neutral_bg']}; border-radius: 3px; }}
QProgressBar::chunk {{ background: {C['primary']}; border-radius: 3px; }}
QCheckBox {{ spacing: 8px; color: {C['text_2']}; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border: 1.5px solid {C['subtle']}; border-radius: 4px; background: white; }}
QCheckBox::indicator:hover {{ border-color: {C['primary']}; }}
QCheckBox::indicator:checked {{ background: {C['primary']}; border-color: {C['primary']}; image: url(__CHECK__); }}
QToolTip {{ background: {C['text']}; color: white; border: none; padding: 6px 8px; border-radius: 6px; }}
QMenu {{ background: white; border: 1px solid {C['border']}; border-radius: 10px; padding: 5px; }}
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


def apply_theme(app) -> None:
    """Paleta clara explícita: evita que o modo escuro do Windows deixe diálogos ilegíveis."""
    from PySide6.QtGui import QColor, QPalette

    from app.config import resource_path
    app.setStyle("Fusion")
    p = QPalette()
    roles = {QPalette.Window: C["bg"], QPalette.WindowText: C["text"], QPalette.Base: "#FFFFFF",
             QPalette.AlternateBase: C["surface_alt"], QPalette.Text: C["text"], QPalette.Button: "#FFFFFF",
             QPalette.ButtonText: C["text"], QPalette.Highlight: C["primary"], QPalette.HighlightedText: "#FFFFFF",
             QPalette.ToolTipBase: C["text"], QPalette.ToolTipText: "#FFFFFF", QPalette.PlaceholderText: C["subtle"],
             QPalette.Link: C["primary"]}
    for role, color in roles.items():
        p.setColor(role, QColor(color))
    p.setColor(QPalette.Disabled, QPalette.Text, QColor(C["subtle"]))
    p.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(C["subtle"]))
    app.setPalette(p)
    app.setStyleSheet(STYLE.replace("__CHECK__", resource_path("assets/check.svg").as_posix()))
