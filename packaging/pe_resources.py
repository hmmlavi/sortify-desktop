"""Write Windows PE resources (icon, version info, manifest) without a resource compiler.

The project normally builds its Windows executable with PyInstaller, which embeds
resources through its own bootloader.  The cross-platform portable builder in
``build_portable_windows.py`` links a small native launcher with ``zig cc`` on a
non-Windows host, where ``rc.exe``/``windres`` are unavailable.  This module fills
that gap: it serialises the resource directory (RT_ICON, RT_GROUP_ICON,
RT_VERSION, RT_MANIFEST) and appends it to a PE32+ image as a new ``.rsrc``
section, updating the COFF header and optional header data directory.

The implementation is deliberately strict: every structural assumption is checked
and a descriptive error is raised instead of producing a silently corrupt binary.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

RT_ICON = 3
RT_GROUP_ICON = 14
RT_VERSION = 16
RT_MANIFEST = 24

LANG_EN_US = 0x0409
IMAGE_SCN_CNT_INITIALIZED_DATA = 0x00000040
IMAGE_SCN_MEM_READ = 0x40000000


class ResourceError(RuntimeError):
    """Raised when resources cannot be parsed or injected safely."""


# --------------------------------------------------------------------------- #
# .ico parsing
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class IconImage:
    width: int
    height: int
    colors: int
    planes: int
    bit_count: int
    payload: bytes


def read_ico(path: Path) -> list[IconImage]:
    """Return the images contained in a Windows ``.ico`` file."""
    raw = Path(path).read_bytes()
    if len(raw) < 6:
        raise ResourceError(f"{path} is too small to be an icon file")
    reserved, kind, count = struct.unpack_from("<HHH", raw, 0)
    if reserved != 0 or kind != 1 or count == 0:
        raise ResourceError(f"{path} is not a valid Windows icon file")
    if len(raw) < 6 + count * 16:
        raise ResourceError(f"{path} has a truncated icon directory")
    images: list[IconImage] = []
    for index in range(count):
        width, height, colors, _reserved, planes, bits, size, offset = struct.unpack_from(
            "<BBBBHHII", raw, 6 + index * 16
        )
        if offset + size > len(raw):
            raise ResourceError(f"{path} image {index} extends past end of file")
        images.append(
            IconImage(width, height, colors, planes, bits, raw[offset : offset + size])
        )
    return images


def icon_entries(ico_path: Path, first_id: int = 1, group_id: int = 1) -> list[tuple[int, int, bytes]]:
    """Build RT_ICON entries plus the matching RT_GROUP_ICON directory."""
    images = read_ico(ico_path)
    entries: list[tuple[int, int, bytes]] = []
    group = bytearray(struct.pack("<HHH", 0, 1, len(images)))
    for offset, image in enumerate(images):
        resource_id = first_id + offset
        entries.append((RT_ICON, resource_id, image.payload))
        group += struct.pack(
            "<BBBBHHIH",
            image.width if image.width < 256 else 0,
            image.height if image.height < 256 else 0,
            image.colors,
            0,
            image.planes,
            image.bit_count,
            len(image.payload),
            resource_id,
        )
    entries.append((RT_GROUP_ICON, group_id, bytes(group)))
    return entries


# --------------------------------------------------------------------------- #
# RT_VERSION
# --------------------------------------------------------------------------- #
def _version_node(key: str, value: bytes, children: bytes, value_length: int, value_type: int) -> bytes:
    buffer = bytearray(struct.pack("<HHH", 0, value_length, value_type))
    buffer += key.encode("utf-16-le") + b"\x00\x00"
    while len(buffer) % 4:
        buffer.append(0)
    buffer += value
    while len(buffer) % 4:
        buffer.append(0)
    buffer += children
    while len(buffer) % 4:
        buffer.append(0)
    struct.pack_into("<H", buffer, 0, len(buffer))
    return bytes(buffer)


def _string_node(key: str, value: str) -> bytes:
    payload = value.encode("utf-16-le") + b"\x00\x00"
    return _version_node(key, payload, b"", len(payload) // 2, 1)


def build_version_info(
    *,
    company_name: str,
    product_name: str,
    file_description: str,
    file_version: tuple[int, int, int, int],
    original_filename: str,
    legal_copyright: str,
    internal_name: str = "Sortify",
) -> bytes:
    """Serialise a VS_VERSIONINFO structure with StringFileInfo and VarFileInfo."""
    major, minor, patch, build = file_version
    version_ms = (major << 16) | minor
    version_ls = (patch << 16) | build
    # VS_FIXEDFILEINFO is exactly 13 DWORDs (52 bytes).
    fixed = struct.pack(
        "<IIIIIIIIIIIII",
        0xFEEF04BD,  # dwSignature
        0x00010000,  # dwStrucVersion
        version_ms,  # dwFileVersionMS
        version_ls,  # dwFileVersionLS
        version_ms,  # dwProductVersionMS
        version_ls,  # dwProductVersionLS
        0x0000003F,  # dwFileFlagsMask
        0,  # dwFileFlags
        0x00040004,  # dwFileOS (VOS_NT_WINDOWS32)
        1,  # dwFileType (VFT_APP)
        0,  # dwFileSubtype
        0,  # dwFileDateMS
        0,  # dwFileDateLS
    )
    strings = {
        "CompanyName": company_name,
        "FileDescription": file_description,
        "FileVersion": f"{major}.{minor}.{patch}.{build}",
        "InternalName": internal_name,
        "LegalCopyright": legal_copyright,
        "OriginalFilename": original_filename,
        "ProductName": product_name,
        "ProductVersion": f"{major}.{minor}.{patch}",
    }
    string_table = b"".join(_string_node(key, value) for key, value in strings.items())
    table = _version_node("040904B0", b"", string_table, 0, 1)
    string_file_info = _version_node("StringFileInfo", b"", table, 0, 1)
    translation = struct.pack("<HH", LANG_EN_US, 1200)
    var = _version_node("Translation", translation, b"", len(translation) // 2, 0)
    var_file_info = _version_node("VarFileInfo", b"", var, 0, 1)
    return _version_node(
        "VS_VERSION_INFO", fixed, string_file_info + var_file_info, len(fixed), 0
    )


def build_manifest(*, name: str = "Sortify", version: str = "1.0.0.0") -> str:
    """Application manifest: asInvoker, per-monitor DPI awareness, long path aware."""
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<assembly xmlns="urn:schemas-microsoft-com:asm.v1" manifestVersion="1.0">\n'
        f'  <assemblyIdentity type="win32" name="{name}" version="{version}" '
        'processorArchitecture="amd64"/>\n'
        '  <trustInfo xmlns="urn:schemas-microsoft-com:asm.v3">\n'
        "    <security><requestedPrivileges>"
        '<requestedExecutionLevel level="asInvoker" uiAccess="false"/>'
        "</requestedPrivileges></security>\n"
        "  </trustInfo>\n"
        '  <application xmlns="urn:schemas-microsoft-com:asm.v3">\n'
        "    <windowsSettings>\n"
        '      <dpiAwareness xmlns="http://schemas.microsoft.com/SMI/2016/WindowsSettings">'
        "PerMonitorV2</dpiAwareness>\n"
        '      <longPathAware xmlns="http://schemas.microsoft.com/SMI/2016/WindowsSettings">'
        "true</longPathAware>\n"
        "    </windowsSettings>\n"
        "  </application>\n"
        '  <compatibility xmlns="urn:schemas-microsoft-com:compatibility.v1">\n'
        "    <application>\n"
        '      <supportedOS Id="{8e0f7a12-bfb3-4fe8-b9a5-48fd50a15a9a}"/>\n'
        "    </application>\n"
        "  </compatibility>\n"
        "</assembly>\n"
    )


# --------------------------------------------------------------------------- #
# Resource directory image
# --------------------------------------------------------------------------- #
def _align(value: int, alignment: int) -> int:
    return (value + alignment - 1) // alignment * alignment


def build_resource_section(
    entries: list[tuple[int, int, bytes]], base_rva: int
) -> bytes:
    """Serialise entries into a rooted RT_* resource directory at ``base_rva``.

    The Windows resource tree has three directory levels before the payload:
    type -> name -> language -> data entry.  Every directory lists ID entries
    only (named resources are not used by this project).
    """
    if not entries:
        raise ResourceError("no resources to write")
    ordered: dict[int, dict[int, bytes]] = {}
    for type_id, name_id, payload in entries:
        if not 0 <= type_id <= 0xFFFF or not 0 <= name_id <= 0xFFFF:
            raise ResourceError("resource ids must fit in 16 bits")
        if name_id in ordered.setdefault(type_id, {}):
            raise ResourceError(f"duplicate resource id {type_id}/{name_id}")
        ordered[type_id][name_id] = payload

    type_ids = sorted(ordered)
    cursor = 16 + 8 * len(type_ids)

    type_dir_offsets: dict[int, int] = {}
    name_dir_offsets: dict[tuple[int, int], int] = {}
    data_entry_offsets: dict[tuple[int, int], int] = {}
    for type_id in type_ids:
        type_dir_offsets[type_id] = cursor
        cursor += 16 + 8 * len(ordered[type_id])
    for type_id in type_ids:
        for name_id in sorted(ordered[type_id]):
            name_dir_offsets[(type_id, name_id)] = cursor
            cursor += 16 + 8  # a single language entry
    for type_id in type_ids:
        for name_id in sorted(ordered[type_id]):
            data_entry_offsets[(type_id, name_id)] = cursor
            cursor += 16

    blob_offsets: dict[tuple[int, int], int] = {}
    cursor = _align(cursor, 4)
    for type_id in type_ids:
        for name_id in sorted(ordered[type_id]):
            blob_offsets[(type_id, name_id)] = cursor
            cursor += _align(len(ordered[type_id][name_id]), 4)

    blob = bytearray(cursor)

    struct.pack_into("<IIHHHH", blob, 0, 0, 0, 0, 0, 0, len(type_ids))
    for index, type_id in enumerate(type_ids):
        struct.pack_into(
            "<II", blob, 16 + 8 * index, type_id, 0x80000000 | type_dir_offsets[type_id]
        )

    for type_id in type_ids:
        names = sorted(ordered[type_id])
        offset = type_dir_offsets[type_id]
        struct.pack_into("<IIHHHH", blob, offset, 0, 0, 0, 0, 0, len(names))
        for index, name_id in enumerate(names):
            struct.pack_into(
                "<II",
                blob,
                offset + 16 + 8 * index,
                name_id,
                0x80000000 | name_dir_offsets[(type_id, name_id)],
            )

    for type_id in type_ids:
        for name_id in sorted(ordered[type_id]):
            offset = name_dir_offsets[(type_id, name_id)]
            struct.pack_into("<IIHHHH", blob, offset, 0, 0, 0, 0, 0, 1)
            struct.pack_into("<II", blob, offset + 16, LANG_EN_US, data_entry_offsets[(type_id, name_id)])

    for type_id in type_ids:
        for name_id in sorted(ordered[type_id]):
            payload = ordered[type_id][name_id]
            offset = data_entry_offsets[(type_id, name_id)]
            payload_offset = blob_offsets[(type_id, name_id)]
            struct.pack_into("<IIII", blob, offset, base_rva + payload_offset, len(payload), 0, 0)
            blob[payload_offset : payload_offset + len(payload)] = payload

    return bytes(blob)


# --------------------------------------------------------------------------- #
# PE injection
# --------------------------------------------------------------------------- #
def _pe_checksum(data: bytes, checksum_offset: int) -> int:
    """Standard PE image checksum."""
    total = 0
    padded = data + (b"\x00" if len(data) % 2 else b"")
    for index in range(0, len(padded), 2):
        if index == checksum_offset or index == checksum_offset + 2:
            word = 0
        else:
            word = padded[index] | (padded[index + 1] << 8)
        total += word
        total = (total & 0xFFFF) + (total >> 16)
    total = (total & 0xFFFF) + (total >> 16)
    return (total + len(data)) & 0xFFFFFFFF


def inject_resources(exe_path: Path, entries: list[tuple[int, int, bytes]]) -> dict[str, int]:
    """Append a ``.rsrc`` section carrying ``entries`` to a PE32+ executable."""
    path = Path(exe_path)
    data = bytearray(path.read_bytes())
    if data[:2] != b"MZ":
        raise ResourceError(f"{path} is not a PE image (missing MZ header)")
    e_lfanew = struct.unpack_from("<I", data, 0x3C)[0]
    if data[e_lfanew : e_lfanew + 4] != b"PE\0\0":
        raise ResourceError(f"{path} has an invalid PE signature")
    coff = e_lfanew + 4
    number_of_sections, = struct.unpack_from("<H", data, coff + 2)
    size_of_optional_header, = struct.unpack_from("<H", data, coff + 16)
    optional = coff + 20
    magic, = struct.unpack_from("<H", data, optional)
    if magic != 0x20B:
        raise ResourceError(f"{path} is not a PE32+ (64-bit) image")
    section_alignment, file_alignment = struct.unpack_from("<II", data, optional + 32)
    _size_of_image, size_of_headers = struct.unpack_from("<II", data, optional + 56)
    if file_alignment <= 0 or section_alignment <= 0:
        raise ResourceError(f"{path} has invalid section alignment")
    section_table = optional + size_of_optional_header
    new_section_header = section_table + number_of_sections * 40
    first_raw = min(
        struct.unpack_from("<I", data, section_table + index * 40 + 20)[0]
        for index in range(number_of_sections)
    )
    if new_section_header + 40 > first_raw:
        raise ResourceError(
            f"{path} has no room for another section header "
            f"(header end {new_section_header + 40}, first raw data at {first_raw})"
        )

    last_va = 0
    last_end = 0
    for index in range(number_of_sections):
        offset = section_table + index * 40
        virtual_size, virtual_address = struct.unpack_from("<II", data, offset + 8)
        raw_size, raw_pointer = struct.unpack_from("<II", data, offset + 16)
        last_va = max(last_va, virtual_address + max(virtual_size, raw_size))
        last_end = max(last_end, raw_pointer + raw_size)
    last_end = max(last_end, len(data))

    new_rva = _align(last_va, section_alignment)
    new_raw = _align(last_end, file_alignment)
    section = build_resource_section(entries, new_rva)
    raw_size = _align(len(section), file_alignment)

    header = bytearray(40)
    header[0:8] = b".rsrc\0\0\0"
    struct.pack_into("<IIII", header, 8, len(section), new_rva, raw_size, new_raw)
    struct.pack_into("<II", header, 32, 0, 0)
    struct.pack_into("<I", header, 36, IMAGE_SCN_CNT_INITIALIZED_DATA | IMAGE_SCN_MEM_READ)
    data[new_section_header : new_section_header + 40] = header

    struct.pack_into("<H", data, coff + 2, number_of_sections + 1)
    struct.pack_into("<I", data, optional + 56, _align(new_rva + len(section), section_alignment))
    struct.pack_into("<I", data, optional + 60, size_of_headers)
    initialized = struct.unpack_from("<I", data, optional + 8)[0]
    struct.pack_into("<I", data, optional + 8, initialized + raw_size)
    directory_offset = optional + 112 + 8 * 2
    struct.pack_into("<II", data, directory_offset, new_rva, len(section))

    if len(data) < new_raw:
        data += b"\x00" * (new_raw - len(data))
    data += section
    data += b"\x00" * (raw_size - len(section))

    checksum_offset = optional + 64
    struct.pack_into("<I", data, checksum_offset, 0)
    struct.pack_into("<I", data, checksum_offset, _pe_checksum(bytes(data), checksum_offset))

    path.write_bytes(bytes(data))
    return {
        "section_rva": new_rva,
        "section_raw_offset": new_raw,
        "section_size": len(section),
        "resource_entries": len(entries),
    }


