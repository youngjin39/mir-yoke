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
five x86_64 Windows binaries placed (executor-query.exe included, SHA-256 equal to the
lock), Claude a9c23877 and Codex 01a19635 attested (five mir-mcp calls ok), finalized,
ready at 8b9573c; consumer commit pushed by the maintainer host.

Release record v0.13.61 (Main, 2026-11-01): E1c native admission of same-home queries when a
repository-local executor override exists (c1e960e) and E1d JSON surrogate escapes accepted
like Python in validation copies (71ab8b1; list-jobs no longer declines to Python on lone
surrogates); version fb63a7c, native prerelease native-71ab8b1c48f1 (30 assets), bind
5a6f53e (supersedes c43d977). CI validate on 5a6f53e all jobs green, including Windows,
before the tag. Fresh-clone readiness at 5a6f53e exit 0 (5085 passed, 219 skipped).
Maintainer host: provider update from the 0.13.60 record lock, five aarch64 binaries placed
(SHA-256 equal to the lock), Codex hook trust 4/4, Claude 92678a46 and Codex 01a197cf
attested (five mir-mcp calls ok), finalized, ready at 5a6f53e. Owner PC:
five x86_64 Windows binaries placed (SHA-256 equal to the lock), Claude a9cfb2e4 and Codex
01a197d4 attested (five mir-mcp calls ok; a first probe pointed at the removed 0.13.60 clone
and returned E_IO, so it was not used), finalized, ready at 5a6f53e; consumer commit pushed
by the maintainer host; consumer memory database unchanged.

Release record v0.13.62 (Main, 2026-11-03): native executor commands. Library slices
E2-E11 (admission, registry, transport, direct execute, worktrees, merge gate, dispatch
attempts, review, finalize, resume, sweep), E12a entrypoint routing of execute and cancel
with an ownership receipt (an older pinned binary falls back to Python), E12b native
dispatch, resume and sweep commands, E12c agent routes, E12w Windows environment lookups;
mir-code bluebricks Language Choice updated. Version 7dd4a10 on release/v0.13.62, native
prerelease native-7dd4a10f2910 (30 assets), bind df48fd5. CI validate on df48fd5 green on
every job, including Windows, after reruns of a GitHub macOS-capacity cancellation and one
timing-bound ontology test, before the tag. Fresh-clone readiness at df48fd5 exit 0 (5366
passed, 219 skipped). Maintainer host: provider update from the 0.13.61 record lock, five
aarch64 binaries placed (SHA-256 equal to the lock), Codex hook trust 4/4, Claude 7843c4ea
and Codex 01a19d8d attested (five mir-mcp calls ok), finalized, ready at df48fd5. Owner PC:
not attested; superseded by v0.13.63 (a consumer whose hooks import virtual-environment
packages fails natively on 0.13.62).

Release record v0.13.63 (Main, 2026-11-03): the native bridge runs consumer hooks in the
caller's interpreter (E12v): interpreter() keeps the unresolved path, and the entrypoint
passes sys.executable as MIR_EXECUTOR_PYTHON unless set. Fix ae878b3 (CI validate green),
version ba79888 on release/v0.13.63, native prerelease native-ba79888394dc (30 assets, after
a rerun of a GitHub macOS-capacity cancellation), bind 3c8fafa. CI validate on 3c8fafa green
on every job, including Windows, after one rerun of the timing-bound ontology test, before
the tag; main push CI green. Fresh-clone readiness at 3c8fafa exit 0 (5372 passed, 219
skipped). Real-consumer gate on Mir Harness (venv and local.py): sweep, list-jobs, status
and result native with no decline and byte-equal to forced Python; cancel declines to
Python by design; a base-interpreter override reproduces the 0.13.62 failure. Maintainer
host: provider update from the 0.13.62 record lock, five aarch64 binaries placed (SHA-256
equal to the lock), Codex hook trust 4/4, Claude d9376e73 and Codex 01a19e2d attested
(five mir-mcp calls ok), finalized, ready at 3c8fafa. Owner PC: pending.
