# Sortify 1.0.0

Windows x64 release. Tag `v1.0.0`, built by GitHub Actions from commit `d4441d1`.

## Downloads

| File | Purpose |
| --- | --- |
| `Sortify-Setup-1.0.0.exe` | Installer. Per-user, no administrator rights, uninstaller keeps user data by default. |
| `Sortify-1.0.0-windows-x64-portable.zip` | Portable build. Unzip and run `Sortify.exe`. |
| `Sortify-1.0.0-windows-x64-standalone.zip` | PyInstaller folder build. Unzip and run `Sortify.exe` inside it. |
| `SHA256SUMS.txt` | SHA-256 checksums for the three files above. |

Builds are unsigned. Windows SmartScreen may warn on first run; verify the checksum first.

## Changes in this release

- Palette: the green glass theme was replaced by smoky charcoal and silver. The dark theme is named **Charcoal** and the light theme **Smoke**.
- Cleanup: removed an unused navigation parameter and unreferenced logo and icon files; merged duplicated manual-name logic.
- Copyright strings now match `LICENSE` ("Sortify contributors").
- README rewritten with current screenshots and release links.
- CI: packages the standalone folder, installs the installer silently and runs the installed app, runs the portable ZIP on Windows, and publishes the release from a `v*` tag.

## Known limitations

- Unsigned builds.
- The standalone build is a folder (PyInstaller one-folder), so `Sortify.exe` must stay next to its `_internal` folder.
- No OCR. Password-protected files are reported, not read.
