import unittest

from app.core.filename_generator import (
    ai_suggestion,
    fallback_suggestion,
    suggest_category,
)


class _DummyProvider:
    def suggest_name(self, filename, extension, content, content_kind, image_path=None):
        return {
            "suggested_stem": "Quarterly Revenue Forecast",
            "subject": "Financial Planning",
            "rationale": "Mock AI analysis",
        }


class FallbackTests(unittest.TestCase):
    def test_fallback_uses_content_words(self):
        result = fallback_suggestion(
            "document.pdf",
            ".pdf",
            "Data Structures and Algorithms lab manual",
            "Underscore_Separated",
            100,
        )
        self.assertTrue(result["name"].endswith(".pdf"))
        self.assertIn("Data", result["name"])
        self.assertIn("fallback", result["rationale"].lower())

    def test_fallback_with_affixes(self):
        result = fallback_suggestion(
            "notes.md",
            ".md",
            "Architecture security checklist",
            "Hyphen-Separated",
            100,
            prepend_date=True,
            date_iso="2026-10-18T09:00:00",
            custom_prefix="SecOps",
        )
        self.assertTrue(result["name"].startswith("SecOps-2026-10-18-"))
        self.assertTrue(result["name"].endswith(".md"))

    def test_image_metadata_fallback_preserves_meaningful_filename(self):
        result = fallback_suggestion(
            "dashboard_mockup.png",
            ".png",
            "Image PNG 1920x1080 (landscape, RGB)",
            "Underscore_Separated",
            100,
        )
        self.assertIn("dashboard_mockup", result["name"])
        self.assertNotIn("landscape", result["name"])

    def test_ai_suggestion_sanitizes_output(self):
        result = ai_suggestion(
            "raw.xlsx",
            ".xlsx",
            "Q4 numbers",
            "spreadsheet",
            _DummyProvider(),
            "Underscore_Separated",
            100,
        )
        self.assertEqual(result["name"], "Quarterly_Revenue_Forecast.xlsx")
        self.assertEqual(result["subject"], "Financial Planning")

    def test_suggest_category(self):
        self.assertEqual(suggest_category(".pdf"), "Documents")
        self.assertEqual(suggest_category(".xlsx"), "Spreadsheets")
        self.assertEqual(suggest_category(".png"), "Images")
        self.assertEqual(suggest_category(".pptx"), "Presentations")


if __name__ == "__main__":
    unittest.main()
