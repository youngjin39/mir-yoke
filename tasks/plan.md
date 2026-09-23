# Plan

Owner-authorized second-pass audit, 2026-09-23. `tasks/intent.json` is the intent authority.

- [x] Re-check the 15 items against actual files, commands and read-only health evidence.
- [x] Repair stale runtime guidance and the setup test isolation defect; preserve prior wording.
- [x] Generate Codex output in a temporary root and verify the generated candidate.
- [x] Run the full suite and affected checks; classify residual failures.

Repository work is complete. The orchestrator committed the verified changes locally (no push, tag or
release). The four agent-source wording edits were withheld: the capability lock binds agent bytes to
a published commit, so they ship with the next authorized release together with the lock binding.
Two network-dependent tests still need a network-capable environment.
Evidence, predecessor records and exact delivery paths: `tasks/change_log.md`,
"Second-pass fleet re-verification".
