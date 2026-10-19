"""Fetch the inputs needed by ``build_portable_windows.py``.

Downloads (with pip, so no manual archive hunting):

* Windows wheels for every runtime dependency pinned in ``requirements-lock.txt``
  (the versions the test suite runs against; build tools are skipped);
* the official CPython *embeddable* distribution for win_amd64, which the
  ``python-embed`` project republishes on PyPI.

The downloaded wheels and the extracted runtime are build inputs only; they are
never committed and nothing here runs on the user's machine.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
REQUIREMENTS = ROOT_DIR / "requirements-lock.txt"
BUILD_ONLY = {"pyinstaller", "pyinstaller-hooks-contrib"}
# The PySide6 metapackage pulls Addons and QtWebEngine; Sortify only imports
# Core/Gui/Widgets/Svg, which ship in PySide6-Essentials (see _runtime_requirements).
NOT_SHIPPED = {"pyside6_addons"}
WINDOWS_ONLY = ("pywin32-ctypes>=0.2.0",)


class FetchError(RuntimeError):
    """Raised when an input cannot be downloaded or extracted."""


def _runtime_requirements() -> list[str]:
    """Return requirement specifiers that belong in the shipped payload."""
    requirements: list[str] = []
    for raw_line in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        name = re.split(r"[<>=!~\[ ;]", line, maxsplit=1)[0].strip().lower()
        if name in BUILD_ONLY or name in NOT_SHIPPED:
            continue
        if name == "pyside6":
            line = re.sub(r"^pyside6", "PySide6-Essentials", line, flags=re.IGNORECASE)
        requirements.append(line)
    if not requirements:
        raise FetchError(f"{REQUIREMENTS} lists no runtime dependencies")
    return requirements


def download_wheels(destination: Path, python_version: str, *, platform: str = "win_amd64") -> list[Path]:
    destination.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        "-m",
        "pip",
        "download",
        "--dest",
        str(destination),
        "--only-binary=:all:",
        "--platform",
        platform,
        "--python-version",
        python_version,
        "--no-cache-dir",
        "--quiet",
        *_runtime_requirements(),
    ]
    if platform.startswith("win"):
        # Environment markers are evaluated for the build host, not the target,
        # so Windows-only dependencies must be requested explicitly.
        command.extend(WINDOWS_ONLY)
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise FetchError("pip download failed:\n" + (result.stderr or result.stdout).strip())
    wheels = sorted(destination.glob("*.whl"))
    if not wheels:
        raise FetchError(f"no wheels were downloaded into {destination}")
    return wheels


def fetch_runtime(destination: Path, python_version: str) -> Path:
    """Download python-embed and extract the win_amd64 embeddable runtime."""
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="sortify-embed-") as workdir:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "download",
                "--dest",
                workdir,
                "--no-deps",
                "--no-binary=:all:",
                "--no-cache-dir",
                "--quiet",
                f"python-embed=={python_version}",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise FetchError(
                "could not download the embeddable runtime:\n" + (result.stderr or result.stdout).strip()
            )
        archives = sorted(Path(workdir).glob("python_embed-*.tar.gz"))
        if not archives:
            expected = "3.13"
            raise FetchError(
                f"python-embed has no {python_version} release; "
                f"choose a published version such as {expected}.0"
            )
        with tarfile.open(archives[0]) as archive:
            members = [member for member in archive.getmembers() if member.name.endswith("data.zip")]
            if not members:
                raise FetchError("python-embed sdist does not contain data.zip")
            extracted = archive.extractfile(members[0])
            if extracted is None:
                raise FetchError("python-embed data.zip could not be read")
            payload = extracted.read()
    with tempfile.TemporaryDirectory(prefix="sortify-embed-zip-") as zipdir:
        archive_path = Path(zipdir) / "data.zip"
        archive_path.write_bytes(payload)
        with zipfile.ZipFile(archive_path) as archive:
            runtime_members = [name for name in archive.namelist() if name.startswith("cp313/")]
            if not runtime_members:
                raise FetchError("python-embed payload has no cp313 runtime")
            for member in runtime_members:
                if member.endswith("/"):
                    continue
                relative = Path(member).relative_to("cp313")
                target = destination / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as source, target.open("wb") as output:
                    output.write(source.read())
    if not (destination / "python313.dll").is_file():
        raise FetchError(f"{destination} does not look like a CPython embeddable runtime")
    return destination


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--output", type=Path, default=Path("/tmp/sortify-build"))
    parser.add_argument("--python-version", default="3.13.0", help="python-embed release (default 3.13.0)")
    parser.add_argument(
        "--wheel-python",
        default="3.13",
        help="Python version whose wheels to resolve (default 3.13)",
    )
    args = parser.parse_args(argv)
    output = args.output.resolve()
    try:
        wheels = download_wheels(output / "wheels", args.wheel_python)
        runtime = fetch_runtime(output / "winpy", args.python_version)
    except FetchError as exc:
        print(f"FETCH FAILED: {exc}", file=sys.stderr)
        return 1
    print(f"wheels:  {len(wheels)} files in {output / 'wheels'}")
    for wheel in wheels:
        print(f"  {wheel.name}")
    print(f"runtime: {runtime}")
    print("PORTABLE INPUTS OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
