import tempfile
import unittest
from pathlib import Path

from app.core.operation_history import OperationHistory
from app.core.rename_engine import RenameEngine


class RenameEngineTests(unittest.TestCase):
    def test_renames_file_and_records_history(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            db = root / "history.sqlite"
            a = root / "a.txt"
            a.write_text("alpha")
            engine = RenameEngine(OperationHistory(db))
            result = engine.apply(root, [(a, "meaningful.txt")])
            self.assertEqual(len(result["success"]), 1)
            self.assertEqual((root / "meaningful.txt").read_text(), "alpha")
            self.assertEqual(len(OperationHistory(db).recent()), 1)

    def test_does_not_overwrite_existing_destination(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            a = root / "a.txt"
            b = root / "b.txt"
            a.write_text("A")
            b.write_text("B")
            result = RenameEngine(OperationHistory(root / "history.sqlite")).apply(
                root, [(a, "b.txt")]
            )
            self.assertTrue(b.exists())
            self.assertEqual(b.read_text(), "B")
            self.assertTrue(a.exists())
            self.assertEqual(len(result["failed"]), 1)

    def test_undo_restores_original_name(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            a = root / "before.txt"
            a.write_text("keep me")
            engine = RenameEngine(OperationHistory(root / "history.sqlite"))
            first = engine.apply(root, [(a, "after.txt")])
            self.assertEqual(len(first["success"]), 1)
            undo = engine.undo_last_session()
            self.assertEqual(len(undo["success"]), 1)
            self.assertEqual(a.read_text(), "keep me")

    def test_handles_swap_cycle(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            a = root / "a.txt"
            b = root / "b.txt"
            a.write_text("A")
            b.write_text("B")
            result = RenameEngine(OperationHistory(root / "history.sqlite")).apply(
                root, [(a, "b.txt"), (b, "a.txt")]
            )
            self.assertEqual(len(result["success"]), 2)
            self.assertEqual(a.read_text(), "B")
            self.assertEqual(b.read_text(), "A")

    def test_detects_batch_duplicate_destinations(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            a = root / "one.txt"
            b = root / "two.txt"
            a.write_text("1")
            b.write_text("2")
            engine = RenameEngine(OperationHistory(root / "history.sqlite"))
            result = engine.apply(root, [(a, "Same_Name.txt"), (b, "same_name.txt")])
            self.assertEqual(len(result["success"]), 1)
            self.assertEqual(len(result["failed"]), 1)

    def test_rejects_path_traversal_in_proposal(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            a = root / "doc.txt"
            a.write_text("content")
            engine = RenameEngine(OperationHistory(root / "history.sqlite"))
            result = engine.apply(root, [(a, "../escaped.txt")])
            self.assertEqual(len(result["success"]), 0)
            self.assertEqual(len(result["failed"]), 1)
            self.assertTrue(a.exists())

    def test_category_subfolder_organization_and_undo(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            a = root / "notes.txt"
            b = root / "table.csv"
            a.write_text("notes")
            b.write_text("col1,col2")
            engine = RenameEngine(OperationHistory(root / "history.sqlite"))
            result = engine.apply(
                root,
                [(a, "Notes_and_Text/Meeting_Notes.txt"), (b, "Spreadsheets/Data.csv")],
                allow_subfolders=True,
            )
            self.assertEqual(len(result["success"]), 2)
            self.assertTrue((root / "Notes_and_Text" / "Meeting_Notes.txt").exists())
            self.assertTrue((root / "Spreadsheets" / "Data.csv").exists())

            undo = engine.undo_last_session()
            self.assertEqual(len(undo["success"]), 2)
            self.assertTrue(a.exists())
            self.assertTrue(b.exists())


if __name__ == "__main__":
    unittest.main()
