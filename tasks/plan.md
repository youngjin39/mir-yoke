# Plan

## Active task: native handoff cross-platform CI (2026-10-31)

Intent authority: current owner request; this cursor owns the bounded design.
Add macOS, Ubuntu and Windows Cargo/parity CI; preserve the Python reference,
hooks.json, versions and generated Codex files. No commit or delivery.
Prior cursor: [preserved evidence](change_log.md#cursor-before-cross-platform-native-ci-2026-10-31).

Design: honor Cargo environment, opt into offline builds, resolve target/executable
paths, use the mechanical-test interpreter for both subprocesses, preserve Windows
CRLF output bytes, and pin CI Python 3.14 to the Unicode 16.0 tables.
The shipped hook still calls python3; document the Windows test/default distinction.

Request matrix/scenarios:
1. Configured Cargo home/target and explicit offline flag reach the build unchanged;
   default builds may fetch dependencies; cargo absence skips the module.
2. Forwarded events use the selected reference interpreter and preserve all bytes/status.
3. Denials and warnings match native platform line endings without normalization;
   UTF-8 subprocess mode protects Unicode fixtures from Windows code pages.
4. Each OS runs four Cargo gates and byte parity with Python 3.14.
5. Local requested pytest/Ruff/YAML checks pass; adopter payload is the final edit.
Evidence: regression checks fail first, then local gates; Linux/Windows execution
remains open until CI runs. No caller switch or cross-platform runtime claim.

Current evidence (2026-10-31): scenarios 1-3 pass locally, including 123 parity
cases with Python 3.14 / Unicode 16.0, and 123 skips with Cargo unavailable.
Cargo fmt, clippy, 9 unit tests and release build pass offline/locked (fmt takes
neither flag). YAML safe_load and Ruff pass. Scenario 4 has macOS evidence only;
Ubuntu and Windows remain open until CI executes. Initial requested Python set:
772 passed, 2 skipped, only stale adopter inventory failed. Regenerate the payload
as the final edit, then rerun the requested set; final execution results belong to
the delivery report to avoid editing this cursor after inventory generation.
No generated Codex files changed; no commit, push, tag, release or version bump.
