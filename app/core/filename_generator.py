"""Intelligent filename generation using external AI or deterministic local heuristics."""

from __future__ import annotations

import re
from pathlib import Path

from app.core.filename_validator import sanitize_filename

STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "this",
    "that",
    "are",
    "was",
    "were",
    "into",
    "your",
    "you",
    "about",
    "document",
    "file",
    "final",
    "new",
    "copy",
    "version",
    "untitled",
    "page",
    "sheet",
    "title",
    "subject",
}

CATEGORY_MAP = {
    ".pdf": "Documents",
    ".docx": "Documents",
    ".rtf": "Documents",
    ".html": "Documents",
    ".htm": "Documents",
    ".txt": "Notes_and_Text",
    ".md": "Notes_and_Text",
    ".rst": "Notes_and_Text",
    ".log": "Notes_and_Text",
    ".xlsx": "Spreadsheets",
    ".csv": "Spreadsheets",
    ".tsv": "Spreadsheets",
    ".pptx": "Presentations",
    ".jpg": "Images",
    ".jpeg": "Images",
    ".png": "Images",
    ".webp": "Images",
    ".gif": "Images",
    ".bmp": "Images",
    ".tiff": "Images",
    ".json": "Data_and_Config",
    ".yaml": "Data_and_Config",
    ".yml": "Data_and_Config",
}


def suggest_category(extension: str, content_kind: str = "") -> str:
    """Return a clean organization folder name based on file type and content kind."""
    ext = (extension or "").lower()
    if ext in CATEGORY_MAP:
        return CATEGORY_MAP[ext]
    if content_kind == "spreadsheet":
        return "Spreadsheets"
    if content_kind == "presentation":
        return "Presentations"
    if content_kind == "image":
        return "Images"
    if content_kind in {"pdf", "document"}:
        return "Documents"
    return "Other_Files"


def _apply_affixes(
    stem: str,
    prepend_date: bool = False,
    date_iso: str = "",
    custom_prefix: str = "",
) -> str:
    parts: list[str] = []
    if custom_prefix and custom_prefix.strip():
        parts.append(custom_prefix.strip(" _-"))
    if prepend_date:
        date_part = (date_iso or "")[:10]
        if re.match(r"^\d{4}-\d{2}-\d{2}$", date_part) and date_part not in stem:
            parts.append(date_part)
    parts.append(stem)
    return " ".join(p for p in parts if p)


def fallback_suggestion(
    filename: str,
    extension: str,
    content: str,
    style: str,
    max_length: int,
    prepend_date: bool = False,
    date_iso: str = "",
    custom_prefix: str = "",
) -> dict:
    """Generate a deterministic, evidence-based filename from extracted text or metadata."""
    raw_content = (content or "").strip()

    # Special handling if content is synthetic local image metadata without an EXIF description
    if raw_content.startswith("Image ") and "Description:" not in raw_content:
        orig_stem = Path(filename).stem
        cleaned_orig = re.sub(r"[_\-]+", " ", orig_stem).strip()
        # Extract resolution or capture date from metadata if original name is generic
        dim_match = re.search(r"\b(\d{2,5}x\d{2,5})\b", raw_content)
        date_match = re.search(r"Captured:\s*(\d{4}):(\d{2}):(\d{2})", raw_content)
        words = [
            w.strip("._-")
            for w in re.split(r"[\s,.;:!?()\[\]{}<>\"'/\\|+=-]+", cleaned_orig)
            if w.strip("._-") and w.strip("._-").lower() not in {"copy", "final", "new"}
        ]
        if date_match and len(words) <= 2:
            words.insert(0, f"{date_match.group(1)}-{date_match.group(2)}-{date_match.group(3)}")
        if dim_match and (not words or words[0].lower() in {"img", "dsc", "image", "photo", "screenshot"}):
            words.append(dim_match.group(1))
        stem = " ".join(words[:6]) if words else orig_stem
        stem = _apply_affixes(stem, prepend_date=prepend_date, date_iso=date_iso, custom_prefix=custom_prefix)
        name = sanitize_filename(stem, extension, max_length, style)
        return {
            "name": name,
            "subject": f"Image ({dim_match.group(1)})" if dim_match else "Image asset",
            "rationale": "Local fallback based on image metadata and filename; not AI-generated.",
        }

    # Prefer the first non-empty heading or title line when structured text is present
    first_lines = [
        line.strip(" #*-_|\t")
        for line in raw_content.splitlines()
        if line.strip(" #*-_|\t")
    ]
    focus_text = " ".join(first_lines[:4]) if first_lines else raw_content
    focus_text = re.sub(r"^(Title|Subject|Sheet|JSON keys):\s*", "", focus_text, flags=re.IGNORECASE)

    words = [
        w.strip("._-*#")
        for w in re.split(r"[\s,.;:!?()\[\]{}<>\"'/\\|+=-]+", focus_text)
        if w.strip("._-*#")
    ]
    meaningful: list[str] = []
    seen_lower: set[str] = set()
    for w in words:
        low = w.lower()
        if len(w) > 1 and low not in STOPWORDS and low not in seen_lower:
            meaningful.append(w)
            seen_lower.add(low)
        if len(meaningful) >= 7:
            break

    stem = " ".join(meaningful[:6]) if meaningful else Path(filename).stem
    stem = re.sub(r"\s+", " ", stem).strip()
    stem = _apply_affixes(stem, prepend_date=prepend_date, date_iso=date_iso, custom_prefix=custom_prefix)
    name = sanitize_filename(stem, extension, max_length, style)
    return {
        "name": name,
        "subject": " ".join(meaningful[:4]) if meaningful else "Unclassified file",
        "rationale": "Local fallback based on available text; not AI-generated.",
    }


def ai_suggestion(
    filename: str,
    extension: str,
    content: str,
    content_kind: str,
    provider,
    style: str,
    max_length: int,
    image_path=None,
    prepend_date: bool = False,
    date_iso: str = "",
    custom_prefix: str = "",
) -> dict:
    """Request an AI-generated filename suggestion and sanitize the returned stem."""
    result = provider.suggest_name(
        filename, extension, content, content_kind, image_path=image_path
    )
    raw_stem = str(result.get("suggested_stem", "")).strip()
    stem = _apply_affixes(
        raw_stem,
        prepend_date=prepend_date,
        date_iso=date_iso,
        custom_prefix=custom_prefix,
    )
    safe = sanitize_filename(stem, extension, max_length, style)
    return {
        "name": safe,
        "subject": result.get("subject") or Path(safe).stem.replace("_", " "),
        "rationale": result.get("rationale", "AI suggestion"),
    }
