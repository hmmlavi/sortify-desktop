"""Regression tests for SQLite connection ownership, WAL cleanup, and quarantine."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.core.operation_history import DB_SCHEMA_VERSION, OperationHistory


class _TrackedConnection:
    """Thin proxy that records whether SQLite connections were closed."""

    def __init__(self, real: sqlite3.Connection) -> None:
        object.__setattr__(self, "_real", real)
        object.__setattr__(self, "closed", False)

    def __getattr__(self, name):
        return getattr(object.__getattribute__(self, "_real"), name)

    def __setattr__(self, name, value):
        if name in {"_real", "closed"}:
            object.__setattr__(self, name, value)
        else:
            setattr(object.__getattribute__(self, "_real"), name, value)

    def close(self) -> None:
        object.__setattr__(self, "closed", True)
        object.__getattribute__(self, "_real").close()


class OperationHistoryLifecycleTests(unittest.TestCase):
    def test_every_file_connection_is_closed_after_operations(self):
        tracked: list[_TrackedConnection] = []
        real_connect = sqlite3.connect

        def tracking_connect(*args, **kwargs):
            conn = _TrackedConnection(real_connect(*args, **kwargs))
            tracked.append(conn)
            return conn

        with tempfile.TemporaryDirectory() as d:
            db = Path(d) / "history.sqlite3"
            with patch(
                "app.core.operation_history.sqlite3.connect",
                side_effect=tracking_connect,
            ):
                history = OperationHistory(db)
                history.record("session-1", "/tmp/a.txt", "/tmp/b.txt", "success")
                self.assertEqual(len(history.recent(10)), 1)
                history.set_cached_suggestion("key", {"name": "a.txt"})
                self.assertEqual(history.get_cached_suggestion("key")["name"], "a.txt")
                history.mark_session_undone("session-1")
                history.prune_older_than(1)
                history.clear_cache()
                history.clear_all()
                history.close()

            self.assertTrue(tracked, "expected at least one SQLite connection")
            self.assertTrue(
                all(conn.closed for conn in tracked),
                "every file-backed SQLite connection must be closed",
            )
            self.assertTrue(db.is_file())

    def test_shared_memory_connection_survives_individual_operations(self):
        tracked: list[_TrackedConnection] = []
        real_connect = sqlite3.connect

        def tracking_connect(*args, **kwargs):
            conn = _TrackedConnection(real_connect(*args, **kwargs))
            tracked.append(conn)
            return conn

        with tempfile.TemporaryDirectory() as d:
            db = Path(d) / "history.sqlite3"
            with patch(
                "app.core.operation_history.sqlite3.connect",
                side_effect=tracking_connect,
            ), patch.object(OperationHistory, "_initialize_or_recover", side_effect=OSError("read-only")):
                history = OperationHistory(db)
                self.assertTrue(history.in_memory_fallback)
                history.record("s", "a", "b", "success")
                history.record("s", "c", "d", "success")
                self.assertEqual(len(history.recent(10)), 2)
                memory_conn = history._memory_conn
                self.assertIsNotNone(memory_conn)
                self.assertFalse(tracked[0].closed, "shared memory connection was closed")
                history.close()

            self.assertIsNone(history._memory_conn)
            self.assertTrue(tracked[0].closed)

    def test_corrupt_database_sidecars_are_preserved_with_backup(self):
        with tempfile.TemporaryDirectory() as d:
            db = Path(d) / "history.sqlite3"
            db.write_bytes(b"definitely not a sqlite database")
            Path(str(db) + "-wal").write_bytes(b"wal-evidence")
            Path(str(db) + "-shm").write_bytes(b"shm-evidence")

            history = OperationHistory(db)
            self.assertTrue(history.recovered_from_corruption)
            self.assertIsNotNone(history.recovery_backup_path)
            backup = history.recovery_backup_path
            assert backup is not None
            self.assertTrue(backup.is_file())
            self.assertEqual(Path(str(backup) + "-wal").read_bytes(), b"wal-evidence")
            self.assertEqual(Path(str(backup) + "-shm").read_bytes(), b"shm-evidence")
            self.assertFalse(Path(str(db) + "-wal").exists())
            self.assertFalse(Path(str(db) + "-shm").exists())

            history.record("s", "a", "b", "success")
            self.assertEqual(len(history.recent(5)), 1)
            history.close()

    def test_legacy_schema_missing_columns_is_migrated_with_backup(self):
        with tempfile.TemporaryDirectory() as d:
            db = Path(d) / "history.sqlite3"
            with sqlite3.connect(db) as conn:
                conn.execute(
                    """CREATE TABLE operations (
                      id INTEGER PRIMARY KEY AUTOINCREMENT,
                      session_id TEXT NOT NULL,
                      original_path TEXT NOT NULL,
                      new_path TEXT NOT NULL,
                      timestamp TEXT NOT NULL,
                      status TEXT NOT NULL
                    )"""
                )
                conn.execute(
                    "INSERT INTO operations(session_id,original_path,new_path,timestamp,status) "
                    "VALUES('legacy','a','b','2026-01-01','success')"
                )
                conn.execute("PRAGMA user_version = 0")
                conn.commit()
            # The connection must be closed explicitly: the context manager only
            # commits, and Windows refuses to rename a database that is still open.
            conn.close()

            history = OperationHistory(db)
            backup = db.with_name(f"history.pre-v{DB_SCHEMA_VERSION}.sqlite3.bak")
            self.assertTrue(backup.is_file())
            rows = history.recent(10)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["undone"], 0)
            history.mark_undone(rows[0]["id"])
            self.assertEqual(history.recent(10)[0]["undone"], 1)
            history.close()

    def test_clean_close_leaves_no_wal_sidecars(self):
        with tempfile.TemporaryDirectory() as d:
            db = Path(d) / "history.sqlite3"
            history = OperationHistory(db)
            for i in range(20):
                history.record(f"s{i}", "a", "b", "success")
            history.close()
            self.assertFalse(Path(str(db) + "-wal").exists())
            self.assertFalse(Path(str(db) + "-shm").exists())
            db.unlink()
            self.assertFalse(db.exists())


if __name__ == "__main__":
    unittest.main()
