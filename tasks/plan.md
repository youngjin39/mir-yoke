# Plan

## Active task: B1b native adoption caller and delivery

Intent authority: owner-supplied B1b brief (2026-11-01), building on the B1
brief and report. This is the single current cursor.
Outcome: switch only adoption-ready evaluation to a receipt-pinned native
binary; install verified host artifacts atomically during explicit adoption;
wire all release targets; preserve shell fallback and rollback.
Design input: receipt native_evaluator records relative path and SHA-256;
verify hash before exact version/protocol. Windows and unavailable artifacts
remain shell. Explicit local builds remain receipt-pinned. No consumer writes,
commits, tags, pushes or workflow dispatch. Public sources stay generic English.
Scenarios: every pin/file/version/protocol fallback, real helper state and
enforcement byte parity, installer verification and atomic placement, release
matrix membership. Preserve all B1 evaluator parity cases.
Acceptance: fail-first and source mutations per family, cargo gates, touched
pytest then full pytest, Ruff, generated parity, 30 interleaved measurements
per state/enforce and 1/8/13/32-file workload including hash and pin reads.
Regenerate adopter payload as the final repository edit.

Prior B1 outcome and decisions are preserved in tasks/change_log.md and the
owner-requested external B1 report. G2/G4 release execution and consumer
attestation remain outside this repository-only task.

Implementation complete: receipt-pinned caller and atomic optional installation,
five-target release wiring, operator docs and dated ADR-77 amendment. Independent
review found and verified corrections for signal-diagnostic stderr leakage and
the historical receipt-only write boundary. No outstanding review findings.
Actual helper mutations (seven), installer mutations (five) and release digest
mutation were detected and restored. Cargo gates passed with 26 tests.
Production benchmark: 480 byte-identical samples, 30 interleaved pairs per
state/enforce and file-count cell; median gains 1.39x to 4.62x including pin/hash.
Main acceptance runs the complete touched selection, then final payload
regeneration and the whole suite. Exact final counts and any open cells are
recorded in the owner-requested external B1b report; no duplicate handoff exists.

Release record (Main, 2026-11-01): source 529828a (caller simplified by the Main:
the receipt hash fixes the version, so no version probe or stderr framing), native
prerelease native-529828a95da6 (20 assets, target 529828a), bind 999823f, hermetic
adoption-test fix 2487c19 after CI public Mir CLI regression failed on the bound
lock (the report test saw the installed evaluator). Fresh-clone readiness exit 0
(4763 passed, 195 skipped); CI validate on 2487c19 all nine jobs green, including
Windows, before the tag `v0.13.58`. Maintainer host: provider update applied from
the 0.13.57 record lock, three aarch64 binaries placed (SHA-256 equal to the lock),
Codex hook trust 4/4, Claude 3dcbab47 and Codex 01a194dd attested (five mir-mcp
calls ok, four lifecycle hooks), finalized, ready at 2487c19. Owner PC: recorded by
Harness (unreachable since 2026-11-01 about 03:00 KST).
