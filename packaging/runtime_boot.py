"""Startup shim for the portable Windows build.

The native launcher starts this module instead of ``main.py`` so that failures
which happen before the application installs its own crash handler (missing
wheels, broken Qt plugins, a corrupted runtime) are reported instead of causing
a silent exit.  PyInstaller builds call ``main.py`` directly and keep their own
handling.
"""

from __future__ import annotations

import os
import re
import runpy
import sys
import traceback
from pathlib import Path

_SECRET_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"(?i)(api[_-]?key\s*[=:]\s*)\S+"),
)


def _redact(text: str) -> str:
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub(lambda match: match.group(1) + "<redacted>" if match.groups() else "<redacted>", text)
    return text


def _startup_log() -> Path:
    # Same data-directory rule as app/config.py, so the log lands next to the app data.
    custom = os.environ.get("SORTIFY_DATA_DIR", "").strip()
    if custom:
        base = Path(custom).expanduser()
    else:
        base = Path(os.environ.get("APPDATA", Path.home())) / "Sortify"
    return base / "startup-error.log"


def _report_failure(exc: BaseException) -> int:
    details = _redact("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
    log_path = _startup_log()
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(details, encoding="utf-8")
    except OSError:
        log_path = Path("unavailable")

    message = (
        "Sortify could not start.\n\n"
        f"{_redact(str(exc)) or type(exc).__name__}\n\n"
        f"Technical details were written to:\n{log_path}\n\n"
        "If the problem persists, reinstall Sortify from the original download."
    )
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, message, "Sortify", 0x00000010)
    except Exception:  # noqa: BLE001 - a dialog is best-effort; stderr is the fallback
        print(message, file=sys.stderr)
    return 1


def main() -> int:
    entry_point = Path(__file__).resolve().with_name("main.py")
    if not entry_point.is_file():
        return _report_failure(FileNotFoundError("main.py is missing from the Sortify folder"))
    try:
        runpy.run_path(str(entry_point), run_name="__main__")
    except SystemExit:
        raise
    except BaseException as exc:  # noqa: BLE001 - must report every startup failure
        return _report_failure(exc)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
