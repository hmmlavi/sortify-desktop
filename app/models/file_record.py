"""Data models representing discovered files, analysis metadata, and rename proposals."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


def format_size(size_bytes: int) -> str:
    """Return a clean human-readable byte size string."""
    size = float(max(0, size_bytes))
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024.0 or unit == "GB":
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size_bytes} B"


TYPE_LABELS = {
    ".pdf": "PDF Document",
    ".docx": "Word Document",
    ".pptx": "Presentation",
    ".xlsx": "Spreadsheet",
    ".csv": "CSV Data",
    ".tsv": "TSV Data",
    ".txt": "Plain Text",
    ".md": "Markdown",
    ".rst": "reStructuredText",
    ".json": "JSON Data",
    ".yaml": "YAML Config",
    ".yml": "YAML Config",
    ".html": "HTML Document",
    ".htm": "HTML Document",
    ".rtf": "Rich Text",
    ".log": "Log File",
    ".jpg": "JPEG Image",
    ".jpeg": "JPEG Image",
    ".png": "PNG Image",
    ".webp": "WebP Image",
    ".gif": "GIF Image",
    ".bmp": "BMP Image",
    ".tiff": "TIFF Image",
}

IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tiff"})


@dataclass
class FileRecord:
    path: Path
    size_bytes: int
    extension: str
    modified_iso: str
    extracted_text: str = ""
    detected_subject: str = ""
    proposed_name: str = ""
    status: str = "Discovered"
    error: str | None = None
    selected: bool = True
    source: str = ""
    rationale: str = ""
    category: str = ""
    root_path: Path | None = None
    conflict_reason: str | None = None
    generation_mode: str = ""

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def relative_path(self) -> str:
        if self.root_path:
            try:
                return str(self.path.relative_to(self.root_path))
            except ValueError:
                pass
        return self.path.name

    @property
    def relative_parent(self) -> str:
        if self.root_path:
            try:
                rel = self.path.parent.relative_to(self.root_path)
                return "" if str(rel) == "." else str(rel)
            except ValueError:
                pass
        return ""

    @property
    def human_size(self) -> str:
        return format_size(self.size_bytes)

    @property
    def file_type_label(self) -> str:
        ext = (self.extension or "").lower()
        if ext in TYPE_LABELS:
            return TYPE_LABELS[ext]
        if ext:
            return f"{ext.lstrip('.').upper()} File"
        return "File (No Extension)"
