"""Layered aurora backdrop and real backdrop-blur helpers for glass surfaces.

Qt style sheets cannot blur what is behind a widget, so Sortify paints its own
canvas: a cached layered gradient ("aurora") is rendered once per window size,
and every glass panel samples the region beneath itself, downsamples it, and
scales it back up.  That produces true frosted glass at very low cost.
"""

from __future__ import annotations

import random

from PySide6.QtCore import QPoint, QRect, QRectF, QSize, Qt
from PySide6.QtGui import (
    QColor,
    QImage,
    QLinearGradient,
    QPainter,
    QPixmap,
    QRadialGradient,
)

from app.ui.styles import ThemeTokens, get_tokens

_NOISE_TILE: QPixmap | None = None


def _noise_tile() -> QPixmap:
    """Return a cached, very faint monochrome grain tile."""
    global _NOISE_TILE
    if _NOISE_TILE is not None:
        return _NOISE_TILE
    size = 96
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    rng = random.Random(20260214)
    for x in range(size):
        for y in range(size):
            if rng.random() < 0.22:
                image.setPixelColor(x, y, QColor(255, 255, 255, 10))
            elif rng.random() < 0.22:
                image.setPixelColor(x, y, QColor(0, 0, 0, 8))
    _NOISE_TILE = QPixmap.fromImage(image)
    return _NOISE_TILE


class Backdrop:
    """Renders and caches the layered canvas for one theme."""

    def __init__(self, dark_mode: bool = True) -> None:
        self._tokens: ThemeTokens = get_tokens(dark_mode)
        self._pixmap = QPixmap()
        self._size = QSize()
        self._generation = 0

    @property
    def tokens(self) -> ThemeTokens:
        return self._tokens

    @property
    def generation(self) -> int:
        return self._generation

    def set_dark_mode(self, dark_mode: bool) -> None:
        tokens = get_tokens(dark_mode)
        if tokens.name != self._tokens.name:
            self._tokens = tokens
            self._pixmap = QPixmap()
            self._generation += 1

    def pixmap(self, size: QSize) -> QPixmap:
        width = max(1, int(size.width()))
        height = max(1, int(size.height()))
        if (
            not self._pixmap.isNull()
            and self._size.width() == width
            and self._size.height() == height
        ):
            return self._pixmap

        t = self._tokens
        image = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(QColor(t.canvas))

        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        base = QLinearGradient(0, 0, width * 0.35, height)
        base.setColorAt(0.0, QColor(t.canvas_top))
        base.setColorAt(0.55, QColor(t.canvas))
        base.setColorAt(1.0, QColor(t.canvas_bottom))
        painter.fillRect(0, 0, width, height, base)

        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        long_side = max(width, height)
        for fx, fy, fr, hex_color in t.aurora:
            color = QColor(hex_color)
            if not color.isValid():
                continue
            center = QPoint(int(width * fx), int(height * fy))
            radius = max(120.0, long_side * fr * 0.72)
            gradient = QRadialGradient(center, radius)
            overlay = QColor(color)
            overlay.setAlpha(150 if not t.is_dark else 128)
            gradient.setColorAt(0.0, overlay)
            mid = QColor(color)
            mid.setAlpha(58 if not t.is_dark else 48)
            gradient.setColorAt(0.55, mid)
            gradient.setColorAt(1.0, QColor(color.red(), color.green(), color.blue(), 0))
            painter.setBrush(gradient)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(center, int(radius), int(radius))

        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

        # Gentle vignette keeps the centre of the workspace luminous.
        vignette = QRadialGradient(
            QPoint(int(width * 0.5), int(height * 0.45)), long_side * 0.95
        )
        vignette.setColorAt(0.0, QColor(0, 0, 0, 0))
        edge = QColor(0, 0, 0, 64 if t.is_dark else 20)
        vignette.setColorAt(1.0, edge)
        painter.fillRect(0, 0, width, height, vignette)

        # Grain breaks up banding in the large gradients.
        painter.setOpacity(0.45 if t.is_dark else 0.32)
        painter.drawTiledPixmap(QRect(0, 0, width, height), _noise_tile())
        painter.setOpacity(1.0)
        painter.end()

        self._pixmap = QPixmap.fromImage(image)
        self._size = QSize(width, height)
        return self._pixmap

    def frosted(
        self,
        window_size: QSize,
        region: QRect,
        *,
        downscale: int = 6,
    ) -> QPixmap:
        """Return a blurred crop of the canvas for a panel-shaped region."""
        source = self.pixmap(window_size)
        bounded = region.intersected(QRect(0, 0, window_size.width(), window_size.height()))
        if bounded.width() < 2 or bounded.height() < 2:
            return QPixmap()
        crop = source.copy(bounded)
        small_w = max(1, bounded.width() // downscale)
        small_h = max(1, bounded.height() // downscale)
        tiny = crop.scaled(
            small_w,
            small_h,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        # A second downsample softens the result into a proper frost.
        tiny = tiny.scaled(
            max(1, small_w // 2),
            max(1, small_h // 2),
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        return tiny.scaled(
            bounded.size(),
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )


def widget_rect_in_window(widget) -> tuple[QSize, QRect]:
    """Return (window size, widget rect in window coordinates)."""
    window = widget.window()
    size = window.size() if window is not None else widget.size()
    top_left: QPoint = widget.mapTo(window, QPoint(0, 0)) if window is not None else QPoint(0, 0)
    return size, QRect(top_left, widget.size())


def rounded_path(rect: QRectF, radius: float):
    from PySide6.QtGui import QPainterPath

    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    return path
