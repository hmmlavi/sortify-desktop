"""Batch-level name conflict resolution for rename proposals.

Kept free of Qt so the rules can be tested directly. A proposal conflicts with
another proposal in the batch, or with a file that already exists in the same
folder. Files that are themselves being renamed in the batch vacate their names,
so swaps and chains of renames are not treated as conflicts.
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path

from app.core.filename_validator import resolve_unique_name, sanitize_filename


class NameLookup:
    """Membership view over several casefolded name sets, without copying them."""

    def __init__(self, *sources) -> None:
        self._sources = sources

    def __contains__(self, name: str) -> bool:
        return any(name in source for source in self._sources)


def _names_on_disk(directory: Path) -> set[str]:
    try:
        return {entry.name.casefold() for entry in os.scandir(directory)}
    except OSError:
        return set()


def resolve_batch_conflicts(records: Iterable, max_length: int, style: str) -> int:
    """Give every selected record that collides a unique name. Returns the number changed.

    ``records`` are objects with ``path``, ``extension``, ``selected``,
    ``proposed_name``, ``conflict_reason`` and ``status`` attributes.
    """
    records = list(records)
    # Names used by unselected files in the batch.
    taken: set[str] = {r.path.name.casefold() for r in records if not r.selected}
    # Selected files vacate their current names when renamed.
    vacating = {(r.path.parent, r.path.name.casefold()) for r in records if r.selected}
    disk_names: dict[Path, set[str]] = {}
    resolved = 0

    def occupied_on_disk(directory: Path) -> set[str]:
        if directory not in disk_names:
            disk_names[directory] = {
                name
                for name in _names_on_disk(directory)
                if (directory, name) not in vacating
            }
        return disk_names[directory]

    for record in records:
        if not record.selected or not record.proposed_name:
            continue
        clean = sanitize_filename(record.proposed_name, record.extension, max_length, style)
        occupied = NameLookup(taken, occupied_on_disk(record.path.parent))
        if clean.casefold() in occupied or record.conflict_reason:
            unique = resolve_unique_name(
                clean, record.extension, occupied, max_length=max_length, style=style
            )
            if unique != record.proposed_name:
                record.proposed_name = unique
                record.status = "Edited by user"
                resolved += 1
            taken.add(unique.casefold())
        else:
            record.proposed_name = clean
            taken.add(clean.casefold())
    return resolved
