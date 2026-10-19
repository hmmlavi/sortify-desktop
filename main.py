"""Sortify desktop application entry point with diagnostic CLI mode and crash safety."""

from __future__ import annotations

import argparse
import io
import json
import logging
import platform
import sys
import traceback

from app.config import (
    APP_DIR,
    APP_NAME,
    APP_ORGANIZATION,
    APP_TAGLINE,
    APP_VERSION,
    CONFIG_PATH,
    DB_PATH,
    LOG_PATH,
    Settings,
)
from app.core.operation_history import OperationHistory
from app.utils.logging_config import configure_logging, redact_secrets
from app.utils.resources import get_bundle_root, is_frozen, verify_runtime_assets


def _install_crash_hook() -> None:
    """Ensure unhandled exceptions are redacted, logged, and surfaced cleanly."""
    original_hook = sys.excepthook

    def _handle_exception(exc_type, exc_value, exc_tb) -> None:
        formatted = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        safe_trace = redact_secrets(formatted)
        logging.getLogger("sortify.crash").critical(
            "Unhandled exception:\n%s", safe_trace
        )
        try:
            from PySide6.QtWidgets import QApplication, QMessageBox

            if QApplication.instance() is not None:
                QMessageBox.critical(
                    None,
                    f"{APP_NAME} — Unexpected Error",
                    f"An unexpected error occurred:\n\n{redact_secrets(str(exc_value))}\n\n"
                    f"Diagnostic details were written to:\n{LOG_PATH}",
                )
                return
        except Exception as gui_exc:  # noqa: BLE001
            logging.getLogger("sortify.crash").debug("GUI crash dialog unavailable: %s", gui_exc)
        original_hook(exc_type, exc_value, exc_tb)

    sys.excepthook = _handle_exception


def _ensure_console_streams() -> None:
    """Give windowed Windows builds usable stdout/stderr.

    PyInstaller's windowed bootloader (and a GUI-subsystem launcher) starts the
    process without console streams. When the executable is started from a
    console we attach to that console so ``--diagnose`` and ``--version`` work;
    otherwise a harmless in-memory stream keeps every write from raising.
    """
    if sys.stdout is not None and sys.stderr is not None:
        return
    if sys.platform == "win32":
        try:
            import ctypes

            if ctypes.windll.kernel32.AttachConsole(-1):
                # These streams live for the rest of the process by design.
                sys.stdout = open("CONOUT$", "w", encoding="utf-8", buffering=1)  # noqa: SIM115
                sys.stderr = open("CONOUT$", "w", encoding="utf-8", buffering=1)  # noqa: SIM115
                return
        except (OSError, AttributeError):
            logging.getLogger(__name__).debug("Console attachment failed", exc_info=True)
    if sys.stdout is None:
        sys.stdout = io.StringIO()
    if sys.stderr is None:
        sys.stderr = io.StringIO()


def run_diagnostics() -> int:
    """Execute a non-interactive startup and environment health verification."""
    _ensure_console_streams()
    settings = Settings.load()
    configure_logging(settings.log_level)
    history = OperationHistory()
    assets = verify_runtime_assets()

    report = {
        "application": APP_NAME,
        "version": APP_VERSION,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "frozen": is_frozen(),
        "bundle_root": str(get_bundle_root()),
        "app_data_dir": str(APP_DIR),
        "config_path": str(CONFIG_PATH),
        "db_path": str(DB_PATH),
        "log_path": str(LOG_PATH),
        "db_in_memory_fallback": history.in_memory_fallback,
        "assets": assets,
        "all_assets_present": all(assets.values()),
    }
    payload = json.dumps(report, indent=2)
    try:
        (APP_DIR / "diagnostics.json").write_text(payload + "\n", encoding="utf-8")
    except OSError as exc:
        logging.getLogger(__name__).debug("Could not persist diagnostics report: %s", exc)
    print(payload)
    return 0 if report["all_assets_present"] else 1


def main(argv: list[str] | None = None) -> int:
    _ensure_console_streams()
    parser = argparse.ArgumentParser(
        prog="sortify",
        description=f"{APP_NAME} v{APP_VERSION} — {APP_TAGLINE}",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"{APP_NAME} {APP_VERSION}",
    )
    parser.add_argument(
        "--diagnose",
        action="store_true",
        help="Run non-interactive startup, asset, and database diagnostics and exit.",
    )
    args, qt_args = parser.parse_known_args(argv)

    if args.diagnose:
        return run_diagnostics()

    settings = Settings.load()
    configure_logging(settings.log_level)
    _install_crash_hook()
    logging.getLogger("sortify.startup").info("Starting %s v%s", APP_NAME, APP_VERSION)

    from PySide6.QtWidgets import QApplication

    from app.ui.icons import get_brand_icon
    from app.ui.main_window import MainWindow

    app = QApplication([sys.argv[0], *qt_args])
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName(APP_ORGANIZATION)
    app.setStyle("Fusion")
    app.setWindowIcon(get_brand_icon())

    window = MainWindow(settings=settings)
    window.show()
    return int(app.exec())


if __name__ == "__main__":
    sys.exit(main())
