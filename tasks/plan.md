# Plan

## Active task: release 0.13.33 (`mir-mcp` test portability fix) (2026-10-27)

Intent authority: the owner's release approval (Discord 1564297975755448493) and
session instruction to use Claude writers (Discord 1564282799035523227), relayed by
Mir Harness Main (parent-supplied). Baseline: 50c96b4 on `main` (tag v0.13.32,
pushed). The v0.13.32 GitHub `release` workflow failed in "Validate repository release
candidate" (`scripts/verify_release_readiness.py --current-clean-tree`, ubuntu,
Python 3.12) with nine `mir-mcp` test failures; `validate` passed.

Prior cursor preserved verbatim:
[cursor before release 0.13.33](change_log.md#cursor-before-release-01333-2026-10-27).

Root causes (confirmed locally, 2026-10-27):
1. In-process test loaders (`spec_from_file_location` plus `exec_module`) in the
   git, indirect-guard and security `mir-mcp` tests wrote
   `plugins/mir-mcp/__pycache__` when `PYTHONDONTWRITEBYTECODE` was unset, and the
   checker and relations tests did the same under `plugins/mir-core`. The closed
   package validator then correctly rejected the undeclared directory, and copies of the
   package carried it into later tests. The product validator reads `INPUT_SCHEMAS` as
   data, and the server compiles its siblings from source, so neither writes bytecode.
2. Profile tests assumed `/usr/bin/python3` lacks `tomllib` (macOS 3.9.6). On ubuntu it
   is 3.12, so the server applied the profile and the expectation flipped.

Design: loaders compile the source directly, so tests never write bytecode; the
validator is unchanged. Profile tests probe each interpreter's real `tomllib` and add a
venv runtime with `tomllib` import blocked, so both branches stay covered on every host;
the server is unchanged apart from its version. The release follows the 0.13.32 pattern:
bump current surfaces to 0.13.33 without historical rewrites, renew the
`mir-lifecycle-hooks` acknowledgement (no `mir-mcp` provider acknowledgement), add
CHANGELOG, README and MIGRATION entries, and regenerate the adopter payload last.
`.mir/capability-lock.json` belongs to the separate bind commit.

Request matrix (initially open):
1. Fail-first: the `__pycache__` failures without `PYTHONDONTWRITEBYTECODE`, and the
   `tomllib` failures with a 3.12 stand-in for `/usr/bin/python3`.
2. Test fixes for both causes; validator and server behavior unchanged.
3. No product path writes `__pycache__` into an installed `mir-mcp` tree.
4. Version surfaces, lifecycle acknowledgement, release notes, this cursor.
5. `mir-mcp` and capability tests without `PYTHONDONTWRITEBYTECODE`, then no new
   `__pycache__` under `plugins/`.
6. Ruff, `git diff --check` and one full suite; only
   `test_repository_lock_is_portable_and_matches_managed_trees` may fail before the bind.
7. Adopter payload regenerated after the last edit.

Constraints: no commits, tags, pushes, sub-agents, capability-lock edits, real
runtime homes or host `mir capability` operations. Scratch stays under the
owner-specified external cache directory.

Observed (2026-10-27, Claude writer): items 1-6 checked; item 7 follows this note.
Without `PYTHONDONTWRITEBYTECODE`, the unfixed tests failed 4 times in `mir-mcp`
(`__pycache__`), and a 3.12 stand-in for `/usr/bin/python3` reproduced the other 5
failures. After the fixes: `mir-mcp` and capability tests `931 passed`, with no new
`__pycache__` under `plugins/`. An installed copy run without `-B` on 3.9 and 3.12
wrote no bytecode. Ruff, `git diff --check` and Codex parity pass. The full suite
without the variable returned `1 failed, 3463 passed in 789.78s`; the failure is the
expected pre-bind lock test. Outside this scope, `tests/test_ontology_skill.py` and
`tests/test_ontology_runner.py` still write `__pycache__` under `plugins/mir-core`
(excluded from tree digests); this is reported, not changed. New tree digests:
`mir-lifecycle-hooks` e49866a7fb93704cb5fc1730dcd1ba9f19194d85ba6f6405da86f0c8ff09bba8
(after Main added the owner-approved delegation guidance to `runtime-continuity`),
`mir-mcp` cb9876feaf228e47d7be285c261e0965a296297637484952092440681e085fe7.
No release, binding or runtime readiness is claimed.
