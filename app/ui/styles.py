"""Sortify design system: colour tokens, typography, spacing, and QSS.

The visual language is built on three ideas:

* a layered smoky canvas that is always visible through frosted surfaces,
* translucent glass panels painted in code (real backdrop blur, not flat cards),
* a restrained palette of smoked grey, charcoal, silver, and muted sand.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.utils.resources import get_asset_path


@dataclass(frozen=True)
class ThemeTokens:
    name: str
    is_dark: bool

    # Canvas
    canvas: str
    canvas_top: str
    canvas_bottom: str
    aurora: tuple[tuple[float, float, float, str], ...]

    # Glass materials
    glass_tint: tuple[int, int, int, int]
    glass_tint_elevated: tuple[int, int, int, int]
    glass_tint_subtle: tuple[int, int, int, int]
    glass_tint_rail: tuple[int, int, int, int]
    glass_stroke: str
    glass_stroke_strong: str
    glass_highlight: str
    glass_shade: str

    # Typography
    text_primary: str
    text_secondary: str
    text_muted: str
    text_faint: str
    text_on_accent: str

    # Accents
    accent: str
    accent_hover: str
    accent_pressed: str
    accent_soft: str
    accent_border: str
    warm: str
    warm_soft: str

    # Controls
    input_bg: str
    input_bg_focus: str
    input_border: str
    row_hover: str
    row_selected: str
    header_bg: str
    scroll_handle: str

    # Semantic
    success_fg: str
    success_bg: str
    success_border: str
    warning_fg: str
    warning_bg: str
    warning_border: str
    danger_fg: str
    danger_bg: str
    danger_border: str
    info_fg: str
    info_bg: str
    info_border: str


DARK_TOKENS = ThemeTokens(
    name="Charcoal",
    is_dark=True,
    canvas="#0B0C0E",
    canvas_top="#121316",
    canvas_bottom="#060607",
    aurora=(
        (0.16, 0.08, 0.62, "#2A2D33"),
        (0.88, 0.12, 0.58, "#23262C"),
        (0.10, 0.92, 0.70, "#1B1D22"),
        (0.80, 0.78, 0.62, "#2B2A29"),
        (0.52, 0.46, 0.55, "#15171B"),
    ),
    glass_tint=(30, 32, 36, 176),
    glass_tint_elevated=(38, 41, 46, 206),
    glass_tint_subtle=(24, 26, 30, 128),
    glass_tint_rail=(18, 20, 23, 196),
    glass_stroke="rgba(200, 206, 214, 40)",
    glass_stroke_strong="rgba(214, 220, 228, 74)",
    glass_highlight="rgba(240, 243, 247, 50)",
    glass_shade="rgba(0, 0, 0, 100)",
    text_primary="#EEF0F3",
    text_secondary="#C3C8D0",
    text_muted="#8D949E",
    text_faint="#60666F",
    text_on_accent="#111214",
    accent="#C8CED6",
    accent_hover="#E2E6EC",
    accent_pressed="#A9B0BA",
    accent_soft="rgba(200, 206, 214, 30)",
    accent_border="rgba(200, 206, 214, 96)",
    warm="#C9B48E",
    warm_soft="rgba(201, 180, 142, 26)",
    input_bg="rgba(12, 13, 15, 170)",
    input_bg_focus="rgba(14, 15, 17, 214)",
    input_border="rgba(200, 206, 214, 46)",
    row_hover="rgba(220, 226, 234, 14)",
    row_selected="rgba(200, 206, 214, 30)",
    header_bg="rgba(16, 17, 19, 150)",
    scroll_handle="rgba(200, 206, 214, 60)",
    success_fg="#D5DBE2",
    success_bg="rgba(213, 219, 226, 18)",
    success_border="rgba(213, 219, 226, 66)",
    warning_fg="#D9B77E",
    warning_bg="rgba(217, 183, 126, 22)",
    warning_border="rgba(217, 183, 126, 66)",
    danger_fg="#E38B8B",
    danger_bg="rgba(227, 139, 139, 22)",
    danger_border="rgba(227, 139, 139, 66)",
    info_fg="#9FB7CC",
    info_bg="rgba(159, 183, 204, 22)",
    info_border="rgba(159, 183, 204, 64)",
)

LIGHT_TOKENS = ThemeTokens(
    name="Smoke",
    is_dark=False,
    canvas="#E9EAEC",
    canvas_top="#F4F5F6",
    canvas_bottom="#DADCE0",
    aurora=(
        (0.14, 0.06, 0.66, "#D5D8DD"),
        (0.90, 0.10, 0.58, "#CDD2D9"),
        (0.08, 0.94, 0.72, "#DEE0E4"),
        (0.84, 0.84, 0.64, "#E4DFD7"),
        (0.50, 0.44, 0.52, "#E2E4E8"),
    ),
    glass_tint=(255, 255, 255, 150),
    glass_tint_elevated=(255, 255, 255, 196),
    glass_tint_subtle=(255, 255, 255, 104),
    glass_tint_rail=(255, 255, 255, 170),
    glass_stroke="rgba(255, 255, 255, 200)",
    glass_stroke_strong="rgba(90, 96, 106, 74)",
    glass_highlight="rgba(255, 255, 255, 235)",
    glass_shade="rgba(30, 34, 40, 24)",
    text_primary="#16181C",
    text_secondary="#3D434C",
    text_muted="#666D78",
    text_faint="#8E949D",
    text_on_accent="#FFFFFF",
    accent="#3E4650",
    accent_hover="#2B3138",
    accent_pressed="#1E2328",
    accent_soft="rgba(62, 70, 80, 20)",
    accent_border="rgba(62, 70, 80, 70)",
    warm="#8A6E3F",
    warm_soft="rgba(138, 110, 63, 18)",
    input_bg="rgba(255, 255, 255, 200)",
    input_bg_focus="#FFFFFF",
    input_border="rgba(90, 96, 106, 70)",
    row_hover="rgba(40, 46, 56, 12)",
    row_selected="rgba(40, 46, 56, 26)",
    header_bg="rgba(255, 255, 255, 130)",
    scroll_handle="rgba(80, 86, 96, 80)",
    success_fg="#2F3B45",
    success_bg="rgba(47, 59, 69, 14)",
    success_border="rgba(47, 59, 69, 50)",
    warning_fg="#7A5A1E",
    warning_bg="rgba(122, 90, 30, 16)",
    warning_border="rgba(122, 90, 30, 52)",
    danger_fg="#A23B3B",
    danger_bg="rgba(162, 59, 59, 16)",
    danger_border="rgba(162, 59, 59, 52)",
    info_fg="#2F5873",
    info_bg="rgba(47, 88, 115, 14)",
    info_border="rgba(47, 88, 115, 50)",
)

FONT_STACK = '"Segoe UI Variable Text", "Segoe UI", "Inter", "SF Pro Text", system-ui, sans-serif'
DISPLAY_STACK = '"Segoe UI Variable Display", "Segoe UI Semibold", "Segoe UI", "Inter", sans-serif'

def get_tokens(dark_mode: bool = True) -> ThemeTokens:
    return DARK_TOKENS if dark_mode else LIGHT_TOKENS


def build_stylesheet(dark_mode: bool = True) -> str:
    t = get_tokens(dark_mode)
    check_asset = get_asset_path(
        "assets/checkmark-dark.svg" if dark_mode else "assets/checkmark-light.svg"
    )
    check_url = check_asset.as_posix().replace('"', '\\"')
    return f"""
* {{
    font-family: {FONT_STACK};
    font-size: 10pt;
    outline: none;
}}

QWidget {{
    color: {t.text_primary};
}}

QMainWindow, QDialog, QWidget#root, QWidget#page {{
    background: transparent;
    color: {t.text_primary};
}}

QLabel {{
    background: transparent;
}}

/* ---------- Typography ---------- */
QLabel#displayTitle {{
    font-family: {DISPLAY_STACK};
    font-size: 20pt;
    font-weight: 700;
    color: {t.text_primary};
}}

QLabel#pageTitle {{
    font-family: {DISPLAY_STACK};
    font-size: 15pt;
    font-weight: 700;
    color: {t.text_primary};
}}

QLabel#sectionTitle {{
    font-size: 10.5pt;
    font-weight: 700;
    color: {t.text_primary};
}}

QLabel#eyebrow {{
    color: {t.text_muted};
    font-size: 8pt;
    font-weight: 700;
}}

QLabel#muted {{
    color: {t.text_muted};
}}

QLabel#secondaryText {{
    color: {t.text_secondary};
}}

QLabel#finePrint {{
    color: {t.text_faint};
    font-size: 8.5pt;
}}

QLabel#brandName {{
    font-family: {DISPLAY_STACK};
    font-size: 14pt;
    font-weight: 700;
    color: {t.text_primary};
}}

QLabel#brandTag {{
    color: {t.text_faint};
    font-size: 7.5pt;
    font-weight: 600;
}}

QLabel#metricValue {{
    font-family: {DISPLAY_STACK};
    font-size: 19pt;
    font-weight: 700;
    color: {t.text_primary};
}}

QLabel#inspectorName {{
    font-size: 11.5pt;
    font-weight: 700;
    color: {t.text_primary};
}}

QLabel#emptyTitle {{
    font-family: {DISPLAY_STACK};
    font-size: 13pt;
    font-weight: 700;
    color: {t.text_primary};
}}

/* ---------- Glass frames (painted in code) ---------- */
QFrame#glassPanel, QFrame#elevatedPanel, QFrame#subtlePanel,
QFrame#sidebar, QFrame#inspectorPanel, QFrame#commandDeck,
QFrame#metricTile, QFrame#glassDialog {{
    background: transparent;
    border: none;
}}

/* ---------- Status badges ---------- */
QLabel#badgeReady, QLabel#badgeInfo, QLabel#badgeWarning, QLabel#badgeDanger, QLabel#badgeNeutral {{
    border-radius: 9px;
    padding: 3px 9px;
    font-size: 8pt;
    font-weight: 700;
}}
QLabel#badgeReady {{ background: {t.success_bg}; color: {t.success_fg}; border: 1px solid {t.success_border}; }}
QLabel#badgeInfo {{ background: {t.info_bg}; color: {t.info_fg}; border: 1px solid {t.info_border}; }}
QLabel#badgeWarning {{ background: {t.warning_bg}; color: {t.warning_fg}; border: 1px solid {t.warning_border}; }}
QLabel#badgeDanger {{ background: {t.danger_bg}; color: {t.danger_fg}; border: 1px solid {t.danger_border}; }}
QLabel#badgeNeutral {{ background: {t.accent_soft}; color: {t.text_secondary}; border: 1px solid {t.glass_stroke}; }}

/* ---------- Buttons ---------- */
QPushButton {{
    background: {t.input_bg};
    border: 1px solid {t.input_border};
    border-radius: 10px;
    padding: 8px 15px;
    color: {t.text_primary};
    font-weight: 600;
    min-height: 18px;
}}
QPushButton:hover {{
    background: {t.input_bg_focus};
    border-color: {t.accent_border};
}}
QPushButton:pressed {{
    background: {t.accent_soft};
}}
QPushButton:focus {{
    border: 1px solid {t.accent};
}}
QPushButton:disabled {{
    color: {t.text_faint};
    background: transparent;
    border-color: {t.input_border};
}}
QPushButton#primary {{
    background: {t.accent};
    color: {t.text_on_accent};
    border: 1px solid {t.accent_border};
    font-weight: 700;
    padding: 9px 18px;
}}
QPushButton#primary:hover {{ background: {t.accent_hover}; }}
QPushButton#primary:pressed {{ background: {t.accent_pressed}; }}
QPushButton#primary:disabled {{
    background: transparent;
    color: {t.text_faint};
    border-color: {t.input_border};
}}
QPushButton#danger {{
    background: {t.danger_bg};
    color: {t.danger_fg};
    border: 1px solid {t.danger_border};
}}
QPushButton#danger:hover {{ border-color: {t.danger_fg}; }}
QPushButton#ghost {{
    background: transparent;
    border: 1px solid transparent;
    padding: 7px 11px;
    color: {t.text_secondary};
}}
QPushButton#ghost:hover {{
    background: {t.row_hover};
    border-color: {t.input_border};
    color: {t.text_primary};
}}
QPushButton#iconButton {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 9px;
    padding: 6px;
    min-width: 20px;
}}
QPushButton#iconButton:hover {{
    background: {t.row_hover};
    border-color: {t.input_border};
}}
QPushButton#segLeft, QPushButton#segRight {{
    background: transparent;
    border: 1px solid {t.input_border};
    padding: 6px 12px;
    font-weight: 600;
    color: {t.text_muted};
}}
QPushButton#segLeft {{ border-top-right-radius: 0; border-bottom-right-radius: 0; }}
QPushButton#segRight {{ border-top-left-radius: 0; border-bottom-left-radius: 0; border-left: none; }}
QPushButton#segLeft:checked, QPushButton#segRight:checked {{
    background: {t.accent_soft};
    color: {t.text_primary};
    border-color: {t.accent_border};
}}
QPushButton#nav {{
    text-align: left;
    padding: 9px 12px;
    border: 1px solid transparent;
    border-radius: 11px;
    background: transparent;
    color: {t.text_secondary};
    font-weight: 600;
}}
QPushButton#nav:hover {{
    background: {t.row_hover};
    color: {t.text_primary};
}}
QPushButton#nav:checked {{
    color: {t.text_primary};
    background: {t.accent_soft};
    border-color: {t.accent_border};
    font-weight: 700;
}}

/* ---------- Inputs ---------- */
QLineEdit, QComboBox, QSpinBox, QPlainTextEdit, QTextEdit {{
    background: {t.input_bg};
    border: 1px solid {t.input_border};
    border-radius: 9px;
    padding: 7px 11px;
    color: {t.text_primary};
    selection-background-color: {t.accent};
    selection-color: {t.text_on_accent};
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QPlainTextEdit:focus, QTextEdit:focus {{
    background: {t.input_bg_focus};
    border: 1px solid {t.accent};
}}
QLineEdit:disabled, QComboBox:disabled {{
    color: {t.text_faint};
}}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
    background: {t.canvas_top};
    color: {t.text_primary};
    border: 1px solid {t.glass_stroke_strong};
    border-radius: 8px;
    selection-background-color: {t.accent_soft};
    selection-color: {t.text_primary};
    padding: 4px;
    outline: none;
}}
QPlainTextEdit {{
    font-family: "Cascadia Mono", "Consolas", {FONT_STACK};
    font-size: 9pt;
    line-height: 140%;
}}
QSpinBox::up-button, QSpinBox::down-button {{ width: 0px; border: none; }}

/* ---------- Tables & lists ---------- */
QTableWidget, QTreeWidget, QListWidget {{
    background: transparent;
    alternate-background-color: {t.row_hover};
    border: 1px solid {t.glass_stroke};
    border-radius: 12px;
    gridline-color: transparent;
    selection-background-color: {t.row_selected};
    selection-color: {t.text_primary};
    outline: none;
}}
QTableWidget::item {{
    padding: 7px 9px;
    border: none;
    border-bottom: 1px solid {t.glass_stroke};
}}
QTableWidget::item:hover {{ background: {t.row_hover}; }}
QTableWidget::item:selected {{ background: {t.row_selected}; }}
QHeaderView {{ background: transparent; }}
QHeaderView::section {{
    background: {t.header_bg};
    color: {t.text_muted};
    border: none;
    border-bottom: 1px solid {t.glass_stroke};
    padding: 8px 9px;
    font-weight: 700;
    font-size: 8.5pt;
}}
QTableCornerButton::section {{ background: {t.header_bg}; border: none; }}

/* ---------- Progress ---------- */
QProgressBar {{
    background: {t.input_bg};
    border: 1px solid {t.input_border};
    border-radius: 4px;
    min-height: 7px;
    max-height: 7px;
    text-align: center;
    color: transparent;
}}
QProgressBar::chunk {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {t.accent}, stop:0.6 {t.accent}, stop:1 {t.warm});
    border-radius: 3px;
}}

/* ---------- Checks ---------- */
QCheckBox {{
    spacing: 8px;
    color: {t.text_secondary};
    background: transparent;
}}
QCheckBox::indicator, QTableWidget::indicator {{
    width: 16px;
    height: 16px;
    border-radius: 5px;
    border: 1px solid {t.input_border};
    background: {t.input_bg};
}}
QCheckBox::indicator:hover, QTableWidget::indicator:hover {{ border-color: {t.accent}; }}
QCheckBox::indicator:checked, QTableWidget::indicator:checked {{
    background: {t.accent};
    border-color: {t.accent};
    image: url("{check_url}");
}}

/* ---------- Scrollbars ---------- */
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 3px 2px; }}
QScrollBar::handle:vertical {{ background: {t.scroll_handle}; min-height: 30px; border-radius: 4px; }}
QScrollBar::handle:vertical:hover {{ background: {t.text_faint}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px 3px; }}
QScrollBar::handle:horizontal {{ background: {t.scroll_handle}; min-width: 30px; border-radius: 4px; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0px; }}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background: transparent; }}

/* ---------- Misc ---------- */
QToolTip {{
    background: {t.canvas_top};
    color: {t.text_primary};
    border: 1px solid {t.glass_stroke_strong};
    border-radius: 7px;
    padding: 5px 9px;
}}
QSplitter::handle {{ background: transparent; width: 10px; }}
QSplitter::handle:hover {{ background: {t.accent_soft}; border-radius: 4px; }}
QTabBar {{
    background: transparent;
    qproperty-drawBase: 0;
}}
QTabWidget::pane {{
    border: 1px solid {t.glass_stroke};
    border-radius: 12px;
    background: transparent;
    top: -1px;
}}
QTabBar::tab {{
    background: transparent;
    color: {t.text_muted};
    border: 1px solid transparent;
    border-radius: 8px;
    padding: 7px 14px;
    margin-right: 4px;
    font-weight: 600;
}}
QTabBar::tab:selected {{
    background: {t.accent_soft};
    color: {t.text_primary};
    border-color: {t.accent_border};
}}
QTabBar::tab:hover {{ color: {t.text_primary}; }}
QStatusBar {{
    background: transparent;
    color: {t.text_faint};
    font-size: 8.5pt;
}}
QStatusBar::item {{ border: none; }}
QMenu {{
    background: {t.canvas_top};
    border: 1px solid {t.glass_stroke_strong};
    border-radius: 9px;
    padding: 6px;
    color: {t.text_primary};
}}
QMenu::item {{ padding: 6px 18px; border-radius: 6px; }}
QMenu::item:selected {{ background: {t.accent_soft}; }}
"""

