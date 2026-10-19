# Verification report: Sortify 1.0.0

Repository: <https://github.com/hmmlavi/sortify-desktop>.

The release workflow is triggered by the `v1.0.0` tag. Its checks cover linting, unit tests, diagnostics, GUI smoke tests, portable Windows execution, standalone packaging, installer installation and execution, and release asset verification. The release job publishes the installer, portable ZIP, standalone ZIP, and SHA-256 checksums from the tagged build.

A successful pre-release build is recorded at <https://github.com/hmmlavi/sortify-desktop/actions/runs/39263031908>. That run passed its Linux and Windows lint/test jobs, standalone/installer job, portable build job, and portable Windows smoke test. The tagged release run is the authoritative verification for the published assets and will be linked here after publication.

## Not verified by CI

- Interactive use on a physical Windows desktop.
- Authenticode signing and SmartScreen behavior (the builds are unsigned).
- OCR for image-only PDFs; password-protected files are reported as unreadable.
