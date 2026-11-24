# Plan

## Active task: v0.14.2 release preparation

Intent authority: owner Discord 1574707453637951510 (2026-11-24),
release the tested candidate now, Mac first; Windows E17 remains open for
its next PC window. The source/version commit B brief authorizes local edits
only. Baseline: `release/v0.14.2` at `061ecb07`.

Design: follow the v0.14.1 source checklist, align release and server versions,
document native MCP and cohort changes, insert the approved automation wait
cap, and refresh managed plugin, marketplace and command digests. Preserve
native artifact pins and source.commit for bind C. Main owns generated Codex
files, final adopter payload generation, review and commit, native publication,
main update, push and tag. No consumer writes are authorized.

Acceptance: offline frozen Python 3.12 dev/vector environment, lock check,
SQLite vector preflight, the nine requested pytest files, mir-mcp locked
Cargo tests, Ruff, fixture pin audit and ASCII diff check. Behaviour scenarios
are not applicable: this slice changes release metadata and skill guidance,
not runtime control flow. Windows and Linux attestation remain outside scope;
Windows mir_entry_e17 needs a Windows-host capture. Adopter classification is
expected to remain stale until Main regenerates its payload.

Prior cursors and release records: [change log](change_log.md).
