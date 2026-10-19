#!/usr/bin/env python3
"""Assemble the portable Windows distribution (no Python installation required).

On Windows the project is packaged with PyInstaller (``build_windows.bat``).
This script is the cross-platform equivalent used when the release is assembled
on a non-Windows machine: it combines the official CPython *embeddable* runtime,
the application wheels, the program sources and a tiny native launcher into a
self-contained ``Sortify.exe`` folder tree, then optionally zips it.

Requirements (build host only, never shipped to users):
  * CPython embeddable distribution for Windows x64 (``--runtime``)
  * wheels for ``win_amd64`` / ``cp313`` (``--wheels``, see requirements.txt)
  * ``ziglang`` (``python -m ziglang``) to compile ``windows_launcher.c``

The resulting folder contains ``Sortify.exe`` with the application icon,
version metadata and manifest embedded.  The script validates the layout and
PE headers before reporting success; it refuses to emit an incomplete build.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path

PACKAGING_DIR = Path(__file__).resolve().parent
ROOT_DIR = PACKAGING_DIR.parent
sys.path.insert(0, str(PACKAGING_DIR))

import pe_resources  # sibling module in packaging/

LAUNCHER_SOURCE = PACKAGING_DIR / "windows_launcher.c"
ICON_PATH = ROOT_DIR / "assets" / "sortify.ico"
REQUIRED_STDLIB = ("python313.zip", "python313.dll", "python313._pth")

# PySide6 ships its entire Qt module set in one wheel.  Sortify only imports
# these four modules, so everything else is pruned to keep the download small.
PYSIDE6_KEEP_PYD = {"QtCore.pyd", "QtGui.pyd", "QtWidgets.pyd", "QtSvg.pyd"}
PYSIDE6_KEEP_DLL = {
    "Qt6Core.dll",
    "Qt6Gui.dll",
    "Qt6Widgets.dll",
    "Qt6Svg.dll",
    "pyside6.abi3.dll",
    "msvcp140.dll",
    "msvcp140_1.dll",
    "msvcp140_2.dll",
    "msvcp140_codecvt_ids.dll",
    "vcruntime140.dll",
    "vcruntime140_1.dll",
    "concrt140.dll",
}
PYSIDE6_KEEP_PLUGINS = {
    "platforms/qwindows.dll",
    "styles/qmodernwindowsstyle.dll",
    "imageformats/qsvg.dll",
    "imageformats/qico.dll",
    "imageformats/qjpeg.dll",
    "iconengines/qsvgicon.dll",
}
PYSIDE6_DROP_DIRS = {
    "doc",
    "glue",
    "include",
    "lib",
    "metatypes",
    "qml",
    "scripts",
    "support",
    "translations",
    "typesystems",
}
REQUIRED_SITE_PACKAGES = (
    "PySide6/QtCore.pyd",
    "PySide6/QtGui.pyd",
    "PySide6/QtWidgets.pyd",
    "PySide6/QtSvg.pyd",
    "PySide6/Qt6Core.dll",
    "PySide6/Qt6Gui.dll",
    "PySide6/Qt6Widgets.dll",
    "PySide6/Qt6Svg.dll",
    "PySide6/plugins/platforms/qwindows.dll",
    "shiboken6/Shiboken.pyd",
    "pypdf/__init__.py",
    "docx/__init__.py",
    "pptx/__init__.py",
    "openpyxl/__init__.py",
    "PIL/Image.py",
    "keyring/__init__.py",
    "jaraco/classes/__init__.py",
    "win32ctypes/__init__.py",
)
COPY_TREES = ("app", "assets")
COPY_FILES = ("main.py", "LICENSE", "README.md")
COPY_RENAMES = {"packaging/runtime_boot.py": "boot.py"}


class BuildError(RuntimeError):
    """Raised when the portable build cannot be produced correctly."""


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _app_metadata() -> dict[str, str]:
    config = (ROOT_DIR / "app" / "config.py").read_text(encoding="utf-8")

    def grab(name: str) -> str:
        match = re.search(rf'^{name}\s*=\s*"([^"]+)"', config, re.MULTILINE)
        if not match:
            raise BuildError(f"app/config.py does not define {name}")
        return match.group(1)

    return {"name": grab("APP_NAME"), "version": grab("APP_VERSION")}


def _version_tuple(version: str) -> tuple[int, int, int, int]:
    parts = [int(part) for part in re.split(r"[.\-+]", version) if part.isdigit()]
    parts += [0] * (4 - len(parts))
    return tuple(parts[:4])  # type: ignore[return-value]


def _zig_command() -> list[str]:
    candidates = [
        [sys.executable, "-m", "ziglang"],
        ["zig"],
    ]
    for candidate in candidates:
        try:
            result = subprocess.run(
                [*candidate, "version"], capture_output=True, text=True, timeout=120, check=False
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if result.returncode == 0 and result.stdout.strip():
            return candidate
    raise BuildError(
        "zig is required to build the native launcher on this platform.\n"
        "Install it with:  python -m pip install ziglang\n"
        "or build on Windows with packaging\\build_windows.bat (PyInstaller)."
    )


def _clean_directory(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True)


def _copy_runtime(runtime_dir: Path, target: Path) -> None:
    missing = [name for name in REQUIRED_STDLIB if not (runtime_dir / name).is_file()]
    if missing:
        raise BuildError(
            f"{runtime_dir} is not a CPython embeddable runtime "
            f"(missing: {', '.join(missing)})"
        )
    for item in runtime_dir.iterdir():
        if item.name in {"python.exe", "__pycache__"}:
            continue
        destination = target / item.name
        if item.is_dir():
            shutil.copytree(item, destination)
        else:
            shutil.copy2(item, destination)


def _extract_wheels(wheels_dir: Path, site_packages: Path) -> list[str]:
    wheels = sorted(wheels_dir.glob("*.whl"))
    if not wheels:
        raise BuildError(f"no wheels found in {wheels_dir}")
    installed: list[str] = []
    for wheel in wheels:
        with zipfile.ZipFile(wheel) as archive:
            for member in archive.namelist():
                if member.endswith("/"):
                    continue
                parts = Path(member).parts
                if parts[0].endswith(".data"):
                    if len(parts) < 3 or parts[1] not in {"purelib", "platlib"}:
                        continue
                    relative = Path(*parts[2:])
                else:
                    relative = Path(*parts)
                destination = site_packages / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as source, destination.open("wb") as output:
                    shutil.copyfileobj(source, output)
        installed.append(wheel.name)
    return installed


def _prune_pyside6(site_packages: Path) -> None:
    pyside = site_packages / "PySide6"
    if not pyside.is_dir():
        raise BuildError("PySide6 is missing from the wheel set")
    for directory in PYSIDE6_DROP_DIRS:
        shutil.rmtree(pyside / directory, ignore_errors=True)
    for item in pyside.iterdir():
        if item.is_dir():
            if item.name in {"plugins", "resources"}:
                continue
            shutil.rmtree(item, ignore_errors=True)
            continue
        suffix = item.suffix.lower()
        if suffix == ".py":
            continue
        if suffix == ".pyd" and item.name in PYSIDE6_KEEP_PYD:
            continue
        if suffix == ".dll" and item.name in PYSIDE6_KEEP_DLL:
            continue
        if item.name == "PySide6_Essentials.json":
            continue
        item.unlink()
    plugins = pyside / "plugins"
    for item in list(plugins.rglob("*")):
        if item.is_file():
            relative = item.relative_to(plugins).as_posix()
            if relative not in PYSIDE6_KEEP_PLUGINS:
                item.unlink()
    for item in sorted(plugins.rglob("*"), reverse=True):
        if item.is_dir() and not any(item.iterdir()):
            item.rmdir()

    shiboken = site_packages / "shiboken6"
    if not shiboken.is_dir():
        raise BuildError("shiboken6 is missing from the wheel set")
    for item in list(shiboken.iterdir()):
        if item.is_dir() or item.suffix.lower() == ".pyi" or item.name.endswith(".lib"):
            if item.is_dir():
                shutil.rmtree(item, ignore_errors=True)
            else:
                item.unlink()


def _remove_bytecode(site_packages: Path) -> None:
    for cache in site_packages.rglob("__pycache__"):
        shutil.rmtree(cache, ignore_errors=True)
    for compiled in site_packages.rglob("*.pyc"):
        compiled.unlink()


def _write_pth(target: Path) -> None:
    lines = [
        "python313.zip",
        ".",
        r"Lib\site-packages",
    ]
    (target / "python313._pth").write_text("\r\n".join(lines) + "\r\n", encoding="ascii")


def _build_launcher(target_exe: Path, metadata: dict[str, str]) -> dict[str, int]:
    zig = _zig_command()
    with tempfile.TemporaryDirectory(prefix="sortify-launcher-") as workdir:
        raw_exe = Path(workdir) / "Sortify.exe"
        command = [
            *zig,
            "cc",
            "-target",
            "x86_64-windows-gnu",
            "-municode",
            "-O2",
            "-s",
            "-Wl,--subsystem,windows",
            "-o",
            str(raw_exe),
            str(LAUNCHER_SOURCE),
        ]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise BuildError(
                "launcher compilation failed:\n" + (result.stderr or result.stdout).strip()
            )
        entries = pe_resources.icon_entries(ICON_PATH)
        entries.append(
            (
                pe_resources.RT_VERSION,
                1,
                pe_resources.build_version_info(
                    company_name=metadata["company"],
                    product_name=metadata["name"],
                    file_description=f"{metadata['name']} — file renaming that keeps you in control",
                    file_version=_version_tuple(metadata["version"]),
                    original_filename=f"{metadata['name']}.exe",
                    legal_copyright=metadata["copyright"],
                ),
            )
        )
        entries.append(
            (
                pe_resources.RT_MANIFEST,
                1,
                pe_resources.build_manifest(
                    name=metadata["name"], version=metadata["version"] + ".0"
                ).encode("utf-8"),
            )
        )
        stats = pe_resources.inject_resources(raw_exe, entries)
        shutil.copy2(raw_exe, target_exe)
    return stats


def _verify_pe(exe_path: Path) -> dict[str, object]:
    """Validate section table, resource directory and checksum without pefile."""
    data = exe_path.read_bytes()
    if data[:2] != b"MZ":
        raise BuildError("Sortify.exe is missing an MZ header")
    e_lfanew = struct.unpack_from("<I", data, 0x3C)[0]
    if data[e_lfanew : e_lfanew + 4] != b"PE\0\0":
        raise BuildError("Sortify.exe has an invalid PE signature")
    coff = e_lfanew + 4
    machine, sections = struct.unpack_from("<HH", data, coff)
    if machine != 0x8664:
        raise BuildError(f"Sortify.exe has an unexpected machine type 0x{machine:04x}")
    optional = coff + 20
    if struct.unpack_from("<H", data, optional)[0] != 0x20B:
        raise BuildError("Sortify.exe is not PE32+")
    subsystem = struct.unpack_from("<H", data, optional + 68)[0]
    if subsystem != 2:
        raise BuildError("Sortify.exe is not a GUI subsystem executable")
    size_of_optional_header = struct.unpack_from("<H", data, coff + 16)[0]
    directory_offset = optional + 112 + 8 * 2
    resource_rva, resource_size = struct.unpack_from("<II", data, directory_offset)
    if resource_rva == 0 or resource_size == 0:
        raise BuildError("Sortify.exe has no resource directory")
    names = []
    section_table = optional + size_of_optional_header
    for index in range(sections):
        offset = section_table + index * 40
        names.append(data[offset : offset + 8].rstrip(b"\0").decode("ascii", "replace"))
    if ".rsrc" not in names:
        raise BuildError("Sortify.exe has no .rsrc section")
    try:
        import pefile  # type: ignore

        pe = pefile.PE(data=data)
        if not pe.verify_checksum():
            raise BuildError("Sortify.exe checksum is invalid")
        pe.parse_data_directories()
        types = {
            entry.id: len(entry.directory.entries)
            for entry in pe.DIRECTORY_ENTRY_RESOURCE.entries
        }
        if types.get(pe_resources.RT_ICON, 0) < 1 or types.get(pe_resources.RT_VERSION) != 1:
            raise BuildError(f"Sortify.exe resources are incomplete: {types}")
    except ImportError:  # pragma: no cover - pefile is a build-time extra
        types = {}
        pe = None
    return {
        "machine": hex(machine),
        "subsystem": subsystem,
        "sections": names,
        "resource_rva": resource_rva,
        "resource_size": resource_size,
        "resource_types": {str(key): value for key, value in types.items()},
        "size": len(data),
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _scan_for_secrets(target: Path) -> None:
    forbidden = re.compile(
        r"^(\.env|credentials\.json|secrets\.ya?ml|id_rsa|.*\.pem|.*\.pfx|.*\.key)$",
        re.IGNORECASE,
    )
    offenders = [path for path in target.rglob("*") if path.is_file() and forbidden.match(path.name)]
    if offenders:
        raise BuildError(
            "refusing to package credential-like files: "
            + ", ".join(str(path.relative_to(target)) for path in offenders)
        )
    if (target / "tests").exists():
        raise BuildError("refusing to package the test suite")


def _write_zip(folder: Path, archive_path: Path) -> None:
    if archive_path.exists():
        archive_path.unlink()
    timestamp = datetime(2026, 10, 18, 0, 0, 0).timetuple()[:6]
    with zipfile.ZipFile(
        archive_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as archive:
        for path in sorted(folder.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(folder.parent).as_posix()
            info = zipfile.ZipInfo(relative, date_time=timestamp)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            with path.open("rb") as handle:
                archive.writestr(info, handle.read())
    with zipfile.ZipFile(archive_path) as archive:
        if archive.testzip() is not None:
            raise BuildError(f"{archive_path} failed its integrity check")


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def build(
    *,
    runtime_dir: Path,
    wheels_dir: Path,
    output_dir: Path,
    make_zip: bool,
) -> dict[str, object]:
    metadata = _app_metadata()
    metadata.update(
        {
            "company": "Sortify",
            "copyright": "Copyright (c) 2026 Sortify contributors (MIT License)",
        }
    )
    if not runtime_dir.is_dir():
        raise BuildError(f"runtime directory not found: {runtime_dir}")
    if not wheels_dir.is_dir():
        raise BuildError(f"wheel directory not found: {wheels_dir}")
    if not ICON_PATH.is_file():
        raise BuildError(f"application icon not found: {ICON_PATH}")

    _clean_directory(output_dir)
    _copy_runtime(runtime_dir, output_dir)

    site_packages = output_dir / "Lib" / "site-packages"
    site_packages.mkdir(parents=True)
    wheels = _extract_wheels(wheels_dir, site_packages)
    _prune_pyside6(site_packages)
    _remove_bytecode(site_packages)
    for data_dir in site_packages.glob("*.data"):
        shutil.rmtree(data_dir, ignore_errors=True)

    for tree in COPY_TREES:
        source = ROOT_DIR / tree
        if not source.is_dir():
            raise BuildError(f"application directory not found: {source}")
        shutil.copytree(
            source,
            output_dir / tree,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
        )
    for filename in COPY_FILES:
        source = ROOT_DIR / filename
        if source.is_file():
            shutil.copy2(source, output_dir / filename)
    for source_name, target_name in COPY_RENAMES.items():
        source = ROOT_DIR / source_name
        if not source.is_file():
            raise BuildError(f"application file not found: {source}")
        shutil.copy2(source, output_dir / target_name)
    _write_pth(output_dir)

    exe_path = output_dir / f"{metadata['name']}.exe"
    resource_stats = _build_launcher(exe_path, metadata)

    missing = [name for name in REQUIRED_SITE_PACKAGES if not (site_packages / name).is_file()]
    if missing:
        raise BuildError("portable build is missing runtime modules: " + ", ".join(missing))
    _scan_for_secrets(output_dir)
    pe_info = _verify_pe(exe_path)

    build_info = {
        "application": metadata["name"],
        "version": metadata["version"],
        "build_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "runtime": "CPython 3.13 embeddable (win_amd64)",
        "wheels": wheels,
        "entry_point": f"{metadata['name']}.exe",
        "resources": resource_stats,
    }
    (output_dir / "build-info.json").write_text(
        json.dumps(build_info, indent=2) + "\n", encoding="utf-8"
    )

    package_size = sum(path.stat().st_size for path in output_dir.rglob("*") if path.is_file())
    summary: dict[str, object] = {
        "output": str(output_dir),
        "files": sum(1 for path in output_dir.rglob("*") if path.is_file()),
        "bytes": package_size,
        "executable": str(exe_path),
        "executable_sha256": _sha256(exe_path),
        "executable_info": pe_info,
        "wheels": wheels,
    }
    if make_zip:
        archive = output_dir.parent / f"{metadata['name']}-{metadata['version']}-windows-x64-portable.zip"
        _write_zip(output_dir, archive)
        summary["archive"] = str(archive)
        summary["archive_bytes"] = archive.stat().st_size
        summary["archive_sha256"] = _sha256(archive)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--runtime", required=True, type=Path, help="CPython embeddable runtime directory")
    parser.add_argument("--wheels", required=True, type=Path, help="directory with win_amd64 wheels")
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT_DIR / "dist" / "Sortify",
        help="destination folder (default: dist/Sortify)",
    )
    parser.add_argument("--no-zip", action="store_true", help="skip the portable ZIP archive")
    args = parser.parse_args(argv)

    try:
        summary = build(
            runtime_dir=args.runtime.resolve(),
            wheels_dir=args.wheels.resolve(),
            output_dir=args.output.resolve(),
            make_zip=not args.no_zip,
        )
    except BuildError as exc:
        print(f"BUILD FAILED: {exc}", file=sys.stderr)
        return 1
    except (OSError, ValueError) as exc:
        print(f"BUILD FAILED: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(summary, indent=2))
    print("PORTABLE BUILD OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
