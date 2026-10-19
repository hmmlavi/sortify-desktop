"""Verify the Windows release assets and write SHA256SUMS.txt and release notes.

Usage: python packaging/verify_release_assets.py <asset-dir> --notes-out <file>

Checks that every expected asset exists and is non-empty, that ZIP archives pass
their CRC test, and that every Sortify.exe found is a 64-bit Windows PE image.
Any failure exits non-zero so the publish job stops before anything is uploaded.
"""

from __future__ import annotations

import argparse
import hashlib
import struct
import sys
import zipfile
from pathlib import Path

EXPECTED = (
    "Sortify-Setup-1.0.0.exe",
    "Sortify-1.0.0-windows-x64-standalone.zip",
    "Sortify-1.0.0-windows-x64-portable.zip",
)
PE_MACHINE_AMD64 = 0x8664
PE_MACHINE_I386 = 0x14C  # Inno Setup loaders are 32-bit; the app they install is x64.


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def check_pe(data: bytes, label: str, allowed: tuple[int, ...] = (PE_MACHINE_AMD64,)) -> int:
    if data[:2] != b"MZ":
        raise SystemExit(f"{label}: not an MZ executable")
    offset = struct.unpack_from("<I", data, 0x3C)[0]
    if data[offset : offset + 4] != b"PE\0\0":
        raise SystemExit(f"{label}: missing PE signature")
    machine = struct.unpack_from("<H", data, offset + 4)[0]
    if machine not in allowed:
        raise SystemExit(f"{label}: machine 0x{machine:04x}, expected one of {[hex(m) for m in allowed]}")
    return machine


def check_zip(path: Path) -> list[str]:
    with zipfile.ZipFile(path) as archive:
        bad = archive.testzip()
        if bad is not None:
            raise SystemExit(f"{path.name}: corrupt member {bad}")
        names = archive.namelist()
        for name in names:
            if name.lower().endswith("sortify.exe"):
                machine = check_pe(archive.read(name), f"{path.name}:{name}")
                print(f"  {name}: machine 0x{machine:04x}")
        return names


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("asset_dir", type=Path)
    parser.add_argument("--notes-out", type=Path, required=True)
    args = parser.parse_args()

    lines = []
    for name in EXPECTED:
        path = args.asset_dir / name
        if not path.is_file() or path.stat().st_size == 0:
            raise SystemExit(f"missing or empty asset: {name}")
        if name.endswith(".zip"):
            members = check_zip(path)
            print(f"{name}: {len(members)} members, CRC OK")
        else:
            machine = check_pe(path.read_bytes(), name, (PE_MACHINE_I386, PE_MACHINE_AMD64))
            print(f"{name}: Windows PE executable, machine 0x{machine:04x}")
        lines.append((name, path.stat().st_size, sha256(path)))

    sums = args.asset_dir / "SHA256SUMS.txt"
    sums.write_text("".join(f"{digest}  {name}\n" for name, _, digest in lines), encoding="utf-8")
    print(sums.read_text(encoding="utf-8"), end="")

    notes = [
        "## Sortify 1.0.0 (Windows x64)",
        "",
        "Built by GitHub Actions on Windows runners from the tagged commit. Unsigned builds:",
        "Windows SmartScreen may warn on first run; compare the SHA-256 values below first.",
        "",
        "| File | Size (bytes) | SHA-256 |",
        "| --- | ---: | --- |",
    ]
    notes += [f"| `{name}` | {size:,} | `{digest}` |" for name, size, digest in lines]
    args.notes_out.write_text("\n".join(notes) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
