"""Sortify settings dialog: naming, AI & privacy, appearance, diagnostics."""

from __future__ import annotations

import copy
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.config import (
    APP_DIR,
    APP_NAME,
    APP_TAGLINE,
    APP_VERSION,
    LOG_PATH,
    VALID_LOG_LEVELS,
    VALID_NAMING_STYLES,
    Settings,
    is_loopback_url,
    validate_api_url,
)
from app.ui.components import GlassDialog, GlassPanel, divider
from app.ui.icons import get_brand_pixmap, get_icon
from app.ui.styles import build_stylesheet, get_tokens


class SettingsDialog(GlassDialog):
    def __init__(self, settings: Settings, parent=None, history=None):
        super().__init__(dark_mode=settings.dark_mode, parent=parent)
        self.settings = settings
        self.history = history
        self.setWindowTitle(f"{APP_NAME} · Settings")
        self.resize(720, 660)
        self.setMinimumSize(620, 560)
        self.setStyleSheet(build_stylesheet(settings.dark_mode))
        t = get_tokens(settings.dark_mode)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(14)

        header = QHBoxLayout()
        header.setSpacing(12)
        logo = QLabel()
        logo.setFixedSize(40, 40)
        logo.setPixmap(get_brand_pixmap(40))
        header.addWidget(logo)
        title_col = QVBoxLayout()
        title_col.setSpacing(1)
        title = QLabel("Settings")
        title.setObjectName("pageTitle")
        subtitle = QLabel("How Sortify names, sorts, and protects your files.")
        subtitle.setObjectName("muted")
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        header.addLayout(title_col, 1)

        self.theme_badge = QLabel("Charcoal" if settings.dark_mode else "Smoke")
        self.theme_badge.setObjectName("badgeNeutral")
        header.addWidget(self.theme_badge, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(header)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        layout.addWidget(self.tabs, 1)
        self.tabs.addTab(self._build_naming_tab(), "Naming and workflow")
        self.tabs.addTab(self._build_ai_tab(), "AI and privacy")
        self.tabs.addTab(self._build_appearance_tab(), "Appearance and system")

        footer = QHBoxLayout()
        footer.setSpacing(8)
        reset = QPushButton("Restore defaults")
        reset.setObjectName("ghost")
        reset.clicked.connect(self._restore_defaults)
        footer.addWidget(reset)
        footer.addStretch()

        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        save = QPushButton("Save settings")
        save.setObjectName("primary")
        save.setIcon(get_icon("check", color=t.text_on_accent, size=15))
        save.clicked.connect(self.save_settings)
        footer.addWidget(cancel)
        footer.addWidget(save)
        layout.addLayout(footer)

    # ------------------------------------------------------------------
    # Tabs
    # ------------------------------------------------------------------
    def _scrollable(self, inner: QWidget) -> QScrollArea:
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.Shape.NoFrame)
        area.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        inner.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        area.setWidget(inner)
        return area

    def _build_naming_tab(self) -> QWidget:
        page = QWidget()
        page.setObjectName("page")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        form = QFormLayout()
        form.setSpacing(12)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

        self.style = QComboBox()
        self.style.addItems(list(VALID_NAMING_STYLES))
        self.style.setCurrentText(self.settings.naming_style)

        self.maxlen = QSpinBox()
        self.maxlen.setRange(20, 220)
        self.maxlen.setValue(self.settings.max_filename_length)
        self.maxlen.setSuffix(" characters")

        self.custom_prefix = QLineEdit(self.settings.custom_prefix)
        self.custom_prefix.setPlaceholderText("Optional prefix, e.g. Project Atlas")
        self.custom_prefix.setMaxLength(30)

        folder_row = QHBoxLayout()
        folder_row.setSpacing(6)
        self.default_folder_edit = QLineEdit(self.settings.default_folder)
        self.default_folder_edit.setPlaceholderText("Optional starting folder")
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._choose_default_folder)
        folder_row.addWidget(self.default_folder_edit, 1)
        folder_row.addWidget(browse)

        form.addRow("Naming style", self.style)
        form.addRow("Maximum length", self.maxlen)
        form.addRow("Prefix", self.custom_prefix)
        form.addRow("Default folder", folder_row)
        layout.addLayout(form)

        layout.addWidget(divider(self.settings.dark_mode))

        self.prepend_date = QCheckBox("Start names with the file date (YYYY-MM-DD)")
        self.prepend_date.setChecked(self.settings.prepend_date)
        self.organize_by_category = QCheckBox("Sort renamed files into category folders")
        self.organize_by_category.setChecked(self.settings.organize_by_category)
        self.subfolders = QCheckBox("Include subfolders when scanning")
        self.subfolders.setChecked(self.settings.include_subfolders)
        self.confirm_apply = QCheckBox("Show a preview before applying changes")
        self.confirm_apply.setChecked(self.settings.confirm_before_apply)
        for widget in (
            self.prepend_date,
            self.organize_by_category,
            self.subfolders,
            self.confirm_apply,
        ):
            layout.addWidget(widget)
        layout.addStretch()
        return self._scrollable(page)

    def _build_ai_tab(self) -> QWidget:
        page = QWidget()
        page.setObjectName("page")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        note = QLabel(
            "Sortify works fully offline. Add an OpenAI-compatible endpoint only if you want "
            "model-written names; excerpts are sent to that endpoint and nowhere else."
        )
        note.setObjectName("muted")
        note.setWordWrap(True)
        layout.addWidget(note)

        form = QFormLayout()
        form.setSpacing(11)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

        self.base = QLineEdit(self.settings.api_base_url)
        self.base.setPlaceholderText("https://api.openai.com/v1")

        self.model = QLineEdit(self.settings.model)
        self.model.setPlaceholderText("gpt-4o-mini")

        key_row = QHBoxLayout()
        key_row.setSpacing(6)
        self.key = QLineEdit(self.settings.api_key)
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        self.key.setPlaceholderText("Stored in the operating system credential store")
        self.toggle_key_btn = QPushButton("Show")
        self.toggle_key_btn.setObjectName("ghost")
        self.toggle_key_btn.setCheckable(True)
        self.toggle_key_btn.toggled.connect(self._toggle_key_visibility)
        key_row.addWidget(self.key, 1)
        key_row.addWidget(self.toggle_key_btn)

        self.extract = QSpinBox()
        self.extract.setRange(500, 100000)
        self.extract.setSingleStep(1000)
        self.extract.setValue(self.settings.max_extract_chars)
        self.extract.setSuffix(" characters")

        self.timeout = QSpinBox()
        self.timeout.setRange(5, 300)
        self.timeout.setValue(self.settings.request_timeout_seconds)
        self.timeout.setSuffix(" seconds")

        self.concurrency = QSpinBox()
        self.concurrency.setRange(1, 8)
        self.concurrency.setValue(self.settings.max_concurrent_requests)
        self.concurrency.setSuffix(" requests")

        form.addRow("API base URL", self.base)
        form.addRow("Model", self.model)
        form.addRow("API key", key_row)
        form.addRow("Excerpt limit", self.extract)
        form.addRow("Request timeout", self.timeout)
        form.addRow("Parallel requests", self.concurrency)
        layout.addLayout(form)

        self.consent = QCheckBox(
            "I allow bounded excerpts of selected files to be sent to this endpoint"
        )
        self.consent.setChecked(self.settings.external_ai_consent)
        layout.addWidget(self.consent)

        self.skip_symlinks = QCheckBox("Skip symbolic links while scanning (recommended)")
        self.skip_symlinks.setChecked(self.settings.skip_symlinks)
        layout.addWidget(self.skip_symlinks)

        card = GlassPanel(
            "subtlePanel",
            dark_mode=self.settings.dark_mode,
            radius=12,
            tint="subtle",
            backdrop=self.backdrop,
        )
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(13, 11, 13, 11)
        card_layout.setSpacing(4)
        card_title = QLabel("Privacy")
        card_title.setObjectName("eyebrow")
        body = QLabel(
            "API keys are stored only in Windows Credential Manager or your OS keyring. "
            "They are never written to settings.json or logs. With external AI off, no file "
            "content leaves this computer."
        )
        body.setObjectName("muted")
        body.setWordWrap(True)
        card_layout.addWidget(card_title)
        card_layout.addWidget(body)
        layout.addWidget(card)
        layout.addStretch()
        return self._scrollable(page)

    def _build_appearance_tab(self) -> QWidget:
        page = QWidget()
        page.setObjectName("page")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        self.dark_mode_check = QCheckBox("Use the Charcoal (dark) appearance")
        self.dark_mode_check.setChecked(self.settings.dark_mode)
        self.reduced = QCheckBox("Reduce motion")
        self.reduced.setChecked(self.settings.reduced_motion)
        self.cache_check = QCheckBox("Cache suggestions for unchanged files")
        self.cache_check.setChecked(self.settings.cache_enabled)
        for widget in (self.dark_mode_check, self.reduced, self.cache_check):
            layout.addWidget(widget)

        layout.addWidget(divider(self.settings.dark_mode))

        form = QFormLayout()
        form.setSpacing(12)
        self.log_level_combo = QComboBox()
        self.log_level_combo.addItems(list(VALID_LOG_LEVELS))
        self.log_level_combo.setCurrentText(self.settings.log_level)
        self.retention_spin = QSpinBox()
        self.retention_spin.setRange(1, 3650)
        self.retention_spin.setValue(self.settings.history_retention_days)
        self.retention_spin.setSuffix(" days")
        form.addRow("Log level", self.log_level_combo)
        form.addRow("Keep history for", self.retention_spin)
        layout.addLayout(form)

        maintenance = QHBoxLayout()
        clear_cache = QPushButton("Clear suggestion cache")
        clear_cache.clicked.connect(self._clear_cache)
        maintenance.addWidget(clear_cache)
        maintenance.addStretch()
        layout.addLayout(maintenance)

        layout.addWidget(divider(self.settings.dark_mode))

        about = QLabel(
            f"{APP_NAME} {APP_VERSION} · {APP_TAGLINE}\n"
            f"Data folder · {APP_DIR}\n"
            f"Log file · {LOG_PATH}\n"
            f"Runtime · Python {sys.version.split()[0]}"
        )
        about.setObjectName("finePrint")
        about.setWordWrap(True)
        about.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(about)
        layout.addStretch()
        return self._scrollable(page)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def _toggle_key_visibility(self, checked: bool) -> None:
        self.key.setEchoMode(
            QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
        )
        self.toggle_key_btn.setText("Hide" if checked else "Show")

    def _choose_default_folder(self) -> None:
        start = self.default_folder_edit.text().strip() or str(Path.home())
        chosen = QFileDialog.getExistingDirectory(self, "Choose a default folder", start)
        if chosen:
            self.default_folder_edit.setText(str(Path(chosen).resolve()))

    def _clear_cache(self) -> None:
        if self.history:
            self.history.clear_cache()
        QMessageBox.information(
            self, "Cache cleared", "Cached filename suggestions were removed."
        )

    def _restore_defaults(self) -> None:
        defaults = Settings()
        self.base.setText(defaults.api_base_url)
        self.model.setText(defaults.model)
        self.style.setCurrentText(defaults.naming_style)
        self.maxlen.setValue(defaults.max_filename_length)
        self.extract.setValue(defaults.max_extract_chars)
        self.timeout.setValue(defaults.request_timeout_seconds)
        self.concurrency.setValue(defaults.max_concurrent_requests)
        self.subfolders.setChecked(defaults.include_subfolders)
        self.consent.setChecked(defaults.external_ai_consent)
        self.reduced.setChecked(defaults.reduced_motion)
        self.dark_mode_check.setChecked(defaults.dark_mode)
        self.cache_check.setChecked(defaults.cache_enabled)
        self.prepend_date.setChecked(defaults.prepend_date)
        self.custom_prefix.setText(defaults.custom_prefix)
        self.organize_by_category.setChecked(defaults.organize_by_category)
        self.confirm_apply.setChecked(defaults.confirm_before_apply)
        self.skip_symlinks.setChecked(defaults.skip_symlinks)
        self.log_level_combo.setCurrentText(defaults.log_level)
        self.retention_spin.setValue(defaults.history_retention_days)
        self.default_folder_edit.setText(defaults.default_folder)

    def save_settings(self) -> None:
        ok, url_or_error = validate_api_url(self.base.text().strip())
        if not ok:
            QMessageBox.warning(self, "Invalid URL", url_or_error)
            return

        if url_or_error.startswith("http://") and not is_loopback_url(url_or_error) and self.key.text().strip():
            reply = QMessageBox.warning(
                self,
                "Unencrypted endpoint",
                "This endpoint uses plain HTTP while an API key is configured. Sending the "
                "key over HTTP is insecure.\n\nSwitch the URL to https://?",
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No
                | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Yes,
            )
            if reply == QMessageBox.StandardButton.Cancel:
                return
            if reply == QMessageBox.StandardButton.Yes:
                url_or_error = "https://" + url_or_error[len("http://"):]

        default_folder = self.default_folder_edit.text().strip()
        if default_folder and not Path(default_folder).expanduser().is_dir():
            QMessageBox.warning(
                self, "Folder unavailable", "The default folder does not exist."
            )
            return

        updated = copy.copy(self.settings)
        updated.api_base_url = url_or_error
        updated.model = self.model.text().strip() or "gpt-4o-mini"
        updated.api_key = self.key.text().strip()
        updated.naming_style = self.style.currentText()
        updated.max_filename_length = self.maxlen.value()
        updated.max_extract_chars = self.extract.value()
        updated.request_timeout_seconds = self.timeout.value()
        updated.max_concurrent_requests = self.concurrency.value()
        updated.include_subfolders = self.subfolders.isChecked()
        updated.external_ai_consent = self.consent.isChecked()
        updated.reduced_motion = self.reduced.isChecked()
        updated.dark_mode = self.dark_mode_check.isChecked()
        updated.cache_enabled = self.cache_check.isChecked()
        updated.default_folder = default_folder
        updated.prepend_date = self.prepend_date.isChecked()
        updated.custom_prefix = self.custom_prefix.text().strip()
        updated.organize_by_category = self.organize_by_category.isChecked()
        updated.confirm_before_apply = self.confirm_apply.isChecked()
        updated.skip_symlinks = self.skip_symlinks.isChecked()
        updated.log_level = self.log_level_combo.currentText()
        updated.history_retention_days = self.retention_spin.value()

        try:
            updated.save()
        except Exception as exc:  # noqa: BLE001 - reported to the user
            QMessageBox.critical(self, "Could not store the API key", str(exc))
            return
        self.settings = updated
        self.accept()
