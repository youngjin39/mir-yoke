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
calls ok, four lifecycle hooks), finalized, ready at 2487c19. Owner PC (2026-11-01): 0.13.58 applied over the
unattested 0.13.56 (three x86_64 Windows binaries placed), Claude 121ec18b and Codex
01a19565 attested (five mir-mcp calls ok; the Codex PowerShell lifecycle hooks ran),
finalized, ready at f204a54; consumer commit pushed by the maintainer host.

Language guidance (2026-11-01, d990257, bind 11063ff): `mir-code` bluebricks starts new
product and tool code in Rust with fixtures first; Python stays for ML/data, analysis,
notebooks and one-off scripts or by repository policy; rust ports a stable component and
retires the old implementation once the Rust path is stable. Full suite after the bind:
4322 passed, 636 skipped.

Release record v0.13.59 (Main, 2026-11-01): B2 hook-scoped `.claude/settings.json`
evidence (709dc53; helper, adoption CLI and evaluator accept the canonical hook digest or
a legacy whole-file digest) and S7 native `runtime-verify` behind `cli.runtime_verifier`
(9c3a9fa; wrapper median 369 -> 304 ms on a realistic closure under load); version
4f5d7cc, native prerelease native-4f5d7cce8e1f (25 assets), bind d9aaa73, Windows test fix
4760c2f (the empty-USERPROFILE reference verdict differs on Windows). Fresh-clone readiness
at d9aaa73 exit 0 (4889 passed, 219 skipped); CI validate on 4760c2f all nine jobs green,
including Windows, before the tag. Maintainer host: provider update from the 0.13.58 record
lock, four aarch64 binaries placed (SHA-256 equal to the lock), Codex hook trust 4/4,
Claude 7375f3b1 and Codex 01a195b2 attested (five mir-mcp calls ok), finalized, ready at
4760c2f. Owner PC: four x86_64 Windows binaries placed (runtime-verify.exe included),
Claude 06a768d6 and Codex 01a195b6 attested (five mir-mcp calls ok; Codex lifecycle hooks
ran), finalized, ready at 73f1b1b; consumer commit pushed by the maintainer host.

Release record v0.13.60 (Main, 2026-11-01): E1 native `executor-query` front end
(a029d0b; same-home `status`, `result` and `list-jobs` from a read-only, fully understood
jobs schema with exact bundled rusqlite 0.40.2; a stdlib-only entrypoint shared by both
Python routes tries the host-locally pinned binary before importing the executor; whole
CLI median 74.1 -> 30.4 ms, binary 3.7 ms, 270/270 identical bytes); version fc083b6,
native prerelease native-fc083b61e55d (30 assets), bind 529b330. CI validate on a029d0b and
529b330 all jobs green, including Windows (executor parity +76 on macOS, Ubuntu and
Windows), before the tag. Fresh-clone readiness at 529b330 exit 0 (5006 passed, 219
skipped). Maintainer host: provider update from the 0.13.59 record lock, five aarch64
binaries placed (SHA-256 equal to the lock), Codex hook trust 4/4, Claude e7190a7a and
Codex 01a19631 attested (five mir-mcp calls ok), finalized, ready at 529b330. Owner PC:
pending.
