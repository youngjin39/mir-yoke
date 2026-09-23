# Plan

Owner-authorized twenty-one-item maintenance skill implementation, 2026-09-24.
Authority: owner Discord 1552387906927333458, relayed by Mir Harness; this repository only.
This cursor is the active intent authority. Predecessor cursor is preserved verbatim
in `tasks/change_log.md`, "Twenty-one-item maintenance skill implementation (2026-09-24)".

- [x] Trace v0.10.6 registration, current scope and owner intent; preserve prior text.
- [x] Prove missing repair, harness parity and Main-runtime probes with failing contracts.
- [x] Update the skill and current descriptions; preserve historical release facts.
- [x] Regenerate payload and temporary derivatives; run the full suite and documented checks.
- [x] Record counts, fail-first proof, installation needs and bootstrap boundaries.

Design: retain all twenty existing topics, strengthen items 6 and 7, and add item 21
with concrete instruction, event, startup, capability, MCP and trust probes tied to
runtime evidence. This edits guidance and its contracts, not runtime hooks. Existing
registration remains valid. Current docs state twenty-one; released history stays dated.

No commits, pushes, tags, stash/reset/checkout, release/version/lock binding, secrets,
memory writes, new restrictions or removed-hook recreation. Generated Codex output
stays temporary. Mir Harness owns subsequent installation, binding and release.

Implementation is complete. Full verification: 1315 passed / 3 failed (one expected
mir-core lock mismatch pending ADR-80 binding; two installation failures on PyPI DNS).
Final focused checks: 33 passed / 0 failed; Ruff and generated parity pass.
No generated Codex installation or bootstrap re-attestation is needed for this change.
Detailed evidence and preserved inputs are in the log entry linked above.
