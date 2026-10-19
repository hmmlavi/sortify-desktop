import tempfile
import unittest
from pathlib import Path

from app.core.file_extractor import ExtractionError, extract_content
from app.core.scanner import scan_folder


class ScannerAndExtractorTests(unittest.TestCase):
    def test_scan_folder_non_recursive_and_recursive(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "top.txt").write_text("hello")
            (root / ".sortify-tmp-ignore.txt").write_text("temp")
            sub = root / "nested"
            sub.mkdir()
            (sub / "child.md").write_text("# Heading")

            non_rec = scan_folder(root, include_subfolders=False)
            self.assertEqual([r.name for r in non_rec], ["top.txt"])

            rec = scan_folder(root, include_subfolders=True)
            self.assertEqual({r.name for r in rec}, {"top.txt", "child.md"})

    def test_scan_cancellation(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for i in range(25):
                (root / f"file_{i:02d}.txt").write_text(f"item {i}")
            calls = 0

            def should_cancel():
                nonlocal calls
                calls += 1
                return calls > 5

            partial = scan_folder(root, cancel_check=should_cancel)
            self.assertLess(len(partial), 25)

    def test_scan_skips_symlinks_by_default(self):
        with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
            root = Path(d1)
            outside = Path(d2) / "secret.txt"
            outside.write_text("top secret")
            (root / "normal.txt").write_text("normal")
            sym = root / "symlink.txt"
            try:
                sym.symlink_to(outside)
            except OSError:
                self.skipTest("Symlinks not supported in this environment")
            records = scan_folder(root, skip_symlinks=True)
            self.assertEqual([r.name for r in records], ["normal.txt"])

    def test_extract_text_csv_json_html_rtf(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            txt = root / "sample.txt"
            txt.write_text("Project Apollo Launch Checklist")
            content, kind = extract_content(txt)
            self.assertEqual(kind, "text")
            self.assertIn("Apollo", content)

            csv_file = root / "metrics.csv"
            csv_file.write_text("Month,Revenue\nJan,1200\nFeb,1500\n")
            c_csv, k_csv = extract_content(csv_file)
            self.assertEqual(k_csv, "spreadsheet")
            self.assertIn("Revenue", c_csv)

            json_file = root / "config.json"
            json_file.write_text('{"service": "billing", "region": "eu-west-1"}')
            c_json, k_json = extract_content(json_file)
            self.assertEqual(k_json, "data")
            self.assertIn("billing", c_json)

            html_file = root / "page.html"
            html_file.write_text("<html><head><script>evil()</script></head><body><h1>Quarterly Engineering Review</h1></body></html>")
            c_html, k_html = extract_content(html_file)
            self.assertEqual(k_html, "document")
            self.assertIn("Quarterly Engineering Review", c_html)
            self.assertNotIn("evil", c_html)

            rtf_file = root / "memo.rtf"
            rtf_file.write_text(r"{\rtf1\ansi\deff0Security Incident Response Plan}")
            c_rtf, k_rtf = extract_content(rtf_file)
            self.assertEqual(k_rtf, "document")
            self.assertIn("Security Incident Response Plan", c_rtf)

    def test_extract_rejects_corrupt_office_container(self):
        with tempfile.TemporaryDirectory() as d:
            bad_docx = Path(d) / "fake.docx"
            bad_docx.write_text("not a zip archive")
            with self.assertRaises(ExtractionError):
                extract_content(bad_docx)

    def test_extract_rejects_unsupported_extension(self):
        with tempfile.TemporaryDirectory() as d:
            unknown = Path(d) / "archive.xyz"
            unknown.write_bytes(b"1234")
            with self.assertRaises(ExtractionError):
                extract_content(unknown)


if __name__ == "__main__":
    unittest.main()
