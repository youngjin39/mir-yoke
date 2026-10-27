# Plan

## Active task: release 0.13.41 (Windows consumer sync fixes) (2026-10-28)

Intent authority: as for 0.13.40 (Discord 1564632417304838205, 1564744151088627924; release-chain
approvals 1564297975755448493, 1564320227062186065), relayed by Mir Harness Main
(parent-supplied). Design authority: this cursor and the 0.13.40 amendment to
[ADR-91](../docs/decisions/adr-91-stdio-mcp-package-admission.md). Baseline: 5cb0ec0 (v0.13.40),
installed and attested on the maintainer host.

Prior cursor preserved verbatim:
[cursor before release 0.13.41](change_log.md#cursor-before-release-01341-2026-10-28).

Why: the 0.13.40 exit check (a consumer sync on the owner's Windows PC, with the capability home,
Claude config and Codex home isolated under the PC's temp folder) failed twice natively:
removing the exported `.git` raised WinError 5 (Git for Windows makes object files read-only), and
Codex for Windows records the local marketplace source as `\\?\C:\...`, which the manager read
as a different path. With both fixed in place on the PC, sync apply registered the four selected
plugins in both CLIs, the binding ledger passed the DACL check and a second update preview was
ready to apply. The `mir-mcp` Windows lane, `windows` receipts and the Python 3.11 floor move to
0.13.42.

Rules:
1. Tree removal clears the read-only attribute before retrying a failed delete.
2. Codex marketplace sources drop the Windows extended-length prefix before they are compared.

Request matrix: (1) fail-first tests and fixes (done: `tests/test_capability_windows_paths.py`);
(2) docs and version surfaces; (3) Main full suite, fresh-clone readiness; (4) release, host
re-attestation; (5) the Windows PC canary rerun on the released code.
