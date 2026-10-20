# Plan

## Active task: one-command ontology handoff pins (2026-10-21)

Intent authority: owner Discord 1562120317504061453, 2026-10-20,
approval of both stages 1 and 2 (parent-supplied by Mir Harness Main), and the current bounded
implementation request. This cursor owns the design. Qualified target:
mir-yoke:ontology-mapping-handoff and mir-yoke:runtime-continuity-message.
Root: this checkout; base HEAD c70c47029607689eab344ca2998b6f72ec710844.

Request matrix: (1) opt-in text/JSON pins and graceful unknowns;
(2) exact SessionStart message under 800 bytes and both shim forwarding paths;
(3) one-sentence Handoff guidance and budget;
(4) fail-first regressions then focused/full checks;
(5) Unreleased entry, verbatim cursor archive and current evidence.
Status: 5/5 cells checked with the owner-accepted Main-owned lock exception.

Design: preserve mapping output byte-for-byte without --handoff; reuse loaded
map/contract pins; collect root/HEAD/dirty and per-file revision/current-byte
SHA-256/HEAD comparison using read-only Git. Missing, outside and unavailable
pins become explicit unknowns without changing mapping exit status. Text appends
one pasteable JSON pin block; --json adds only a handoff object.
Run tests first, implement, check focused behavior, then one full suite, Ruff
and diff checks. Refresh adopter payload only if surface checks require it.

Semantic evidence: .mir/ontology-map.json#/contract declares
mir.common-semantics@1.1.0; /concepts/Task identifies this cursor. Map SHA256:
516c5b160c0fa49de51e4a0dc6f14c6e6a955d1baf72cc75dc2c93de7ea23e79.
Contract: plugins/mir-core/skills/ontology/references/common-contract.json,
SHA256 b2f1ecd01aaa88d41caac2bc2481e7f4c5a429cff3983aaa85ddfb0fc2f1b93f.

Authority: requested checkout edits and local checks only; no version bump,
release preparation, commit/tag/push, network, capability commands or lock writes,
.codex/**, other repositories, Memory Keeper or handoff-file writes.
Preserve tasks/handoffs/session-handoff-LATEST.md. Main owns delivery and binding.
Lifecycle: owner-approved; temporal: current working tree; epistemic: local state
verified-in-repo, behavior-uptake evidence parent-supplied; verification: checked with the accepted Main-owned lock exception.
Parent report: Mir Harness
`tasks/reports/ontology-engineering/settlement-2026-10-17/after/report-p3-c1-2026-10-20b.md`,
supplied in the request; no independent retrieval. Cause of non-uptake and future behavior
remain unknown. Observation date: 2026-10-21.
Self-check: source pins and executed evidence are recorded below; behavior effect,
Main lock binding and later release/delivery pins remain unknown.
Previous cursor: tasks/change_log.md#superseded-cursor-before-handoff-pin-block-2026-10-21.

Current evidence: fail-first ontology/package modules: 13 failed, 314 passed
(20.12s); after implementation: 327 passed (21.15s). Expanded focused run with
both runner modules and additional last-touch/no-path/error-exit checks:
372 passed (24.81s). Both shims forward --handoff without edits. SessionStart
stdout is 784 bytes including newline; its exact equality test passes.
Ruff and diff checks pass. Local mapping reports 0 errors, 0 warnings.
Full suite (one execution): 2091 passed, 70 failed (239.98s): 68 stale hook
acknowledgement failures, one public-language failure from the approval quotation,
and the expected repository lock mismatch. Updated the hook acknowledgement for
the changed reviewed handler and recorded approval in English; re-ran every
failing module: 168 passed, one expected lock mismatch (15.77s). No second full
suite was run. The unchanged Main-owned lock is the sole known remaining failure.
Final adopter inventory regeneration follows these records; read-only public
surface/payload, language, Ruff and diff checks must pass before delivery.
Evidence and full source pins:
tasks/change_log.md#one-command-ontology-handoff-pins-2026-10-21.
