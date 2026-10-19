"""Sortify main window: workspace, rename review, and activity history."""

from __future__ import annotations

import hashlib
import logging
import sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from PySide6.QtCore import (
    QSize,
    Qt,
    QThreadPool,
    QTimer,
    QUrl,
)
from PySide6.QtGui import (
    QAction,
    QColor,
    QDesktopServices,
    QDragEnterEvent,
    QDropEvent,
    QFont,
    QKeySequence,
    QPainter,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.ai.base_provider import AIProviderError
from app.ai.openai_compatible import OpenAICompatibleProvider
from app.config import APP_NAME, APP_TAGLINE, APP_VERSION, VALID_NAMING_STYLES, Settings
from app.core.batch_names import resolve_batch_conflicts as resolve_batch_names
from app.core.file_extractor import extract_content
from app.core.filename_generator import (
    ai_suggestion,
    fallback_suggestion,
    suggest_category,
)
from app.core.filename_validator import (
    sanitize_filename,
    validate_filename_text,
)
from app.core.operation_history import OperationHistory
from app.core.rename_engine import RenameEngine
from app.core.scanner import SUPPORTED, scan_folder
from app.models.file_record import IMAGE_EXTENSIONS, FileRecord
from app.ui.backdrop import Backdrop
from app.ui.components import (
    BatchPreviewDialog,
    EmptyState,
    GlassPanel,
    MetricTile,
    NotificationBanner,
    configure_table,
    divider,
    dot_pixmap,
)
from app.ui.icons import (
    get_brand_icon,
    get_brand_pixmap,
    get_icon,
    get_icon_pixmap,
    icon_name_for_extension,
)
from app.ui.settings_dialog import SettingsDialog
from app.ui.styles import build_stylesheet, get_tokens
from app.utils.logging_config import configure_logging
from app.workers.tasks import FunctionWorker

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    def __init__(
        self,
        settings: Settings | None = None,
        history: OperationHistory | None = None,
    ):
        super().__init__()
        self.settings = settings or Settings.load()
        self.records: list[FileRecord] = []
        self.folder: Path | None = None
        if self.settings.default_folder:
            candidate = Path(self.settings.default_folder).expanduser()
            if candidate.is_dir():
                self.folder = candidate.resolve()

        self.backdrop = Backdrop(self.settings.dark_mode)
        self.threadpool = QThreadPool.globalInstance()
        self.history = history or OperationHistory()
        self.engine = RenameEngine(self.history)
        self._prune_history()
        self._active_worker: FunctionWorker | None = None
        self._selected_record_path: str | None = None
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(140)
        self._search_timer.timeout.connect(self._filter_table)

        self.setWindowTitle(f"{APP_NAME} — {APP_TAGLINE}")
        self.setWindowIcon(get_brand_icon())
        self.resize(1440, 900)
        self.setMinimumSize(1080, 700)
        self.setAcceptDrops(True)

        self._build_ui()
        self.apply_theme(self.settings.dark_mode)
        self._refresh_status()
        if self.folder:
            self._set_folder_labels()
        self._show_recovery_notices()

    # ------------------------------------------------------------------
    # Shell
    # ------------------------------------------------------------------
    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        try:
            painter.drawPixmap(self.rect(), self.backdrop.pixmap(self.size()))
        finally:
            painter.end()
        super().paintEvent(event)

    def _panel(
        self,
        object_name: str = "glassPanel",
        radius: int = 18,
        tint: str = "regular",
        elevation: int = 0,
    ) -> GlassPanel:
        return GlassPanel(
            object_name=object_name,
            dark_mode=self.settings.dark_mode,
            radius=radius,
            tint=tint,
            backdrop=self.backdrop,
            elevation=elevation,
        )

    def _show_recovery_notices(self) -> None:
        if getattr(self.settings, "recovered_from_corrupt", False):
            self.banner.show_banner(
                "warning",
                "Settings were restored from a backup",
                f"Your settings file could not be read. A copy was saved to "
                f"{self.settings.corrupt_backup_path or 'a .bak file'} and defaults were restored.",
                dark_mode=self.settings.dark_mode,
            )
        elif getattr(self.history, "recovered_from_corruption", False):
            self.banner.show_banner(
                "warning",
                "History database recovered",
                f"The local history file was unreadable. It was preserved at "
                f"{self.history.recovery_backup_path or 'a .bak file'} and a clean database was created.",
                dark_mode=self.settings.dark_mode,
            )
        elif getattr(self.history, "in_memory_fallback", False):
            self.banner.show_banner(
                "warning",
                "Running with temporary history",
                "Sortify could not write to its data folder. History for this session is kept in memory only.",
                dark_mode=self.settings.dark_mode,
            )

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)

        outer = QHBoxLayout(root)
        outer.setContentsMargins(18, 18, 18, 12)
        outer.setSpacing(14)

        outer.addWidget(self._build_sidebar())

        center = QVBoxLayout()
        center.setContentsMargins(0, 0, 0, 0)
        center.setSpacing(12)
        self.banner = NotificationBanner(
            dark_mode=self.settings.dark_mode, backdrop=self.backdrop
        )
        center.addWidget(self.banner)

        self.stack = QStackedWidget()
        center.addWidget(self.stack, 1)
        outer.addLayout(center, 1)

        self.workspace = self._make_workspace()
        self.review_page = self._make_review()
        self.history_page = self._make_history()
        self.stack.addWidget(self.workspace)
        self.stack.addWidget(self.review_page)
        self.stack.addWidget(self.history_page)

        self.setStatusBar(QStatusBar())
        self.statusBar().setSizeGripEnabled(False)
        self.statusBar().showMessage("Ready")

        self._register_shortcuts()
        self._navigate(0)

    def _build_sidebar(self) -> GlassPanel:
        sidebar = self._panel("sidebar", radius=22, tint="rail")
        sidebar.setFixedWidth(252)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(16, 18, 16, 14)
        side.setSpacing(8)

        brand_row = QHBoxLayout()
        brand_row.setSpacing(10)
        self.brand_logo_lbl = QLabel()
        self.brand_logo_lbl.setFixedSize(36, 36)
        self.brand_logo_lbl.setPixmap(get_brand_pixmap(36))
        brand_row.addWidget(self.brand_logo_lbl)

        brand_text = QVBoxLayout()
        brand_text.setSpacing(0)
        self.brand = QLabel("Sortify")
        self.brand.setObjectName("brandName")
        self.tagline = QLabel("ORDER, BY DESIGN")
        self.tagline.setObjectName("brandTag")
        tag_font = self.tagline.font()
        tag_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.2)
        self.tagline.setFont(tag_font)
        brand_text.addWidget(self.brand)
        brand_text.addWidget(self.tagline)
        brand_row.addLayout(brand_text, 1)
        side.addLayout(brand_row)
        side.addSpacing(18)

        nav_header = QLabel("WORKSPACE")
        nav_header.setObjectName("eyebrow")
        side.addWidget(nav_header)
        side.addSpacing(2)

        self.nav_buttons: list[QPushButton] = []
        self._nav_specs = [
            ("Workspace", "workspace", "Choose a folder and build a naming plan"),
            ("Review", "review", "Inspect and edit every proposed filename"),
            ("History", "history", "Browse sessions and undo a batch"),
        ]
        for index, (label, _icon_name, tip) in enumerate(self._nav_specs):
            button = QPushButton(f"  {label}")
            button.setObjectName("nav")
            button.setCheckable(True)
            button.setToolTip(tip)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setIconSize(QSize(17, 17))
            button.clicked.connect(lambda checked=False, i=index: self._navigate(i))
            side.addWidget(button)
            self.nav_buttons.append(button)

        side.addStretch()

        self.status_card = self._panel("subtlePanel", radius=14, tint="subtle")
        card = QVBoxLayout(self.status_card)
        card.setContentsMargins(12, 11, 12, 11)
        card.setSpacing(5)
        head = QHBoxLayout()
        head.setSpacing(6)
        title = QLabel("NAMING ENGINE")
        title.setObjectName("eyebrow")
        head.addWidget(title, 1)
        self.ai_dot = QLabel()
        self.ai_dot.setFixedSize(14, 14)
        head.addWidget(self.ai_dot)
        card.addLayout(head)
        self.ai_status = QLabel("Local heuristics")
        self.ai_status.setStyleSheet("font-size: 9pt; font-weight: 600;")
        card.addWidget(self.ai_status)
        self.ai_detail = QLabel("Files never leave this computer")
        self.ai_detail.setObjectName("finePrint")
        self.ai_detail.setWordWrap(True)
        card.addWidget(self.ai_detail)
        side.addWidget(self.status_card)
        side.addSpacing(6)

        appearance = QHBoxLayout()
        appearance.setSpacing(0)
        self.light_btn = QPushButton("Light")
        self.light_btn.setObjectName("segLeft")
        self.light_btn.setCheckable(True)
        self.light_btn.setToolTip("Smoke appearance (Ctrl+T)")
        self.light_btn.clicked.connect(lambda: self._set_theme(False))
        self.dark_btn = QPushButton("Dark")
        self.dark_btn.setObjectName("segRight")
        self.dark_btn.setCheckable(True)
        self.dark_btn.setToolTip("Charcoal appearance (Ctrl+T)")
        self.dark_btn.clicked.connect(lambda: self._set_theme(True))
        appearance.addWidget(self.light_btn)
        appearance.addWidget(self.dark_btn)
        side.addLayout(appearance)

        self.settings_btn = QPushButton("  Settings")
        self.settings_btn.setObjectName("ghost")
        self.settings_btn.setToolTip("Preferences and AI configuration (Ctrl+,)")
        self.settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.settings_btn.clicked.connect(self.open_settings)
        side.addWidget(self.settings_btn)

        footer = QLabel(f"v{APP_VERSION} · Local-first")
        footer.setObjectName("finePrint")
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        side.addWidget(footer)

        return sidebar

    def _register_shortcuts(self) -> None:
        shortcuts = [
            ("Open folder", "Ctrl+O", self.choose_folder),
            ("Scan folder", "F5", self.start_scan),
            ("Generate names", "Ctrl+Return", self.start_analysis),
            ("Settings", "Ctrl+,", self.open_settings),
            ("Toggle appearance", "Ctrl+T", self.toggle_theme),
            ("Workspace", "Ctrl+1", lambda: self._navigate(0)),
            ("Review", "Ctrl+2", lambda: self._navigate(1)),
            ("History", "Ctrl+3", lambda: self._navigate(2)),
            ("Preview plan", "Ctrl+P", self.preview_batch_plan),
        ]
        for label, sequence, slot in shortcuts:
            action = QAction(label, self)
            action.setShortcut(QKeySequence(sequence))
            action.triggered.connect(slot)
            self.addAction(action)

    # ------------------------------------------------------------------
    # Page 1 — Workspace
    # ------------------------------------------------------------------
    def _make_workspace(self) -> QWidget:
        page = QWidget()
        page.setObjectName("page")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(14)

        header = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(2)
        title = QLabel("Workspace")
        title.setObjectName("displayTitle")
        subtitle = QLabel(
            "Point Sortify at a folder. It reads what is inside each document and proposes a "
            "clearer name — you approve every change before anything moves."
        )
        subtitle.setObjectName("muted")
        subtitle.setWordWrap(True)
        titles.addWidget(title)
        titles.addWidget(subtitle)
        header.addLayout(titles, 1)

        self.open_review_btn = QPushButton("Open review")
        self.open_review_btn.setObjectName("ghost")
        self.open_review_btn.setToolTip("Jump to the review table (Ctrl+2)")
        self.open_review_btn.clicked.connect(lambda: self._navigate(1))
        header.addWidget(self.open_review_btn, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(header)

        layout.addWidget(self._build_command_deck())
        layout.addLayout(self._build_metrics())
        layout.addWidget(self._build_detected_panel(), 1)
        return page

    def _build_command_deck(self) -> GlassPanel:
        deck = self._panel("commandDeck", radius=20, tint="elevated", elevation=1)
        layout = QVBoxLayout(deck)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        top = QHBoxLayout()
        top.setSpacing(12)

        chip = QLabel()
        chip.setFixedSize(38, 38)
        chip.setPixmap(get_brand_pixmap(38))
        top.addWidget(chip)

        folder_col = QVBoxLayout()
        folder_col.setSpacing(1)
        self.folder_label = QLabel("No folder selected")
        self.folder_label.setObjectName("sectionTitle")
        self.folder_label.setStyleSheet("font-size: 12pt;")
        self.folder_path = QLabel(
            "Choose a folder, or drop one anywhere in this window to begin."
        )
        self.folder_path.setObjectName("muted")
        self.folder_path.setWordWrap(False)
        self.folder_path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        folder_col.addWidget(self.folder_label)
        folder_col.addWidget(self.folder_path)
        top.addLayout(folder_col, 1)

        self.organize_check = QCheckBox("Sort into category folders")
        self.organize_check.setToolTip(
            "Move renamed files into Documents, Spreadsheets, Presentations, Images, and similar folders."
        )
        self.organize_check.setChecked(self.settings.organize_by_category)
        self.organize_check.toggled.connect(self._organize_changed)
        top.addWidget(self.organize_check)

        self.scope_check = QCheckBox("Include subfolders")
        self.scope_check.setToolTip("Walk nested folders inside the selected folder.")
        self.scope_check.setChecked(self.settings.include_subfolders)
        self.scope_check.toggled.connect(self._scope_changed)
        top.addWidget(self.scope_check)
        layout.addLayout(top)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.folder_btn = QPushButton("Choose folder")
        self.folder_btn.setObjectName("primary")
        self.folder_btn.setToolTip("Select a folder to scan (Ctrl+O)")
        self.folder_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.folder_btn.clicked.connect(self.choose_folder)
        actions.addWidget(self.folder_btn)

        self.scan_btn = QPushButton("Scan folder")
        self.scan_btn.setToolTip("Discover files in the selected folder (F5)")
        self.scan_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.scan_btn.clicked.connect(self.start_scan)
        actions.addWidget(self.scan_btn)

        self.analyze_btn = QPushButton("Generate names")
        self.analyze_btn.setToolTip("Read file content and propose names (Ctrl+Enter)")
        self.analyze_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.analyze_btn.clicked.connect(self.start_analysis)
        self.analyze_btn.setEnabled(False)
        actions.addWidget(self.analyze_btn)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("danger")
        self.cancel_btn.setVisible(False)
        self.cancel_btn.clicked.connect(self.cancel_active_operation)
        actions.addWidget(self.cancel_btn)
        actions.addStretch()

        style_label = QLabel("Naming style")
        style_label.setObjectName("muted")
        self.quick_style_combo = QComboBox()
        self.quick_style_combo.addItems(list(VALID_NAMING_STYLES))
        self.quick_style_combo.setCurrentText(self.settings.naming_style)
        self.quick_style_combo.setToolTip("How words are joined in generated filenames")
        self.quick_style_combo.setMinimumWidth(190)
        self.quick_style_combo.currentTextChanged.connect(self._quick_style_changed)
        actions.addWidget(style_label)
        actions.addWidget(self.quick_style_combo)

        self.clear_btn = QPushButton("Clear")
        self.clear_btn.setObjectName("ghost")
        self.clear_btn.setToolTip("Clear this session without touching files on disk")
        self.clear_btn.clicked.connect(self.clear_session)
        actions.addWidget(self.clear_btn)
        layout.addLayout(actions)

        progress_row = QHBoxLayout()
        progress_row.setSpacing(12)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        progress_row.addWidget(self.progress, 1)
        self.progress_label = QLabel("Ready when you are")
        self.progress_label.setObjectName("finePrint")
        progress_row.addWidget(self.progress_label, 0, Qt.AlignmentFlag.AlignRight)
        layout.addLayout(progress_row)
        return deck

    def _build_metrics(self) -> QHBoxLayout:
        t = get_tokens(self.settings.dark_mode)
        row = QHBoxLayout()
        row.setSpacing(12)
        specs = [
            ("Files", "folder", t.info_fg, "In scope"),
            ("Supported", "file_pdf", t.accent, "Readable formats"),
            ("Suggested", "check_circle", t.success_fg, "Names ready"),
            ("Needs attention", "warning", t.warning_fg, "Conflicts or errors"),
        ]
        self.stat_files = MetricTile(
            specs[0][0], "0", specs[0][3], specs[0][1], specs[0][2],
            dark_mode=self.settings.dark_mode, backdrop=self.backdrop,
        )
        self.stat_supported = MetricTile(
            specs[1][0], "0", specs[1][3], specs[1][1], specs[1][2],
            dark_mode=self.settings.dark_mode, backdrop=self.backdrop,
        )
        self.stat_ready = MetricTile(
            specs[2][0], "0", specs[2][3], specs[2][1], specs[2][2],
            dark_mode=self.settings.dark_mode, backdrop=self.backdrop,
        )
        self.stat_issues = MetricTile(
            specs[3][0], "0", specs[3][3], specs[3][1], specs[3][2],
            dark_mode=self.settings.dark_mode, backdrop=self.backdrop,
        )
        for tile in (self.stat_files, self.stat_supported, self.stat_ready, self.stat_issues):
            row.addWidget(tile, 1)
        return row

    def _build_detected_panel(self) -> GlassPanel:
        panel = self._panel("glassPanel", radius=18)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 14, 16, 12)
        layout.setSpacing(10)

        head = QHBoxLayout()
        head.setSpacing(8)
        title = QLabel("Detected files")
        title.setObjectName("sectionTitle")
        head.addWidget(title)
        self.detected_count = QLabel("Nothing scanned yet")
        self.detected_count.setObjectName("badgeNeutral")
        head.addWidget(self.detected_count)
        head.addStretch()
        hint = QLabel("Drop a folder anywhere in this window")
        hint.setObjectName("finePrint")
        head.addWidget(hint)
        layout.addLayout(head)

        self.detected_stack = QStackedWidget()
        layout.addWidget(self.detected_stack, 1)

        empty = EmptyState(
            "A clear view of any folder",
            "Sortify reads your documents to suggest descriptive names. "
            "Files are only read — never modified — until you approve.",
            icon_name="folder_open",
            dark_mode=self.settings.dark_mode,
        )
        empty.description_label.setMaximumWidth(470)
        empty.description_label.setMinimumWidth(380)
        empty.description_label.setMinimumHeight(42)
        choose = QPushButton("Choose folder")
        choose.setObjectName("primary")
        choose.clicked.connect(self.choose_folder)
        empty.actions.addWidget(choose)
        self.workspace_empty = empty
        self.detected_stack.addWidget(empty)

        self.detected_table = QTableWidget(0, 4)
        configure_table(
            self.detected_table,
            ["File", "Type", "Size", "Status"],
            stretch_columns=(0,),
            row_height=36,
        )
        self.detected_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.detected_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.detected_table.verticalHeader().setDefaultSectionSize(36)
        self.detected_table.setIconSize(QSize(16, 16))
        header_view = self.detected_table.horizontalHeader()
        header_view.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header_view.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header_view.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.detected_stack.addWidget(self.detected_table)

        self.detected_stack.setCurrentWidget(empty)
        return panel

    # ------------------------------------------------------------------
    # Page 2 — Rename review
    # ------------------------------------------------------------------
    def _make_review(self) -> QWidget:
        page = QWidget()
        page.setObjectName("page")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(12)

        head = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(2)
        title = QLabel("Review")
        title.setObjectName("displayTitle")
        subtitle = QLabel(
            "Check each proposal against the original. Edit any name, resolve conflicts, "
            "then apply the batch in one protected step."
        )
        subtitle.setObjectName("muted")
        subtitle.setWordWrap(True)
        titles.addWidget(title)
        titles.addWidget(subtitle)
        head.addLayout(titles, 1)

        self.resolve_conflicts_btn = QPushButton("Resolve conflicts")
        self.resolve_conflicts_btn.setObjectName("ghost")
        self.resolve_conflicts_btn.setToolTip("Append a number to duplicate destination names")
        self.resolve_conflicts_btn.clicked.connect(self.resolve_batch_conflicts)
        self.resolve_conflicts_btn.setVisible(False)
        head.addWidget(self.resolve_conflicts_btn, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(head)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search names, subjects, types, or status")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(lambda _: self._search_timer.start())
        self.search.setMinimumWidth(220)
        toolbar.addWidget(self.search, 1)

        self.filter = QComboBox()
        self.filter.addItems(["All files", "Ready", "Issues", "Conflicts", "Edited", "Unsupported"])
        self.filter.currentTextChanged.connect(lambda _: self._filter_table())
        toolbar.addWidget(self.filter)

        self.select_all_btn = QPushButton("Select visible")
        self.select_all_btn.setObjectName("ghost")
        self.select_all_btn.clicked.connect(self.select_all)
        toolbar.addWidget(self.select_all_btn)

        self.deselect_all_btn = QPushButton("Deselect")
        self.deselect_all_btn.setObjectName("ghost")
        self.deselect_all_btn.clicked.connect(self.deselect_all)
        toolbar.addWidget(self.deselect_all_btn)

        self.generate_btn = QPushButton("Generate names")
        self.generate_btn.clicked.connect(self.start_analysis)
        toolbar.addWidget(self.generate_btn)
        layout.addLayout(toolbar)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        table_shell = QStackedWidget()
        self.review_table_stack = table_shell

        table_panel = self._panel("glassPanel", radius=16)
        table_layout = QVBoxLayout(table_panel)
        table_layout.setContentsMargins(8, 8, 8, 8)
        self.table = QTableWidget(0, 5)
        configure_table(
            self.table,
            ["Use", "Original name", "Proposed name", "Type · size", "Status"],
            stretch_columns=(1, 2),
            row_height=40,
        )
        self.table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
        )
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setIconSize(QSize(16, 16))
        header = self.table.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(0, 44)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setColumnWidth(1, 250)
        self.table.itemChanged.connect(self._table_edited)
        self.table.itemSelectionChanged.connect(self._on_table_selection_changed)
        table_layout.addWidget(self.table)
        table_shell.addWidget(table_panel)

        review_empty = EmptyState(
            "No files to review yet",
            "Scan a folder, then generate names. Each proposal appears here with "
            "its source content and destination.",
            icon_name="review",
            dark_mode=self.settings.dark_mode,
        )
        review_empty.description_label.setMinimumWidth(360)
        back = QPushButton("Open workspace")
        back.clicked.connect(lambda: self._navigate(0))
        review_empty.actions.addWidget(back)
        self.review_empty = review_empty
        table_shell.addWidget(review_empty)
        table_shell.setCurrentWidget(review_empty)

        splitter.addWidget(table_shell)
        self.inspector_panel = self._make_inspector_panel()
        splitter.addWidget(self.inspector_panel)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([880, 340])
        layout.addWidget(splitter, 1)

        bottom = QHBoxLayout()
        bottom.setSpacing(10)
        self.review_summary = QLabel("Nothing selected")
        self.review_summary.setObjectName("muted")
        bottom.addWidget(self.review_summary, 1)

        self.undo_btn = QPushButton("Undo last session")
        self.undo_btn.setObjectName("ghost")
        self.undo_btn.clicked.connect(self.undo_last)
        bottom.addWidget(self.undo_btn)

        self.preview_plan_btn = QPushButton("Preview plan")
        self.preview_plan_btn.setToolTip("Review every planned change before applying (Ctrl+P)")
        self.preview_plan_btn.clicked.connect(self.preview_batch_plan)
        bottom.addWidget(self.preview_plan_btn)

        self.rename_btn = QPushButton("Apply changes")
        self.rename_btn.setObjectName("primary")
        self.rename_btn.setToolTip("Apply selected rename proposals")
        self.rename_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.rename_btn.clicked.connect(self.apply_renames)
        bottom.addWidget(self.rename_btn)
        layout.addLayout(bottom)
        return page

    def _make_inspector_panel(self) -> GlassPanel:
        panel = self._panel("inspectorPanel", radius=18, tint="subtle")
        panel.setMinimumWidth(300)
        panel.setMaximumWidth(430)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 15, 16, 14)
        layout.setSpacing(9)

        head = QHBoxLayout()
        eyebrow = QLabel("INSPECTOR")
        eyebrow.setObjectName("eyebrow")
        head.addWidget(eyebrow, 1)
        self.inspector_status_badge = QLabel("No selection")
        self.inspector_status_badge.setObjectName("badgeNeutral")
        head.addWidget(self.inspector_status_badge)
        layout.addLayout(head)

        self.inspector_filename = QLabel("Select a file")
        self.inspector_filename.setObjectName("inspectorName")
        self.inspector_filename.setWordWrap(True)
        layout.addWidget(self.inspector_filename)

        self.inspector_meta = QLabel(
            "Choose a row to see its metadata, proposed destination, and extracted content."
        )
        self.inspector_meta.setObjectName("muted")
        self.inspector_meta.setWordWrap(True)
        self.inspector_meta.setStyleSheet("font-size: 8.8pt;")
        layout.addWidget(self.inspector_meta)
        layout.addSpacing(2)

        rename_label = QLabel("RENAME PREVIEW")
        rename_label.setObjectName("eyebrow")
        layout.addWidget(rename_label)

        preview = self._panel("subtlePanel", radius=12, tint="subtle")
        preview_layout = QVBoxLayout(preview)
        preview_layout.setContentsMargins(11, 9, 11, 9)
        preview_layout.setSpacing(4)

        self.preview_current = QLabel("—")
        self.preview_current.setObjectName("muted")
        self.preview_current.setWordWrap(True)
        self.preview_current.setStyleSheet("font-size: 8.8pt;")
        preview_layout.addWidget(self.preview_current)

        arrow_row = QHBoxLayout()
        arrow_row.setSpacing(6)
        arrow = QLabel()
        arrow.setFixedSize(14, 14)
        arrow_row.addWidget(arrow)
        self.preview_arrow = arrow
        self.preview_proposed = QLabel("—")
        self.preview_proposed.setWordWrap(True)
        self.preview_proposed.setStyleSheet("font-size: 10pt; font-weight: 700;")
        arrow_row.addWidget(self.preview_proposed, 1)
        preview_layout.addLayout(arrow_row)
        layout.addWidget(preview)

        self.inspector_name_edit = QLineEdit()
        self.inspector_name_edit.setPlaceholderText("Proposed filename")
        self.inspector_name_edit.setEnabled(False)
        self.inspector_name_edit.editingFinished.connect(self._inspector_name_committed)
        layout.addWidget(self.inspector_name_edit)

        edit_actions = QHBoxLayout()
        edit_actions.setSpacing(6)
        self.inspector_apply_btn = QPushButton("Update")
        self.inspector_apply_btn.setEnabled(False)
        self.inspector_apply_btn.clicked.connect(self._inspector_name_committed)
        self.inspector_reset_btn = QPushButton("Reset")
        self.inspector_reset_btn.setObjectName("ghost")
        self.inspector_reset_btn.setEnabled(False)
        self.inspector_reset_btn.clicked.connect(self._inspector_reset_name)
        edit_actions.addWidget(self.inspector_apply_btn, 1)
        edit_actions.addWidget(self.inspector_reset_btn)
        layout.addLayout(edit_actions)

        layout.addWidget(divider(self.settings.dark_mode))

        rationale_label = QLabel("RATIONALE")
        rationale_label.setObjectName("eyebrow")
        layout.addWidget(rationale_label)
        self.inspector_rationale = QLabel("—")
        self.inspector_rationale.setObjectName("secondaryText")
        self.inspector_rationale.setWordWrap(True)
        self.inspector_rationale.setStyleSheet("font-size: 8.8pt;")
        layout.addWidget(self.inspector_rationale)

        excerpt_label = QLabel("EXTRACTED CONTENT")
        excerpt_label.setObjectName("eyebrow")
        layout.addWidget(excerpt_label)
        self.inspector_excerpt = QPlainTextEdit()
        self.inspector_excerpt.setReadOnly(True)
        self.inspector_excerpt.setPlaceholderText("Content appears here after analysis.")
        layout.addWidget(self.inspector_excerpt, 1)

        self.reveal_btn = QPushButton("Show in Explorer")
        self.reveal_btn.setObjectName("ghost")
        self.reveal_btn.setIcon(get_icon("folder_open", color=get_tokens(self.settings.dark_mode).text_secondary, size=14))
        self.reveal_btn.setEnabled(False)
        self.reveal_btn.clicked.connect(self._reveal_selected_file)
        layout.addWidget(self.reveal_btn)
        return panel

    # ------------------------------------------------------------------
    # Page 3 — History
    # ------------------------------------------------------------------
    def _make_history(self) -> QWidget:
        page = QWidget()
        page.setObjectName("page")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(12)

        head = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(2)
        title = QLabel("History")
        title.setObjectName("displayTitle")
        subtitle = QLabel(
            "A local record of every applied batch. File contents are never stored here."
        )
        subtitle.setObjectName("muted")
        subtitle.setWordWrap(True)
        titles.addWidget(title)
        titles.addWidget(subtitle)
        head.addLayout(titles, 1)

        self.history_search = QLineEdit()
        self.history_search.setPlaceholderText("Filter by path or session")
        self.history_search.setClearButtonEnabled(True)
        self.history_search.setFixedWidth(250)
        self.history_search.textChanged.connect(lambda _: self._filter_history_table())
        head.addWidget(self.history_search, 0, Qt.AlignmentFlag.AlignBottom)
        layout.addLayout(head)

        panel = self._panel("glassPanel", radius=18)
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(8, 8, 8, 8)
        panel_layout.setSpacing(8)

        self.history_stack = QStackedWidget()
        self.history_empty = EmptyState(
            "No sessions yet",
            "Once you apply a batch of renames, the session appears here so you can review "
            "or undo it.",
            icon_name="history",
            dark_mode=self.settings.dark_mode,
        )
        self.history_stack.addWidget(self.history_empty)

        self.history_table = QTableWidget(0, 5)
        configure_table(
            self.history_table,
            ["When", "Session", "Original path", "New path", "Status"],
            stretch_columns=(2, 3),
            row_height=38,
        )
        self.history_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.history_table.setIconSize(QSize(15, 15))
        self.history_table.horizontalHeader().setDefaultAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self.history_stack.addWidget(self.history_table)
        panel_layout.addWidget(self.history_stack, 1)

        footer = QHBoxLayout()
        footer.setSpacing(8)
        self.history_count_label = QLabel("0 recorded operations")
        self.history_count_label.setObjectName("muted")
        footer.addWidget(self.history_count_label, 1)

        refresh = QPushButton("Refresh")
        refresh.setObjectName("ghost")
        refresh.clicked.connect(self.refresh_history)
        footer.addWidget(refresh)

        clear_history_btn = QPushButton("Clear history")
        clear_history_btn.setObjectName("ghost")
        clear_history_btn.clicked.connect(self.clear_history_records)
        footer.addWidget(clear_history_btn)

        undo = QPushButton("Undo last session")
        undo.clicked.connect(self.undo_last)
        footer.addWidget(undo)
        panel_layout.addLayout(footer)
        layout.addWidget(panel, 1)
        return page

    # ------------------------------------------------------------------
    # Theme
    # ------------------------------------------------------------------
    def apply_theme(self, dark_mode: bool) -> None:
        self.settings.dark_mode = dark_mode
        self.backdrop.set_dark_mode(dark_mode)
        t = get_tokens(dark_mode)
        self.setStyleSheet(build_stylesheet(dark_mode))

        for panel in self.findChildren(GlassPanel):
            panel.set_dark_mode(dark_mode)
        for empty in self.findChildren(EmptyState):
            empty.set_dark_mode(dark_mode)

        for index, (_, icon_name, _) in enumerate(self._nav_specs):
            active = self.nav_buttons[index].isChecked()
            self.nav_buttons[index].setIcon(
                get_icon(icon_name, color=t.accent if active else t.text_muted, size=17)
            )

        self.brand_logo_lbl.setPixmap(get_brand_pixmap(36))
        self.light_btn.setChecked(not dark_mode)
        self.dark_btn.setChecked(dark_mode)
        self.light_btn.setIcon(get_icon("sun", color=t.text_secondary if dark_mode else t.accent, size=14))
        self.dark_btn.setIcon(get_icon("moon", color=t.accent if dark_mode else t.text_secondary, size=14))
        self.settings_btn.setIcon(get_icon("settings", color=t.text_muted, size=15))
        self.folder_btn.setIcon(get_icon("folder_open", color=t.text_on_accent, size=15))
        self.scan_btn.setIcon(get_icon("scan", color=t.text_primary, size=15))
        self.analyze_btn.setIcon(get_icon("sparkles", color=t.text_primary, size=15))
        self.open_review_btn.setIcon(get_icon("arrow_right", color=t.text_secondary, size=14))
        self.cancel_btn.setIcon(get_icon("close", color=t.danger_fg, size=14))
        self.clear_btn.setIcon(get_icon("trash", color=t.text_muted, size=14))
        self.generate_btn.setIcon(get_icon("sparkles", color=t.text_primary, size=14))
        self.preview_plan_btn.setIcon(get_icon("eye", color=t.text_primary, size=15))
        self.rename_btn.setIcon(get_icon("check", color=t.text_on_accent, size=15))
        self.undo_btn.setIcon(get_icon("undo", color=t.text_secondary, size=14))
        self.resolve_conflicts_btn.setIcon(get_icon("filter", color=t.warning_fg, size=14))
        self.preview_arrow.setPixmap(get_icon_pixmap("arrow_right", color=t.accent, size=14))
        self.reveal_btn.setIcon(get_icon("folder_open", color=t.text_secondary, size=14))
        self.search.setStyleSheet("")

        self._refresh_status()
        self._render_records()
        self.refresh_history()
        self.update()
        self.repaint()

    def _set_theme(self, dark_mode: bool) -> None:
        if self.settings.dark_mode == dark_mode:
            return
        self.apply_theme(dark_mode)
        try:
            self.settings.save()
        except (OSError, RuntimeError) as exc:
            logger.debug("Could not persist appearance: %s", exc)
        name = "Charcoal" if dark_mode else "Smoke"
        self.statusBar().showMessage(f"{name} appearance")

    def toggle_theme(self) -> None:
        self._set_theme(not self.settings.dark_mode)

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------
    def _navigate(self, index: int) -> None:
        if not hasattr(self, "stack"):
            return
        self.stack.setCurrentIndex(index)
        t = get_tokens(self.settings.dark_mode)
        for i, button in enumerate(self.nav_buttons):
            button.setChecked(i == index)
            _, icon_name, _ = self._nav_specs[i]
            button.setIcon(
                get_icon(
                    icon_name,
                    color=t.accent if i == index else t.text_muted,
                    size=17,
                )
            )
        if index == 1:
            self._render_records()
        elif index == 2:
            self.refresh_history()

        # Page transitions are intentionally instant: graphics-effect fades can
        # leave a page at zero opacity if a paint cycle is skipped, and file
        # operations must never be gated behind animations.
        self.stack.update()

    # ------------------------------------------------------------------
    # Drag & drop
    # ------------------------------------------------------------------
    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.isLocalFile():
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        for url in event.mimeData().urls():
            if not url.isLocalFile():
                continue
            local_path = Path(url.toLocalFile()).expanduser()
            target = local_path if local_path.is_dir() else local_path.parent
            if not target.is_dir():
                continue
            self.folder = target.resolve()
            self._set_folder_labels()
            self.banner.setVisible(False)
            self.statusBar().showMessage(f"Folder selected: {self.folder}")
            self._navigate(0)
            self.start_scan()
            event.acceptProposedAction()
            return

    # ------------------------------------------------------------------
    # Options
    # ------------------------------------------------------------------
    def _scope_changed(self, checked: bool) -> None:
        self.settings.include_subfolders = checked
        try:
            self.settings.save()
        except (OSError, RuntimeError) as exc:
            logger.debug("Could not persist subfolder setting: %s", exc)

    def _organize_changed(self, checked: bool) -> None:
        self.settings.organize_by_category = checked
        try:
            self.settings.save()
        except (OSError, RuntimeError) as exc:
            logger.debug("Could not persist organization setting: %s", exc)
        if self.records:
            self._recompute_collisions()
            self._render_records()

    def _quick_style_changed(self, style_text: str) -> None:
        if style_text not in VALID_NAMING_STYLES:
            return
        self.settings.naming_style = style_text
        try:
            self.settings.save()
        except (OSError, RuntimeError) as exc:
            logger.debug("Could not persist naming style: %s", exc)
        if self.records:
            for record in self.records:
                if record.proposed_name:
                    record.proposed_name = self._sanitize(record.proposed_name, record.extension)
            self._recompute_collisions()
            self._render_records()

    # ------------------------------------------------------------------
    # Folder selection and scanning
    # ------------------------------------------------------------------
    def _set_folder_labels(self) -> None:
        if not self.folder:
            return
        name = self.folder.name or str(self.folder)
        self.folder_label.setText(name)
        self.folder_path.setText(str(self.folder))
        self.folder_path.setToolTip(str(self.folder))
        self.folder_label.setToolTip(str(self.folder))

    def choose_folder(self) -> None:
        if self._active_worker is not None:
            return
        start_dir = str(self.folder) if self.folder else str(Path.home())
        folder = QFileDialog.getExistingDirectory(self, "Choose a folder", start_dir)
        if not folder:
            return
        self.folder = Path(folder).resolve()
        self._set_folder_labels()
        self.banner.setVisible(False)
        self.statusBar().showMessage("Folder selected. Scanning…")
        self.start_scan()

    def start_scan(self) -> None:
        if self._active_worker is not None:
            self.statusBar().showMessage("An operation is already running")
            return
        if not self.folder:
            QMessageBox.information(
                self, "Choose a folder", "Select a folder before scanning."
            )
            return
        if not self.folder.is_dir():
            QMessageBox.warning(
                self,
                "Folder unavailable",
                f"Sortify cannot access:\n{self.folder}\n\nChoose another folder and try again.",
            )
            return
        self.banner.setVisible(False)
        self._set_busy(True, "Scanning folder…")
        self.progress.setRange(0, 0)
        self.progress_label.setText("Scanning…")

        worker = FunctionWorker(
            lambda: scan_folder(
                self.folder,
                include_subfolders=self.scope_check.isChecked(),
                skip_symlinks=self.settings.skip_symlinks,
                cancel_check=worker.token.is_cancelled,
                progress_callback=worker.signals.progress.emit,
            )
        )
        self._active_worker = worker
        worker.signals.progress.connect(self._scan_progress)
        worker.signals.result.connect(self._scan_done)
        worker.signals.cancelled.connect(self._operation_cancelled)
        worker.signals.error.connect(self._worker_error)
        worker.signals.finished.connect(lambda: self._set_busy(False))
        self.threadpool.start(worker)

    def _scan_progress(self, count: int, current_name: str) -> None:
        if count <= 3:
            self.progress_label.setText(f"Scanning · {count} files found")
        else:
            self.progress_label.setText(f"Scanning · {count} files · {current_name}")

    def _scan_done(self, records: list[FileRecord]) -> None:
        self.records = records
        self.progress.setRange(0, 100)
        self.progress.setValue(100 if records else 0)
        self._update_stats()
        self._render_records()
        self._render_detected(records)

        has_supported = any(r.selected and r.status != "Unsupported" for r in records)
        self.analyze_btn.setEnabled(has_supported)
        self.progress_label.setText(
            f"{len(records)} file{'s' if len(records) != 1 else ''} found"
        )
        self.statusBar().showMessage(
            f"Scan complete · {len(records)} file(s) discovered"
        )

        if not records:
            self.banner.show_banner(
                "info",
                "No files in this folder",
                "Try enabling “Include subfolders”, or choose a different folder.",
                dark_mode=self.settings.dark_mode,
                reduced_motion=self.settings.reduced_motion,
            )
        elif not has_supported:
            self.banner.show_banner(
                "warning",
                "No readable formats found",
                f"{len(records)} file(s) were found, but none are supported document, "
                "spreadsheet, slide, text, data, or image formats.",
                dark_mode=self.settings.dark_mode,
                reduced_motion=self.settings.reduced_motion,
            )
        else:
            supported = sum(r.extension in SUPPORTED for r in records)
            self.banner.show_banner(
                "info",
                f"{len(records)} files · {supported} readable",
                "Generate names when you are ready. Nothing changes until you apply.",
                action_text="Generate names",
                action_callback=self.start_analysis,
                dark_mode=self.settings.dark_mode,
                reduced_motion=self.settings.reduced_motion,
            )

    def _render_detected(self, records: list[FileRecord]) -> None:
        if not hasattr(self, "detected_table"):
            return
        t = get_tokens(self.settings.dark_mode)
        table = self.detected_table
        table.setUpdatesEnabled(False)
        table.setRowCount(0)
        for record in records[:400]:
            row = table.rowCount()
            table.insertRow(row)
            name_item = QTableWidgetItem(record.relative_path if self.settings.include_subfolders else record.name)
            name_item.setIcon(
                get_icon(icon_name_for_extension(record.extension), color=t.accent, size=15)
            )
            name_item.setToolTip(str(record.path))
            table.setItem(row, 0, name_item)

            type_item = QTableWidgetItem(record.file_type_label)
            type_item.setForeground(QColor(t.text_muted))
            table.setItem(row, 1, type_item)

            size_item = QTableWidgetItem(record.human_size)
            size_item.setForeground(QColor(t.text_muted))
            table.setItem(row, 2, size_item)

            status_item = QTableWidgetItem(record.status)
            status_item.setForeground(
                QColor(t.success_fg if record.status != "Unsupported" else t.text_faint)
            )
            table.setItem(row, 3, status_item)
        table.setUpdatesEnabled(True)

        if records:
            self.detected_stack.setCurrentWidget(self.detected_table)
            suffix = " (showing first 400)" if len(records) > 400 else ""
            self.detected_count.setText(f"{len(records)} files{suffix}")
        else:
            self.detected_stack.setCurrentWidget(self.workspace_empty)
            self.detected_count.setText("Nothing scanned yet")

    # ------------------------------------------------------------------
    # Analysis
    # ------------------------------------------------------------------
    def start_analysis(self) -> None:
        if self._active_worker is not None:
            return
        if not self.records:
            QMessageBox.information(self, "Nothing to analyze", "Scan a folder first.")
            return

        if self.settings.external_ai_consent and not self.settings.api_key:
            QMessageBox.warning(
                self,
                "API key missing",
                "External AI is enabled but no API key is saved. Add one in Settings, or turn "
                "off external AI to keep everything local.",
            )
            return

        provider = None
        if self.settings.external_ai_consent and self.settings.api_key:
            try:
                provider = OpenAICompatibleProvider(
                    self.settings.api_key,
                    self.settings.api_base_url,
                    self.settings.model,
                    self.settings.request_timeout_seconds,
                )
            except AIProviderError as exc:
                QMessageBox.warning(self, "AI configuration", str(exc))
                return

        selected = [r for r in self.records if r.selected and r.status != "Unsupported"]
        if not selected:
            QMessageBox.information(
                self, "No supported files", "Select at least one supported file."
            )
            return

        if provider:
            reply = QMessageBox.question(
                self,
                "Send excerpts to the AI provider?",
                f"Bounded excerpts from {len(selected)} file(s) will be sent to\n"
                f"{self.settings.api_base_url}\nusing {self.settings.model}.\n\n"
                "File contents are only used to suggest names. Continue?",
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        self.banner.setVisible(False)
        self._set_busy(True, "Reading files and proposing names…")
        self.progress.setRange(0, len(selected))
        self.progress.setValue(0)
        self.progress_label.setText(f"0 of {len(selected)}")

        worker = FunctionWorker(
            lambda: self._analyze_records(
                selected,
                provider,
                worker.signals.progress.emit,
                worker.token.is_cancelled,
            )
        )
        self._active_worker = worker
        worker.signals.progress.connect(self._analysis_progress)
        worker.signals.result.connect(self._analysis_done)
        worker.signals.cancelled.connect(self._operation_cancelled)
        worker.signals.error.connect(self._worker_error)
        worker.signals.finished.connect(lambda: self._set_busy(False))
        self.threadpool.start(worker)

    def _compute_cache_key(self, record: FileRecord, mode: str) -> str:
        raw = (
            f"{record.path}|{record.size_bytes}|{record.modified_iso}|"
            f"{self.settings.naming_style}|{self.settings.max_filename_length}|"
            f"{self.settings.prepend_date}|{self.settings.custom_prefix}|{mode}"
        )
        return hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()

    def _analyze_single_record(
        self,
        record: FileRecord,
        provider: OpenAICompatibleProvider | None,
    ) -> FileRecord:
        mode = f"ai:{self.settings.model}" if provider else "local"
        cache_key = self._compute_cache_key(record, mode)
        if self.settings.cache_enabled:
            cached = self.history.get_cached_suggestion(cache_key)
            if cached and cached.get("name"):
                record.proposed_name = self._sanitize(cached["name"], record.extension)
                record.detected_subject = cached.get("subject", "")
                record.rationale = cached.get("rationale", "")
                record.extracted_text = cached.get("extracted_text", record.extracted_text)
                record.source = cached.get("source", record.source)
                record.category = suggest_category(record.extension, record.source)
                record.status = cached.get(
                    "status", "AI suggestion ready" if provider else "Local fallback"
                )
                record.generation_mode = "ai" if provider else "local"
                record.error = None
                return record

        text, kind = extract_content(record.path, self.settings.max_extract_chars)
        record.extracted_text = text
        record.source = kind
        record.category = suggest_category(record.extension, kind)

        is_image = record.extension in IMAGE_EXTENSIONS
        if provider and (text.strip() or is_image):
            suggestion = ai_suggestion(
                record.name,
                record.extension,
                text,
                kind,
                provider,
                self.settings.naming_style,
                self.settings.max_filename_length,
                image_path=record.path if is_image else None,
                prepend_date=self.settings.prepend_date,
                date_iso=record.modified_iso,
                custom_prefix=self.settings.custom_prefix,
            )
            record.status = "AI suggestion ready"
            record.generation_mode = "ai"
        else:
            suggestion = fallback_suggestion(
                record.name,
                record.extension,
                text or record.path.stem.replace("_", " "),
                self.settings.naming_style,
                self.settings.max_filename_length,
                prepend_date=self.settings.prepend_date,
                date_iso=record.modified_iso,
                custom_prefix=self.settings.custom_prefix,
            )
            record.status = "Local fallback" if text.strip() else "Metadata fallback"
            record.generation_mode = "local" if text.strip() else "metadata"

        record.proposed_name = suggestion["name"]
        record.detected_subject = suggestion["subject"]
        record.rationale = suggestion.get("rationale", "")
        record.error = None

        if self.settings.cache_enabled:
            self.history.set_cached_suggestion(
                cache_key,
                {
                    "name": record.proposed_name,
                    "subject": record.detected_subject,
                    "rationale": record.rationale,
                    "extracted_text": record.extracted_text[:4000],
                    "source": record.source,
                    "status": record.status,
                },
            )
        return record

    def _analyze_records(
        self,
        records: list[FileRecord],
        provider: OpenAICompatibleProvider | None,
        progress_callback=None,
        cancel_check=None,
    ) -> list[FileRecord]:
        results: list[FileRecord] = []
        workers = (
            max(1, min(8, self.settings.max_concurrent_requests))
            if provider and len(records) > 1
            else 1
        )

        if workers == 1:
            for index, record in enumerate(records, 1):
                if cancel_check and cancel_check():
                    break
                try:
                    self._analyze_single_record(record, provider)
                except Exception as exc:  # noqa: BLE001 - surfaced per file
                    record.status = "Analysis failed"
                    record.error = str(exc)
                    record.rationale = f"Error: {exc}"
                    record.proposed_name = ""
                    record.detected_subject = ""
                results.append(record)
                if progress_callback:
                    progress_callback(index, record.name)
            return results

        completed = 0
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(self._analyze_single_record, record, provider): record
                for record in records
            }
            for future in as_completed(futures):
                if cancel_check and cancel_check():
                    for pending in futures:
                        pending.cancel()
                    break
                record = futures[future]
                try:
                    future.result()
                except Exception as exc:  # noqa: BLE001 - surfaced per file
                    record.status = "Analysis failed"
                    record.error = str(exc)
                    record.rationale = f"Error: {exc}"
                    record.proposed_name = ""
                    record.detected_subject = ""
                completed += 1
                results.append(record)
                if progress_callback:
                    progress_callback(completed, record.name)
        return results

    def _analysis_progress(self, current: int, name: str) -> None:
        self.progress.setValue(current)
        self.progress_label.setText(f"{current} of {self.progress.maximum()} · {name}")

    def _analysis_done(self, analyzed_records: list[FileRecord]) -> None:
        by_path = {str(r.path): r for r in analyzed_records}
        if self.records:
            merged: list[FileRecord] = []
            seen: set[str] = set()
            for existing in self.records:
                key = str(existing.path)
                merged.append(by_path.get(key, existing))
                seen.add(key)
            for extra in analyzed_records:
                if str(extra.path) not in seen:
                    merged.append(extra)
            self.records = merged
        else:
            self.records = analyzed_records

        self._recompute_collisions()
        self._update_stats()
        self._render_records()
        self._render_detected(self.records)
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        self.progress_label.setText("Names ready for review")
        self._navigate(1)

        failed = sum(r.status == "Analysis failed" for r in self.records)
        conflicts = sum(bool(r.conflict_reason) for r in self.records)
        ready = sum(bool(r.proposed_name) and not r.conflict_reason for r in self.records)

        if conflicts:
            self.banner.show_banner(
                "warning",
                f"{conflicts} naming conflict{'s' if conflicts != 1 else ''}",
                f"{ready} proposal(s) are ready. Some destinations collide — resolve them "
                "automatically in the review header, or edit the names.",
                dark_mode=self.settings.dark_mode,
                reduced_motion=self.settings.reduced_motion,
            )
        elif failed:
            self.banner.show_banner(
                "warning",
                f"Finished with {failed} issue{'s' if failed != 1 else ''}",
                f"{ready} name(s) were generated. Files that could not be read are marked "
                "in the review table.",
                dark_mode=self.settings.dark_mode,
                reduced_motion=self.settings.reduced_motion,
            )
        else:
            self.banner.show_banner(
                "success",
                f"{ready} proposal{'s' if ready != 1 else ''} ready",
                "Compare each original with its new name. Nothing has been changed on disk.",
                dark_mode=self.settings.dark_mode,
                reduced_motion=self.settings.reduced_motion,
            )
        self.statusBar().showMessage(f"Analysis complete · {ready} proposal(s) ready")

    def cancel_active_operation(self) -> None:
        if self._active_worker:
            self._active_worker.cancel()
            self.progress_label.setText("Cancelling…")

    def _operation_cancelled(self) -> None:
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress_label.setText("Cancelled")
        self.banner.show_banner(
            "info",
            "Operation cancelled",
            "The background task stopped. No files were modified.",
            dark_mode=self.settings.dark_mode,
            reduced_motion=self.settings.reduced_motion,
        )
        self.statusBar().showMessage("Operation cancelled")

    # ------------------------------------------------------------------
    # Collision handling
    # ------------------------------------------------------------------
    def _target_destination_for_record(self, record: FileRecord) -> Path:
        if not record.proposed_name:
            return record.path
        if self.settings.organize_by_category and self.folder:
            category = self._category_for(record)
            return self.folder / category / record.proposed_name
        return record.path.with_name(record.proposed_name)

    def _recompute_collisions(self) -> None:
        destinations: dict[str, list[FileRecord]] = {}
        selected_sources = {
            str(r.path.resolve()).casefold()
            for r in self.records
            if r.selected and r.proposed_name
        }

        for record in self.records:
            record.conflict_reason = None
            if not record.proposed_name:
                continue
            name_error = validate_filename_text(record.proposed_name)
            if name_error:
                record.conflict_reason = name_error
                record.status = "Conflict"
                continue
            destination = self._target_destination_for_record(record)
            try:
                key = str(destination.parent.resolve() / destination.name).casefold()
            except OSError:
                key = str(destination).casefold()
            if record.selected:
                destinations.setdefault(key, []).append(record)

            if destination.exists():
                try:
                    dest_key = str(destination.resolve()).casefold()
                    src_key = str(record.path.resolve()).casefold()
                    if dest_key != src_key and dest_key not in selected_sources:
                        record.conflict_reason = (
                            f"“{destination.name}” already exists in the destination folder."
                        )
                        record.status = "Conflict"
                except OSError:
                    pass

        for group in destinations.values():
            if len(group) > 1:
                for record in group:
                    record.conflict_reason = (
                        f"“{record.proposed_name}” is proposed for {len(group)} files in this batch."
                    )
                    record.status = "Conflict"

        for record in self.records:
            if not record.conflict_reason and record.status == "Conflict":
                record.status = (
                    "Edited by user"
                    if record.generation_mode == "manual"
                    else ("AI suggestion ready" if record.generation_mode == "ai" else "Local fallback")
                )

        if hasattr(self, "resolve_conflicts_btn"):
            self.resolve_conflicts_btn.setVisible(
                any(bool(r.conflict_reason) for r in self.records)
            )

    def _sanitize(self, name: str, extension: str) -> str:
        return sanitize_filename(
            name,
            extension,
            self.settings.max_filename_length,
            self.settings.naming_style,
        )

    @staticmethod
    def _category_for(record: FileRecord) -> str:
        return record.category or suggest_category(record.extension, record.source)

    def resolve_batch_conflicts(self) -> None:
        resolved = resolve_batch_names(
            self.records, self.settings.max_filename_length, self.settings.naming_style
        )
        self._recompute_collisions()
        self._update_stats()
        self._render_records()
        self.banner.show_banner(
            "success",
            "Conflicts resolved",
            f"Unique names were assigned to {resolved} proposal(s).",
            dark_mode=self.settings.dark_mode,
            reduced_motion=self.settings.reduced_motion,
        )

    # ------------------------------------------------------------------
    # Metrics & table rendering
    # ------------------------------------------------------------------
    def _update_stats(self) -> None:
        supported = sum(1 for r in self.records if r.extension in SUPPORTED)
        ready = sum(1 for r in self.records if r.proposed_name and not r.conflict_reason)
        issues = sum(
            1
            for r in self.records
            if r.status in {"Unsupported", "Analysis failed", "Conflict"} or r.conflict_reason
        )
        self.stat_files.set_value(str(len(self.records)), "In scope")
        self.stat_supported.set_value(str(supported), "Readable formats")
        self.stat_ready.set_value(str(ready), "Names ready")
        self.stat_issues.set_value(str(issues), "Conflicts or errors")

    def _render_records(self) -> None:
        if not hasattr(self, "table"):
            return
        t = get_tokens(self.settings.dark_mode)
        table = self.table
        scroll_position = table.verticalScrollBar().value()
        table.setUpdatesEnabled(False)
        table.blockSignals(True)
        table.setRowCount(0)
        restore_row = -1

        for record in self.records:
            row = table.rowCount()
            table.insertRow(row)
            if self._selected_record_path and str(record.path) == self._selected_record_path:
                restore_row = row

            check = QTableWidgetItem()
            check.setFlags(
                Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsUserCheckable
                | Qt.ItemFlag.ItemIsSelectable
            )
            check.setCheckState(
                Qt.CheckState.Checked if record.selected else Qt.CheckState.Unchecked
            )
            check.setData(Qt.ItemDataRole.UserRole, str(record.path))
            table.setItem(row, 0, check)

            display = record.relative_path if self.settings.include_subfolders else record.name
            original = QTableWidgetItem(display)
            original.setIcon(
                get_icon(icon_name_for_extension(record.extension), color=t.accent, size=15)
            )
            subject_line = f"\nDetected subject: {record.detected_subject}" if record.detected_subject else ""
            original.setToolTip(
                f"{record.path}\n{record.file_type_label} · {record.human_size}\n"
                f"Modified {record.modified_iso}{subject_line}"
            )
            original.setData(Qt.ItemDataRole.UserRole, str(record.path))
            original.setFlags(original.flags() & ~Qt.ItemFlag.ItemIsEditable)
            table.setItem(row, 1, original)

            proposed = QTableWidgetItem(record.proposed_name)
            proposed.setData(Qt.ItemDataRole.UserRole, str(record.path))
            if self.settings.organize_by_category and record.proposed_name:
                category = self._category_for(record)
                proposed.setToolTip(f"Destination: {category}/{record.proposed_name}")
            else:
                proposed.setToolTip(record.proposed_name or "Double-click to edit this name")
            table.setItem(row, 2, proposed)

            type_item = QTableWidgetItem(f"{record.extension or 'none'} · {record.human_size}")
            type_item.setFlags(type_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            type_item.setForeground(QColor(t.text_muted))
            table.setItem(row, 3, type_item)

            status_text, status_color, icon_name = self._format_status(record, t)
            status = QTableWidgetItem(status_text)
            status.setIcon(get_icon(icon_name, color=status_color, size=14))
            status.setData(Qt.ItemDataRole.UserRole, str(record.path))
            status.setForeground(QColor(status_color))
            status.setFlags(status.flags() & ~Qt.ItemFlag.ItemIsEditable)
            status.setToolTip(record.conflict_reason or record.error or record.rationale or record.status)
            table.setItem(row, 4, status)

        table.blockSignals(False)
        table.setUpdatesEnabled(True)

        has_records = bool(self.records)
        self.review_table_stack.setCurrentWidget(
            self.review_table_stack.widget(0) if has_records else self.review_empty
        )
        self.review_empty.setVisible(not has_records)

        proposals = sum(1 for r in self.records if r.proposed_name)
        selected = sum(1 for r in self.records if r.selected and r.proposed_name)
        conflicts = sum(1 for r in self.records if r.conflict_reason)
        parts = [
            f"{len(self.records)} file{'s' if len(self.records) != 1 else ''}",
            f"{proposals} name{'s' if proposals != 1 else ''}",
            f"{selected} selected",
        ]
        if conflicts:
            parts.append(f"{conflicts} conflict{'s' if conflicts != 1 else ''}")
        self.review_summary.setText("  ·  ".join(parts))
        self.review_summary.setStyleSheet(
            f"color: {t.warning_fg};" if conflicts else ""
        )
        self.rename_btn.setEnabled(bool(selected))
        self.preview_plan_btn.setEnabled(bool(selected))

        self._filter_table()
        table.verticalScrollBar().setValue(scroll_position)

        if restore_row >= 0 and restore_row < table.rowCount():
            table.blockSignals(True)
            table.selectRow(restore_row)
            table.blockSignals(False)
        elif not self._selected_record_path and table.rowCount() > 0:
            preferred = next((r for r in self.records if r.proposed_name), self.records[0])
            index = next(
                (i for i, r in enumerate(self.records) if str(r.path) == str(preferred.path)),
                0,
            )
            table.blockSignals(True)
            table.selectRow(index)
            table.blockSignals(False)
            self._selected_record_path = str(preferred.path)
            self._update_inspector(preferred)
        else:
            self._update_inspector(None)

    def _format_status(self, record: FileRecord, t) -> tuple[str, str, str]:
        if record.conflict_reason or record.status == "Conflict":
            return "Conflict", t.warning_fg, "warning"
        if record.status == "Analysis failed":
            return "Analysis failed", t.danger_fg, "error"
        if record.status == "Unsupported":
            return "Unsupported", t.text_faint, "info"
        if record.status == "AI suggestion ready":
            return "AI suggestion", t.success_fg, "check_circle"
        if record.status == "Local fallback":
            return "Local suggestion", t.info_fg, "check"
        if record.status == "Metadata fallback":
            return "Metadata", t.info_fg, "info"
        if record.status == "Edited by user":
            return "Edited", t.accent, "edit"
        if record.status == "Needs review":
            return "Needs review", t.warning_fg, "info"
        if record.status == "Ready to analyze":
            return "Discovered", t.text_muted, "clock"
        return record.status or "Discovered", t.text_secondary, "info"

    def _apply_manual_name(self, record: FileRecord, raw_name: str) -> None:
        """Set a user-typed proposed name; an empty value sends the record back to review."""
        value = raw_name.strip()
        if value:
            record.proposed_name = self._sanitize(value, record.extension)
            record.status = "Edited by user"
            record.generation_mode = "manual"
        else:
            record.proposed_name = ""
            record.status = "Needs review"

    def _table_edited(self, item: QTableWidgetItem) -> None:
        path = item.data(Qt.ItemDataRole.UserRole)
        target: FileRecord | None = None
        for record in self.records:
            if str(record.path) != path:
                continue
            target = record
            if item.column() == 0:
                record.selected = item.checkState() == Qt.CheckState.Checked
            elif item.column() == 2:
                self._apply_manual_name(record, item.text())
            break
        self._recompute_collisions()
        self._update_stats()
        self._render_records()
        if target is not None:
            self._update_inspector(target)

    def _on_table_selection_changed(self) -> None:
        items = self.table.selectedItems()
        if not items:
            self._selected_record_path = None
            self._update_inspector(None)
            return
        path = items[0].data(Qt.ItemDataRole.UserRole)
        self._selected_record_path = path
        for record in self.records:
            if str(record.path) == path:
                self._update_inspector(record)
                return
        self._update_inspector(None)

    def _update_inspector(self, record: FileRecord | None) -> None:
        if not hasattr(self, "inspector_filename"):
            return
        t = get_tokens(self.settings.dark_mode)
        if record is None:
            self.inspector_status_badge.setText("No selection")
            self.inspector_status_badge.setObjectName("badgeNeutral")
            self._repolish(self.inspector_status_badge)
            self.inspector_filename.setText("Select a file")
            self.inspector_meta.setText(
                "Choose a row to see its metadata, proposed destination, and extracted content."
            )
            self.inspector_name_edit.setText("")
            self.inspector_name_edit.setEnabled(False)
            self.inspector_apply_btn.setEnabled(False)
            self.inspector_reset_btn.setEnabled(False)
            self.inspector_rationale.setText("—")
            self.inspector_excerpt.setPlainText("")
            self.preview_current.setText("—")
            self.preview_proposed.setText("—")
            self.preview_proposed.setStyleSheet(f"color: {t.text_faint}; font-size: 10pt;")
            self.reveal_btn.setEnabled(False)
            return

        self.inspector_filename.setText(record.name)
        self.inspector_filename.setToolTip(str(record.path))
        folder = record.relative_parent or "current folder"
        self.inspector_meta.setText(
            f"{record.file_type_label} · {record.human_size}\n"
            f"Modified {record.modified_iso} · {folder}"
        )
        self.preview_current.setText(record.name)
        self.preview_current.setToolTip(record.name)
        proposed_display = record.proposed_name or "No proposal yet"
        if self.settings.organize_by_category and record.proposed_name:
            category = self._category_for(record)
            proposed_display = f"{record.proposed_name}\n→ {category}/"
        self.preview_proposed.setText(proposed_display)
        self.preview_proposed.setToolTip(proposed_display)
        color = t.accent if record.proposed_name else t.text_faint
        self.preview_proposed.setStyleSheet(f"color: {color}; font-size: 10pt; font-weight: 700;")

        if record.status == "Analysis failed":
            badge = "badgeDanger"
        elif record.conflict_reason or record.status == "Conflict":
            badge = "badgeWarning"
        elif record.proposed_name:
            badge = "badgeReady"
        else:
            badge = "badgeNeutral"
        self.inspector_status_badge.setText(record.status)
        self.inspector_status_badge.setObjectName(badge)
        self._repolish(self.inspector_status_badge)

        self.inspector_name_edit.setEnabled(True)
        self.inspector_name_edit.setText(record.proposed_name)
        self.inspector_name_edit.setCursorPosition(0)
        self.inspector_name_edit.setToolTip(record.proposed_name)
        self.inspector_apply_btn.setEnabled(True)
        self.inspector_reset_btn.setEnabled(True)
        self.reveal_btn.setEnabled(record.path.exists())

        if record.conflict_reason:
            self.inspector_rationale.setText(f"Conflict · {record.conflict_reason}")
            self.inspector_rationale.setStyleSheet(f"color: {t.warning_fg}; font-size: 8.8pt;")
        elif record.error:
            self.inspector_rationale.setText(f"Error · {record.error}")
            self.inspector_rationale.setStyleSheet(f"color: {t.danger_fg}; font-size: 8.8pt;")
        elif record.rationale:
            self.inspector_rationale.setText(record.rationale)
            self.inspector_rationale.setStyleSheet(f"color: {t.text_secondary}; font-size: 8.8pt;")
        else:
            self.inspector_rationale.setText(
                "Generate names to extract content and build a proposal."
            )
            self.inspector_rationale.setStyleSheet(f"color: {t.text_muted}; font-size: 8.8pt;")

        self.inspector_excerpt.setPlainText(
            record.extracted_text
            or (
                "This format is not read for content; the name is based on metadata."
                if record.status == "Unsupported"
                else "No content extracted yet."
            )
        )

    @staticmethod
    def _repolish(widget: QWidget) -> None:
        widget.style().unpolish(widget)
        widget.style().polish(widget)

    def _inspector_name_committed(self) -> None:
        if not self._selected_record_path:
            return
        value = self.inspector_name_edit.text().strip()
        for record in self.records:
            if str(record.path) != self._selected_record_path:
                continue
            self._apply_manual_name(record, value)
            self._recompute_collisions()
            self._update_stats()
            self._render_records()
            self._update_inspector(record)
            return

    def _inspector_reset_name(self) -> None:
        if not self._selected_record_path:
            return
        for record in self.records:
            if str(record.path) != self._selected_record_path:
                continue
            record.proposed_name = record.name
            record.status = "Edited by user"
            record.generation_mode = "manual"
            self._recompute_collisions()
            self._update_stats()
            self._render_records()
            self._update_inspector(record)
            return

    def _reveal_selected_file(self) -> None:
        if not self._selected_record_path:
            return
        path = Path(self._selected_record_path)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent if path.is_file() else path)))

    # ------------------------------------------------------------------
    # Filtering & selection
    # ------------------------------------------------------------------
    def _filter_table(self) -> None:
        if not hasattr(self, "table"):
            return
        query = self.search.text().casefold().strip()
        filt = self.filter.currentText()

        for row in range(self.table.rowCount()):
            check_item = self.table.item(row, 0)
            path = check_item.data(Qt.ItemDataRole.UserRole) if check_item else ""
            record = next((r for r in self.records if str(r.path) == path), None)
            values = [
                self.table.item(row, col).text().casefold()
                if self.table.item(row, col)
                else ""
                for col in (1, 2, 3, 4)
            ]
            subject = (record.detected_subject if record else "").casefold()
            haystack = " ".join(values) + " " + subject
            visible = query in haystack if query else True

            status = (record.status if record else values[3]).casefold()
            has_name = bool(record.proposed_name) if record else bool(values[1].strip())
            has_conflict = bool(record.conflict_reason) if record else ("conflict" in status)

            if filt == "Ready":
                visible = (
                    visible
                    and has_name
                    and not has_conflict
                    and "failed" not in status
                    and "unsupported" not in status
                )
            elif filt == "Issues":
                visible = visible and (
                    has_conflict
                    or "failed" in status
                    or "unsupported" in status
                    or "needs review" in status
                    or "conflict" in status
                )
            elif filt == "Conflicts":
                visible = visible and (has_conflict or "conflict" in status)
            elif filt == "Edited":
                visible = visible and "edited" in status
            elif filt == "Unsupported":
                visible = visible and "unsupported" in status

            self.table.setRowHidden(row, not visible)

    def select_all(self) -> None:
        self.table.blockSignals(True)
        visible_paths: set[str] = set()
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item and not self.table.isRowHidden(row):
                item.setCheckState(Qt.CheckState.Checked)
                visible_paths.add(str(item.data(Qt.ItemDataRole.UserRole)))
        self.table.blockSignals(False)
        for record in self.records:
            if not visible_paths or str(record.path) in visible_paths:
                record.selected = True
        self._recompute_collisions()
        self._update_stats()

    def deselect_all(self) -> None:
        self.table.blockSignals(True)
        visible_paths: set[str] = set()
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item and not self.table.isRowHidden(row):
                item.setCheckState(Qt.CheckState.Unchecked)
                visible_paths.add(str(item.data(Qt.ItemDataRole.UserRole)))
        self.table.blockSignals(False)
        for record in self.records:
            if not visible_paths or str(record.path) in visible_paths:
                record.selected = False
        self._recompute_collisions()
        self._update_stats()

    # ------------------------------------------------------------------
    # Applying changes
    # ------------------------------------------------------------------
    def _collect_selected_proposals(self) -> list[tuple[Path, str]]:
        selected: list[tuple[Path, str]] = []
        for record in self.records:
            if not (record.selected and record.proposed_name):
                continue
            safe = self._sanitize(record.proposed_name, record.extension)
            if safe != record.proposed_name:
                record.proposed_name = safe
            if self.settings.organize_by_category and self.folder:
                category = self._category_for(record)
                relative = f"{category}/{safe}"
                if record.path.parent != (self.folder / category) or record.path.name != safe:
                    selected.append((record.path, relative))
            elif record.path.name != safe:
                selected.append((record.path, safe))
        return selected

    def preview_batch_plan(self) -> None:
        if not self.folder:
            QMessageBox.information(self, "No folder", "Choose and scan a folder first.")
            return
        self._recompute_collisions()
        if any(r.selected and r.conflict_reason for r in self.records):
            QMessageBox.warning(
                self,
                "Resolve conflicts first",
                "Some selected files still have naming conflicts. Use “Resolve conflicts” "
                "or edit the proposed names, then preview again.",
            )
            return
        selected = self._collect_selected_proposals()
        if not selected:
            QMessageBox.information(
                self,
                "Nothing to preview",
                "No selected file has a changed, valid proposal.",
            )
            return
        dialog = BatchPreviewDialog(
            selected,
            organize_by_category=self.settings.organize_by_category,
            dark_mode=self.settings.dark_mode,
            parent=self,
        )
        if dialog.exec():
            self._execute_rename_batch(selected)

    def apply_renames(self) -> None:
        if self._active_worker is not None:
            return
        if not self.folder:
            QMessageBox.information(self, "No folder", "Choose and scan a folder first.")
            return

        self._recompute_collisions()
        conflicts = [r for r in self.records if r.selected and r.conflict_reason]
        if conflicts:
            reply = QMessageBox.warning(
                self,
                "Conflicts detected",
                f"{len(conflicts)} selected file(s) have conflicts.\n\n"
                f"{conflicts[0].name}\n{conflicts[0].conflict_reason}\n\n"
                "Resolve duplicate names automatically and continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Yes,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            self.resolve_batch_conflicts()

        selected = self._collect_selected_proposals()
        if not selected:
            QMessageBox.information(
                self,
                "Nothing to rename",
                "No selected file has a changed, valid proposal.",
            )
            return

        if self.settings.confirm_before_apply:
            preview_lines = "\n".join(f"{src.name}  →  {name}" for src, name in selected[:10])
            if len(selected) > 10:
                preview_lines += f"\n… and {len(selected) - 10} more"
            mode = (
                "Rename and sort into category folders"
                if self.settings.organize_by_category
                else "Rename in place"
            )
            message = (
                f"{mode} for {len(selected)} file(s)?\n\n{preview_lines}\n\n"
                "Existing files are never overwritten and file contents are never modified."
            )
            if (
                QMessageBox.warning(
                    self,
                    "Confirm changes",
                    message,
                    QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Yes,
                    QMessageBox.StandardButton.Cancel,
                )
                != QMessageBox.StandardButton.Yes
            ):
                return

        self._execute_rename_batch(selected)

    def _execute_rename_batch(self, selected: list[tuple[Path, str]]) -> None:
        if not self.folder:
            return
        report = self.engine.apply(
            self.folder,
            selected,
            allow_subfolders=self.settings.organize_by_category,
        )
        self.refresh_history()
        succeeded = len(report["success"])
        failed = len(report["failed"])
        skipped = len(report["skipped"])

        self.statusBar().showMessage(
            f"Applied · {succeeded} succeeded · {failed} failed · {skipped} skipped"
        )

        if failed:
            self.banner.show_banner(
                "warning",
                f"Finished with {failed} issue{'s' if failed != 1 else ''}",
                f"{succeeded} file(s) were renamed. Remaining files were left untouched.",
                dark_mode=self.settings.dark_mode,
                reduced_motion=self.settings.reduced_motion,
            )
        else:
            self.banner.show_banner(
                "success",
                f"Renamed {succeeded} file{'s' if succeeded != 1 else ''}",
                f"Session {report['session_id']} · undo anytime from History.",
                action_text="Undo session",
                action_callback=self.undo_last,
                dark_mode=self.settings.dark_mode,
                reduced_motion=self.settings.reduced_motion,
            )

        details = (
            f"Session  {report['session_id']}\n"
            f"Renamed  {succeeded}\n"
            f"Skipped  {skipped}\n"
            f"Failed   {failed}"
        )
        if report["failed"]:
            details += "\n\n" + "\n".join(f"{a}: {b}" for a, b in report["failed"][:8])
        QMessageBox.information(self, "Batch complete", details)
        self.start_scan()

    # ------------------------------------------------------------------
    # Undo & history
    # ------------------------------------------------------------------
    def undo_last(self) -> None:
        if (
            QMessageBox.question(
                self,
                "Undo last session",
                "Reverse the most recent completed batch? Existing files are never "
                "overwritten.",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        report = self.engine.undo_last_session()
        restored = len(report.get("success", []))
        issues = len(report.get("failed", []))
        message = f"Restored  {restored}\nIssues    {issues}"
        if issues:
            message += "\n\n" + "\n".join(f"{a}: {b}" for a, b in report.get("failed", [])[:6])
        QMessageBox.information(self, "Undo complete", message)
        if restored:
            self.banner.show_banner(
                "success",
                f"Restored {restored} file{'s' if restored != 1 else ''}",
                "The most recent session was reversed.",
                dark_mode=self.settings.dark_mode,
                reduced_motion=self.settings.reduced_motion,
            )
        self.refresh_history()
        if self.folder:
            self.start_scan()

    def refresh_history(self) -> None:
        if not hasattr(self, "history_table"):
            return
        t = get_tokens(self.settings.dark_mode)
        rows = self.history.recent(500)
        table = self.history_table
        table.setUpdatesEnabled(False)
        table.setRowCount(0)
        for entry in rows:
            row = table.rowCount()
            table.insertRow(row)
            status_text = "Undone" if entry["undone"] else entry["status"]
            values = [
                self._friendly_time(entry["timestamp"]),
                entry["session_id"],
                entry["original_path"],
                entry["new_path"],
                status_text.replace("_", " ").capitalize(),
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setToolTip(str(value))
                if col == 4:
                    if status_text == "success":
                        item.setForeground(QColor(t.success_fg))
                        item.setIcon(get_icon("check_circle", color=t.success_fg, size=13))
                    elif status_text in {"Undone", "restored"}:
                        item.setForeground(QColor(t.info_fg))
                        item.setIcon(get_icon("undo", color=t.info_fg, size=13))
                    else:
                        item.setForeground(QColor(t.warning_fg))
                        item.setIcon(get_icon("warning", color=t.warning_fg, size=13))
                elif col == 0:
                    item.setForeground(QColor(t.text_muted))
                table.setItem(row, col, item)
        table.setUpdatesEnabled(True)

        self.history_count_label.setText(
            f"{len(rows)} recorded operation{'s' if len(rows) != 1 else ''}"
        )
        self.history_stack.setCurrentWidget(self.history_table if rows else self.history_empty)
        self._filter_history_table()

    @staticmethod
    def _friendly_time(iso_value: str) -> str:
        from datetime import datetime

        try:
            stamp = datetime.fromisoformat(str(iso_value))
        except ValueError:
            return str(iso_value)
        today = datetime.now().date()
        if stamp.date() == today:
            return stamp.strftime("Today, %H:%M")
        return stamp.strftime("%d %b %Y, %H:%M")

    def _filter_history_table(self) -> None:
        if not hasattr(self, "history_table") or not hasattr(self, "history_search"):
            return
        query = self.history_search.text().casefold().strip()
        for row in range(self.history_table.rowCount()):
            values = [
                (self.history_table.item(row, col).text().casefold() if self.history_table.item(row, col) else "")
                for col in range(5)
            ]
            self.history_table.setRowHidden(row, bool(query and query not in " ".join(values)))

    def clear_history_records(self) -> None:
        if (
            QMessageBox.question(
                self,
                "Clear history",
                "Delete all recorded sessions? Past batches can no longer be undone.",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        self.history.clear_all()
        self.refresh_history()
        self.statusBar().showMessage("History cleared")

    # ------------------------------------------------------------------
    # Settings and session lifecycle
    # ------------------------------------------------------------------
    def open_settings(self) -> None:
        dialog = SettingsDialog(self.settings, self, history=self.history)
        if dialog.exec():
            self.settings = dialog.settings
            configure_logging(self.settings.log_level)
            self.scope_check.setChecked(self.settings.include_subfolders)
            self.organize_check.setChecked(self.settings.organize_by_category)
            self.quick_style_combo.setCurrentText(self.settings.naming_style)
            self.apply_theme(self.settings.dark_mode)
            self._prune_history()
            self._refresh_status()
            self.statusBar().showMessage("Settings saved")

    def _prune_history(self) -> None:
        """Enforce the "Keep history for N days" setting."""
        try:
            self.history.prune_older_than(self.settings.history_retention_days)
        except sqlite3.Error as exc:
            logger.warning("Could not prune operation history: %s", exc)

    def _refresh_status(self) -> None:
        t = get_tokens(self.settings.dark_mode)
        if self.settings.external_ai_consent and self.settings.api_key:
            self.ai_status.setText(f"AI · {self.settings.model}")
            self.ai_detail.setText("Bounded excerpts are sent to your endpoint")
            color = t.success_fg
        elif self.settings.api_key:
            self.ai_status.setText("Local · key saved")
            self.ai_detail.setText("External AI is off until you consent")
            color = t.warning_fg
        else:
            self.ai_status.setText("Local heuristics")
            self.ai_detail.setText("Files never leave this computer")
            color = t.accent
        self.ai_dot.setPixmap(dot_pixmap(color, 7))

    def clear_session(self) -> None:
        if self._active_worker is not None:
            return
        if (
            self.records
            and QMessageBox.question(
                self,
                "Clear session",
                "Clear the current file list and proposals? Files on disk are not changed.",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        self.records = []
        self._selected_record_path = None
        self.progress.setValue(0)
        self.progress_label.setText("Ready when you are")
        self.banner.setVisible(False)
        self.analyze_btn.setEnabled(False)
        self._update_stats()
        self._render_records()
        self._render_detected([])
        self._update_inspector(None)

    def _set_busy(self, busy: bool, message: str = "Working…") -> None:
        self.scan_btn.setEnabled(not busy)
        self.folder_btn.setEnabled(not busy)
        self.analyze_btn.setEnabled(not busy and bool(self.records))
        self.generate_btn.setEnabled(not busy)
        self.rename_btn.setEnabled(not busy and any(r.selected and r.proposed_name for r in self.records))
        self.cancel_btn.setVisible(busy)
        if busy:
            self.progress_label.setText(message)
        else:
            self._active_worker = None

    def _worker_error(self, message: str) -> None:
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress_label.setText("Operation failed")
        self.banner.show_banner(
            "danger",
            "Operation failed",
            message,
            dark_mode=self.settings.dark_mode,
            reduced_motion=self.settings.reduced_motion,
        )
        QMessageBox.critical(self, "Operation failed", message)
        self.statusBar().showMessage("Operation failed")

    def closeEvent(self, event) -> None:
        if self._active_worker is not None:
            self._active_worker.cancel()
        try:
            self.settings.save()
        except (OSError, RuntimeError) as exc:
            logger.debug("Could not save settings on close: %s", exc)
        try:
            self.history.close()
        except Exception as exc:  # noqa: BLE001 - shutdown must not crash
            logger.debug("Could not close history on exit: %s", exc)
        super().closeEvent(event)
