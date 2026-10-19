"""Runtime resource resolution supporting both source execution and PyInstaller frozen bundles."""

from __future__ import annotations

import sys
from pathlib import Path


def is_frozen() -> bool:
    """Return True when running inside a PyInstaller frozen application bundle."""
    return bool(getattr(sys, "frozen", False))


def get_bundle_root() -> Path:
    """Return the base directory containing bundled application assets."""
    if is_frozen():
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass).resolve()
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent.parent


def get_asset_path(relative_path: str) -> Path:
    """Resolve an asset path (e.g. 'assets/sortify-icon.svg') in source or frozen mode."""
    clean_rel = relative_path.lstrip("/\\")
    candidate = get_bundle_root() / clean_rel
    if candidate.exists():
        return candidate
    # Fallback for one-folder PyInstaller builds where assets may sit next to executable
    exe_dir_candidate = Path(sys.executable).resolve().parent / clean_rel
    if exe_dir_candidate.exists():
        return exe_dir_candidate
    return candidate


def verify_runtime_assets() -> dict[str, bool]:
    """Verify presence of core brand and icon assets."""
    required = [
        "assets/sortify-icon.svg",
        "assets/sortify-logo.svg",
        "assets/sortify.ico",
        "assets/checkmark-dark.svg",
        "assets/checkmark-light.svg",
    ]
    return {rel: get_asset_path(rel).is_file() for rel in required}
