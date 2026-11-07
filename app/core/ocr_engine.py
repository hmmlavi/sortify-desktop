"""Optional, fully offline OCR for scanned PDFs and text-bearing images.

OCR is an optional extra: the normal Sortify install stays small. RapidOCR
ships its model files in its wheel, so inference does not fetch models or
contact a service at runtime.
"""
from __future__ import annotations

import importlib.util
import logging
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

MAX_OCR_PAGES = 5
MAX_OCR_CHARS = 12_000
MAX_OCR_IMAGE_PIXELS = 12_000_000
OCR_RENDER_SCALE = 1.5

_engine: Any | None = None
_engine_lock = threading.RLock()


def ocr_dependencies_available(*, for_pdf: bool = False) -> bool:
    """Return whether the optional local OCR runtime is installed."""
    required = ["rapidocr", "onnxruntime"]
    if for_pdf:
        required.append("pypdfium2")
    return all(importlib.util.find_spec(name) is not None for name in required)


def _get_engine() -> Any:
    """Create one shared CPU OCR engine; serialize calls for thread safety."""
    global _engine
    with _engine_lock:
        if _engine is None:
            from rapidocr import RapidOCR
            _engine = RapidOCR()
        return _engine


def _prepare_image(image: Any) -> Any:
    """Convert to RGB and cap pixel count before passing data to the OCR runtime."""
    from PIL import Image
    if not isinstance(image, Image.Image):
        image = Image.fromarray(image)
    image = image.convert("RGB")
    width, height = image.size
    pixels = width * height
    if pixels > MAX_OCR_IMAGE_PIXELS:
        ratio = (MAX_OCR_IMAGE_PIXELS / pixels) ** 0.5
        image = image.resize(
            (max(1, int(width * ratio)), max(1, int(height * ratio))),
            Image.Resampling.LANCZOS,
        )
    return image


def _recognize(image: Any, max_chars: int = MAX_OCR_CHARS) -> str:
    """Recognize text from a PIL image, returning bounded, confident lines."""
    from PIL import Image
    if not isinstance(image, Image.Image):
        image = Image.fromarray(image)
    prepared = _prepare_image(image)
    with _engine_lock:
        result = _get_engine()(prepared)
    if result is None:
        return ""
    texts = getattr(result, "txts", ()) or ()
    scores = getattr(result, "scores", ()) or ()
    lines: list[str] = []
    total = 0
    for index, raw_text in enumerate(texts):
        line = " ".join(str(raw_text).split()).strip()
        score = scores[index] if index < len(scores) else 1.0
        try:
            confidence = float(score)
        except (TypeError, ValueError):
            confidence = 0.0
        if not line or confidence < 0.35:
            continue
        remaining = max_chars - total
        if remaining <= 0:
            break
        line = line[:remaining]
        lines.append(line)
        total += len(line) + 1
    return "\n".join(lines).strip()


def extract_image_text(path: Path, max_chars: int = MAX_OCR_CHARS) -> str:
    """Run local OCR on a supported image. Missing extras return empty text."""
    if not ocr_dependencies_available():
        return ""
    try:
        from PIL import Image
        with Image.open(path) as image:
            image.load()
            return _recognize(image.copy(), max_chars=max_chars)
    except Exception as exc:  # noqa: BLE001 - OCR must not break normal metadata extraction.
        logger.warning("Local image OCR skipped for %s (%s)", path, type(exc).__name__)
        return ""


def extract_pdf_text(
    path: Path,
    max_chars: int = MAX_OCR_CHARS,
    page_indexes: list[int] | None = None,
) -> str:
    """Render up to five selected PDF pages locally and OCR them; no network access."""
    if not ocr_dependencies_available(for_pdf=True):
        return ""
    try:
        import pypdfium2 as pdfium
        document = pdfium.PdfDocument(str(path))
        chunks: list[str] = []
        total = 0
        try:
            selected_pages = (
                page_indexes if page_indexes is not None
                else list(range(min(len(document), MAX_OCR_PAGES)))
            )
            for page_index in selected_pages[:MAX_OCR_PAGES]:
                if not isinstance(page_index, int) or page_index < 0 or page_index >= len(document):
                    continue
                page = document[page_index]
                try:
                    page_width, page_height = page.get_size()
                    page_pixels = max(1.0, page_width * page_height)
                    safe_scale = min(
                        OCR_RENDER_SCALE,
                        (MAX_OCR_IMAGE_PIXELS / page_pixels) ** 0.5,
                    )
                    image = page.render(scale=max(0.1, safe_scale)).to_pil()
                    remaining = max_chars - total
                    if remaining <= 0:
                        break
                    text = _recognize(image, max_chars=remaining)
                    if text:
                        chunks.append(text)
                        total += len(text) + 1
                finally:
                    page.close()
        finally:
            document.close()
        return "\n".join(chunks).strip()
    except Exception as exc:  # noqa: BLE001 - OCR must not break normal PDF extraction.
        logger.warning("Local PDF OCR skipped for %s (%s)", path, type(exc).__name__)
        return ""
