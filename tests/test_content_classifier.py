import unittest

from app.core.content_classifier import (
    classify_content_subcategory,
    organization_category,
)


class ContentClassifierTests(unittest.TestCase):
    def test_invoice_requires_multiple_signals(self):
        self.assertIsNone(classify_content_subcategory("This document mentions an invoice."))
        text = "TAX INVOICE\nInvoice Number: INV-104\nBill To: Example Ltd\nAmount Due: 500"
        self.assertEqual(classify_content_subcategory(text), "Invoices")

    def test_resume_classification(self):
        text = "Curriculum Vitae\nProfessional Summary\nWork Experience\nTechnical Skills"
        self.assertEqual(classify_content_subcategory(text), "Resumes")

    def test_certificate_classification(self):
        text = "Certificate of Completion\nThis certifies that Alex completed the course."
        self.assertEqual(classify_content_subcategory(text), "Certificates")

    def test_ambiguous_content_falls_back(self):
        text = "General notes about a project, planning, and next steps."
        self.assertIsNone(classify_content_subcategory(text))
        self.assertEqual(organization_category("Documents", text), "Documents")

    def test_type_and_content_categories_are_combined(self):
        text = "Tax Invoice\nInvoice Number: 42\nAmount Due: 250"
        self.assertEqual(
            organization_category("Documents", text),
            "Documents/Invoices",
        )


if __name__ == "__main__":
    unittest.main()
