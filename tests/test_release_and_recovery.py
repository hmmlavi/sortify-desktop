"""Tests for database corruption recovery, legacy migration, Unicode naming, zip-bomb defense, and packaging/frozen runtime."""

from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import main as main_mod
from app.config import Settings, migrate_legacy_data_dir
from app.core.file_extractor import ExtractionError, _validate_zip_safety
from app.core.filename_generator import fallback_suggestion
from app.core.filename_validator import sanitize_filename
from app.core.operation_history import DB_SCHEMA_VERSION, OperationHistory
from app.utils.resources import get_asset_path, get_bundle_root, verify_runtime_assets


class ReleaseAndRecoveryTests(unittest.TestCase):
    def test_unicode_filename_generation_and_sanitization(self):
        # Verify non-ASCII Unicode scripts (Devanagari, Japanese, accented Latin) are preserved safely
        latin = sanitize_filename("Résumé Financier 2026: Q3", ".pdf", style="Underscore_Separated")
        self.assertEqual(latin, "Résumé_Financier_2026_Q3.pdf")

        hindi_res = fallback_suggestion(
            "doc.txt",
            ".txt",
            "वार्षिक वित्तीय रिपोर्ट 2026",
            "Underscore_Separated",
            100,
        )
        self.assertIn("वार्षिक", hindi_res["name"])
        self.assertTrue(hindi_res["name"].endswith(".txt"))

    def test_zip_bomb_entry_count_protection(self):
        with tempfile.TemporaryDirectory() as d:
            bomb_path = Path(d) / "many_entries.docx"
            with zipfile.ZipFile(bomb_path, "w") as zf:
                for i in range(60):
                    zf.writestr(f"part_{i}.xml", "<p>hello</p>")
            with patch("app.core.file_extractor.MAX_ARCHIVE_ENTRIES", 25):
                with self.assertRaises(ExtractionError) as ctx:
                    _validate_zip_safety(bomb_path)
                self.assertIn("too many entries", str(ctx.exception).lower())

    def test_corrupt_settings_json_backs_up_and_recovers(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = Path(d) / "settings.json"
            cfg.write_text("{corrupt json: [unclosed", encoding="utf-8")

            loaded = Settings.load(config_path=cfg)
            self.assertTrue(loaded.recovered_from_corrupt)
            self.assertTrue(Path(loaded.corrupt_backup_path).is_file())
            self.assertEqual(loaded.naming_style, "Underscore_Separated")

    def test_legacy_renova_to_sortify_migration_preserves_originals(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            legacy = root / "RenovaAI"
            legacy.mkdir()
            (legacy / "settings.json").write_text(
                '{"naming_style": "Title Case", "max_filename_length": 85}',
                encoding="utf-8",
            )
            sortify_dir = root / "Sortify"

            migrated = migrate_legacy_data_dir(sortify_dir, legacy)
            self.assertTrue(migrated)
            self.assertTrue((sortify_dir / "settings.json").is_file())
            # Original legacy file must remain untouched
            self.assertTrue((legacy / "settings.json").is_file())

            loaded = Settings.load(config_path=sortify_dir / "settings.json")
            self.assertEqual(loaded.naming_style, "Title Case")
            self.assertEqual(loaded.max_filename_length, 85)

    def test_corrupt_sqlite_history_quarantines_and_reinitializes(self):
        with tempfile.TemporaryDirectory() as d:
            db_file = Path(d) / "history.sqlite3"
            db_file.write_bytes(b"NOT A VALID SQLITE3 FILE HEADER AT ALL")

            hist = OperationHistory(db_file)
            self.assertTrue(hist.recovered_from_corruption)
            self.assertIsNotNone(hist.recovery_backup_path)
            self.assertTrue(hist.recovery_backup_path.is_file())

            # Verify the re-initialized database works normally
            hist.record("sess01", "/tmp/a.txt", "/tmp/b.txt", "success")
            rows = hist.recent(10)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["session_id"], "sess01")
            hist.close()

    def test_sqlite_v0_to_v2_schema_migration_creates_backup(self):
        with tempfile.TemporaryDirectory() as d:
            db_file = Path(d) / "history.sqlite3"
            with sqlite3.connect(db_file) as conn:
                conn.execute(
                    """CREATE TABLE operations (
                      id INTEGER PRIMARY KEY AUTOINCREMENT,
                      session_id TEXT NOT NULL,
                      original_path TEXT NOT NULL,
                      new_path TEXT NOT NULL,
                      timestamp TEXT NOT NULL,
                      status TEXT NOT NULL,
                      error TEXT,
                      undone INTEGER NOT NULL DEFAULT 0
                    )"""
                )
                conn.execute(
                    "INSERT INTO operations(session_id,original_path,new_path,timestamp,status) VALUES('legacy1','a','b','2026-01-01','success')"
                )
                conn.execute("PRAGMA user_version = 0")
                conn.commit()
            # Closing is required: sqlite3's context manager commits but keeps the
            # handle open, and Windows then refuses to move the file for the backup.
            conn.close()

            hist = OperationHistory(db_file)
            self.assertFalse(hist.recovered_from_corruption)
            backup = db_file.with_name(f"history.pre-v{DB_SCHEMA_VERSION}.sqlite3.bak")
            self.assertTrue(backup.is_file())
            self.assertEqual(len(hist.recent(10)), 1)
            hist.close()

    def test_frozen_meipass_resource_resolution(self):
        with tempfile.TemporaryDirectory() as d:
            fake_meipass = Path(d)
            (fake_meipass / "assets").mkdir()
            (fake_meipass / "assets" / "sortify-icon.svg").write_text("<svg/>", encoding="utf-8")

            with patch.object(sys, "frozen", True, create=True), patch.object(
                sys, "_MEIPASS", str(fake_meipass), create=True
            ):
                self.assertEqual(get_bundle_root(), fake_meipass.resolve())
                resolved = get_asset_path("assets/sortify-icon.svg")
                self.assertEqual(resolved, (fake_meipass / "assets" / "sortify-icon.svg").resolve())

    def test_runtime_assets_and_packaging_specs_exist(self):
        assets = verify_runtime_assets()
        self.assertTrue(all(assets.values()), f"Missing runtime assets: {assets}")

        root = get_bundle_root()
        self.assertTrue((root / "Sortify.spec").is_file())
        self.assertTrue((root / "packaging" / "installer.iss").is_file())
        self.assertTrue((root / "packaging" / "windows_version_info.txt").is_file())
        self.assertTrue((root / "packaging" / "build_windows.bat").is_file())

    def test_cli_diagnose_mode_succeeds(self):
        with tempfile.TemporaryDirectory() as d, patch.dict(
            "os.environ", {"SORTIFY_DATA_DIR": d}
        ):
            rc = main_mod.main(["--diagnose"])
            self.assertEqual(rc, 0)

    def test_diagnose_survives_missing_console_streams(self):
        """A windowed Windows build has no stdout/stderr; diagnostics must still work."""
        with tempfile.TemporaryDirectory() as d, patch.object(
            main_mod, "APP_DIR", Path(d)
        ), patch.object(main_mod, "OperationHistory") as history_cls, patch.object(
            sys, "stdout", None
        ), patch.object(sys, "stderr", None):
            history_cls.return_value.in_memory_fallback = False
            self.assertEqual(main_mod.run_diagnostics(), 0)
            report_path = Path(d) / "diagnostics.json"
            self.assertTrue(report_path.is_file())
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertTrue(report["all_assets_present"])
            self.assertEqual(report["application"], "Sortify")


if __name__ == "__main__":
    unittest.main()
