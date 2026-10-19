# Verification report: Sortify 1.0.0

Source commit: `d4441d1`. Tag: `v1.0.0`. Release: <https://github.com/hmmlavi/sortify/releases/tag/v1.0.0>.

## Checks run in GitHub Actions (run 39219875094)

| Job | Runner | Result |
| --- | --- | --- |
| Ruff, unit tests (unittest and pytest), `--diagnose`, GUI smoke test | Ubuntu and Windows, Python 3.11 and 3.12 | Passed |
| Portable Windows build | Ubuntu | Passed (ZIP assembled, CRC-tested) |
| Standalone folder, installer (Inno Setup), installer silent install, installed `--diagnose`, silent uninstall | Windows | Passed |
| Portable ZIP extracted and run: `--diagnose`, GUI stays up for 10 seconds | Windows | Passed |
| Release asset verification (ZIP CRC, PE header and machine type) and release creation | Ubuntu | Passed |

The checksums in `SHA256SUMS.txt` are the SHA-256 values GitHub reports for the release assets. Each download URL returns a redirect from github.com to GitHub's asset storage.

## Not verified

- Interactive use on a physical Windows desktop.
- Authenticode signing and SmartScreen behavior (no certificate).
- The local Linux GUI smoke harness exits with code 134 at interpreter shutdown in this sandbox, after all 20 checks pass. The same harness exits 0 on the Windows runner.
