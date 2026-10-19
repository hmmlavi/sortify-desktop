"""Safe two-phase transactional rename and organization engine with rollback and session undo."""

from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

from app.core.filename_validator import validate_destination, validate_filename_text
from app.core.operation_history import OperationHistory


class RenameEngine:
    def __init__(self, history: OperationHistory | None = None):
        self.history = history or OperationHistory()

    def apply(
        self,
        root: Path,
        proposals: list[tuple[Path, str | Path]],
        allow_subfolders: bool = False,
        record_status: str = "success",
    ) -> dict:
        root = Path(root).resolve()
        session = uuid4().hex[:12]
        report: dict = {
            "session_id": session,
            "success": [],
            "failed": [],
            "skipped": [],
        }

        source_set = set()
        for s, _ in proposals:
            try:
                source_set.add(str(Path(s).resolve()).casefold())
            except OSError:
                pass

        planned: list[tuple[Path, Path]] = []
        seen: set[str] = set()

        for raw_source, new_target in proposals:
            source = Path(raw_source)
            try:
                if source.is_symlink():
                    report["failed"].append(
                        (str(source), "Symbolic links cannot be renamed for safety")
                    )
                    continue
                if not source.exists() or not source.is_file():
                    report["skipped"].append((str(source), "Source no longer exists"))
                    continue
            except OSError as e:
                report["failed"].append((str(source), f"Cannot access source: {e}"))
                continue

            if isinstance(new_target, Path):
                destination = new_target
            else:
                target_str = str(new_target or "").strip()
                if not target_str:
                    report["failed"].append((str(source), "Proposed filename is empty"))
                    continue
                if allow_subfolders and ("/" in target_str or "\\" in target_str):
                    rel_parts = [p for p in Path(target_str.replace("\\", "/")).parts if p not in {"", "."}]
                    if not rel_parts or ".." in rel_parts:
                        report["failed"].append(
                            (str(source), "Invalid relative destination path")
                        )
                        continue
                    destination = root.joinpath(*rel_parts)
                else:
                    name_err = validate_filename_text(target_str)
                    if name_err:
                        report["failed"].append((str(source), name_err))
                        continue
                    try:
                        destination = source.with_name(target_str)
                    except ValueError as e:
                        report["failed"].append((str(source), f"Invalid filename: {e}"))
                        continue

            try:
                dest_resolved_str = str(
                    destination.parent.resolve() / destination.name
                ).casefold()
            except OSError as e:
                report["failed"].append((str(source), f"Invalid destination path: {e}"))
                continue

            if dest_resolved_str in seen:
                report["failed"].append(
                    (str(source), "Duplicate destination within batch")
                )
                continue
            seen.add(dest_resolved_str)

            err = validate_destination(
                source, destination, root, allow_subfolders=allow_subfolders
            )
            # Existing destination is allowed only if it is another source in this batch; cycle handling follows.
            if (
                err
                and destination.exists()
                and not destination.is_symlink()
                and str(destination.resolve()).casefold() in source_set
            ):
                err = None

            if err:
                report["failed"].append((str(source), err))
                continue

            try:
                if (
                    source.parent.resolve() == destination.parent.resolve()
                    and source.name == destination.name
                ):
                    report["skipped"].append((str(source), "Name is unchanged"))
                    continue
            except OSError:
                pass

            planned.append((source, destination))

        # Reject collisions with non-source existing files.
        source_keys = {str(s.resolve()).casefold() for s, _ in planned}
        safe: list[tuple[Path, Path]] = []
        for s, d in planned:
            if d.exists() and str(d.resolve()).casefold() not in source_keys:
                report["failed"].append(
                    (str(s), f"Destination already exists: {d.name}")
                )
            else:
                safe.append((s, d))

        if not safe:
            return report

        # Two-phase temporary rename avoids cycles such as A->B and B->A.
        staged: list[tuple[Path, Path, Path]] = []
        created_dirs: list[Path] = []
        try:
            for i, (s, d) in enumerate(safe):
                if allow_subfolders and not d.parent.exists():
                    d.parent.mkdir(parents=True, exist_ok=True)
                    created_dirs.append(d.parent)
                temp = s.with_name(f".sortify-tmp-{session}-{i}{s.suffix}")
                while temp.exists():
                    temp = s.with_name(
                        f".sortify-tmp-{session}-{uuid4().hex[:6]}{s.suffix}"
                    )
                s.rename(temp)
                staged.append((s, d, temp))

            completed: list[tuple[Path, Path]] = []
            for s, d, temp in staged:
                if d.exists():
                    raise FileExistsError(f"Destination became occupied: {d}")
                temp.rename(d)
                completed.append((s, d))
        except OSError as e:
            # Best-effort rollback for every item in the transaction.
            for s, d, temp in reversed(staged):
                try:
                    if d.exists() and not s.exists():
                        d.rename(s)
                    elif temp.exists() and not s.exists():
                        temp.rename(s)
                except OSError:
                    continue
            for cdir in reversed(created_dirs):
                try:
                    if cdir.exists() and not any(cdir.iterdir()):
                        cdir.rmdir()
                except OSError:
                    continue
            report["failed"].append(
                ("batch", f"Batch failed and rollback was attempted: {e}")
            )
        else:
            for s, d in completed:
                self.history.record(session, s, d, record_status)
                report["success"].append((str(s), str(d)))

        return report

    def undo_last_session(self) -> dict:
        rows = self.history.recent(1000)
        candidates: list[str] = []
        seen: set[str] = set()
        for r in rows:
            if (
                r["status"] == "success"
                and not r["undone"]
                and r["session_id"] not in seen
            ):
                seen.add(r["session_id"])
                candidates.append(r["session_id"])
        if not candidates:
            return {
                "success": [],
                "failed": [("undo", "No completed session available to undo")],
                "skipped": [],
            }
        return self.undo_session(candidates[0], rows=rows)

    def undo_session(self, session_id: str, rows: list[dict] | None = None) -> dict:
        if rows is None:
            rows = self.history.recent(1000)
        items = [
            r
            for r in rows
            if r["session_id"] == session_id
            and r["status"] == "success"
            and not r["undone"]
        ]
        if not items:
            return {
                "success": [],
                "failed": [("undo", f"Session {session_id} has no undoable operations")],
                "skipped": [],
            }

        reverse: list[tuple[Path, str | Path]] = []
        all_parents: list[str] = []
        cross_dir = False

        for r in items:
            old = Path(r["original_path"])
            new = Path(r["new_path"])
            if not new.exists():
                return {
                    "success": [],
                    "failed": [(str(new), "Renamed file is missing; undo cancelled")],
                    "skipped": [],
                }
            old_parent = old.parent.resolve()
            new_parent = new.parent.resolve()
            all_parents.extend([str(old_parent), str(new_parent)])
            if old_parent != new_parent:
                cross_dir = True
                reverse.append((new, old))
            else:
                reverse.append((new, old.name))

        common_root = Path(os.path.commonpath(all_parents))
        result = self.apply(
            common_root,
            reverse,
            allow_subfolders=cross_dir,
            record_status="restored",
        )
        if result["success"]:
            self.history.mark_session_undone(session_id)
        return result
