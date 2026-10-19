"""SQLite-backed operation history, schema migration, corruption recovery, and suggestion cache.

Connection ownership rules
--------------------------
* File-backed databases never keep a long-lived connection.  Every public
  operation opens a short-lived connection, commits or rolls back, and closes it
  in a ``finally`` block.  This is what makes quarantine, migration backups, and
  temporary-directory cleanup reliable on Windows.
* The in-memory fallback owns exactly one shared connection.  Individual
  operations must never close it; :meth:`OperationHistory.close` is the only
  place that does.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Self

from app.config import DB_PATH

logger = logging.getLogger(__name__)
DB_SCHEMA_VERSION = 2


class OperationHistory:
    def __init__(self, db_path: Path | str = DB_PATH):
        self.db_path = Path(db_path)
        self.recovered_from_corruption: bool = False
        self.recovery_backup_path: Path | None = None
        self.in_memory_fallback: bool = False
        self._memory_conn: sqlite3.Connection | None = None
        self._memory_lock = threading.RLock()
        self._precheck_sidecars: dict[str, Path] = {}

        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._initialize_or_recover()
        except OSError as exc:
            logger.warning(
                "History directory %s unavailable (%s); using in-memory SQLite fallback.",
                self.db_path.parent,
                exc,
            )
            self._enable_memory_fallback()
        except sqlite3.Error:
            logger.exception(
                "Unexpected SQLite failure while opening %s; using in-memory fallback.",
                self.db_path,
            )
            self._enable_memory_fallback()

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------
    def _enable_memory_fallback(self) -> None:
        self.in_memory_fallback = True
        if self._memory_conn is not None:
            return
        conn = sqlite3.connect(":memory:", check_same_thread=False)
        try:
            self._apply_schema(conn)
            conn.commit()
        except sqlite3.Error:
            conn.close()
            raise
        self._memory_conn = conn

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        """Yield a connection, commit/rollback it, and close owned connections.

        The shared in-memory connection is committed but deliberately kept open.
        File-backed connections are always closed, including on exceptions, so
        Windows never keeps a SQLite handle open after an operation returns.
        """
        if self.in_memory_fallback:
            with self._memory_lock:
                conn = self._memory_conn
                if conn is None:
                    self._enable_memory_fallback()
                    conn = self._memory_conn
                assert conn is not None
                try:
                    yield conn
                    conn.commit()
                except BaseException:
                    try:
                        conn.rollback()
                    except sqlite3.Error:
                        pass
                    raise
            return

        conn = self._raw_connect()
        try:
            yield conn
            conn.commit()
        except BaseException:
            try:
                conn.rollback()
            except sqlite3.Error:
                pass
            raise
        finally:
            # A close failure must not mask the original operation error.
            try:
                conn.close()
            except sqlite3.Error as exc:  # pragma: no cover - defensive
                logger.warning("Failed to close history connection: %s", exc)

    def _raw_connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=15.0)
        try:
            conn.execute("PRAGMA busy_timeout = 15000")
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
        except sqlite3.Error:
            conn.close()
            raise
        return conn

    def _open_probe(self) -> sqlite3.Connection:
        """Open a connection without switching journal modes.

        Integrity checks must not enable WAL (or otherwise mutate) a database
        that may be corrupt or is about to be quarantined.
        """
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.execute("PRAGMA busy_timeout = 10000")
        return conn

    # ------------------------------------------------------------------
    # Initialization, migration, and recovery
    # ------------------------------------------------------------------
    def _validate_existing_database(self) -> tuple[int, bool]:
        """Validate integrity and read the schema version using a closed probe.

        Any sqlite3.DatabaseError raised here is handled by
        :meth:`_initialize_or_recover` as corruption.
        """
        conn = self._open_probe()
        try:
            row = conn.execute("PRAGMA quick_check").fetchone()
            if not row or str(row[0]).strip().lower() != "ok":
                raise sqlite3.DatabaseError("SQLite quick_check failed")
            version = int(conn.execute("PRAGMA user_version").fetchone()[0] or 0)
            has_ops = bool(
                conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='operations'"
                ).fetchone()
            )
            return version, has_ops
        finally:
            conn.close()

    def _backup_before_migration(self) -> None:
        backup = self.db_path.with_name(
            f"{self.db_path.stem}.pre-v{DB_SCHEMA_VERSION}{self.db_path.suffix}.bak"
        )
        if backup.exists():
            logger.info("Migration backup already exists at %s; leaving it intact.", backup)
            return

        # Flush WAL content into the main database before copying so the backup
        # is a complete snapshot, then close every handle before the copy.
        checkpoint_conn: sqlite3.Connection | None = None
        try:
            checkpoint_conn = sqlite3.connect(str(self.db_path), timeout=10.0)
            checkpoint_conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            checkpoint_conn.commit()
        except sqlite3.Error as exc:
            logger.warning(
                "Could not checkpoint %s before migration backup: %s", self.db_path, exc
            )
        finally:
            if checkpoint_conn is not None:
                checkpoint_conn.close()

        try:
            shutil.copy2(self.db_path, backup)
            logger.info("Created pre-migration history backup at %s", backup)
        except OSError as exc:
            # Never silently discard a user's history: surface the failure in
            # the log, but continue with the in-place schema migration.
            logger.error(
                "Could not create pre-migration backup %s: %s", backup, exc
            )

    def _snapshot_sidecars(self) -> None:
        """Copy WAL/shm files before the integrity probe can consume them.

        SQLite may recover or discard a malformed ``-wal`` file merely by
        opening the database.  Keeping a byte-for-byte pre-check snapshot lets
        corruption quarantine preserve the original sidecars as evidence.
        """
        for suffix in ("-wal", "-shm"):
            sidecar = Path(str(self.db_path) + suffix)
            if not sidecar.is_file():
                continue
            snapshot = Path(str(self.db_path) + f"{suffix}.sortify-precheck")
            try:
                if snapshot.exists():
                    snapshot.unlink()
                shutil.copy2(sidecar, snapshot)
                self._precheck_sidecars[suffix] = snapshot
            except OSError as exc:
                logger.debug("Could not snapshot %s before integrity check: %s", sidecar, exc)

    def _discard_sidecar_snapshots(self) -> None:
        for snapshot in self._precheck_sidecars.values():
            try:
                if snapshot.exists():
                    snapshot.unlink()
            except OSError as exc:
                logger.debug("Could not remove sidecar snapshot %s: %s", snapshot, exc)
        self._precheck_sidecars.clear()

    def _initialize_or_recover(self) -> None:
        existed = False
        try:
            existed = self.db_path.is_file() and self.db_path.stat().st_size > 0
        except OSError:
            existed = self.db_path.exists()

        if existed:
            self._snapshot_sidecars()

        try:
            if existed:
                current_version, has_ops = self._validate_existing_database()
                if has_ops and current_version < DB_SCHEMA_VERSION:
                    self._backup_before_migration()
        except sqlite3.DatabaseError as exc:
            logger.warning(
                "Corrupt SQLite database detected at %s (%s); quarantining and creating a clean database.",
                self.db_path,
                exc,
            )
            self._quarantine_corrupt_database()
            # If quarantine itself failed, the raised OSError/sqlite3.Error is
            # caught by __init__, which logs it and enables the memory fallback.
        finally:
            if not self.recovered_from_corruption:
                self._discard_sidecar_snapshots()

        conn = self._raw_connect()
        try:
            self._apply_schema(conn)
            conn.commit()
        finally:
            conn.close()

    def _quarantine_corrupt_database(self) -> None:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        backup = self.db_path.with_name(
            f"{self.db_path.stem}.corrupt-{timestamp}{self.db_path.suffix}.bak"
        )
        moved_any = False

        move_errors: list[OSError] = []
        if self.db_path.exists():
            try:
                os.replace(self.db_path, backup)
                moved_any = True
            except OSError as exc:
                move_errors.append(exc)

        # Move WAL/shm sidecars next to the quarantined main database instead
        # of deleting them.  Prefer the pre-check snapshot, which still exists
        # even if SQLite consumed the original sidecar during validation.
        for suffix in ("-wal", "-shm"):
            sidecar_backup = Path(str(backup) + suffix)
            snapshot = self._precheck_sidecars.get(suffix)
            if snapshot is not None and snapshot.exists():
                try:
                    os.replace(snapshot, sidecar_backup)
                    moved_any = True
                except OSError as exc:
                    move_errors.append(exc)

            sidecar = Path(str(self.db_path) + suffix)
            if not sidecar.exists():
                continue
            try:
                if sidecar_backup.exists():
                    os.replace(sidecar, Path(str(sidecar_backup) + ".live"))
                else:
                    os.replace(sidecar, sidecar_backup)
                moved_any = True
            except OSError as exc:
                move_errors.append(exc)

        if move_errors:
            # Windows can still deny a move if an external process holds the
            # file.  Preserve byte-for-byte copies when possible, then surface
            # the real cause rather than silently pretending recovery worked.
            for exc in move_errors:
                logger.warning("Could not move corrupt database file: %s", exc)
            try:
                if self.db_path.exists() and not backup.exists():
                    shutil.copy2(self.db_path, backup)
                    moved_any = True
                for suffix in ("-wal", "-shm"):
                    sidecar = Path(str(self.db_path) + suffix)
                    sidecar_backup = Path(str(backup) + suffix)
                    if sidecar.exists() and not sidecar_backup.exists():
                        shutil.copy2(sidecar, sidecar_backup)
                if self.db_path.exists():
                    self.db_path.unlink()
            except OSError as copy_exc:
                logger.error(
                    "Database quarantine failed for %s (copy fallback: %s)",
                    self.db_path,
                    copy_exc,
                )
                raise

        if moved_any and backup.exists():
            self.recovered_from_corruption = True
            self.recovery_backup_path = backup
            logger.info("Corrupt database preserved at %s", backup)

    def _apply_schema(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS operations (
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
            """CREATE TABLE IF NOT EXISTS suggestion_cache (
              cache_key TEXT PRIMARY KEY,
              payload_json TEXT NOT NULL,
              updated_iso TEXT NOT NULL
            )"""
        )

        # Databases created by very old Sortify/RenovaAI builds may lack columns
        # that were added later.  Add them without touching existing rows.
        columns = {
            str(row[1]).lower()
            for row in conn.execute("PRAGMA table_info(operations)").fetchall()
        }
        if "error" not in columns:
            conn.execute("ALTER TABLE operations ADD COLUMN error TEXT")
        if "undone" not in columns:
            conn.execute(
                "ALTER TABLE operations ADD COLUMN undone INTEGER NOT NULL DEFAULT 0"
            )

        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_operations_session_id ON operations(session_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_operations_timestamp ON operations(timestamp)"
        )
        conn.execute(f"PRAGMA user_version = {DB_SCHEMA_VERSION}")

    # ------------------------------------------------------------------
    # Operations
    # ------------------------------------------------------------------
    def record(
        self,
        session_id: str,
        old: Path | str,
        new: Path | str,
        status: str,
        error: str | None = None,
    ) -> None:
        with self._connection() as c:
            c.execute(
                "INSERT INTO operations(session_id,original_path,new_path,timestamp,status,error) VALUES(?,?,?,?,?,?)",
                (
                    session_id,
                    str(old),
                    str(new),
                    datetime.now().isoformat(timespec="seconds"),
                    status,
                    error,
                ),
            )

    def recent(self, limit: int = 500) -> list[dict]:
        with self._connection() as c:
            c.row_factory = sqlite3.Row
            rows = c.execute(
                "SELECT * FROM operations ORDER BY id DESC LIMIT ?", (int(limit),)
            ).fetchall()
            return [dict(r) for r in rows]

    def mark_undone(self, operation_id: int) -> None:
        with self._connection() as c:
            c.execute("UPDATE operations SET undone=1 WHERE id=?", (operation_id,))

    def mark_session_undone(self, session_id: str) -> None:
        with self._connection() as c:
            c.execute(
                "UPDATE operations SET undone=1 WHERE session_id=?", (session_id,)
            )

    def prune_older_than(self, days: int) -> int:
        cutoff = (datetime.now() - timedelta(days=max(1, int(days)))).isoformat(
            timespec="seconds"
        )
        with self._connection() as c:
            cur = c.execute("DELETE FROM operations WHERE timestamp < ?", (cutoff,))
            return cur.rowcount

    def clear_all(self) -> None:
        with self._connection() as c:
            c.execute("DELETE FROM operations")

    def get_cached_suggestion(self, cache_key: str) -> dict | None:
        try:
            with self._connection() as c:
                row = c.execute(
                    "SELECT payload_json FROM suggestion_cache WHERE cache_key=?",
                    (cache_key,),
                ).fetchone()
                if row:
                    data = json.loads(row[0])
                    if isinstance(data, dict):
                        return data
        except (sqlite3.Error, ValueError, TypeError) as exc:
            logger.debug("Cache read failed: %s", exc)
        return None

    def set_cached_suggestion(self, cache_key: str, payload: dict) -> None:
        try:
            with self._connection() as c:
                c.execute(
                    "INSERT OR REPLACE INTO suggestion_cache(cache_key, payload_json, updated_iso) VALUES(?,?,?)",
                    (
                        cache_key,
                        json.dumps(payload, ensure_ascii=False),
                        datetime.now().isoformat(timespec="seconds"),
                    ),
                )
        except (sqlite3.Error, TypeError, ValueError) as exc:
            logger.debug("Cache write failed: %s", exc)

    def clear_cache(self) -> None:
        with self._connection() as c:
            c.execute("DELETE FROM suggestion_cache")

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------
    def close(self) -> None:
        """Close the shared in-memory connection (file connections are per-op)."""
        with self._memory_lock:
            if self._memory_conn is not None:
                try:
                    self._memory_conn.commit()
                except sqlite3.Error:
                    pass
                try:
                    self._memory_conn.close()
                finally:
                    self._memory_conn = None

        if not self.in_memory_fallback and self.db_path.is_file():
            # A clean checkpoint lets SQLite remove -wal/-shm sidecars, which
            # keeps temporary history directories deletable on Windows.
            checkpoint: sqlite3.Connection | None = None
            try:
                checkpoint = sqlite3.connect(str(self.db_path), timeout=5.0)
                checkpoint.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                checkpoint.commit()
            except sqlite3.Error as exc:
                logger.debug("History checkpoint on close skipped: %s", exc)
            finally:
                if checkpoint is not None:
                    checkpoint.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
