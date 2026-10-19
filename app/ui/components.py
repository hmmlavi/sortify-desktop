"""Sortify interface components: frosted glass surfaces, metrics, banners, dialogs."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QLinearGradient,
    QPainter,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.ui.backdrop import Backdrop, rounded_path, widget_rect_in_window
from app.ui.icons import get_icon, get_icon_pixmap
from app.ui.styles import get_tokens


def _qcolor(rgba: tuple[int, int, int, int]) -> QColor:
    return QColor(*rgba)


class GlassPanel(QFrame):
    """A translucent surface that frosts the real canvas behind it."""

    def __init__(
        self,
        object_name: str = "glassPanel",
        dark_mode: bool = True,
        radius: int = 18,
        tint: str = "regular",
        parent: QWidget | None = None,
        backdrop: Backdrop | None = None,
        elevation: int = 0,
    ) -> None:
        super().__init__(parent)
        self.setObjectName(object_name)
        self._dark_mode = dark_mode
        self._radius = radius
        self._tint = tint
        self._backdrop = backdrop
        self._elevation = elevation
        self._cache_key: tuple | None = None
        self._frost: QPixmap | None = None

    # -- configuration ---------------------------------------------------
    def set_dark_mode(self, dark_mode: bool) -> None:
        self._dark_mode = dark_mode
        self._cache_key = None
        self.update()

    def _resolve_backdrop(self) -> Backdrop | None:
        if self._backdrop is not None:
            return self._backdrop
        window = self.window()
        return getattr(window, "backdrop", None)

    # -- painting --------------------------------------------------------
    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        t = get_tokens(self._dark_mode)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        if rect.width() <= 2 or rect.height() <= 2:
            painter.end()
            return
        path = rounded_path(rect, self._radius)
        painter.setClipPath(path)

        backdrop = self._resolve_backdrop()
        if backdrop is not None:
            window_size, region = widget_rect_in_window(self)
            key = (backdrop.generation, region.x(), region.y(), region.width(), region.height(), self._dark_mode)
            if self._cache_key != key or self._frost is None:
                self._frost = backdrop.frosted(window_size, region)
                self._cache_key = key
            if self._frost is not None and not self._frost.isNull():
                painter.drawPixmap(self.rect(), self._frost)

        tint_map = {
            "regular": t.glass_tint,
            "elevated": t.glass_tint_elevated,
            "subtle": t.glass_tint_subtle,
            "rail": t.glass_tint_rail,
        }
        base_tint = _qcolor(tint_map.get(self._tint, t.glass_tint))
        fill = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        top = QColor(base_tint)
        top.setAlpha(min(255, int(base_tint.alpha() * 1.05)))
        bottom = QColor(base_tint)
        bottom.setAlpha(max(0, int(base_tint.alpha() * 0.82)))
        fill.setColorAt(0.0, top)
        fill.setColorAt(0.72, bottom)
        fill.setColorAt(1.0, QColor(base_tint.red(), base_tint.green(), base_tint.blue(), max(0, bottom.alpha() - 14)))
        painter.fillPath(path, fill)

        # Diagonal light sweep across the upper third.
        sheen = QLinearGradient(rect.topLeft(), QPoint(int(rect.width() * 0.85), int(rect.height() * 0.55)))
        sheen.setColorAt(0.0, QColor(255, 255, 255, 30 if self._dark_mode else 96))
        sheen.setColorAt(0.45, QColor(255, 255, 255, 8 if self._dark_mode else 26))
        sheen.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.fillPath(path, sheen)

        painter.setClipping(False)

        # Rim: brighter along the top edge, fading toward the base.
        rim = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        rim.setColorAt(0.0, QColor(t.glass_stroke_strong))
        rim.setColorAt(0.35, QColor(t.glass_stroke))
        rim.setColorAt(1.0, QColor(t.glass_stroke))
        painter.setPen(QPen(rim, 1.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)

        if self._elevation > 0:
            shadow = QColor(t.glass_shade)
            shadow.setAlpha(min(120, 40 + self._elevation * 28))
            painter.setPen(QPen(shadow, 1.0))
            outer = rounded_path(rect.adjusted(-1.0, -1.0, 1.0, 1.0), self._radius + 1)
            painter.drawPath(outer)

        # Specular top hairline, inset so it reads as an edge highlight.
        width = int(rect.width())
        if width > 48:
            inset = min(26, width // 6)
            highlight = QLinearGradient(rect.left() + inset, 0, rect.right() - inset, 0)
            alpha = 150 if not self._dark_mode else 95
            highlight.setColorAt(0.0, QColor(255, 255, 255, 0))
            highlight.setColorAt(0.28, QColor(255, 255, 255, alpha))
            highlight.setColorAt(0.72, QColor(255, 255, 255, alpha))
            highlight.setColorAt(1.0, QColor(255, 255, 255, 0))
            painter.setPen(QPen(highlight, 1.0))
            painter.drawLine(inset, 1, width - inset, 1)

        painter.end()


class MetricTile(GlassPanel):
    """Compact metric: icon chip, value, label, and a supporting caption."""

    def __init__(
        self,
        label: str,
        value: str = "0",
        caption: str = "",
        icon_name: str = "workspace",
        accent_color: str | None = None,
        dark_mode: bool = True,
        backdrop: Backdrop | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(
            "metricTile", dark_mode=dark_mode, radius=16, parent=parent, backdrop=backdrop
        )
        self._accent = accent_color
        self._icon_name = icon_name
        t = get_tokens(dark_mode)
        self._accent = accent_color or t.accent

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(12)

        self.icon_label = QLabel()
        self.icon_label.setFixedSize(34, 34)
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_label.setPixmap(get_icon_pixmap(icon_name, color=self._accent, size=17))
        self.icon_label.setStyleSheet(
            f"background: {_rgba_string(self._accent, 26)};"
            f"border: 1px solid {_rgba_string(self._accent, 52)};"
            "border-radius: 10px;"
        )
        layout.addWidget(self.icon_label, 0, Qt.AlignmentFlag.AlignTop)

        text_col = QVBoxLayout()
        text_col.setSpacing(1)
        row = QHBoxLayout()
        row.setSpacing(8)
        self.value_label = QLabel(value)
        self.value_label.setObjectName("metricValue")
        self.value_label.setStyleSheet("font-size: 17pt;")
        row.addWidget(self.value_label)
        self.eyebrow = QLabel(label.upper())
        self.eyebrow.setObjectName("eyebrow")
        self.eyebrow.setStyleSheet("font-size: 7.5pt;")
        row.addWidget(self.eyebrow, 0, Qt.AlignmentFlag.AlignBottom)
        row.addStretch()
        text_col.addLayout(row)

        self.caption_label = QLabel(caption)
        self.caption_label.setObjectName("muted")
        self.caption_label.setStyleSheet("font-size: 8.5pt;")
        text_col.addWidget(self.caption_label)
        layout.addLayout(text_col, 1)

    def set_value(self, value: str, caption: str | None = None) -> None:
        self.value_label.setText(str(value))
        if caption is not None:
            self.caption_label.setText(caption)

    def set_dark_mode(self, dark_mode: bool) -> None:
        super().set_dark_mode(dark_mode)
        t = get_tokens(dark_mode)
        if self._accent in {"#000000", ""}:
            self._accent = t.accent
        self.icon_label.setPixmap(get_icon_pixmap(self._icon_name, color=self._accent, size=17))
        self.icon_label.setStyleSheet(
            f"background: {_rgba_string(self._accent, 26)};"
            f"border: 1px solid {_rgba_string(self._accent, 52)};"
            "border-radius: 10px;"
        )


def _rgba_string(hex_color: str, alpha: int) -> str:
    color = QColor(hex_color)
    if not color.isValid():
        color = QColor("#C8CED6")
    return f"rgba({color.red()}, {color.green()}, {color.blue()}, {alpha})"


class NotificationBanner(GlassPanel):
    """Inline status strip with a semantic icon, message, action, and dismiss."""

    def __init__(
        self,
        dark_mode: bool = True,
        backdrop: Backdrop | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(
            "bannerInfo",
            dark_mode=dark_mode,
            radius=14,
            tint="elevated",
            parent=parent,
            backdrop=backdrop,
        )
        self._kind = "info"
        self._action_callback: Callable[[], None] | None = None
        self.setVisible(False)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 12, 10, 12)
        layout.setSpacing(11)
        self.setMinimumHeight(58)

        self.icon_label = QLabel()
        self.icon_label.setFixedSize(22, 22)
        layout.addWidget(self.icon_label, 0, Qt.AlignmentFlag.AlignTop)

        text_col = QVBoxLayout()
        text_col.setSpacing(1)
        self.title_label = QLabel()
        self.title_label.setMinimumHeight(17)
        self.title_label.setStyleSheet("font-weight: 700; font-size: 9.5pt;")
        self.message_label = QLabel()
        self.message_label.setObjectName("secondaryText")
        self.message_label.setWordWrap(True)
        self.message_label.setStyleSheet("font-size: 9pt;")
        text_col.addWidget(self.title_label)
        text_col.addWidget(self.message_label)
        layout.addLayout(text_col, 1)

        self.action_btn = QPushButton()
        self.action_btn.setVisible(False)
        self.action_btn.clicked.connect(self._on_action)
        layout.addWidget(self.action_btn, 0, Qt.AlignmentFlag.AlignVCenter)

        self.dismiss_btn = QPushButton()
        self.dismiss_btn.setObjectName("iconButton")
        self.dismiss_btn.setFixedSize(26, 26)
        self.dismiss_btn.setToolTip("Dismiss")
        self.dismiss_btn.clicked.connect(self.hide_banner)
        layout.addWidget(self.dismiss_btn, 0, Qt.AlignmentFlag.AlignTop)

        self._opacity = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity)

    def _on_action(self) -> None:
        if self._action_callback:
            self._action_callback()

    def hide_banner(self) -> None:
        self.setVisible(False)

    def show_banner(
        self,
        kind: str,
        title: str,
        message: str,
        action_text: str | None = None,
        action_callback: Callable[[], None] | None = None,
        dark_mode: bool | None = None,
        reduced_motion: bool = False,
    ) -> None:
        if dark_mode is not None and dark_mode != self._dark_mode:
            self.set_dark_mode(dark_mode)
        t = get_tokens(self._dark_mode)
        mapping = {
            "info": ("info", t.info_fg),
            "success": ("check_circle", t.success_fg),
            "warning": ("warning", t.warning_fg),
            "danger": ("error", t.danger_fg),
        }
        icon_name, fg = mapping.get(kind, mapping["info"])
        self._kind = kind
        self.icon_label.setPixmap(get_icon_pixmap(icon_name, color=fg, size=18))
        self.title_label.setText(title)
        self.title_label.setStyleSheet(f"font-weight: 700; font-size: 9.5pt; color: {fg};")
        self.message_label.setText(message)
        self.dismiss_btn.setIcon(get_icon("close", color=t.text_muted, size=13))

        if action_text and action_callback:
            self._action_callback = action_callback
            self.action_btn.setText(action_text)
            self.action_btn.setObjectName("ghost")
            self.action_btn.setStyleSheet(
                f"border: 1px solid {t.glass_stroke_strong}; background: {t.input_bg};"
                f"color: {t.text_primary}; padding: 5px 12px;"
            )
            self.action_btn.setVisible(True)
        else:
            self._action_callback = None
            self.action_btn.setVisible(False)

        self.setVisible(True)
        self.update()
        if not reduced_motion:
            self._fade = QPropertyAnimation(self._opacity, b"opacity", self)
            self._fade.setDuration(170)
            self._fade.setStartValue(0.35)
            self._fade.setEndValue(1.0)
            self._fade.setEasingCurve(QEasingCurve.Type.OutCubic)
            self._fade.finished.connect(lambda: self._opacity.setOpacity(1.0))
            self._fade.start()
        else:
            self._opacity.setOpacity(1.0)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        t = get_tokens(self._dark_mode)
        color_map = {
            "info": t.info_fg,
            "success": t.success_fg,
            "warning": t.warning_fg,
            "danger": t.danger_fg,
        }
        accent = QColor(color_map.get(self._kind, t.info_fg))
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = rounded_path(rect, 14)

        wash = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        wash.setColorAt(0.0, QColor(accent.red(), accent.green(), accent.blue(), 34))
        wash.setColorAt(1.0, QColor(accent.red(), accent.green(), accent.blue(), 10))
        painter.fillPath(path, wash)

        painter.setPen(QPen(QColor(accent.red(), accent.green(), accent.blue(), 92), 1.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)

        # Accent spine along the leading edge.
        spine = QRectF(rect.left() + 1, rect.top() + 10, 2.4, max(0, rect.height() - 20))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(accent.red(), accent.green(), accent.blue(), 210))
        painter.drawRoundedRect(spine, 1.2, 1.2)
        painter.end()


class EmptyState(QWidget):
    """Refined empty state with a composed plate illustration and actions."""

    def __init__(
        self,
        title: str,
        description: str,
        icon_name: str = "folder_open",
        dark_mode: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._dark_mode = dark_mode
        self._icon_name = icon_name
        self._title = title
        self._description = description

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 30, 24, 30)
        layout.setSpacing(0)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.plate = QLabel()
        self.plate.setFixedSize(132, 104)
        self.plate.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.plate, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addSpacing(18)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("emptyTitle")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.title_label)
        layout.addSpacing(6)

        self.description_label = QLabel(description)
        self.description_label.setObjectName("muted")
        self.description_label.setWordWrap(True)
        self.description_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.description_label.setMaximumWidth(430)
        self.description_label.setMinimumWidth(340)
        self.description_label.setStyleSheet("font-size: 9.5pt;")
        layout.addWidget(self.description_label, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addSpacing(18)

        self.actions = QHBoxLayout()
        self.actions.setSpacing(8)
        self.actions.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addLayout(self.actions)
        self.refresh_art()

    def refresh_art(self) -> None:
        self.plate.setPixmap(self._render_plate())

    def set_dark_mode(self, dark_mode: bool) -> None:
        self._dark_mode = dark_mode
        self.refresh_art()

    def _render_plate(self) -> QPixmap:
        t = get_tokens(self._dark_mode)
        pixmap = QPixmap(132, 104)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)

        cards = [
            (30, 18, 0.55, t.accent),
            (20, 30, 0.75, t.text_secondary),
            (10, 44, 1.0, t.warm),
        ]
        for ox, oy, opacity, color in cards:
            card = QRectF(ox, oy, 112 - ox * 0.9, 46)
            painter.setBrush(QColor(color))
            painter.setOpacity(0.10 * opacity + 0.04)
            painter.drawRoundedRect(card, 11, 11)
            painter.setOpacity(0.30 + 0.35 * opacity)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(color), 1.0))
            painter.drawRoundedRect(card, 11, 11)
            painter.setPen(Qt.PenStyle.NoPen)

        front = QRectF(10, 44, 112, 46)
        painter.setOpacity(0.22)
        painter.setBrush(QColor(t.text_primary))
        painter.drawRoundedRect(front, 11, 11)
        painter.setOpacity(1.0)

        icon = get_icon_pixmap(self._icon_name, color=t.text_primary, size=24)
        painter.drawPixmap(int((132 - 24) / 2), 55, icon)
        painter.end()
        return pixmap


class GlassDialog(QDialog):
    """Dialog base that paints the same aurora canvas as the main window."""

    def __init__(self, dark_mode: bool = True, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.dark_mode = dark_mode
        self.backdrop = Backdrop(dark_mode)
        self.setStyleSheet("")
        self.setModal(True)

    def set_dark_mode(self, dark_mode: bool) -> None:
        self.dark_mode = dark_mode
        self.backdrop.set_dark_mode(dark_mode)
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.drawPixmap(self.rect(), self.backdrop.pixmap(self.size()))
        painter.end()
        super().paintEvent(event)


class BatchPreviewDialog(GlassDialog):
    """Pre-execution confirmation of every planned filesystem operation."""

    def __init__(
        self,
        proposals: list[tuple[Path, str]],
        organize_by_category: bool = False,
        dark_mode: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(dark_mode=dark_mode, parent=parent)
        self.setWindowTitle("Sortify · Review Plan")
        self.resize(820, 560)
        self.setMinimumSize(680, 460)
        t = get_tokens(dark_mode)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(14)

        head = QHBoxLayout()
        head.setSpacing(13)
        badge = QLabel()
        badge.setFixedSize(40, 40)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setPixmap(get_icon_pixmap("shield", color=t.accent, size=21))
        badge.setStyleSheet(
            f"background: {_rgba_string(t.accent, 24)};"
            f"border: 1px solid {_rgba_string(t.accent, 60)}; border-radius: 12px;"
        )
        head.addWidget(badge, 0, Qt.AlignmentFlag.AlignTop)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title = QLabel(f"{len(proposals)} change{'s' if len(proposals) != 1 else ''} ready to apply")
        title.setObjectName("pageTitle")
        title.setStyleSheet("font-size: 15pt;")
        subtitle = QLabel(
            "Files are renamed inside their current folders."
            if not organize_by_category
            else "Files are renamed and moved into category folders."
        )
        subtitle.setObjectName("muted")
        subtitle.setWordWrap(True)
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        head.addLayout(title_col, 1)
        layout.addLayout(head)

        chips = QHBoxLayout()
        chips.setSpacing(8)
        for text, icon_name in (
            ("Contents unchanged", "shield"),
            ("Existing files protected", "layers"),
            ("Session can be undone", "undo"),
        ):
            chips.addWidget(chip_label(icon_name, text, dark_mode=dark_mode))
        chips.addStretch()
        layout.addLayout(chips)

        table = QTableWidget(len(proposals), 3)
        table.setHorizontalHeaderLabels(["Current name", "Proposed name", "Folder"])
        table.setAlternatingRowColors(False)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setShowGrid(False)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(34)
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setHighlightSections(False)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        for row, (src, dst_name) in enumerate(proposals):
            table.setItem(row, 0, QTableWidgetItem(src.name))
            proposed_item = QTableWidgetItem(str(dst_name))
            proposed_item.setIcon(get_icon("arrow_right", color=t.accent, size=13))
            table.setItem(row, 1, proposed_item)
            folder = Path(str(dst_name)).parent.as_posix()
            folder_item = QTableWidgetItem("current folder" if folder in {"", "."} else folder)
            folder_item.setForeground(QColor(t.text_muted))
            table.setItem(row, 2, folder_item)
        layout.addWidget(table, 1)

        footer = QHBoxLayout()
        footer.setSpacing(10)
        note = QLabel("Two-phase atomic rename · no overwrites · rollback protected")
        note.setObjectName("finePrint")
        footer.addWidget(note, 1)
        cancel = QPushButton("Cancel")
        cancel.setObjectName("ghost")
        cancel.clicked.connect(self.reject)
        confirm = QPushButton(f"Apply {len(proposals)} change{'s' if len(proposals) != 1 else ''}")
        confirm.setObjectName("primary")
        confirm.setIcon(get_icon("check", color=t.text_on_accent, size=15))
        confirm.clicked.connect(self.accept)
        footer.addWidget(cancel)
        footer.addWidget(confirm)
        layout.addLayout(footer)


def configure_table(
    table: QTableWidget,
    headers: list[str],
    stretch_columns: tuple[int, ...] = (),
    row_height: int = 38,
) -> None:
    """Apply Sortify's consistent table presentation."""
    table.setHorizontalHeaderLabels(headers)
    table.setAlternatingRowColors(False)
    table.verticalHeader().setVisible(False)
    table.verticalHeader().setDefaultSectionSize(row_height)
    table.setShowGrid(False)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setWordWrap(False)
    header = table.horizontalHeader()
    header.setHighlightSections(False)
    header.setStretchLastSection(False)
    header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    for index in range(len(headers)):
        header.setSectionResizeMode(
            index,
            QHeaderView.ResizeMode.Stretch
            if index in stretch_columns
            else QHeaderView.ResizeMode.ResizeToContents,
        )


def divider(dark_mode: bool = True) -> QFrame:
    t = get_tokens(dark_mode)
    line = QFrame()
    line.setFixedHeight(1)
    line.setStyleSheet(f"background: {t.glass_stroke}; border: none;")
    return line


def dot_pixmap(color: str, size: int = 8) -> QPixmap:
    """Return a small filled status dot with a soft halo."""
    pixmap = QPixmap(size * 2, size * 2)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    halo = QColor(color)
    halo.setAlpha(60)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(halo)
    painter.drawEllipse(QRectF(0, 0, size * 2, size * 2))
    painter.setBrush(QColor(color))
    painter.drawEllipse(QRectF(size * 0.5, size * 0.5, size, size))
    painter.end()
    return pixmap


def chip_label(icon_name: str, text: str, dark_mode: bool = True) -> QFrame:
    """Small pill with a leading vector icon and a readable label."""
    t = get_tokens(dark_mode)
    frame = QFrame()
    frame.setStyleSheet(
        f"QFrame {{ background: {t.accent_soft}; border: 1px solid {t.glass_stroke};"
        f" border-radius: 10px; }} QLabel {{ background: transparent; border: none; }}"
    )
    frame.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
    row = QHBoxLayout(frame)
    row.setContentsMargins(9, 4, 10, 4)
    row.setSpacing(6)
    icon = QLabel()
    icon.setFixedSize(13, 13)
    icon.setPixmap(get_icon_pixmap(icon_name, color=t.text_secondary, size=13))
    label = QLabel(text)
    label.setStyleSheet(f"color: {t.text_secondary}; font-size: 8.4pt; font-weight: 600;")
    row.addWidget(icon)
    row.addWidget(label)
    return frame
