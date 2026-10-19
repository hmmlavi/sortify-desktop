"""Crisp vector iconography and the Sortify brand mark."""

from __future__ import annotations

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QImage, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from app.models.file_record import IMAGE_EXTENSIONS
from app.utils.resources import get_asset_path

BRAND_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" fill="none">
  <defs>
    <linearGradient id="t" x1="6" y1="4" x2="58" y2="60" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="#122528"/><stop offset="0.55" stop-color="#0B1417"/><stop offset="1" stop-color="#070D0F"/>
    </linearGradient>
    <linearGradient id="rt" x1="13" y1="20" x2="51" y2="20" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="#7FE3DA"/><stop offset="1" stop-color="#B8F3EC"/>
    </linearGradient>
    <linearGradient id="rm" x1="13" y1="32" x2="51" y2="32" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="#CFE6E3"/><stop offset="1" stop-color="#F3FBFA"/>
    </linearGradient>
    <linearGradient id="rl" x1="13" y1="43" x2="51" y2="43" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="#C9A874"/><stop offset="1" stop-color="#EBD6AE"/>
    </linearGradient>
  </defs>
  <rect x="2.5" y="2.5" width="59" height="59" rx="17.5" fill="url(#t)"/>
  <rect x="3.3" y="3.3" width="57.4" height="57.4" rx="16.8" stroke="#8FE0D7" stroke-opacity="0.40" stroke-width="1.4"/>
  <path d="M19 4.4H45C50.4 4.4 54.8 7.2 56.7 11.6" stroke="#E9FFFC" stroke-opacity="0.30" stroke-width="1" stroke-linecap="round"/>
  <path d="M13.5 20.5C18.2 13.6 23.4 27.4 28.2 20.5C31.2 16.4 33.8 19.4 36 20.5L50.5 20.5" stroke="url(#rt)" stroke-width="4.2" stroke-linecap="round" stroke-linejoin="round"/>
  <path d="M13.5 32C19.2 24.8 24.4 39.2 30.4 32C33.2 28.6 35.2 31.3 37 32L50.5 32" stroke="url(#rm)" stroke-width="4.2" stroke-linecap="round" stroke-linejoin="round"/>
  <path d="M13.5 43.5C18.2 37.6 23.4 50.4 28.2 43.5C31.2 39.4 33.8 42.4 36 43.5L50.5 43.5" stroke="url(#rl)" stroke-width="4.2" stroke-linecap="round" stroke-linejoin="round"/>
  <circle cx="51.2" cy="32" r="2.55" fill="#F4DFBC"/>
</svg>"""

ICON_PATHS: dict[str, str] = {
    "workspace": (
        '<rect x="3" y="3" width="7.5" height="7.5" rx="2"/>'
        '<rect x="13.5" y="3" width="7.5" height="7.5" rx="2"/>'
        '<rect x="3" y="13.5" width="7.5" height="7.5" rx="2"/>'
        '<rect x="13.5" y="13.5" width="7.5" height="7.5" rx="2"/>'
    ),
    "review": (
        '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>'
        '<polyline points="14 2 14 8 20 8"/>'
        '<path d="m9 15 2 2 4-4"/>'
    ),
    "history": (
        '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/>'
        '<path d="M3 3v5h5"/>'
        '<path d="M12 7v5l4 2"/>'
    ),
    "settings": (
        '<circle cx="12" cy="12" r="3"/>'
        '<path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06'
        'a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09'
        'A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06'
        'a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09'
        'A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06'
        'a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09'
        'a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06'
        'a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09'
        'a1.65 1.65 0 0 0-1.51 1z"/>'
    ),
    "folder": (
        '<path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>'
    ),
    "folder_open": (
        '<path d="m6 14 1.5-2.9A2 2 0 0 1 9.24 10H20a2 2 0 0 1 1.94 2.5l-1.54 6a2 2 0 0 1-1.95 1.5H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h3.9a2 2 0 0 1 1.69.9l.81 1.2a2 2 0 0 0 1.67.9H18a2 2 0 0 1 2 2v2"/>'
    ),
    "scan": (
        '<path d="M3 7V5a2 2 0 0 1 2-2h2"/>'
        '<path d="M17 3h2a2 2 0 0 1 2 2v2"/>'
        '<path d="M21 17v2a2 2 0 0 1-2 2h-2"/>'
        '<path d="M7 21H5a2 2 0 0 1-2-2v-2"/>'
        '<line x1="7" y1="12" x2="17" y2="12"/>'
    ),
    "sparkles": (
        '<path d="m12 3-1.9 5.8a2 2 0 0 1-1.3 1.3L3 12l5.8 1.9a2 2 0 0 1 1.3 1.3L12 21l1.9-5.8a2 2 0 0 1 1.3-1.3L21 12l-5.8-1.9a2 2 0 0 1-1.3-1.3Z"/>'
        '<path d="M5 3v4"/><path d="M3 5h4"/><path d="M19 17v4"/><path d="M17 19h4"/>'
    ),
    "cpu": (
        '<rect x="4" y="4" width="16" height="16" rx="2"/>'
        '<rect x="9" y="9" width="6" height="6"/>'
        '<path d="M9 1v3"/><path d="M15 1v3"/><path d="M9 20v3"/><path d="M15 20v3"/>'
        '<path d="M20 9h3"/><path d="M20 14h3"/><path d="M1 9h3"/><path d="M1 14h3"/>'
    ),
    "check": '<polyline points="20 6 9 17 4 12"/>',
    "check_circle": (
        '<path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>'
        '<polyline points="22 4 12 14.01 9 11.01"/>'
    ),
    "warning": (
        '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/>'
        '<line x1="12" y1="9" x2="12" y2="13"/>'
        '<line x1="12" y1="17" x2="12.01" y2="17"/>'
    ),
    "error": (
        '<circle cx="12" cy="12" r="10"/>'
        '<line x1="15" y1="9" x2="9" y2="15"/>'
        '<line x1="9" y1="9" x2="15" y2="15"/>'
    ),
    "info": (
        '<circle cx="12" cy="12" r="10"/>'
        '<line x1="12" y1="16" x2="12" y2="12"/>'
        '<line x1="12" y1="8" x2="12.01" y2="8"/>'
    ),
    "search": (
        '<circle cx="11" cy="11" r="8"/>'
        '<line x1="21" y1="21" x2="16.65" y2="16.65"/>'
    ),
    "filter": '<polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/>',
    "undo": (
        '<path d="M3 7v6h6"/>'
        '<path d="M21 17a9 9 0 0 0-9-9 9 9 0 0 0-6 2.3L3 13"/>'
    ),
    "trash": (
        '<polyline points="3 6 5 6 21 6"/>'
        '<path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>'
    ),
    "eye": (
        '<path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"/>'
        '<circle cx="12" cy="12" r="3"/>'
    ),
    "edit": (
        '<path d="M12 20h9"/>'
        '<path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z"/>'
    ),
    "sun": (
        '<circle cx="12" cy="12" r="4"/>'
        '<path d="M12 2v2"/><path d="M12 20v2"/>'
        '<path d="m4.93 4.93 1.41 1.41"/><path d="m17.66 17.66 1.41 1.41"/>'
        '<path d="M2 12h2"/><path d="M20 12h2"/>'
        '<path d="m6.34 17.66-1.41 1.41"/><path d="m19.07 4.93-1.41 1.41"/>'
    ),
    "moon": '<path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/>',
    "shield": '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
    "close": '<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>',
    "refresh": (
        '<path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/>'
        '<path d="M3 3v5h5"/>'
        '<path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16"/>'
        '<path d="M16 16h5v5"/>'
    ),
    "arrow_right": '<line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/>',
    "chevron_right": '<polyline points="9 18 15 12 9 6"/>',
    "arrow_up_right": '<line x1="7" y1="17" x2="17" y2="7"/><polyline points="7 7 17 7 17 17"/>',
    "layers": (
        '<polygon points="12 2 2 7 12 12 22 7 12 2"/>'
        '<polyline points="2 17 12 22 22 17"/>'
        '<polyline points="2 12 12 17 22 12"/>'
    ),
    "clock": '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>',
    "sliders": (
        '<line x1="4" y1="21" x2="4" y2="14"/><line x1="4" y1="10" x2="4" y2="3"/>'
        '<line x1="12" y1="21" x2="12" y2="12"/><line x1="12" y1="8" x2="12" y2="3"/>'
        '<line x1="20" y1="21" x2="20" y2="16"/><line x1="20" y1="12" x2="20" y2="3"/>'
        '<line x1="1" y1="14" x2="7" y2="14"/><line x1="9" y1="8" x2="15" y2="8"/>'
        '<line x1="17" y1="16" x2="23" y2="16"/>'
    ),
    "file_pdf": (
        '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>'
        '<polyline points="14 2 14 8 20 8"/>'
        '<path d="M9 13h6"/><path d="M9 17h4"/>'
    ),
    "file_image": (
        '<rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>'
        '<circle cx="8.5" cy="8.5" r="1.5"/>'
        '<polyline points="21 15 16 10 5 21"/>'
    ),
    "file_sheet": (
        '<rect x="3" y="3" width="18" height="18" rx="2"/>'
        '<path d="M3 9h18"/><path d="M3 15h18"/><path d="M9 3v18"/>'
    ),
    "file_slides": (
        '<rect x="2" y="4" width="20" height="13" rx="2"/>'
        '<line x1="12" y1="17" x2="12" y2="21"/>'
        '<line x1="8" y1="21" x2="16" y2="21"/>'
    ),
    "file_code": (
        '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>'
        '<polyline points="14 2 14 8 20 8"/>'
        '<polyline points="10 13 8 15 10 17"/>'
        '<polyline points="14 13 16 15 14 17"/>'
    ),
    "file_generic": (
        '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>'
        '<polyline points="14 2 14 8 20 8"/>'
    ),
}

_PIXMAP_CACHE: dict[tuple[str, str, int, float], QPixmap] = {}
_BRAND_CACHE: dict[int, QPixmap] = {}


def render_svg_pixmap(svg_markup: str, size: int = 20) -> QPixmap:
    """Render raw SVG XML into a crisp transparent QPixmap."""
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    renderer = QSvgRenderer(QByteArray(svg_markup.encode("utf-8")))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()
    return QPixmap.fromImage(image)


def get_brand_pixmap(size: int = 36) -> QPixmap:
    if size in _BRAND_CACHE:
        return _BRAND_CACHE[size]
    svg_path = get_asset_path("assets/sortify-icon.svg")
    svg_text = BRAND_SVG
    if svg_path.is_file():
        try:
            svg_text = svg_path.read_text(encoding="utf-8")
        except OSError:
            svg_text = BRAND_SVG
    pixmap = render_svg_pixmap(svg_text, size)
    _BRAND_CACHE[size] = pixmap
    return pixmap


def get_brand_icon() -> QIcon:
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(get_brand_pixmap(size))
    return icon


def get_icon_pixmap(
    name: str,
    color: str = "#E2E8F0",
    size: int = 18,
    stroke_width: float = 1.75,
) -> QPixmap:
    key = (name, color, size, stroke_width)
    if key in _PIXMAP_CACHE:
        return _PIXMAP_CACHE[key]
    body = ICON_PATHS.get(name, ICON_PATHS["file_generic"])
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        f'stroke="{color}" stroke-width="{stroke_width}" stroke-linecap="round" '
        f'stroke-linejoin="round">{body}</svg>'
    )
    pixmap = render_svg_pixmap(svg, size)
    _PIXMAP_CACHE[key] = pixmap
    return pixmap


def get_icon(
    name: str,
    color: str = "#E2E8F0",
    size: int = 18,
    stroke_width: float = 1.75,
) -> QIcon:
    return QIcon(get_icon_pixmap(name, color=color, size=size, stroke_width=stroke_width))


def icon_name_for_extension(ext: str) -> str:
    low = (ext or "").lower()
    if low in IMAGE_EXTENSIONS:
        return "file_image"
    if low in {".xlsx", ".csv", ".tsv"}:
        return "file_sheet"
    if low == ".pptx":
        return "file_slides"
    if low in {".json", ".yaml", ".yml"}:
        return "file_code"
    if low in {".pdf", ".docx", ".txt", ".md", ".rst", ".rtf", ".html", ".htm", ".log"}:
        return "file_pdf"
    return "file_generic"
