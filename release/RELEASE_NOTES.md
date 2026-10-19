# Sortify 1.0.0

Windows x64 desktop release for [hmmlavi/sortify-desktop](https://github.com/hmmlavi/sortify-desktop). GitHub Actions builds the release from tag `v1.0.0` and verifies the installer, portable ZIP, standalone ZIP, checksums, archive integrity, and executable architecture before publishing.

## Downloads

| File | Purpose |
| --- | --- |
| `Sortify-Setup-1.0.0.exe` | Per-user installer. No administrator rights required; the uninstaller keeps user data by default. |
| `Sortify-1.0.0-windows-x64-portable.zip` | Portable build. Unzip anywhere and run `Sortify.exe`. |
| `Sortify-1.0.0-windows-x64-standalone.zip` | PyInstaller folder build. Unzip and run `Sortify.exe` inside the `Sortify` folder. |
| `SHA256SUMS.txt` | SHA-256 checksums for the three application downloads. |

## Highlights

- Review and approve every proposed filename, with conflict checks, a preview plan, and undo for applied batches.
- Read bounded content from supported documents, spreadsheets, presentations, text files, and image metadata.
- Choose the offline local heuristic engine or explicitly enable an OpenAI-compatible endpoint.
- Store settings and rename history locally; API keys stay in the operating system keyring.
- Use the Charcoal dark theme or Smoke light theme.

## Install

1. Download `Sortify-Setup-1.0.0.exe` for a per-user installation, or download and extract the portable ZIP and launch `Sortify.exe`.
2. Choose a folder and scan it, generate names, review the proposals, and apply changes when ready.
3. Use **History → Undo last session** to reverse a batch when the original names are still available.

Windows 10 or 11, 64-bit, is required. Builds are unsigned, so Windows SmartScreen may warn on first launch. Compare the downloaded file against `SHA256SUMS.txt` before running it. For the portable build, allow about 120 MB of disk space.

See the [project README](https://github.com/hmmlavi/sortify-desktop#readme) for supported file types, privacy details, and troubleshooting.
