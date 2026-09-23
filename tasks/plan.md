# Plan

Owner Tasks B and D, 2026-09-24, in this repository only. Authority: owner Discord
1552352486801547415 and 1552354384296411267, relayed by Mir Harness; this cursor
records the current intent. Prior cursor and retired rules are preserved verbatim
in `tasks/change_log.md`, "Owner Tasks B and D (2026-09-24)".

- [x] B: inventory and consolidate the local path guard; preserve the 20-case baseline.
- [x] D: verify 13 archived Mir Harness successor mappings and close the pending item.
- [x] Verify fail-first regressions, hook/governance checks and generated parity.
- [x] Record evidence, generated installation differences and re-attestation needs.

Local implementation and verification are complete. Mir Harness owns clone
remeasurement and re-attestation of the changed PreToolUse bootstrap evidence.
No Codex generated-file installation is needed. Full evidence is in the log above.

## Owner choice B follow-up (2026-09-24)

This cursor records the owner-authorized cleanup of the orphan code-path helper.
The completed B/D work above remains historical evidence; the ready bootstrap
receipt and all declared bootstrap evidence must remain unchanged in this pass.

- [x] Reproduce R8, remove the unused helper and helper-only test fixture.
- [x] Regenerate payload and temporary Codex output; record pending installation.
- [x] Run full tests, public-surface and hook/governance checks, and baseline probes.
- [x] Record evidence and remaining external work in tasks/change_log.md.

Follow-up implementation and permitted verification are complete; full-suite status
is 1298 passed / 5 failed, with the snapshot failure passing its frozen rerun.
Two network failures and two payload checks remain limited. The orchestrator must
apply the generated deletion of `.codex/hooks/lib/code-path-config.py` and recheck
working-tree payload/parity. No bootstrap evidence changed in this follow-up.
See `tasks/change_log.md`, "Owner choice B orphan-helper follow-up (2026-09-24)".
