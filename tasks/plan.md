# Plan

## Active task: New-machine global setup guide (2026-10-19)

Intent authority: current owner brief relayed by Mir Harness Main (parent-supplied).
This is the single active cursor and bounded design authority. Guide a user or AI
through the user-scope layer on macOS, Linux, WSL and native Windows, and route
new-project entrypoints through that check. Preserve ADR-79 platform lanes,
ADR-81/83 optional host adoption, ADR-85 operator policy and ADR-89/90 delivery.
The prior cursor remains recoverable at the Git pin recorded in
[tasks/change_log.md](change_log.md#new-machine-global-setup-guide-2026-10-19).

Design: one concise operations guide, five routing edits, docs-only evidence.
Request matrix: (1) OS/prerequisites; (2) dual-runtime user-scope plugins and
optional agents; (3) merged global instructions; (4) settings ownership;
(5) optional MCP parity and MK supply; (6) fresh-session verification;
(7) AI preflight and five routes; (8) command/source validation and platform
limits; (9) bounded checks, sanitization and final evidence. Status: 9/9 documentation cells checked.
Fail-first: the guide-existence assertion failed before writing. No behavior
change or new regression test is needed. Evaluate with existing Starter/Kit,
public-surface, classification, ontology and derivative checks plus source review.

Semantic pins: .mir/ontology-map.json#/contract = mir.common-semantics@1.1.0;
/concepts/Task identifies this cursor; /domain/invariants distinguishes install
from discovery and keeps coupled hooks/MCP local. Map SHA256:
516c5b160c0fa49de51e4a0dc6f14c6e6a955d1baf72cc75dc2c93de7ea23e79.
Only authorized docs and the required generated adopter inventory may change;
Main owns generated Codex files. No commit,
home/consumer writes, secrets, plugin/src/setup behavior or version/lock changes.

Acceptance: focused pytest 36 passed; Ruff, generated Codex parity, context paths
(7 files / 67 refs), 5 routes / 14 local guide links, public-surface sanitization,
map 0 errors / 0 warnings, strict impact and diff checks passed. Stale adopter
hashes were repaired by the documented generator; final records precede its final
run and read-only verification. Full evidence and explicit runtime/OS unknowns:
[tasks/change_log.md](change_log.md#new-machine-global-setup-guide-2026-10-19).
No ADR conflict; installation is optional and native Windows receives no ready receipt.
