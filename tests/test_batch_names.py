import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path

from app.core.batch_names import resolve_batch_conflicts


@dataclass
class _Rec:
    path: Path
    proposed_name: str
    extension: str = ".txt"
    selected: bool = True
    conflict_reason: str | None = None
    status: str = "Ready"


class BatchConflictTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _touch(self, name: str) -> Path:
        path = self.root / name
        path.write_text("x", encoding="utf-8")
        return path

    def test_name_already_on_disk_is_made_unique(self):
        """A file that exists but is not in the batch must still be avoided."""
        source = self._touch("draft.txt")
        self._touch("Report.txt")  # not part of the batch
        record = _Rec(source, "report.txt", conflict_reason="Destination already exists")
        resolved = resolve_batch_conflicts([record], 100, "Underscore_Separated")
        self.assertEqual(resolved, 1)
        self.assertNotEqual(record.proposed_name.casefold(), "report.txt")
        self.assertEqual(record.status, "Edited by user")

    def test_names_of_selected_files_are_free_for_chained_renames(self):
        a = self._touch("a.txt")
        b = self._touch("b.txt")
        recs = [_Rec(a, "b.txt"), _Rec(b, "c.txt")]
        resolved = resolve_batch_conflicts(recs, 100, "Underscore_Separated")
        self.assertEqual(resolved, 0)
        self.assertEqual([r.proposed_name for r in recs], ["b.txt", "c.txt"])

    def test_names_taken_by_unselected_files_are_avoided(self):
        a = self._touch("a.txt")
        keep = self._touch("final.txt")
        rec = _Rec(a, "final.txt")
        other = _Rec(keep, "final.txt", selected=False)
        resolve_batch_conflicts([rec, other], 100, "Underscore_Separated")
        self.assertNotEqual(rec.proposed_name.casefold(), "final.txt")

    def test_two_proposals_in_batch_get_distinct_names(self):
        a = self._touch("a.txt")
        b = self._touch("b.txt")
        recs = [_Rec(a, "Same.txt"), _Rec(b, "Same.txt")]
        resolve_batch_conflicts(recs, 100, "Underscore_Separated")
        self.assertNotEqual(recs[0].proposed_name.casefold(), recs[1].proposed_name.casefold())


if __name__ == "__main__":
    unittest.main()
