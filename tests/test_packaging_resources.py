"""Structural tests for the cross-platform PE resource writer used by the portable build."""

from __future__ import annotations

import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "packaging"))

import pe_resources  # packaging helper, not an installed module
import prepare_portable_inputs  # packaging helper, not an installed module

ICON_PATH = ROOT_DIR / "assets" / "sortify.ico"


def parse_resource_directory(blob: bytes, offset: int = 0) -> dict:
    """Minimal resource-directory reader used to verify the generated section."""
    _characteristics, _timestamp, _major, _minor, named, ids = struct.unpack_from(
        "<IIHHHH", blob, offset
    )
    entries = {}
    for index in range(named + ids):
        name, target = struct.unpack_from("<II", blob, offset + 16 + index * 8)
        if target & 0x80000000:
            entries[name] = parse_resource_directory(blob, target & 0x7FFFFFFF)
        else:
            data_rva, size, _codepage, _reserved = struct.unpack_from("<IIII", blob, target)
            entries[name] = (data_rva, size)
    return entries


class IconParsingTests(unittest.TestCase):
    def test_icon_contains_expected_sizes(self):
        images = pe_resources.read_ico(ICON_PATH)
        self.assertGreaterEqual(len(images), 6)
        sizes = {(image.width or 256, image.height or 256) for image in images}
        self.assertIn((256, 256), sizes)
        self.assertIn((16, 16), sizes)

    def test_rejects_non_icon_files(self):
        with tempfile.TemporaryDirectory() as directory:
            bogus = Path(directory) / "bogus.ico"
            bogus.write_bytes(b"not an icon at all")
            with self.assertRaises(pe_resources.ResourceError):
                pe_resources.read_ico(bogus)

    def test_icon_entries_include_group_directory(self):
        entries = pe_resources.icon_entries(ICON_PATH)
        types = [type_id for type_id, _name, _payload in entries]
        self.assertEqual(types.count(pe_resources.RT_GROUP_ICON), 1)
        icons = [entry for entry in entries if entry[0] == pe_resources.RT_ICON]
        self.assertEqual(len(icons), len(pe_resources.read_ico(ICON_PATH)))
        group = next(payload for type_id, _, payload in entries if type_id == pe_resources.RT_GROUP_ICON)
        reserved, kind, count = struct.unpack_from("<HHH", group, 0)
        self.assertEqual((reserved, kind, count), (0, 1, len(icons)))
        for index in range(count):
            _w, _h, _colors, _res, _planes, _bits, size, resource_id = struct.unpack_from(
                "<BBBBHHIH", group, 6 + index * 14
            )
            self.assertEqual(size, len(icons[index][2]))
            self.assertEqual(resource_id, index + 1)


class ResourceSectionTests(unittest.TestCase):
    def test_section_has_three_level_tree(self):
        entries = pe_resources.icon_entries(ICON_PATH)
        entries.append(
            (
                pe_resources.RT_VERSION,
                1,
                pe_resources.build_version_info(
                    company_name="Sortify",
                    product_name="Sortify",
                    file_description="Sortify",
                    file_version=(1, 0, 0, 0),
                    original_filename="Sortify.exe",
                    legal_copyright="Copyright (c) 2026 Sortify",
                ),
            )
        )
        entries.append((pe_resources.RT_MANIFEST, 1, pe_resources.build_manifest().encode("utf-8")))
        blob = pe_resources.build_resource_section(entries, base_rva=0x10000)
        tree = parse_resource_directory(blob)
        self.assertEqual(
            set(tree),
            {
                pe_resources.RT_ICON,
                pe_resources.RT_GROUP_ICON,
                pe_resources.RT_VERSION,
                pe_resources.RT_MANIFEST,
            },
        )
        self.assertEqual(len(tree[pe_resources.RT_ICON]), len(pe_resources.read_ico(ICON_PATH)))
        icon_languages = tree[pe_resources.RT_ICON][1]
        self.assertEqual(set(icon_languages), {pe_resources.LANG_EN_US})
        rva, size = icon_languages[pe_resources.LANG_EN_US]
        self.assertGreaterEqual(rva, 0x10000)
        self.assertEqual(blob[rva - 0x10000 : rva - 0x10000 + size], pe_resources.read_ico(ICON_PATH)[0].payload)

    def test_duplicate_resource_ids_are_rejected(self):
        with self.assertRaises(pe_resources.ResourceError):
            pe_resources.build_resource_section(
                [(pe_resources.RT_MANIFEST, 1, b"a"), (pe_resources.RT_MANIFEST, 1, b"b")], 0x1000
            )

    def test_empty_input_is_rejected(self):
        with self.assertRaises(pe_resources.ResourceError):
            pe_resources.build_resource_section([], 0x1000)


class VersionInfoTests(unittest.TestCase):
    def test_version_node_contains_strings(self):
        blob = pe_resources.build_version_info(
            company_name="Sortify",
            product_name="Sortify",
            file_description="Order, by design",
            file_version=(1, 2, 3, 4),
            original_filename="Sortify.exe",
            legal_copyright="Copyright (c) 2026 Sortify",
        )
        length, value_length, value_type = struct.unpack_from("<HHH", blob, 0)
        self.assertEqual(length, len(blob))
        self.assertEqual(value_type, 0)
        self.assertEqual(value_length, 52)
        text = blob.decode("utf-16-le", errors="ignore")
        for expected in ("VS_VERSION_INFO", "FileDescription", "Order, by design", "1.2.3.4"):
            self.assertIn(expected, text)

    def test_manifest_declares_invoker_and_dpi(self):
        manifest = pe_resources.build_manifest()
        self.assertIn('level="asInvoker"', manifest)
        self.assertIn("PerMonitorV2", manifest)
        self.assertIn("longPathAware", manifest)
        self.assertIn('processorArchitecture="amd64"', manifest)


class WindowsScriptTests(unittest.TestCase):
    def test_batch_files_use_crlf_and_ascii(self):
        """cmd.exe mis-parses parenthesised blocks in LF-only or non-ASCII batch files."""
        for name in ("build_windows.bat", "sign_windows.bat"):
            path = ROOT_DIR / "packaging" / name
            data = path.read_bytes()
            self.assertNotIn(
                b"\n",
                data.replace(b"\r\n", b""),
                f"{name} must use CRLF line endings",
            )
            self.assertTrue(all(byte < 128 for byte in data), f"{name} must be ASCII")

    def test_launcher_runs_startup_shim_not_main(self):
        """The native launcher must start boot.py, otherwise startup failures are silent."""
        source = (ROOT_DIR / "packaging" / "windows_launcher.c").read_text(encoding="utf-8")
        self.assertIn('#define SORTIFY_SCRIPT L"boot.py"', source)
        self.assertIn('argv[count++] = "boot.py";', source)
        self.assertNotIn('argv[count++] = "main.py";', source)
        self.assertTrue((ROOT_DIR / "packaging" / "runtime_boot.py").is_file())

    def test_installer_script_is_ascii(self):
        data = (ROOT_DIR / "packaging" / "installer.iss").read_bytes()
        self.assertTrue(all(byte < 128 for byte in data))
        self.assertIn(b"Source: \"..\\dist\\Sortify\\*\"", data)


class VersionConsistencyTests(unittest.TestCase):
    """Packaging files hardcode the release version; they must match app/config.py."""

    def test_packaging_versions_match_app_version(self):
        import re

        sys.path.insert(0, str(ROOT_DIR))
        from app.config import APP_VERSION

        checks = {
            "packaging/installer.iss": r'#define MyAppVersion "([^"]+)"',
            "packaging/build_windows.bat": r"Sortify v([0-9.]+)",
            "packaging/build_release.py": r"Sortify-Setup-([0-9.]+)\.exe",
            "packaging/windows_version_info.txt": r"FileVersion\D+([0-9., ]+)",
        }
        for rel, pattern in checks.items():
            text = (ROOT_DIR / rel).read_text(encoding="utf-8", errors="replace")
            found = re.findall(pattern, text)
            self.assertTrue(found, f"no version found in {rel}")
            for value in found:
                normalized = value.replace(", ", ".").replace(",", ".").strip()
                self.assertTrue(
                    normalized.startswith(APP_VERSION),
                    f"{rel} has version {normalized}, expected {APP_VERSION}",
                )


class PortableInputTests(unittest.TestCase):
    def test_runtime_requirements_exclude_build_tools(self):
        requirements = prepare_portable_inputs._runtime_requirements()
        lowered = [item.lower() for item in requirements]
        self.assertFalse(any(item.startswith("pyinstaller") for item in lowered))
        self.assertTrue(any(item.startswith("pypdf") for item in lowered))

    def test_pyside6_metapackage_is_replaced_by_essentials(self):
        requirements = prepare_portable_inputs._runtime_requirements()
        lowered = [item.lower() for item in requirements]
        self.assertFalse(any(item.startswith("pyside6>") for item in lowered))
        self.assertTrue(any(item.startswith("pyside6-essentials") for item in lowered))

    def test_windows_only_dependency_is_requested(self):
        self.assertIn("pywin32-ctypes>=0.2.0", prepare_portable_inputs.WINDOWS_ONLY)


if __name__ == "__main__":
    unittest.main()
