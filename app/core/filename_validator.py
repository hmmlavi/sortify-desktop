"""Filename sanitization, platform restriction checks, and path boundary validation."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Collection
from pathlib import Path

INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f\x7f]')
RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    "CONIN$",
    "CONOUT$",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
    "COM\u00b9",
    "COM\u00b2",
    "COM\u00b3",
    "LPT\u00b9",
    "LPT\u00b2",
    "LPT\u00b3",
}


def _clean_extension(extension: str) -> str:
    ext = INVALID.sub("", str(extension or "")).strip(" .")
    if not ext:
        return ""
    return "." + ext


def _is_reserved_stem(stem: str) -> bool:
    base = stem.split(".")[0].strip(" _-").upper()
    return base in RESERVED


def sanitize_filename(
    name: str,
    extension: str,
    max_length: int = 100,
    style: str = "Underscore_Separated",
) -> str:
    """Sanitize a proposed filename stem and extension for cross-platform and Windows safety."""
    name = unicodedata.normalize("NFC", str(name or ""))
    ext = _clean_extension(unicodedata.normalize("NFC", str(extension or "")))
    if ext and name.casefold().endswith(ext.casefold()):
        name = name[: -len(ext)]

    # Strip path traversal sequences and invalid filesystem characters
    name = INVALID.sub(" ", name)
    name = re.sub(r"\.{2,}", ".", name)

    if style == "Underscore_Separated":
        name = re.sub(r"[\s\-]+", "_", name)
        name = re.sub(r"_+", "_", name)
    elif style == "Readable With Spaces":
        name = re.sub(r"[_\-]+", " ", name)
        name = re.sub(r"\s+", " ", name)
    elif style == "Title Case":
        name = re.sub(r"[_\-]+", " ", name)
        name = " ".join(
            (w if (w.isupper() and len(w) <= 5) else w.capitalize())
            for w in name.split()
        )
    elif style == "Hyphen-Separated":
        name = re.sub(r"[\s_]+", "-", name)
        name = re.sub(r"-+", "-", name)
    elif style == "camelCase":
        words = [w for w in re.split(r"[\s_\-]+", name) if w]
        if words:
            name = words[0].lower() + "".join(w.capitalize() for w in words[1:])
        else:
            name = ""
    else:
        name = re.sub(r"[\s\-]+", "_", name)
        name = re.sub(r"_+", "_", name)

    name = name.strip(" ._-")
    if not name:
        name = "Renamed_File"

    if _is_reserved_stem(name):
        name = "_" + name

    max_length = max(12, int(max_length or 100))
    budget = max(1, max_length - len(ext))
    name = name[:budget].rstrip(" ._-") or "File"

    # Re-verify reserved stem after length truncation
    if _is_reserved_stem(name):
        name = ("_" + name)[:budget].rstrip(" ._-") or "_File"

    return name + ext


def validate_filename_text(filename: str) -> str | None:
    """Validate a single filename string without modifying it."""
    if not filename or filename in {".", ".."}:
        return "Filename cannot be empty."
    if "/" in filename or "\\" in filename:
        return "Filename must not contain directory separators."
    if INVALID.search(filename):
        return "Filename contains characters not allowed on Windows (< > : \" / \\ | ? *)."
    if filename.endswith((" ", ".")):
        return "Filename cannot end with a space or period on Windows."
    if _is_reserved_stem(filename):
        return f"'{filename.split('.')[0]}' is a reserved Windows device name."
    if len(filename) > 255:
        return "Filename exceeds the 255-character filesystem limit."
    return None


def validate_destination(
    source: Path,
    destination: Path,
    allowed_root: Path,
    allow_subfolders: bool = False,
) -> str | None:
    """Validate that moving/renaming source -> destination stays within allowed boundaries."""
    try:
        if source.is_symlink() or destination.is_symlink():
            return "Symbolic links cannot be renamed for security reasons."

        root = allowed_root.resolve()
        src_resolved = source.resolve()
        src_parent = src_resolved.parent
        dest_parent = destination.parent.resolve()

        if src_parent != root and root not in src_parent.parents:
            return "Source is outside the selected folder scope."

        if not allow_subfolders:
            if dest_parent != src_parent:
                return "Renaming must not move files to another directory."
        else:
            if dest_parent != root and root not in dest_parent.parents:
                return "Destination is outside the selected folder scope."

        if destination.name in {"", ".", ".."}:
            return "Invalid destination filename."

        name_err = validate_filename_text(destination.name)
        if name_err:
            return name_err

        if destination.exists():
            try:
                same_file = destination.resolve() == src_resolved
            except OSError:
                same_file = False
            if not same_file:
                return "A file with this destination name already exists."

        return None
    except OSError as e:
        return f"Path validation failed: {e}"


def resolve_unique_name(
    proposed_name: str,
    extension: str,
    taken_casefold: Collection[str],
    max_length: int = 100,
    style: str = "Underscore_Separated",
) -> str:
    """Generate a non-colliding filename by appending a numeric suffix (_2, _3, ...)."""
    base_clean = sanitize_filename(proposed_name, extension, max_length, style)
    if base_clean.casefold() not in taken_casefold:
        return base_clean

    ext = _clean_extension(extension)
    stem = base_clean[: -len(ext)] if ext and base_clean.casefold().endswith(ext.casefold()) else base_clean
    sep = "-" if style == "Hyphen-Separated" else (" " if style in {"Readable With Spaces", "Title Case"} else "_")

    counter = 2
    while counter < 10_000:
        suffix = f"{sep}{counter}"
        budget = max(1, max_length - len(ext) - len(suffix))
        candidate = f"{stem[:budget].rstrip(' ._-')}{suffix}{ext}"
        if candidate.casefold() not in taken_casefold:
            return candidate
        counter += 1
    return base_clean
