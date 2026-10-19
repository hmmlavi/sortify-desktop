"""Release orchestration and SHA-256 checksum generator for Sortify."""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
RELEASE_DIR = ROOT_DIR / "release"
DIST_DIR = ROOT_DIR / "dist" / "Sortify"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def generate_checksums() -> Path:
    RELEASE_DIR.mkdir(parents=True, exist_ok=True)
    # The one-folder app lives in dist/Sortify for both the PyInstaller and the
    # portable build (dist/ is not tracked and not archived); the ZIP lives in release/windows.
    candidates = [
        RELEASE_DIR / "Sortify-Setup-1.0.0.exe",
        RELEASE_DIR / "windows" / "Sortify-1.0.0-windows-x64-portable.zip",
        DIST_DIR / "Sortify.exe",
        DIST_DIR / "build-info.json",
        ROOT_DIR / "assets" / "sortify.ico",
        ROOT_DIR / "assets" / "sortify-icon.svg",
        ROOT_DIR / "assets" / "sortify-logo.svg",
        ROOT_DIR / "Sortify.spec",
        ROOT_DIR / "packaging" / "installer.iss",
    ]
    lines: list[str] = []
    for item in candidates:
        if item.is_file():
            rel = item.relative_to(ROOT_DIR).as_posix()
            lines.append(f"{sha256_file(item)}  {rel}")

    checksum_path = RELEASE_DIR / "SHA256SUMS.txt"
    checksum_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return checksum_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sortify release checksum & artifact helper")
    parser.add_argument(
        "--checksums-only",
        action="store_true",
        help="Generate release/SHA256SUMS.txt for existing build and release artifacts.",
    )
    parser.parse_args(argv)
    out = generate_checksums()
    print(f"Wrote checksums to {out}:")
    print(out.read_text(encoding="utf-8").strip())
    return 0


if __name__ == "__main__":
    sys.exit(main())
