"""Filesystem scanning with boundary enforcement, symlink protection, and cancellation."""

from __future__ import annotations

import os
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from app.models.file_record import FileRecord

SUPPORTED = {
    ".pdf",
    ".docx",
    ".txt",
    ".md",
    ".pptx",
    ".xlsx",
    ".csv",
    ".tsv",
    ".json",
    ".yaml",
    ".yml",
    ".rst",
    ".html",
    ".htm",
    ".rtf",
    ".log",
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".gif",
    ".bmp",
    ".tiff",
}

IGNORED_NAMES = {
    ".ds_store",
    "thumbs.db",
    "desktop.ini",
}

TEMP_PREFIXES = (
    ".sortify-tmp-",
    ".renova-tmp-",
    "~$",
)


class ScanError(Exception):
    """Raised when a target folder cannot be accessed or scanned."""


def _is_ignored_name(name: str) -> bool:
    low = name.lower()
    if low in IGNORED_NAMES:
        return True
    return any(low.startswith(prefix) for prefix in TEMP_PREFIXES)


def scan_folder(
    folder: Path,
    include_subfolders: bool = False,
    skip_symlinks: bool = True,
    cancel_check: Callable[[], bool] | None = None,
    progress_callback: Callable[[int, str], None] | None = None,
) -> list[FileRecord]:
    """Scan a directory and return discovered FileRecords sorted by relative path."""
    try:
        raw_folder = Path(folder).expanduser()
        if skip_symlinks and raw_folder.is_symlink():
            raise ScanError(f"Refusing to scan symbolic link directory: {raw_folder}")
        resolved_folder = raw_folder.resolve()
    except OSError as e:
        raise ScanError(f"Could not resolve folder path: {e}") from e

    if not resolved_folder.exists() or not resolved_folder.is_dir():
        raise ScanError(f"Folder does not exist or is not a directory: {resolved_folder}")

    records: list[FileRecord] = []
    discovered_count = 0

    def _visit_dir(current_dir: Path) -> None:
        nonlocal discovered_count
        if cancel_check and cancel_check():
            return
        try:
            entries = sorted(os.scandir(current_dir), key=lambda e: e.name.casefold())
        except (OSError, PermissionError):
            return

        subdirs: list[Path] = []
        for entry in entries:
            if cancel_check and cancel_check():
                return
            if _is_ignored_name(entry.name):
                continue
            entry_path = Path(entry.path)
            try:
                if entry.is_symlink():
                    if skip_symlinks:
                        continue
                    resolved_target = entry_path.resolve()
                    if resolved_target != resolved_folder and resolved_folder not in resolved_target.parents:
                        continue
                if entry.is_dir(follow_symlinks=not skip_symlinks):
                    if include_subfolders and not entry.name.startswith("."):
                        subdirs.append(entry_path)
                    continue
                if not entry.is_file(follow_symlinks=not skip_symlinks):
                    continue

                stat = entry.stat(follow_symlinks=not skip_symlinks)
                ext = entry_path.suffix.lower()
                is_supported = ext in SUPPORTED
                records.append(
                    FileRecord(
                        path=entry_path,
                        size_bytes=stat.st_size,
                        extension=ext,
                        modified_iso=datetime.fromtimestamp(stat.st_mtime).isoformat(
                            timespec="seconds"
                        ),
                        status="Ready to analyze" if is_supported else "Unsupported",
                        selected=is_supported,
                        root_path=resolved_folder,
                    )
                )
                discovered_count += 1
                if progress_callback and (discovered_count <= 20 or discovered_count % 10 == 0):
                    progress_callback(discovered_count, entry.name)
            except (OSError, PermissionError):
                continue

        for subdir in subdirs:
            _visit_dir(subdir)

    _visit_dir(resolved_folder)
    return sorted(records, key=lambda r: (r.relative_parent.casefold(), r.path.name.casefold()))
