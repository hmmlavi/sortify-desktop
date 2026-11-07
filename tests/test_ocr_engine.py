from types import ModuleType, SimpleNamespace
import sys

from PIL import Image

from app.core import file_extractor, ocr_engine


def test_recognize_filters_low_confidence_and_caps_text(monkeypatch):
    class FakeEngine:
        def __call__(self, image):
            assert image.mode == "RGB"
            return SimpleNamespace(
                txts=("  Invoice   Number 42 ", "noise", "Total: 500"),
                scores=(0.99, 0.10, 0.95),
            )

    monkeypatch.setattr(ocr_engine, "_get_engine", lambda: FakeEngine())
    result = ocr_engine._recognize(Image.new("RGB", (20, 20)), max_chars=17)
    assert result == "Invoice Number 42"


def test_prepare_image_downscales_large_images(monkeypatch):
    monkeypatch.setattr(ocr_engine, "MAX_OCR_IMAGE_PIXELS", 100)
    image = Image.new("RGB", (40, 20))
    prepared = ocr_engine._prepare_image(image)
    assert prepared.width * prepared.height <= 100


def test_image_ocr_is_safely_skipped_without_optional_dependencies(monkeypatch, tmp_path):
    image_path = tmp_path / "sample.png"
    Image.new("RGB", (10, 10)).save(image_path)
    monkeypatch.setattr(ocr_engine, "ocr_dependencies_available", lambda **kwargs: False)
    assert ocr_engine.extract_image_text(image_path) == ""


def test_pdf_ocr_is_safely_skipped_without_optional_dependencies(monkeypatch, tmp_path):
    pdf_path = tmp_path / "scan.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")
    monkeypatch.setattr(ocr_engine, "ocr_dependencies_available", lambda **kwargs: False)
    assert ocr_engine.extract_pdf_text(pdf_path) == ""


def test_scanned_pdf_with_metadata_still_uses_ocr(monkeypatch, tmp_path):
    pdf_path = tmp_path / "scanned.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")

    class FakeReader:
        is_encrypted = False
        metadata = {"/Title": "Scanned invoice"}
        pages = [SimpleNamespace(extract_text=lambda: "")]

    fake_pypdf = ModuleType("pypdf")
    fake_pypdf.PdfReader = lambda _path: FakeReader()
    monkeypatch.setitem(sys.modules, "pypdf", fake_pypdf)
    monkeypatch.setattr(
        file_extractor, "extract_pdf_text", lambda _path, max_chars: "Invoice Number INV-42"
    )

    text, kind = file_extractor.extract_content(pdf_path)
    assert kind == "pdf_ocr"
    assert "Scanned invoice" in text
    assert "Invoice Number INV-42" in text


def test_image_extraction_appends_local_ocr_text(monkeypatch, tmp_path):
    image_path = tmp_path / "photo.png"
    Image.new("RGB", (32, 20)).save(image_path)
    monkeypatch.setattr(
        file_extractor, "extract_image_text", lambda _path, max_chars: "RECEIPT TOTAL 250"
    )

    text, kind = file_extractor.extract_content(image_path)
    assert kind == "image_ocr"
    assert "Image text (OCR)" in text
    assert "RECEIPT TOTAL 250" in text
