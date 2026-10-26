# Plan

## Active task: release 0.13.32 (`mir-mcp`) (2026-10-27)

Intent authority: the owner's release approval (Discord 1564297975755448493) and
session instruction to use Claude writers (Discord 1564282799035523227), relayed by
Mir Harness Main (parent-supplied). Design authority: this cursor and
[ADR-91](../docs/decisions/adr-91-stdio-mcp-package-admission.md). Baseline: e38add3
on `main`, fast-forwarded from `feat/mir-mcp`, not pushed; slices 1 and 2 are
committed at f715b19 and e38add3.

Prior cursors are preserved verbatim in the evidence log:
- slice 1: [cursor before B3 mir-mcp slice 2](change_log.md#cursor-before-b3-mir-mcp-slice-2-2026-10-26);
- slice 2: [cursor before B3 slice-2 review fixes](change_log.md#cursor-before-b3-slice-2-review-fixes-2026-10-26)
  and [cursor before release 0.13.32](change_log.md#cursor-before-release-01332-2026-10-27).

Design: the source commit follows the daa7e35 release pattern. Bump current release
surfaces from 0.13.31 to 0.13.32 without rewriting historical release records;
acknowledge the new `mir-lifecycle-hooks` tree digest in the provider config (hook
behavior unchanged by owner decision); add no `mir-mcp` provider acknowledgement.
Add 0.13.32 CHANGELOG, README and MIGRATION entries, then regenerate the adopter
payload. `.mir/capability-lock.json` belongs to the separate bind commit.

Request matrix (initially open):
1. Version surfaces: VERSION, pyproject, uv.lock project entry, both marketplaces'
   current entries, every plugin manifest, `mir_mcp.py` VERSION, version-pinning tests.
2. Lifecycle digest acknowledgement equals `_tree_digest(plugins/mir-lifecycle-hooks)`.
3. Release notes: CHANGELOG, README and MIGRATION 0.13.32 entries.
4. This cursor; prior cursors preserved and every reference resolvable.
5. Preparation-only tests comparing the working tree to HEAD removed if found.
6. Adopter payload regenerated after the last edit.
7. Ruff, `git diff --check` and one full suite; only
   `test_repository_lock_is_portable_and_matches_managed_trees` may fail before the bind.

Constraints: no commits, tags, pushes, sub-agents, capability-lock edits, real
runtime homes or host `mir capability` operations. Scratch stays under the
owner-specified external cache directory.

Observed (2026-10-27, Claude writer): items 1-4 and 6 prepared. Item 5: no test
compares the working tree to HEAD in a way that fails after the bind; the only
HEAD-relative check is the lock test itself, so nothing was removed. Ruff,
`git diff --check` and Codex parity pass. The full suite on the tree before this
status note returned `1 failed, 3458 passed in 564.22s`; the failure is the expected
pre-bind lock test. The final suite runs after the payload is regenerated from this
note; Main records its result. No release, binding or runtime readiness is claimed.
