import tempfile
import unittest
from pathlib import Path

from app.core.filename_validator import (
    resolve_unique_name,
    sanitize_filename,
    validate_destination,
    validate_filename_text,
)


class FilenameValidatorTests(unittest.TestCase):
    def test_sanitizes_windows_characters(self):
        self.assertEqual(
            sanitize_filename("Data: Structures? / Lab", ".pdf"),
            "Data_Structures_Lab.pdf",
        )

    def test_reserved_name(self):
        self.assertNotEqual(sanitize_filename("CON", ".txt"), "CON.txt")

    def test_reserved_name_after_truncation(self):
        # Even if truncation cuts a stem down to 'CON', it must not remain 'CON.txt'
        result = sanitize_filename("CON_extra_words", ".txt", max_length=12)
        self.assertNotEqual(result.split(".")[0].upper(), "CON")

    def test_preserves_extension(self):
        self.assertTrue(sanitize_filename("Hello world", ".pdf").endswith(".pdf"))

    def test_length_limit(self):
        self.assertLessEqual(len(sanitize_filename("x" * 500, ".pdf", 40)), 40)

    def test_naming_styles(self):
        self.assertEqual(
            sanitize_filename("quarterly budget report", ".pdf", style="Title Case"),
            "Quarterly Budget Report.pdf",
        )
        self.assertEqual(
            sanitize_filename("quarterly budget report", ".pdf", style="Hyphen-Separated"),
            "quarterly-budget-report.pdf",
        )
        self.assertEqual(
            sanitize_filename("Quarterly Budget Report", ".pdf", style="camelCase"),
            "quarterlyBudgetReport.pdf",
        )

    def test_validate_filename_text(self):
        self.assertIsNone(validate_filename_text("Clean_Report_2026.pdf"))
        self.assertIsNotNone(validate_filename_text("../escape.pdf"))
        self.assertIsNotNone(validate_filename_text("CON.txt"))
        self.assertIsNotNone(validate_filename_text("bad:name.txt"))
        self.assertIsNotNone(validate_filename_text("trailing_dot."))

    def test_resolve_unique_name(self):
        taken = {"report.pdf", "report_2.pdf"}
        unique = resolve_unique_name("Report.pdf", ".pdf", taken)
        self.assertEqual(unique, "Report_3.pdf")

    def test_no_move(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            source = root / "a.txt"
            source.write_text("x")
            dest = root / "sub" / "b.txt"
            self.assertIn("another directory", validate_destination(source, dest, root))

    def test_rejects_outside_root_and_symlinks(self):
        with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
            root = Path(d1)
            outside = Path(d2) / "outside.txt"
            outside.write_text("secret")
            err = validate_destination(outside, outside.with_name("renamed.txt"), root)
            self.assertIn("outside", err.lower())

            link = root / "link.txt"
            try:
                link.symlink_to(outside)
                link_err = validate_destination(link, root / "safe.txt", root)
                self.assertIn("symbolic link", link_err.lower())
            except OSError:
                pass


if __name__ == "__main__":
    unittest.main()
