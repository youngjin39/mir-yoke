# Plan

## Active task: reference application profile registration and 0.10.8 preparation (2026-10-11)

Authority: the current owner request in this repository only. This single cursor owns intent and design.
Predecessor cursor and intent are preserved verbatim in `tasks/change_log.md` under
"Reference application profile registration and 0.10.8 preparation (2026-10-11)".

Design: mirror e3cb1a8 registration and e3cb1a8/4c5a85b release preparation; use the
existing knowledge category, alphabetical capability inventory and seventeen-skill
package expectation. Preserve the new skill and test bytes. Refresh all eight plugin
manifests, release metadata, lifecycle package acknowledgement and generated adopter payload.
No canonical Codex derivative source changes are needed; verify parity without installing derivatives.

- [x] Inspect both precedent commits, contracts and current inventory.
- [x] Register the existing skill and prepare version 0.10.8 metadata and documentation.
- [x] Regenerate digest acknowledgement and adopter payload through repository routines.
- [x] Run full pytest, Ruff and Codex sync; report tails, exit codes and final status.

No commit, push, tag, release, other-repository write, protected-memory write or `.codex/**` write.
The capability lock remains pre-release-bound; only the documented same lock test failure is acceptable.

Completed: final full pytest returned exit 1 with 1786 passed and only the accepted
pre-release-bind failure, `tests/test_capability_cli.py::test_repository_lock_is_portable_and_matches_managed_trees`.
Ruff and Codex sync returned exit 0. The first run also exposed a private absolute path
in the new evidence log; it was corrected and the second full run proves that failure resolved.
The skill and test remain byte-identical to their initial untracked files.
No requested source work remains. Release binding and all Git publication remain outside this task.
