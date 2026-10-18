# Change log

## Always-delivered handoff authority (2026-10-18)

Intent and bounded design authority: tasks/plan.md; current Main writer brief and owner
Discord 1561203611252297729 are parent-supplied. Probe counts in the brief were not
independently reproduced. Verified repository HEAD: b19984bac4de2d0be61fee4cf4b9e270f7797414.
Qualified target: mir-yoke:always-delivered-handoff-authority. Lifecycle: implemented;
temporal: current working tree; epistemic: locally checked; verification: targeted checks
pass, full-suite green pending Main's lock update. Observed on 2026-10-18.
Map SHA-256 matches the supplied 516c5b160c0fa49de51e4a0dc6f14c6e6a955d1baf72cc75dc2c93de7ea23e79;
map /concepts/Task identifies the cursor and /contract declares mir.common-semantics@1.1.0.
The unchanged ontology SKILL.md Handoff section supplies the six fields and authority rule.

One sentence appended to MESSAGE; validator source pin and package digest acknowledgement
updated to the validated hook tree a12ee8de9b487c9aab61eb6f0e1eefc34ee79c55c095abb950800f19ee76faeb.
This is source-byte validation; fresh runtime delivery/attestation remains unknown and Main-owned.
No commit, tag, push, capability command, lock, version, release heading, consumer, live-memory
or repository .codex/** edit. Output remains bounded; handler is 814 bytes (limit 1024).

All uv commands used the host's shared external-volume UV cache and a task-scoped TMPDIR.
- Fail-first: uv run pytest -q tests/test_plugin_skill_packages.py::test_lifecycle_hook_plugin_uses_one_exact_shared_hook_file
  yielded 1 failed in 0.14s, specifically for the missing sentence.
- After implementation: package tests 15 passed; final focused package, digest and asset tests
  (test_plugin_skill_packages.py, test_capability_security.py::test_capability_source_declares_the_reviewed_active_hook_package,
  test_template_asset_classification.py) yielded 22 passed in 0.49s.
- Initial uv run pytest -q: 2070 passed, 69 failed in 239.76s; stale source digest acknowledgement
  caused capability failures. Updated that pinned digest; no runtime registration was performed.
- Final uv run pytest -q: 2138 passed, 1 failed in 227.43s. Sole failure:
  tests/test_capability_cli.py::test_repository_lock_is_portable_and_matches_managed_trees,
  existing lock digest versus changed plugin tree. Lock edits are explicitly reserved to Main.
- uv run ruff check: all checks passed. git diff --check: exit 0.
- uv run python scripts/mir_ontology.py impact --git-diff --strict: exit 0, no stale refs.

After these record edits, regenerate payload with
uv run python -m tools.template_assets --write-adopter-payload --json, rerun the 22 focused
checks and diff check, then delete scratch. No further record mutation after generation.
Request matrix: 4/4 evaluated, 3/4 closed. Main owns lock refresh, full-gate rerun, repository
derivatives if needed, delivery and actual runtime attestation; those outcomes remain unknown.

## 0.13.6 release preparation (2026-10-18)

Intent and bounded design authority: `tasks/plan.md`, recording the current Mir Harness Main
writer brief. Owner Discord 1561086355767824457 and earlier delivery direction are
parent-supplied context, not independently retrieved messages. Qualified target:
`mir-yoke:release-0.13.6-commit-a`. Lifecycle: prepared content; temporal: current working
tree; epistemic: locally checked; verification: full offline suite checked; only the explicitly deferred repository-lock gate is open.

Verified HEAD: `b42ec20c944d77b84acf0202a2da99794e61e4f6`; reference preparation: `5276401`.
Verified map `.mir/ontology-map.json` SHA-256:
`516c5b160c0fa49de51e4a0dc6f14c6e6a955d1baf72cc75dc2c93de7ea23e79`.
Map `/namespace` and `/contract` declare `mir-yoke` and `mir.common-semantics@1.1.0`.
Map `/concepts/Task` identifies this cursor; `/concepts/Capability` identifies capability
selection, not runtime adoption. Release behavior evidence is the unchanged source/test commit
`b42ec20` and its two CHANGELOG Fixed items; metadata preparation adds no behavior or contract
change and establishes no fresh runtime activation.

Mirrored the predecessor's exact 19-file release preparation set. VERSION, pyproject,
editable project entry only in uv.lock, four marketplace versions, eight plugin manifests and
two package-test expectations now use 0.13.6. Moved only b42ec20's two Fixed notes from
Unreleased into v0.13.6 dated 2026-10-18; updated MIGRATION current version and appended notes.
Validated lifecycle-hooks on a cache-free temporary copy using `_validate_plugin` with
`package_kind="skills-hooks"`; acknowledgement is now
`661680ec231a6c9b0de72ca6d689b44f377bde6cdf3fbab8a63e00d35235f79c`.
No hook source changed. The documented generator classified all 887 tracked files without
unclassified, duplicate or prohibited entries. Final records require payload regeneration.

All uv commands use the required external SSD cache; temporary suite/validation storage is
on the external SSD. Commands below use `uv run --offline` where applicable.

- Fail-first package version checks: 2 failed, 13 deselected in 0.06s before version edits.
- Focused release/package/public-surface/classification checks: 30 passed in 0.71s.
- `uv run --offline ruff check`: exit 0, all checks passed.
- `uv run --offline python scripts/verify_codex_sync.py`: exit 0, Codex derivatives match
  Claude sources. This verifier generates only in temporary storage; no repository derivative
  write was made.
- `uv run --offline python scripts/verify_context_paths.py`: exit 0, 9 files and 77 references.
- `uv run --offline python scripts/mir_ontology.py impact --git-diff --strict`: exit 0,
  no stale refs or selected extra checks.
- `git diff --check`: exit 0. Exact changed-file set equals `5276401` (19 files).
  Capability lock, ontology map and repository `.codex/**` have no diff.

Initial full offline suite: 2137 passed, 2 failed in 224.22s. Besides the expected lock
failure, exact adopter inventory comparison failed because this writer edited records after
payload generation while the suite was running. Regenerate payload before rerunning the full
suite, and regenerate/check again after final result recording. No product-code fix is needed.
Full-suite rerun: `uv run --offline pytest -q`, exit 1, **2138 passed, 1 failed in 234.69s**.
Sole failure: `tests/test_capability_cli.py::test_repository_lock_is_portable_and_matches_managed_trees`
at line 397 (unchanged lock versus modified plugin tree), explicitly deferred to Main commit B.
No tests were excluded or weakened. Request matrix: 5/5 evaluated, 4/5 closed; full-gate cell
remains open only for this lock binding. Version-surface assertions also verified uv.lock differs
only in the editable project version and the map hash matches the supplied pin.

After these final record updates, run the documented
`uv run --offline python -m tools.template_assets --write-adopter-payload --json`, exact
inventory comparison, the same 30-test focused gate and `git diff --check`. Final evidence is
reported in the writer response without another record mutation, avoiding stale payload hashes. Main owns repository derivative
regeneration/review, commit A, separate lock-binding commit B, final lock/full-gate verification,
and any subsequent authorized delivery. No commit, tag, push, external network, lock binding,
activation, consumer write, live database write or secret read was performed by this writer.
Final A/B identities and delivery/runtime outcomes remain unknown and Main-owned.

## Namespace fence and activation scope (2026-10-18)

Intent/design authority: `tasks/plan.md`, recording the current Mir Harness Main writer brief.
Owner Discord 1561086355767824457 and the Harness run
`ontology-engineering-settlement-2026-10-17` are parent-supplied authority context, not messages
independently retrieved here. Qualified target: `mir-yoke:namespace-fence-and-activation-scope`.
Lifecycle: source changes prepared; temporal: current working tree; epistemic: locally checked;
verification: full suite has only the release-coupled repository-lock mismatch documented below.

Verified pins: portable repository root `.`; HEAD `6abc3ff28e3b80e154adaa599142bc1a8848ab8c`.
The supplied map SHA-256 matched before edits:
`c20fbf3bdb910d3872b1f66730b56e0f34e8fa00c707e91eedd458c25a374340`.
Current `.mir/ontology-map.json` SHA-256:
`516c5b160c0fa49de51e4a0dc6f14c6e6a955d1baf72cc75dc2c93de7ea23e79`.
Map `/namespace` and `/contract` retain `mir-yoke` and `mir.common-semantics@1.1.0`.
Current source SHA-256 pins:

- `plugins/mir-core/skills/ontology/scripts/mk_query.py`:
  `a9c9939c25ccd2dbbf922087d5cf6aa08ce4b72a940f1421d7224e70bbf664d6`.
- `scripts/verify_plugin_cli_activation.py`:
  `99c9e0881c4cdc4caa6c5ac4884c415d11fee4b3809fae263fd6f11b7f3c326f`.

Observation: local session on 2026-10-18. Read the parent-supplied Harness settlement
`tasks/reports/ontology-engineering/settlement-2026-10-17/final-report.md` lines 37, 43 and
67-69, and the J3/J4 report defect sections. These explain the prior gaps, not edit authority.
Verified locally that the old client printed supplier nodes unchanged and that ADR-89 section
2.2 requires rejecting returned Claude scopes other than `user`. Map `/questions/1` indexes
that activation evidence; `/error_cases/7` now links only the synthetic client namespace fence.
It does not establish supplier authorization or end-to-end private-data protection.

The client now filters both nodes and citations against explicit requested namespaces, or the
four federation namespaces in the guide when omitted. Unknown and unlabelled entries are
dropped. It appends a separate `{"scope":"client","reasons":["namespace_filtered"]}`
object to the degradation list, preserving supplier
diagnostics without echoing discarded content or source references. All-dropped results retain
the exact empty status/reason and soft/hard exits, plus degradation. Every query response is
fenced, including a supplier response labelled `refused`; refusal status and content-free
refusals remain unchanged. Feedback is untouched. The verifier now compares the single enabled
Claude record's scope to `user` before validating its path/digest; Codex needs no scope field.
Updated the guide in one line and added two Unreleased fixes without changing versions.

Fail-first evidence (all uv commands used the owner-specified external SSD cache, `--offline`,
and external SSD temporary storage; no live supplier, network or runtime activation was used):

- Before implementation:
  `uv run --offline pytest -q tests/test_ontology_skill.py tests/test_plugin_skill_packages.py -k 'outside_allowed_namespaces or namespace_filter_removes_all_nodes or non_user_claude_install_scope' --tb=short`:
  exit 1, **11 failed, 1 passed, 262 deselected in 0.71s**. Six cases leaked synthetic
  out-of-scope nodes/citations, two missed filtered-empty behavior, and three accepted
  project/local/missing Claude scope. The user-scope positive control passed.
  After the first fix: **12 passed, 262 deselected in 0.53s**.
- Review added the supplier-status bypass negative. Before removing the refusal exemption:
  `uv run --offline pytest -q tests/test_ontology_skill.py -k 'fence_namespaces and refused' --tb=short`:
  exit 1, **6 failed, 259 deselected in 0.47s**. They now pass in the final suite.
- The new namespace test was renamed to `test_should_fence_namespaces` and its E08 reason
  shortened to retain the existing 12 KiB mapping budget. An intermediate run exposed
  **7 failed, 310 passed** solely from that budget warning; no gate was weakened.
- The initial payload verification exposed **1 failed, 36 passed** because generated hashes
  were stale; documented payload regeneration restored the boundary checks below.

Original-pass verification read directly from executed output:

- `uv run --offline pytest -q tests/test_ontology_skill.py tests/test_ontology_runner.py tests/test_mir_ontology.py tests/test_plugin_skill_packages.py --tb=short`:
  exit 0, **323 passed in 19.64s**. Includes the current 18 namespace/scope cases, process
  cleanup, isolated skill execution, Python 3.9 stdlib, unavailable/empty, refusal and feedback.
- `uv run --offline pytest -q tests/test_template_asset_classification.py tests/test_adopter_slim.py tests/test_no_korean_in_user_facing.py tests/test_release_metadata.py tests/test_public_template_surface.py --tb=short`:
  exit 0, **37 passed** after payload regeneration.
- `uv run --offline ruff check`: exit 0, all checks passed.
- `python3 scripts/mir_ontology.py mapping`: exit 0, **0 errors, 0 warnings**, contract/map 1.1.0.
- `python3 scripts/mir_ontology.py impact --git-diff --strict`: exit 0, no stale refs;
  selects the executed namespace regression. Selection itself is not execution evidence.
- `uv run --offline python scripts/verify_codex_sync.py`: exit 0,
  **Codex derivatives match Claude sources**; generation occurred in external scratch only.
- `uv run --offline python scripts/verify_context_paths.py`: exit 0, **9 files/77 references**.
- `uv run --offline python -m tools.template_assets --write-adopter-payload --json`: exit 0,
  **887 tracked/classified**, no unclassified, duplicate or prohibited entries. This refreshes
  the existing stale capability-lock inventory hash without changing the lock itself; final
  record hashes use the same generator.
- `uv run --offline pytest -q tests/test_capability_cli.py -k repository_lock_is_portable_and_matches_managed_trees --tb=short`:
  exit 1, **1 failed, 55 deselected in 0.08s** at line 397: modified mir-core tree digest
  `9d2a0dbe427fb4c86adb9bf2213d68e75560da690f53c2683fa67dcfc57bcb32` differs from locked
  `340987bee8b04046f3be57c1a2d04929164099802e8769fe1d53e79636c4a53f`.
  Main must rebind the plugin tree during the later 0.13.6 release; this writer did not alter it.
- `git diff --check`: exit 0. Full pytest was not run in the original bounded pass;
  the continuation below runs it at Main's explicit request.

Degradation-shape correction, continuing this same entry under Main's writer brief:

- Read-only local evidence: `memory-keeper:src/mir/federation/assemble.py#ContextPack`
  types `degradation` as `list[dict[str, Any]]`; `ContextPack.to_dict` emits it unchanged.
  `memory-keeper:src/mir/federation/mcp_server.py#_validate_context_pack_response` checks
  an array of objects with string `scope` and list-of-string `reasons`.
  Observed locally on 2026-10-18, source SHA-256s respectively
  `2182fab222452b679d735814f1b2887bb2a721ec59afbc818ebbab5eeb9b98aa` and
  `ed305322cb1107f29c24a297c6e4e96ba717ede87cbe292fa97bef1b0f2ffdaa`.
  This verifies payload shape only, not supplier authority. The earlier client digest was
  `69cee15aa1dc1478dfdb53f58ed370f7d7308ea4a71c79e5cafa47df9b5f7669`.
- Fixture packs now include `degradation: []`; namespace regressions cover absent, empty and
  existing supplier lists, structured/text transport, default/explicit namespaces, refused
  status, no echo and both filtered-empty exits. Exact list equality proves supplier objects
  remain unchanged and the client record is appended separately.
- Fail-first command:
  `uv run --offline pytest -q tests/test_ontology_skill.py -k 'fence_namespaces and existing' -x --tb=short`:
  exit 1, **1 failed, 281 deselected in 0.15s**. Output at `mk_query.py:205`:
  `AttributeError: 'list' object has no attribute 'setdefault'`.
- After the minimal append fix:
  `uv run --offline pytest -q tests/test_ontology_skill.py -k 'fence_namespaces or namespace_filter_removes_all_nodes or return_pack_and_reap_server' --tb=short`:
  exit 0, **44 passed, 249 deselected in 2.42s**.
- `uv run --offline ruff check plugins/mir-core/skills/ontology/scripts/mk_query.py tests/fixtures/ontology_mcp_server.py tests/test_ontology_skill.py`:
  exit 0, all checks passed. Mapping: **0 errors, 0 warnings**; strict impact: exit 0,
  no stale refs. The guide now explicitly describes a list of `{scope, reasons}` objects.
- `uv run --offline python -m tools.template_assets --write-adopter-payload --json`:
  exit 0, **887 tracked/classified**, no unclassified, duplicate or prohibited entries.
- `uv run --offline pytest -q`: exit 1, **2138 passed, 1 failed in 244.93s (0:04:04)**.
  The sole failure is
  `tests/test_capability_cli.py::test_repository_lock_is_portable_and_matches_managed_trees`
  at line 397. Current mir-core tree digest
  `d14c42468453164f5ef7c6484c45ac5324a50baa3667bd70412a40a4f4e194db`
  differs from locked `340987bee8b04046f3be57c1a2d04929164099802e8769fe1d53e79636c4a53f`.
  Per Main's brief, leave this release-bind gate unchanged. Exact adopter payload parity
  passed within that suite. Final-record procedure: regenerate the payload after these
  bookkeeping edits and rerun the exact parity check.
- Continuation matrix: **5/5 requested writer outcomes evidenced** (fail-first, append and
  preservation/client contracts, guide shape, payload binding, full-suite result reporting).
  The inherited release-lock gate remains open for Main. This continuation changed only
  `mk_query.py`, the synthetic fixture, `test_ontology_skill.py`, the guide, this entry,
  `tasks/plan.md` and generated `config/adopter-payload.json`; other earlier changes remain intact.

Original-pass request matrix: **5/5 evaluated, 4/5 closed**. Cells 1-4 (namespace/citation isolation,
unchanged client contracts, returned user scope, reference/Unreleased notes) have passing
evidence. Cell 5 is open only for Main's release-coupled lock gate; lint, ontology, package,
surface, generated parity and canonical records are checked. No recommendation was already
satisfied or stopped as incorrect. Changed files: the two scripts, two test modules, synthetic
MCP fixture, guide, changelog, E08 map entry, plan/evidence log and generated adopter payload.
No commits, repository `.codex/**` writes, lock writes, version bump, tag/release, restarts,
consumer/secret/private-body access or live database/service writes occurred. Unknowns:
actual post-release runtime adoption and supplier-side authorization remain untested. The
packet fields/pins are present; exact observation time is limited to the local date, and the
host root is represented portably rather than published. Main owns remaining release work.

## Superseded cursor before namespace fence and activation scope (2026-10-18)

```markdown
# Plan

## Active task: 0.13.5 release preparation (2026-10-18)

Intent authority: current Mir Harness Main writer brief, owner Discord 1561054690681032776
(2026-10-18) and directive `ontology-engineering-settlement-2026-10-17`, parent-supplied.
This single active cursor is the bounded design authority for commit A content preparation.
Release the ontology handoff-packet change `f25e508`; mirror preparation commit `8a9fa95`.
Previous cursor: `tasks/change_log.md#superseded-cursor-before-0135-release-preparation-2026-10-18`.

Bounded design: align the same release/version surfaces, move only the handoff note into
v0.13.5, follow the migration-entry pattern, refresh the lifecycle acknowledgement from a
cache-free copy, regenerate adopter payload after final records, and generate Codex derivatives
in external scratch. Do not write repository `.codex/**` or `.mir/capability-lock.json`.
No commits, tags, pushes, publishing, activation, consumer writes or live database writes.
Existing package/release checks cover these metadata-only edits; no new logic tests are needed.

Request matrix: (1) version surfaces and acknowledgement, (2) changelog/migration,
(3) adopter generation and scratch Codex parity, (4) required verification with only the
repository lock failure expected until B, (5) records and Main handoff.
Completion: 5/5 evaluated, 4/5 closed. Full pytest: 2092 passed, 1 expected lock failure
until B. Ruff, scratch Codex generation/parity, context paths, public surface and focused
release/package checks passed. Final records are included in regenerated adopter hashes.
Evidence: `tasks/change_log.md#0135-release-preparation-2026-10-18`.

Main remaining: review/regenerate repository derivatives, commit A, bind the lock in separate
commit B, verify the final lock and full gate, tag/push/publish, capability update/attest/finalize.
```

## 0.13.5 release preparation (2026-10-18)

Intent and bounded design authority: `tasks/plan.md`, recording the Mir Harness Main writer
brief. Owner Discord 1561054690681032776 (2026-10-18) and directive
`ontology-engineering-settlement-2026-10-17` are parent-supplied authority context, not
independently retrieved messages. Qualified target: `mir-yoke:release-0.13.5-commit-a`.
Lifecycle: prepared content; temporal: current working tree; epistemic: locally checked;
verification: required checks executed, repository-lock gate open until Main's commit B.

Verified pins: repository root `.`; HEAD `f25e508372c869585cb04d060fe5b3977e8b3a84`;
reference preparation commit `8a9fa95126b2b92420c344c3eaef88bddd801a6c`;
map `.mir/ontology-map.json` SHA-256
`c20fbf3bdb910d3872b1f66730b56e0f34e8fa00c707e91eedd458c25a374340`.
Map `/namespace` and `/contract` declare `mir-yoke` and `mir.common-semantics@1.1.0`.
Observation: local session on 2026-10-18. Released guidance is verified in
`plugins/mir-core/skills/ontology/SKILL.md#handoff` and
`plugins/mir-core/skills/ontology/references/knowledge-supply.md#agent-handoff-and-delegation`;
this preparation does not establish real-agent adherence or fresh runtime adoption.

Mirrored the predecessor's release-only 19-file set (excluding its two guidance/test fixes):
VERSION, pyproject, editable uv.lock package, four marketplace versions, eight plugin manifests,
and both package-test expectations now use 0.13.5. `uv lock --offline` resolved 29 packages;
only the editable package version changed in uv.lock. Moved only the handoff note from
Unreleased into v0.13.5 and followed the MIGRATION current-version/appended-entry pattern.
No contract version or implementation change was made.

Refreshed the lifecycle-hooks acknowledgement using `_validate_plugin` with
`package_kind="skills-hooks"` on a temporary copy excluding Python/cache artifacts:
`8eb85c9394a5d53c23b19e09fd1c383a2d7c80f74b970e842137c4b601401670`.
Hook source is unchanged. The documented adopter generator classified all 887 tracked files
with no unclassified, duplicate or prohibited entries; inventory contains 886 file hashes.
Generated Codex derivatives in external scratch; repository `.codex/**` was not written.

Verification uses the required external SSD uv cache and task-local external SSD temporary
storage. No private host paths are recorded here.

- Fail-first: `uv run pytest -q tests/test_plugin_skill_packages.py -k 'dual_runtime_manifests_share_one_skill_tree or marketplace'`:
  exit 1, 1 failed, 2 passed, 8 deselected in 0.07s, before manifest updates.
- `uv run pytest -q`: exit 1, **2092 passed, 1 failed in 252.97s**. Sole failure:
  `tests/test_capability_cli.py::test_repository_lock_is_portable_and_matches_managed_trees`,
  unchanged-lock/plugin-tree digest assertion at line 397. Expected until Main binds A in B;
  no test was excluded or weakened.
- `uv run ruff check`: exit 0, all checks passed.
- `CODEX_DERIVATION_OUTPUT_ROOT=<external scratch>/derivatives bash scripts/generate_codex_derivatives.sh`:
  exit 0. `uv run python scripts/verify_codex_sync.py`: exit 0,
  Codex derivatives match Claude sources.
- `uv run python scripts/verify_context_paths.py`: exit 0, 9 files and 77 references passed.
- `uv run pytest -q tests/test_no_korean_in_user_facing.py`: exit 0, 5 passed in 0.22s.
- `uv run pytest -q tests/test_release_metadata.py tests/test_plugin_skill_packages.py tests/test_no_korean_in_user_facing.py tests/test_template_asset_classification.py tests/test_public_template_surface.py`:
  exit 0, 26 passed in 0.69s before final records.
- `python3 plugins/mir-core/skills/ontology/scripts/ontology_check.py impact --repo . --git-diff HEAD --strict --json`:
  exit 0, no errors, warnings, stale refs or selected extra checks.
- `git diff --check`: exit 0. Changed-file set matches the predecessor's release-only set:
  19 files. Capability lock, ontology map and repository Codex derivatives have no diff.

Request matrix: **5/5 evaluated, 4/5 closed**. The full-gate cell remains open only for the
repository lock. Final records are followed by
`uv run python -m tools.template_assets --write-adopter-payload --json`, exact payload-hash
comparison and the same 26-test focused gate; results are reported in the writer handoff.
Main owns repository derivative regeneration/review, commit A, separate lock-binding commit B,
final lock/full-gate verification, tag/push/publish and capability update/attest/finalize.
No commit, lock bind, delivery, activation, consumer write, live database write or secret read
ran here. Unknowns: final A/B identities, delivery/runtime results and exact observation time;
all remain Main-owned. Self-check: qualified target, status axes, pins, evidence/provenance,
unknowns and bounded authority are recorded; private absolute root is deliberately omitted.

## Ontology handoff packet (2026-10-18)

Intent and bounded design authority: `tasks/plan.md`, recording the current Mir Harness Main
writer brief. Qualified target: `mir-yoke:ontology-handoff-guidance`. Lifecycle: implemented;
temporal: current working tree; epistemic: locally checked source/test evidence;
verification: bounded documentation and package checks passed, not agent adoption evidence.

Parent-supplied judge evidence inspected locally on 2026-10-18: report-J1.md:82 (missing pins/time),
report-J2.md:46,53,57 (incomplete packets, authority enlargement and config-source inference),
report-J3.md:55,63 (packet gaps and unauthorized child actions), report-J4.md:48,60-62
(handoff reference not read and authority enlargement). These are motivating evidence, not
permission to edit consumers or run their agents. No private bodies or live services were read.

Pins checked: repository root `.` (Mir Yoke); HEAD `ecf8291c87b9fff4620ff37123bb5809429b06fb`;
source `plugins/mir-core/skills/ontology/SKILL.md` working-tree SHA-256
`8f58621801a62d6115781a2c5ef92c498a77edf9246fe39f9984620eb88111ea`;
`.mir/ontology-map.json` SHA-256
`c20fbf3bdb910d3872b1f66730b56e0f34e8fa00c707e91eedd458c25a374340`.
Map `/namespace` and `/contract` declare `mir-yoke` and `mir.common-semantics@1.1.0`.
Distributed contract SHA-256:
`b2f1ecd01aaa88d41caac2bc2481e7f4c5a429cff3983aaa85ddfb0fc2f1b93f`.
The existing six-field source is `references/knowledge-supply.md#agent-handoff-and-delegation`
under the ontology skill. It now appears directly in the body with a final missing-field/pin
self-check, child provenance labels and no expansion of owner authority. Frontmatter is unchanged.
The guide adds one sentence requiring actual client outcome/reason and the applied config source.

Fail-first (before the documentation fix):
`uv run pytest -q tests/test_ontology_skill.py -k 'carry_handoff_guards or report_actual_client'`
exited 1: **11 failed, 240 deselected in 0.19s**. Ten cases failed on missing `## Handoff`;
the client-outcome test failed on the absent reporting sentence. After the minimal fix,
the same command exited 0: **11 passed, 240 deselected in 0.03s**.

Verification (external SSD uv cache and task-local external SSD temporary directory):

- `uv run pytest -q tests/test_ontology_skill.py tests/test_mir_ontology.py tests/test_plugin_skill_packages.py`:
  exit 0, **271 passed in 19.45s**, including mapping and strict impact gates.
- `uv run pytest -q tests/test_template_asset_classification.py tests/test_adopter_slim.py`:
  exit 0, **28 passed in 4.06s** after documented payload regeneration.
- `uv run ruff check`: exit 0, **All checks passed!**
- `uv run python scripts/verify_codex_sync.py`: exit 0,
  **OK: Codex derivatives match Claude sources**. No repository `.codex/**` writes.
- `uv run python -m tools.template_assets --write-adopter-payload --json`: exit 0,
  **887 tracked/classified**, no unclassified, duplicate or prohibited entries.
  Regeneration also corrects a pre-existing stale capability-lock inventory hash;
  the capability lock itself is unchanged. Final record hashes are refreshed with the same command.
- `git diff --check`: exit 0 after removing a trailing blank line from the cursor.

Request matrix: **3/3 done** (body packet/authority, actual result/config guidance, tests/changelog/payload).
No already-satisfied or owner-decision item. Unknown: whether future real-agent briefs will carry
the packet; these tests enforce the supplied guidance, not agent adherence. Owner authority permits
only this bounded source/test/document/payload update; no commits, release, activation, network,
live database writes, consumer writes or repository `.codex/**` writes. Self-check: all packet fields
are present; absolute host root and exact observation time remain unspecified beyond local date.

## 0.13.4 release preparation (2026-10-17)

Authority: owner Discord 1561020393568079954 (2026-10-17), via Mir Harness Main, and directive `ontology-engineering-settlement-2026-10-17`, parent-supplied. Intent and bounded design authority: `tasks/plan.md`. This records commit A content preparation only, not a commit, release or activation.

Mirrored the exact 19-file set of e20d6fa. VERSION, pyproject, the editable uv.lock package version, four marketplace entries, all eight plugin manifests and both package-test expectations now say 0.13.4. `uv lock --offline` resolved 29 packages and changed only the editable package version. Moved only the ontology-reachability note out of Unreleased into the dated v0.13.4 section; followed the predecessor MIGRATION current-version and appended-entry pattern.

Refreshed the lifecycle-hooks acknowledgement with `_validate_plugin(..., package_kind="skills-hooks")` from a temporary copy excluding Python/cache artifacts: `2eb397e2a934165a2c1b4734453f6bddda540ed8a66f29101ed239672a2b1e82`. The hook source is unchanged. Generated the adopter payload with `uv run python -m tools.template_assets --write-adopter-payload --json`: 887 tracked/classified files, no unclassified, duplicate or prohibited entries.

Semantic evidence: unchanged `.mir/ontology-map.json` `/contract` declares `mir.common-semantics@1.1.0`, `/namespace` is `mir-yoke`, and `/error_cases/3` separates selection from execution. Its SHA-256 matches the brief: `c20fbf3bdb910d3872b1f66730b56e0f34e8fa00c707e91eedd458c25a374340`. Released guidance comes from c600b27 and the ontology-reachability record below; no runtime invocation-rate improvement is claimed.

Verification: all uv invocations use the host external-SSD uv cache; test/generator scratch uses the task-owned external SSD directory.

- Fail-first: package expectations changed before manifests; `uv run pytest -q tests/test_plugin_skill_packages.py -k "dual_runtime_manifests_share_one_skill_tree or marketplace"`: 1 failed, 2 passed, 8 deselected. Failure compared 0.13.3 manifests with 0.13.4.
- `uv run pytest -q`: exit 1; 2080 passed, 1 failed in 240.27s. The sole failure is `tests/test_capability_cli.py::test_repository_lock_is_portable_and_matches_managed_trees` at the unchanged-lock/plugin-tree digest assertion (line 397). Expected until Main binds A in B; no test was weakened or excluded.
- `uv run ruff check`: exit 0, all checks passed.
- `CODEX_DERIVATION_OUTPUT_ROOT=<external scratch>/derivatives bash scripts/generate_codex_derivatives.sh`: exit 0. No canonical derivative input changed. `uv run python scripts/verify_codex_sync.py`: exit 0, derivatives match Claude sources. Repository `.codex/**` was not written. The initial generator call lacked the external uv-cache variable and failed cache initialization; rerun with the required variable passed.
- `uv run python scripts/verify_context_paths.py`: exit 0; 9 files and 77 references passed.
- `uv run pytest -q tests/test_no_korean_in_user_facing.py`: exit 0; 5 passed.
- `git diff --check`: exit 0. File-set comparison with e20d6fa: equal, 19 files. `.mir/capability-lock.json`, `.mir/ontology-map.json` and repository `.codex/**` have no diff.

Request matrix: 5/5 evaluated, 4/5 closed. Only the full-gate cell remains open for the release lock. After closing the records, regenerated adopter hashes and ran `uv run pytest -q tests/test_release_metadata.py tests/test_plugin_skill_packages.py tests/test_no_korean_in_user_facing.py tests/test_template_asset_classification.py`: exit 0, 23 passed in 0.61s. Final inventory is refreshed again after recording this evidence and checked for exact equality. Main owns repository derivative regeneration/review, commit A, separate lock-binding commit B, final lock verification, tag/push/publish and capability update/attest/finalize. No commit or delivery operation ran here.

## Superseded cursor before 0.13.4 release preparation (2026-10-17)

```markdown
# Plan

## Active task: ontology reachability (2026-10-17)

Authority: owner Discord 1560995198857777253 and Mir Harness directive
`ontology-engineering-settlement-2026-10-17`, both parent-supplied. The directive
and pilot report remain in Mir Harness; they have not been independently inspected.
This single active cursor records intent and is the bounded design authority.

Make `mir-core:ontology` reachable from ordinary meaning-sensitive requests and
agent handoffs. Preserve selective lookup, add the minimum parent/child packet,
and update at most one existing bluebricks routing line. Add fail-first regression
coverage and an Unreleased note; run full pytest, Ruff, Codex parity and context
path checks. Check supported generators without writing repository `.codex/**`.

No commit, push, tag, release, version bump, release/attestation record change,
activation, restart, consumer write, secret access or live database access.
Use the external uv cache. Main owns `.codex/**` regeneration and final acceptance.

Parent-supplied pilot evidence: Mir Harness
`tasks/reports/ontology-engineering/settlement-2026-10-17/pilot/report.md` describes
30 sessions: ontology loaded but not invoked in 15 Claude sessions, map read in
8/15 Codex sessions, and six handoff briefs missing current semantic/evidence pins.
These are reported observations, not locally re-derived results or new authority.

Evidence log: `tasks/change_log.md#ontology-reachability-2026-10-17`.
Previous cursor and intent are preserved verbatim at
`tasks/change_log.md#superseded-cursor-before-ontology-reachability-2026-10-17`.

### Bounded design and evaluation

This cursor is the design authority. Extend the existing description, provenance
reference and single bluebricks route; add no skill, hook, gate or command.
Static regressions cover eight trigger groups, eight handoff packet groups and
the existing design route. They pin guidance, not actual runtime invocation rates.
Keep the body rule to retrieve only relevant sources and needed evidence.

Request matrix: (1) selective ordinary triggers, (2) minimum parent/child packet,
(3) one bluebricks route, (4) supported generated parity and Unreleased note with
version/release records unchanged, (5) fail-first and the full requested gate.
Packet semantics follow the distributed common contract's four axes and the
project map `/contract`, `/namespace`, `/error_cases/3` (selection is not execution).
The map digest matches the parent-supplied pin; it is not being edited.

### Acceptance

4/5 cells closed. Final new regression selection: 17 failed before source edits,
then 17 passed. An additional handoff-link assertion failed eight packet cases
before its one-line cue fix, then the new selection passed 17/17 again.
The final source full suite passed 2080 tests and failed one release-bound plugin
tree digest assertion; lock/attestation changes are forbidden here. All five
cells were evaluated; the full-gate cell remains open for Main. Ruff, Codex
scratch-generation parity, context paths, mapping and
strict impact passed. Main owns lock refresh under separate release authority;
no tests have been weakened or excluded. Actual runtime invocation improvement
is not claimed. Evidence remains in the single log linked above.

Main acceptance (2026-10-17, Mir Harness): every hunk reviewed. On the host the 17 new
ontology-skill tests fail against the previous skill files and pass now (239 in the module).
Full pytest: 2080 passed, 1 expected failure,
`test_capability_cli.py::test_repository_lock_is_portable_and_matches_managed_trees`, because
the plugin trees no longer match the 0.13.3 lock. The lock is rebound only by the release
procedure. Ruff, Codex parity and the context-path check (77) pass. Committed on branch
`feat/ontology-reachability`, so `main` stays at the released lock. Release, push and activation
wait on the owner's decision, because the capability source is the public repository.
```

## Ontology reachability (2026-10-17)

Authority: owner Discord 1560995198857777253 and Mir Harness directive
`ontology-engineering-settlement-2026-10-17`, parent-supplied; the external originals
were not independently fetched. Intent and bounded design authority: `tasks/plan.md`.
Pilot observations in the writer brief are parent-supplied evidence, not runtime
results of this change. No commit, delivery, activation or release is authorized.

Changed the ontology description to name ordinary meaning-sensitive situations,
retaining selective source lookup in the body. Extended the existing provenance
reference with a minimum handoff packet and one existing bluebricks route. No new
skill, gate, hook or command. Static regressions pin guidance; actual invocation
rates require a separate runtime pilot and are not claimed here.

Description before (213 characters):

> Apply a project-owned ontology mapping to the common semantic contract. Use for ontology, semantic contract, identity, same entity, relation meaning, status meaning, provenance, impact analysis, or a mapping file.

Description after (510 characters):

> Apply the project-owned ontology mapping and common semantic contract when an answer depends on whether two names are the same thing; who knew or believed what at a given time versus what is true; whether something is current, proposed, historical, retracted or superseded; whether evidence is still valid after its source changed; whether being able to act means being allowed to; a relation's direction or scope; or writing or receiving a handoff/brief for another agent. Use selectively, not for every task.

Description checks: inspected package/common-skill tests, capability validation and
Codex generator/verifier; no explicit numeric skill-description ceiling is declared
there. The description remains one quoted scalar and 510 characters.

Semantic evidence: the unchanged map `.mir/ontology-map.json` `/contract` pins
`mir.common-semantics@1.1.0`; `/namespace` qualifies Yoke identities;
`/concepts/Task` maps this cursor; `/vocabularies/7` separates verification claims,
and `/error_cases/3` (E04) distinguishes selection from execution. SHA-256 matches
the supplied pin `c20fbf3bdb910d3872b1f66730b56e0f34e8fa00c707e91eedd458c25a374340`.
The distributed `plugins/mir-core/skills/ontology/references/common-contract.json`
`/axes` declares lifecycle, temporal, epistemic and verification. Packet guidance
preserves those meanings and explicitly separates actor belief from truth.

Verification uses the owner-specified external uv cache and task-owned external TMPDIR.

- Fail-first: after adding only tests, the first selection produced 16 failed,
  1 passed, 222 deselected; existing provenance covered one field group. Tightened
  the reference-section boundary before implementation; the final new selection
  produced **17 failed, 222 deselected** (exit 1, 0.07s).
- Command: `uv run pytest -q tests/test_ontology_skill.py -k
  'ordinary_meaning_sensitive or minimum_parent_child or meaning_sensitive_design'`.
  After source changes: **17 passed, 222 deselected** (exit 0, 0.03s).
- Focused package/skill command: `uv run pytest -q tests/test_ontology_skill.py
  tests/test_common_skill_contracts.py tests/test_plugin_skill_packages.py`:
  **261 passed** (exit 0, 16.40s).
- First full `uv run pytest -q`: **2079 passed, 2 failed** (exit 1, 241.06s).
  The release-bound plugin tree digest assertion and public absolute-path scan
  failed. Removed the newly introduced host path from this log; retained the
  existing privacy test and capability lock unchanged. Follow-up results below.
- Privacy correction plus asset-classification checks: `uv run pytest -q
  tests/test_public_template_surface.py::test_should_expose_no_private_absolute_path_when_public_surfaces_are_scanned
  tests/test_template_asset_classification.py`: **7 passed** (exit 0, 0.36s).
- `uv run ruff check`: exit 0, all checks passed.
- `uv run python scripts/verify_codex_sync.py`: exit 0, derivatives match Claude
  sources. This invokes the documented generator in disposable external output;
  plugin skills share one source tree, so no repository `.codex/**` write is needed.
- `uv run python scripts/verify_context_paths.py`: exit 0, 9 files / 77 refs.
- `python3 scripts/mir_ontology.py mapping`: exit 0, 0 errors / 0 warnings,
  contract and mapping 1.1.0. `impact --git-diff HEAD --strict`: exit 0,
  only `/concepts/Task` and `/vocabularies/9` affected, no checks or stale refs.
- `uv run python -m tools.template_assets --write-adopter-payload`: exit 0;
  refreshed source inventory hashes only in `config/adopter-payload.json`.
  No released version, lock, attestation or release record changed.
- `git diff --check`: exit 0. All changes are supplier-owned source, tests,
  continuity records and the generated source inventory.

- Second full `uv run pytest -q`: **2080 passed, 1 failed** (exit 1, 220.55s).
  The privacy failure is closed; only the unchanged release-bound plugin tree
  digest assertion remains.
- Final review added an explicit handoff cue to the existing reference link in
  the ontology workflow. Before changing that line, the new link-reachability
  assertion failed all eight packet cases (8 failed, 231 deselected, exit 1).
  After the one-line cue change, the complete new selection again produced
  **17 passed, 222 deselected** (exit 0, 0.03s). Selective lookup remains unchanged.
- Final source-revision `uv run pytest -q`: **2080 passed, 1 failed** (exit 1,
  230.49s). Sole failure:
  `tests/test_capability_cli.py::test_repository_lock_is_portable_and_matches_managed_trees`
  at line 397: edited plugin trees do not match the unchanged released lock.
  No source changes followed this run; only final continuity evidence and its
  generated inventory hashes were refreshed.
- Final-source Ruff, Codex scratch-generation parity and context paths passed
  again; mapping/strict impact again reported no errors, warnings or stale refs.

Current request matrix (5/5 evaluated, 4/5 closed):

| Cell | Evidence | Status |
| --- | --- | --- |
| Selective ordinary triggers | Eight new description cases; selective body rule retained | closed |
| Minimum handoff packet | Eight new packet cases; common contract `/axes` | closed |
| One design routing line | New bluebricks case; one-line source diff | closed |
| Derivatives / Unreleased / version boundary | Scratch Codex generation and inventory generation; version/lock unchanged | closed |
| Fail-first / full requested gate | 17 red then 17 green; final full suite 2080 passed, 1 release-bound lock failure | open for Main |

Main owns final acceptance and any separate committed-source capability lock
refresh/release. The current `mir-code` and `mir-core` trees differ from their
release-bound lock digests; no test was weakened or excluded to conceal that.
Current HEAD at inspection: `2b8908790d4b8b14b97ba56172c7ff4410c2ef51`.


## 0.13.3 release (2026-10-17)

Authority: owner Discord 1560822145624580200 (via Mir Harness Main) for D1: release the held
item-22 skill, the verify request-matrix rule and the runner extraction together, with push,
tag and release. Reviewed and committed by Mir Harness Main.

Main cherry-picked 26d2f42 (repo-maintenance item 22) and 1a24dc0 (verify request matrix,
`select_active_distribution` extraction) from `maint/repo-maintenance-item-22` onto 0.13.2
`main`, then bumped VERSION, package metadata, the uv.lock editable line, all eight plugin
manifests and the marketplace to 0.13.3, refreshed the lifecycle-hooks acknowledgement with
`_validate_plugin` from a cache-free copy (`4b1993f3…35c4`) and regenerated
`config/adopter-payload.json`. The lock is bound to the prep commit from its git-archive tree in
the following commit. Consumers that keep a byte copy of the ontology runner refresh it after
activation.

## 0.13.1 release preparation (2026-10-16)

Authority: current owner release-preparation brief in `tasks/intent.json`; active cursor
and bounded design: `tasks/plan.md`. This records preparation only, not release or runtime proof.

Mirrored the exact 21-file set from 06ca2f9. VERSION, package metadata, the editable
package version line in uv.lock, all eight plugin manifests and marketplace versions
now say 0.13.1. Refreshed the lifecycle-hooks acknowledgement using the existing
`mir.core.capabilities.manager._tree_digest` implementation:
`0a5e1ba21fd2bd284af2ac483f0764e594b7deadcfe76052d799c277a86d20e1`.
Generated only `config/adopter-payload.json` with
`uv run python -m tools.template_assets --write-adopter-payload`; classification passed.
No generated Codex or instruction files were changed. No lock binding or delivery ran.

CHANGELOG moves the ec3372c fixes into the requested dated `[v0.13.1]` section and
adds the 22ff9a8 invariant-check selection and isolated distribution/rollback rehearsal.
The carried Unreleased block is byte-identical to eb5aeaa. The release heading test and
format note follow the owner's explicit v-prefixed heading request. MIGRATION describes
additional selected invariant checks, correction/removal of unresolved optional check refs,
and separate execution of selected checks. Contract 1.1.0 remains unchanged.

Semantic evidence: `tests/test_ontology_skill.py#test_should_select_declared_invariant_checks_without_execution`,
`tests/test_ontology_skill.py#test_should_reject_invalid_declared_invariant_check`, and
`docs/operations/ontology-distribution-rehearsal.md`. The unchanged project map declares
contract 1.1.0 at `/contract` and selection-only verification at `/error_cases/3` (E04).
Map SHA-256 remains `331ac91cd1d8ddd22558c11549395c62c06f2ad9616294470aec795ca44abe40`.

Verification (all uv invocations use the owner-specified external cache; fixture TMPDIR
is external; UV_FROZEN is not set; live-root consistency is excluded):

- HEAD: `uv run pytest --ignore=tests/test_harness_consistency.py`: exit 1,
  **2,058 passed, 1 failed in 290.33s**.
- Prepared tree: same command: exit 1, **2,058 passed, 1 failed in 240.83s**.
- The only failure in both runs is
  `tests/test_capability_cli.py::test_repository_lock_is_portable_and_matches_managed_trees`,
  asserting current plugin tree digests equal the unchanged committed lock. It already
  fails at HEAD after 22ff9a8; preparation changes the versioned tree digests further.
  No new failure appeared. Preserve the test and bind the committed tree under ADR-80.
- `uv run ruff check`: exit 0, `All checks passed!`.
- `uv run python scripts/verify_codex_sync.py`: exit 0,
  `OK: Codex derivatives match Claude sources`; generated comparison uses temporary output.
- `uv run python tests/test_no_korean_in_user_facing.py`: exit 0, PASS.
- `uv run python tests/test_link_integrity.py`: exit 0, PASS.
- `uv run python tests/test_schema_validity.py`: exit 0, PASS.
- `python3 scripts/mir_ontology.py mapping`: exit 0, **0 errors, 0 warnings**;
  contract/mapping 1.1.0, zero line refs.
- `python3 scripts/mir_ontology.py impact --git-diff --strict`: exit 0; affected
  entries reported, no selected checks, undeclared check links or stale refs.
- `git diff --check`: exit 0. File-set equality with 06ca2f9 and Unreleased byte
  equality with eb5aeaa were explicitly asserted.

After closing the task records, regenerate adopter hashes and rerun the focused
public-surface, release metadata, plugin package, asset inventory and ontology gates;
the final response reports those results. No implementation changes follow the full run.

Remaining Main steps:

1. Review and commit the prepared release tree.
2. Bind the capability lock to that committed implementation in a separate commit
   under ADR-80; refresh the adopter inventory after the lock changes.
3. Rerun full allowed tests and the clean-tree release gate against the bound candidate.
   Codex parity already passes; regenerate derivatives only if their canonical sources change.
4. Tag v0.13.1, push the implementation/lock commits and tag, and publish the public release.
5. Perform the separately authorized consumer sync and runtime registration/discovery
   verification. Revalidate each consumer map, run strict impact and execute its selected
   checks; installation or check selection alone is not passing evidence.

No commit, tag, push, publish, capability update/attest/finalize, consumer write,
user-runtime-home write, live database access or memory/context synchronization was performed.

## Automatic memory render guard (2026-10-16)

Authority: current owner section-A request in `tasks/intent.json`; active design and
cursor: `tasks/plan.md`. The previously completed release preparation cursor is
superseded; its outcome and pending Main delivery steps remain in the dated release
preparation entry below.

The shared `tests/test_harness_consistency.py` now passes a temporary copy of the
repository default manifest with only `generated_marker_rerender` (R11) disabled,
and prints the reason. The default manifest and production runner are unchanged.
An intercepted-command regression checks exact manifest equality apart from R11,
the original root, and preservation of the committed manifest without running a
single live-root rule. The shared file has no repository-specific tool imports.

Local tool tests no longer rerender from the live root. Matching/default-run R11
coverage uses a fake `.mir/memory.db` and observable fake render module in tmp;
the existing synthetic drift test remains. Runner equivalence uses a synthetic
failing ADR. The real-root green execution test was consolidated into the existing
synthetic green-manifest test, including schema validation. Searched shell scripts
and workflows contain no consistency-tool gate invocation requiring an edit.

Evidence so far (all uv commands use the owner-specified external cache; scratch is
external and every pytest command includes the required consistency-file deselect):

- Fail-first: `uv run pytest -q tools/harness_consistency/tests/test_memory_guard.py
  --deselect tests/test_harness_consistency.py --basetemp=<scratch>/red`:
  **1 failed**, asserting HEAD lacked `--manifest`; subprocess was intercepted.
  An earlier setup-only attempt had **1 error** because scratch parents were absent;
  created the owned scratch directory before the accepted failing assertion.
- After fix: `uv run pytest -q tools/harness_consistency/tests
  tests/test_public_template_surface.py --deselect tests/test_harness_consistency.py
  --basetemp=<scratch>/focused --tb=short`: **69 passed in 1.14s**.
- `uv run ruff check`: **All checks passed**.
- `uv run python scripts/verify_codex_sync.py`: **OK**, read-only parity check.
- Payload check initially reported **1 failed, 5 passed** after source changes;
  `uv run python -m tools.template_assets --write-adopter-payload --json` safely
  rebuilt its hashes: **884 classified**, no missing/duplicate/prohibited assets.
  Its diff also refreshes already-stale HEAD hashes for the capability lock and
  changelog; neither of those source files was changed by this task.
- Supplied ontology-map SHA-256 matched before edits; the map is unchanged.

Full-suite evidence:

- `uv run pytest -q --deselect tests/test_harness_consistency.py
  --basetemp=<scratch>/full --tb=short` with external TMPDIR:
  **2,042 passed, 3 failed, 1 deselected in 347.51s**. The early
  `test_should_remove_reference_snapshot_when_adopter_payload_is_built` saw stale
  inventory before regeneration; source tests were unchanged during execution.
- The remaining failures are
  `tests/test_capability_cli.py::test_repository_lock_is_portable_and_matches_managed_trees`
  (plugin tree digest mismatch) and
  `tests/test_release_metadata.py::test_release_version_is_consistent`
  (missing `## [v0.13.0]` heading). A focused rerun reproduced **2 failed in 0.08s**.
  `git diff --exit-code -- .mir/capability-lock.json plugins CHANGELOG.md
  pyproject.toml tests/test_capability_cli.py tests/test_release_metadata.py` returned
  **0**, establishing unchanged HEAD inputs for both failures. Leave these release
  issues intact; this bounded request does not authorize release-state repair.
- After final bookkeeping/payload regeneration:
  `uv run pytest -q tools/harness_consistency/tests tests/test_public_template_surface.py
  tests/test_template_asset_classification.py tests/test_advanced_reference_templates.py
  --deselect tests/test_harness_consistency.py --basetemp=<scratch>/final --tb=short`:
  **82 passed in 1.04s**. This verifies the repaired early inventory failure as well
  as all affected tests and the required public scan. Final Ruff also passed.
  The full suite is not claimed green. After this evidence-only update, regenerate
  the inventory once more and check the two inventory suites plus the public scan.

No live DB, memory/context synchronization, secrets, commit/push, or generated
instruction/runtime derivative write was performed. The ontology map retains the
supplied SHA-256. Main must run `uv run pytest -q tests/test_harness_consistency.py`
on the host with the external uv cache and external temporary directory; then rerun
the full suite after resolving the two release-state failures. No Codex regeneration
is needed for these test-only source changes; read-only parity already passed.

## P4 ontology work path (2026-10-15)

Authority: current P4 owner request in `tasks/intent.json`; design/cursor: `tasks/plan.md`.
Added `scripts/mir_ontology.py`, a stdlib checkout dispatcher with an explicit checker
override, root-bound local commands and normalized MK `--soft`. Released checker, client,
contract and versions are unchanged. Pytest now consumes Yoke's own map using mapping
and strict Git impact; selection prints checks without claiming execution.
The map retains canonical identities/refs and its existing 1.1.0/range declaration.
Whitespace and scoped new reasons keep it at 12,245 bytes. CLAUDE is 3,598 bytes;
surface commands moved intact to `docs/operations/ontology-verification.md`, retaining
the sub-agent routing pointer. MK connection declares supported on-demand transport,
not observed availability; no real MK, intake, live database or credentials were used.

Fail-first evidence (`UV_CACHE_DIR` set to the owner-provided external cache for every uv command):
- `uv run pytest -q tests/test_mir_ontology.py --basetemp=.pytest_cache/p4-red`:
  1 failure/4 setup errors before the runner existed.
- Same suite with `--basetemp=.pytest_cache/p4-red-ready`: **5 failed** at assertions
  with the unconnected runner; independent Git fixtures now initialized/committed.
- Runner implementation: **5 passed**. Each negative case starts with a passing gate,
  then deletes ARCHITECTURE or changes the map version; the wired gate rejects both.
- Extended own-map cases reverse a relation and substitute a disallowed Run endpoint;
  a changed declared check contains a raising sentinel, but selection never executes it.
  Repeated the disconnected-runner baseline for these three additions: **3 failed**;
  restored the runner byte-for-byte: **8 passed in 2.67s**. E02/E04 now reference these
  own-domain checks rather than only the existing generic checker regressions.
- Added zero-warning gate assertion, ran the single gate test against the temporarily
  oversized map: **1 failed**, reporting 12,307 bytes and 1 warning; trimmed only new
  reasons/formatting, then checker returned **0 errors, 0 warnings**.
- `uv run pytest -q tests/test_mir_ontology.py tests/test_ontology_skill.py
  --basetemp=.pytest_cache/p4-final-affected2`: **132 passed in 8.91s**.
- `uv run pytest -q tests/test_codex_derivation_script.py tests/test_plugin_skill_packages.py
  tests/test_template_asset_classification.py tests/test_advanced_reference_templates.py
  --basetemp=.pytest_cache/p4-package-final`: **34 passed in 3.80s** after payload refresh.
- `uv run ruff check`: **All checks passed**.
- `uv run python scripts/verify_context_paths.py`: **9 files, 75 references passed**
  after disposable fixtures were removed; `git diff --check`: passed.
- Explicit `MIR_ONTOLOGY_CHECKER=<checkout checker>` runner mapping: **0/0**, 1.1.0;
  strict Git impact: exit 0, no stale refs, checks-to-run section and re-validate prompt.
- Read-only `uv run python scripts/verify_codex_sync.py`: **FAIL: generated drift: AGENTS.md**.
  HEAD CLAUDE is embedded in HEAD AGENTS; working AGENTS equals HEAD. This is newly
  expected source/derivative drift, not a pre-existing failure. Main must regenerate.

Full-suite execution is being recorded below. The first direct in-repository basetemp
run was interrupted: an existing test copies ROOT recursively into its own scratch.
No pre-existing-failure claim is made. The replacement uses a disposable committed
current-source Git fixture inside `.pytest_cache/`, with basetemp as its sibling;
all writes remain inside this repository and no real index or commit is touched.

Final error-case scope:
| ID | Status | Evidence/scope |
| --- | --- | --- |
| E01 | not_applicable | Map navigation never merges cross-project entities. |
| E02 | covered | Own-map gate rejects reversed direction and disallowed endpoints. |
| E03 | covered | Existing current-versus-historical decision index test. |
| E04 | covered | Own-map changed-check selection leaves a raising sentinel unexecuted. |
| E05 | not_applicable | Lexical map navigation has no vector/inferred identity promotion. |
| E06 | covered | Existing graph source-digest refresh test. |
| E07 | covered | Existing explicit-apply authority/parser test. |
| E08 | covered | Existing synthetic MK personal-namespace refusal test. |
| E09 | covered | Runner soft missing-config query followed by a passing local gate. |
| E10 | covered | Wired own-map gate rejects stale refs and incompatible versions. |

No generated instruction/runtime derivatives were modified by this executor. Main owns
`scripts/generate_codex_derivatives.sh`, then adopter-payload refresh and parity recheck.
No live availability/ingestion claim or owner decision is inferred from these tests.

Later working-tree observation: a separate writer compacted the two new instruction
lines and regenerated AGENTS. Those edits were preserved, not reproduced or reverted.
Latest CLAUDE: 3,587 bytes; AGENTS: 3,676 bytes. A new read-only
`uv run python scripts/verify_codex_sync.py` returned **OK: Codex derivatives match Claude sources**;
this supersedes the earlier parity blocker. Updated affected suite:
`uv run pytest -q tests/test_mir_ontology.py tests/test_ontology_skill.py
--basetemp=.pytest_cache/p4-last-affected`: **135 passed in 10.50s**.

Full-suite isolation corrections: the initial source fixture with an artificial commit
finished with 11 failures, 1,907 passes and 1 skip (185.09s): stale inventory, missing
source ancestry and Git/provider-boundary artifacts. It was not treated as HEAD evidence.
The replacement is a local clone preserving the original HEAD, overlaid with current
sources, with its adopter payload refreshed. Tests use a sibling basetemp and
`GIT_CEILING_DIRECTORIES=<owner repo>` so non-Git fixture paths cannot inherit the outer
repository. A completed run then reported **2 failed, 1,919 passed, 1 skipped in 234.49s**:
the new evidence log exposed a local cache path (removed), and a reused fixture contained
ontology interpreter bytecode that the exact plugin-tree digest correctly rejected.
Removed only those disposable ontology caches and set `PYTHONDONTWRITEBYTECODE=1`.
The original-root capability-lock and public-path tests then both passed (**2 passed in 0.22s**).
There is no asserted pre-existing source failure: plugin sources and lock match HEAD,
and the clean-cache lock check passes. Final full-suite output follows below.

Changed files owned by this task: `.mir/ontology-map.json`, `scripts/mir_ontology.py`,
`tests/test_mir_ontology.py`, `CLAUDE.md`, `docs/operations/ontology-verification.md`,
`CHANGELOG.md`, `config/adopter-payload.json`, `tasks/intent.json`,
`tasks/archive/intent-history.json`, `tasks/plan.md`, `tasks/change_log.md`,
`tasks/handoffs/session-handoff-LATEST.md`. The separate AGENTS regeneration was preserved.
The runner also parses under Python's 3.9 grammar. No source contract, released checker,
client behaviour, package version, consumer repository or original Git history changed.

Final full-suite invocation: from the owner repository, with `GIT_CEILING_DIRECTORIES=$PWD`,
`PYTHONDONTWRITEBYTECODE=1` and the requested external UV cache, `uv run python` changed
directory to the current-source local clone and called
`pytest.main(["-q", "--basetemp=<owner repo>/.pytest_cache/p4-clean-final"])`.
The execution session returned **exit_code: 0**, observed after completion. Its redirected
scratch output path disappeared before the summary line could be read; the cause was not
established. No final pass/skip count is claimed from that missing output. The earlier
failed full-run counts above remain historical, not the final result.

Final current-source boundary checks (latest instruction/derivative edits included):
`uv run pytest -q` on the two capability-lock/public-path checks, followed by
`tests/test_mir_ontology.py tests/test_ontology_skill.py tests/test_codex_derivation_script.py
tests/test_plugin_skill_packages.py tests/test_template_asset_classification.py
tests/test_advanced_reference_templates.py`, with bytecode disabled and repository-local
basetemp: **171 passed in 13.61s**. An initial combined recheck had 170 passes and the
same ignored ontology bytecode-tree failure; removing that disposable cache made the
entire current-source boundary set pass. No lock or released source was edited to hide it.
Exact adopter-payload hashes must be refreshed after bookkeeping byte changes.

Final read-only receipts: `scripts/verify_context_paths.py` passed **9 files / 77 refs**;
`scripts/verify_codex_sync.py` returned **OK**; `ruff check` and `git diff --check` passed.
With the explicit checkout checker override, runner mapping returned **0 errors, 0 warnings**
at contract/mapping **1.1.0** and strict Git impact exited **0**, printed checks-to-run,
reported no stale refs and requested map revalidation. There is no remaining derivative
regeneration requirement in the observed working tree; this executor still made no generated writes.

## Covered-check resolution and MK guide (2026-10-15)

Authority: the owner request in `tasks/intent.json`; design authority: `tasks/plan.md`.
Covered checks now resolve files, one-based lines and last dotted name segments. Documentation
checks warn; absolute paths, traversal and escaping symlinks remain errors. Contract unchanged.
The 58-line MK guide follows federation mcp_server.py, serve.py and assemble.py, with
intake_fleet.py confirming the content Metadata status/valid_to line. The consumer contract's
lifetime-reader paragraph is stale: code releases connections and leases per call; the existing
test_mcp_call_lifetime.py release-between-calls case corroborates it. MK tests were read only.

Verification, with the requested UV cache:
- `uv run pytest -q tests/test_ontology_skill.py`: fail-first 8 failed, 60 passed;
  after implementation 68 passed.
- `uv run pytest -q tests/test_ontology_skill.py tests/test_plugin_skill_packages.py
  tests/test_template_asset_classification.py tests/test_advanced_reference_templates.py`:
  91 passed, including isolated packages and exact adopter payload equality.
- `uv run python -m tools.template_assets --write-adopter-payload`: pass.
- `uv run python scripts/verify_codex_sync.py`: OK; no generated writes or regeneration needed.
- `uv run ruff check tests/test_ontology_skill.py
  plugins/mir-core/skills/ontology/scripts/ontology_check.py`: pass.

Read-only invocation: `python3 plugins/mir-core/skills/ontology/scripts/ontology_check.py
mapping --repo <root>`. All used contract/mapping 1.0.0.

All 16 fleet mappings (names kept out of this public log): 15 clean; quietleaf 1 error, 1 warning.

quietleaf `/error_cases/9/check` references
`tasks/reports/ontology-adoption-2026-10-14.md#e10-negative-check`: check name not found,
plus "covered needs a repeatable check; a document is not one". Consumer left untouched.
No commit, push, install, service operation, live database access or generated writes.

One bullet per non-trivial change. Newest at the top.

- 2026-09-06: aligned Yoke's current purpose as the Harness-managed central capability supply
  system for independently owned repositories. Mir Harness manages direction, reuse decisions,
  verification, and authorized delivery coordination; Yoke supplies versioned generic capabilities;
  consumers retain their goals, data, local policy, adapters, and execution. The public-template
  classification and Starter, Project Agent Kit, optional CLI, and plugin channels remain intact.
  ADR-86 now takes precedence over older template-only role wording. The adopter boundary detects
  both the new and legacy Yoke contract titles. Regenerated derivatives and payload passed 52
  focused tests plus Codex parity, asset, Ruff, and diff checks; log:
  `/tmp/mir-yoke-purpose-alignment-postdocs.log`.

- 2026-09-06: published central operations implementation `0d5501fb765e7a829d3aec7ff64fa591f226f0d9` to main and verified origin parity. Compact current trackers supersede the mixed historical completion lists retained at that commit; the final implementation baseline is 987 full tests, not the earlier 974-test audit.

- 2026-09-06: separated central provider health from consumer enrollment and local integration,
  made read-only status bounded and snapshot-free, and added schema-3 provider advancement with
  receipt-bound pending-consumer catch-up and candidate-config rollback. Clean-candidate readiness
  passed every gate with 987 full tests.
- 2026-09-05: published the verified implementation as
  `dcff8d155ecb996b2a0dc014a293775fd05f5f06` on local `main` and `origin/main`.
- 2026-09-05: made the user-runtime installer reject lexical and physical runtime-home overlap,
  including case-insensitive macOS aliases and physical ancestors, before it writes a receipt or
  payload. Its transaction now rolls back on process interrupts before reraising the original
  `KeyboardInterrupt` or `SystemExit`. Final verification passed 974 tests, and clean-candidate
  release readiness passed every gate.
- 2026-09-05: repaired the maintainer and Project Agent Kit `PreCompact` hooks so the generated
  handoff snapshot keeps ordered Markdown tasks and formal incomplete `Step N:` cursors. The shared
  single-pass matcher accepts `in progress`, `in_progress`, `pending`, `blocked`, `active`,
  `running`, and `todo`, while excluding completed steps.
- 2026-09-05: recorded the current Yoke maintenance audit in the canonical intent cursor, archived
  superseded cursor history, and regenerated the adopter payload so its asset hashes remain exact.
  The first full run exposed the expected stale-payload detection after that cursor write
  (`test_should_remove_reference_snapshot_when_adopter_payload_is_built` and
  `test_should_match_exact_adopter_payload_when_release_inventory_is_generated`); regeneration
  restored the derived-state contract.
- 2026-08-30: accepted ADR-86, assigned Mir Harness as repository-maintenance manager, tracked the
  portable maintainer Profile without capability-lock protection, preserved adopter lock protection,
  regenerated derivatives and payload, and passed all 803 tests.
- 2026-08-30: replaced the remaining host-specific Codex reviewer contracts, made generated
  read-only sandbox classification require exact `Write` and `Edit` tool tokens, rejected invalid
  patterned frontmatter before agent output, refreshed the adopter payload and derivatives, and
  bound the protected capability lock to implementation commit `3018f5c`, and passed all 803 tests.
- 2026-08-30: made generated Codex configuration inherit operator-owned approval and native-agent
  routing policy, modernized host-neutral agent contracts, derived the fleet documentation
  advisor's read-only sandbox from frontmatter, preserved Claude model fields while keeping Codex
  agents unpinned, and documented external skill registry migration; implementation commit
  `90bb4f6` is lock-bound and all repository checks pass.
- 2026-08-29: migrated generated Codex permission ownership to operator-selected profiles, rejected
  legacy/profile mixing, bound vector writes to a persisted encoder fingerprint, preserved fact
  subject/provenance, quarantined credential-shaped facts, and passed clean-candidate readiness
  with 797 tests; published the implementation to `origin/main` at `d3693b8`.
- 2026-08-28: added ADR-84 and the current harness engineering upgrade guide without expanding the
  Starter, Project Agent Kit, optional CLI, plugin, or consumer-authority boundaries.
- 2026-08-28: corrected current-only fact/document retrieval, semantic history classification,
  explicit resumable missing-vector backfill, and the public 1024-dimension vector contract.
- 2026-08-28: fixed current Codex patch hook input, secret-value redaction, instruction-like memory
  quarantine, least-privilege generated Codex defaults, bounded SessionEnd parity, and hook-trust
  guidance; clean-candidate readiness passed with 793 tests.
- 2026-08-28: published the portable compact lifecycle and Project Agent Kit common-harness parity
  on `main`; owner-run Claude/Codex example repositories remain optional post-release acceptance.
- 2026-08-28: refreshed the protected capability lock against implementation commit `a0768ce` and
  reconciled the canonical intent, plan, checklist, TDD evidence, profile, and handoff.
- 2026-08-11: closed the active repository plan, reconciled canonical state, and removed merged
  local and remote agent branches so `main` is the only branch.
- 2026-08-11: clarified the canonical Project Agent Kit prompt in `409d09e`; concrete project
  purpose and goals are required before repository writes.
- 2026-08-11: published the restored harness engineering surface as GitHub Release `v0.9.0`; the
  immutable tag points to release commit `1d17358`.


## Archived trackers replaced by the 2026-09-06 closeout

These are historical snapshots from `0d5501fb765e7a829d3aec7ff64fa591f226f0d9`; current status belongs only to the active intent, plan and canonical handoff.

<details>
<summary>Historical tasks/plan.md</summary>

# Plan

## Current status — central capability operations repair complete (2026-09-06)

- [x] Separate host provider health from optional consumer enrollment and local integration status.
- [x] Make status read-only without project-tree hashing, while reporting bounded common-skill
  collisions and explicit `change_evidence` non-measurement.
- [x] Preserve current legacy active-provider compatibility and fail closed on a missing, tampered,
  or symlinked receipt-bound active configuration.
- [x] Migrate a fully verified legacy consumer set to schema 3, advance one host provider version
  without peer writes, and let pending peers catch up from the receipt-bound active configuration.
- [x] Prove candidate-config rollback restores the prior provider, registry, requester, and peer
  state; run focused capability and adopter checks before the final repository suite.
- [x] Regenerate the adopter payload and pass clean-candidate release readiness, including 987 full
  repository tests and the configured contract, CLI, asset, derivative, sanitization, link, schema,
  and lint gates.

- [x] Record the current audit in `tasks/intent.json`, archive superseded cursor history, and keep
  the active cursor as the authority for this review.
- [x] Confirm the four role-plugin manifests, inventories, shared lifecycle contract, capability
  source, managed lock, Claude/Codex generated parity, platform-lane documentation, and exhaustive
  asset classification remain aligned.
- [x] Inspect plugin and user-runtime installation boundaries for symlinks, collisions, divergence,
  home replacement, and rollback. Repair lexical and physical runtime-home overlap rejection and
  make process interrupts run transactional rollback before propagating the original interrupt.
- [x] Repair the maintainer and Project Agent Kit `PreCompact` hooks so one ordered matcher retains
  incomplete Markdown and formal `Step N:` plan cursors while excluding complete steps.
- [x] Regenerate `config/adopter-payload.json` after cursor and evidence-log changes, then rerun
  static gates, focused contract tests, and the full suite (974 passed); clean-candidate release
  readiness passed every gate.

The audit repaired the user-runtime installer and shared continuation snapshot. It found no remaining
plugin, platform, lock, Profile, or generated-parity defect. ADR-79 remains unchanged: macOS is the
primary operational and release-evidence lane; Linux and WSL are separate compatibility lanes;
native Windows is reference adaptation only.

Implementation commit `dcff8d155ecb996b2a0dc014a293775fd05f5f06` is verified at both local
`main` and `origin/main`. This closeout records the observed implementation delivery. Before further Yoke work, compare
`git rev-parse HEAD` with `git ls-remote origin refs/heads/main` to verify the latest local and
remote revisions.

## Completed prerequisite — role-plugin and common-hook delivery (2026-09-04)

- [x] Record the operator's packaging rule: common workflows formerly copied into repositories are
  grouped into Yoke-owned, role-oriented plugins and selected by repository Profile.
- [x] Accept ADR-90, which reserves a separately named `mir-lifecycle-hooks` package while keeping
  target-specific policy, protected paths, and writes repository-owned.
- [x] Publish `mir-lifecycle-hooks` with one shared, read-only `SessionStart` handler and supporting
  skill; admit only its exact schema-4 shape and acknowledged digest.
- [x] Add a separate dry-run-first installer for Yoke-authored Claude/Codex agents and Claude
  commands, with explicit homes, divergence protection, and file-digest receipts.
- [x] Audit MCP runtime and repository state: neither Claude nor Codex has a registered server, and
  Yoke implements no MCP server; `.mcp.json.example` is inactive consumer guidance only.
- [x] Record the future `mir-mcp` admission boundary without publishing an empty or misleading MCP
  plugin.
- [x] Prepare the Codex feature-request comment for the existing agent-plugin issue and a separate
  command-alias issue without duplicating upstream issue `#18308`.
- [x] Submit the Yoke use case to the open plugin-agent request `#18308`. Do not open the command
  alias issue because three prior requests were closed as intentionally replaced by skills.
- [x] Regenerate declared asset projections; run focused, full, derivative, lint, asset, and
  isolated real-CLI verification gates. The user-runtime installer has 14 passing safety tests.
- [x] Commit and push Yoke `main`, then activate and verify the published surfaces in the current
  Claude and Codex user homes without changing consumer repositories.

The four plugins are enabled in both runtimes and visible from all 14 registered repository roots.
The separate installer projects 11 agents into both runtimes and six commands into Claude; Codex
resolves those command intents through the corresponding plugin skills. Fresh Claude and Codex
sessions observed the exact 14-skill catalog and the trusted common `SessionStart` hook, so the
capability state is active and READY. The final closeout commit and remote-parity check are part of
this same completed delivery record.

Consumer repository mutation remains prohibited. The current operator instruction authorizes Yoke
commit/push and user-level activation; it does not authorize a PR, workflow, tag, or release.

## Completed prerequisite — ADR-89

- [x] Preserve and re-verify the completed ADR-88 supply-chain hardening.
- [x] Confirm isolated Claude and Codex installations expose the same three Yoke plugin trees from
  a working directory outside the provider checkout.
- [x] Record one explicit five-surface management contract for agents, skills, hooks, MCP servers,
  and commands without treating every surface as a plugin component.
- [x] Extend the commit-pinned capability sync so selected Claude commands are copied and locked
  like agents while Codex resolves the same workflow intent through the mapped plugin skill.
- [x] Strengthen the real-CLI probe to prove host-level recognition from two independent consumer
  working directories and verify installed skill inventories.
- [x] Update ADRs and current documentation, regenerate declared derivatives, and run focused and
  full verification plus independent review.

ADR-88 remains binding: the three role plugins stay skills-only, the exact `skills-hooks` package is
admitted under ADR-90, and MCP remains rejected. Central management means one Yoke-owned contract
with runtime-native delivery, not one undifferentiated plugin format. Status output distinguishes
the global plugin hook from repository-coupled generated hooks.

ADR-89 is now accepted and implemented. The schema-4 contract exposes all five surfaces, command
sync is digest-bound, host activation preserves the union of registered consumers, and rollback,
interruption, symlink, schema-downgrade, and concurrent-apply regressions are covered. The current
operator instruction authorizes commit, publication, and user-level host activation; only
consumer-repository mutation remains outside this delivery scope.

## Completed prerequisite — ADR-88

- [x] Classify the interrupted three-path worktree state and preserve valid generated output.
- [x] Remove host-specific tracked plugin activation from the public maintainer checkout.
- [x] Add an accepted decision for passive versus active plugin components and runtime boundaries.
- [x] Make capability-source declarations and validation fail closed for undeclared hooks or MCP.
- [x] Add focused regressions, regenerate declared projections, and run the affected/full gates.
- [x] Record verified completion without committing, pushing, tagging, releasing, reinstalling host
  plugins, or modifying a consumer repository.
- [x] Close final-review gaps for manifest permissions, schema-1 revalidation, and marketplace
  inventory/digest provenance; rerun all gates and obtain a clean independent verdict.
- [x] Close version-validation, receipt-downgrade, and rollback activation-scope findings; rerun
  all gates and obtain a clean independent verdict.

Independent final and CWE reviews returned PASS after the last rollback schema cross-check.

The current user instruction authorizes direct Mir Yoke edits, commit and push to `main`, and
user-level plugin/agent/command activation. It does not authorize a PR, workflow, tag, release, or
consumer-repository changes.

The three role plugins remain skills-only. ADR-90 admits only the separately named, exact read-only
hook package; no MCP behavior is invented without a concrete server requirement.

## Deferred owner work

When the owner supplies a target, run the published prompt once with Claude and once with Codex in
separate empty repositories. This is post-release acceptance, not an open repository task or a
`v0.9.0` claim.

</details>

<details>
<summary>Historical tasks/handoffs/session-handoff-LATEST.md</summary>

# Session Handoff — Yoke Central Capability Operations Repair

- Date: 2026-09-06
- Status: central capability status and multi-consumer update repair is implemented and awaiting
  final repository verification and authorized delivery.
- Authority: `tasks/intent.json` is the active audit cursor. The operator authorized this Yoke
  review and direct main delivery. Do not mutate user runtimes, consumer repositories, protected
  memory, credentials, external accounts, releases, or tags.

## Current Decision

Host provider health is separate from consumer-local enrollment and integration. Read-only status
uses bounded provider receipt, marketplace, package-tree, runtime activation, and collision evidence
without hashing the inspected repository tree. A global-only root reports `not-enrolled`; an enrolled
root can remain `pending-local-update` after a host provider advance.

Schema-3 registry state keeps one active provider commit and preserves peer local files and locks.
The first schema migration validates every legacy peer before activation. A pending peer later uses
the active receipt-bound configuration and commit rather than its stale local configuration or a
newer remote revision. The active configuration is digest-bound and rejects missing or symlinked
paths. Rollback restores the prior bound configuration before restoring host runtime registration.

Provider status proves installed package activation and cache evidence for the required hosts. It
does not substitute for a fresh repository-specific hook execution or trust attestation.

The supported capability contract remains healthy. The four optional role plugins have one shared
skill provider each, and `mir-lifecycle-hooks` alone supplies the exact, read-only shared
`SessionStart` handler. Project hooks and MCP configuration remain target-local. The user-runtime
installer and capability manager reject symlinked or replaced homes and paths, unmanaged collisions,
diverged managed files, unsafe caches, and incomplete rollback states. The installer now rejects
lexical and physical Claude/Codex home overlap, including a case-insensitive macOS alias or a
physical ancestor. It rolls back on a process interrupt before reraising that original interrupt.

ADR-79 remains binding: macOS is the primary provider and release-evidence lane; Linux and WSL are
separate compatibility lanes; native Windows is a target-owned reference-adaptation lane. No
platform-runtime, plugin, lock, Profile, or generated-parity defect remained after review. The
audit repaired one continuation defect: `PreCompact` had recognized only unchecked Markdown items,
so it could falsely report no active work for formal `Step N:` cursors. Both shipped hook copies now
use one ordered matcher for unchecked Markdown plus incomplete `in progress`, `in_progress`,
`pending`, `blocked`, `active`, `running`, and `todo` step states; completed steps are excluded.

## Evidence and next step

- `uv run python scripts/verify_release_readiness.py` passed every clean-candidate gate with exit
  code 0 after 987 full tests in 161.72 seconds. Its log is
  `/tmp/mir-yoke-capability-release-readiness.log`.

- Implementation commit `dcff8d155ecb996b2a0dc014a293775fd05f5f06` was verified at both local
  `main` and `origin/main` after publication.
- The final full suite passed 974 tests in 162.78 seconds with exit code 0. Its authoritative log is
  `/tmp/mir-yoke-final-pytest.log`.
- Focused plugin, capability, installer, derivative, asset, decision, and classification checks
  passed. The installer-specific suite has 19 passing tests, including physical macOS alias and
  process-interrupt rollback coverage. `uv run python scripts/verify_codex_sync.py`,
  `uv run python -m tools.template_assets --json`, and `uv run ruff check` also passed.
- `uv run python scripts/verify_release_readiness.py` passed every clean-candidate gate with exit
  code 0; its authoritative log is `/tmp/mir-yoke-final-release-readiness.log`.
- The first full run correctly failed two stale `config/adopter-payload.json` hash tests after the
  audit cursor changed. Regenerating the payload fixed the derived-state drift; the final full run
  passed.
- Changed files are the installer and its regression, two shipped pre-compact hooks and regression,
  cursor/history, plan, checklist, handoff, change log, and generated adopter payload. No
  user-runtime installation or consumer write occurred.

No further repository repair is pending. Before the next session begins new work, compare
`git rev-parse HEAD` with `git ls-remote origin refs/heads/main` to verify the latest local and
remote revisions. The generated snapshot below records the checkpoint before closeout delivery.

<!-- mir:runtime-snapshot:begin -->
## Runtime Snapshot (Generated)

### Active Plan Items
- No open plan items.

### Working Tree
- Working tree dirty (inspect git status --short).
<!-- mir:runtime-snapshot:end -->

</details>

Final independent parent acceptance (2026-09-06): 52 tests passed in 4.07s across `test_adopter_slim`, `test_public_template_identity`, `test_decision_authority`, `test_template_asset_classification`, `test_advanced_reference_templates`, `test_release_metadata`, and `test_no_korean_in_user_facing`. Current and legacy provider contract titles are both detected even when CLAUDE.md is the only copied provider surface. An intermediate exact-payload failure during documentation changes was resolved by final payload regeneration. Ruff passed; the independent final policy/docs review has no remaining blocker.

## 2026-09-06: Central capability supply mandate delivered

Implementation `f6d3f9a4949cfe19785d37ab952bf8f699d51802` was committed and pushed to `origin/main`; the parent observed matching local HEAD and remote refs/heads/main after the push. Final independent review has no remaining blocker. This documentation closeout records that observed delivery; its own revision can be checked through Git. No consumer commit/push or runtime installation was performed.

## 2026-09-23: Fleet consolidation — preserved inputs

Owner authority: Discord message 1552179237325377586, relayed by Mir Harness.
This maintenance continues ADR-86 without replacing its accepted purpose or consumer boundary.
Prior active documents below are preserved verbatim; current work lives in `tasks/plan.md`.

<details>
<summary>Pre-consolidation CLAUDE.md</summary>

```text
# Mir Yoke — Harness-Managed Central Capability Supply Contract

Mir Yoke is the Harness-managed central capability supply system for independently owned repositories. It distributes versioned generic capability sources as a public agent-guided template,
not an agent runtime and not a universal installer, and has no standing authority over consumers.
`starter/` is the four-file payload; the Project Agent Kit is the greenfield recipe; installed `mir`
acts only on an explicit target and operation.

## Outcome and completion

- Mir Harness owns Yoke management direction, reuse decisions, verification, and authorized
  delivery coordination. Yoke owns the generic shared sources, plugins, separately delivered common
  agents and commands, versioned delivery, and compatibility evidence.
- Consumers own their goals, data, local policy, adapters, and execution. Maintain the four-file
  Starter, Project Agent Kit with harness and required memory, optional public `mir` CLI,
  namespaced plugins, and retrievable reference corpus without requiring any channel.
- Finish when the affected supported-surface contracts, generated parity, and smallest relevant
  checks pass.

## Sources

- `starter/HARNESS.md`, `recipes/project-agent-kit/`, and `src/mir/cli/` own the minimum consumer contract, empty-target recipe, and optional installed CLI; the Kit never copies CLI code.
- `plugins/` owns common skills and the exact read-only global hook; `config/capability-sources.json` owns commit-pinned runtime selection.
- ADR-86, including its 2026-09-06 amendment, owns current purpose and management; ADR-79 controls platform lanes, and ADRs 81, 83-86, and 88-90 control adoption and capability boundaries.
- `config/template-assets.json` classifies the checkout; `.mir/repo-profile.toml` owns local boundaries.

- Yoke-only read-only SRR uses `"<user-bin>/mir"` with `--root "<yoke-checkout>"`; consumers use `MIR_SRR_PROVIDER` and `MIR_SRR_ROOT` with their own memory path.

## Authority and safety

- Mir Harness may manage Yoke directly within current user authority; `.mir/capability-lock.json` is
  managed, not protected. That responsibility does not give Yoke authority to manage consumers.
- Get explicit direction before destructive actions, credentials, consumer writes, commits, pushes,
  tags, releases, or material scope expansion.
- Preserve unrelated local changes and keep public material generic, English, and sanitized.
- Consumers own every result. Mir Yoke never discovers them, grants standing write authority, or
  provides an active `yoke` composer; installing `mir` does not expand authority.
- The Project Agent Kit recipe may describe target-local Git initialization and one commit only when
  the user's target prompt explicitly grants that authority.
- The Kit creates bounded project-owned files and SQLite+FTS5 memory. Its thin `scripts/mir.sh`
  executes the exact provider revision with runtime state below ignored `.mir/`, without vendoring
  the package or requiring a host-global installation.
- Plugins are optional; local skills must not shadow them, and ADR-82 stays inert. Agents and Claude
  commands use project sync or the user-runtime installer; Codex uses generated agents and mapped
  skills. ADR-90 admits only the global continuity hook; coupled hooks and MCP stay target-local.
- Edit canonical sources first and regenerate `AGENTS.md`, nested `AGENTS.md`, and `.codex/`.

## Execution and evidence

- Use direct work for bounded changes; scale design, delegation, and review with uncertainty.
- Run the smallest check that can fail for changed behavior.
- For Starter or recipe changes, run
  `uv run pytest -q tests/test_project_agent_kit.py tests/test_minimal_starter.py`.
- For CLI changes, include `tests/test_installed_cli.py` and the affected command regression.
- For plugin changes, run isolated package and common-contract tests.
- Use broader tests only when affected maintainer code or release coupling requires them.

Commands: `uv run pytest`, `uv run ruff check`, `uv run python scripts/verify_codex_sync.py`. Artifacts are English; user-facing language follows the user.

## Role policy (template summary)
```

</details>

<details>
<summary>Pre-consolidation AGENTS.md</summary>

```text
<!-- GENERATED FILE: edit CLAUDE.md and rerun scripts/generate_codex_derivatives.sh -->

# Mir Yoke — Harness-Managed Central Capability Supply Contract

Mir Yoke is the Harness-managed central capability supply system for independently owned repositories. It distributes versioned generic capability sources as a public agent-guided template,
not an agent runtime and not a universal installer, and has no standing authority over consumers.
`starter/` is the four-file payload; the Project Agent Kit is the greenfield recipe; installed `mir`
acts only on an explicit target and operation.

## Outcome and completion

- Mir Harness owns Yoke management direction, reuse decisions, verification, and authorized
  delivery coordination. Yoke owns the generic shared sources, plugins, separately delivered common
  agents and commands, versioned delivery, and compatibility evidence.
- Consumers own their goals, data, local policy, adapters, and execution. Maintain the four-file
  Starter, Project Agent Kit with harness and required memory, optional public `mir` CLI,
  namespaced plugins, and retrievable reference corpus without requiring any channel.
- Finish when the affected supported-surface contracts, generated parity, and smallest relevant
  checks pass.

## Sources

- `starter/HARNESS.md`, `recipes/project-agent-kit/`, and `src/mir/cli/` own the minimum consumer contract, empty-target recipe, and optional installed CLI; the Kit never copies CLI code.
- `plugins/` owns common skills and the exact read-only global hook; `config/capability-sources.json` owns commit-pinned runtime selection.
- ADR-86, including its 2026-09-06 amendment, owns current purpose and management; ADR-79 controls platform lanes, and ADRs 81, 83-86, and 88-90 control adoption and capability boundaries.
- `config/template-assets.json` classifies the checkout; `.mir/repo-profile.toml` owns local boundaries.

- Yoke-only read-only SRR uses `"<user-bin>/mir"` with `--root "<yoke-checkout>"`; consumers use `MIR_SRR_PROVIDER` and `MIR_SRR_ROOT` with their own memory path.

## Authority and safety

- Mir Harness may manage Yoke directly within current user authority; `.mir/capability-lock.json` is
  managed, not protected. That responsibility does not give Yoke authority to manage consumers.
- Get explicit direction before destructive actions, credentials, consumer writes, commits, pushes,
  tags, releases, or material scope expansion.
- Preserve unrelated local changes and keep public material generic, English, and sanitized.
- Consumers own every result. Mir Yoke never discovers them, grants standing write authority, or
  provides an active `yoke` composer; installing `mir` does not expand authority.
- The Project Agent Kit recipe may describe target-local Git initialization and one commit only when
  the user's target prompt explicitly grants that authority.
- The Kit creates bounded project-owned files and SQLite+FTS5 memory. Its thin `scripts/mir.sh`
  executes the exact provider revision with runtime state below ignored `.mir/`, without vendoring
  the package or requiring a host-global installation.
- Plugins are optional; local skills must not shadow them, and ADR-82 stays inert. Agents and Claude
  commands use project sync or the user-runtime installer; Codex uses generated agents and mapped
  skills. ADR-90 admits only the global continuity hook; coupled hooks and MCP stay target-local.
- Edit canonical sources first and regenerate `AGENTS.md`, nested `AGENTS.md`, and `.codex/`.

## Execution and evidence

- Use direct work for bounded changes; scale design, delegation, and review with uncertainty.
- Run the smallest check that can fail for changed behavior.
- For Starter or recipe changes, run
  `uv run pytest -q tests/test_project_agent_kit.py tests/test_minimal_starter.py`.
- For CLI changes, include `tests/test_installed_cli.py` and the affected command regression.
- For plugin changes, run isolated package and common-contract tests.
- Use broader tests only when affected maintainer code or release coupling requires them.

Commands: `uv run pytest`, `uv run ruff check`, `uv run python scripts/verify_codex_sync.py`. Artifacts are English; user-facing language follows the user.

## Role policy (template summary)
```

</details>

<details>
<summary>Pre-consolidation tasks/plan.md</summary>

```text
# Plan

## Current status — completed and published (2026-09-06)

- Authority: `tasks/intent.json` records the current Yoke purpose and management alignment. Parent
  Harness cursor `tasks/plan.md` run `harness-managed-central-provider-mandate-2026-09-06` is the
  overall design authority.
- [x] Preserve the published central capability implementation and its 987-test clean-candidate
  evidence at `0d5501fb765e7a829d3aec7ff64fa591f226f0d9`.
- [x] Record the superseding Yoke intent and preserve the previous cursor in the evidence archive.
- [x] Amend the current purpose/authority sources and maintain public-template distribution,
  supported-channel, and consumer-ownership boundaries.
- [x] Regenerate canonical derivatives and adopter payload after documentation stabilizes, then pass
  focused purpose, authority, adopter-boundary, asset, and parity verification: 52 tests passed;
  Codex derivative, asset classification, Ruff, and diff checks passed. The current and legacy
  Yoke contract titles both remain provider-identity markers. Log:
  `/tmp/mir-yoke-purpose-alignment-postdocs.log`.

Published implementation `f6d3f9a4949cfe19785d37ab952bf8f699d51802` has verified local/origin main parity.

## Current boundaries

- Retain the three role packages and one exact lifecycle package (14 skills total). Agents/commands remain separately delivered, and project policy/hooks/MCP remain target-owned.
- Source/config/path/digest/runtime checks remain fail-closed. Removed peer-required plugin names are a compatibility rejection, not an automatic migration.
- No live provider update/install, user trust change, capability-driven peer write, PR, workflow, tag or release was part of this repository repair.
- macOS remains the executed lane. WSL/native Windows and live model/hook execution are not claimed by these tests.

Before new work, compare `git rev-parse HEAD` with `git ls-remote origin refs/heads/main` and inspect the working tree.
```

</details>

<details>
<summary>Pre-consolidation tasks/checklist.md</summary>

```text
# Checklist

Historical evidence remains in `tasks/change_log.md`, `tasks/tdd.json` and Git history.

## Current purpose alignment

- [x] Record the Yoke purpose/management alignment in the active cursor and preserve the prior
  cursor in the evidence archive.
- [x] Align canonical purpose, authority, Profile, current ADR precedence, and supported-channel
  documentation without changing consumer interfaces or classification enums.
- [x] Regenerate derivatives and adopter payload after the final canonical wording, then pass
  focused purpose, authority, adopter-boundary, asset, and parity checks (52 focused tests;
  derivative, asset, Ruff, and diff checks passed;
  `/tmp/mir-yoke-purpose-alignment-postdocs.log`).

Prior capability implementation and publication evidence remains in `tasks/change_log.md` and Git
history. Recheck current local/remote revisions and dirty state before new work.
```

</details>

<details>
<summary>Pre-consolidation tasks/handoffs/session-handoff-LATEST.md</summary>

```text
# Session Handoff — Central Capability Supply Purpose Alignment

- Date: 2026-09-06.
- Status: completed and published.
- Intent authority: `tasks/intent.json`; `tasks/plan.md` is the current cursor. The Harness cursor run `harness-managed-central-provider-mandate-2026-09-06` owns the overall design.

## Decisions

Mir Yoke is the Harness-managed central capability supply system for independently owned repositories. Harness owns management direction, reuse decisions, verification and authorized delivery coordination. Yoke owns generic shared sources, plugins, separate common agents/commands, versioned delivery and compatibility evidence. Consumers retain goals, data, local policy, adapters and execution.

ADR-86's 2026-09-06 amendment controls this primary purpose and management split. Starter, Project Agent Kit, optional CLI and plugins remain supported; `public_harness_template` remains the distribution classification. New and legacy provider contract titles are recognized by adopter boundary checks.

## Verified Delivery

Implementation `f6d3f9a4949cfe19785d37ab952bf8f699d51802` was committed and pushed to origin/main with matching local/remote revisions. The parent observed 52 passing focused tests, exact payload parity, complete classification of 806 assets, generated Codex parity, Ruff and diff checks. Final policy/docs review has no blocker. For future delivery-record edits, regenerate the payload and verify its exact hashes before committing.

Detailed evidence and the prior capability/runtime proof remain in `tasks/change_log.md` and Git history. No live provider installation/update, consumer deployment, trust/credential/protected-memory change, PR or workflow was performed.

## Resume

No work remains for this mandate. Compare current local/remote main revisions and inspect the working tree before new work. Consumer ownership and explicit delivery authority remain intact.

<!-- mir:runtime-snapshot:begin -->
## Runtime Snapshot (Generated)

### Active Plan Items
- No open plan items.

### Working Tree
- Working tree dirty (11 paths; inspect git status --short).
<!-- mir:runtime-snapshot:end -->
```

</details>

<details>
<summary>Pre-consolidation tasks/intent.json</summary>

```text
{
  "goal": "Align Mir Yoke as the Harness-managed central capability supply system for independently owned repositories: make the primary purpose, management authority, supported adoption channels, consumer ownership boundaries, ADR precedence, maintainer Profile, operating documentation, contract tests, generated derivatives, and adopter payload consistent without changing interfaces, profile enums, runtime installations, consumer repositories, protected memory, credentials, or external services.",
  "goal_type": "maintenance",
  "scope": "Align only Yoke-owned purpose, management, supported-surface, and consumer-ownership documentation and metadata. Preserve the accepted capability repair, current source/digest/runtime boundaries, supported Starter/Project Agent Kit/optional CLI interfaces, and public_harness_template classification. Do not mutate live user runtimes, consumer repositories, protected memory, credentials, external services, code, schemas, or delivery state. Update canonical derivatives, task evidence, focused contract tests, and the generated adopter payload; prepare the bounded Yoke result for authorized delivery after verification.",
  "priority": "normal",
  "updated": "2026-09-06",
  "history": [
    {
      "goal": "Complete and deploy Yoke-owned role plugins so Claude and Codex load the same common skills and read-only lifecycle hook globally, while agents and commands use a separate digest-bound user-runtime distribution path and repository-local definitions retain precedence.",
      "updated": "2026-09-04",
      "status": "superseded"
    },
    {
      "goal": "Audit and minimally repair Mir Yoke supported surfaces: plugin configuration and contract alignment, Claude/Codex generated parity, platform continuity documentation, installer and lock references, asset classification, current Profile and documentation consistency, and concrete runtime defects. Preserve the ADR-79 macOS-primary and Linux/WSL-compatible posture, with native Windows as a reference-adaptation lane; do not install into user runtimes or consumer repositories. Record evidence, run focused and full verification, and prepare the maintainer-owned result for direct main commit and push.",
      "updated": "2026-09-05",
      "status": "superseded"
    },
    {
      "goal": "Repair Mir Yoke central capability status and multi-consumer update architecture: make global provider health readable without a consumer-local configuration or enrollment, separate consumer-local integration state, and permit atomic provider version migration across registered consumers while preserving non-requesting consumer files and locks as pending local integration. Preserve capability trust, digest, identity, secret, path, runtime, and activation checks; update ADR-89, current documentation, tests, and generated adopter payload without user-runtime or consumer writes.",
      "updated": "2026-09-06",
      "status": "superseded"
    }
  ]
}
```

</details>

<details>
<summary>Pre-consolidation config/doc-size-guard.json</summary>

```text
[
  {"path": "CLAUDE.md", "max_lines": 65, "max_bytes": 4304, "label": "CLAUDE.md (startup invariants only; keep procedures on demand)"},
  {"path": "AGENTS.md", "max_lines": 67, "max_bytes": 4393, "label": "AGENTS.md (generated shared startup contract)"},
  {"path": "tasks/plan.md", "max_lines": 800, "label": "tasks/plan.md"},
  {"path": "tasks/tdd.json", "max_lines": 20000, "label": "tasks/tdd.json (TDD ledger — run archiver when exceeded)"},
  {"path": "tasks/lessons.md", "max_lines": 600, "label": "tasks/lessons.md (generated projection)"}
]
```

</details>

### Architecture wording clarified

The Git authority condition already required by the canonical contract now appears in the supported flow. Previous wording:

4. It initializes Git locally only after verification, installs the tracked pre-commit hook, and
   creates one verified initial commit.

### Profile purpose contract repair

The pre-existing shortened purpose failed `test_public_template_identity.py:52`. Preserve it verbatim below; the active Profile retains its meaning and restores the tested ADR-86 identity phrase. No bootstrap receipt exists in this provider checkout; the existing template-maintainer bootstrap exemption applies. No receipt or runtime was changed.

```toml
purpose = "Harness-managed central capability supply for independent repositories: Starter, Project Agent Kit recipe, optional CLI, plugins, and versioned Claude/Codex delivery evidence."
```

### Memory projection before regeneration

The previous generated block is preserved below; the current projection is generated by `mir memory render`.

```text

## Keyword → File Index (DB projection)

| Keyword | File | Title |
|---|---|---|
| (no ingested documents) | — | — |
```

## 2026-09-23: Fleet consolidation audit evidence

Authority: owner Discord message 1552179237325377586 relayed by Mir Harness; repository-only.
The design authority is the current `tasks/plan.md` cursor backed by `tasks/intent.json`.
ADR-86 purpose and consumer boundaries remain accepted. No commit, push, tag, stash, reset,
checkout, release, consumer write, secret access or direct database edit was performed.

### Owner items

1. Consistency: Profile paths all exist. Restored the tested purpose phrase, checked references,
   regenerated derivatives in a temporary root and refreshed the exact adopter payload.
2. Operating base: inspected hook registration and maintainer scripts. No justified dead safety
   gate removal was found; the missing receipt limits the target launcher in this provider checkout.
3. Current facts: updated cursor, status, resume pointer, purpose wording and the memory projection;
   historical publication claims remain in their original wording in the log.
4. Archival: previous instructions, intent, cursor, checklist and handoff are preserved verbatim
   above with pointers in their current surfaces. No rule, decision or lesson was deleted.
5. Context: root instructions now contain startup invariants and short verification commands;
   the repository-only SRR invocation is on demand in the preserved input. One active cursor remains.
6. Memory: `.mir/memory.db` is 348160 bytes. Immutable read-only SQLite `pragma quick_check`
   returned `ok`. Ordinary `sqlite3 -readonly` could not open it; no unsupported cause is asserted.
   `mir memory doctor --project-root . --json` returned `not_ready` because `harness_a.toml` is
   absent. This pre-existing provider configuration was not replaced with a new consumer runtime.
   Documented `memory query` returned the SRR title; `memory render` refreshed the projection.
7. Constraints: raw-exec and secret-path hook regressions passed. Bootstrap and receipt guards,
   protected paths, preservation rules and destructive-action boundaries remain unchanged.
8. Skills/agents: isolated plugin/common-contract checks and agent registry checks passed.
   No repository Codex model pins exist. No plugin skill behavior or central capability changed.
9. Instructions: CLAUDE.md 59 lines / 4219 bytes -> 41 / 3448; AGENTS.md 61 / 4308 -> 43 / 3537.
   The generated body matches the canonical source; enforced budgets are now 55/3600 and 60/3800.
10. Rules/lessons: rules stay canonical in CLAUDE.md and generated into AGENTS.md; the existing
    lesson projection remains the lesson location. No populated duplicate lesson store was found.
11. Architecture: supported modules match the checkout; the Kit Git step now repeats its existing
    explicit-authority condition so the flow cannot imply unconditional commit permission.
12. Routing: the pre-existing executor uses app-server; its code and tests remain untouched.
    The central policy overlay resolves unit work to gpt-6-luna/high. Local route fields are null,
    so they introduce no competing pins. Accepted transport wording remains an owner decision below.
13. Continuity: one cursor (`tasks/plan.md`), resume pointer (`tasks/handoffs/session-handoff-LATEST.md`),
    status projection (`tasks/checklist.md`) and evidence log (this file).
14. Retrieval: the file-anchor implementation query had no edges. The declared requirement anchor
    `SRR-MEMORY-RELATIONS` returned four implementation edges, including the CLI and memory-reader
    files. `context pull "central capability supply"` returned architecture references but no
    facts/chunks and reported no configured archives; task retrieval is only partially populated.
15. Efficiency: observed repository SessionStart output was 946 bytes (existing 10240-byte cap);
    the shared continuity hook prints 94 bytes. Combined root instructions fell by 1542 bytes.
    Large historical and spec-reference documents remain on demand, not startup input.

### Observed verification

- Focused instruction, identity, authority, decision, adopter, classification, hook, continuity,
  intent, link, schema and sanitization suite: 95 passed in 16.03s.
- Isolated plugins, common skill contracts, routing policy and the pre-existing app-server/client,
  dispatch and shim regressions: 214 passed in 35.80s. No live model was invoked.
- Codex derivative verification passed; temporary generation differs in no `.codex/` file.
- Context paths: 9 files and 60 references passed. Agent management checks passed.
- Harness consistency passed with zero errors and zero warnings after documented projection render.
- Ruff and `git diff --check` passed. DB quick_check passed. Memory doctor remains not ready as above.
- Initial generator/hook failures came from an inaccessible inherited uv cache. They disappeared
  with a task-local `UV_CACHE_DIR`. The remaining pre-existing Profile phrase failure was repaired
  while preserving its prior added line verbatim above. No introduced failure remains in these runs.
- The original dirty implementation, capability lock and untracked evaluation artifact were not
  edited. Original changed instruction/Profile lines remain in the current diff or verbatim archive.

### Owner decisions needed

ADR-69 currently requires Claude-to-Codex MCP delegation and an MCP-backed executor. ADR-85 also
names the supported MCP/native lane. The current owner direction requires the user-scope
`codex:codex-rescue` / `/codex:rescue` plugin with model/effort, and `codex app-server` for
`tools/mir_executor`; the existing dirty implementation already uses app-server. Under the owner's
explicit conflict rule, no accepted ADR or agent routing wording was overwritten. Authorize a
transport amendment before changing ADR-69/85 and the four affected maintainer agents
(main-orchestrator, executor-agent, codex-final-reviewer and pipeline-validator). The raw-exec ban
must remain intact. No delegated model run was attempted through the stale lane.

### Remaining limits and delivery

- `scripts/mir.sh` reports a missing bootstrap receipt. The provider's existing bootstrap gate
  recognizes its template-maintainer identity without a receipt; none was created or re-attested.
  The only Profile edit restores identity wording. No profile edit is awaiting orchestrator install.
- Memory doctor cannot prove a configured archive baseline; context facts/chunks were empty.
  SQLite vector support is absent and queries report FTS5-only mode. No configuration or DB schema
  mutation was attempted to disguise these limits.
- No `.codex/` installation is pending, and no plugin behavior was changed. Shared/runtime delivery,
  native Windows execution, live model execution and a full release gate were outside this audit.
- Prior local diffs and generator output are retained in
  a local temporary directory together with the consolidation test logs (paths redacted for the public surface).

## 2026-09-23: Project-document cleanup preserved inputs

### Pre-cleanup tasks/plan.md

```text
# Plan

## Fleet consolidation — bounded work complete (2026-09-23)

Authority: `tasks/intent.json`; owner Discord message 1552179237325377586 relayed by Mir Harness.
This is repository-only maintenance under ADR-86; its accepted purpose and consumer boundaries remain binding.
The completed prior cursor is preserved verbatim in `tasks/change_log.md` under the 2026-09-23 preserved inputs.

- [x] Capture initial dirty state and preserve prior instructions, intent and continuity records.
- [x] Audit the 15 owner items against actual paths, documented commands and accepted decisions.
- [x] Minimize startup instructions without losing rules; regenerate into a temporary output root.
- [x] Run focused governance, documentation, safety, memory and relation checks; classify failures.
- [x] Record final evidence, remaining owner decisions and generated files for orchestrator installation.

No commit, push, tag, stash, reset, checkout, credential access, consumer write, release or direct DB edit.
Keep one cursor here, one resume pointer in `tasks/handoffs/session-handoff-LATEST.md`, one status
projection in `tasks/checklist.md`, and one evidence log in `tasks/change_log.md`.

Accepted transport decisions still need owner adjudication; see the 2026-09-23 audit evidence in
`tasks/change_log.md`. Memory readiness is reported, not claimed. No publication is authorized.
```

### Pre-cleanup tasks/checklist.md

```text
# Checklist

Status projection for `tasks/plan.md`; it is the only active cursor.

- [x] Complete the repository-only 15-item consolidation audit and bounded repairs.
- [x] Preserve prior edits and moved text; verify instruction budgets and generated parity.
- [x] Record passing checks, memory limitations and the unresolved transport decision in `tasks/change_log.md`.

Previous checklist: `tasks/change_log.md`, 2026-09-23 preserved inputs.
No release or consumer deployment was performed. Resume through `tasks/handoffs/session-handoff-LATEST.md`.
```

## 2026-09-23: Project-document cleanup evidence

Authority: owner Discord message 1552197111624372339 relayed by Mir Harness; `tasks/intent.json` is the cursor authority. The completed fleet consolidation pass above was not repeated.

### Preserved predecessor records

Pre-cleanup `tasks/intent.json` scope (verbatim):

```text
Repository-only governance and continuity maintenance. Preserve all pre-existing edits and accepted decisions; archive moved text verbatim. No commits, pushes, tags, stash, reset, checkout, secrets, direct database edits, live runtime installs or consumer writes. Generate derivatives in a temporary root; leave .codex installation to the orchestrator.
```

Pre-closeout `tasks/plan.md` (verbatim):

```text
# Plan

## Project-document cleanup (2026-09-23)

Authority: `tasks/intent.json`; owner Discord message 1552197111624372339 relayed by Mir Harness.
The completed fleet consolidation cursor is preserved verbatim in `tasks/change_log.md` under
"Project-document cleanup preserved inputs". ADR-86 and the owner decisions in that log still govern.

- [x] Audit the current spec snapshot and document entry points against the supported surfaces.
- [x] Index every ADR with its recorded status and successor where one is known.
- [x] Align the architecture and README navigation without changing product behavior.
- [ ] Run document/reference/size/spec checks, document-pinning tests and the full suite if reasonable.
- [ ] Record evidence, remaining owner decisions and generated-file installation needs in the log.

No commit, push, tag, stash, reset, checkout, credential access, consumer write, release or direct DB edit.
Keep one cursor here, one resume pointer in `tasks/handoffs/session-handoff-LATEST.md`, one status
projection in `tasks/checklist.md`, and one evidence log in `tasks/change_log.md`.
```

Pre-closeout `tasks/checklist.md` (verbatim):

```text
# Checklist

Status projection for `tasks/plan.md`; it is the only active cursor.

- [x] Audit current spec and supported document entry points.
- [x] Complete the decision-record index and document navigation.
- [ ] Verify references, sizes, spec, relevant tests and the full suite.
- [ ] Record owner decisions and residual risks in `tasks/change_log.md`.

Previous checklist: `tasks/change_log.md`, 2026-09-23 project-document cleanup preserved inputs.
No release or consumer deployment is authorized. Resume through `tasks/handoffs/session-handoff-LATEST.md`.
```

Pre-closeout `tasks/handoffs/session-handoff-LATEST.md` (verbatim):

```text
# Session Handoff — Fleet Consolidation

Resume pointer: `tasks/plan.md` is the only active cursor; `tasks/intent.json` records owner authority.
Status is projected in `tasks/checklist.md`; detailed evidence and verbatim prior records live in
`tasks/change_log.md` under 2026-09-23. The bounded consolidation is complete.

Before follow-up, inspect current dirty state and the remaining owner transport decision in that
log. Preserve the pre-existing app-server implementation and recovery stash. Do not infer delivery,
runtime installation, consumer-write or memory-reconfiguration authority from this handoff.
There are no differing `.codex/` files to install. The provider has no bootstrap receipt to re-attest.

Prior resume text is preserved verbatim in the 2026-09-23 evidence log.

<!-- mir:runtime-snapshot:begin -->
## Runtime Snapshot (Generated)

### Active Plan Items
- No open plan items.

### Working Tree
- Working tree dirty (22 paths; inspect git status --short).
<!-- mir:runtime-snapshot:end -->
```

### Result

- `spec/STATE.md` and `spec/index.yaml` already identify the complete v0.8 automation tree as a superseded reference. No active PRD exists; ADR-83 remains the current support contract. No spec shard or accepted ADR body was rewritten.
- `docs/decisions/INDEX.md` now links all 71 local ADRs and mirrors their frontmatter statuses: 49 accepted, 14 superseded, 5 archived, 2 deferred, 1 rejected. ADR-82 points to ADR-83. The 13 superseded Mir Harness mirror summaries say they were retired but provide no numbered successor; the register records that uncertainty without inventing one.
- `README.md` and `ARCHITECTURE.md` now point to current architecture, decision, historical spec, active cursor and evidence log. The pre-existing architecture Git-authority clarification remains intact. The completed consolidation plan and checklist were moved verbatim into this log.
- No `.codex/` file differs or needs installation. The orchestrator-owned `config/adopter-payload.json` was not edited. Its generated inventory now differs only for seven edited document paths: `ARCHITECTURE.md`, `README.md`, `docs/decisions/INDEX.md`, `tasks/change_log.md`, `tasks/checklist.md`, `tasks/intent.json`, and `tasks/plan.md`. The orchestrator must regenerate it after this documentation pass.

### Checks and failure classification

- Document-focused pytest: 38 passed. `scripts/verify_context_paths.py` checked 8 files and 108 path references. `scripts/verify_codex_sync.py`, Ruff, document-size budgets and `git diff --check` passed.
- Full pytest: 1224 passed, 5 failed in 224.65 seconds. Two exact-adopter-payload tests fail because the seven document hashes changed and the owner-reserved generated inventory cannot be refreshed here; this is pending orchestrator installation.
- Two isolated install/greenfield tests fail while fetching PyPI packages because the current sandbox has no DNS/network access. The unchanged setup-wrapper test `test_receipt_cli_is_not_reused_after_locked_source_changes` fails because its fake `uv` marker is absent; it exercises `setup.sh` and temporary fixtures, none of the edited documents. Its exact upstream cause remains unevaluated.

### Owner decisions needed and risks

- The pre-existing ADR-69/ADR-85 transport conflict remains as recorded in the fleet consolidation evidence above. No accepted decision body or orchestrator-owned path was changed.
- The retired Mir Harness mirror ADRs do not identify numbered successors. Confirm the upstream mappings if those records must name successors; the current index explicitly marks them unrecorded.
- The document inventory needs an orchestrator-owned regeneration before the two payload equality tests can pass. Network-dependent tests need a network-capable environment, and the setup-wrapper failure needs separate diagnosis if it persists there.


## 2026-09-23 — Second-pass fleet re-verification

Owner-authorized repository-only second pass, relayed by the control plane. This extends the completed cleanup and preserves ADR-86 purpose; it grants no delivery or consumer authority. The single cursor is `tasks/plan.md`.

### Preserved predecessor continuity records

#### tasks/plan.md

````text
# Plan

No active repository document cleanup remains. The completed 2026-09-23 plan and verification
record are preserved verbatim in `tasks/change_log.md` under "Project-document cleanup evidence".
`tasks/intent.json` records the owner instruction. The orchestrator-owned adopter payload refresh
and unresolved owner decisions are listed once in that log.
````

#### tasks/checklist.md

````text
# Checklist

Status projection for the single `tasks/plan.md` cursor: document cleanup is complete.
The check results, pending orchestrator payload refresh and owner decisions are recorded in
`tasks/change_log.md` under "Project-document cleanup evidence".

Previous checklist text is preserved verbatim in that log. No release or consumer deployment was performed.
````

#### tasks/handoffs/session-handoff-LATEST.md

````text
# Session Handoff — Project-document cleanup

Resume pointer: `tasks/plan.md` is the only cursor; `tasks/intent.json` records owner authority.
The cleanup and verification evidence, preserved predecessor records, pending adopter payload refresh,
and unresolved owner decisions live in `tasks/change_log.md` under 2026-09-23.

The orchestrator owns `config/adopter-payload.json` and must refresh the seven changed document
hashes before its exact-inventory tests can pass. No `.codex/` file differs. Preserve the pre-existing
dirty implementation, protected files, recovery stash and worktrees. Do not infer release, consumer
write, runtime installation or memory-reconfiguration authority from this handoff.

Prior resume text is preserved verbatim in the evidence log.

<!-- mir:runtime-snapshot:begin -->
## Runtime Snapshot (Generated)

### Active Plan Items
- No open plan items.

### Working Tree
- Working tree dirty (26 paths; inspect git status --short).
<!-- mir:runtime-snapshot:end -->
````

#### tasks/intent.json

````text
{
  "goal": "Clean up Mir Yoke project documents under owner Discord message 1552197111624372339 (2026-09-23): align the current documentation entry points and decision index with the supported surfaces, keep one active plan, preserve historical text and existing work, and verify document references and tests without changing behavior or delivery state.",
  "goal_type": "maintenance",
  "scope": "Repository-only PRD/spec, architecture/decision-index, plan/checklist, README and document-index cleanup. Preserve all pre-existing edits and accepted decision bodies; archive moved text verbatim. Do not edit orchestrator-owned paths, behavior, configuration values, generated projections, secrets, memory databases, recovery stash or worktrees. No commits, pushes, tags, stash, reset, checkout, releases, runtime installs or consumer writes.",
  "priority": "normal",
  "updated": "2026-09-23",
  "history": [
    {
      "goal": "Consolidate this Mir Yoke checkout under owner Discord message 1552179237325377586 (2026-09-23): audit the 15 fleet items, preserve ADR-86 purpose and all safety boundaries, minimize startup context, verify generated parity and read-only memory/relation health, and report remaining owner decisions without delivery or consumer writes.",
      "updated": "2026-09-23",
      "status": "complete"
    },
    {
      "goal": "Audit and minimally repair Mir Yoke supported surfaces: plugin configuration and contract alignment, Claude/Codex generated parity, platform continuity documentation, installer and lock references, asset classification, current Profile and documentation consistency, and concrete runtime defects. Preserve the ADR-79 macOS-primary and Linux/WSL-compatible posture, with native Windows as a reference-adaptation lane; do not install into user runtimes or consumer repositories. Record evidence, run focused and full verification, and prepare the maintainer-owned result for direct main commit and push.",
      "updated": "2026-09-05",
      "status": "superseded"
    },
    {
      "goal": "Repair Mir Yoke central capability status and multi-consumer update architecture: make global provider health readable without a consumer-local configuration or enrollment, separate consumer-local integration state, and permit atomic provider version migration across registered consumers while preserving non-requesting consumer files and locks as pending local integration. Preserve capability trust, digest, identity, secret, path, runtime, and activation checks; update ADR-89, current documentation, tests, and generated adopter payload without user-runtime or consumer writes.",
      "updated": "2026-09-06",
      "status": "superseded"
    },
    {
      "goal": "Align Mir Yoke as the Harness-managed central capability supply system for independently owned repositories: make the primary purpose, management authority, supported adoption channels, consumer ownership boundaries, ADR precedence, maintainer Profile, operating documentation, contract tests, generated derivatives, and adopter payload consistent without changing interfaces, profile enums, runtime installations, consumer repositories, protected memory, credentials, or external services.",
      "updated": "2026-09-06",
      "status": "superseded"
    }
  ]
}
````

### Preserved superseded runtime guidance

The ADR-69/85 transport amendment already authorizes the plugin/app-server route. These replacements update operational guidance without changing accepted decisions or safety guards. Compatibility class and function names remain unchanged.

#### .claude/agents/main-orchestrator.md

````text
- Match trigger table (CLAUDE.md) → Read matching skills (max 3) → one-line report.
See CLAUDE.md "Orchestration Presets" table (single source of truth).
2. If `execution_backend: codex`, use the supported MCP/native lane when that agent is selected. Raw `codex exec` is banned. A missing preferred lane blocks only work that truly requires that protected or isolated route; safe bounded direct work may continue.
See CLAUDE.md "Role Policy (Template Profile)" and AGENTS.md `template:profile:role-policy` block for the binding policy contract. This section covers the per-agent declarative surface introduced by ADR-09.
- A missing preferred MCP lane is a lane limitation, not a task blocker when a safe direct, native, or manual path remains. Never use raw `codex exec` fallback.
- **Supported Codex MCP lane**:
  - When the current host exposes a Codex MCP lane, keep read-only investigation or review bounded
    and request its read-only sandbox mode.
    explicit routing fields when the active policy requires them. Repository custom-agent settings
    still take precedence when the runtime defines that behavior.
- User correction feedback → record pattern in tasks/lessons.md.
- New project knowledge → save to docs/{category}/ + update memory-map.md.
````

#### .claude/agents/executor-agent.md

````text
> **Codex Backend Dispatch Rule (ADR-18 §S2, amended by ADR-69/73)**: When this delegated agent is selected, use the MCP/native Codex lane and never raw `codex exec`. Delegation itself is proportional; bounded main work may stay direct.
Routing SoT: ADR-69 amends ADR-65. Raw `codex exec` is banned. When delegation is selected, use `mir_executor --dispatch`, MCP, or native read-only breadth according to the task. A missing preferred lane is not a task blocker when a safe bounded direct path remains.
`--codex-args` is a legacy option name; in `--dispatch` mode its positional prompt is sent to the MCP Codex backend, not to raw `codex exec`.
### Read-only / non-mutating work → MCP/native routing (nothing to merge)
Claude-main investigation/review uses the supported Codex MCP lane. Codex-main breadth uses only
MCP/native routes. If the selected lane is unavailable, report the lane limitation so the parent
  positional prompt and sends it to the MCP backend.
- **Verify Codex actually ran** by checking the JobRegistry status/result plus MCP dispatch artifacts.
  `${CODEX_HOME:-$HOME/.codex}`). If `codex --version` works in the shell, auth is set.
````

#### .claude/agents/codex-final-reviewer.md

````text
> **Codex Backend Dispatch Rule (ADR-85)**: This agent declares `execution_backend: codex`. When delegation is selected, use the supported MCP or native Codex collaboration operation exposed by the current host. Never invoke raw `codex exec`.
````

#### .claude/agents/pipeline-validator.md

````text
> **Codex Backend Dispatch Rule (ADR-85)**: This agent declares `execution_backend: codex`. When delegation is selected, use the supported MCP or native Codex collaboration operation exposed by the current host. Never invoke raw `codex exec`.
````

#### scripts/codex-shim.sh

````text
# MCP-backed clients honor CODEX_BIN when a shimmed Codex binary is required.
    _POLICY_MESSAGE="[codex-shim] raw 'codex exec' and 'codex e' are prohibited; use MCP-backed dispatch."
````

#### tools/mir_executor/tests/test_codex_shim.py

````text
        'use MCP-backed dispatch.\n'
````

#### tools/mir_executor/executor.py

````text
        """Run Codex through the MCP backend (blocking).

        Maps the MCP response into the existing SubprocessResult contract.
````

#### Additional stale invocation text

The design skill absorbs deep-interview. The raw-exec guard keeps the same condition and exit status; only its route hint changes. Prior lines:

````text
**0 signals** → load deep-interview skill → ambiguity gating.
    block "raw codex exec/e is banned — route through MCP/mir_executor"
````

### Second-pass item results

1. Consistency: Profile-declared paths exist; current references and root rule parity pass.
   Codex candidate parity passes, with four sandbox-blocked agent derivatives awaiting installation.
2. Operating base: registered hook targets exist. Retained optional/reference hooks do not grant
   activation authority; no justified safety-gate removal was found. Stale transport hints were fixed.
3. Current facts: corrected agent invocation, missing section references, binary/auth distinction,
   generated-memory write guidance and obsolete continuity claims. Accepted ADR bodies stay unchanged.
4. Archival: all four predecessor continuity records and 24 replaced agent guidance lines were
   checked verbatim against HEAD in this log; current documents retain archive pointers.
5. Context: root instructions already meet budget. The single cursor remains tasks/plan.md;
   detailed evidence stays here on demand. No additional status or handoff document was created.
6. Memory: the 348160-byte database passes immutable read-only quick_check; 21 facts exist.
   Ordinary sqlite3 -readonly reports unable to open database (cause not established).
   Memory doctor fails with missing harness_a.toml. The Profile does not require the memory baseline;
   no consumer configuration was introduced. Documented dry-run renders match both existing projections.
7. Constraints: secret/protected-path, destructive-action, raw-exec, bootstrap and receipt tests
   remain intact. A pre-existing setup test tried the real host data directory before its fake uv;
   XDG_DATA_HOME now points to its temporary fixture. The same assertions pass without guard changes.
8. Skills/agents: isolated plugin/common-contract checks, registry checks and strict parsing of
   all four changed agents pass. No local duplicate skills or Codex model pins were introduced.
9. Instructions: unchanged CLAUDE.md = 41 lines / 3448 bytes; AGENTS.md = 43 / 3537.
   Both before and after satisfy 55/3600 and 60/3800; generated root body equals the source.
10. Rules/lessons: corrected the orchestrator to use documented memory commands and render lessons
    and memory-map projections. No lesson, safety rule or accepted decision was deleted.
11. Architecture: supported Starter, recipe, CLI, plugin, agent/command and reference boundaries
    match the checkout. No architecture rewrite was needed.
12. Routing: applied the already accepted ADR-69/85 amendment to the four operational agent
    contracts and route hints. The central policy overlay resolves unit work to gpt-6-luna/high;
    local null routing fields inherit policy. Compatibility CodexMcp* API names remain unchanged.
13. Continuity: one cursor, one resume pointer, one status projection and one evidence log remain.
    The canonical pre-compact generator refreshes the handoff's managed runtime snapshot.
14. Retrieval: memory-backed SRR-MEMORY-RELATIONS returns four implementation edges, including
    src/mir/core/memory_relations.py and src/mir/cli/relations.py. Context pull returns relevant
    architecture/verification anchors but no facts or chunks because no archives are configured.
    The historical spec graph does not contain that SRR anchor; no graph was synthesized.
15. Efficiency: current repository SessionStart emits 551 bytes; the shared continuity hook emits
    94 bytes. Large evidence, TDD and historical documents remain on demand. Root sizes are unchanged.

### Second-pass verification and failure classification

- Full final suite: 1226 passed, 3 failed in 203.46 seconds.
- Focused generator, isolated plugin/common-contract, public-surface/sanitization, links, payload,
  release-evidence, release metadata, startup, safety guards and shim suite: 166 passed.
- Setup isolation regression: observed failure with a host-directory permission error, then 1 passed
  after the fixture-only change. The full final suite also passes that test.
- The first full run overlapped the diagnostic-text edit after pytest had imported its old expectation,
  producing 8 transient shim mismatches; the final full run passes all 8. They are not pre-existing defects.
- Two final failures are pre-existing environment limitations: test_greenfield_slim_integration and
  test_installed_cli cannot download required PyPI packages because DNS/network access is unavailable.
  Their test files and production paths were not changed; the same failures appeared in the initial run.
- One final failure is caused by these authorized agent-source edits: the capability-lock test requires
  both committed-source hashes and working-source hashes to match. All existing committed-source hashes
  still verify, but the four edited agents differ. ADR-85 requires committed-source binding, while this
  turn forbids commits. The lock and its test were not weakened or given fabricated provenance.
- Worktree verify_codex_sync reports exactly the four pending agent derivatives below. A temporary
  tracked-source copy with generated output installed passes the same verifier. Non-Codex generator
  outputs are byte-identical; nothing needed copying back. Root and nested generated files are intact.
- Ruff, context paths (9 files / 69 references), document-size budgets, agent registry, strict agent
  frontmatter and harness consistency (0 errors / 0 warnings) pass. git diff --check passes.
- The adopter payload is regenerated after tracked documentation changes. Final closing checks
  are run again after recording this evidence and generating the handoff snapshot.

### Second-pass delivery and owner boundaries

Pending generated installation (re-run scripts/generate_codex_derivatives.sh in an authorized environment):

- .codex/agents/codex-final-reviewer.toml
- .codex/agents/executor-agent.toml
- .codex/agents/main-orchestrator.toml
- .codex/agents/pipeline-validator.toml

The temporary generated output and command logs are retained outside the checkout for the orchestrator;
no host-specific absolute path is added to public files. After installing derivatives, regenerate the
adopter payload. Capability-lock binding requires a separately authorized commit containing the source
changes, followed by the repository's normal committed-source binding process and lock verification.

No Profile edit or bootstrap re-attestation is pending. No new ADR policy decision is needed for the
transport corrections: amendment A1 already settled it. The prior uncertainty about unnumbered
successors for 13 retired mirror ADRs remains historical and was not resolved by guessing.
The remaining owner boundary is the no-commit instruction versus committed-source lock binding;
this pass preserves both and leaves that delivery action to the orchestrator. Live model execution,
runtime installation, network-dependent acceptance, commits, tags and releases were not performed.

Orchestrator acceptance (2026-09-23): the four `.claude/agents/*.md` wording edits and their
`.codex/agents/*.toml` derivatives were withheld from the local commit because the capability lock
binds agent bytes to a published source commit, which requires release authority. The replaced lines
listed above remain the current agent text until that release. The adopter payload was regenerated
and the full suite passed (1,229).


## Twenty-item repository maintenance re-verification (2026-09-23)

Owner-authorized repository-only re-verification and minimal improvements. The active intent authority is `tasks/intent.json`; the sole cursor is `tasks/plan.md`. No delivery or runtime authority is added.

### Preserved predecessor continuity records

#### tasks/plan.md

````text
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

````

#### tasks/intent.json

````text
{
  "goal": "Re-verify and minimally fix all 15 owner fleet audit items in this repository only under the owner-authorized second pass of 2026-09-23. Preserve accepted decisions, safety gates, historical text and user work; validate actual commands and generated parity; report sandbox-only installation gaps without committing or delivering changes.",
  "goal_type": "maintenance",
  "scope": "Repository-only second-pass audit and minimal fixes. No commits, pushes, tags, stash, reset, checkout, user-work deletion, credentials, consumer writes, runtime installation or direct database mutation. Generated files change only through repository generators; sandbox-blocked Codex derivatives are staged outside the checkout for the orchestrator.",
  "priority": "normal",
  "updated": "2026-09-23",
  "history": [
    {
      "goal": "Repair Mir Yoke central capability status and multi-consumer update architecture: make global provider health readable without a consumer-local configuration or enrollment, separate consumer-local integration state, and permit atomic provider version migration across registered consumers while preserving non-requesting consumer files and locks as pending local integration. Preserve capability trust, digest, identity, secret, path, runtime, and activation checks; update ADR-89, current documentation, tests, and generated adopter payload without user-runtime or consumer writes.",
      "updated": "2026-09-06",
      "status": "superseded"
    },
    {
      "goal": "Align Mir Yoke as the Harness-managed central capability supply system for independently owned repositories: make the primary purpose, management authority, supported adoption channels, consumer ownership boundaries, ADR precedence, maintainer Profile, operating documentation, contract tests, generated derivatives, and adopter payload consistent without changing interfaces, profile enums, runtime installations, consumer repositories, protected memory, credentials, or external services.",
      "updated": "2026-09-06",
      "status": "superseded"
    },
    {
      "goal": "Clean up Mir Yoke project documents under owner Discord message 1552197111624372339 (2026-09-23): align the current documentation entry points and decision index with the supported surfaces, keep one active plan, preserve historical text and existing work, and verify document references and tests without changing behavior or delivery state.",
      "updated": "2026-09-23",
      "status": "complete"
    }
  ]
}

````

#### tasks/handoffs/session-handoff-LATEST.md

````text
# Session Handoff — Second-pass re-verification

Resume pointer: `tasks/plan.md` is the only cursor; `tasks/intent.json` records authority.
Evidence and predecessor records: `tasks/change_log.md`, "Second-pass fleet re-verification".
Verified changes are committed locally; the four agent-source wording edits were withheld until the
next authorized release can bind them in the capability lock. No push, tag, release or consumer write.

<!-- mir:runtime-snapshot:begin -->
## Runtime Snapshot (Generated)

### Active Plan Items
- No open plan items.

### Working Tree
- Working tree clean.
<!-- mir:runtime-snapshot:end -->

````

#### tasks/checklist.md

````text
# Checklist

Status projection for the single `tasks/plan.md` cursor: all 15 audit items were checked.
Local fixes and verification are complete and committed; the withheld agent-source edits (next
authorized release, with lock binding) and two network-dependent tests remain open.
Details and preserved predecessor text: `tasks/change_log.md`, "Second-pass fleet re-verification".

````

### Preserved stale closeout guidance

The generated Claude and Codex registrations both include SessionEnd;
`tests/test_compact_lifecycle_hooks.py` asserts the respective 60s and 3s timeouts.
Prior `.ai-harness/session-closeout.md` text:

````text
Claude wires `.claude/hooks/session-end.sh` to `SessionEnd`. This template's Codex hook surface does
not have that event, so run the same script manually only when a Codex closeout is explicitly
requested.
````

### Bounded maintenance design

Authority: `tasks/intent.json`. Correct only the on-demand closeout document to match
the existing canonical hook configuration and executed lifecycle tests. Preserve its
old text above; change no event, timeout, guard, profile, released package or lock.
The predecessor audit is marked complete in intent history because its cursor and
orchestrator acceptance already record completion; this new request extends it to
the twenty-item checklist. No unresolved owner conflict is suppressed.

The earlier handoff claimed four agent-source corrections were still withheld.
Current HEAD already contains those corrections after the intervening 0.10.5 release;
the generated mirror and committed capability-lock tests are rechecked below.
The superseded handoff is retained above, not rewritten as historical fact.

### Twenty-item results and evidence

1. Consistency: done. Profile paths exist; context verifier checks 9 files / 69 references;
   source/derivative parity, registry and harness consistency pass. Context freshness still
   correctly identifies the historical Profile baseline as review_required; this audit does not
   invent a replacement attestation.
2. Operating base: no change needed. Registered hook targets exist. Retained optional hooks and
   inert reference surfaces do not imply activation; no justified safety-check removal was found.
3. Documents: done. Corrected the on-demand SessionEnd statement against canonical configuration
   and existing lifecycle tests; current continuity no longer repeats the pre-0.10.5 release hold.
4. Archiving: done. Four predecessor continuity files and replaced closeout guidance are preserved
   verbatim above, with live pointers. No rule, decision or lesson was deleted.
5. Context: no change needed. One plan cursor; large logs and historical specifications remain
   on demand. Root instruction documents remain within their stricter budgets.
6. Memory: partial. Immutable read-only quick_check returns ok; database 348160 bytes / 21 facts;
   no foreign-key errors or expired facts. Documented reconcile-missing --dry-run returns 0;
   both render projections match. Doctor reports missing harness_a.toml, as before; the provider
   Profile requires no memory baseline. No memory reconfiguration or direct mutation was performed.
7. Harness: done. Both runtimes register SessionEnd. Actual PreToolUse permits a safe read and
   rejects raw Codex exec and secret-path edits. Bootstrap/receipt and protected-path guards remain.
8. Skills and agents: no change needed. Plugin/common-contract tests pass; no local skills shadow
   plugins. All 12 generated agent TOMLs parse with no model pins. Current agent transport wording
   already uses the Codex plugin/native lane; compatibility CodexMcp API names are not MCP dispatch.
9. Instructions: unchanged before/after: CLAUDE.md 41 lines / 3448 bytes; AGENTS.md 43 / 3537.
   Generated root body equals the source; limits 55/3600 and 60/3800 pass.
10. Rules and lessons: no change needed. Existing canonical rule ownership is retained; lessons and
    memory-map match documented dry-run rendering. No competing policy or lesson store was added.
11. Architecture: no change needed. Starter, Kit recipe, optional CLI, plugins, separate agent and
    command delivery, and inert references match actual paths and public-surface contract tests.
12. Delegation: no change needed. Central overlay resolves Astra > Sol > Luna, unit=Luna/high,
    default=Sol/medium; no model pin or extra delegation layer was introduced. App-server protocol
    tests execute locally; no authenticated live model run is claimed.
13. Continuity: done. One cursor, resume pointer, status projection and evidence log are retained;
    the repository PreCompact generator refreshes the handoff runtime snapshot.
14. Work context: done. Context pull returns relevant architecture anchors; archives are unconfigured,
    so facts/chunks are empty. Immutable SRR query returns four current implementation edges.
15. Token efficiency: no change needed. Actual SessionStart emits 551 bytes; shared continuity
    emits 94 bytes. Completed predecessor intent is marked complete using its recorded acceptance,
    preventing a false unfinished-intent advisory. No startup context expansion was added.
16. Test health: done with environment limits. All tracked tests lie under default tests/tools
    testpaths. A teardown regression had an unrelated 1-second process-start deadline: the full
    suite observed an initialize timeout, and an injected 1.2-second startup reproduced it before
    the fix. The same probe passes after restoring the normal client startup budget; all teardown
    assertions and kill timeout remain unchanged. Transport tests: 27 passed. Two new ancestor-path cases fail before the scan fix and pass after it; all 52 rule tests pass.
    Two installation tests still require PyPI access and therefore are not hermetic offline.
17. Code/security/dependencies: done with skipped online checks. The isolated full run exposed two scans that skipped all code when an ancestor directory
    was named tests. Both now apply the existing exclusion to repository-relative paths.
    Bounded transport and final-diff review found no further confirmed production defect. Public sanitization passes; no private
    absolute paths were found. The only credential-pattern hit is a synthetic security fixture in
    tests/test_capability_security.py. Direct runtime/dev dependency metadata uses MIT, BSD-3-Clause
    or Apache-2.0. Latest-version lookup fails with PyPI DNS errors; current vulnerability and
    transitive-license verification are not claimed. No dependency upgrade was made.
18. Integrity: done. Adopter payload is regenerated after tracked edits. Provider lock, Profile,
    plugin trees and receipts stay unchanged; only two maintainer scan conditions change. No integrity evidence needs rebind.
19. Runtime: done with live-runtime exclusions. All 17 shell hook entrypoints were invoked in an
    isolated fixture: 16 exit 0, PreToolUse rejects its missing bootstrap evidence as designed;
    missing-TDD warnings are advisory. Real-repository safe/blocked probes pass. The shared hook
    exits 0. Installed package and all plugins are 0.10.6; Codex CLI reports 0.156.0. Credential-backed
    live execution and runtime installation are outside this pass; no activation claim is made.
20. Historical pending item, closed 2026-09-24 by owner Tasks B and D below.
    Original record retained: one existing historical decision remains. Thirteen mirrored ADRs record
    retirement, but no numbered successor is recorded. Keep their retirement notes unless the
    owner supplies authoritative successor mappings; only a definitive historical mapping is
    blocked. No implementation change in this pass conflicts with an accepted ADR.

### Verification and failure classification

- First full run: 1227 passed / 4 failed. Two payload mismatches were caused by this pass's
  concurrent documentation updates; generation and frozen-state reruns resolve them. Two failures
  were PyPI DNS/network limitations in unchanged installation tests.
- Second frozen-state run: 1228 passed / 3 failed. The same two network failures plus an existing
  teardown test's initialize timeout. Its exact scheduling cause is unknown; the bounded slow-start
  reproduction establishes the unrelated startup-budget sensitivity. The test-only fix restores
  the existing 10-second initialization default; no production timeout or guard changes.
- An additional full rerun lost its shared pytest scratch directory mid-run: 378 passed,
  1 failed, 852 setup errors. FileNotFoundError identifies the missing directory; the removal
  cause is unknown and disk space was available. No code fix was inferred from that event.
  The final run uses a new dedicated --basetemp outside the shared pytest scratch tree.
- First isolated full run: 1227 passed / 4 failed: the two network failures plus two confirmed
  ancestor-path scan defects. Added two regression cases: 2 fail and 2 existing cases pass before
  the fix; all 52 rule tests pass after the two-line fix. Existing repository-local test exclusions
  remain intact; parent directory names no longer suppress production scanning.
- Final implementation-state full run: 2 failed, 1231 passed in 200.74s (0:03:20).
  Both remaining failures are PyPI DNS/network errors in test_greenfield_slim_integration.py and
  test_installed_cli.py. Their files and production paths are unchanged.
- Focused lifecycle/plugin/common/release-evidence checks: 83 passed. Document/payload/generator,
  schemas, links, sanitization and decision checks: 72 passed. Transport tests after the fix:
  27 passed; injected slow-start probe fails before and passes after.
- Ruff, context paths, agent registry, harness consistency (0 errors / 0 warnings), generated
  parity and git diff --check pass. Existing tests cover the documentation contract; two new scan regression cases fail
  without the fix and pass with it. Closing record edits are followed by payload regeneration and
  relevant payload/release-evidence checks.
- Temporary-root generator initially failed on the inaccessible default uv cache; retry with
  UV_CACHE_DIR in a writable temporary directory succeeds. Generated outputs are byte-identical:
  no non-Codex copy-back, Codex installation or Codex removal is required.

### Delivery boundary

No commits, pushes, tags, releases, dependency upgrades, consumer writes, runtime installation,
secret access or direct database writes. No pending Codex derivative installation/removal or
integrity rebind. The remaining operational limitations are offline installation acceptance and
online dependency intelligence; optional provider memory doctor remains not_ready as documented.
Only the historical ADR mapping decision in item 20 remains; the prior agent release hold is closed.

## Preserved predecessor continuity text (2026-09-24)

### tasks/plan.md

```markdown
# Plan

Twenty-item repository maintenance, 2026-09-23. `tasks/intent.json` is the intent authority.
Predecessor records and evidence: `tasks/change_log.md`, "Twenty-item repository maintenance re-verification".

- [x] Re-check all twenty items against files, runtime probes and read-only memory evidence.
- [x] Correct closeout guidance, teardown startup budget and repository-relative scan exclusions.
- [x] Verify full tests, governance, generator parity and adopter payload/release evidence.
- [x] Record results, environment limits and the existing historical owner decision.

Repository maintenance is complete within the authorized boundary. Two installation checks remain
limited by unavailable PyPI access. No delivery, Codex installation or integrity rebind is pending.
```

### tasks/checklist.md

```markdown
# Checklist

Status projection for the single `tasks/plan.md` cursor: all twenty maintenance items were checked.
Closeout guidance, teardown-test startup sensitivity and ancestor-sensitive scans are repaired. Two installation tests are
network-limited; online dependency checks are unavailable. Generated derivatives match.
Evidence, preserved predecessor text and the single historical owner decision are in
`tasks/change_log.md`, "Twenty-item repository maintenance re-verification".
```

### tasks/handoffs/session-handoff-LATEST.md

```markdown
# Session Handoff — Twenty-item repository maintenance

Resume pointer: `tasks/plan.md` is the only cursor; `tasks/intent.json` records authority.
Evidence and predecessor records: `tasks/change_log.md`, "Twenty-item repository maintenance re-verification".

Corrected SessionEnd guidance, a teardown test's startup deadline, and repository-relative scan exclusions.
Final full suite: 1231 passed, two PyPI DNS/network failures; the slow-start reproduction and
27 transport tests pass. No Codex installation/removal or integrity rebind is pending.
Next verification requires network access for the two installation tests and dependency intelligence.
The existing historical ADR-mapping decision is recorded once in the evidence log.
No commit, push, tag, release, runtime installation or consumer write was performed.

<!-- mir:runtime-snapshot:begin -->
## Runtime Snapshot (Generated)

### Active Plan Items
- No open plan items.

### Working Tree
- Working tree dirty (11 paths; inspect git status --short).
<!-- mir:runtime-snapshot:end -->
```

## Owner-authorized maintenance continuation (2026-09-24)

- Authority: renewed owner maintenance scope; `tasks/intent.json` and `tasks/plan.md`; initial tree clean at 9b1fde0.
- Items 1–5: profile/layout/contracts checked; predecessor cursor, projection and handoff preserved verbatim above; one current cursor remains.
- Items 6, 14: immutable quick_check ok, 348160 bytes, 21 facts, no FK errors, expired facts or missing sources; both memory projections match.
- Memory relation retrieval returned four implementation edges without notices; context pull returned architecture anchors. Optional doctor remains not_ready because harness_a.toml is absent.
- Item 7: fail closed on bootstrap, parser, path, required-validator and safety-regex errors; diagnostics omit command and validator bodies.
- Items 8–12: registry, instruction parity, canonical rules, architecture and central routing checked; no local shared-skill shadow or model pin introduced.
- Item 9 before/after: CLAUDE.md 41 lines / 3448 bytes; AGENTS.md 43 / 3537; unchanged and within limits.
- Items 13, 15: one cursor/resume/projection/log retained; SessionStart emits 550 bytes and the shared continuity hook 94 bytes.
- Item 16: all tests remain under default tests/tools collection; unrelated one-second startup limits removed after a 1.2-second delayed-handshake reproduction failed before and passed after.
- Item 17: Codex completion params/items and external capability-status JSON now validate types; malformed replies reject pending calls. No dependency upgrades.
- Items 18–19: temporary-root generation is byte-identical; no Codex install/removal. All 17 shell hooks exit 0 on isolated representative inputs; shared hook exits 0.
- Guard regressions: 38 new cases fail without their respective fixes; guard/deny suite 81 passed. Client regressions: 17 fail against preceding/original code; client suite 44 passed.
- Slim JSON regression: 5 failed before, 22 passed after. Advisory regressions: 6 failed before fixes; related suite 43 passed; template parity suite 6 passed.
- Independent review reproduced patch-extraction and Python-fallback defects; both repaired. Final safety-regex review accepted; no unresolved introduced defect reported.
- Frozen full run: 1300 passed / 2 failed in 365.99s. Both failures are unchanged test_greenfield_slim_integration.py and test_installed_cli.py PyPI DNS failures.
- Earlier runs: 1231/4 and 1284/4 pass/fail; concurrent edits caused payload/clean-room mismatches, and the compact template parity regression was repaired. Final frozen run clears these.
- Earlier focused run: 177 passed / 1 existing initialize-timeout failure; the test-only startup fix above resolves the reproduced sensitivity.
- Ruff, context references (9 files / 69 refs), agent registry, harness consistency (0 errors / 0 warnings), generator parity and diff checks pass.
- Dependency latest-version lookup failed on DNS; online vulnerability and transitive-license checks skipped. Direct installed package metadata reviewed; no private absolute-path matches found.
- Credential-pattern locations only (not proof of real credentials): docs/_archive/harness-engineering/applications/example-harness/phase-1-application-2026-06-13-historical.md; tests/test_adr53_phase3b_context_cli.py; tests/test_capability_security.py; tests/test_hook_executability.py.
- Runtime limits: general Bash writes do not expose edit paths to the post-edit scan; intended context output sites remain pre-compact.sh, compact-resume.sh and user-prompt-submit.sh. No credential-backed runtime activation exercised.
- Item 20 (historical; closed by owner Tasks B and D below): the sole historical successor-mapping decision remains in the prior twenty-item entry, item 20; retirement records are preserved and no successor is invented.
- Integrity: profile, receipts, capability lock and released plugin trees unchanged; adopter payload regenerated after tracked edits. No rebind or delivery required.
- No commits, pushes, tags, releases, consumer writes, secret access or direct database mutation.

## Owner Tasks B and D (2026-09-24)

Authority: owner Discord messages 1552352486801547415 (items 1–4) and
1552354384296411267 (lighter harness), relayed by Mir Harness. Scope: this repository
only; no delivery, re-attestation, secrets or direct memory writes.

### Superseded cursor (verbatim)

```markdown
# Plan

Owner-authorized maintenance re-verification, 2026-09-23–24, within this repository only.
`tasks/intent.json` remains the intent authority; the owner renewed the same scope.
Predecessor completion evidence: `tasks/change_log.md`, "Twenty-item repository maintenance re-verification".

- [x] Re-check twenty items, including output disclosure, guard errors, JSON types and hermetic tests.
- [x] Repair reproduced defects with failing regression tests, preserving released plugin bytes.
- [x] Run full tests, governance, temporary-root generation and payload/release evidence checks.
- [x] Record concise results, deferred work and owner decisions in the existing evidence log.

Verification and repairs are complete within scope. Full suite: 1300 passed; two unchanged
installation tests fail on PyPI DNS. Final record evidence: `tasks/change_log.md`,
"Owner-authorized maintenance continuation (2026-09-24)". No delivery or integrity rebind is pending.
```

### Historical profile enforcement region (verbatim)

Retired by the owner choice above. Safety behavior moves to the local guard; only
the redundant region and its code-path/dogfooding advisories are retired.

```bash
# --- Mir profile-driven enforcement (V2.2 — phase-2 scope + ADR-23 dogfooding exemption) ---
if [ "${MIR_FAMILY_CODE_PATHS_INITIALIZED:-no}" != "yes" ]; then
    MIR_FAMILY_SLUG="${MIR_FAMILY_SLUG:-your-harness}"
    MIR_FAMILY_CODE_PATHS=()
    _MIR_CODE_PATH_HELPER="$PROJECT_DIR/.claude/hooks/lib/code-path-config.py"
    if [ -f "$_MIR_CODE_PATH_HELPER" ]; then
        _mir_code_paths="$("$_MIR_PYTHON_LAUNCHER" "$_MIR_CODE_PATH_HELPER" \
                 --family "$MIR_FAMILY_SLUG" --check code-paths 2>/dev/null)" || {
            warn "code-path configuration inspection failed; using advisory defaults"
            _mir_code_paths=""
        }
        while IFS= read -r line; do
            [ -n "$line" ] && MIR_FAMILY_CODE_PATHS+=("$line")
        done <<< "$_mir_code_paths"
    fi
    [ "${#MIR_FAMILY_CODE_PATHS[@]}" -eq 0 ] && MIR_FAMILY_CODE_PATHS=( "tools/" "src/" )

    # ADR-23 dogfooding exempt check
    MIR_DOGFOODING_EXEMPT="no"
    if [ -f "$_MIR_CODE_PATH_HELPER" ]; then
        MIR_DOGFOODING_EXEMPT="$("$_MIR_PYTHON_LAUNCHER" "$_MIR_CODE_PATH_HELPER" \
                                --family "$MIR_FAMILY_SLUG" --check dogfooding-exempt 2>/dev/null)" || {
            warn "dogfooding advisory inspection failed; using advisory defaults"
            MIR_DOGFOODING_EXEMPT="no"
        }
    fi

    MIR_CODEX_DEFAULT_ENABLED="true"
    MIR_FAMILY_CODE_PATHS_INITIALIZED=yes
fi

_mir_path_matches_code_path() {
    "$_MIR_PYTHON_LAUNCHER" - "$1" "${MIR_FAMILY_CODE_PATHS[@]}" <<'PY'
import fnmatch
import os
import sys

path, *patterns = sys.argv[1:]
pwd = os.environ.get("PWD", "")
candidates = [path]
if pwd and path.startswith(pwd + "/"):
    candidates.append(path[len(pwd) + 1:])

def matches(candidate, pattern):
    if pattern.endswith("/"):
        return candidate.startswith(pattern) or ("/" + pattern) in ("/" + candidate + "/")
    return fnmatch.fnmatch(candidate, pattern.replace("**", "*"))

print("yes" if any(matches(candidate, pattern) for candidate in candidates for pattern in patterns) else "no")
PY
}

_mir_patch_path_safety_reason() {
    "$_MIR_PYTHON_LAUNCHER" - "$1" "$PROJECT_DIR" <<'PY'
import os
from pathlib import Path
import sys

raw_path, project_dir = sys.argv[1:]
root = Path(project_dir).resolve()
candidate = Path(os.path.expanduser(raw_path))
if not candidate.is_absolute():
    candidate = root / candidate
resolved = candidate.resolve(strict=False)
try:
    relative = resolved.relative_to(root).as_posix()
except ValueError:
    print("patch path outside project root")
    raise SystemExit(0)

parts = Path(relative).parts
if ".git" in parts:
    print("patch targets git internal state")
    raise SystemExit(0)

name = Path(relative).name
secret_names = {".env", "credentials", "id_rsa", "id_ed25519"}
if (
    name in secret_names
    or name.startswith(".env.")
    or name.startswith("credentials.")
    or name.endswith((".pem", ".key", ".p12"))
):
    print("patch targets a secret or credential file")
PY
}

_mir_tool_name="$TOOL_NAME"
if [ "$_mir_tool_name" = "Edit" ] || [ "$_mir_tool_name" = "Write" ]; then
    _mir_file_path="$FP"
    if [ -n "$_mir_file_path" ]; then
        _mir_file_safety_reason="$(_mir_patch_path_safety_reason "$_mir_file_path" 2>/dev/null)" || block "file path safety inspection failed"
        if [ -n "$_mir_file_safety_reason" ]; then
            echo "[PreToolUse BLOCK] $_mir_file_safety_reason: $_mir_file_path" >&2
            exit 2
        fi
        if [ "${#MIR_FAMILY_CODE_PATHS[@]}" -gt 0 ]; then
            _mir_match="$(_mir_path_matches_code_path "$_mir_file_path" 2>/dev/null)" || warn "code-path advisory inspection failed"
            if [ "$_mir_match" = "yes" ] && [ -z "${MIR_CODEX_SESSION_ID:-}" ] && [ "${MIR_CODEX_MAIN:-0}" != "1" ]; then
                echo "[mir ADVISORY] code-path edit on $_mir_file_path: consider the delegated lane when isolation, review independence, or parallelism justifies its cost; bounded direct-main edits are allowed." >&2
            fi
        fi
    fi
fi
if [ "$_mir_tool_name" = "apply_patch" ] || [ "$_mir_tool_name" = "ApplyPatch" ]; then
    _mir_patch="$(extract_json '.tool_input.command // .tool_input.input // .tool_input.patch // .tool_input.content | select(type == "string" and length > 0)')" || block "Malformed apply_patch payload"
    _mir_patch_paths="$(printf '%s\n' "$_mir_patch" | sed -nE \
        -e 's/^\*\*\* (Add|Update|Delete) File: (.*)$/\2/p' \
        -e 's/^\*\*\* Move to: (.*)$/\1/p')" || block "patch path extraction failed"
    while IFS= read -r _mir_patch_path; do
        [ -n "$_mir_patch_path" ] || continue
        _mir_patch_safety_reason="$(_mir_patch_path_safety_reason "$_mir_patch_path" 2>/dev/null)" || block "patch path safety inspection failed"
        if [ -n "$_mir_patch_safety_reason" ]; then
            echo "[PreToolUse BLOCK] $_mir_patch_safety_reason: $_mir_patch_path" >&2
            exit 2
        fi
        # ADR-87 follow-up: the safety reason above covers outside-root, git internals
        # and secret basenames, but not the deny-list. A patch could therefore add
        # secrets/prod.yaml, which protected-secrets-dir exists to stop.
        apply_deny_list "$_mir_patch_path" "path"
        _mir_match="$(_mir_path_matches_code_path "$_mir_patch_path" 2>/dev/null)" || warn "code-path advisory inspection failed"
        if [ "$_mir_match" = "yes" ] && [ -z "${MIR_CODEX_SESSION_ID:-}" ] && [ "${MIR_CODEX_MAIN:-0}" != "1" ]; then
            echo "[mir ADVISORY] code-path patch on $_mir_patch_path: consider the delegated lane when isolation, review independence, or parallelism justifies its cost; bounded direct-main edits are allowed." >&2
        fi
    done <<< "$_mir_patch_paths"
fi
# --- end Mir profile-driven enforcement (V2.2) ---

```

### Superseded index qualification (verbatim)

Mirrored summaries marked superseded say Mir Harness retired them but do not identify a
numbered successor. That missing mapping needs an owner decision before it can be asserted.

### B: behavior inventory and disposition

| Concern | Existing local behavior | Retired region contribution retained locally |
|---|---|---|
| Git internals | Raw `.git/config`, hooks, refs and objects check for file tools | Root-resolved `.git` at any path component for Edit/Write and patches |
| Secret basenames | Raw basename check for Edit/Write/NotebookEdit | Root-resolved basename checks for Edit/Write and patches, including symlink destinations |
| Outside root | Listed system prefixes block file tools | Every outside-root Edit/Write or patch target blocks; no outside-root advisory or exemption existed |
| Deny-list | File tools screen cwd-resolved relative paths | Patches keep their raw-path deny-list subject and rule reason; no pattern is removed |
| Protected paths | Secret/credential rules are literal and deny-list driven | No general profile protected-path loader existed in the region; no new profile policy is inferred |
| Memory/scratchpad | No dedicated exception | No exception existed; owner memory and scratchpad Write probes remain blocked |
| Parsing/errors | jq required; malformed JSON, missing paths, failed inspectors block | Non-string/empty patch and failed Add/Update/Delete/Move extraction or safety inspection still block |
| Redaction | Bash/validator contents omitted from block messages | Moved diagnostics use `block` with a fixed reason, never command or patch contents |

All file tools and both patch spellings now enter `screen_path_target`. The existing
root-based helper is retained within that local section to preserve its distinct
resolution semantics; NotebookEdit keeps its existing narrower checks. The removed
region never enforced family code-path ownership. Its initialization, matcher,
dogfooding probe and delegation advisory were advisory-only.

`rg` found no runtime readers of the removed initialized/code-path/dogfooding/default
variables outside the removed block. The remaining enabled-phases reader uses
`${MIR_FAMILY_SLUG:-your-harness}`, preserving the previous default without setup.
The standalone code-path helper and unrelated bluebrick/phase/contract advisories
remain unchanged. Removed unused tier declaration, preserved verbatim:

```bash
#   pre-tool-use/code-path-block  : tier=block  (your-harness BLOCK code path protection)
_MIR_HOOK_TIER_CODE_PATH="warn"
```

### D: authoritative successor resolution

Verified all 13 `superseded_by` fields in the Mir Harness archived copies named by
these records' `mirrors` fields. The complete mappings are now in
`docs/decisions/INDEX.md` and each corresponding ADR. Mir Harness ADR-06 explicitly
also names Mir Harness ADR-72 and Mir Harness ADR-73 in its supersession note;
Mir Harness ADR-23 points to Mir Harness ADR-41, whose archived field points to
Mir Harness ADR-76. No same-numbered Yoke decision is substituted.

The prior item 20 is closed under owner Discord 1552352486801547415 and
1552354384296411267 (2026-09-24), relayed by Mir Harness. Its original pending text
remains labeled historical. Tasks A/C were not assigned in this execution request.

### Verification evidence

- Before implementation, the updated retired-profile-advisory test and new compiler-marker
  regression both fail: 2 failed / 53 deselected. After implementation, hook and deny-list
  checks pass: 81 passed / 0 failed, including parser/extractor fail-closed and redaction cases.
- Bootstrap/decisions/governance/generation/classification/identity first run: 59 passed /
  1 failed. The failure is the stale adopter-payload digest after source edits;
  regenerate through `python -m tools.template_assets --write-adopter-payload` at closeout.
- Links, schemas and public surface/identity: 10 passed / 0 failed.
- Ruff, context paths (9 files / 69 references), repository agent management and Codex sync pass.
- Temporary-root Codex generation is byte-identical to every checked-in generated output;
  no extra Codex output exists and no `.codex` install or removal is needed.
- Real-repository probes before and after: 20/20 match the supplied baseline. Payloads only
  reach PreToolUse; no tested Bash command or file mutation executes. Probe-added invocation
  log suffixes are removed with prefix validation, preserving pre-existing log bytes.

| Case | Baseline | Before | After |
|---|---:|---:|---:|
| edit-src | 0 | 0 | 0 |
| write-readme | 0 | 0 | 0 |
| write-env | 2 | 2 | 2 |
| write-git | 2 | 2 | 2 |
| write-etc | 2 | 2 | 2 |
| write-outside | 2 | 2 | 2 |
| write-memory | 2 | 2 | 2 |
| write-scratch | 2 | 2 | 2 |
| write-secretsdir | 2 | 2 | 2 |
| nb-env | 2 | 2 | 2 |
| nb-src | 0 | 0 | 0 |
| patch-src | 0 | 0 | 0 |
| patch-env | 2 | 2 | 2 |
| patch-git | 2 | 2 | 2 |
| patch-outside | 2 | 2 | 2 |
| patch-secretsdir | 2 | 2 | 2 |
| bash-ls | 0 | 0 | 0 |
| bash-rmrf | 2 | 2 | 2 |
| bash-cat-env | 0 | 0 | 0 |
| malformed | 2 | 2 | 2 |

Bootstrap evidence changed: `.claude/hooks/pre-tool-use.sh`. Re-attestation belongs
to the Mir Harness orchestrator and was not performed. Profile, capability lock,
receipts, memory databases and released plugin bytes are unchanged. Owner B/D
implementation is complete; orchestrator clone remeasurement and re-attestation
remain external acceptance work. No commits, pushes, tags or consumer writes.

Final follow-up: after repository-owned payload regeneration, the same
bootstrap/decisions/governance/generation/classification/identity suite passes:
60 passed / 0 failed. Public sanitization passes; harness consistency reports
0 errors / 0 warnings. The payload changes only the 18 edited source-file hashes,
with identical file membership and classifications. Final record edits are followed
by regeneration and the focused payload/link/schema checks.


## Owner choice B orphan-helper follow-up (2026-09-24)

Authority: owner Discord 1552352486801547415 and 1552354384296411267, relayed
by Mir Harness. The follow-up section of `tasks/plan.md` is the active intent cursor.
Scope is this repository only. The prior B/D evidence above remains historical;
its statement that the standalone helper remains unchanged is superseded here.

### Changes and delivery

- Removed `.claude/hooks/lib/code-path-config.py`, the orphan reported by R8, and
  removed its construction from the retired-advisory test. Existing safety tests remain.
- Made the existing Codex generator tolerate an absent hook library and omit its
  mapping. Added a missing-source regression; the portable-copy test now supplies
  its own library fixture instead of depending on the retired production helper.
- Regenerated `.codex-sync/manifest.json` through the repository generator in a
  temporary output root. All other generated file bytes match the checked-in files.
- Regenerated `config/adopter-payload.json` through `tools.template_assets` against
  the candidate after applying generated removals. Both Claude and Codex helper
  entries are absent. No payload filtering or hand editing was used.
- Added an Unreleased entry in `CHANGELOG.md`, preserving the old introduction.
  Adopters no longer receive this helper or the profile enforcement block removed
  by owner choice B. Local safety guard behavior is unchanged.

Pending orchestrator application: delete `.codex/hooks/lib/code-path-config.py`
using the repository generator. The sandbox cannot modify `.codex/**`; its stale
copy remains in this working tree. Consequently the prepared payload describes
833 minus 1 = 832 candidate files, while the working tree still has 833 files.
This is a delivery dependency, not permission to suppress parity checks.

### Verification

- Before cleanup: existing `test_hook_file_reachability_real_repo_green` fails
  with the exact R8 orphan finding (1 failed).
- New missing-source generator regression before the fix: 1 failed, with
  `cp: .claude/hooks/lib: No such file or directory`. After the fix it passes.
- First focused run: 66 passed / 1 failed. The pre-existing portable-copy test
  assumed the retired production library existed; the independent fixture fixes
  that assumption without dropping its directory, symlink or digest assertions.
- Final hook, Codex generation, harness/governance, decisions, public surface,
  identity, links and schema tests: 153 passed / 0 failed.
- Candidate payload/classification/public tests: 10 passed / 0 failed. Candidate
  Codex sync passes. Working-tree Codex sync reports the expected portable-library
  drift until the orchestrator applies the generated deletion.
- The first candidate sync attempt could not download dependencies because PyPI
  DNS resolution failed. Retrying with the existing environment and UV_NO_SYNC=1
  passes; no dependency or environment policy was changed in the repository.
- Harness consistency: 0 errors / 0 warnings. Ruff, context paths (9 files /
  69 references), agent management, sanitization, links, schemas and diff checks pass.

### Task B probes versus the preserved baseline

These payloads are supplied only to PreToolUse; commands and edits are not executed.
The probe records stay in ignored runtime evidence. Nineteen direct probes match
the preserved baseline. The inline destructive-command probe was rejected by the
execution tool's own PreToolUse screening; an attempted temporary test-script patch
was also rejected as outside the project. Neither guard was bypassed. Existing
`test_should_redact_command_when_bash_guard_blocks` covers destructive command
blocking in the passing hook suite. That isolated test is not a twentieth direct probe.

| Case | BASELINE | Follow-up probe |
|---|---:|---:|
| edit-src | 0 | 0 |
| write-readme | 0 | 0 |
| write-env | 2 | 2 |
| write-git | 2 | 2 |
| write-etc | 2 | 2 |
| write-outside | 2 | 2 |
| write-memory | 2 | 2 |
| write-scratch | 2 | 2 |
| write-secretsdir | 2 | 2 |
| nb-env | 2 | 2 |
| nb-src | 0 | 0 |
| patch-src | 0 | 0 |
| patch-env | 2 | 2 |
| patch-git | 2 | 2 |
| patch-outside | 2 | 2 |
| patch-secretsdir | 2 | 2 |
| bash-ls | 0 | 0 |
| bash-cat-env | 0 | 0 |
| malformed | 2 | 2 |
| bash-rmrf | 2 | Not rerun directly; tool rejected the probe |

### Boundaries and remaining owner work

No declared bootstrap evidence changed in this follow-up (23 tracked evidence
files checked against starting hashes); no re-attestation is required by this pass.
The pre-existing `pre-tool-use.sh` edits and the orchestrator's SessionStart fix
remain intact. No memory commands, database edits, credential access, commits,
pushes, tags or consumer writes were performed. B's local helper cleanup is done;
D's earlier successor mapping remains closed. Owner A/C were not assigned here.
Only generated Codex deletion and the resulting parity/payload acceptance remain
with the orchestrator, in addition to any explicitly reported full-suite limits.

### Full-suite closeout

`UV_CACHE_DIR=/tmp/mir-yoke-followup-uv uv run pytest -q` completed with
1298 passed / 5 failed in 337.76 seconds:

- Two payload equality tests report the pending generated Codex removal; final
  payload regeneration and candidate checks below isolate the remaining mismatch
  to `.codex/hooks/lib/code-path-config.py`.
- `test_should_leave_minimal_starter_and_project_owned_changes_when_candidate_is_slimmed`
  cannot download PyYAML because files.pythonhosted.org DNS resolution fails.
- `test_should_run_copied_tool_when_repository_python_is_not_on_path` cannot fetch
  pydantic because pypi.org DNS resolution fails. No installation code was changed.
- `test_release_evidence_rejects_unobserved_git_configuration` reports a changed
  provider snapshot. Closeout documentation was edited while this full run was
  active, so the run was not frozen. With writes stopped, its exact rerun passes:
  1 passed / 0 failed in 5.60 seconds. No test or guard was changed for this failure.

The full suite is not claimed green. After final cursor/log writes, payload is
regenerated through the existing generator and its candidate/public checks are
rerun; the orchestrator must apply the Codex deletion and verify the working-tree
payload/parity checks. Network-enabled installation acceptance remains open.
Evidence logs are under `/tmp/mir-yoke-helper-followup/`: `generator-red.log`,
`focused.log`, `governance-tests.log`, `full.log`, `release-recheck.log`,
`payload-candidate-tests.log`, `sync-cwd.log`, `sync-candidate.log`, and `probes.json`.


## Codex/Claude hook parity (2026-09-24)

Authority: owner Discord 1552383320107515968, item 6, relayed by Mir Harness.
The active intent authority is `tasks/plan.md`; scope is this repository only.
Initial `git status --short` was empty.

### Preserved predecessor cursor (verbatim)

```markdown
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
```

### Policy finding and bounded decision

`git log -S 'remain Claude-only'` traced the generator exclusion to `d3693b8`
(2026-08-29). ADR-84 section 2.4 acknowledged Codex event support but deferred the
cross-runtime efficiency decision. No incompatible field or blocking requirement
was recorded. The current owner task resolves that deferral for this repository.
ADR-84 preserves the original ADR, registration and README wording as dated
superseded notes. The only new runtime registration is UserPromptSubmit; all
pre-existing Codex registrations compare equal. StopFailure stays Claude-only.

The hook is unchanged: at most six terms, one advisory hint, no retrieval execution,
network or memory write; parser/interpreter/tokenizer failures return zero.
Synthetic payload fields follow the official reference:
https://learn.chatgpt.com/docs/hooks#userpromptsubmit and #common-input-fields.

### SessionStart finding

The actual Claude command and generated Codex command produce identical stdout,
stderr and exit code zero with a synthetic startup payload. Both invoke the same
session-start script and upfront-context builder. They inject identity and safety
boundaries, not cursor or intent bodies; only an applicable intent-conflict advisory
is included. This preserves existing task-blind startup policy, so no parity fix
is needed. The compact-only resume registration is unchanged.

No native MEMORY.md for this repo was found at the repository root,
`.claude/MEMORY.md`, `.claude/memory/MEMORY.md`, or matching mir-yoke project-memory
paths under the standard Claude home and installed per-agent Claude homes. No
native index was available to compare/inject. This finding does not attest other
machines or operator-specific memory-directory overrides. No memory DB was accessed.

### Verification and fail-first evidence

- All 5 new generated-command regressions failed before the fix with
  KeyError: UserPromptSubmit. After the fix, the whole prompt-hook file passes
  9/9. New cases cover normal, short, slash-command, XML-like and invalid-type
  prompts, asserting exit zero and exact advisory/empty output.
- Focused hooks, startup and Starter/Kit checks: 81 passed / 0 failed.
- Candidate derivation, compact lifecycle, startup and Starter/Kit checks:
  40 passed / 0 failed. Initial candidate run: 39 passed / 1 failed because the
  disposable copy lacked Git metadata; initializing only that copy fixed it.
- Full documented `uv run pytest -q`: 1303 passed / 5 failed in 200.02 seconds,
  with source writes paused. Two payload equality failures were resolved by the
  existing payload generator, then 13/13 related checks passed. One hook equality
  failure awaits Codex installation. Two unchanged installation tests fail on DNS:
  greenfield-slim cannot download jsonschema from files.pythonhosted.org; copied
  CLI cannot fetch httpx from pypi.org. The full suite is not claimed green.
- Candidate payload/classification: 13 passed / 0 failed.
- Ruff, Bash syntax and diff whitespace checks pass. Context paths: 9 files /
  69 references pass.
- Documented Codex sync fails in cwd for exactly `.codex/README.md` and
  `.codex/hooks.json`; the same verifier passes with the generated candidate.

### Generated installation and boundaries

Temporary output: `/tmp/mir-yoke-hook-parity/generated/`, produced with
CODEX_DERIVATION_OUTPUT_ROOT by the repository generator. Install only
`.codex/hooks.json` and `.codex/README.md`, then rerun the existing
`uv run python tools/template_assets.py --write-adopter-payload` and
`uv run python scripts/verify_codex_sync.py`. The cwd payload manifest reflects
currently installed bytes and needs regeneration after Codex installation.
No other Codex/AGENTS/.agents or sync-manifest installation is required.
The payload generator also corrected a pre-existing stale hash for the unchanged
`.mir/repo-profile.toml`; the profile itself was not edited.

No declared bootstrap evidence changed: hook and repo-profile bytes are unchanged.
This checkout has neither a bootstrap adoption manifest nor a local bootstrap
receipt; the existing maintainer path is unchanged. No re-attestation, new guard,
removed-hook recreation, credential access, memory edits, commits or delivery
occurred. Starter, Project Agent Kit and the shared template renderer are unchanged.

Evidence: `/tmp/mir-yoke-hook-parity/` contains fail-first.log, focused.log,
full.log, candidate-tests.log, candidate-payload.log, session-start.json,
unchanged-boundaries.json, generated/ and candidate/. Synthetic invocation proves
payload compatibility, not live Codex dispatch/trust in a new session. Installation
and network-enabled acceptance remain external. A shell-based documentation append
was rejected by command screening; the explicit file patch succeeded without
changing any guard.


## Twenty-one-item maintenance skill implementation (2026-09-24)

Authority: owner Discord 1552387906927333458, relayed by Mir Harness.
The active design and scope authority is `tasks/plan.md`. ADR-80 binding is deferred.
The owner explicitly authorizes updating this plugin source, superseding the prior
maintenance task's released-plugin byte freeze for this implementation only.

### Implementation and verification

- Items 1-5 and 8-20 retain their original text. Item 6 adds documented database,
  memory and relation-graph repair and stable snapshots that include WAL state.
  Item 7 names Claude/Codex harness consistency. Item 21 covers both Main runtimes:
  root/nested instructions and design references, hook events/commands and documented
  runtime-only exemptions, SessionStart cursor/intent/native-memory index, skill and
  workflow loading, MCP bindings, current Codex hook trust, and observed evidence.
- Bounds prohibit new restrictions, owner-removed hook recreation and blocking
  previously allowed behavior. No runtime hook or safety guard was changed.
- Traced registration through `git log -S repo-maintenance` and e3cb1a8 (v0.10.6).
  Capability sources, agent-management catalog, verifier inventory, dual-runtime
  manifests and sixteen-skill package count already match; no registration edit needed.
  Current descriptions say twenty-one; historical v0.10.6 release text stays historical.
- Fail-first: 11 failed / 1 passed before the skill edit. Every new case failed:
  memory repair, harness bounds and eight parameterized Main-runtime probes, plus
  the updated item-count contract. The unchanged safety-bound contract passed.
- Full documented `uv run pytest`: 1315 passed / 3 failed in 206.87 seconds.
  The lock test fails because only mir-core differs from the unchanged capability
  lock; the other three plugin trees still match. ADR-80 binding is explicitly deferred.
  The greenfield-slim installation cannot download rpds-py from files.pythonhosted.org;
  the copied CLI installation cannot fetch httpx from pypi.org. Both report DNS errors.
  Full-suite acceptance remains blocked by binding and network-enabled installation.
- Final focused skill/package/common contracts: 33 passed / 0 failed after clarifying
  the WAL snapshot wording and fixing one Ruff line-length error in the test.
  Ruff, Codex sync, agent-management schema/catalog checks, context paths (9 files,
  69 references), and diff whitespace checks pass. No skill-size budget was found in
  repository checks; the skill is 63 lines / 6181 bytes (previously 52 / 4670), English only.
  CLAUDE.md stays 3448 bytes and AGENTS.md stays 3537 bytes, both byte-identical.
- Temporary generation produced no differing files: no .codex, AGENTS, .agents or
  sync-manifest installation is needed. The adopter payload is regenerated through
  `tools/template_assets.py --write-adopter-payload`; it is not a runtime lock rebind.
- Declared bootstrap evidence, profile, versions, locks and runtime hooks are unchanged.
  No re-attestation, credentials, protected memory writes, consumer edits or Git
  publication occurred. The worktree was clean before this task.
- Evidence lives at `/tmp/mir-yoke-maintenance-21/`: fail-first.log, focused.log,
  focused-final.log, full.log, generation.log, codex-sync.log and generated-diff.json.
  UV_CACHE_DIR points to its writable uv-cache subdirectory because the inherited cache
  was not writable. The documented intent launcher found no bootstrap receipt; the
  same intent_store.py document operation ran through uv without re-attestation.
- Statuses here concern implementing skill guidance, not certifying live CLI parity.
  Fresh-session hook trust and consumer installation are outside this source-only step.
  The prior generated checklist projection and handoff snapshot were not hand-edited.

### Superseded handoff (verbatim)

```text
# Session Handoff — Repository maintenance re-verification

Resume pointer: `tasks/plan.md` is the only cursor; `tasks/intent.json` records authority.
Evidence and preserved predecessor text: `tasks/change_log.md`, 2026-09-24.
Guards now reject checker errors, diagnostics omit command bodies, advisory hooks report failures,
and malformed external JSON completes with protocol errors instead of leaving pending calls.
Final full suite: 1300 passed; two unchanged installation tests failed on PyPI DNS.
Network access is needed for installation acceptance and current dependency intelligence.
No Codex installation/removal, receipt rebind, commit or delivery is pending.
The historical ADR mapping decision remains in the prior evidence entry, item 20.

<!-- mir:runtime-snapshot:begin -->
## Runtime Snapshot (Generated)

### Active Plan Items
- No open plan items.

### Working Tree
- Working tree dirty (18 paths; inspect git status --short).
<!-- mir:runtime-snapshot:end -->
```

### Superseded operations description (verbatim)

```text
Mir Yoke's portable set is intentionally limited to four plugins and sixteen skills. The optional
`mir-core:selective-relations` skill supports bounded retrieval through declared relationships. The
`design`, `governance`, `efficiency`, `bluebricks`, `testing`, `code-review`, and
`verify` skills already compose this upgrade workflow; an umbrella duplicate would add discovery
cost without a new capability. `mir-core:repo-maintenance` is the owner-defined twenty-item
periodic checklist; it sequences those skills for a maintenance pass and does not restate their procedures.
```

### Superseded input (verbatim)

#### tasks/plan.md

```
# Plan

Owner-authorized Codex/Claude hook parity, 2026-09-24, in this repository only.
Authority: owner Discord 1552383320107515968, item 6, relayed by Mir Harness.
This cursor is the active intent authority. Predecessor cursor is preserved verbatim
in `tasks/change_log.md`, "Codex/Claude hook parity (2026-09-24)".

- [x] Trace the Claude-only policy and verify synthetic Codex prompt compatibility.
- [x] Add only advisory parity through canonical sources; preserve superseded wording.
- [x] Compare SessionStart context and native memory index availability.
- [x] Prove regressions fail first; run documented verification and temp generation.
- [x] Record generated installation list, bootstrap evidence and residual risks.

No commits, delivery, memory writes, consumer-template changes, new restrictions,
or removed-hook recreation are authorized. Generated Codex output stays temporary.

Local source work and permitted verification are complete. Mir Harness must install
`.codex/hooks.json` and `.codex/README.md` from the temporary generator output, then
regenerate `config/adopter-payload.json` and rerun parity. Two installation tests
remain blocked by PyPI DNS. Full evidence is in the log entry named above.
No declared bootstrap evidence changed; no re-attestation was performed.
```

#### tasks/intent.json

```
{
  "goal": "Re-verify all twenty repo-maintenance checklist items against actual repository state and execution evidence, then minimally repair confirmed defects within this repository only.",
  "goal_type": "maintenance",
  "scope": "Owner-authorized maintenance on 2026-09-23. Preserve accepted decisions, user work, safety guards, released plugin and capability-lock bytes, generated-source boundaries and memory databases. No commits, delivery, dependency upgrades, credentials or consumer writes. Previous intent is preserved verbatim in tasks/change_log.md under Twenty-item repository maintenance re-verification.",
  "priority": "normal",
  "updated": "2026-09-23",
  "history": [
    {
      "goal": "Align Mir Yoke as the Harness-managed central capability supply system for independently owned repositories: make the primary purpose, management authority, supported adoption channels, consumer ownership boundaries, ADR precedence, maintainer Profile, operating documentation, contract tests, generated derivatives, and adopter payload consistent without changing interfaces, profile enums, runtime installations, consumer repositories, protected memory, credentials, or external services.",
      "updated": "2026-09-06",
      "status": "superseded"
    },
    {
      "goal": "Clean up Mir Yoke project documents under owner Discord message 1552197111624372339 (2026-09-23): align the current documentation entry points and decision index with the supported surfaces, keep one active plan, preserve historical text and existing work, and verify document references and tests without changing behavior or delivery state.",
      "updated": "2026-09-23",
      "status": "complete"
    },
    {
      "goal": "Re-verify and minimally fix all 15 owner fleet audit items in this repository only under the owner-authorized second pass of 2026-09-23. Preserve accepted decisions, safety gates, historical text and user work; validate actual commands and generated parity; report sandbox-only installation gaps without committing or delivering changes.",
      "updated": "2026-09-23",
      "status": "complete"
    }
  ]
}
```

#### plugins/mir-core/skills/repo-maintenance/SKILL.md

```
---
name: repo-maintenance
description: "Periodic maintenance checkup of an agent-operated repository across twenty fixed items: consistency, operating base, documents, archiving, context, memory, harness constraints, skills and agents, instruction docs, rules and lessons, architecture, delegation and routing, continuity, work-context retrieval, token efficiency, test health, code/security/dependencies, integrity evidence, runtime behavior, and open decisions.\n\nTrigger: repository maintenance, periodic check, repo checkup, fleet maintenance, clean up and improve the repository"
---

# Repository Maintenance

## Use When
- The owner asks for a full maintenance pass over one repository or every managed repository.
- A previous pass needs re-verification against actual files and command output.

## Bounds
- Read, review and status requests stay read-only. A fix request authorizes in-scope edits and relevant checks only.
- Commit, push, tag, release, protected paths, secrets and memory-store writes follow the repository's
  own authority rules. Use only documented commands for memory and generated files.
- Move stale or duplicate material verbatim to the repository's log or archive and leave a pointer.
  Never delete a rule, decision or lesson.
- Relaxing a constraint means removing duplication, dead checks or gates for removed features. It never weakens a safety guard.
- A change that contradicts an accepted decision record or recorded owner intent is listed for the owner, not applied.
- Use a concept (fleet registry, bootstrap receipt, memory store, provider lock) only when the repository declares it.

## Checklist
Apply each item proportionately. Mark it done, no change needed (with evidence), or skipped (with a reason).
1. Consistency: profile and declared paths and commands match reality; docs match code; references resolve; generator parity holds.
2. Operating base: scripts, configs and hooks for removed features; dead entries.
3. Documents: plans, checklists and decision records state current facts. History is not rewritten.
4. Archiving: stale explanations, detailed history and duplicates move to the log or archive.
5. Context: always-loaded files stay minimal and procedures load on demand. Keep a single active cursor.
6. Memory: memory-store integrity and size, stale or missing-source records, and relation-graph health, checked through the documented commands.
7. Harness: excessive, duplicated or dead constraints are relaxed; harness consistency is improved.
8. Skills and agents: unused or duplicate capabilities, stale model or tool references, broken frontmatter.
9. Instruction docs: CLAUDE.md and AGENTS.md stay within size limits and carry the same rules for both runtimes.
10. Rules and lessons: each rule has one home, and lessons live in the declared location.
11. Architecture: the overview matches the actual layout and lists no removed components.
12. Delegation: model routing, delegation lanes and sub-agent limits follow the governing policy.
13. Continuity: one cursor, one resume pointer, one status projection and one evidence log.
14. Work context: one retrieval smoke query returns relevant anchors when retrieval is supported.
15. Token efficiency: session-start and hook output size, always-loaded file sizes, oversized routine reads.
16. Test health: the whole suite runs by default, stays hermetic, is not flaky under load, and new regression tests fail without their fix.
17. Code, security, dependencies: real defects, secret exposure, vulnerable or outdated dependencies, licenses.
18. Integrity evidence: locks, ledgers, receipts, audit chains and profile baselines are rebound through their documented commands after edits. Never fabricate provenance.
19. Runtime behavior: hooks fire, plugins and skills load, tool servers connect, and CLI versions match. Static documentation is not proof.
20. Open decisions: every pending owner decision is listed once, with both sides and the item it blocks.

## Workflow
1. Record the request in the repository's active cursor, then read its contract and profile.
2. Start from a clean or snapshotted worktree so changes can be attributed.
3. Run the checklist. When available, use `mir-core:governance`, `mir-core:verify`, `mir-code:testing` and
   `mir-code:code-review` for item procedures. For many repositories, handle each one under its own contract.
4. Verify with the repository's documented tests and gates. Re-run them yourself before accepting delegated work.
5. Report per item, then list changed files, before/after instruction-doc sizes, checks with pass/fail counts,
   integrity evidence to rebind, owner decisions and residual risks.
```

## Executor common split successor (2026-10-01)

The user supplied a new executor-common specification and local-commit authority. The completed predecessor cursor is preserved below.

```markdown
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
```

Executor common implementation evidence: 89 fail-first nodes, both full suites
1417 passed, both Ruff runs clean, Python 3.11.16 compiled 15 common files, Codex
parity passed. The common manifest is separate from adopter inventory; Yoke local
schema validation and verifier data remain excluded from common sync. Pilot syncs
were read-only and compared package/config/Git-index hashes before and after.

Local commit attempt was blocked: Git could not create `.git/index.lock` under the
session's read-only Git metadata boundary. No commits or remote delivery occurred.
The complete scoped change is retained in the working tree and a temporary patch.

## Archived cursor sections: executor common (moved 2026-10-02)

Moved verbatim from `tasks/plan.md` by the 2026-10-02 maintenance pass; the cursor keeps a pointer.
Resolution facts recorded after the move (from `git log`): the "Commit blocker" and the
unchecked commit item below were resolved by 79536b2; v3.4 (merge gate refuses declared
secrets, unused `state_callback` dropped) landed as 14209a2; Stop hook temp-file
randomisation as 443e293; Harness model-routing lock redeploys as 27ce08a and cf2aa6c.

```markdown
## Active task: executor common v3.3 (2026-10-01)

Authority: the current user request and supplied `spec-executor-v33.md`.
This cursor is the design authority for background failure exit codes and the
read-only route invariant after local hooks. Work only in mir-yoke; named
consumer files are read-only. Do not commit or push.

- [x] Port background regression tests and add route tests; observe failure first.
- [x] Record exit_code=1 and enforce read-only routes; observe focused passes.
- [x] Update the sync guide and regenerate common manifests and affected payload.
- [x] Run full pytest, Ruff, Python 3.11 compilation, self-target sync and parity.

Fail-first: `7 failed, 5 passed, 29 deselected in 0.20s`.
Same initial selection after implementation: `12 passed, 29 deselected in 0.16s`.
Expanded regression selection: `18 passed, 29 deselected in 0.24s`.
Affected files: `47 passed in 0.46s`.
Ruff (`tools tests`): `All checks passed!`. Python 3.11.16 compiled all 15
common manifest files. Self-target sync and Codex parity passed; manifest, sync
and adopter tests: `35 passed in 4.16s`.

First full run: `1 failed, 1597 passed in 210.13s (0:03:30)`.
The exact adopter-payload test failed because this cursor was updated during
that run, after payload generation. Regenerate the payload before rerunning;
keep hashed source documents unchanged while the suite executes.

Final full pytest: `1598 passed in 198.08s (0:03:18)`.
After regenerating the payload, exact inventory, adopter, sync and manifest checks
passed (`41 passed in 4.77s`). Final cursor updates are followed by payload
regeneration and the same generated-inventory checks. No commit, push or consumer
write occurred.

The predecessor records below preserve earlier implementation evidence.

## Active task: executor common v3.2 (2026-10-01)

Authority: the current user request and supplied `spec-executor-v32.md`.
This cursor owns the implementation plan: the invoking Git repository's optional
`authorize_target` guard and opt-in `verifier_env` isolation only.
Write only in mir-yoke; inspect Harness read-only. Do not commit or push.

- [x] Add guard tests, observe failure at ba298f0, implement and observe pass.
- [x] Add verifier isolation tests, observe failure, implement and observe pass.
- [x] Update sync guide and regenerate manifests (payload is affected).
- [x] Run full pytest, Ruff, Python 3.11 compilation and self-target sync checks.

Fail-first evidence (all new nodes also run against an exported ba298f0 package):
guard: `13 failed in 0.55s` -> `13 passed in 0.57s`;
verifier isolation: `5 failed in 1.04s` -> `5 passed in 1.02s`.
Guard coverage includes option registration, writer admission, root changes,
saved and legacy resume targets, and preserved local-option help.
Isolation covers per-verifier directories, explicit environment inputs and cleanup
on success, failure, timeout and process errors.

Final full pytest: `1580 passed in 210.20s (0:03:30)`.
Ruff (`tools tests`): `All checks passed!`. Python 3.11.16 compiled all 15
common manifest files. Self-target sync, Codex parity and 19 manifest/sync/adopter
checks passed. No repository commit, push or Harness write occurred.

The predecessor records below preserve earlier implementation evidence.

## Active task: executor common v3 (2026-10-01)

Authority: the current user request and supplied `spec-executor-v3.md`.
This cursor is the design authority for the six specified common execution changes.
Write only in mir-yoke; named consumers are read-only. No commit, push or tag.

- [x] Per item: add regression tests, observe fail, implement and observe pass.
- [x] Cover CLI routes, agent API, execution writer lease, strict item shape,
      provider hook and optional timeout bounds with compatible absent defaults.
- [x] Update sync guide and regenerate common manifests and affected payload.
- [x] Run full pytest, Ruff, Python 3.11 compilation and self-target drift check.

Evidence: `tasks/reports/executor-common-fail-first.md` owns per-item fail/pass
results. Final full pytest: `1546 passed in 205.29s (0:03:25)`; all 88 v3 tests
passed. Ruff, Python 3.11.16 common-file compilation, generated parity,
self-target sync and regenerated-payload checks passed. No commit, push, tag
or consumer write occurred.

The predecessor records below are preserved as historical evidence.

## Active task: executor common base v2 (2026-10-01)

Authority: the current user request and the supplied `spec-executor-v2.md`.
This cursor is the design authority for the v2 extension hooks and resume integrity.
Write only in mir-yoke; consumers remain read-only. Do not commit or push.

- [x] Add fail-first tests for lifecycle events, identity, rendered briefs, root selection and resume.
- [x] Implement optional hooks with compatible defaults and additive job options storage.
- [x] Document semantics and regenerate common manifests and affected adopter payload.
- [x] Run focused/full pytest, Ruff, Python 3.11 compilation, sync and parity checks.

Fail-first evidence: `test_hooks_v2.py` initially reported `13 failed in 0.39s`:
7 lifecycle nodes, 2 identity nodes, 2 rendered-brief nodes and 2 root-selection nodes.
Durable-review, started/running, effective-options and absent-render-hook regressions
each subsequently failed in a focused run before their respective fixes.
Resume tests first reported `4 failed in 0.11s`; after schema-only implementation,
`2 failed, 2 passed in 0.09s` independently proved lost options and digest acceptance.
The portable manifest test failed with common CLI drift before regeneration.

Final focused pass lines:
- Lifecycle: `9 passed, 8 deselected in 0.30s`.
- Identity: `2 passed, 15 deselected in 0.09s`.
- Rendered brief: `2 passed, 15 deselected in 0.09s`.
- Root selection: `2 passed, 15 deselected in 0.10s`.
- Resume and effective options: `6 passed, 16 deselected in 0.16s`.
- Common manifest and adopter classification: `7 passed in 0.32s`.
- All new v2 tests, including absent-hook compatibility: `22 passed in 0.68s`.

Final full pytest: `1452 passed in 190.83s (0:03:10)`.
Ruff (`tools tests`): `All checks passed!`. Python 3.11.16 compiled all 15
manifest common files. Self-target sync and Codex derivative parity passed.
`policy.py` has no diff and remains self-contained. `cli.py`: 960 lines;
`dispatch.py`: 1211 lines. No commit, push or consumer write occurred.
Fail-first and final suite logs are in `/tmp/mir-executor-v2-*.txt`; resume
fail-first output is explicitly labeled as a transcription of observed tool output.

The completed follow-up below is preserved as evidence, not active authority.

## Active follow-up: executor fixes (2026-10-01)

Authority: the current user request and the supplied `spec-executor-fix1.md`.
This cursor is the design authority for three bounded common-executor fixes.
The predecessor record below is retained as evidence; its commit permission does
not apply to this follow-up. Write only in mir-yoke; do not commit or push.

- [x] Fail first, fix and pass: blocked-dispatch hint uses the actual artifacts path.
- [x] Fail first, fix and pass: backend resolution accepts per-project objects and ignores malformed entries.
- [x] Fail first, fix and pass: fallback policies preserve routing and monitoring.
- [x] Regenerate manifests and adopter payload; run focused/full pytest, Ruff and Python 3.11 compilation.

Fail-first and immediate pass evidence (pytest selectors):
- `blocked_prints_retry_diagnostic`: `2 failed, 118 deselected in 0.35s` -> `2 passed, 118 deselected in 0.23s`.
- `should_return_backend_when_per_project`: `8 failed, 1 passed, 120 deselected in 0.30s` -> `9 passed, 120 deselected in 0.04s`.
- `should_return_routing_and_monitoring`: `3 failed, 33 deselected in 0.07s` -> `3 passed, 33 deselected in 0.03s`.

Focused executor/sync suite: `438 passed in 48.62s`. Ruff: `All checks passed!`.
Full suite: `1430 passed in 200.40s (0:03:20)`. Adopter payload tests: `6 passed`.
Python 3.11.16: all 15 manifest common files compiled. Codex derivatives match sources.
Use `UV_CACHE_DIR=/tmp/mir-yoke-uv-cache` because the default cache is outside writable roots.
All three fixes are complete. No commit, push or other-repository write occurred.

## Preserved predecessor

Executor common base, local split and explicit sync, 2026-10-01.
Authority: current user task and the full owner-approved executor-common specification.
This cursor owns the current intent; the completed predecessor is preserved in
`tasks/change_log.md`, "Executor common split successor (2026-10-01)".

Design authority: this cursor and the supplied spec. Keep common code byte-identical,
repository hooks/data local, and routing policy in existing deployed files.

- [x] Prove missing policy, dispatch, client, job, CLI and sync behavior with failing tests.
- [x] Implement common modules, optional local adapter and cycle-free CLI split.
- [x] Generate independent common manifests and document explicit sync/drift checks.
- [x] Run full pytest, Ruff, Python 3.11 compilation and Codex parity checks.
- [ ] Commit scoped files locally; both dry-run pilots and migration reports are complete.

Only mir-yoke writes and local commits are authorized. No push, tag, release,
capability-lock or plugin edits. Pilot repositories remain read-only. Leave
`tasks/handoffs/session-handoff-LATEST.md` unstaged and uncommitted.

Verification completed: 89 new test nodes have explicit fail-first and pass lines in
`tasks/reports/executor-common-fail-first.md`. Full `uv run pytest`: 1417 passed;
Python 3.11.16 full pytest: 1417 passed. Ruff (both environments), Python 3.11
compilation of 15 common files, Codex parity and manifest drift checks pass.
Both pilot dry-runs report eight changed, six added and two identical files.
Package/config/index hashes remain unchanged in both pilots. Migration details remain
in temporary pilot reports; no consumer file was written. Common source commits and
final pilot revision binding remain pending the Git write boundary below.

Final compatibility follow-up: both legacy executor paths now honor local child
environment filtering and extra keys. Two more nodes failed first and passed;
both final full suites passed all 1417 tests.

Commit blocker: `git add` returned Operation not permitted when creating
`.git/index.lock`. The session grants read-only Git metadata access. No staging,
commit, push, tag or release occurred. The implementation and all requested checks
are complete; source and consumer manifests retain the generated source placeholder
until a writable Git session can commit and bind the consumer manifest.
```

## Repository maintenance pass (2026-10-02)

Authority: the owner's 2026-10-02 maintenance instruction relayed by the Mir Harness
Control Plane (`mir-core:repo-maintenance`, 21 items, this repository only). Cursor:
`tasks/plan.md`. Starting worktree clean at `cf2aa6c`. Baseline: full pytest
`1604 passed in 463.76s`; Ruff `All checks passed!`; Codex parity OK.

Changes:
- Removed six never-called functions from `scripts/generate_codex_derivatives.sh`;
  regenerated output is byte-identical (parity OK, no generated file changed).
- Removed the wired `session-end.sh` from the hook manual-trigger allowlist in
  `config/harness-consistency.json`; regression test
  `test_manual_trigger_allowlist_lists_only_unwired_hooks` failed first on HEAD config.
- Upgraded anyio 4.13.0 -> 4.15.1 (GHSA-82r6-8w77-94w6, GHSA-5p39-cfhj-2xmp; pulls
  typing-extensions 4.16.0) in `uv.lock` and the exported CLI runtime constraints.
  pip-audit: 2 findings before, none after.
- Moved six completed executor-common cursor sections verbatim (above); refreshed the
  stale handoff and checklist (superseded text below); added ARCHITECTURE and
  Unreleased CHANGELOG entries for the executor common source and routing lock;
  corrected a stale session-start claim in `.ai-harness/failure-patterns.md`.

Verified without change: profile paths exist; context paths PASS (71 references);
harness consistency 0 findings; executor common manifest PASS (15 files); routing lock
`source_sha256` matches its Harness sources and agent model fields match the lock;
hook probes (fail-closed on malformed PreToolUse payloads, no Stop/StopFailure echo,
SessionStart identical for both runtimes); memory database integrity ok.

Owner decisions:
- `CLAUDE.md` ends with an empty `## Role policy (template summary)` heading whose
  generated block was removed in 3aab445; `.mir-preserve.toml` still preserves it.
  Keep it (preserve contract) or drop it from both files (35 bytes of always-loaded text).
- The opt-in `MIR_REVIEW_GATE` block in `.claude/hooks/mir-stop.sh` cannot succeed
  (unregistered change ID, `review` is not a lock category, placeholder family) and
  cites ADR files that do not exist here. Remove it or rewire it; blocks hook cleanup.
- `.mir/memory.db` is one migration behind (018); `mir migrate up` writes a protected store.
- Whether owner message identifiers in public tests and logs count as private identifiers.
- Two installation tests need PyPI and are unmarked; a network skip would hide failures.
- The 13 superseded ADRs without successor numbers remain open (prior item 20).

Mir Harness requests: guard non-object `agent_criteria` in common
`tools/mir_executor/dispatch.py` (AttributeError); qualify "ADR-88" as Mir Harness
ADR-88 in common `policy.py` comments; refresh `profile_base_commit` (`e3207d5`;
`mir context pull` reports `profile-freshness state=review_required`), which has no
documented rebind command. `.mir/capability-lock.json` (source d8a1516) needs no
rebind: all 17 pinned file digests match the working tree.

Resumed run (same day): the run above stopped before committing. Its edits were audited
against the files: the six removed shell functions had no callers; `session-end.sh` is
wired in `.claude/settings.json` and `.codex/hooks.json`; pip-audit on the HEAD
constraints reports PYSEC-2026-4024/4025 (aliases GHSA-5p39-cfhj-2xmp,
GHSA-82r6-8w77-94w6; fix 4.14.2) and nothing on the new lock export. Fail-first for
`test_manual_trigger_allowlist_lists_only_unwired_hooks` re-run: HEAD config
`1 failed`, fixed config `1 passed`. Memory database read through an immutable
snapshot (no WAL/SHM files present): `integrity_check` ok, `foreign_key_check` empty,
`mir migrate status` 017 of 018, `reconcile-missing --dry-run` would expire 0.
`mir memory doctor` reports `not_ready` only because this checkout has no active
`harness_a.toml` (profile `requires_memory_store = false`). Codex project trust is
`trusted` with 11 `trusted_hash` entries for the 11 hooks in `.codex/hooks.json`
(unchanged since 7b0c37f); the hash values were not recomputed.
Final gates: pytest `tools` 699 passed, `tests` 906 passed; Ruff `All checks passed!`;
Codex parity OK; context paths PASS (75 references); harness consistency 0 findings;
executor common manifest PASS; `uv lock --check` resolves. Committed locally only.

Superseded continuity text, verbatim:

```markdown
# Session Handoff — Twenty-one-item maintenance skill

Resume pointer: `tasks/plan.md` is the only cursor; `tasks/intent.json` records authority.
Evidence and preserved predecessor text: `tasks/change_log.md`,
"Twenty-one-item maintenance skill implementation (2026-09-24)".
Items 6 and 7 are strengthened; item 21 adds concrete parity probes for either Main CLI.
Full suite: 1315 passed / 3 failed. Final focused tests: 33 passed / 0 failed.
Mir Harness owns ADR-80 binding (mir-core currently differs from the unchanged lock).
Two installation checks also need working PyPI DNS. Ruff and generated parity pass.
No Codex installation, bootstrap evidence change or re-attestation is needed.
No new restriction, hook recreation, memory write, version bump or Git publication occurred.
The generated snapshot below belongs to the preceding hook run; inspect current Git status.

# Checklist

Status projection for `tasks/plan.md`: all twenty maintenance items were re-verified.
Guards, advisory failure handling, external JSON validation and startup-test timing were repaired.
Final full suite: 1300 passed, two unchanged installation tests failed on PyPI DNS.
Evidence and preserved predecessor text: `tasks/change_log.md`, 2026-09-24.
Generated parity passes; no Codex installation/removal or integrity rebind is pending.
The historical ADR mapping decision remains in the prior twenty-item evidence entry, item 20.
```

## Archived maintenance cursor (2026-10-02 executor follow-up)

# Plan

## Active task: repository maintenance pass (2026-10-02)

Authority: the owner's 2026-10-02 maintenance instruction, relayed by the
Mir Harness Control Plane: run `mir-core:repo-maintenance` (21 items) over this
repository, then improve it. This cursor is the intent and design authority.
mir-yoke only; local commits of own files only. No push, tag, release, consumer
write, secret access, `config/model-routing.lock.json` or synced
`tools/mir_executor` common edits (those go to NEEDS HARNESS).
Starting worktree: clean at `cf2aa6c`.

- [x] Baseline: full pytest, Ruff, Codex parity.
- [x] Audit 21 items; re-verify the 2026-09-23/24 fixes, the ADR-88 lock and executor v3.4.
- [x] Fix in-scope defects; each new regression test fails first, then passes.
- [x] Re-run documented gates; regenerate the adopter payload; commit own files locally.

Final gates (resumed run): `uv run pytest` over `tools` 699 passed and `tests` 906
passed (1605); Ruff, Codex parity, context paths, harness consistency and the
executor common manifest pass. No task item remains open.

Evidence, owner decisions and Mir Harness requests: `tasks/change_log.md`,
"Repository maintenance pass (2026-10-02)".

## Predecessor cursor sections

Executor common v3.3, v3.2, v3, base v2, the executor fixes follow-up and the
preserved executor-common predecessor (2026-10-01; its open commit item was resolved
by 79536b2) moved verbatim to `tasks/change_log.md`,
"Archived cursor sections: executor common (moved 2026-10-02)".

## Executor common v3.5 maintenance (2026-10-02)

Authority: the explicit owner follow-up relayed by Mir Harness; design and intent
authority: `tasks/plan.md`. Baseline: clean HEAD `279c90f`. The follow-up authorizes
common changes deferred by the preceding maintenance pass and a local commit.
No consumer writes, credentials, memory writes, capability lock edits or publication.

### Changes and fail-first evidence

1. Production `cleanup_worktree` already removes its tracked automatic temporary
   base. CLI-level tests used `_cleanup_repo_dispatch_worktrees`, which
   directly removed Git worktrees and bypassed that production cleanup. The test
   helper now reconstructs the dispatch metadata and calls `cleanup_worktree`.
   The isolated-TMPDIR regression counts `mir-wt-*` entries before/after and
   verifies the created base is inside that directory.
2. The resolver now rejects non-object `agent_criteria` and non-object selected
   agent entries with clear `ValueError` messages, matching the existing
   malformed-lock `policy` error wording. Missing criteria still default normally.
3. Only the host-mode test docstring changed in `test_policy.py`: the deployed
   repository lock wins; the host policy is a fallback when no lock is deployed.
4. Common `policy.py` comments/docstring now name Mir Harness ADR-88 explicitly.
   Documented the common increment as v3.5; manifest schema stays version 1.

Fail-first command (before the helper and production fixes):

```sh
uv run pytest -q -p no:cacheprovider tools/mir_executor/tests/test_dispatch.py -k 'temp_bases or agent_criteria_is_not'
```

Observed: **9 failed, 134 deselected in 0.61s** (pytest exit 1).
All nine new nodes were observed failing:
- `test_should_remove_temp_bases_when_cli_test_worktrees_are_cleaned`: one empty
  automatic temporary base remained after test cleanup.
- `test_should_raise_clear_error_when_agent_criteria_is_not_an_object`:
  `[None]`, `[criteria1]`, `[invalid]`, `[1]`, `[criteria4]`, `[criteria5]`,
  `[criteria6]`, `[criteria7]` each raised AttributeError instead of ValueError.
  Inputs were null/list/string/integer for the criteria map and for its selected entry.

The same command after the fix returned **9 passed, 134 deselected in 0.38s**.
No new test passed before its fix, and no collection failure is counted as evidence.

### Verification

- Full executor tests: `uv run pytest -q -p no:cacheprovider tools/mir_executor/tests`:
  **608 passed in 71.97s**. Fresh isolated TMPDIR had **0** `mir-wt-*` entries
  before and **0** afterward; **0** new entries.
- Ruff on all four touched Python files: all checks passed.
- Python 3.11.16 compilation: all **15** common-manifest Python files compiled.
- `python -m tools.executor_sync --generate`: regenerated both common manifests,
  retaining the literal `SOURCE_COMMIT` placeholder and schema version 1.
- `python -m tools.executor_sync --help`: exit 0.
- `python -m tools.executor_sync --check --target .`: Common manifest PASS.
- `uv run python scripts/verify_codex_sync.py`: derivatives match Claude sources.
- No modified path is pinned by `.mir/capability-lock.json`; no rebind is needed.
- Full repository suite: `uv run pytest -q -p no:cacheprovider`:
  **1614 passed in 315.35s (0:05:15)**, pytest exit 0.
- Continuity projections and the adopter payload are refreshed for this task.
  Final portable-manifest, sync-tool, template-classification and reference-payload
  checks returned **26 passed in 2.00s**. Payload hashes are regenerated after
  recording this result and checked for exact equality before local commit.

### Explicit consumer resync

From the tested, committed Mir Yoke checkout, for each owner-authorized target:

```sh
python -m tools.executor_sync --target /path/to/repo
python -m tools.executor_sync --target /path/to/repo --apply
python -m tools.executor_sync --check --target /path/to/repo
```

Sync copies common runtime files and the portable manifest test only. The
repository-owned `test_dispatch.py` cleanup fix and `test_policy.py` docstring
are not synced; target owners must adapt those local tests separately.
No consumer repository was inspected or changed during this task.

### Local commit blocked by filesystem permissions

After verification, an explicit `git add` of the fourteen task-owned files failed:
`Unable to create .git/index.lock: Operation not permitted`. The execution
environment exposes `.git` read-only and does not allow permission escalation.
No file was staged and no new commit was made; HEAD remains
`279c90f9fbd91aeab37ed19cfdf2d9a58f1dae6c`. The worktree contains the reviewed edits.
The owner already authorized the commit; a Git-writable session must finish it
before this checkout is used as a consumer sync source.

Prepared commit subject: `fix(executor): validate agent criteria and clean test worktree bases`.
Material boundary trailer: `Constraint: Mir Yoke only; no consumer writes or publication.`
Required final commit-message line:
`Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Executor common v3.5 extension: items 5-6 (2026-10-02)

Authority: the owner's additional instruction extends the same uncommitted
v3.5 maintenance task. `tasks/plan.md` remains the intent and design authority.
Items 1-4 and their fail-first evidence above remain part of this change.
No consumer writes or publication; no amendment occurred because the earlier
local staging attempt was denied and HEAD remains `279c90f`.

5. The client issues integer RPC request IDs. Responses with string IDs, including
   internal `turn:<threadId>` wait keys, are ignored. Integer IDs not present in
   the issued pending-request map are ignored before envelope validation. Thus an
   unknown response cannot resolve a turn or fail genuine requests.
6. JSON decoding RecursionError is recorded and ignored like invalid JSON.
   The stdout reader's finalization maps unexpected exceptions and EOF to
   CodexMcpProcessError, preserves explicit protocol errors, stops the server and
   signals all pending calls. It also drains requests registered during teardown.
   Normal process-exit diagnostics retain the exit code.

### Additional fail-first evidence

Tests use the real subprocess test server. No hard timeout is passed to the
reader-failure calls; each test bounds its own observation and closes the client
in finally, so red runs cannot hang the test suite.

Initial definitive red command:

```sh
uv run pytest -q -p no:cacheprovider tools/mir_executor/tests/test_codex_mcp_client.py -k 'internal_turn or invalid_input_or_dies'
```

Result before either implementation fix: **6 failed, 44 deselected, 2 warnings
in 8.65s** (exit 1).
- Item 5: `test_should_ignore_response_when_id_matches_only_an_internal_turn`
  failed for `[spoofed_turn]` (SPOOFED accepted), `[spoofed_scalar]`
  (AttributeError) and `[spoofed_error]` (unissued error rejected the genuine turn).
- Item 6: `test_should_release_no_timeout_call_when_reader_gets_invalid_input_or_dies`
  failed for `[deeply_nested]`, `[reader_exception]` and `[reader_eof]`:
  each left the no-timeout call pending. The nested line raised RecursionError in
  the reader; the test uses depth 10000 because depth 5000 parses on Python 3.12.

A further item-5 boundary case was added before its corresponding membership fix:

```sh
uv run pytest -q -p no:cacheprovider tools/mir_executor/tests/test_codex_mcp_client.py -k integer_id_was_never_sent
```

`test_should_ignore_response_when_integer_id_was_never_sent` failed with
CodexMcpProtocolError for an unknown integer response envelope:
**1 failed, 50 deselected in 0.36s** (exit 1).

Final additional regression selector:

```sh
uv run pytest -q -p no:cacheprovider tools/mir_executor/tests/test_codex_mcp_client.py -k 'internal_turn or invalid_input_or_dies or integer_id_was_never_sent'
```

Result: **7 passed, 44 deselected in 1.61s**.
Each of the seven additional new cases failed before its own fix.
An intermediate complete transport check returned **68 passed in 15.47s**;
final verification below includes the additional unknown-integer case.

Both common manifests are regenerated for the same v3.5 increment; the manifest
schema remains 1. The third changed common runtime module is
`codex_mcp_client.py`; repository-owned tests remain excluded from sync.
### Combined six-item verification

- Full repository command: `uv run pytest -q -p no:cacheprovider`:
  **1621 passed in 240.54s (0:04:00)**, exit 0.
- Full executor command: `uv run pytest -q -p no:cacheprovider tools/mir_executor/tests`:
  **615 passed in 72.35s (0:01:12)**. The isolated TMPDIR had 0 `mir-wt-*`
  entries before and 0 afterward; no new directory leaked.
- All sixteen new regression cases across items 1, 2, 5 and 6 failed before
  their own fixes and pass in the full suite. Items 3 and 4 only change wording;
  their existing tests and affected common-file checks pass.
- Ruff on all six touched Python files: all checks passed.
- Python 3.11 compilation: all 15 manifest Python files compiled.
- `python -m tools.executor_sync --help`: exit 0.
- Both regenerated common manifests pass self-target `executor_sync --check`.
- `scripts/verify_codex_sync.py`: derivatives match Claude sources.
- No modified path overlaps capability-lock pins; no rebind is needed.
- Added tracked text is English and contains no private paths, owner IDs or
  machine-specific identifiers. Consumers were not inspected or modified.

The common version remains v3.5 for all six items; manifest schema remains 1.
The explicit consumer resync commands above remain unchanged and require a
tested, committed source checkout. Local staging must be retried; no commit
exists yet because the earlier Git sandbox denied `.git/index.lock` creation.

Prepared final commit message:

```text
fix(executor): harden request correlation and dispatch cleanup

Reject malformed agent criteria and unissued response IDs. Ignore excessive
JSON nesting and fail pending calls on stdout-reader failure or EOF. Reuse
production cleanup in CLI tests and clarify Mir Harness policy precedence.

Constraint: Mir Yoke only; no consumer writes, push, tag or release.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

Final closure checks for the extension: portable manifest, executor sync,
classification and reference payload tests returned **26 passed in 1.44s**.
The final explicit staging attempt for all sixteen task-owned files again
returned exit 128: `Unable to create .git/index.lock: Operation not permitted`.
No new commit or amendment was possible. The local commit remains the only open
task; the prepared message above retains the required final Co-Authored-By line.
HEAD is still `279c90f9fbd91aeab37ed19cfdf2d9a58f1dae6c`. The final evidence
record is included in the regenerated adopter payload and its exact hashes are
checked after regeneration. Temporary task scratch is removed at closure.

## Executor common v3.6: redaction coverage (2026-10-02)

Authority: owner Discord 1555264868402335765 (fleet maintenance pass), relayed by the Mir
Harness Main. Reported by the quietleaf maintenance run and reproduced by the Main:
`redact_secret_like_content` left `"api_key": "value"`, `SECRET_KEY=value`,
`Authorization: Basic <credential>` and quoted values with spaces visible, and
`redact_structured_value` kept string values whose dict key names a secret.

- `tools/mir_executor/redaction.py`: the secret-name pattern accepts a `_KEY` suffix, an
  optional quote after the key, quoted values (replaced whole) and a `Basic` scheme; a dict
  string value under a secret-named key becomes `[REDACTED]`. Unquoted assignments keep the
  existing `key=[REDACTED]` form.
- `tools/mir_executor/tests/test_redaction.py`: 6 cases failed before the fix (4 shapes,
  quoted value with spaces, dict key); 5 cases passed before and after
  (`AWS_SECRET_ACCESS_KEY`, three plain mentions, the existing unquoted format).
- Manifests regenerated with `python -m tools.executor_sync --generate`.

## Archived cursor: before executor common v3.7 (2026-10-02)

# Plan

## Active task: fleet Codex transport wording (2026-10-02)

Authority: owner Discord 1555375556290154528, 2026-10-02. This cursor records
intent and is the design authority. Work only in mir-yoke; preserve history,
compatibility identifiers, generated sources and unrelated changes. No executor
common-code edits, protected-path writes, commits or pushes.

Design: classify the requested grep inventory; update live transport guidance;
add the exact supersession line only to current ADRs without an equivalent note.
Preserve the dependent inactive MCP example entry and report that limitation.

- [x] Inventory and minimally update eligible sources and ADR notes.
- [x] Refresh the repository-only adopter payload and check docs, links and parity.
- [x] Record class counts, changes, generators, checks and unresolved dependencies for reporting.

Inventory (original line numbers; matching rows, not individual occurrences):

- LIVE: zero requested-regex hits; supplemental `.mcp.json.example` guidance and
  split command/args identify one live configuration source.
- HISTORY (12): `CHANGELOG.md:187`; ADR-65:16; ADR-69:32; ADR-85:104;
  ADR-90:40; `tasks/change_log.md`:681,943,944,945,958,960;
  `tasks/tdd.json`:577. ADR-69 and ADR-85 already have equivalent amendments.
- IDENTIFIER (15): `config/adopter-payload.json`:4837,4927;
  `config/mir-executor-common.json`:8; ADR-90:38 (real `codex mcp list` client
  command); `tasks/change_log.md`:1038,1239,2571,2584,2600,2604,2610,2620;
  `tasks/tdd.json`:1395,1398,1403.

Evidence: 18 tests passed via `uv run pytest -q tests/test_link_integrity.py
 tests/test_decision_authority.py tests/test_template_asset_classification.py`;
`uv run python scripts/verify_codex_sync.py` passed. No tests assert the changed
transport wording, so the conditional full-suite gate does not apply.
Generator: `uv run python -m tools.template_assets --write-adopter-payload`.
Use the owner-provided external `UV_CACHE_DIR`; temporary verification files use
an external `TMPDIR` and are removed afterward. Host paths are normalized here;
the original cursor remains available at `7f7e677:tasks/plan.md`.
The generator also refreshes an already-stale routing-lock digest; it does not
modify the routing lock. The inactive example has dependants in README,
MIGRATION, capability configuration, asset inventory, operations and ADRs;
its removed server entry is retained under the owner's removal condition.

## Previous completed task

## Active task: executor common v3.5 maintenance (2026-10-02)

Authority: the explicit owner follow-up relayed by Mir Harness on 2026-10-02.
This cursor is the intent and design authority. The follow-up authorizes the
previously deferred common executor edits and one local commit in mir-yoke.
No consumer writes, push, tag, release, credentials or capability-pinned changes.
Starting worktree: clean at `279c90f`.

Design: reproduce the isolated-TMPDIR test leak and reuse production cleanup,
which already removes its temporary base. Reject non-object agent criteria with
the resolver's normal ValueError contract. Correct the requested policy docstring
and qualify common policy references as Mir Harness ADR-88. Version this bounded
common maintenance increment as v3.5 in the sync document and changelog; keep
manifest schema version 1.

Owner extension: include items 5 and 6 in this same v3.5 increment. Only response
IDs issued by this client may resolve requests; internal turn keys are not RPC
request IDs. Treat excessive JSON nesting like other malformed lines. Unexpected
stdout-reader failure or EOF must release pending calls, including calls without
a timeout, through the existing process-error contract.

- [x] Reproduce response-ID collisions, excessive JSON nesting and unexpected reader death.
- [x] Fix request correlation and reader failure handling; record fail-first evidence.
- [x] Regenerate manifests and rerun the full verification for items 1-6.

- [x] Add regression cases and record every case failing before its fix.
- [x] Repair cleanup and criteria validation; correct policy wording.
- [x] Generate manifests; verify full executor tests leave no new mir-wt directories.
- [x] Run full pytest, touched-file Ruff, Python 3.11 compilation, sync and Codex parity.
- [x] Record evidence and refresh continuity projections and payload.
- [x] Commit locally: the Codex sandbox could not create `.git/index.lock`; the Mir Harness Main re-ran the full suite and committed.

Evidence: `tasks/change_log.md`, "Executor common v3.5 maintenance (2026-10-02)".
Other open owner items in the preceding maintenance evidence remain unchanged.

Predecessor cursor: `tasks/change_log.md`,
"Archived maintenance cursor (2026-10-02 executor follow-up)".

## Executor common v3.7: symlink safety and backend precedence (2026-10-02)

Authority: current owner task; intent/design authority: `tasks/plan.md`.
Baseline: clean HEAD `7f7e677`, common v3.6. No commit, tag, push, release,
consumer write, secret access or generated `.codex/**` write is authorized.

- Private worktree writes now set O_NOFOLLOW before truncating/chmodding files.
- Artifact persistence opens `.mir-dispatch` with O_DIRECTORY/O_NOFOLLOW and
  opens each artifact relative to that directory descriptor with O_NOFOLLOW.
  Both file and directory symlinks fail closed; absent artifacts remain optional.
- Current CLI already gave agent-route backends precedence over policy force and
  default backends. Its remaining defect ignored conflicting explicit backend
  flags even in user_command_priority mode. Backend resolution now accepts the
  agent backend and preserves policy-permitted user_command precedence while
  agent backends win over forced, project and default policy choices.
- Documented the common increment as v3.7. Common manifests retain schema 1,
  the same 15 file entries and literal SOURCE_COMMIT placeholder. Routing lock
  bytes and format are unchanged.

Fail-first evidence is preserved in `tasks/reports/executor-common-fail-first.md`
under "Common v3.7". Worktree: 1 failed -> 1 passed. Artifacts: 12 failed ->
12 passed. CLI: 12 failed / 96 passed -> 108 passed. Focused four-file suite:
198 passed in 9.93s. One new test line exceeded Ruff's line limit and was wrapped;
repository-wide Ruff subsequently passed.

Generators: `uv run python -m tools.executor_sync --generate` (15 common files)
and `uv run python -m tools.template_assets --write-adopter-payload`.
Every uv command uses the owner-provided external UV_CACHE_DIR; scratch stays
under the owner-authorized external cache and is removed after checks.
Initial checks: common manifest PASS; Codex derivatives match Claude sources;
Python 3.11.16 compiled all 15 common files. Final suite evidence follows below.

### Final verification and remaining item

- `uv run pytest -q -p no:cacheprovider tools/mir_executor/tests`:
  **1 failed, 742 passed in 72.49s (0:01:12)**, exit 1.
- `uv run pytest -q -p no:cacheprovider`:
  **1 failed, 1748 passed in 232.84s (0:03:52)**, exit 1.
- Both final runs fail only
  `test_policy.py::test_adr88_this_repository_routes_from_its_deployed_lock`:
  `assert 'force_codex' == 'user_command_priority'`. The test hardcodes a mode
  inconsistent with the committed routing lock. The test, conftest, policy.py,
  local sub-agent policy and routing lock match HEAD byte-for-byte. Its isolated
  rerun also failed in 0.05s. This unrelated existing assertion is left unchanged.
- `uv run ruff check`: All checks passed!
- `uv run python scripts/verify_codex_sync.py`:
  OK: Codex derivatives match Claude sources.
- `uv run python -m tools.executor_sync --check --target .`:
  Common manifest: PASS. Manifest top-level keys, schema 1, SOURCE_COMMIT and
  all 15 file entries are unchanged; the two common manifests are identical.
- Python 3.11.16 compiled all 15 common files using an external pycache.
- Portable manifest, executor sync and payload checks: 19 passed in 1.76s.
  Public-surface and exact-payload checks after path normalization:
  9 passed in 0.42s. The initial whole-repository run had an additional public
  path failure caused by host paths copied from the prior cursor and new evidence;
  these paths were normalized and the final whole-repository run passes that check.

Changed paths: CHANGELOG.md; config/adopter-payload.json;
config/mir-executor-common.json; docs/operations/mir-executor-sync.md;
tasks/change_log.md; tasks/plan.md; tasks/reports/executor-common-fail-first.md;
tools/mir_executor/COMMON_MANIFEST.json; tools/mir_executor/cli.py;
tools/mir_executor/dispatch.py; tools/mir_executor/worktree.py;
tools/mir_executor/tests/test_cli_common.py;
tools/mir_executor/tests/test_dispatch_common.py;
tools/mir_executor/tests/test_v3_cli_routes.py;
tools/mir_executor/tests/test_worktree.py.

No requested production fix remains open. The stale repository-owned policy
assertion prevents a green full-suite gate; it is not distributed by executor sync.
No commit, tag, push, release, consumer change, protected-path change or generated
Codex installation occurred. Final evidence edits require the final adopter-payload
refresh and its exact-content check; temporary scratch is removed afterward.

## Archived cursor: before executor common v3.7 review corrections (2026-10-02)

# Plan

## Active task: executor common v3.7 (2026-10-02)

Authority: the current owner task; this cursor owns intent and design. Fix the
three reported executor common defects test-first within Mir Yoke only. Preserve
lock formats, protected paths and unrelated changes. No commits, tags, pushes,
releases, consumer writes, credentials or generated `.codex/**` writes.
Baseline: clean HEAD `7f7e677`; prior common base v3.6.

Design: refuse symlink destinations using O_NOFOLLOW in private worktree writes;
open artifact sources without following symlinks before copying. Current CLI
already lets agent-route backends win over policy defaults/force modes; reproduce
that behavior and fix the remaining explicit backend flag precedence only where
policy permits selection. Keep model/effort overrides and read-only constraints.
Version this common increment as v3.7 in the sync guide and CHANGELOG; retain
manifest schema 1 and routing lock bytes.

- [x] Add each regression and capture baseline failure/pass evidence before fixes.
- [x] Apply minimum fixes and rerun each regression.
- [x] Record version/changelog; regenerate common manifests and adopter payload.
- [x] Run executor suite, repository pytest/Ruff/parity, manifest check and Python 3.11 compilation.
- [x] Record changed paths, exact evidence and anything left.

The superseded cursor is preserved with host paths normalized in `tasks/change_log.md` under
"Archived cursor: before executor common v3.7 (2026-10-02)".
The original is available at `7f7e677:tasks/plan.md`.

Results: focused checks passed; executor suite 742 passed / 1 failed; repository
suite 1748 passed / 1 failed. Both failures are the same unchanged policy test:
it hardcodes user_command_priority while the committed lock declares force_codex.
Policy source, fixture, local policy and routing lock match HEAD byte-for-byte.
Ruff, Codex parity, common manifest and Python 3.11 compilation passed.
Final evidence: `tasks/change_log.md`, "Executor common v3.7", and
`tasks/reports/executor-common-fail-first.md`, "Common v3.7".
No commit, delivery or generated Codex write occurred. The unrelated stale policy
assertion remains open; no requested production defect remains.


## Executor common v3.7 owner review corrections (2026-10-02)

Authority: current owner follow-up; intent/design authority: `tasks/plan.md`.
This correction supersedes the earlier v3.7 decision that agent backends override
forced modes. `_resolve_dispatch_backend` again returns the forced backend
unconditionally for force_codex/force_claude. The new force_codex plus Claude
agent-route regression failed first with `assert 'claude' == 'codex'`,
`1 failed in 0.06s`, exit 1. Existing explicit user_command precedence and agent
precedence over project/default steps remain. The dispatch route matrix is
updated to expect the forced backend. The committed-lock policy test now reads
its expected mode from the lock; lock bytes and format remain unchanged.
The v3.7 CHANGELOG and sync guide explicitly document enforced forced modes.
Captured fail-first and final evidence belongs to
`tasks/reports/executor-common-fail-first.md`, "v3.7 owner review corrections".
Final follow-up outputs (all exit 0; external UV cache and scratch applied):

```text
uv run pytest -q -p no:cacheprovider tools/mir_executor/tests/test_cli_common.py tools/mir_executor/tests/test_v3_cli_routes.py tools/mir_executor/tests/test_policy.py
177 passed in 3.86s

uv run python -m tools.executor_sync --generate
Generated config/mir-executor-common.json: 15 files

uv run python -m tools.template_assets --write-adopter-payload
template asset classification: pass

uv run pytest -q -p no:cacheprovider
1750 passed in 248.36s (0:04:08)

uv run ruff check
All checks passed!

uv run python scripts/verify_codex_sync.py
OK: Codex derivatives match Claude sources

uv run python -m tools.executor_sync --check --target .
Common manifest: PASS
```

The fail-first regression is covered by the 177-test focused run and the full
1750-test run. Both required corrections are complete. This follow-up changed
CHANGELOG.md; config/adopter-payload.json; config/mir-executor-common.json;
docs/operations/mir-executor-sync.md; tasks/change_log.md; tasks/plan.md;
tasks/reports/executor-common-fail-first.md; tools/mir_executor/COMMON_MANIFEST.json;
tools/mir_executor/cli.py; tools/mir_executor/tests/test_cli_common.py;
tools/mir_executor/tests/test_policy.py; tools/mir_executor/tests/test_v3_cli_routes.py.
Earlier v3.7 symlink implementation/tests remain intact. No commit, tag, push or
consumer write occurred. The committed lock and generated `.codex/**` are
unchanged. Final evidence edits are followed by the same payload generator and
exact-payload/public-surface checks; task scratch is removed after those checks.
No requested item remains open.

Final record/payload checks: `9 passed in 0.41s` using
`uv run pytest -q -p no:cacheprovider tests/test_template_asset_classification.py
tests/test_public_template_surface.py`. Lock and all 15 generated `.codex/**`
files match the follow-up baseline SHA-256 values.


## Archived cursor: before executor common v3.8 (2026-10-02)

# Plan

## Active task: executor common v3.7 review corrections (2026-10-02)

Authority: the current owner follow-up; this cursor owns intent and design.
Preserve the existing uncommitted v3.7 work. The owner corrects the prior decision
that agent backends override forced modes: force_codex and force_claude must
return their forced backend unconditionally. Explicit user backend selection
still wins in the selected user_command step; agent routes otherwise beat
project/default steps. The committed routing lock decides the live-policy test.
Do not change the lock, consumers, protected paths or generated `.codex/**`.
No commit, tag or push is authorized. Use the owner-provided external UV cache.

- [x] Review existing diff, cursor and v3.7 evidence.
- [x] Add the force_codex/conflicting agent-route regression; capture its failure.
- [x] Restore forced backend resolution; update route matrix and lock-based assertion.
- [x] Correct v3.7 guide/changelog/evidence; run both requested generators.
- [x] Run full pytest (zero failures), Ruff, Codex parity and executor manifest check.
- [x] Record final outputs, changed paths and remaining work; remove scratch.

The prior cursor is preserved in `tasks/change_log.md` under
"Archived cursor: before executor common v3.7 review corrections (2026-10-02)".

Results: the force_codex/conflicting-agent regression failed first (`1 failed in
0.06s`); focused tests passed (`177 passed in 3.86s`). Full pytest passed:
`1750 passed in 248.36s (0:04:08)`, zero failures. Ruff, Codex parity and executor
manifest checks passed; both requested generators succeeded. Final evidence:
`tasks/reports/executor-common-fail-first.md`, "v3.7 owner review corrections",
and the matching entry in `tasks/change_log.md`. Final record edits were followed by the
same payload refresh and exact-content/public-surface checks: `9 passed in 0.41s`. No requested item
remains; no commit/tag/push, consumer write, lock edit or `.codex/**` write occurred.


## Executor common v3.8: forced-mode route model guard (2026-10-02)

Authority: owner Discord 1555426386900942934, 2026-10-02; intent and design
are recorded in the single `tasks/plan.md` cursor. Baseline: clean `f95dcd5`.
Agent-route model/effort now apply only when the explicit execution_backend
matches the resolved backend. Explicit CLI model/effort keep precedence.
Category/default routes declare no backend; resolve_category returns model/effort
only. Forced dispatch rejects recognized opposite-backend automatic models using
Claude aliases sonnet/opus/fable/haiku and claude-* versus Codex gpt-* before
creating a runner. Unknown model names remain usable; explicit user models bypass
the guard. No policy or lock changes are required.

Fail-first: the force_codex plus Claude/sonnet agent regression observed
`assert 'sonnet' == 'gpt-category'`, `1 failed in 0.07s`, exit 1 before the fix.
Focused policy/CLI/route tests: `211 passed in 4.00s`, exit 0.
Both generators passed: common manifest generated 15 files; adopter asset
classification passed. Required acceptance results (all exit 0):

```text
uv run pytest -q -p no:cacheprovider
1784 passed in 220.99s (0:03:40)

uv run ruff check
All checks passed!

uv run python scripts/verify_codex_sync.py
OK: Codex derivatives match Claude sources

uv run python -m tools.executor_sync --check --target .
Common manifest: PASS

python3.11 -m compileall -q tools/mir_executor
(no output; exit 0, external task bytecode cache)
```

The guide and CHANGELOG version the common base as v3.8; generated manifests keep
schema 1 and SOURCE_COMMIT. Full fail-first output, changed files and final outputs
are in `tasks/reports/executor-common-fail-first.md`, "Common v3.8". The previous
cursor is preserved above. No commit/tag/push, consumer write, lock edit or generated
`.codex/**` write occurred. Final record edits are followed by the payload generator
and exact-content/public-surface checks; task scratch is removed afterward.


Final record refresh: `uv run python -m tools.template_assets --write-adopter-payload`
passed; `uv run pytest -q -p no:cacheprovider tests/test_template_asset_classification.py
tests/test_public_template_surface.py` passed (`9 passed in 0.35s`, exit 0).
The closing cursor/log update repeats the same payload refresh and checks.
No requested implementation or acceptance item remains. Task scratch is removed
after the closing checks; no additional delivery or Git authority is exercised.

## Reference application profile registration and 0.10.8 preparation (2026-10-11)

Owner authority: current repository-only request. Preserve the already-authored skill and contract test byte-for-byte. No commits, pushes, tags, releases, consumer writes or generated `.codex/**` writes.

### Superseded cursor and intent (verbatim)

#### tasks/plan.md

```
# Plan

## Active task: executor common v3.8 forced-mode route model guard (2026-10-02)

Authority: owner Discord 1555426386900942934, 2026-10-02, and the current
executor task. This single cursor owns intent and design. Baseline: clean
HEAD `f95dcd5`, common v3.7. Work stays in Mir Yoke; no commit/tag/push,
consumer writes, routing lock edits or generated `.codex/**` writes.

Design: only apply agent model/effort when its declared execution_backend equals
the resolved dispatch backend. CLI model/effort overrides retain precedence.
The policy/lock category and default routes declare model/effort, not a backend;
resolve_category also discards any unrelated keys. Reject a recognized opposite
backend model in forced modes before constructing or invoking the runner, unless
the user supplied an explicit model. Recognize Claude aliases sonnet/opus/fable/haiku
and claude-* versus Codex gpt-*; do not guess ownership of unknown model names.
Keep manifest schema 1 and document common v3.8 following the v3.7 convention.

- [x] Add regressions and show force_codex/Claude agent model failing before the fix.
- [x] Apply the minimum guard; verify CLI overrides, non-forced routes and bad defaults.
- [x] Update v3.8 guide/changelog/evidence; regenerate common manifests and adopter payload.
- [x] Run full pytest (zero failures), Ruff, Codex parity and common manifest check.
- [x] Record final outputs, changed paths and remaining work; remove task scratch.

The predecessor cursor is preserved in `tasks/change_log.md` under
"Archived cursor: before executor common v3.8 (2026-10-02)".

Results: fail-first observed sonnet instead of gpt-category (`1 failed in 0.07s`).
Focused regression suite: `211 passed in 4.00s`. Full pytest: `1784 passed in
220.99s (0:03:40)`, zero failures. Ruff, Codex parity, common manifest and Python
3.11 compilation passed. Both requested generators passed. Evidence:
`tasks/reports/executor-common-fail-first.md`, "Common v3.8", and the matching
`tasks/change_log.md` entry. Final record refresh passed the exact-content/public-surface checks:
`9 passed in 0.35s`. The closing cursor update uses the same payload refresh and
checks. No requested implementation or acceptance item remains; no commit/tag/push,
consumer write, lock edit or `.codex/**` write occurred. Scratch is removed after
the closing checks.
```

#### tasks/intent.json

```
{
  "goal": "Fix executor temporary-directory test cleanup, malformed agent criteria, response-ID collisions and reader failures test-first; correct policy wording; verify all six items and commit common v3.5 locally.",
  "goal_type": "maintenance",
  "scope": "mir-yoke only; common executor edits and a local commit authorized by the owner follow-up. No consumer writes, push, tag, release, credentials or capability-pinned changes. tasks/plan.md is the intent and design authority.",
  "priority": "normal",
  "updated": "2026-10-02",
  "history": [
    {
      "goal": "Run the 2026-10-02 mir-core:repo-maintenance pass (all 21 items) on mir-yoke only under the owner instruction of 2026-10-02: re-verify prior fixes, check ADR-88 routing lock and mir_executor common v3.4 consistency, fix in-scope defects test-first, run documented gates, local commits of own files only.",
      "updated": "2026-10-02",
      "status": "complete"
    },
    {
      "goal": "Re-verify all twenty repo-maintenance checklist items against actual repository state and execution evidence, then minimally repair confirmed defects within this repository only.",
      "updated": "2026-09-23",
      "status": "superseded"
    },
    {
      "goal": "Strengthen mir-core:repo-maintenance to the owner-authorized twenty-one items in this repository only; prove regressions fail first and run full verification, leaving ADR-80 release binding to Mir Harness.",
      "updated": "2026-09-24",
      "status": "complete"
    },
    {
      "goal": "Implement the owner-approved mir_executor common base, optional local hooks/data and explicit sync/drift tooling test-first in mir-yoke only.",
      "updated": "2026-10-01",
      "status": "complete"
    }
  ],
  "status": "complete"
}
```

## Ontology phase B1 verification (2026-10-14)

Authority: `tasks/plan.md`, the single active cursor, and the owner request recorded in
`tasks/intent.json`. The contract distribution remains owner-controlled, version 1.0.0. Its exact
SHA-256 is recorded in `plugins/mir-core/skills/ontology/references/SOURCE.md`. The byte comparison
passed in the actual worktree. No contract bytes were edited.

Package findings: `src/mir/core/capabilities/manager.py` rejects Git mode 100755, symlinks and
submodules during export, and executable permission bits and symlinks during tree hashing.
Its role-plugin root/manifest allowlists forbid active root components, not inert files nested
inside skills. `_validate_plugin` imposes no extension restriction on nested scripts/references.
`tests/test_plugin_skill_packages.py` proves isolated package validation. ADR-89 section 2.3 and
ADR-90 sections 2.1/2.3 retain the active-component boundary. No hook, command or MCP registration
was added. The checker has mode 0644. Python and JSON assets are admitted without weakening rules.

Verification:

- Test-first checker run: 40 failures before implementation. Two malformed-contract regressions
  and one symlink-loop regression were also observed failing before their fixes.
- `uv run pytest -q tests/test_ontology_skill.py`: 45 passed in the actual worktree, including
  the byte-identical owner contract test, schema/value/ref boundaries, SemVer and Python 3.9 syntax.
- `uv run pytest -q tests/test_ontology_skill.py tests/test_template_asset_classification.py tests/test_advanced_reference_templates.py`:
  58 passed before the public-path-only test edit.
- `uv run pytest -q tests/test_ontology_skill.py tests/test_public_template_surface.py`:
  48 passed after that edit; owner-source comparison still passed.
- Marketplace version regression: observed failing with old marketplace entries, then passed after
  aligning all four entries to 0.11.0. Existing capability materialization regression also passed.
- Full `uv run pytest -q`: exit 1; 1830 passed, 1 skipped, 1 failed in 219.30 seconds. The only failure
  was `tests/test_capability_cli.py::test_repository_lock_is_portable_and_matches_managed_trees`,
  the expected pre-release lock mismatch. The skip was the owner-source comparison because the
  isolated public copy had no adjacent owner source; that test passed in the actual worktree.
- `uv run ruff check`: exit 0, all checks passed.
- `uv run python scripts/verify_codex_sync.py`: exit 1, only generated drift at
  `.codex/agents/ontology-validator.toml`.
- `python3 plugins/mir-core/skills/ontology/scripts/ontology_check.py contract`: exit 0,
  0 errors and 0 warnings. Host `python3` is 3.14.6; `/usr/bin/python3` is 3.9.6 and the same command
  also passed there. Valid mappings, the documentation example, and structured JSON/exit 2 for a
  symlink loop were separately exercised on Python 3.9.6.
- Final worktree metadata/public checks:
  `uv run pytest -q tests/test_ontology_skill.py tests/test_template_asset_classification.py tests/test_advanced_reference_templates.py tests/test_public_template_surface.py`:
  61 passed after the evidence and payload refresh. Ruff also passed again.
- `git diff --check`: passed before this evidence update and checked again at closeout.

All uv commands used the owner-specified shared cache. Full-suite isolation stayed inside this
repository: an ignored `.mir/runtime/` verification copy, scratch outside that copy, its dev
extras installed with `uv sync --extra dev`, and `GIT_CEILING_DIRECTORIES` at the scratch boundary
prevented fixtures from inheriting the real worktree. The 36 authored/metadata files matched the
completed test copy byte-for-byte before evidence updates. Earlier attempts exposed recursive
fixture copies, inherited Git discovery and missing isolated dev dependencies; those were corrected
without changing tests or package rules. A real marketplace-version omission and the new test's
public-path spelling were corrected before the final full run. Temporary artifacts are removed at
closeout. No daemon or emulator was started.

Remaining: Main must regenerate the ontology-validator Codex derivative, refresh the adopter
payload and rerun parity. Capability-lock binding and release delivery remain separate.
No commit, tag, push, capability apply/attest/finalize, user-plugin install or original `.codex/**`
write was performed. `uv.lock` changed only the local package version; the capability lock did not.

Changed files (36; repository-relative):

- `.claude-plugin/marketplace.json`.
- `.claude/agents/ontology-validator.md`.
- `CHANGELOG.md`.
- `MIGRATION.md`.
- `VERSION`.
- `config/adopter-payload.json`.
- `config/capability-sources.json`.
- `config/repo-agent-management.json`.
- `plugins/mir-code/.claude-plugin/plugin.json`.
- `plugins/mir-code/.codex-plugin/plugin.json`.
- `plugins/mir-code/skills/bluebricks/SKILL.md`.
- `plugins/mir-content/.claude-plugin/plugin.json`.
- `plugins/mir-content/.codex-plugin/plugin.json`.
- `plugins/mir-content/skills/knowledge/SKILL.md`.
- `plugins/mir-core/.claude-plugin/plugin.json`.
- `plugins/mir-core/.codex-plugin/plugin.json`.
- `plugins/mir-core/skills/design/SKILL.md`.
- `plugins/mir-core/skills/ontology/SKILL.md`.
- `plugins/mir-core/skills/ontology/references/SOURCE.md`.
- `plugins/mir-core/skills/ontology/references/common-contract.json`.
- `plugins/mir-core/skills/ontology/references/knowledge-supply.md`.
- `plugins/mir-core/skills/ontology/references/mapping-guide.md`.
- `plugins/mir-core/skills/ontology/scripts/ontology_check.py`.
- `plugins/mir-core/skills/selective-relations/SKILL.md`.
- `plugins/mir-core/skills/spec-architect/SKILL.md`.
- `plugins/mir-core/skills/verify/SKILL.md`.
- `plugins/mir-lifecycle-hooks/.claude-plugin/plugin.json`.
- `plugins/mir-lifecycle-hooks/.codex-plugin/plugin.json`.
- `pyproject.toml`.
- `scripts/verify_codex_sync.py`.
- `tasks/change_log.md`.
- `tasks/intent.json`.
- `tasks/plan.md`.
- `tests/test_ontology_skill.py`.
- `tests/test_plugin_skill_packages.py`.
- `uv.lock`.

### Implementation evidence

Registered the existing skill in the alphabetical mir-core inventory, knowledge category and parity set; package contracts expect seventeen skills and version 0.10.8. Updated the predecessor release/version surfaces, migration and upgrade guide. The lifecycle-hooks acknowledgement is generated from the repository dedicated `_validate_plugin(..., package_kind="skills-hooks")` validator and its tree digest; no hook content changed. Adopter payload generator: `uv run python -m tools.template_assets --write-adopter-payload` (with the owner-required UV_CACHE_DIR environment) (exit 0). No canonical derivative input changed, so no `.codex/**` regeneration or write is required.

### Initial verification and correction

Full `uv run pytest -q`: exit 1, `2 failed, 1785 passed in 229.01s`. The expected pre-bind failure is `tests/test_capability_cli.py::test_repository_lock_is_portable_and_matches_managed_trees`. The other failure, `tests/test_public_template_surface.py::test_should_expose_no_private_absolute_path_when_public_surfaces_are_scanned`, came from an absolute UV cache path written into this evidence log; the path is removed, retaining the command and required environment reference. Run the full suite again without bypassing or narrowing checks. Ruff: exit 0, `All checks passed!`. Codex sync: exit 0, `OK: Codex derivatives match Claude sources`. Both original untracked file hashes match their starting bytes.

### Final verification

All UV commands use the owner-required UV_CACHE_DIR environment.
- `uv run pytest -q`: exit 1; tail `1 failed, 1786 passed in 216.54s (0:03:36)`.
  Only `tests/test_capability_cli.py::test_repository_lock_is_portable_and_matches_managed_trees`
  fails at the plugin tree digest comparison (the accepted pre-release-bind test from the precedent).
- `uv run ruff check`: exit 0; tail `All checks passed!`.
- `uv run python scripts/verify_codex_sync.py`: exit 0; tail `OK: Codex derivatives match Claude sources`.
- `git diff --check`: exit 0.

Version 0.10.8 preparation and registration are complete. Final cursor/evidence updates are
followed by the documented adopter payload generator and exact-payload/public-surface checks.
The original skill and contract test hashes match; both are included in the generated payload.
No commits, pushes, tags, releases, other-repository writes, `.codex/**` writes or capability-lock
binding occurred. Binding and publication are left to the authorized release step.

## Superseded cursor: reference application profile preparation (2026-10-14)

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

Previous intent:

```json
{
  "goal": "Register the already-authored reference-app-profile skill exactly like repo-maintenance and release-prepare 0.10.8 in Mir Yoke only.",
  "goal_type": "maintenance",
  "scope": "Current owner request of 2026-10-11. Preserve the skill and contract test bytes; no commits, pushes, tags, releases, other-repository writes or generated .codex writes. tasks/plan.md is the active intent and design authority.",
  "priority": "normal",
  "updated": "2026-10-11",
  "history": [
    {
      "goal": "Fix executor temporary-directory test cleanup, malformed agent criteria, response-ID collisions and reader failures test-first; correct policy wording; verify all six items and commit common v3.5 locally.",
      "updated": "2026-10-02",
      "status": "complete"
    },
    {
      "goal": "Run the 2026-10-02 mir-core:repo-maintenance pass (all 21 items) on mir-yoke only under the owner instruction of 2026-10-02: re-verify prior fixes, check ADR-88 routing lock and mir_executor common v3.4 consistency, fix in-scope defects test-first, run documented gates, local commits of own files only.",
      "updated": "2026-10-02",
      "status": "complete"
    },
    {
      "goal": "Re-verify all twenty repo-maintenance checklist items against actual repository state and execution evidence, then minimally repair confirmed defects within this repository only.",
      "updated": "2026-09-23",
      "status": "superseded"
    },
    {
      "goal": "Strengthen mir-core:repo-maintenance to the owner-authorized twenty-one items in this repository only; prove regressions fail first and run full verification, leaving ADR-80 release binding to Mir Harness.",
      "updated": "2026-09-24",
      "status": "complete"
    },
    {
      "goal": "Implement the owner-approved mir_executor common base, optional local hooks/data and explicit sync/drift tooling test-first in mir-yoke only.",
      "updated": "2026-10-01",
      "status": "complete"
    }
  ],
  "status": "complete"
}
```


## Superseded cursor: ontology phase B1 (2026-10-15)

The phase-D request supersedes the completed phase-B1 cursor. Preserved cursor:

# Plan

## Active task: common semantic contract distribution, phase B1 (2026-10-14)

Authority: the current owner request recorded in `tasks/intent.json`; this is the single active
cursor and design authority. The superseded cursor and intent remain in `tasks/change_log.md`.

Outcome: ship `mir-core:ontology`, a byte-identical owner contract, generic mapping and knowledge
references, and a Python 3.9 standard-library checker. Prepare 0.11.0 without release binding.

Design: keep the project-owned mapping as JSON. Concepts are keyed by common concept id;
vocabularies, relations, questions, error cases and entrypoints are lists. References are repository
relative strings. Deterministic checks cover structure, declared compatibility and local references;
semantic interpretation, execution evidence and authority remain separate verification layers.
Package scripts are inert non-executable files, invoked explicitly with Python. No runtime hook,
automatic service connection or consumer write is introduced.

- [x] Confirm package rules and read the complete owner contract.
- [x] Write checker regression tests, run them failing, then implement and pass them.
- [x] Add generic skill/references, workflow pointers and bounded validator guidance.
- [x] Register the skill, refresh version/catalog metadata and prepare 0.11.0.
- [x] Run full pytest, Ruff, Codex parity and system Python contract checks; report evidence.

Constraints: write only here. Preserve canonical owner contract bytes. Do not commit, tag, push,
bind locks, apply/attest/finalize capabilities, change user installs or write generated `.codex/**`.
Full pytest may retain the named pre-release capability-lock failure. Agent-source changes may
require Main-owned derivative regeneration; report that state without bypassing parity checks.

Source work and required check execution are complete. Main must regenerate the ontology-validator
Codex derivative; release capability-lock binding remains outside this task. See
`tasks/change_log.md` under "Ontology phase B1 verification (2026-10-14)" for commands, results,
package rules, isolation details and the exact changed-file inventory.

## Ontology phase D adoption evidence (2026-10-15)

Baseline: `996e9fa21ef953950daa0a6f21d4617a42ea1680`, initial worktree clean.
Authority: phase-D owner request; `tasks/plan.md` is the active cursor/design authority.
The mapping describes Yoke itself, not consumer runtime state. It uses only public repository-relative
references. Contract distribution, versions, capability locks and generated runtime surfaces are unchanged.

### Domain comparison procedure and scope

First read canonical sources directly, before authoring the mapping. Then answer the same questions
through `questions`, `canonical_index`, domain identity schemes, relation mappings and vocabularies.
These are qualitative source-selection comparisons, not independent blind trials or runtime acceptance.
No false first-pass mistake is invented. All three answers agree; the mapping changes the retrieval
route and makes scope distinctions explicit, without demonstrated accuracy or timing improvement.

Q1: Which capabilities can code-only and content consumers adopt, and which remain project-owned?

- Without mapping: `config/capability-sources.json:52`, `config/capability-sources.json:116`,
  `ARCHITECTURE.md:63`, `docs/decisions/adr-90-role-plugins-and-common-hooks.md:47`.
- Answer: code_app selects core, code and lifecycle packages; content_workspace selects core,
  content and lifecycle packages. Both have their own selected agent/command lists. Agents and Claude
  commands are delivered separately; Codex command intent resolves namespaced plugin skills. Project
  instructions, policy and coupled hook/MCP adapters stay project-owned. The global lifecycle hook is
  the exact read-only exception. Profile selection does not authorize installation or consumer writes.
- With mapping: Q1 -> canonical capability source + ADR-90 + architecture; `profile aliases` and
  `plugin selected by profile` are local selection relations, not entity identity or ownership.
  Domain identifies supplier/consumer and plugin/pack identities. Same source evidence and same answer.
- Difference: no difference in the answer. The index supplies a bounded source route; no execution
  or adoption claim is inferred from selection. Historical spec is unnecessary to this question.

Q2: Can installed skills work without the provider checkout, and what proves runtime discovery?

- Without mapping: `docs/decisions/adr-89-dual-runtime-capability-management.md:55`,
  `scripts/verify_plugin_cli_activation.py:204`, `scripts/verify_plugin_cli_activation.py:234`,
  `src/mir/core/capabilities/manager.py#CapabilityManager.attest`,
  `src/mir/core/capabilities/manager.py#CapabilityManager.finalize`.
- Answer: the supported design is host-installed namespaced skills independent of the provider
  checkout and consumer CWD. The verifier renames its provider unavailable and compares installed
  digests/inventories from consumer roots. Real activation additionally requires CLI installation
  evidence, expected skill/hook observations in fresh sessions from both required runtimes and guarded
  finalization. Source selection, package hash and catalog declaration alone do not establish it.
  Actual live discovery in this unit is unverified; the real-CLI probe is not executed here.
- With mapping: Q2 -> canonical ADR-89 + attest implementation + activation verifier; domain separates
  distribution from activation; vocabulary separates attested, verified, active and incomplete.
  Same sources and same answer, including the live-observation limit.
- Difference: no difference in the answer. The mapping explicitly preserves declared-versus-executed
  and byte-identity-versus-truth distinctions. No installed READY claim is made.

Q3: Does shared executor delivery preserve adapters and reject dirty/unsafe delivery?

- Without mapping: `tools/executor_sync.py:23`, `tools/executor_sync.py:45`,
  `tools/executor_sync.py:90`, `docs/operations/mir-executor-sync.md:63`,
  `tools/mir_executor/COMMON_MANIFEST.json`.
- Answer: sync acts on one explicit target, copies only manifest-selected common files plus the
  consumer manifest, excludes local.py and tests/local, leaves local config/policy untouched, refuses
  dirty selected paths and symlinks, and rejects stale source hashes. Source commit identifies the
  delivered provider revision; manifest version 1 is schema version, not executor product version.
  This unit's read-only manifest check passes; target delivery and dirty/symlink regression execution
  are not claimed.
- With mapping: Q3 -> executor source and operations guide; domain identity schemes distinguish
  source commit/file SHA256/schema version; derived_from describes target manifest provenance.
  Same source evidence and same answer.
- Difference: no difference in the answer. The map narrows impact to common manifest-selected files;
  it does not establish a consumer write permission or executed delivery.

### Error-case coverage

Coverage is deliberately scoped. A format pass is not semantic, runtime or authorization completion.
No new regression test: missing semantic guards have no existing enforcing implementation to exercise.

| Case | Status | Actual local exercise or reason |
| --- | --- | --- |
| E01 | planned | Namespace mismatch fixture exists, but no cross-project entity-merge isolation test. |
| E02 | planned | Traversal tests exist; generic common endpoint/type/scope validation is not enforced. |
| E03 | covered | `tests/test_decision_authority.py#test_should_route_centralization_decisions_to_history_when_reading_current_authority`; decision authority routing only. |
| E04 | planned | No direct guard against reporting a declared verified_by as passed; runtime attestation is different. |
| E05 | planned | No general similarity/inference-to-identity guard. |
| E06 | covered | `tests/test_relations.py#test_current_graph_is_reloaded_and_source_digest_changes`; edited graph reloads and digest changes. |
| E07 | covered | `tests/test_public_template_authority.py#test_should_expose_only_single_root_explicit_apply_mutation_flags`; CLI no-apply default only. |
| E08 | not_applicable | No personal knowledge plane/binding in this supplier unit; sensitive bodies and protected memory excluded. |
| E09 | not_applicable | No knowledge-service binding/dependency in this unit; later binding must revisit outage behavior. |
| E10 | covered | `tests/test_ontology_skill.py#test_invalid_mapping_fails_with_specific_message`; contract/mapping version and range mismatches only, not installed plugin-version alignment. |

### Executed checks

uv commands used a host-local cache directory (`UV_CACHE_DIR`).
Scratch is repository-local `.mir/ontology-adoption-check-tmp`, removed after checks. The parity
checker used its own generator in disposable output only; it did not regenerate root derivatives.

- `python3 plugins/mir-core/skills/ontology/scripts/ontology_check.py mapping --repo .`
  -> initial missing ADR-82 ref corrected; final `0 errors, 0 warnings; contract 1.0.0, mapping 1.0.0`, exit 0.
- `python3 plugins/mir-core/skills/ontology/scripts/ontology_check.py contract`
  -> `0 errors, 0 warnings; contract 1.0.0, mapping None`, exit 0.
- `TMPDIR="$PWD/.mir/ontology-adoption-check-tmp" uv run pytest -q -p no:cacheprovider --basetemp="$PWD/.mir/ontology-adoption-check-tmp/pytest" tests/test_ontology_skill.py tests/test_decision_authority.py tests/test_public_template_authority.py::test_should_expose_only_single_root_explicit_apply_mutation_flags tests/test_relations.py::test_current_graph_is_reloaded_and_source_digest_changes tests/test_session_upfront_context.py tests/test_public_template_identity.py`
  -> 67 passed in 1.78s, exit 0. Existing regression code unchanged.
- `uv run python scripts/verify_context_paths.py CLAUDE.md ARCHITECTURE.md tasks/plan.md`
  -> PASS: checked 3 files and 35 path references, exit 0.
- `uv run python scripts/verify_context_paths.py`
  -> PASS: checked 9 files and 75 path references, exit 0.
- `TMPDIR="$PWD/.mir/ontology-adoption-check-tmp" uv run python scripts/verify_codex_sync.py`
  -> exit 1: `FAIL: generated drift: AGENTS.md`. Sole reported drift is expected after adding the
  canonical rule. No root .codex file or other generated derivative was changed.
- `python3 -B tools/executor_sync.py --target . --check` -> `Common manifest: PASS`, exit 0.
- `git check-ignore -v .mir/ontology-map.json` -> no matching rule (exit 1); no .gitignore edit needed.
- `git diff --check` -> initial archival trailing blank line repaired; final result recorded below.

### Delivery and remaining work

Changed: `.mir/ontology-map.json`, `CLAUDE.md`, `ARCHITECTURE.md`, `tasks/intent.json`,
`tasks/plan.md`, `tasks/change_log.md`. No production code, tests, distributed contract, versions,
locks or root generated derivatives changed. No commit, publish, service action, target delivery or
live DB operation. Memory Keeper is explicitly not_connected; binding belongs to a later unit.

Main must run `bash scripts/generate_codex_derivatives.sh` and rerun parity under its own write
scope. This generator writes .codex/**, which the phase-D worker is explicitly prohibited from writing;
therefore worker regeneration is pending, not a passed parity claim. The real-CLI activation probe
and executor sync regression suite create fixture Git commits; neither was run under the no-commit
instruction. Current host discovery and delivered consumer behavior remain unverified here.
E01/E02/E04/E05 remain planned; the covered cases above do not promise general semantic enforcement.

Final closeout: mapping checker again returned 0 errors / 0 warnings; `git diff --check` passed.
Repository-local check scratch was removed. Final status contains exactly the six delivery files above.
The final cursor check initially rejected a backtick path with a heading fragment; the pointer was
changed to the file path plus the named heading. Recheck passed for 3 files and 37 references.

2026-10-15: Owner-directed map reduction: 31,821 -> 12,268 bytes; mapping checker 0 errors / 0 warnings; canonical refs, questions, domain identities/invariants and all covered check refs preserved; ambiguous vocabulary and essential relation mappings retained.

## Superseded cursor: ontology phase D closeout (2026-10-15)

# Plan

## Active task: Yoke ontology adoption, phase D (2026-10-15)

Authority: the current phase-D owner request recorded in `tasks/intent.json`; this is the single
active cursor and design authority. Superseded phase-B1 detail remains in `tasks/change_log.md`.
Baseline: `996e9fa21ef953950daa0a6f21d4617a42ea1680`; clean initial worktree.

Outcome: a project-owned mapping of Yoke's supplier model to contract 1.0.0, two selective
usage entrypoints, three evidenced domain comparisons and honest E01–E10 coverage.
Design: reference current supported-surface definitions first; label retained spec and maintainer
contracts explicitly. Keep local identities, vocabularies and state machines. Installation,
declaration, byte integrity, runtime observation and write authority remain separate.

- [x] Re-read authority, Profile, canonical definitions and existing checks; answer cold questions.
- [x] Add mapping and selective pointers; review endpoints and public relative refs.
- [x] Run mapping, context-path, instruction/parity and scoped invariant checks.
- [x] Record question comparisons, coverage, results and Main-owned regeneration pending.

Constraints: repository-only writes; no commits, push, version bumps, lock binding, release,
services, live DB or sensitive bodies. Do not write generated `.codex/**`. The documented generator
writes that scope, so regeneration is deferred to Main. Checker success is format evidence only.

Repository-local mapping and evidence work are complete. Harness Main regenerated the derivatives,
trimmed CLAUDE.md back to its 3600-byte budget (ontology pointer merged into the Sources line), refreshed
`config/adopter-payload.json`; codex sync OK; full suite 1833 passed, 1 expected failure (capability lock
not bound until release). Evidence and remaining semantic coverage are recorded in
`tasks/change_log.md` under "Ontology phase D adoption evidence (2026-10-15)". Memory Keeper binding is deferred.

## Superseded cursor: covered-check resolution and MK guide (2026-10-15)

# Plan

## Active task: covered-check resolution and MK consumer guide (2026-10-15)

Authority: current Harness central-run owner request (Discord decision "1, 2"), recorded in
`tasks/intent.json`. This is the single active cursor and design authority.

Outcome: covered checks resolve real repository-local files, lines and names; the public MK
consumer guide matches the implemented stdio tools and ContextPack fields.
Design: reuse safe ref resolution, tighten only covered checks, preserve the owner contract,
and follow MK code over the stale lifetime-reader statement in its consumer contract.

- [x] Prove new covered-ref regressions fail before implementation.
- [x] Implement checks and compact interface-based consumer guidance.
- [x] Refresh adopter payload; run focused tests, parity and all 16 read-only map checks.
- [x] Record results, changed files and Main-owned work remaining.

Constraints: repository-only writes; no commits, installs, services, database access, credentials,
or generated `.codex/**` writes. Other repositories are read-only evidence sources.

Completed: fail-first 8 failed / 60 passed; checker 68 passed; affected package, asset/payload
and reference checks 91 passed. Codex parity is current; no regeneration was needed.
All 16 read-only map checks ran: 15 clean, quietleaf E10 has 1 error and 1 warning.
The consumer correction is out of scope. Evidence: `tasks/change_log.md`,
"Covered-check resolution and MK guide (2026-10-15)".
## P2 ontology executable consumer paths (2026-10-15)

Authority: current P2 request, recorded in `tasks/intent.json`; design authority:
`tasks/plan.md`. Implementation is bounded to this repository.

Implemented:
- Validated mapping version >=1.1.0 requires nonempty common-concept endpoint arrays or
  a scalar wildcard, constrained by the loaded relation. Local-only and 1.0.0 relations
  retain their behavior. 1.1.0 optional binding values are validated; legacy binding refs remain.
- `impact` selects affected entries and covered checks by changed/shared ref paths, checks
  stale refs, and requests map revalidation. It never executes checks. Git selection unions
  staged-versus-base and unstaged paths, retaining deletions/renames and cancelling edits.
  JSON errors and invalid map structure remain reportable with strict exit 1.
- `lookup` returns bounded term-matching questions, concepts and domain identities with evidence.
- `mk_query.py` uses only stdlib and host-local launch config, MCP stdio initialize/initialized/
  tools-call, structured or text JSON results, explicit feedback and telemetry-only client names.
  Soft failure preserves unrelated local work; every owned child is terminated/reaped, including
  initialization/serve timeouts. POSIX process groups also cover launchers. Refusals are preserved.
- Public skill/mapping/supply guidance and exact adopter inventory are updated. No install,
  version change, contract edit, generated Codex write, real MK launch, database access or commit.
- Package test explicitly models its provider root so repository-local scratch is valid, while
  preserving checks rejecting provider paths and symlinked/out-of-runtime installations.

Fail-first receipts:
- Initial ontology run: 43 failed / 68 passed before implementing the new commands and endpoints.
- Extra invalid-JSON/nonobject/null-list, wildcard-array and empty-response cases: 6 failed.
- Cancelling staged/unstaged changes: 1 failed before unioning the two Git diffs.
- Planned-check symbol resolution, refusal with empty nodes, and legacy binding gating each
  failed before their corrections. All corresponding regressions now pass.
- Package/payload run before payload regeneration and fixture isolation: 3 failed / 148 passed
  (owner contract parity, provider-root assumption, stale payload). Provider-root and payload
  failures are fixed; the owner parity failure remains intentionally visible.

Verification (all uv invocations use the owner-requested external UV_CACHE_DIR; scratch stays
under repository-local ignored pytest cache):
- `uv run pytest -q tests/test_ontology_skill.py` (repo-local basetemp, short traceback):
  123 passed / 1 failed, 7.13s. Only `test_contract_distribution_is_byte_identical_to_owner`
  fails: Yoke's protected-by-request distribution is 1.0.0, while the parallel owner source
  is now 1.1.0. This is an honest pending delivery check, not a skipped or weakened assertion.
- `uv run pytest -q tests/test_plugin_skill_packages.py tests/test_common_skill_contracts.py`:
  21 passed, 0.13s. Package-only rerun after preserving unrelated formatting: 10 passed, 0.11s.
- `uv run pytest -q tests/test_template_asset_classification.py`: 6 passed, 0.33s after refresh.
- `uv run python -m tools.template_assets --write-adopter-payload`: pass.
- `uv run python -m tools.template_assets --json`: 877/877 classified; no unknown,
  duplicate or prohibited assets. New script/fixture are automatically classified.
- `uv run python scripts/verify_codex_sync.py`: exit 0,
  `OK: Codex derivatives match Claude sources`; no regeneration or generated writes.
- `uv run ruff check` on checker, client, fixture and both changed Python test files: pass.
- `git diff --check`: pass. New scripts are regular nonexecutable mode 0644.
- Independent read-only review found planned-check and legacy-binding defects; both were
  corrected with regressions. The final source review reported no unresolved concrete finding.

Actual read-only command receipts follow. The Harness lookup explicitly selects the owner
1.1.0 contract so its newer map is checked against the correct distribution. No consumer writes.

Command (exit 0):

```sh
uv run python plugins/mir-core/skills/ontology/scripts/ontology_check.py impact --repo . --git-diff HEAD~3
```

```text
affected entries:
  /concepts/Task: tasks/plan.md, src/mir/core/contracts/task_spec.py
  /error_cases/9: tests/test_ontology_skill.py#test_invalid_mapping_fails_with_specific_message
  /vocabularies/9: tasks/intent.json
checks to run (selection only):
  tests/test_ontology_skill.py#test_invalid_mapping_fails_with_specific_message
stale refs:
map changed: re-validate
```

Command (exit 0):

```sh
uv run python plugins/mir-core/skills/ontology/scripts/ontology_check.py lookup --repo . 'capability authority' --limit 3
```

```text
mir.common-semantics 1.0.0
/concepts/Capability: {"status": "mapped", "local": [{"name": "Capability selection", "ref": "config/capability-sources.json"}]}
  evidence: config/capability-sources.json
/concepts/Decision: {"status": "mapped", "local": [{"name": "ADR authority", "ref": "docs/decisions/INDEX.md"}]}
  evidence: docs/decisions/INDEX.md
/concepts/Assessment: {"status": "mapped", "local": [{"name": "ValidationResult", "ref": "src/mir/core/contracts/gate.py#ValidationResult"}, {"name": "Capability health", "ref": "src/mir/core/capabilities/manager.py#CapabilityManager.status"}]}
  evidence: src/mir/core/contracts/gate.py#ValidationResult, src/mir/core/capabilities/manager.py#CapabilityManager.status
```

Command (exit 0):

```sh
uv run python plugins/mir-core/skills/ontology/scripts/ontology_check.py lookup --repo "$HARNESS_ROOT" --contract "$HARNESS_ROOT/config/ontology/common-contract.json" 'capability authority' --limit 3
```

```text
mir.common-semantics 1.1.0
/concepts/Capability: {"status": "mapped", "local": [{"name": "catalog skills, agents, commands", "ref": "config/repo-agent-management.json"}, {"name": "copied executor manifest", "ref": "tools/mir_executor/COMMON_MANIFEST.json"}]}
  evidence: config/repo-agent-management.json, tools/mir_executor/COMMON_MANIFEST.json
/domain/invariants/2: {"id": "observations-grant-no-write-authority", "ref": "ARCHITECTURE.md", "check": "tests/test_control_plane_contract.py"}
  evidence: ARCHITECTURE.md, tests/test_control_plane_contract.py
/questions/1: {"id": "Q2", "question": "Does a capability belong to Yoke, Harness-local tooling or a consumer, and which delivered version applies?", "evidence": ["config/repo-agent-management.json", "tools/mir_executor/COMMON_MANIFEST.json", "ARCHITECTURE.md"]}
  evidence: config/repo-agent-management.json, tools/mir_executor/COMMON_MANIFEST.json, ARCHITECTURE.md
ERROR /relations/4/from/0: endpoint not allowed
ERROR /relations/4/to/0: endpoint not allowed
ERROR /relations/5/from/0: endpoint not allowed
ERROR /relations/6/from/0: endpoint not allowed
```

The Harness result includes four endpoint errors at `/relations/4/from/0`,
`/relations/4/to/0`, `/relations/5/from/0`, `/relations/6/from/0`: those entries
use arrays containing `"*"`, while the supplied contract text permits arrays of concept IDs
or a scalar `"*"`. The Harness owner must resolve them; external files were not changed.
Lookup returns navigation results with validation findings and does not claim map validity.

Changed delivery files:
- `plugins/mir-core/skills/ontology/SKILL.md`
- `plugins/mir-core/skills/ontology/references/mapping-guide.md`
- `plugins/mir-core/skills/ontology/references/knowledge-supply.md`
- `plugins/mir-core/skills/ontology/scripts/ontology_check.py`
- `plugins/mir-core/skills/ontology/scripts/mk_query.py` (new)
- `tests/test_ontology_skill.py`
- `tests/test_plugin_skill_packages.py`
- `tests/fixtures/ontology_mcp_server.py` (new)
- `config/adopter-payload.json`
- `tasks/intent.json`, `tasks/plan.md`, `tasks/change_log.md`

Main-owned follow-up: copy the owner 1.1.0 contract byte for byte, update its SOURCE digest,
refresh the adopter inventory after those changes and rerun parity/full requested tests;
regenerate Codex derivatives only if its source changes demand it; choose the version bump.
Resolve the reported Harness mapping findings through its writer. Real host configuration,
real MK access and consumer rollout were explicitly outside this sandbox task. No standing
consumer authority, install, commit, push, tag or release is implied.

Final boundary regression: deleting the map initially returned IO exit 2; its new test failed
first. Impact now reports the missing map and revalidation with normal exit 0 / strict exit 1,
while the existing mapping command retains its IO exit behavior. Final ontology-only command:
`uv run pytest -q tests/test_ontology_skill.py --basetemp=.pytest_cache/p2-ontology-final --tb=short`
returned 124 passed / 1 owner-distribution parity failure in 7.18s. The aggregate focused result
is 151 passed / 1 pending owner-parity failure (124 ontology + 21 package/common + 6 asset passes).
The final bounded scratch directories were removed; no fake MCP child remains after the
lifecycle assertions. No production service, database, credentials or generated Codex file was used.

## Superseded cursor: P2 executable paths before P4 (2026-10-15)


Authority: the current P2 owner request recorded in `tasks/intent.json`; this is the single
active cursor and design authority. The prior completed cursor is preserved in `tasks/change_log.md`.

Outcome: version-gated endpoint validation; bounded impact/check selection and lookup; an
on-demand stdlib MCP client with failure independence, fake-server lifecycle evidence and public docs.
Design: extend the existing checker without full-tree scans; select checks but never execute them;
load host-local MK configuration explicitly and bound/reap every child. Preserve 1.0.0 mappings.

- [x] Add regressions and record fail-first evidence for endpoints, impact, lookup and MK.
- [x] Implement consumer commands and update supported public guidance.
- [x] Refresh adopter payload; run focused/package/asset checks, lint and read-only parity.
- [x] Exercise Yoke impact/lookup and read-only Harness lookup; record output and remaining Main work.

Constraints: write only here; no commits, push, release, installation, real MK or databases;
never read credentials or edit `.codex/**` or the owner-distributed common contract. Main owns
the contract copy, generated derivatives and version bump. Use the external uv cache.

Bounded P2 implementation and requested checks are complete. Evidence and exact impact/lookup
receipts: `tasks/change_log.md`, "P2 ontology executable consumer paths (2026-10-15)".
The ontology tests have 124 passes and one pending owner-contract byte-parity failure;
package/common tests have 21 passes and asset tests have 6 passes. Codex parity and lint pass.
Main still owns the 1.1.0 contract copy/SOURCE digest, any required derivative regeneration,
version choice and consumer rollout. Read-only Harness lookup exposed four wildcard-array
endpoint errors; its writer must resolve them. No real MK or database was opened.

## Superseded cursor: completed P4 before Closure W2 (2026-10-15)

# Plan

## Active task: P4 ontology work path (2026-10-15)

Authority: current P4 owner request in `tasks/intent.json`; this is the single active
cursor and design authority. Prior P2 cursor is preserved in `tasks/change_log.md`.

Outcome: map 1.1.0 validates at 0/0 within 12,288 bytes; pytest runs mapping and strict
Git impact; a thin checkout runner connects optional MK lookup; no planned errors remain.
Design: reuse released scripts unchanged; exercise own-map failures in an independent
committed Git fixture. No generated writes, live MK, databases, commits or delivery.

- [x] Add fail-first runner/gate and missing-config regressions.
- [x] Connect runner, map and instructions within budgets.
- [x] Run full pytest, lint, checker and read-only derivative parity; record evidence.

Completed at the code/test boundary. Final full-suite process exited 0; exact receipts,
scoped error statuses and the separately observed derivative update are in `tasks/change_log.md`.
No live MK or delivery operation is authorized or needed for this bounded task.

## Closure W2 implementation and fail-first evidence (2026-10-15)

Authority: current W2 owner request in `tasks/intent.json`; design/cursor: `tasks/plan.md`.
This extends completed P4. Scope is the named audit rows 5-2.9a, E10, 5-4.9,
5-3.10a and section 6 D at Yoke's code/test boundary. No consumer rollout is claimed.

Implementation:
- Applied the exact `mk_query.py` patch and regression from branch commit `36131bd`.
  No Git merge/commit was attempted under the sandbox's explicit no-commit instruction.
  Retained its Unreleased Fixed wording; released sections and versions are unchanged.
- Added the canonical Python 3.9 stdlib consumer runner and copy/update guidance. It prefers
  explicit overrides, checks both runtime records in both homes, refuses active disagreement,
  missing paths and ambiguous unpinned Codex caches, and warns only on no-active fallback.
  Real Codex metadata has enabled=true without a version; its sole cache is unambiguous.
- Extended the existing shared ref resolver to validate symbol declarations, test names,
  Markdown headings, structured JSON keys and TOML keys/tables in every declared ref field,
  including local domain extensions. Comments/prose do not establish symbols. Covered checks
  retain line-bound checks and dotted last-segment compatibility. Mapping reports informational
  line_ref_count; strict Git impact rejects line refs into changed files.
- Re-anchored all three own-map line refs; size 12,274 bytes, no legacy lines remain.
  Documented the distinct checkout runner and byte-identical consumer runner.

Fail-first commands (all uv commands use the owner-specified external UV_CACHE_DIR):
- `uv run pytest -q tests/test_ontology_skill.py -k 'sandbox_denies or unresolved_symbols_in_every or declarations_and_reject or legacy_lines_as_information or empty_or_unresolved or reanchor_changed' --basetemp=.pytest_cache/w2-red --tb=short`
  returned 41 failed / 127 deselected before checker/EPERM implementation.
- Worker ran all original runner regressions against the exact prior newest-cache consumer:
  `uv run pytest tests/test_ontology_runner.py -q --basetemp=.pytest_cache/ontology-runner-all-red --tb=no`:
  24 failed / 0 passed. Restored implementation: 24 passed.
- Review exposed quoted-comment symbol false positives. Expanded removed-symbol cases and added
  a Python-comment regression: `uv run pytest -q tests/test_ontology_skill.py -k 'declarations_and_reject or python_comments' --basetemp=.pytest_cache/w2-review-red --tb=no`:
  24 failed / 145 deselected before the suffix/JSON fix; then focused checker/gate/runner: 201 passed.
- SemVer edge regressions (empty identifiers/numeric prerelease leading zeros): selected 9 tests
  failed against both the intermediate runner and a scratch copy of the prior consumer.
  Final worker runner suite: 33 passed. Every one of the 75 new test cases failed before its fix.
- Read-only independent review found these two issues; both were corrected and reread with no
  outstanding finding. Python 3.9 grammar, release/prerelease ordering and structural keys passed.

Initial full-suite attempt and comparison (not a passing gate):
- `TMPDIR=$PWD/.pytest_cache/w2-tmp uv run pytest -q --basetemp=.pytest_cache/w2-full --tb=short`
  was interrupted with exit 130 after 289 passed / 2 failed in 223.65s. Existing broad ROOT-copy
  fixtures included the nested scratch tree and live database filenames; the recursive copy
  made this unsafe to continue. The initial fixture may have copied the live memory file;
  no SQLite connection/query or live intake was run. The owned temporary tree was removed.
- One failure was NEW plugin-tree digest drift from W2 edits. HEAD's archived public plugins
  matched all four original lock digests. Refreshed only local managed mir-core SHA256 using
  the existing _tree_digest; no source pin, version, registration or installed state changed.
- The other was the broad-copy fixture. HEAD's original AST has no ignore filter; an isolated
  synthetic reproduction copied scratch and a DB-named sentinel without reading any live DB.
  Both whole-root fixtures now exclude scratch, VCS/venv/bytecode, secret names and DB names.
  Their existing tests pass: 2 passed / 103 deselected in 4.96s. Git-diff fixtures are committed
  independent repositories; the two earlier write-tree fixtures now also commit their baselines.
- Intermediate failures in old expected JSON shape/document-name fixtures, planned-symbol fixture
  and the first oversized own-map candidate were caused by these edits and repaired, not labeled
  pre-existing. Final own map directly passed mapping at 0/0 and strict impact with no stale refs.

Read-only real-home `python3 plugins/mir-core/skills/ontology/scripts/mir_ontology_runner.py --which`:
version: 0.12.0
path: ~/.claude/plugins/cache/mir-yoke/mir-core/0.12.0/skills/ontology/scripts/ontology_check.py
reason: active Claude record

Full Ruff and read-only Codex sync passed before final review fixes; final rerun follows below.
No generated derivative was written; parity needs no regeneration unless Main changes upstream
instruction sources later. Adopter payload is refreshed for candidate source bytes.
Final full-suite, final lint/sync receipts and closeout remain pending at this entry.

### W2 full-suite comparison and remaining verification boundary

The first complete run (`uv run pytest -q --basetemp=.pytest_cache/w2-full-final --tb=short`,
with repository-local TMPDIR and the owner-specified external UV_CACHE_DIR) returned exit 1:
**1989 passed / 8 failed in 326.11s**. All 75 new cases passed in that run.
One failure was NEW: a literal host cache path in this evidence entry violated public sanitization.
HEAD's log was clean; the new literal was removed and the candidate inventory refreshed.
Public-surface, classification and reference-template checks then returned 16 passed in 0.62s.

The other seven failures were reproduced against byte-identical HEAD tests and production code
under the same repository-local temporary-path constraint:
- `tests/test_project_agent_kit_release_evidence.py::test_release_evidence_requires_one_claude_and_one_codex_run`
- `tests/test_project_agent_kit_release_evidence.py::test_release_evidence_recomputes_artifact_hashes`
- `tests/test_project_agent_kit_release_evidence.py::test_release_evidence_rejects_unobserved_git_configuration`
- `tests/test_project_agent_kit_release_evidence.py::test_release_evidence_rejects_missing_memory_rehydration_observation`
- `tests/test_project_agent_kit_release_evidence.py::test_observer_rejects_a_hook_that_skips_missing_memory`
- `tests/test_project_agent_kit_release_evidence.py::test_release_evidence_rejects_sensitive_runtime_transcript`
- `tools/mir_executor/tests/test_hooks_v2.py::test_should_refuse_non_git_selected_root`

The six clean-room tests fail before running a target because `prepare` rejects an existing Git
worktree; observer state must also be outside the provider. The executor test's supposed non-Git
sibling inherits the outer repository. These are HEAD-reproduced failures for this temporary layout,
not a claim that HEAD fails when tested outside a worktree. Source equality was asserted using
Git's HEAD file contents for the entire clean-room test module, both observer/verifier helpers,
the executor test module and executor CLI. Selected reruns returned 6 failed / 25 deselected
and 1 failed with the same messages. No product check was weakened, skipped or marked xfail.
A fully green gate needs owner-authorized scratch outside the repository; this task forbids it.

The earlier broad-copy comparison was strengthened: a synthetic dangling scratch link reproduces
HEAD's copytree IOError, while the current filter passes on the identical synthetic tree and omits
the DB-named sentinel. The local managed lock change is exactly one SHA256 value; all four current
plugin trees match it and all four HEAD trees match the original lock.

Main independently reran all final new cases against baseline copies without swapping canonical
files: 42 checker/EPERM cases failed against HEAD, and 33 runner cases failed against the prior
newest-cache consumer. Thus the complete final set of 75 cases has direct fail-first evidence.
No new code failure is being labeled pre-existing. Final complete-run receipt follows below.

Final CLI compatibility inspection added trailing `--soft` support for MK feedback as well as
query. The selected regression failed before this last fix (1 failed / 3 passed / 30 deselected),
then the runner suite passed 34 cases. Parent's baseline-copy rerun failed all 34 cases.
The final set is therefore 76 new fail-first cases (42 checker/EPERM and 34 runner).
The in-progress closeout rerun was interrupted with exit 130 to include this last case in the
next complete collection; no complete-run count is claimed for that interrupted process.
Ruff passed after the fix; refreshed only the same local mir-core digest and candidate inventory.

### W2 final receipt and changed files

Final complete invocation (owner-specified external UV_CACHE_DIR throughout):
`TMPDIR=$PWD/.pytest_cache/w2-final-tmp uv run pytest -q --basetemp=.pytest_cache/w2-full-final-verified --tb=short`
returned exit 1: **1991 passed / 7 failed in 225.51s**. The failures are exactly the seven
HEAD-reproduced, repository-local temporary-layout cases listed above. The gate is not green.
All 76 new regression cases passed in this full run.

A last assignment-boundary probe failed first because the quoted-TOML-key branch also accepted
an equality expression. Added the same negative lookahead already used by ordinary assignments:
`anchor_name == other` now fails resolution, while `anchor_name = other` resolves.
The final affected command after that one-character-pattern correction was:
`uv run pytest -q tests/test_capability_cli.py::test_repository_lock_is_portable_and_matches_managed_trees tests/test_ontology_skill.py tests/test_mir_ontology.py tests/test_ontology_runner.py --basetemp=.pytest_cache/w2-final-focus --tb=short`:
**212 passed in 16.52s**, exit 0.

Other final evidence:
- `uv run ruff check`: All checks passed, exit 0.
- `uv run python scripts/verify_codex_sync.py`: OK: Codex derivatives match Claude sources, exit 0.
- `uv run python scripts/mir_ontology.py mapping`: INFO 0 line-number refs; 0 errors, 0 warnings;
  contract 1.1.0, mapping 1.1.0, exit 0. Own map remains 12,274 bytes.
- `uv run python scripts/mir_ontology.py impact --git-diff HEAD --strict`: no stale refs, exit 0;
  selected checks only and requested map re-validation.
- `python3 plugins/mir-core/skills/ontology/scripts/mir_ontology_runner.py --which`: version 0.12.0,
  path `~/.claude/plugins/cache/mir-yoke/mir-core/0.12.0/skills/ontology/scripts/ontology_check.py`
  (home prefix normalized here), reason `active Claude record`, exit 0.
- Python 3.9 grammar: runner, checker and MK client pass. Configured document budgets pass.
- `git diff --check`: clean. `mk_query.py` bytes equal branch commit 36131bd exactly.
- Public-surface/classification/reference-template checks after removing the new literal host
  path: 16 passed. Final candidate inventory is regenerated after these durable record updates.

Changed files (17):
- `.mir/capability-lock.json` (only local mir-core tree SHA256)
- `.mir/ontology-map.json`
- `CHANGELOG.md` (Unreleased only)
- `config/adopter-payload.json`
- `docs/operations/ontology-verification.md`
- `plugins/mir-core/skills/ontology/SKILL.md`
- `plugins/mir-core/skills/ontology/references/mapping-guide.md`
- `plugins/mir-core/skills/ontology/scripts/mir_ontology_runner.py` (new)
- `plugins/mir-core/skills/ontology/scripts/mk_query.py`
- `plugins/mir-core/skills/ontology/scripts/ontology_check.py`
- `scripts/mir_ontology.py`
- `tasks/change_log.md`
- `tasks/intent.json`
- `tasks/plan.md`
- `tests/test_capability_security.py` (safe existing ROOT-copy fixtures)
- `tests/test_ontology_runner.py` (new)
- `tests/test_ontology_skill.py`

Remaining: Main needs owner-authorized scratch outside the repository to obtain a green gate for
the seven unchanged tests. The cursor/intent is blocked only on that verification boundary.
No generated derivative currently needs regeneration; no generated instruction/runtime artifact
was written. Main retains release/version binding, actual branch merge/commit, installed-plugin
updates and byte-identical consumer rollout. No commit, push, tag, release, restart, live intake
or MK call was performed. The earlier broad-copy caveat remains material: it may have copied
the live memory file before interruption; no SQLite connection/query was run. Owned test scratch
is removed at closeout; shared uv cache is preserved.


## Superseded cursor: Closure W2 before W2b (2026-10-15)

```markdown
# Plan

## Active task: Closure W2 (2026-10-15)

Authority: current W2 owner request in `tasks/intent.json`; this is the single active
cursor and design authority. The completed P4 cursor is preserved in `tasks/change_log.md`.
The explicit W2 follow-up extends completed P4; it does not reopen delivery authority.

Outcome: active-runtime consumer distribution selection, resolvable symbol refs and strict
changed-line rejection, own map 0/0 under 12,288 bytes, and EPERM-safe child cleanup.
Design: one portable runner copied byte-identically by consumers; reuse the common ref resolver
for covered and ordinary refs; apply the EPERM branch patch without a merge commit.

- [x] Prove runner, symbol and EPERM regressions fail before implementation.
- [x] Implement bounded canonical changes, re-anchor own map, update public guidance/Unreleased.
- [x] Run full pytest, ruff, read-only Codex sync, own mapping/impact and real runner --which.
- [x] Record exact evidence and Main-owned regeneration/delivery follow-up.

No generated writes, live MK/databases, services, commits, pushes, tags, releases or consumer writes.

Code boundary complete; a fully green verification gate is blocked by repository-only scratch.
Final full pytest: 1991 passed / 7 HEAD-reproduced layout failures. Final affected checks: 212 passed.
Ruff, Codex parity, own mapping 0/0, strict impact, Python 3.9 grammar and document budgets pass.
Main must rerun the seven outside-worktree checks with authorized external scratch. No generated
derivative currently needs regeneration. No merge commit or consumer/version delivery was performed.
The initial broad-copy fixture may have copied the live memory file before its unsafe scope was
noticed; it was stopped and hardened. No SQLite connection/query or live intake was run.
Exact commands, comparisons and changed-file inventory: `tasks/change_log.md`, Closure W2.
```


## Closure W2b anchor compatibility and verification (2026-10-15)

Authority: current W2b owner instruction recorded in `tasks/intent.json`; design authority:
`tasks/plan.md`. Existing uncommitted W2 changes are the baseline and remain preserved.
The supplied own-map hash remains ee2ca84035dc1bdab8ac354eac9bd935723de95a749d101948375ae228d604f7.
No bootstrap receipt exists, so there is no pinned-file edit blocker.

Extended the shared resolver with GitHub heading slugs and collision suffixes, JSON pointer
traversal (optional leading slash, arrays, ~0/~1 escapes), Kotlin/Dart word modifiers and
annotations, generic Kotlin functions and object declarations, and shell function forms.
Markdown comments/fences and Kotlin/Dart comments cannot preserve a removed declaration;
prose and prefix names are rejected. Existing Python/TS/JS and dotted-name compatibility
is retained, including the historical declaration-in-document warning case.
Added the documented explicit-root `scripts/check_ontology_fleet.py`: read-only mapping
checks, no discovery, consumer runner execution, consumer writes or MK calls, nonzero on errors.
No private host paths were added to plugins.

Fail-first evidence (all uv commands used the owner-specified external UV_CACHE_DIR;
all W2b pytest runs used TMPDIR outside the worktree and disabled bytecode):
- Initial added forms: 22 failed, 169 deselected against unchanged W2; then 22 passed.
- Added escaped single-key pointer and stronger prose negatives: 13 failed / 10 passed
  before the boundary correction; no failure was labeled pre-existing.
- Final regression matrix imported the existing test module with CHECKER explicitly set to
  the byte-identical saved pre-W2b checker, using `pytest.main(["-q",
  "tests/test_ontology_skill.py", "-k", "fleet_anchor_forms", "--tb=no"])`:
  **23 failed / 169 deselected**. Every final new test has direct fail-first evidence;
  both existing keyword shell forms are additionally exercised within the failing shell cases.
- `uv run pytest -q tests/test_ontology_skill.py --tb=short`: **192 passed in 30.33s**.
  A new intermediate Markdown early-return regression failed one existing document case;
  HEAD checker comparison of its three suffixes passed 3/3, and the corrected current suite
  passed all 192. This was a new regression and was repaired.

Full-suite evidence:
- `uv run pytest -q --tb=short`, with external TMPDIR and PYTHONDONTWRITEBYTECODE=1:
  initial run **2019 passed / 1 failed in 281.07s**. The slim-integration failure reported
  preserved ontology_check.py content after the source changed during the run and its
  inventory digest lagged. It was not classified as pre-existing.
- Same failing test in an independent committed HEAD clone, with the same external UV cache
  and TMPDIR: **1 passed in 6.37s**. An initial comparison attempt omitted the external UV
  cache variable and failed during derivative generation; the corrected command above passed.
- Refreshed the inventory and reran the FULL suite against stable implementation bytes:
  `uv run pytest -q --tb=short`: **2021 passed in 242.45s**, exit 0, no failures or skips.
- `uv run ruff check`: all checks passed. `uv run python scripts/verify_codex_sync.py`:
  OK, Codex derivatives match Claude sources. `uv run python scripts/verify_context_paths.py`:
  9 files / 77 references passed. `git diff --check`: passed.
- Both changed Python scripts parse under Python 3.9 grammar.
  `python3 scripts/mir_ontology.py impact --git-diff HEAD --strict`: exit 0, no stale refs;
  printed checks are selection only. Own mapping: 0 errors / 0 warnings, contract/map 1.1.0.
- No plugins/__pycache__ directories existed before digest calculation or after full pytest.
  Used the repository's `mir.core.capabilities.manager._tree_digest` as W2 did, updating only
  the local managed mir-core SHA256 to
  6cc00a931039ddce1dac83319785dcb33d934e501716fe9047bccdeea643000d.
  Final independent digest comparison matched. Refreshed candidate inventory with
  `uv run python -m tools.template_assets --write-adopter-payload`.
- Instruction sizes remain CLAUDE 3,587 bytes / AGENTS 3,676 bytes; neither was edited.

Read-only fleet invocation: `python3 scripts/check_ontology_fleet.py ROOT ...`, supplying
all 15 owner-listed repository roots plus Yoke explicitly. Aggregate exit 1 is intentional
because of the one genuinely unresolved target below. Every warning count is zero.

Result: every requested consumer map and Yoke's own map report 0 warnings. All but one report
0 errors. One consumer map names a symbol its target file does not declare (one similarly named
declaration exists). No fuzzy or prefix fallback was added. The fix belongs to that consumer's
owner. Kotlin `fun <T>` declarations, Markdown heading slugs, JSON pointers and shell functions now
resolve.

W2b changed files: plugins/mir-core/skills/ontology/scripts/ontology_check.py;
tests/test_ontology_skill.py; scripts/check_ontology_fleet.py;
docs/operations/ontology-verification.md; .mir/capability-lock.json;
config/adopter-payload.json; tasks/intent.json; tasks/plan.md; tasks/change_log.md.
The other W2 working-tree files remain preserved. No generated instruction/runtime derivative
was written; no regeneration is currently required (read-only parity passed). No version bump,
released changelog edit, consumer write, live database/intake/MK call, service operation,
commit in the owner repository, push, tag or release was performed. Only isolated Git test
fixtures created their own commits. Final bookkeeping is followed by inventory refresh and
focused exact-payload/public-surface checks; full code evidence above remains the complete suite.

## Superseded cursor: Closure W2b before domain relation audit fix (2026-10-15)

Preserved intent:

```json
{
  "goal": "Closure W2b: resolve existing fleet Markdown slugs, JSON pointers, modified declarations and shell functions without accepting mere mentions.",
  "goal_type": "maintenance",
  "scope": "Current W2b owner instruction; preserve W2 changes, repository code/test boundary, read-only fleet verification, no generated derivatives or delivery.",
  "priority": "normal",
  "updated": "2026-10-15",
  "history": [
    {
      "goal": "Closure W2: canonical active-distribution ontology runner, symbol-anchored refs and EPERM cleanup fix.",
      "updated": "2026-10-15",
      "status": "blocked",
      "evidence": "tasks/change_log.md#superseded-cursor-closure-w2-before-w2b-2026-10-15"
    },
    {
      "goal": "Implement the owner-approved mir_executor common base, optional local hooks/data and explicit sync/drift tooling test-first in mir-yoke only.",
      "updated": "2026-10-01",
      "status": "complete"
    },
    {
      "goal": "Resolve covered ontology check refs and document the actual Memory Keeper consumer API.",
      "updated": "2026-10-15",
      "status": "complete",
      "evidence": "tasks/change_log.md#superseded-cursor-covered-check-resolution-and-mk-guide-2026-10-15"
    },
    {
      "goal": "Implement P2 ontology endpoints, impact, lookup and the on-demand Memory Keeper stdio client.",
      "updated": "2026-10-15",
      "status": "superseded"
    },
    {
      "goal": "Complete P4 Yoke ontology pytest gate, on-demand MK runner and scoped E01-E10 closure without generated writes or live operations.",
      "updated": "2026-10-15",
      "status": "complete",
      "evidence": "tasks/change_log.md#superseded-cursor-completed-p4-before-closure-w2-2026-10-15"
    }
  ],
  "status": "complete"
}
```

Preserved plan:

# Plan

## Active task: Closure W2b (2026-10-15)

Authority: current W2b owner request recorded in `tasks/intent.json`; this is the single
active cursor and design authority. The preceding W2 cursor is preserved in `tasks/change_log.md`.

Outcome: resolve declared fleet anchor forms, retain strict missing-name rejection, provide
an explicit-root fleet check, and run the complete suite with scratch outside the worktree.
Design: extend the existing resolver with heading slugs, RFC 6901 traversal, declaration
modifiers/annotations/generic functions and shell declaration forms. Preserve ordinary names.
A real missing declaration remains an error and is reported without consumer edits.

- [x] Prove each new anchor regression fails against unchanged W2 code.
- [x] Implement the bounded resolver change and document an explicit-root fleet check.
- [x] Run full pytest, compare any failures with HEAD, run lint/parity and fleet checks.
- [x] Refresh the cache-free mir-core digest and adopter inventory; record exact evidence.

No generated writes, consumer writes, live operations, version bumps, commits or delivery.

Code/test boundary complete: full pytest 2,021 passed; Ruff, read-only Codex parity,
context paths, Python 3.9 grammar and strict impact pass. Fleet results are 14 requested
roots at 0/0 and one consumer at 1 error/0 warnings: its Artifact ref names an undeclared symbol,
which the target does not declare. Yoke is also 0/0. Consumer correction remains Main/owner
work; the matcher must not accept a different declaration. No derivative regeneration
is currently needed. Exact commands and per-root receipts: `tasks/change_log.md`, Closure W2b.

## Domain common relation audit fix (2026-10-15)

Authority: current owner request in `tasks/intent.json`; active cursor/design record:
`tasks/plan.md`. Initial working tree was clean. Own map SHA256 matched the supplied
ee2ca84035dc1bdab8ac354eac9bd935723de95a749d101948375ae228d604f7
before work and was not changed.

Extracted the existing common relation ID and version-gated endpoint validation into
`Checker.common_relation`; both top-level relations and `domain.relations` with `common`
call it. Domain entries without `common` retain ref-only checks. The existing mapping guide
permits common concept IDs and contract-allowed wildcards, so local domain concept IDs remain
invalid even for unrestricted relation endpoints. One guide line documents the added domain
validation; the unreleased changelog records the fix. Semantic evidence: mapping-guide.md,
"Required keys and shapes", and common-contract.json relation endpoint definitions.

All uv runs used the owner-specified external UV cache. Pytest used TMPDIR outside the
repository and PYTHONDONTWRITEBYTECODE=1. No plugin bytecode directories existed before
digest generation or after the full suite.

Fail-first: verified the unchanged checker was byte-identical to `git show HEAD:` for its
path before adding regressions. Against that checker the selected final cases reported
**18 failed / 22 passed / 177 deselected**. Failures cover domain unknown IDs (including
malformed values) at 1.0.0/1.1.0 and invalid/missing/restricted/local/wildcard-array endpoints
at 1.1.0. Positive controls cover allowed endpoints, ref-only entries and legacy endpoints.
An initial legacy positive control retained a 1.1.0 binding interpreted as a legacy ref;
corrected that test fixture to not_connected before recording accepted fail-first evidence.
Selector: `uv run pytest -q tests/test_ontology_skill.py -k 'invalid_endpoints_at_11 or
allowed_endpoints_at_11 or unknown_common_when_declared_in_domain_relation or
local_concept_endpoint_when_declared_in_domain_relation or
check_only_ref_when_domain_relation_has_no_common or
preserve_legacy_endpoints_when_domain_relation_declares_common or
wildcard_array_even_for_unrestricted_relation' --tb=line`.

Validation:
- `uv run pytest -q tests/test_ontology_skill.py --tb=short`: 217 passed in 15.67s;
  final rerun after test-only line-length corrections: 217 passed in 15.75s.
- `uv run pytest -q --tb=short`: **2,046 passed in 243.60s**, exit 0, no failures or skips.
  Checker/guide bytes stayed fixed throughout the run and afterward. Only test formatting,
  bookkeeping and dependent inventory refresh followed the full run.
- `uv run ruff check`: all checks passed after correcting two new test lines above 100 chars.
- `uv run python scripts/verify_codex_sync.py`: OK, derivatives match; only temporary output
  outside the checkout was generated. No checked-in Codex derivatives were written.
- `python3 plugins/mir-core/skills/ontology/scripts/ontology_check.py contract`: 0/0.
- `python3 scripts/mir_ontology.py mapping`: 0 errors / 0 warnings, map/contract 1.1.0.
- `python3 scripts/mir_ontology.py impact --git-diff HEAD --strict`: exit 0, no stale refs;
  selected checks are navigation only; the focused ontology suite executed the selected test.
- Changed checker parses under Python 3.9 grammar; `git diff --check` passed.

Read-only 16-map comparison used exactly the owner's explicit root list, with no discovery:
`python3 plugins/mir-core/skills/ontology/scripts/ontology_check.py mapping --repo ROOT`
for each root, both before and after the checker change. Every baseline and post-change
invocation exited 0, with 0 errors / 0 warnings. **New findings: none; no new pointers.**
No consumer repository was edited.

Refreshed only mir-core's managed lock SHA256 using
`mir.core.capabilities.manager._tree_digest`:
`9989c59d723059aa0eb337a43af939dcbbc259b8dbace08bb3975068a28e61f4`.
Refreshed `config/adopter-payload.json` with
`uv run python -m tools.template_assets --write-adopter-payload`; final bookkeeping is
followed by another refresh and focused exact-inventory/public-surface checks.
Changed files: checker, mapping guide, ontology tests, CHANGELOG.md, managed capability lock,
adopter payload, tasks/intent.json, tasks/plan.md and this evidence log.
No checked-in generated derivatives or consumer files were written. No secrets or live
databases were read. No owner-repository commit, push, tag, release or live service operation
was performed. No implementation or consumer work remains.

## Superseded cursor: domain relation audit before covered-label fix (2026-10-16)

## Active task: Domain common relation audit fix (2026-10-15)

Authority: the current owner request is recorded in `tasks/intent.json`; this document is
the single active cursor and design record. Previous cursor details are preserved in
`tasks/change_log.md#superseded-cursor-closure-w2b-before-domain-relation-audit-fix-2026-10-15`.

Outcome: common declarations in `domain.relations` receive the same relation-ID and
version-gated endpoint validation as top-level relations. The mapping guide permits only
common concept IDs or a contract-allowed wildcard; local concept IDs remain invalid.
Entries without `common` retain ref-only validation. Extract and reuse the existing validator.

- [x] Capture baseline results for the 16 owner-listed maps and prove new regressions fail at HEAD.
- [x] Share the relation validation, add the guide line and unreleased changelog entry.
- [x] Run focused/full pytest, lint, read-only parity, mapping/impact and all 16 maps; report new pointers.
- [x] Refresh cache-free mir-core digest and adopter payload; record evidence and remaining work.

No generated derivatives, consumer writes, database inspection, commits or delivery.

Completed implementation and verification: 18 fail-first regressions against the byte-identical
HEAD checker; 217 focused tests and 2,046 full-suite tests passed. All 16 explicit owner-listed
maps report 0 errors and 0 warnings before and after; there are no new finding pointers.
Ruff, read-only Codex parity, contract, own mapping, strict impact and Python 3.9 grammar pass.
The mir-core digest and adopter inventory are refreshed; final inventory/public checks follow
bookkeeping. No consumer correction or generated regeneration is needed. Evidence:
`tasks/change_log.md#domain-common-relation-audit-fix-2026-10-15`.

## Covered-label fix (2026-10-16)

Authority: current owner request recorded in `tasks/intent.json`; single cursor and design
record: `tasks/plan.md`. Baseline working tree was clean, with map SHA256
`ee2ca84035dc1bdab8ac354eac9bd935723de95a749d101948375ae228d604f7`.
No bootstrap receipt exists to pin the edited files.

Reviewed E03/ST-3 and E07/AUTH-1/AUTH-2 in the installed mir-core 0.12.0 distribution's
`skills/ontology/references/common-contract.json` (contract 1.1.0; source digest
`b2f1ecd01aaa88d41caac2bc2481e7f4c5a429cff3983aaa85ddfb0fc2f1b93f`).
Only the two `error_cases` checks and their scoped reasons changed; both retain `covered`.

| Row | Action and check ref | Executed behavior and scope |
| --- | --- | --- |
| E03 | Re-pointed to `tests/test_adr53_phase3a_search.py#test_search_default_excludes_semantic_historical_documents` | Scans current, superseded and mirrored documents into a temporary fixture database; default search returns only current.md, while explicit include_history returns all three. Tests obsolete-material exclusion, rather than decision-index wording. |
| E07 | Re-pointed to `tests/test_public_template_authority.py#test_should_make_zero_writes_when_existing_repository_contract_is_missing` | Calls adoption --apply on a temporary target without its repository contract; asserts exit 2, no reported changed paths and an unchanged filesystem. Tests refusal of mutation without the required contract, rather than parser defaults; other authorization paths are outside this claim. |

Existing tests already exercise the behavior, so no new tests or fail-first additions were
needed. Map size: **12,275 bytes**, below 12,288. Every other mapping entry is unchanged.

Validation (UV_CACHE_DIR used the owner-specified external cache; pytest TMPDIR and
--basetemp used disposable repository-local scratch; bytecode writing was disabled):

- `uv run pytest -q tests/test_mir_ontology.py tests/test_ontology_skill.py tests/test_ontology_runner.py tests/test_adr53_phase3a_search.py::test_search_default_excludes_semantic_historical_documents tests/test_public_template_authority.py::test_should_make_zero_writes_when_existing_repository_contract_is_missing tests/test_relations.py::test_current_graph_is_reloaded_and_source_digest_changes --ignore=tests/test_harness_consistency.py --basetemp=<scratch>/pytest --tb=short`: **262 passed in 19.22s**, exit 0. Includes every check now named in the map (all parameterizations).
- `MIR_ONTOLOGY_CHECKER=<installed mir-core checker> python3 scripts/mir_ontology.py mapping`: **0 errors, 0 warnings; contract 1.1.0, mapping 1.1.0**, exit 0.
- `MIR_ONTOLOGY_CHECKER=<checkout checker> python3 scripts/mir_ontology.py mapping`: same **0/0**, exit 0; informational 0 line-number refs.
- `MIR_ONTOLOGY_CHECKER=<installed mir-core checker> python3 scripts/mir_ontology.py impact --git-diff --strict`: exit 0, no stale refs, map re-validation requested; affected Task/intent entries only, no selected executable checks.
- `MIR_ONTOLOGY_CHECKER=<checkout checker> python3 scripts/mir_ontology.py impact --git-diff --strict`: same result, exit 0.
- `python3 <checker> contract` for both installed and checkout distributions: **0 errors, 0 warnings**, exit 0.
- `git diff --check`: passed before final bookkeeping; final verification follows below.

Updated `tasks/intent.json`, `tasks/plan.md` and this evidence log, preserving the previous
cursor above. Refreshed `config/adopter-payload.json` after bookkeeping because the existing
exact inventory includes the changed map and task files; validated the inventory separately.
No instruction/runtime derivative regeneration is required: their sources are unchanged.

Skipped by owner instruction: FULL suite; `tests/test_harness_consistency.py`;
`harness_consistency run`; memory render/sync; context sync; any wrapping gate. No live
memory database, intake, credentials, generated derivatives, consumer files, service
operations were accessed or changed. No owner-repository commit was created. Git fixture
commits occur only inside the tests' disposable independent repositories. No behavior work remains.

Final inventory/behavior confirmation:
- `uv run python -m tools.template_assets --write-adopter-payload`: template asset classification: pass.
- `uv run pytest -q tests/test_template_asset_classification.py tests/test_adr53_phase3a_search.py::test_search_default_excludes_semantic_historical_documents tests/test_public_template_authority.py::test_should_make_zero_writes_when_existing_repository_contract_is_missing --ignore=tests/test_harness_consistency.py --basetemp=<scratch>/final --tb=short`: **8 passed in 0.49s**, exit 0. Both changed-row tests pass again through the normal pytest runner.
- Refresh the payload once more after this evidence entry; the final exact-inventory assertion,
  both mapping/strict-impact invocations and whitespace check follow without further source edits.
Disposable task scratch is removed at closeout. Changed files: `.mir/ontology-map.json`,
`tasks/intent.json`, `tasks/plan.md`, `tasks/change_log.md`, `config/adopter-payload.json`.
No remaining implementation work or derivatives to regenerate.


## Superseded cursor: covered-label fix before 0.13.0 preparation (2026-10-16)

Preserved intent:

```json
{
  "goal": "Correct E03 and E07 covered check references using existing executable behavior tests.",
  "goal_type": "maintenance",
  "scope": "Owner-requested covered-label re-review: only the two mapping rows and task records; run ontology tests, every mapped test and installed/checkout mapping plus strict impact; exclude live-memory consistency and generated writes.",
  "priority": "normal",
  "updated": "2026-10-16",
  "history": [
    {
      "goal": "Validate declared common relations under domain.relations using the shared common relation validator.",
      "updated": "2026-10-15",
      "status": "complete",
      "evidence": "tasks/change_log.md#domain-common-relation-audit-fix-2026-10-15"
    },
    {
      "goal": "Closure W2b: resolve existing fleet Markdown slugs, JSON pointers, modified declarations and shell functions without accepting mere mentions.",
      "updated": "2026-10-15",
      "status": "complete"
    },
    {
      "goal": "Closure W2: canonical active-distribution ontology runner, symbol-anchored refs and EPERM cleanup fix.",
      "updated": "2026-10-15",
      "status": "blocked",
      "evidence": "tasks/change_log.md#superseded-cursor-closure-w2-before-w2b-2026-10-15"
    },
    {
      "goal": "Implement the owner-approved mir_executor common base, optional local hooks/data and explicit sync/drift tooling test-first in mir-yoke only.",
      "updated": "2026-10-01",
      "status": "complete"
    },
    {
      "goal": "Resolve covered ontology check refs and document the actual Memory Keeper consumer API.",
      "updated": "2026-10-15",
      "status": "complete",
      "evidence": "tasks/change_log.md#superseded-cursor-covered-check-resolution-and-mk-guide-2026-10-15"
    },
    {
      "goal": "Implement P2 ontology endpoints, impact, lookup and the on-demand Memory Keeper stdio client.",
      "updated": "2026-10-15",
      "status": "superseded"
    },
    {
      "goal": "Complete P4 Yoke ontology pytest gate, on-demand MK runner and scoped E01-E10 closure without generated writes or live operations.",
      "updated": "2026-10-15",
      "status": "complete",
      "evidence": "tasks/change_log.md#superseded-cursor-completed-p4-before-closure-w2-2026-10-15"
    }
  ],
  "status": "complete"
}
```

## Active task: Covered-label fix (2026-10-16)

Authority: the current owner request recorded in `tasks/intent.json`; this is the single
active cursor and design record. Prior cursor details are preserved in
`tasks/change_log.md#superseded-cursor-domain-relation-audit-before-covered-label-fix-2026-10-16`.

Outcome: E03 and E07 retain `covered` only with symbol-anchored tests that exercise their
error cases, and reasons describing that tested scope. Reuse the owner-suggested existing
tests; no behavior changes or new tests are needed. Keep the map at most 12,288 bytes.

- [x] Confirm supplied map hash, installed 1.1.0 contract definitions and candidate behavior.
- [x] Re-point E03/E07 checks and scope reasons; preserve every unrelated mapping entry.
- [x] Run ontology tests and every mapped check with temporary fixture databases only.
- [x] Pass installed and checkout mapping (0/0) and strict Git impact; record evidence.

Skip `tests/test_harness_consistency.py`, `harness_consistency run`, memory render/sync,
context sync and any gate wrapping them. Run individual allowed gate steps only.
No commits, generated derivatives, live databases, service operations or consumer writes.

Completed: 262 ontology and mapped-check tests passed. Installed and checkout checkers each
reported mapping 0 errors / 0 warnings and strict impact exit 0 with no stale refs; both
contract self-checks returned 0/0. The map is 12,275 bytes. Refs and evidence:
`tasks/change_log.md#covered-label-fix-2026-10-16`.

The dependent adopter inventory is refreshed after bookkeeping and checked separately.
No generated instruction/runtime derivatives need regeneration because their sources did
not change. Full suite and live-memory steps are intentionally excluded by owner scope.

## 0.13.0 release preparation (2026-10-16)

Authority: owner-requested version-only working-tree preparation, recorded in
`tasks/intent.json`; `tasks/plan.md` is the single active cursor/design record.
Mirrored bbc3248 release metadata, retaining the existing ontology map and runner fixtures.
Moved the complete Unreleased body under
`## [v0.13.0] — 2026-10-16 — Canonical ontology runner and strict reference validation`,
leaving Unreleased empty. MIGRATION describes byte-identical runner replacement,
symbol-anchored refs, strict impact and common-relation validation under domain.relations.
The release metadata test now checks the requested v-prefixed heading.

The lifecycle-hooks acknowledgement was computed by the existing dedicated
`mir.core.capabilities.manager._validate_plugin(..., package_kind="skills-hooks")` validator:
`235032d02dfd490ff01bfcae067f82803acfa2c649b0b6067a8808633fc0946a`.
The documented generator is `uv run python -m tools.template_assets --write-adopter-payload`.
No generated instruction/runtime source changed, and no checked-in Codex derivatives were written.

Executed evidence (all uv commands used the owner-required external UV_CACHE_DIR; test and
generator scratch used external TMPDIR):

- Before edits: `uv run pytest --ignore=tests/test_harness_consistency.py`:
  2,045 passed in 243.01 seconds, exit 0.
- Prepared tree: the same full command: 2,044 passed, 1 failed in 218.16 seconds, exit 1.
  The only failure is
  `tests/test_capability_cli.py::test_repository_lock_is_portable_and_matches_managed_trees`
  at line 360. The changed mir-code tree digest is
  `42c0a6753558f50969e86d4d1a362afe28d92dd0813902f4c93084595619424c`;
  the unchanged lock expects
  `cefc2975c9caddd3869798539629ee5f1029852288d8ff18f22860df2db9b48f`.
  This failure is new relative to HEAD. Main owns the commit-bound lock refresh;
  preparation does not weaken or deselect this assertion.
- `uv run ruff check`: All checks passed, exit 0.
- `uv run python scripts/verify_codex_sync.py`:
  OK: Codex derivatives match Claude sources, exit 0; generation uses isolated scratch only.
- `uv run python -m tools.template_assets --json`: all 883 assets classified once;
  no unclassified, duplicate or prohibited assets, exit 0.
- `uv run python tests/test_no_korean_in_user_facing.py`,
  `uv run python tests/test_link_integrity.py`,
  `uv run python tests/test_schema_validity.py`: PASS, exit 0 each.
- `python3 scripts/mir_ontology.py mapping`: 0 errors, 0 warnings; contract and mapping 1.1.0.
- `python3 scripts/mir_ontology.py impact --git-diff --strict`: exit 0, no stale refs;
  no covered checks selected for these changed paths. Selection is not execution evidence.
- The full run includes passing public-template-surface tests. `git diff --check`: exit 0.
- After final cursor/evidence updates and payload regeneration:
  `uv run pytest -q tests/test_public_template_surface.py tests/test_release_metadata.py tests/test_plugin_skill_packages.py tests/test_template_asset_classification.py tests/test_mir_ontology.py`:
  28 passed in 2.98 seconds, exit 0. Mapping remained 0/0 and strict impact exit 0.

Remaining Main work, not performed here:

1. Review and commit implementation preparation (commit A).
2. Bind the capability lock to exact commit A and validated plugin/marketplace digests,
   regenerate the adopter payload, then commit that binding separately (commit B), per ADR-80.
3. Rerun full verification, including the lock assertion, and the documented
   `uv run python scripts/verify_release_readiness.py --current-clean-tree` after committing.
   Under the current no-live-database constraint, do not run a wrapper containing harness
   consistency; that gate needs separate Main authority or the allowed individual steps.
4. Tag commit B as v0.13.0 and push the release branch and tag. The release workflow validates
   the clean tree and publishes with `gh release create` using `--verify-tag --generate-notes`.
5. Perform authorized `mir capability update --project-root <target> --apply --json`.
   Start fresh Claude and Codex sessions, observe every selected namespaced skill and the
   trusted `mir-lifecycle-hooks:SessionStart` output; run `mir capability attest` separately
   for `claude-code` and `codex-cli-desktop`, supplying actual observed skills/hook and --apply.
   Then `mir capability finalize --project-root <target> --apply --after-restart --json`
   and `mir capability status --project-root <target> --json`.

Release procedure evidence: ADR-80; `.github/workflows/release.yml`;
`docs/operations/global-plugin-migration.md` sections 3 and 4;
`src/mir/cli/capability.py` command options. No commit, tag, push, publishing, runtime-home
operation, capability apply/attest/finalize, live database, memory or context sync was performed.


## Superseded cursor: memory render guard before local and CI fixes (2026-10-16)

The completed section A intent and cursor are preserved here before the owner-authorized follow-up.

```json
{
  "goal": "Prevent automatic consistency tests from rendering live agent memory.",
  "goal_type": "maintenance",
  "scope": "Section A: shared consistency test and local tool tests only; synthetic fixtures, unchanged explicit-run defaults, no live databases, commits or generated derivatives.",
  "priority": "normal",
  "updated": "2026-10-16",
  "history": [
    {
      "goal": "Prepare the Mir Yoke 0.13.0 release working tree with version metadata and migration notes only.",
      "updated": "2026-10-16",
      "status": "complete",
      "evidence": "tasks/change_log.md#0130-release-preparation-2026-10-16"
    },
    {
      "goal": "Correct E03 and E07 covered check references using existing executable behavior tests.",
      "updated": "2026-10-16",
      "status": "complete",
      "evidence": "tasks/change_log.md#superseded-cursor-covered-label-fix-before-0130-preparation-2026-10-16"
    }
  ],
  "status": "complete",
  "evidence": "tasks/change_log.md#automatic-memory-render-guard-2026-10-16"
}
```

# Plan

## Active task: memory render guard (2026-10-16)

Authority: the current owner request recorded in `tasks/intent.json`; this is the single
active cursor and design record. Prior completed release preparation and its remaining
Main steps are preserved in `tasks/change_log.md#0130-release-preparation-2026-10-16`.

Outcome: automatic consistency tests never render live agent memory. The shared test
passes a temporary copy of the default manifest with only R11 disabled. Synthetic
fixtures retain matching/drift rendering, default-run and green-manifest coverage.
Keep the default manifest and explicit-run behavior unchanged.

- [x] Inspect relevant tests, gate references, default manifest and accepted reference fix.
- [x] Demonstrate HEAD failure with an intercepted subprocess; never run live-root rules.
- [x] Guard the shared test and replace live-root renderer/tool tests with synthetic fixtures.
- [x] Run full pytest with required deselect; record results and Main's host check.

Hard limits: one writer; no commits/pushes, live databases, secrets, memory/context sync,
live-root consistency/gate invocation or generated instruction/runtime derivatives.
Every pytest command deselects `tests/test_harness_consistency.py`.

Fail-first: shared test command inspection failed because HEAD used no `--manifest`.
After the fix: affected tool tests plus public-template-surface checks passed (69);
Ruff and read-only Codex parity passed. Full suite: 2,042 passed, 3 failed, 1 deselected.
One inventory failure was observed before payload regeneration; final inventory checks
are recorded in the evidence entry. The other two failures reproduce on unchanged
HEAD inputs: capability lock/plugin digest and the missing v0.13.0 changelog heading.
These are outside this section-A change. Main must run the shared test on the host
and rerun the full suite after resolving the two release-state failures.


## Local and CI validation fixes (2026-10-16)

Authority: the owner requested local and validate-workflow-equivalent validation while
keeping Actions enabled. `tasks/intent.json` and the single cursor/design record at
`tasks/plan.md` own this bounded follow-up. The existing, Main-reviewed section A memory
guard remains intact, including its untracked synthetic regression test.

Root causes and minimum corrections:

1. Release headings: `git log -p -- CHANGELOG.md` shows that `06ca2f9` added a v-prefixed
   0.13.0 heading and changed the metadata test; `eb5aeaa` deliberately restored the existing
   unprefixed heading without restoring the assertion. `v0.12.0:tests/test_release_metadata.py`
   and `scripts/extract_changelog_entry.py#extract_entry` both require unprefixed headings.
   Restored that exact assertion, kept one accepted form, and aligned the changelog preamble.
   The historical v0.12.0 passing claim is recorded in `afe4ace`; it was not rerun here.
2. Capability digests: `_tree_digest` hashed transient directories and files, so importing
   ontology scripts changed the digest of an otherwise unchanged managed tree. Reused
   `mir.core.adoption.runtime._is_transient` for `__pycache__`, `.pytest_cache`, `.ruff_cache`,
   `.pyc` and `.pyo`. `_validate_plugin` (bind/materialize) and installed status verification
   share the same digest helper; the lock test already imports this production helper.
   Symlinks and executable files are rejected before cache exclusion. Package admission
   allowlists remain unchanged. No plugin source or capability lock was refreshed.
3. CI ancestry: checkout's default shallow history omits the lock's `be51f1d` source commit.
   A local depth-one clone reproduced Git exit 128 (`Not a valid commit name`); the full
   fresh clone returned 0 for the identical `merge-base --is-ancestor` command. Set
   `fetch-depth: 0` only on `public_cli`, preserving workflow triggers and all assertions.
4. CI inventory: a pristine local HEAD clone reproduced `supported_contracts` as 60 passed,
   one failed. There were no missing/extra file paths, mode, ordering or environment
   differences in the generated payload. Exactly two stored hashes were stale:
   `.mir/capability-lock.json` (stored `41b0ff9f...`, actual `1fb7f129...`) and `CHANGELOG.md`
   (stored `5c225bb4...`, actual `5a8b166f...`). The payload was last generated in `be51f1d`,
   before the later changelog and lock edits. Regenerated with the existing generator after
   candidate/bookkeeping changes; retained the exact payload equality test.

Fail-first and verification evidence (external UV cache and scratch used throughout;
every pytest invocation includes `--deselect tests/test_harness_consistency.py`):

- Initial release-metadata and repository-lock tests: two failures, reproducing both reports.
- Added cache regression against unchanged HEAD manager: five failed, including a planted
  `__pycache__` in a temporary tree. After the fix, ordinary source changes still affect the
  digest. Review exposed an executable-cache bypass in the first implementation; its five
  cases failed before moving the permission check ahead of the exclusion, then the cache,
  repository-lock and existing unsafe-plugin matrix passed (nine tests). Final tests also
  cover symlink cache entries and all pass in the complete suite.
- Focused capability/release/runtime/security selection: 164 passed before the review
  adjustment; the final complete suite supersedes that intermediate implementation evidence.
- An intermediate complete run overlapped deliberate review/bookkeeping edits: 2,048 passed,
  two failed (provider snapshot changed during its probe and inventory changed during hashing),
  one deselected. It is superseded, not accepted as final evidence. The final implementation
  was held stable for the following complete run.
- `uv run pytest --deselect tests/test_harness_consistency.py`: **2,050 passed, one deselected**,
  234.76 seconds, exit 0. This includes public-template-surface and section A synthetic tests.
- `uv run ruff check`: all checks passed, exit 0.
- `uv run python scripts/verify_codex_sync.py`: derivatives match sources, exit 0;
  the checker renders only to isolated scratch, with no repository `.codex/**` writes.
- `git diff --check`: exit 0. Independent read-only implementation review: no remaining findings.
- All four committed plugin digests matched after the change: mir-code `42c0a675...`,
  mir-content `7fe3624d...`, mir-core `97122b8d...`, mir-lifecycle-hooks `235032d0...`.
  `.mir/capability-lock.json` remained byte-identical to HEAD.

Fresh-clone validation: cloned local HEAD `eb164fa` into isolated external scratch, first
reproduced the failure without overlays, then copied only the complete candidate files
(including section A's untracked test). No ignored files, live databases, credentials or
runtime homes were copied. Commands came directly from `.github/workflows/validate.yml`;
pytest adds only the mandatory deselection. macOS host, CPython 3.12.13. npm's global prefix
and cache were isolated on external storage, preserving installed user CLIs. The initial
local static setup lacked pip (exit 127); seeded pip in the scratch virtualenv, then reran
its exact install command successfully, matching the Actions setup-python prerequisite.

| Validate job | Exact command | Result |
|---|---|---|
| supported_contracts | `uv sync --extra dev --frozen` | PASS; exit 0 |
| supported_contracts | `uv run pytest -q tests/test_project_agent_kit.py tests/test_minimal_starter.py tests/test_public_template_identity.py tests/test_decision_authority.py tests/test_template_asset_classification.py tests/test_plugin_skill_packages.py tests/test_common_skill_contracts.py --deselect tests/test_harness_consistency.py` | 61 passed in 0.61s; exit 0 |
| supported_contracts | `uv run python scripts/verify_codex_sync.py` | PASS; exit 0 |
| supported_contracts | `uv run ruff check` | PASS; exit 0 |
| public_cli | `uv sync --extra dev --frozen` | PASS; exit 0 |
| public_cli | `uv run pytest -q tests/test_installed_cli.py tests/test_bootstrap_cli.py tests/test_bootstrap_adoption_cli.py tests/test_existing_repository_adoption.py tests/test_greenfield_slim_integration.py tests/test_setup_wrappers.py tests/test_adr53_phase1_schema.py tests/test_adr53_phase2_population.py tests/test_adr53_phase3a_search.py tests/test_adr53_phase3b_context_cli.py tests/test_memory_doctor.py tests/test_migrations.py tests/test_loop_cli.py tests/test_loop_driver.py tests/test_capability_cli.py tests/test_capability_security.py tests/test_run_python_cli.py tests/test_runtime_manifest.py tools/mir_executor/tests --deselect tests/test_harness_consistency.py` | 1109 passed in 106.19s (0:01:46); exit 0 |
| portable_plugins | `uv sync --extra dev --frozen` | PASS; exit 0 |
| portable_plugins | `npm install --global @anthropic-ai/claude-code@2.1.223 @openai/codex@0.146.1` | PASS; exit 0 |
| portable_plugins | `uv run pytest -q tests/test_plugin_skill_packages.py tests/test_common_skill_contracts.py --deselect tests/test_harness_consistency.py` | 21 passed in 0.13s; exit 0 |
| portable_plugins | `uv run python scripts/verify_plugin_cli_activation.py` | PASS; two consumers, both CLIs, all four plugin digests and skill inventories; exit 0 |
| static_public_checks | `pip install jsonschema pytest` | PASS; exit 0 |
| static_public_checks | `python tests/test_schema_validity.py` | PASS; exit 0 |
| static_public_checks | `python tests/test_link_integrity.py` | PASS; exit 0 |
| static_public_checks | `python tests/test_hook_executability.py` | PASS; exit 0 |
| static_public_checks | `python tests/test_no_korean_in_user_facing.py` | PASS; exit 0 |
| static_public_checks | `python tests/test_phase_doc_completeness.py` | PASS; exit 0 |

Changed in this follow-up: `.github/workflows/validate.yml`, `CHANGELOG.md`,
`src/mir/core/capabilities/manager.py`, `tests/test_capability_cli.py`,
`tests/test_release_metadata.py`, `config/adopter-payload.json`, `tasks/intent.json`,
`tasks/plan.md`, `tasks/tdd.json`, and this evidence log. Preserved section A changes:
`tests/test_harness_consistency.py`, `tools/harness_consistency/tests/test_generate.py`,
`tools/harness_consistency/tests/test_rules.py`, and untracked
`tools/harness_consistency/tests/test_memory_guard.py`.

Ontology scope and evidence: `.mir/ontology-map.json` remains unchanged at SHA-256
`9b9d8eab4b8ab065ccd1e92840fc92503520d4ef75964bf52615c25e99500eda`, declaring
`mir.common-semantics@1.1.0`. Source/test refs above support the implementation claims;
no mapping meaning or consumer authority changed.

Remaining Main verification: actual GitHub Actions Ubuntu/macOS matrices after authorized
delivery, plus the guarded shared consistency test on the host (excluded in this sandbox).
Generated parity passes without regeneration. No commit, push, tag, GitHub access, lock
binding/refresh, live memory database, secret read, or consumer write was performed.


## Superseded cursor: local and CI fixes before ontology gap development (2026-10-16)

# Plan

## Active task: local and CI validation fixes (2026-10-16)

Authority: the owner request recorded in `tasks/intent.json`; this is the single active
cursor and design record. Preserve the completed memory render guard (section A), whose
cursor is archived in `tasks/change_log.md#superseded-cursor-memory-render-guard-before-local-and-ci-fixes-2026-10-16`.

Outcome: strict release metadata and committed capability digests agree with supported
sources; runtime caches do not affect bind/verify; every validate job command has fresh
checkout evidence, with actual Actions and platform limits stated explicitly.

- [x] Reproduce release, cache and fresh-checkout inventory failures; inspect release history.
- [x] Apply minimum fixes, prove cache fail-first and unchanged committed lock digests.
- [x] Run focused checks, full pytest with required deselect, lint and read-only parity.
- [x] Overlay only final candidate changes onto fresh HEAD clone; run each validate command.
- [x] Record root causes, commands/counts and remaining Main verification; regenerate payload.

Limits: one writer; no commits, pushes, tags, GitHub access, capability lock refresh,
live memory databases, secrets or generated `.codex/**` writes. Every pytest command uses
`--deselect tests/test_harness_consistency.py`. UV cache and scratch remain on external
storage. Ontology map remains unchanged at the owner-supplied SHA-256; semantic assertions
must cite map entries or direct source/test evidence. No cross-project authority is inferred.

Completed: the fixed implementation passed 2,050 tests with one required deselection.
Fresh HEAD plus the complete candidate overlay passed all four validate job command sets
on macOS/Python 3.12, including the pinned real CLI activation probe. See
`tasks/change_log.md#local-and-ci-validation-fixes-2026-10-16` for commands, counts and causes.
The committed capability lock and generated Codex files remain unchanged.

Main must verify actual Ubuntu/macOS Actions matrix results after authorized delivery and
run the guarded shared consistency test separately on the host. This sandbox did not
run Actions, publish, commit, or access a live memory database.

## Ontology gap development (2026-10-16)

Authority and design: current owner brief, recorded in `tasks/intent.json` and the single
`tasks/plan.md` cursor. Scope is G04, the supplier-side G05 fixture interface, and rows
7.E06/7.E08. No network, live database, memory sync, consumer write, runtime updater,
commit, push, release or checkout `.codex/**` regeneration was performed.

### Reproduction and changes

- G04 reproduced. `impact` previously selected covered error-case checks only. The new
  focused tests failed before the checker edit: 4 failed / 1 passed (two omitted invariant
  checks, accepted directory check and accepted non-string check; missing paths already failed).
  After the edit: 5 passed. Optional `domain.invariants[].check` now uses covered-check
  validation; affected invariant checks are selected and exact duplicate refs collapse.
  Unaffected invariants stay absent. `undeclared_check_links` explicitly reports affected
  invariants with no declared check; no missing dependency is inferred. The public skill
  and mapping guide document this selection-only behavior. Source and consumer fixtures
  include an ADR-style definition and a source module; byte-copied canonical consumer runners
  forward the new JSON report without requiring runner changes. Sentinel check code never runs.
- G05: the missing round-trip evidence was confirmed; a manager implementation defect did
  not reproduce. Existing `CapabilityManager` constructor injection and `sync`/`update`
  already support offline suppliers and explicit temporary consumers. No production manager
  change or transport-policy relaxation was needed. The new fixture uses immutable revision
  exports, a temporary supplier/provider, two consumer profiles (`code_app`, `infra_runtime`),
  and stub runtimes. It exercises contract 1.1.0 -> 1.1.1 -> 1.1.0 through real package
  validation/digest binding, compatibility impact, explicit local apply, map revalidation and
  package/map rollback. Peer locks/maps and unrelated files are preserved. Contract 2.0.0
  is rejected for both consumers before apply (impact exit 1); injected incomplete derivative
  rollback raises `local rollback was incomplete`, rather than reporting success. These are
  expected negative receipts, not newly fixed production defects. All three fixture scenarios
  passed with the production manager unchanged. The separate caller-owned rehearsal must
  treat those outcomes as failures; `docs/operations/ontology-distribution-rehearsal.md`
  specifies the transport and ownership interface. Orchestration remains outside this repository.
- 7.E06: the broader stale-evidence guarantee did not reproduce as an implemented local
  mechanism. `src/mir/core/relations.py#_load_graph` hashes graph bytes; queries reload edges,
  not referenced target contents. Existing coverage remains intact and a negative regression
  proves that a removed verification edge is not reused on the next query. The map entry
  `/error_cases/5` now explicitly limits coverage to graph reload/digest and excludes target
  content freshness/cached-evidence validation. The new regression passes with unchanged
  relation code; no absent cache-validation product was invented.
- 7.E08: personal-data isolation was not established by the cited check. The real client
  `plugins/mir-core/skills/ontology/scripts/mk_query.py#exchange` forwards structured supplier
  output; `main` prints it. The supplier owns namespace authorization. Map `/error_cases/7`
  is now `not_applicable` within that transport scope, with a verified reason. The existing
  synthetic refusal forwarding test remains unchanged and passes. No privacy-policy layer
  or claim of live supplier isolation was added.

### Verification receipts

Commands use the owner-specified external UV cache and fixture TMPDIR/basetemp. Every pytest
invocation includes `--deselect tests/test_harness_consistency.py`; no full-suite result is claimed.

- Initial focused G04 run: 4 failed, 1 passed. An earlier attempt had five setup errors because
  the requested scratch parent was missing; creating that parent allowed actual fail-first checks.
- Expanded check:
  `uv run --offline pytest -q tests/test_ontology_skill.py tests/test_ontology_runner.py tests/test_mir_ontology.py tests/test_capability_cli.py tests/test_capability_security.py tests/test_relations.py tests/test_public_template_surface.py tests/test_plugin_skill_packages.py --deselect tests/test_harness_consistency.py --basetemp "$TASK_SCRATCH/pytest" --tb=short`
  returned **462 passed, 1 failed**. The sole failure is
  `tests/test_capability_cli.py#test_repository_lock_is_portable_and_matches_managed_trees`:
  the existing lock binds the prior committed mir-core package digest, while this candidate
  changes that package. The package lock is deliberately left for Main's separate release
  binding. No check was bypassed or assertion weakened.
- An intermediate expanded run returned 445 passed / 8 failed: seven own-map gate failures
  resulted from the larger wording exceeding the map byte budget. Minimal wording restored
  the budget; all seven then passed. The eighth was the same release-binding failure above.
- Focused corrected own-map/rehearsal selection: 10 passed.
- `uv run --offline pytest -q -s tests/test_capability_security.py -k rehearse_ontology --deselect tests/test_harness_consistency.py --basetemp "$TASK_SCRATCH/pytest" --tb=short`:
  3 passed. Printed receipts retain sync/update/rollback operations, revision and package
  digest, plus per-consumer impact/mapping command exits. Candidate package digest:
  `77d4efcceafcd1e9ed46e3ed17881249d76e66e67a8d376655fb7fb7fde9eaa5`;
  restored baseline package digest:
  `4adaffed4173cc10284a733ec6e64cc33e3a567cb1af063a1aca505dc6437e0e`.
- `uv run --offline ruff check`: passed. Read-only
  `uv run --offline python scripts/verify_codex_sync.py`: passed, no checkout regeneration.
- `python3 scripts/mir_ontology.py mapping`: 0 errors / 0 warnings, contract/mapping 1.1.0.
- `python3 scripts/mir_ontology.py impact --git-diff --strict`: exit 0, no stale refs.
- Public-surface and isolated plugin-package checks passed in the expanded run above.

### Distribution identities and Main follow-up

Original map SHA-256 was the owner-supplied
`9b9d8eab4b8ab065ccd1e92840fc92503520d4ef75964bf52615c25e99500eda`.
New map SHA-256 is `331ac91cd1d8ddd22558c11549395c62c06f2ad9616294470aec795ca44abe40`.
The canonical runner bytes did not need changing; its candidate SHA-256 is
`fe4c885c9501cf297c062b99e33333cecd3e664de452fedcffbe1fed5a9e6891`.
The changed checker SHA-256 is
`d4383a8b30f92463f73f6dcbe0840737296701a4a66d3a6bd4f4adb0c42ee528`.
No copy into any consumer was performed.

Main must run its separately owned end-to-end rehearsal against this documented fixture
interface, perform authorized release/lock binding and consumer delivery separately, then
rerun the lock gate and full host suite including the guarded consistency check. No additional
product feature decision is required for the bounded changes. The working tree is not fully
green until the release-binding failure is resolved by Main.

Changed sources: `.mir/ontology-map.json`, ontology skill/guide/checker, the new rehearsal
interface document, `tests/test_ontology_skill.py`, `tests/test_capability_security.py`,
`tests/test_relations.py`, and cursor/intent/this log. The documented adopter-payload generator
refreshes `config/adopter-payload.json` after final bookkeeping; it has no database candidates.

Final follow-up checks after strengthening reverse-update peer preservation:
- Combined G04/G05 selection (`-k 'rehearse_ontology or declared_invariant'`): 8 passed.
- `uv run --offline pytest -q tests/test_public_template_surface.py --deselect tests/test_harness_consistency.py`: 3 passed after final documentation/bookkeeping.
- `uv run --offline pytest -q tests/test_template_asset_classification.py --deselect tests/test_harness_consistency.py`: 6 passed, including exact adopter-payload parity.
- Final `uv run --offline ruff check` and `git diff --check`: passed.
- A direct system-Python payload probe lacked `jsonschema`; the repository's uv environment
  passed the actual six classification tests. Adopter payload is regenerated after this log update.

## Superseded cursor: ontology gaps before 0.13.1 preparation (2026-10-16)

# Plan

## Active task: ontology gap development (2026-10-16)

Authority: current owner brief; this single cursor records intent and design.
Preserve prior completed validation evidence in `tasks/change_log.md`.

Outcome: affected invariants select declared checks without execution (G04); the
capability manager supports fixture-only supplier/two-consumer distribution and
rollback (G05); E06/E08 claims match their actual producer/consumer scope.

- [x] Reproduce gaps with isolated fail-first tests and inspect E06/E08 boundaries.
- [x] Implement minimal selection and fixture interface changes; narrow map claims.
- [x] Run focused tests, mapping, strict impact, lint and public-surface checks.
- [x] Record files, commands/counts, canonical runner digest and Main follow-ups.

Limits: one writer; no commits, network, live databases, consumer writes or live
updater. Do not write generated `.codex/**`. Every pytest command deselects
`tests/test_harness_consistency.py`. Use external uv cache and fixture scratch.
Harness owns its separate rehearsal script; release and consumer sync stay with Main.

Implementation and bounded verification are complete. Expanded checks returned 462 passed
and one release-binding failure because the candidate mir-core tree differs from the
existing committed capability lock. Mapping/strict impact, lint, public surface and
read-only generated parity passed. The canonical consumer runner is unchanged.

Evidence and exact digests: `tasks/change_log.md#ontology-gap-development-2026-10-16`.
Main owns the separate rehearsal script, release/lock binding, consumer sync and full host
verification (including the excluded consistency test). No live updater or delivery ran.

Previous intent:

```json
{
  "goal": "Close ontology impact and isolated distribution gaps and scope E06/E08 evidence.",
  "goal_type": "maintenance",
  "scope": "G04, G05 Yoke fixture interface, PARTIAL 7.E06 and 7.E08; repository only.",
  "priority": "normal",
  "updated": "2026-10-16",
  "history": [
    {
      "goal": "Make local validation and fresh-checkout validate workflow commands pass while retaining the memory render guard.",
      "updated": "2026-10-16",
      "status": "complete",
      "evidence": "tasks/change_log.md#local-and-ci-validation-fixes-2026-10-16"
    },
    {
      "goal": "Prevent automatic consistency tests from rendering live agent memory.",
      "updated": "2026-10-16",
      "status": "complete",
      "evidence": "tasks/change_log.md#automatic-memory-render-guard-2026-10-16"
    },
    {
      "goal": "Prepare the Mir Yoke 0.13.0 release working tree with version metadata and migration notes only.",
      "updated": "2026-10-16",
      "status": "complete",
      "evidence": "tasks/change_log.md#0130-release-preparation-2026-10-16"
    },
    {
      "goal": "Correct E03 and E07 covered check references using existing executable behavior tests.",
      "updated": "2026-10-16",
      "status": "complete",
      "evidence": "tasks/change_log.md#superseded-cursor-covered-label-fix-before-0130-preparation-2026-10-16"
    }
  ],
  "status": "complete",
  "evidence": "tasks/change_log.md#ontology-gap-development-2026-10-16"
}
```


## Superseded cursor: 0.13.1 preparation before Linux test fixes (2026-10-16)

The completed release-preparation cursor is preserved before the owner-authorized Linux failure investigation.

# Plan

## Active task: 0.13.1 release preparation (2026-10-16)

Authority: the current owner release brief recorded in `tasks/intent.json`.
This is the single active cursor and design record. Prior completed cursor details
remain in `tasks/change_log.md#superseded-cursor-ontology-gaps-before-0131-preparation-2026-10-16`.

Outcome: consistent 0.13.1 version metadata, focused release notes with the carried
Unreleased backlog preserved, consumer migration guidance and regenerated adopter hashes.
No implementation or common-contract version changes are authorized.

- [x] Compare HEAD checks and mirror the 06ca2f9 version surfaces.
- [x] Update release notes, migration guidance and lifecycle-hooks digest acknowledgement.
- [x] Generate adopter payload; run allowed full tests, lint, generated parity and ontology checks.
- [x] Record results and exact remaining Main delivery steps.

Limits: no commits, tags, pushes, publishing, capability update/attest/finalize,
consumer or user-runtime writes, live databases, memory/context synchronization,
or generated `.codex/**` writes. Exclude `tests/test_harness_consistency.py`.
Use the owner-specified external uv cache and external fixture scratch.
Main owns commit, lock binding, derivative regeneration if needed, tagging and delivery.

Preparation is complete; release delivery remains with Main. HEAD and the prepared tree
both returned 2,058 passed and one capability-lock binding failure. No new failure appeared.
Lint, generated parity, sanitization, links, schemas, mapping 0/0 and strict impact passed.
The Unreleased backlog is byte-identical to eb5aeaa and the 21-file change set matches 06ca2f9.
Evidence and remaining Main steps: `tasks/change_log.md#0131-release-preparation-2026-10-16`.

Previous intent:

```json
{
  "goal": "Prepare the Mir Yoke 0.13.1 release working tree with version metadata and migration notes only.",
  "goal_type": "maintenance",
  "scope": "Mirror 06ca2f9 release surfaces; preserve the carried Unreleased backlog and contract 1.1.0. Refresh lifecycle-hooks digest acknowledgement and generated adopter payload. No commits, delivery, capability operations, runtime-home writes, live databases, memory/context synchronization or generated Codex writes.",
  "priority": "normal",
  "updated": "2026-10-16",
  "history": [
    {
      "goal": "Close ontology impact and isolated distribution gaps and scope E06/E08 evidence.",
      "updated": "2026-10-16",
      "status": "complete",
      "evidence": "tasks/change_log.md#ontology-gap-development-2026-10-16"
    },
    {
      "goal": "Make local validation and fresh-checkout validate workflow commands pass while retaining the memory render guard.",
      "updated": "2026-10-16",
      "status": "complete",
      "evidence": "tasks/change_log.md#local-and-ci-validation-fixes-2026-10-16"
    },
    {
      "goal": "Prevent automatic consistency tests from rendering live agent memory.",
      "updated": "2026-10-16",
      "status": "complete",
      "evidence": "tasks/change_log.md#automatic-memory-render-guard-2026-10-16"
    },
    {
      "goal": "Prepare the Mir Yoke 0.13.0 release working tree with version metadata and migration notes only.",
      "updated": "2026-10-16",
      "status": "complete",
      "evidence": "tasks/change_log.md#0130-release-preparation-2026-10-16"
    },
    {
      "goal": "Correct E03 and E07 covered check references using existing executable behavior tests.",
      "updated": "2026-10-16",
      "status": "complete",
      "evidence": "tasks/change_log.md#superseded-cursor-covered-label-fix-before-0130-preparation-2026-10-16"
    }
  ],
  "status": "complete",
  "evidence": "tasks/change_log.md#0131-release-preparation-2026-10-16"
}
```


## Linux release-runner fixtures (2026-10-16)

Authority: current owner brief recorded in `tasks/intent.json`; design/cursor:
`tasks/plan.md`. Investigated failed release run 38847178888 with
`gh run view 38847178888 -R youngjin39/mir-yoke --log-failed` (exit 0).

### Root causes and bounded changes

- `test_missing_receipt_allows_setup_and_bootstrap_commands`: a trusted provider
  fixture inherited host Git filters and was rejected by
  `.claude/hooks/_lib/bootstrap-gate.sh#_mir_bootstrap_has_unsafe_git_extensions`.
- `test_adoption_recovery_allows_only_pinned_official_detached_worktree`: the
  same inherited configuration rejected the provider before pinned recovery.
- `test_worktree_add_accepts_the_persistent_provider_root`: overriding the fixture
  HOME did not suppress system Git config, so the same trust check rejected it.
- `test_canonical_file_anchor_matches_stored_locator_spelling_but_not_case`:
  only `src/a.py` existed, while ingest also declared `SRC/A.PY`. Linux correctly
  rejected the missing case-variant endpoint before the selection assertions.
- `test_uppercase_only_implementation_owner_does_not_match_lowercase_anchor`:
  its uppercase implementation endpoint was likewise missing on Linux.

The runner image installs Git LFS ([image installation source](https://github.com/actions/runner-images/blob/ubuntu24/20261012.334/images/ubuntu/scripts/build/install-git-lfs.sh));
its [Debian postinstall](https://github.com/git-lfs/git-lfs/blob/main/debian/postinst)
runs `git lfs install --skip-repo --system`. Inherited LFS configuration is the
reproduced cause and the image's likely source; the original runner's Git config
was not printed in its failed log. This is not evidence of a Git-version or
realpath defect.

`tests/test_bootstrap_start_gate.py` now opts only these three provider tests into
an `isolated_git_config` fixture (`GIT_CONFIG_NOSYSTEM=1`,
`GIT_CONFIG_GLOBAL=os.devnull`). Local hostile filter/fsmonitor/attributes,
dirty provider, wrong pin, aliases and non-executed hook assertions remain active.
`tests/test_srr_sql_neighborhood.py` explicitly creates both file spellings and
adds positive evidence that the uppercase relation exists and is queryable,
while preserving the negative lowercase-match assertions. Both spellings may
refer to one physical file on a case-insensitive filesystem; SQL identity remains
case-sensitive. Production validation/selection code and ontology are unchanged.

Semantic basis: `.mir/ontology-map.json#/relations/7` defines the local
`memory_relations.implemented_in` location relation; endpoint existence is enforced
by `src/mir/core/relations.py#_validate_endpoint`. Case-sensitive SQL comparison
is explicit in `src/mir/core/memory_relations.py#_locator_nodes` and
`src/mir/core/memory_relations.py#_implemented_in_rows`.

### Executed focused evidence

All uv commands used the owner-specified external UV_CACHE_DIR. Fixture scratch,
TMPDIR and pytest `--basetemp` were external and task-owned. No live memory file
or runtime-home file was used. Public command examples omit host-specific paths.

- Read-only baseline copies from HEAD, injected system/global LFS config and an
  external pytest probe tracking exact case of explicitly written fixture files:
  **5 failed** at the same trust/endpoint assertions as CI. The probe simulates
  endpoint existence only; it is not a Linux filesystem or a production change.
- The five named tests with the same injected config/probe: **5 passed in 4.42s**.
- `uv run pytest -q tests/test_bootstrap_start_gate.py tests/test_srr_sql_neighborhood.py`
  with system/global LFS injection: **45 passed in 12.43s**.
- `uv run ruff check`: exit 0, `All checks passed!`.
- `uv run python scripts/verify_codex_sync.py`: exit 0,
  `OK: Codex derivatives match Claude sources`. Checked-in generated files were
  not changed; verification generated comparison files only in external scratch.
- `uv run python scripts/mir_ontology.py impact --git-diff HEAD --strict`: exit 0,
  affected Task/intent entries only; no selected checks or stale refs.

Full-suite and final artifact evidence follows after execution. Actual Linux CI
execution and owner delivery remain outside this sandbox task.


### Dependent adopter inventory refresh

Initial full command `uv run pytest -q --ignore=tests/test_harness_consistency.py`
returned **3 failed, 2056 passed in 233.07s** (exit 1). The original five CI
failures passed. The remaining failures were the exact adopter inventory checks
and a slim integration check that preserved the edited plan as user-owned because
its recorded SHA256 was stale. The stale entries covered the six files changed
here plus `.mir/capability-lock.json`, whose hash was already stale after HEAD
`effbe4c` (that commit changed only the capability lock). The lock itself is unchanged.

Regenerate `config/adopter-payload.json` with the existing canonical command
`uv run python -m tools.template_assets --write-adopter-payload`; this updates only
dependent content hashes and does not execute adoption, capability or release work.


### Final full-suite evidence and remaining work

- `uv run python -m tools.template_assets --write-adopter-payload`: exit 0,
  `template asset classification: pass`. Only seven SHA256 entries changed;
  all paths, classifications and dispositions are preserved.
- `uv run pytest -q tests/test_advanced_reference_templates.py tests/test_greenfield_slim_integration.py tests/test_template_asset_classification.py`:
  **18 passed in 9.55s** after regenerating the dependent inventory.
- `uv run pytest -q --ignore=tests/test_harness_consistency.py` with external
  fixture scratch/TMPDIR and `GIT_CONFIG_SYSTEM` pointing to an external file
  containing the standard four Git LFS filter settings:
  **2059 passed in 219.53s (0:03:39)**, exit 0. This includes all five original cases.
- `uv run python scripts/mir_ontology.py mapping`: exit 0,
  **0 errors, 0 warnings; contract 1.1.0, mapping 1.1.0**.
- Strict impact and `git diff --check` pass. The ontology SHA256 remains
  `331ac91cd1d8ddd22558c11549395c62c06f2ad9616294470aec795ca44abe40`.

After final cursor/evidence edits and adopter-hash regeneration, the bounded
public-surface, inventory, slim integration and ontology tests returned
**29 passed in 12.30s**. Ruff again returned `All checks passed!`; read-only Codex
parity again returned `OK: Codex derivatives match Claude sources` (both exit 0).
No production or test-source changes follow the green full run. Actual execution was macOS with targeted Linux-like
configuration/endpoint simulation; no Linux CI job was started. Main owns any
subsequent CI rerun, commit or release. Generated Codex files, capability state,
live memory and runtime homes are unchanged. Task-owned scratch is removed after
final verification.


## Superseded cursor before ontology rejudgment (2026-10-16)

Linux release-runner test fixes (2026-10-16)

Authority: the current owner brief recorded in `tasks/intent.json`.
This is the single active cursor and design record. The previous completed cursor
is preserved in `tasks/change_log.md#superseded-cursor-0131-preparation-before-linux-test-fixes-2026-10-16`.

Outcome: identify and fix all five failures from release run 38847178888 while
retaining BootstrapGate trust checks and case-sensitive relation selection.

- [x] Read the failed log, distinguish product defects from platform-dependent fixtures, and reproduce the relevant assumptions.
- [x] Apply minimal fixes and verify the five cases and both affected modules.
- [x] Run full pytest excluding the consistency module, Ruff and read-only Codex parity.
- [x] Review the final diff and record causes, commands, results and remaining Main work.

Limits: no commits, tags, pushes, releases, capability operations, runtime-home
writes, live databases, memory render/sync, secrets or generated `.codex/**` writes.
Use the owner-specified external uv cache and external fixture scratch.

Completed: five original cases reproduce before the fixture fixes and pass afterward;
both affected modules pass (45 tests). The full suite with injected runner-style
system Git LFS config passes (2,059 tests; consistency module excluded). Ruff,
Codex parity, mapping (0 errors/warnings) and strict impact pass. Regenerated
adopter SHA256 entries retain the same paths, classifications and dispositions.
Production code, the ontology map and checked-in Codex derivatives are unchanged.

Evidence: `tasks/change_log.md#linux-release-runner-fixtures-2026-10-16`.
Actual Linux CI execution and authorized delivery remain with Main; no commit,
push, tag, release or live capability operation ran here.


## Ontology rejudgment G08/G13 (2026-10-16)

Authority: current owner brief and the common development instructions at
the Harness re-judgment development brief (`rejudgment-dev/common.md`).
Intent/design authority: `tasks/plan.md`, with structured intent in `tasks/intent.json`.
Initial tree was clean. Supplied map digest matched
`331ac91cd1d8ddd22558c11549395c62c06f2ad9616294470aec795ca44abe40`.
No live stores, network, secrets, runtime homes or generated Codex files were used or changed.
Fixture-only Git baselines are created by the existing test fixture; repository commits are forbidden.

### G08 bounded domain scenario and per-item findings

All twelve missing-proof findings were confirmed: existing tests exercised the gate,
errors and forwarding, but retained no Q1 domain answer plus bounded child receipt.
One scenario now uses the unchanged `/questions/0` (Q1), its exact three sources,
real checkout `scripts/mir_ontology.py lookup`, and real config loader in a Python
`-I` child outside the supplier working directory. It sends one map entry (not the
full map), source bodies/hashes, contract, map/checker/implementation/instruction
hashes, a bounded instruction excerpt and runtime version. Packet size is <64 KiB.
Child output is asserted equal to the parent packet; altered contract version and
source hashes fail. This is a child-process protocol rehearsal, NOT an actual
Claude/Codex agent handoff, installed-plugin or live-runtime observation.

The same question, source bodies/hashes and runtime are used with and without the
selected map entry. Both arms produce the SAME profile answer. The measured map
contribution is the explicit Q1 evidence association, not improved answer quality.
The child resolves code -> code_app and content -> content_workspace using the
real config implementation, and reports target-local integration ownership and
hook/MCP delivery from the source. ADR-90 is a policy evidence basis, not authority
to install or write. The existing ADR-90 invariant (`/domain/invariants/2`) now
links this scenario as a check; editing ADR-90 selects it through strict impact.
Source/question identity, evidence hashes and uncertainty are explicit assertions.

| Item | Scoped retained result; remaining limit |
| --- | --- |
| 1.1 | Q1 intent is profile adoption plus integration ownership; selected question is exact. No agent understanding claim. |
| 1.2 | Config implementation selects code/content packs and target-local delivery; ADR-90 supplies design evidence. No target write. |
| 1.3 | Real lookup followed by real impact selects the linked check without executing it. No autonomous agent planning claim. |
| 1.6 | Q1 retrieves exactly its three local evidence sources; MK and live memory remain untested. |
| 1.7 | Python child receives and uses the bounded versioned packet; actual agent handoff remains unobserved. |
| 1.goal | One Yoke-domain selection/evidence rehearsal covers these uses; not all acting agents or all hosts. |
| 2.6.2 | Printed receipt pins source/map/contract/runtime and retains interpretation scope and uncertainty. |
| 5-2.10 | Isolated source fixture can answer Q1 outside supplier cwd. Installation, loading, tools and domain use are separate; this adds only synthetic domain use. |
| 5-2.done | Synthetic domain result added; existing rollback/distribution evidence is not reinterpreted as fresh runtime proof. |
| 5-4.10 | Identical source/question arms plus bad-version/bad-hash negatives; answer unchanged, evidence association differs. |
| 5-4.5 | Real selective lookup plus actual Python child packet equality; no live agent execution claimed. |
| 5-4.done | Local Q1/domain-invariant link is exercised; runtime/memory/agent-quality unknowns remain explicit. |

These rows are development evidence, not LIVE, ACCEPTED, or a rejudgment status
promotion. Broader actual-agent/runtime observations remain with Main/owner.

### G13 inspected producer/consumer boundary

Finding confirmed: target contents are not hashed by the declared YAML consumer.
Local non-applicability applies to target-derived cache invalidation because there
is no such cache in this path. Inspected boundaries:

- `src/mir/core/relations.py#_load_graph` reads current graph bytes and produces Edge declarations plus graph digest.
- `src/mir/core/relations.py#query_relations` validates endpoint safety/availability and traverses declarations. `_result` supplies no execution result or target-content digest.
- `src/mir/core/relations.py#bundle_relations` shares the graph only within one call; it stores no downstream result cache.
- `src/mir/cli/relations.py#main` queries, renders and exits; the memory route is explicitly separate.
- `src/mir/core/memory_relations.py` separately verifies relation SOURCE hashes/provenance. That is not cached test-target execution evidence and is not widened by this finding.

The existing graph-reload/digest and removed-verification-edge tests are retained.
A new target-only edit regression prohibits target reads, observes unchanged
DECLARATIONS after the edit, asserts declaration-only scope/edge fields, then
removes the target and observes exclusion. It does NOT call unchanged declarations
fresh execution evidence. The query docstring and E06 reason record the boundary.
No product cache or freshness API was added. No fail-first behavior claim applies
to this non-applicability proof: it passes existing behavior by design.

### Fail-first and intermediate checks

- New G08 scenario before adding its invariant check link: **1 failed** at the
  missing selected check after a domain-source change (exit 1). All preceding
  lookup, same-source comparison, child provenance and error assertions passed.
- After wiring the map: **2 passed** (G08 scenario + target-only boundary proof).
- First broader focused run: **7 failed, 25 passed** due solely to map byte-budget
  warnings; subsequent run reproduced the budget issue. Map descriptions and
  whitespace were compacted within the existing 12,288-byte budget; gate unchanged.
- Ruff initially reported three E501 lines, then passed after wrapping.
- Bare Codex parity invocation initially failed to access its default uv cache;
  rerun with owner-specified UV_CACHE_DIR passed without changing derivatives.
- Focused ontology/relations/CLI run: **45 passed in 4.03s** before final provenance
  assertions. Final commands/results follow below.

### Pinned scenario receipt

Question: Which capabilities can code-only and content consumers adopt, and which integration surfaces remain project-owned?
Contract: `mir.common-semantics@1.1.0`; selection: `/questions/0`.
Runtime: isolated Python fixture, Python 3.12.13, Clang 17.0.0, macOS.
Final map SHA256: `c20fbf3bdb910d3872b1f66730b56e0f34e8fa00c707e91eedd458c25a374340`.

| Evidence | SHA256 |
| --- | --- |
| config/capability-sources.json | f77b60b5b7016a49bb80038a16aba57ccc717f7dbb96344ebaf42d4d9ff69e74 |
| docs/decisions/adr-90-role-plugins-and-common-hooks.md | 32dc4d8240e102a5e155f681681d8b7a4a09c7522df42d8fbf88b9e392bde1b6 |
| ARCHITECTURE.md | 6f18414515b8ed1516b495d5328bd45ad47e1738e7616d1b11c6dafd3e7971cc |
| ontology_check.py | d4383a8b30f92463f73f6dcbe0840737296701a4a66d3a6bd4f4adb0c42ee528 |
| ontology/SKILL.md | fc497e961e4e748c9217896c6e8c8ce7a69ecca46e672da03edc7b3c5d87d80a |
| src/mir/core/capabilities/config.py | 59472973939249bfdc899c2512e19c6ec1dbdd37164805ee333e00a07543a767 |

Result: code_app = mir-core, mir-code, mir-lifecycle-hooks; content_workspace =
mir-core, mir-content, mir-lifecycle-hooks. Integrations remain target-local-only.
Uncertainty: no installation, loading, tools, live agent or runtime discovery observed.

### Final validation and remaining Main work

All uv commands used `a shared `UV_CACHE_DIR``.

- `uv run pytest -q tests/test_mir_ontology.py tests/test_relations.py tests/test_cli_relations.py tests/test_advanced_reference_templates.py tests/test_greenfield_slim_integration.py tests/test_template_asset_classification.py --deselect tests/test_harness_consistency.py --basetemp=<scratch>`:
  **63 passed in 17.63s**, exit 0, on the final test/source/map state.
- `uv run ruff check`: **All checks passed!**, exit 0.
- `python3 scripts/mir_ontology.py mapping`: **0 errors, 0 warnings**, exit 0.
- `python3 scripts/mir_ontology.py impact --git-diff --strict`: exit 0;
  selects the new scenario and existing covered checks; no stale refs or
  undeclared affected invariant check links.
- `a shared `UV_CACHE_DIR` python3 scripts/verify_codex_sync.py`:
  **OK: Codex derivatives match Claude sources**, exit 0; no regeneration needed.
- `git diff --check`: exit 0.
- `uv run python -m tools.template_assets --write-adopter-payload`: exit 0;
  only the seven dependent file hashes change, with paths/classifications/dispositions preserved.

The inventory is regenerated once more after this evidence-only append and its
focused inventory/ontology checks are rerun. Full pytest was not run for this
bounded map/test/documentation change. Main should replay mapping, strict impact
and the selected tests after integration; no generated Codex change is pending.
Actual Claude/Codex child execution, supported-runtime installation/loading/tool
observations, live retrieval, other hosts and old resident sessions remain outside
this authorized synthetic scope. No owner decision is needed to ship this bounded
development evidence; broader acceptance requires separate observations.
No repository commit, push or release ran. Task-owned external scratch is removed
after verification; no daemon or emulator was started.


## Maintenance continuity inputs (2026-10-16)

Verbatim superseded continuity text, preserved before the owner-directed maintenance pass.

### Prior tasks/plan.md

```markdown
# Plan

## Active task: ontology rejudgment G08/G13 (2026-10-16)

Authority: the current owner brief, including the common rejudgment development
instructions. This cursor records the requested intent before implementation.

Outcome: one repeatable synthetic Yoke-domain selection/evidence scenario through
the real map and lookup/impact runner, and an inspected G13 target-freshness boundary.
This proves selection/evidence use only, not agent quality, LIVE or ACCEPTED.

- [x] Retain fail-first evidence and bounded child-process provenance assertions.
- [x] Record G13 local non-applicability without inventing a cache product.
- [x] Run focused tests, lint, mapping and strict impact; record remaining Main work.

Limits: no network, live databases, memory operations, commits, delivery,
runtime-home writes or generated `.codex/**` edits. Use external fixture scratch
and a shared `UV_CACHE_DIR`.

Evidence: `tasks/change_log.md#ontology-rejudgment-g08-g13-2026-10-16`.
```

### Prior tasks/checklist.md

```markdown
# Checklist

Status projection for `tasks/plan.md`: executor common v3.5 now includes all six items.
All sixteen new regression cases failed before their fixes, then passed.
Combined full pytest: 1621 passed; executor tests: 615 passed, with zero new
mir-wt temporary directories. Ruff, Python 3.11 compilation, sync and Codex parity
passed. Committed locally by the Mir Harness Main after its own full re-run
(the Codex sandbox could not create `.git/index.lock`).
Evidence: `tasks/change_log.md`, "Executor common v3.5 maintenance (2026-10-02)".
```

### Prior tasks/handoffs/session-handoff-LATEST.md

```markdown
# Session Handoff — P4 ontology work path (2026-10-15)

Resume pointer: `tasks/plan.md` is the only cursor; `tasks/intent.json` records authority.
Evidence and superseded continuity text: `tasks/change_log.md`,
"P4 ontology work path (2026-10-15)".
Checkout runner, pytest mapping/strict-impact gate, optional MK instruction and scoped
E01-E10 closure are implemented. Map: 1.1.0, 0/0, 12,245 bytes; CLAUDE: 3,587 bytes.
Final affected/package/derivation/assets and integrity checks: 171 passed. Full-suite evidence is
in the change log. Separately updated CLAUDE/AGENTS were preserved; read-only parity
now passes. This executor did not write generated derivatives. No commit or delivery is authorized.
The corrected full-suite process exited 0; its final summary file was unavailable when read.
No real MK, intake, live database, consumer write or capability lock edit was performed.
The generated snapshot below belongs to the preceding hook run; inspect current Git status.

<!-- mir:runtime-snapshot:begin -->
## Runtime Snapshot (Generated)

### Active Plan Items
- No open plan items.

### Working Tree
- Working tree clean.
<!-- mir:runtime-snapshot:end -->
```

### Prior maintenance skill count wording

```text
description: "Periodic maintenance checkup of an agent-operated repository across twenty-one fixed items: consistency, operating base, documents, archiving, context, database/memory/graph inspection and repair, Claude/Codex harness consistency, skills and agents, instruction docs, rules and lessons, architecture, delegation and routing, continuity, work-context retrieval, token efficiency, test health, code/security/dependencies, integrity evidence, runtime behavior, open decisions, and parity when either CLI is Main.\n\nTrigger: repository maintenance, periodic check, repo checkup, fleet maintenance, clean up and improve the repository"
5. Report against all twenty-one items using the evidence below.
```


## Repository maintenance (2026-10-16)

Authority: the current owner brief, recorded in `tasks/intent.json`; the single
active cursor is `tasks/plan.md`. The parent-supplied Harness directive dated
2026-10-16 (ADR-91) supplies scope evidence, not independent authority.
Start `git status --short`: empty. No pre-existing dirty paths.
No commit, push, tag, release, version change, live database write, secret read,
consumer write, runtime-home installation or generated `.codex/**` edit is part of this pass.

### Bounded improvements

The checklist and handoff pointed to 2026-10-02 and 2026-10-15 while the cursor
pointed to completed 2026-10-16 ontology work. The current intent, cursor, status
projection and resume pointer now describe this pass. Their superseded text is
preserved verbatim under "Maintenance continuity inputs (2026-10-16)" above.
Previous intent entries remain in `tasks/intent.json`.

The portable maintenance skill still specified 21 items. Add the owner-requested
Agent/Loop/Graph/Ontology assessment as item 22 and update its existing count
contract test. No new gate, runtime hook or execution restriction was introduced.
The prior count wording is preserved above. This changes a shared plugin source
and therefore needs Harness review before any later authorized delivery.

### Checklist evidence

1. DONE: current path verification passed (9 files, 77 refs); Codex generation parity passed.
2. NO CHANGE: active hook registrations and capability manifests retain ADR-90 boundaries; retired composition remains under reference templates.
3. DONE: current continuity documents now describe the maintenance brief; historical spec remains explicitly superseded-reference (`spec/STATE.md`).
4. DONE: prior cursor, checklist and handoff text, plus replaced skill count wording, are preserved verbatim in this evidence log.
5. DONE: one active cursor, one resume pointer, one projection and one evidence log; no competing maintenance report was added.
6. NO CHANGE: SQLite backup including WAL was diagnosed on SSD scratch: integrity_check=ok, foreign_key_check=0 rows; 348160 bytes, 21 facts, 12 entities. All facts have valid created_from rows; the single source exists and its hash matches. No missing affected-file paths or missing-source expiries. No live DB repair.
7. NO CHANGE: common source-to-Codex parity passed; safety bounds remain intact.
8. BRANCH-ONLY: shared maintenance skill and count contract cover 22 items on held branch `maint/repo-maintenance-item-22` (b181541); main retains 21 items. The 33 passing isolated/common skill checks describe the pre-split writer tree. See the post-split correction below.
9. NO CHANGE: CLAUDE.md 40 lines/3587 bytes; AGENTS.md 42 lines/3676 bytes, before=after; declared size budgets are 55/3600 and 60/3800.
10. NO CHANGE: generated lessons and memory-map sections match snapshot renders; neither generated document was edited.
11. NO CHANGE: ARCHITECTURE.md matches Starter, recipe, optional CLI, four plugin packages and inert historical references.
12. NO CHANGE: generated routing lock matches the supplied policy: gpt-6.1-sol/medium default, narrow/unit gpt-6-luna/high, cap 8, depth 2, no full-history forks. Central source freshness was not independently checked; lock unchanged.
13. DONE: owner intent is recorded in the canonical intent/cursor; stale projections were replaced with pointers and retained in history.
14. NO CHANGE: ontology lookup returned /questions/0 (Q1) and its capability config, ADR-90 and architecture evidence; local retrieval works without MK.
15. NO CHANGE: both registered SessionStart commands executed successfully with identical 550-byte stdout and no stderr, SHA256 a3b6e93ee355a65eb3f8d159b87b145ac3744d65421febf861a862a85d2ffd88. Startup intentionally carries safety/profile context, with task context retrieved on demand.
16. SKIPPED (commit-bound closure): final full pytest returned 2061 passed, 1 failed in 299.13s; the changed plugin cannot match the old committed lock before Main commits the implementation and rebinds it under ADR-80/86. The guard remains mandatory. Cache and fixture scratch are external; pytest cache provider is disabled.
17. NO CHANGE: uv audit --frozen found no known vulnerabilities or adverse project statuses in 28 locked packages. Installed-package freshness check found 14 newer versions; no dependency changes. License metadata inspected for 26 installed packages (MIT/BSD/Apache/MPL/PSF); optional sqlite-vec and platform-only colorama are not installed. Credential-signature scan covered 885 tracked text files, excluding protected secrets; all four hits are explicit test fixtures at tests/test_capability_security.py:530,540,550 and tools/mir_executor/tests/test_v31_regressions.py:66. Values were not reported. This is a bounded scan, not a comprehensive security certification.
18. SKIPPED (lock rebinding pending): adopter inventory is regenerated through tools.template_assets after source/evidence changes. Published capability lock is preserved; new mir-core source digest needs Harness-owned delivery/rebinding.
19. NO CHANGE: observed uv 0.11.3, Claude Code 2.1.301 and Codex CLI 0.159.2; both plugin inventories list all four Mir packages enabled at 0.13.1. Direct execution of both configured SessionStart commands matches. These observations do not prove fresh-session skill invocation or native hook trust.
20. NO CHANGE: no new accepted-decision conflict or owner policy decision was found. Runtime trust and future delivery work are listed once under remaining work below.
21. SKIPPED (partial evidence only): source/generated rules, registrations, absent project MCP binding and direct SessionStart outputs match. Native Codex hook trust and actual fresh Claude/Codex session discovery/enforcement could not be inspected through this noninteractive writer. No trust hash was written.
22. DONE: Agent uses the shared contract, generated routing and four enabled packages; continuity drift is repaired. Loop remains an optional explicit CLI surface (`tests/test_loop_cli.py`, `tests/test_loop_driver.py`), with no standing process started. Graph uses the source-backed memory declaration and bounded YAML reader; CR-006 implementation retrieval returned 7 edges, with 5 unavailable historical file endpoints explicitly skipped. The memory-only SRR anchor is not a YAML identity. Ontology uses the unchanged 1.1.0 map and Q1 lookup/strict impact; the smallest shared improvement is the explicit four-axis checklist item. No graph/cache/service was added.

### Semantic scope

Map SHA256 remains `c20fbf3bdb910d3872b1f66730b56e0f34e8fa00c707e91eedd458c25a374340`;
contract `mir.common-semantics@1.1.0`.
Map `/questions/0` supplies Q1's evidence refs.
`/vocabularies/2` marks spec readiness as historical; `/vocabularies/4`
does not equate stored active facts with truth/freshness; `/vocabularies/5`
separates capability diagnostics from READY; `/vocabularies/9` scopes intent
completion to the task. `/domain/invariants` retains no standing consumer authority.
Snapshot source inspection, not the active label, established source existence/hash match.
No MK or parent ContextPack was used to establish a new semantic claim.

### Executed checks and intermediate results

All uv commands use the owner-specified external `UV_CACHE_DIR`.
All temporary output uses the owner-specified external task scratch via `TMPDIR`.

- Fail first: `uv run pytest -q -p no:cacheprovider tests/test_repo_maintenance_skill.py --basetemp=<scratch>/fail-first`: 1 failed, 11 passed; item 22 was absent before the skill fix.
- After fix: `uv run pytest -q -p no:cacheprovider tests/test_repo_maintenance_skill.py tests/test_common_skill_contracts.py tests/test_plugin_skill_packages.py --basetemp=<scratch>/skill-fixed`: 33 passed.
- First full run, started before skill/test edits: 2 failed, 2060 passed in 385.52s. It had collected the old 21-item contract and also observed the intermediate stale adopter inventory. This is not final-state evidence; a clean final collection was started after both fixes.
- `uv run ruff check`: all checks passed.
- `uv run python scripts/verify_codex_sync.py`: Codex derivatives match Claude sources; only temporary generator output was produced.
- `python3 scripts/mir_ontology.py mapping`: 0 errors, 0 warnings.
- `python3 scripts/mir_ontology.py impact --git-diff --strict`: exit 0; Task/intent affected, no stale refs or undeclared check links; selection is not execution.
- `python3 scripts/verify_context_paths.py`: 9 files, 77 refs passed.
- `uv run python scripts/verify_repo_agent_management.py`: schema, wiring, catalog, pack, specialist and repositories-dir checks passed; dispatch audit had 0 entries.
- `uv audit --frozen`: exit 0, 28 packages, no known vulnerabilities or adverse statuses (OSV service; experimental CLI warning).
- `uv pip list --outdated --format json`: 14 installed packages have newer versions; this does not establish compatibility with declared upper bounds.
- SQLite `.backup` succeeded; opening the WAL-mode backup with the sqlite3 CLI initially returned unable-to-open. An immutable read-only connection to that stable backup passed integrity and FK checks. No live DB diagnostic writes were used.
- `uv run mir memory render --db <snapshot> --target all`: exit 0; both generated sections match. `uv run mir memory reconcile-missing --db <snapshot> --project-root . --dry-run`: exit 0, would_expire=0. Both ran only on the backup; optional sqlite-vec was unavailable, so they used FTS5.
- Initial YAML retrieval with the memory-only SRR anchor returned unknown anchor; corrected `uv run mir relations query CR-006 --purpose implementation --json` exited 0 with 7 edges and the historical-endpoint notice above.
- `claude plugin list --json` and `codex plugin list --json`: exit 0, four Mir packages enabled each. Codex also warned that PATH aliases could not be created under the sandbox; no native trust inference follows.
- A first multiline edit command was rejected by the existing shell screening hook; the quoted Python invocation succeeded. The hook was not changed or bypassed.

### Integrity and remaining work

`config/adopter-payload.json` is regenerated with
`uv run python -m tools.template_assets --write-adopter-payload`; classifications,
paths and dispositions are preserved, only dependent file hashes change.

The published local capability receipt matches the original mir-core tree digest
`1d4d89c5f05a78da485faa4e653ebff362f3c7a41f27b902636f12422e13ec9c`.
The edited source tree digest is
`0752773c635ae2ad86be46c5ff8447a8d28874b07f8039550fb14437c27b1b11`.
ADR-80 section 7 and ADR-86's commit-bound managed-configuration rule require a committed implementation before lock reconciliation. Do not restamp a published-revision receipt with uncommitted source bytes.
Harness Main owns any later approved revision, delivery, sync/finalization and
runtime discovery receipts. No version bump or release is included here.

No owner decision is needed for these bounded edits. Harness must inspect native
hook trust and fresh-session discovery/enforcement before claiming full live Main
parity. Either retain this limited evidence or obtain those runtime observations;
only the broader parity claim is blocked. No safety gate or new restriction is added.

Dependency upgrades (14 newer installed packages) and optional/platform-only license
metadata remain separate compatibility work. No optional vector package was installed.
The isolated activation verifier was not run because this pass does not install into runtime homes or expand commit authority; read-only host inventory probes were used. Fixture Git operations inside the required pytest suite remain test setup, not a repository commit.
The release-readiness delivery workflow was not invoked; maintainer checks run directly.


### Final-state failures diagnosed before closeout

The second full collection completed with **2060 passed, 2 failed in 336.71s**:
`tests/test_capability_cli.py::test_repository_lock_is_portable_and_matches_managed_trees`
reported the old/new mir-core digest difference above, and
`tests/test_public_template_surface.py::test_should_expose_no_private_absolute_path_when_public_surfaces_are_scanned`
found newly recorded host paths in this log. Those paths have been generalized to
owner-specified cache/scratch variables to preserve the public contract.
The lock assertion is not weakened or skipped in the suite. ADR-80 section 7 and
ADR-86 require Main's committed implementation before lock reconciliation.
This writer has no commit authority, so that exact remaining failure belongs to
INTEGRITY/NEEDS HARNESS. A final full run follows the public-log correction.

`uv run python <installed-skill-creator>/scripts/quick_validate.py plugins/mir-core/skills/repo-maintenance`
also exited 0 (`Skill is valid!`).

After public-log correction and inventory regeneration, the focused public-surface, maintenance-skill and adopter-inventory run passed **21 tests in 0.42s**.

The documented `bash .claude/hooks/session-end.sh` ran with the explicit repository root and exited 0. It refreshed the canonical handoff's generated runtime snapshot through `pre-compact.sh`, reporting the two still-open verification/closeout items and 8 dirty paths. Generated snapshot contents were produced by the hook, not hand-edited.


### Final writer closeout

- Final full command: `uv run pytest -q -p no:cacheprovider --basetemp=<scratch>/pytest-closeout`.
  **2061 passed, 1 failed in 299.13s**, exit 1. The sole failure is
  `tests/test_capability_cli.py::test_repository_lock_is_portable_and_matches_managed_trees`.
  It compares edited mir-core bytes with the prior committed lock. This gate is
  still failing, not waived; Main must follow ADR-80/86 before claiming closure.
- The public-path failure is fixed; the final full suite contains no other failure.
- Snapshot `uv run mir memory query SRR --limit 3 --db <snapshot>` exited 0
  with one relevant FTS result. No live database was queried or written by this probe.
- Live memory DB remains 348160 bytes with its original 2026-09-21 modification time;
  its WAL remains 0 bytes with its original 2026-10-16 00:56 modification time.
- Final source instruction sizes are unchanged (CLAUDE 40 lines/3587 bytes;
  AGENTS 42 lines/3676 bytes). `git diff -- .codex .codex-sync AGENTS.md uv.lock VERSION`
  is empty. No binaries/interpreters, services, emulators or daemons were changed/started.
- Current intent/cursor mark only this bounded writer pass complete.
  Committed-object integrity and live native Main parity remain explicitly unverified.
- The canonical runtime snapshot is refreshed again through SessionEnd after
  checking off the cursor. Inventory regeneration and affected public/skill/inventory
  checks follow this evidence update; final command results are reported to Main.
- Scratch is removed after the checks; no owner-repository commit, push or release ran.

End `git status --short` (the same eight modified paths remain after inventory refresh):

```text
 M config/adopter-payload.json
 M plugins/mir-core/skills/repo-maintenance/SKILL.md
 M tasks/change_log.md
 M tasks/checklist.md
 M tasks/handoffs/session-handoff-LATEST.md
 M tasks/intent.json
 M tasks/plan.md
 M tests/test_repo_maintenance_skill.py
```

After cursor/intent closeout and the generated SessionEnd snapshot, `uv run pytest -q -p no:cacheprovider tests/test_public_template_surface.py tests/test_repo_maintenance_skill.py tests/test_template_asset_classification.py --basetemp=<scratch>/final-focused` returned **21 passed in 0.57s**, exit 0. Inventory is regenerated once more after this append and its exact-inventory assertion is checked again.


## Independent-review corrections (2026-10-16)

Authority: owner-directed independent review and confirmed F2–F4, supplied by
Mir Harness Main. The active cursor is `tasks/plan.md`. Scope is documentation
only on main; the held item-22 branch remains deferred to owner D1.

Evidence: `fc548ec` changes six record/inventory files and no skill or test;
main has the 21-item skill/count contract. ADR-86, Decision, permits reconciling
the managed lock to a committed implementation. D1 retains the release hold
as a Main/owner choice, not a technical requirement of the lock.
Semantic scope: `.mir/ontology-map.json` `/concepts/Task` identifies the cursor;
`/vocabularies/9` scopes intent completion to task work, not release/runtime proof.
The map remains unchanged at the owner-supplied SHA256.

Superseded current-state wording is retained verbatim below. Replacements in
the named files and item 8 above point to this dated record.

### Prior tasks/plan.md

```text
# Plan

## Active task: repository maintenance (2026-10-16)

Authority: the current owner maintenance brief, recorded in `tasks/intent.json`.
The parent-supplied Harness directive is evidence of scope, not independent authority.

Outcome: assess all 22 requested items, apply minimal evidenced improvements,
and record exact checks, integrity dependencies and remaining Main/owner work.

- [x] Inspect contracts, continuity, memory snapshot, routing and runtime boundaries.
- [x] Apply bounded improvements and retain superseded text verbatim in the log.
- [x] Run full pytest, Ruff, Codex parity and ontology checks on the final sources.
- [x] Update continuity, rebind the adopter inventory, inspect diff and report all items.

Limits: no commits, release/version changes, consumer writes, live database writes,
secrets or generated `.codex/**` edits. Scratch stays on the external SSD.

Evidence: `tasks/change_log.md#repository-maintenance-2026-10-16`.
Prior cursor and projections: `tasks/change_log.md#maintenance-continuity-inputs-2026-10-16`.

Writer pass finished: full pytest has 2061 passes and one committed-lock failure.
Harness Main must review/commit the implementation and reconcile its lock under
ADR-80/86. Native hook trust and fresh-session discovery remain unobserved.

Main disposition (Mir Harness, 2026-10-16): the repo-maintenance item-22 skill change, its test and the adopter-payload rehash are held on local branch `maint/repo-maintenance-item-22` (b181541), not main, because the capability lock binds only at a release; merging needs an owner-approved release.
```

### Prior tasks/checklist.md

```text
# Checklist

Status projection for `tasks/plan.md`: the 22-item writer maintenance pass is ready for Main review.
Full pytest: 2061 passed, 1 failed (commit-bound capability lock; ADR-80/86).
Focused skill/common-plugin checks: 33 passed; corrected public-surface/skill/inventory checks: 21 passed.
Ruff, generated Codex parity, path references and ontology mapping/strict impact passed.
Harness Main owns implementation commit, lock reconciliation and native runtime trust observations.
Evidence: `tasks/change_log.md#repository-maintenance-2026-10-16`.
Prior projection: `tasks/change_log.md#maintenance-continuity-inputs-2026-10-16`.
```

### Prior tasks/handoffs/session-handoff-LATEST.md

```text
# Session Handoff

Resume pointer: `tasks/plan.md` is the only active cursor; `tasks/intent.json` records authority.
Read `tasks/checklist.md` for status and
`tasks/change_log.md#repository-maintenance-2026-10-16` for this pass.
Superseded handoff text is preserved verbatim at
`tasks/change_log.md#maintenance-continuity-inputs-2026-10-16`.
No commit, release, live database write or generated `.codex/**` edit is authorized.

<!-- mir:runtime-snapshot:begin -->
## Runtime Snapshot (Generated)

### Active Plan Items
- No open plan items.

### Working Tree
- Working tree dirty (8 paths; inspect git status --short).
<!-- mir:runtime-snapshot:end -->
```

### Prior checklist evidence item 8

8. DONE: shared maintenance skill and count contract now cover 22 items; isolated/common skill checks passed (33 tests).

### Correction checks

- Before and after the documentation correction: `uv run pytest -q -p no:cacheprovider tests/test_capability_cli.py::test_repository_lock_is_portable_and_matches_managed_trees tests/test_repo_maintenance_skill.py tests/test_public_template_surface.py --basetemp=<scratch>`: 16 passed, 0 failed on each run (0.51s / 0.25s). UV_CACHE_DIR used the owner-specified external cache; scratch stayed on the external SSD.
- Python assertions: intent JSON parses, corrected fragment resolves to the existing heading, `/vocabularies/9` names the maintainer intent lifecycle, and the supplied map digest is unchanged: 4 passed, 0 failed.
- `git diff --check`: passed. No code/test finding or fail-first case applies. No full-suite rerun, generator, commit, release or held-branch edit was performed. Main owns review/commit; owner D1 retains the held-branch decision.

## Matrix pass 2026-10-16

Observation date: 2026-10-17 KST. Authority: the current owner-directed per-item
verification request, recorded by the existing intent in `tasks/intent.json`.
`tasks/plan.md` remains the single active cursor and design authority.
Starting worktree: clean on main. The held item-22 branch is outside this pass.

### Superseded continuity text

Prior `tasks/plan.md`, preserved verbatim:

```text
# Plan

## Active task: repository maintenance (2026-10-16)

Authority: the current owner maintenance brief, recorded in `tasks/intent.json`.
The parent-supplied Harness directive is evidence of scope, not independent authority.

Outcome: assess all 22 requested items, apply minimal evidenced improvements,
and record exact checks, integrity dependencies and remaining Main/owner work.

- [x] Inspect contracts, continuity, memory snapshot, routing and runtime boundaries.
- [x] Apply bounded improvements and retain superseded text verbatim in the log.
- [x] Run full pytest, Ruff, Codex parity and ontology checks on the final sources.
- [x] Update continuity, rebind the adopter inventory, inspect diff and report all items.

Limits: no commits, release/version changes, consumer writes, live database writes,
secrets or generated `.codex/**` edits. Scratch stays on the external SSD.

Evidence: `tasks/change_log.md#repository-maintenance-2026-10-16`.
Prior cursor and projections: `tasks/change_log.md#maintenance-continuity-inputs-2026-10-16`.

Post-split state: `fc548ec` contains maintenance records/inventory only; main
retains the 21-item skill/count contract. The targeted capability-lock regression
passes; the 2061-pass/1-failure full run describes the pre-split writer tree.
Native hook trust and fresh-session discovery remain unobserved.

Main disposition (Mir Harness, 2026-10-16): the repo-maintenance item-22 skill change, its test and the adopter-payload rehash are held on local branch `maint/repo-maintenance-item-22` (b181541), not main, by Main/owner choice D1 pending an owner-approved release merge. ADR-86 permits reconciling the lock to a committed implementation without requiring a release.

Independent-review fix scope (F2–F4, 2026-10-16): correct post-split projections,
retain superseded wording, and repair the intent evidence fragment.
Checks: targeted lock/skill/public-surface tests, evidence-anchor validation and
`git diff --check`. History: `tasks/change_log.md#independent-review-corrections-2026-10-16`.
```

Prior `tasks/checklist.md`, preserved verbatim:

```text
# Checklist

Status projection for `tasks/plan.md`: post-split maintenance records are committed in `fc548ec`; independent-review F2–F4 corrections are ready for Main review.
The main skill/count contract retains 21 items; item 22 remains on held branch `maint/repo-maintenance-item-22` (b181541), pending owner D1.
Current targeted capability-lock, maintenance-skill and public-surface checks: 16 passed. No lock reconciliation is needed for the records-only split.
The prior full pytest result (2061 passed, 1 failed) and focused results describe the pre-split writer tree, not current main.
Prior writer checks: Ruff, generated Codex parity, path references and ontology mapping/strict impact passed.
Harness Main owns review/commit and native runtime trust observations.
Evidence and superseded projection: `tasks/change_log.md#independent-review-corrections-2026-10-16`.
Original maintenance evidence: `tasks/change_log.md#repository-maintenance-2026-10-16`.
```

Prior `tasks/handoffs/session-handoff-LATEST.md`, preserved verbatim:

```text
# Session Handoff

Resume pointer: `tasks/plan.md` is the only active cursor; `tasks/intent.json` records authority.
Read `tasks/checklist.md` for status and
`tasks/change_log.md#repository-maintenance-2026-10-16` for this pass.
Superseded handoff text is preserved verbatim at
`tasks/change_log.md#maintenance-continuity-inputs-2026-10-16`.
No commit, release, live database write or generated `.codex/**` edit is authorized.

<!-- mir:runtime-snapshot:begin -->
## Runtime Snapshot (Generated)

### Active Plan Items
- No open plan items.

### Working Tree
- Historical pre-commit snapshot (2026-10-16): working tree dirty (8 paths); see `tasks/change_log.md#independent-review-corrections-2026-10-16`. Inspect `git status --short` for current state.
<!-- mir:runtime-snapshot:end -->
```

Prior changed intent fields, preserved verbatim:

```json
  "scope": "This repository writer pass only; the commit-bound integrity gate and native runtime trust evidence remain for Harness Main. No commit, release, consumer write, live database write, secret access or generated .codex edit.",
  "evidence": "tasks/change_log.md#repository-maintenance-2026-10-16",
```

### Current-run evidence and scope

Observation date: 2026-10-17 KST. The installed maintenance skill supplies items
1–21; the current owner request supplies item 22. The ontology skill was also
read. No cross-project MK lookup was needed. Contract: mir.common-semantics@1.1.0;
map SHA256: c20fbf3bdb910d3872b1f66730b56e0f34e8fa00c707e91eedd458c25a374340.
Semantic anchors: /concepts/Agent, /concepts/Task, /relations, /vocabularies/2,
/vocabularies/4, /vocabularies/9, /domain/invariants and /questions/0. Historical
readiness, stored active facts, task completion and current proof stay distinct.

All uv commands use the specified external UV_CACHE_DIR. Execution probes use
`uv run --no-sync`; pytest disables cacheprovider. TMPDIR, Ruff cache, SQLite
snapshots and pytest basetemp are below the specified external scratch directory.
No tracked generated output is refreshed; suite fixtures are disposable.

- `python3 scripts/verify_context_paths.py`: PASS, 9 files / 77 references.
- Read-only `tools.template_assets.classify_tracked_files`: PASS, 885 files
  classified exactly once; no unclassified, duplicate or prohibited paths.
- `python3 scripts/mir_ontology.py mapping`: 0 errors / 0 warnings, version 1.1.0.
- `python3 scripts/mir_ontology.py lookup "Which capabilities can code-only and content consumers adopt" --limit 1`:
  Q1 (/questions/0) returned capability config, ADR-90 and architecture evidence.
- `python3 scripts/mir_ontology.py impact --git-diff --strict`: exit 0; Task cursor
  affected, no selected checks, stale refs or undeclared check links. Selection
  is navigation, not execution proof.
- `uv run --no-sync ruff check`: all checks passed.
- `uv run --no-sync python scripts/verify_repo_agent_management.py`: schema,
  wiring, catalog, pack, specialist and repositories-directory checks passed;
  dispatch audit 0 entries / 0 non-compliant.
- Inline Python imported read-only `scripts.verify_codex_sync` validators:
  plugin providers, managed surfaces, portable hook copy and nested instruction
  validation returned zero findings. All 17 manifest mappings resolve. Root body
  equality and the one nested Starter body transformation passed. All 12 agent
  names/descriptions, absent Codex model pins and declared read-only boundaries
  match their sources. An initial probe incorrectly expected a `model` key and
  raised KeyError; the corrected probe follows the intentionally omitted pins
  in scripts/generate_codex_derivatives.sh:365. The standalone generator-backed
  verifier remains for Main; these are explicitly narrower read-only checks.
- In-memory `render_hooks` matches both checked-in runtime hook JSON files.
  Eleven configured script paths exist. config/project-hooks.json:112 declares
  Claude-only StopFailure; SessionEnd declares Codex's 3-second override versus
  Claude's 60 seconds. No project MCP file or Codex MCP table exists.
- Inline TOML comparisons with the current Harness central source passed for
  tiers, main, default + nine category routes, spawn, delegation and pins.
  Default gpt-6.1-sol/medium, narrow/unit gpt-6-luna/high, concurrency 8, depth 2
  and no full-history forks match. No routing source or lock was edited.
- Checkout and active runtime each contain 18 Mir skills with name/description
  frontmatter. `claude plugin list --json` and `codex plugin list --json` each
  report four enabled Mir packages at 0.13.1. Version commands observed uv
  0.11.3, Claude Code 2.1.301 and Codex CLI 0.159.2. Codex emitted a PATH-alias
  permission warning but both version/list commands exited 0.
- Synthetic JSON was passed via stdin to both runtimes' registered SessionStart
  and UserPromptSubmit commands. All four exited 0 with empty stderr.
  SessionStart: both 550 B, SHA256
  a3b6e93ee355a65eb3f8d159b87b145ac3744d65421febf861a862a85d2ffd88.
  UserPromptSubmit: both 121 B, SHA256
  1ce75f7912a770d632bf319c2f518805bff7d257bc148049324ad7cf82055eec.
  Startup intentionally carries safety/profile context with task retrieval on
  demand (.claude/hooks/session-start.sh:25). The global continuity Python hook
  also exited 0 and printed its expected reminder.
- Parent-supplied, observed 2026-10-16, not re-observed here: fresh Claude
  home-server SessionStart/UserPromptSubmit/Stop fired with 0 failures; native
  Codex trust found 0 untrusted/modified hooks; repository-context envelopes were
  Claude 644 B / Codex 642 B with equivalent repository context per parent.
  Parent also supplied no MCP, 18 Mir skills and held branch b181541. Local
  branch resolution confirms b181541; no checkout or edit touched that branch.
- SQLite online mode=ro backup included WAL state; immutable snapshot inspection
  returned integrity_check=ok and foreign_key_check=0 rows: 348160 B, 21 facts,
  12 entities, 1 source, 0 conflicts and 0 fact_links. Missing source provenance,
  subject/object entities and affected-file refs: zero. The source exists and
  its SHA256 matches content_items.text_hash. FTS5 has 21 rows.
  `uv run --no-sync mir memory query SRR --limit 3 --db <snapshot>` returned the
  SRR title; `memory reconcile-missing --dry-run` reported would_expire=0.
  Optional sqlite-vec is absent; FTS5 was used. Pure snapshot renders match the
  generated memory-map and lessons sections. Original DB/WAL content and mtime
  are unchanged. SQLite's read-only backup changed SHM mtime; its final size and
  hash match the original. No live diagnostic or repair write was issued.
- `uv run --no-sync mir relations query CR-006 --purpose implementation --json`:
  7 edges, not truncated; 5 unavailable historical endpoints explicitly skipped.
  Scope: declared_spec_relations_only; graph SHA256
  a26d2f530c0acd26cad958982ec89acaea7a21f7b2fc8232266c0730ee1829a5.
  This is not current implementation proof (/vocabularies/2).
  `mir loop --help` exited 0; no standing loop was started.
- `uv audit --frozen`: no known vulnerabilities or adverse statuses in 28 locked
  packages. `uv pip list --outdated --format json`: 14 installed packages have
  newer versions; no compatibility or upgrade verdict is implied. Installed
  license metadata was inspected for 26 dependencies (MIT/BSD/Apache/MPL/PSF);
  platform colorama and optional sqlite-vec are absent. A bounded credential
  signature scan of 885 tracked text files excluded secrets and the protected
  DB. Five matches are test-fixture lines: tests/test_capability_security.py:
  530,535,540,550 and tools/mir_executor/tests/test_v31_regressions.py:66. No
  credential values were recorded.
- Startup document sizes before=after: CLAUDE.md 40 lines / 3587 B; AGENTS.md
  42 lines / 3676 B. Declared 55/3600 and 60/3800 budgets are respected.

The inventory dependency is source evidence, not an assumed release gate:
tools/template_assets.py:127 computes
`"sha256": hashlib.sha256(path.read_bytes()).hexdigest()`.
The exact-inventory assertion in tests/test_template_asset_classification.py
compares the checked-in inventory against that function. Main owns regeneration
after the final evidence write under the current no-generator instruction.
This differs from D1: ADR-86:40–42 permits capability-lock reconciliation against
a committed implementation without requiring a release.

### Per-item matrix

All evidence below was read or executed in this run. Assessment coverage: 22/22;
successful closure: 19/22. One cell remains OWNER; two cells remain BLOCKED.

| # | verdict | evidence checked now | change |
|---|---|---|---|
| 1 | PASS | Profile/CLAUDE/architecture read; path verifier 9 files/77 refs; asset classification 885/885; read-only parity has no findings. | None; generated inventory is separately tracked in item 18. |
| 2 | PASS | config/project-hooks.json and both registrations read; all 11 scripts exist; four enabled Mir packages; no project MCP. | None. |
| 3 | IMPROVED | Current cursor/checklist/handoff still described pre-split results and unobserved native trust; current evidence is above. | Updated five continuity/evidence documents; historical spec stays superseded-reference. |
| 4 | IMPROVED | Superseded continuity text above preserves the three original documents and changed intent fields verbatim. | Moved replaced current-state text to this existing log with pointers; no rule, decision or lesson deleted. |
| 5 | PASS | CLAUDE 40 lines/3587 B, AGENTS 42/3676; one plan cursor, one checklist, one handoff and one evidence log. | No additional summary or snapshot file. |
| 6 | PASS | WAL-aware snapshot integrity=ok/FK=0; 21 facts/12 entities; source hash matches; missing provenance/entities/paths=0; dry-run would_expire=0. | No live DB repair; DB/WAL unchanged; SHM mtime-only observation disclosed above. |
| 7 | PASS | Root/nested bodies and in-memory hook render match; pure Codex validators return zero findings; safety bounds read. | No new restriction or hook; generator-backed verifier remains for Main. |
| 8 | OWNER | Checkout/runtime each expose 18 skills; skill frontmatter/12 agent mirrors checked; main maintenance skill has 21 items; held branch resolves b181541. | D1 is retained in tasks/plan.md; recommend preserving its hold until owner-authorized merge. |
| 9 | PASS | Root body equality plus one nested Starter transformation pass; both startup size budgets pass. | CLAUDE/AGENTS and generated Codex files unchanged. |
| 10 | PASS | Snapshot-generated memory-map and lesson sections equal tracked sections; repository rule/boundary/ADR source locations read. | No rule or lesson deletion, duplicate home or projection write. |
| 11 | PASS | ARCHITECTURE.md supported flows match Starter four files, Kit recipe, optional CLI, four plugin packages and inert reference corpus. | None. |
| 12 | PASS | Current central TOML matches lock tiers/main/default/nine routes/spawn/delegation/pins; management verifier passes with 0 non-compliant dispatches. | None; no routing or model pin edit. |
| 13 | IMPROVED | Intent evidence fragment resolves; plan/checklist/handoff now point to this matrix; old state preserved above. | Removed stale current-state claims; native parent evidence and local probes are distinguished. |
| 14 | PASS | Local ontology lookup returns Q1 and its three evidence refs; scratch FTS5 query SRR returns the source title. | None; no live MK dependency introduced. |
| 15 | PASS | Current synthetic startup 550 B in each runtime; prompt advisory 121 B each; source declares task-blind startup and 10 KB cap. | No always-loaded context growth. |
| 16 | BLOCKED | Full suite 2058 passed/4 failed; targeted cleanup rerun 1 passed/3 failed; remaining failures are inventory comparisons and slim preservation caused by old hashes. | Own stray bytecode removed. Generator refresh is forbidden to this writer; Main must rebind inventory and rerun the gate. |
| 17 | PASS | uv audit: 28 packages/no known vulnerabilities; 26 installed license records; 885-file bounded scan has five explicit fixture matches; full suite's remaining failures documented. | No dependency or code change; 14 newer installed-package versions are observations only. |
| 18 | BLOCKED | tools/template_assets.py:127 hashes file bytes; read-only comparison identifies only the five task documents changed here. | No generated inventory/lock write; Main must refresh config/adopter-payload.json after final evidence. |
| 19 | PASS | Version commands: uv 0.11.3/Claude 2.1.301/Codex 0.159.2; both plugin inventories 4 enabled at 0.13.1; synthetic hooks all exit 0. | Fresh-session Stop/trust observations remain explicitly parent-supplied. |
| 20 | PASS | Current plan has the canonical D1 disposition; ADR-86:40–42 read; no new owner-policy conflict found. | D1 recommendation is recorded once in the active cursor; delivery work is not a new owner decision. |
| 21 | PASS | Same root/nested rules, hook render, skills and absent MCP; identical current synthetic outputs; parent supplies fresh-session/trust observations. | Current projections now distinguish parent/native evidence from direct synthetic observations. |
| 22 | PASS | Map /concepts/Agent, /concepts/Task, /relations, /domain/invariants checked; agent/routing probes pass; loop help exits 0; CR-006 returns 7 edges with 5 historical skips; mapping 0/0. | Existing bounded Agent/Loop/Graph/Ontology surfaces fit Yoke's supplier role; no service, graph or loop added. Shared checklist delivery remains D1 in item 8. |

### Test results and remaining delivery

- Full command: `uv run --no-sync pytest -q -p no:cacheprovider --basetemp=<scratch>/pytest-full`:
  **2058 passed, 4 failed in 279.29s**. Failures:
  - tests/test_advanced_reference_templates.py::test_should_remove_reference_snapshot_when_adopter_payload_is_built
  - tests/test_common_harness_template.py::test_should_provide_only_the_bounded_common_harness_sources
  - tests/test_greenfield_slim_integration.py::test_should_leave_minimal_starter_and_project_owned_changes_when_candidate_is_slimmed
  - tests/test_template_asset_classification.py::test_should_match_exact_adopter_payload_when_release_inventory_is_generated
- The common-harness failure named an extra renderer .pyc made by this run's
  initial Python import. That exact file and its empty directory were removed.
  No source/test change was needed. The same four node IDs were rerun with
  `-q -p no:cacheprovider --basetemp=<scratch>/recheck`: **1 passed, 3 failed in
  7.53s**. Two failures compare the persisted inventory directly; the third
  preserves the changed plan because src/mir/core/adoption/slim.py:549–553
  retains files whose bytes differ from the persisted hash. Read-only inventory
  comparison is limited to this pass's five task documents.
- FAIL-FIRST: none. No code/test implementation changed; no existing consumed
  heading, JSON key order or document format changed. New evidence was appended
  in the explicitly requested existing log section. The .pyc failure was probe
  contamination and its removal was verified by the targeted rerun.
- Prior top-level intent status, preserved verbatim: `"status": "complete",`.
  It is now in_progress because the matrix's operational gate is not closed.
- Main owns inventory rebinding, generator-backed parity verification and the
  repository gate before delivery. Next action: matrix pass 2026-10-16: reviewed
  and committed by Mir Harness Main. This phrase names the requested delivery
  disposition; this writer has not committed anything.
- OWNER D1: the canonical current disposition remains in tasks/plan.md.
  Recommendation: retain the held branch until the owner authorizes its release
  merge; do not conflate that choice with a capability-lock technical limit.

### Final focused verification

- `uv run --no-sync pytest -q -p no:cacheprovider tests/test_repo_maintenance_skill.py tests/test_public_template_surface.py tests/test_capability_cli.py::test_repository_lock_is_portable_and_matches_managed_trees tests/test_mir_ontology.py tests/test_common_harness_template.py --basetemp=<scratch>/final-focused`:
  **31 passed, 0 failed in 3.89s** after all five continuity documents were aligned.
- Final Ruff: all checks passed. Final Python assertions confirmed exactly 22
  ordered matrix rows (16 PASS / 3 IMPROVED / 1 OWNER / 2 BLOCKED), valid intent
  JSON and resolving evidence anchor, unchanged live DB/WAL size/mtime/hash,
  absent probe bytecode and exactly five changed task documents. Read-only
  inventory comparison differs in exactly those same five paths, with no other
  source or generated drift attributed to this pass.
- Final source changes are documentation only. Main must refresh the inventory,
  execute the generator-backed parity verifier and rerun the repository gate.
  No commit, push, release, service restart, runtime install, live DB repair or
  generated-file refresh was performed. Scratch is removed after checks.
- Final `python3 scripts/verify_context_paths.py`: 9 files / 77 refs passed.
  Final ontology mapping: 0 errors / 0 warnings; strict impact exits 0 and names
  /concepts/Task plus /vocabularies/9, with no stale refs or selected checks.
  `git diff --check`: passed with no output.


## Portable default work method (2026-10-17)

Authority: current parent-supplied owner direction to make the default method portable across computers and both runtimes, including delegated Codex threads. The supplied runtime observation and method excerpt are evidence, not independent authority.

Delivery disposition: "reviewed and committed by Mir Harness Main" describes the required Main acceptance step; this delegated writer does not commit. Release: owner Discord 1560695634611409009 authorized this change alone as 0.13.2 (push, tag, host activation); item-22 stays held (D1).

### Superseded active cursor (verbatim)

```markdown
# Plan

## Active task: repository maintenance (2026-10-16)

Authority: the current owner maintenance brief, recorded in `tasks/intent.json`.
The parent-supplied Harness directive is evidence of scope, not independent authority.

Outcome: verify each of the 22 items against current main, improve evidenced gaps,
and record checks and remaining owner/Main work in the existing evidence log.

- [x] Inspect current contracts, continuity, memory snapshot, routing and runtime boundaries.
- [x] Assess all items; retain superseded continuity text verbatim in the evidence log.
- [x] Execute full pytest, Ruff, read-only parity, ontology and synthetic runtime checks.
- [x] Record all 22 assessments and align the status projection and resume pointer.

Assessment coverage: 22/22 cells have evidence checked in this run; 19/22 cells
are PASS or IMPROVED, one retains owner D1, and two await generated inventory
rebinding. Full pytest: 2058 passed / 4 failed; after removing this run's stray
bytecode, the four-test recheck returned 1 passed / 3 inventory-related failures.
Main acceptance: Mir Harness Main (2026-10-17) regenerated the adopter inventory (`python -m tools.template_assets --write-adopter-payload`) and re-ran the host gate: 2062 passed, ruff clean; items 16 and 18 PASS, 21/22 complete, D1 remains owner-only.

Limits: no commit, push, release, consumer write, live database write, secret read,
`uv sync`, service restart, generated `.codex/**` edit or generated-file refresh.
Scratch is confined to the owner-specified external task directory.

Evidence: `tasks/change_log.md#matrix-pass-2026-10-16`.
Prior cursor and projections: the superseded continuity text in that section.
Historical passes: `tasks/change_log.md#repository-maintenance-2026-10-16` and
`tasks/change_log.md#independent-review-corrections-2026-10-16`.

Main disposition (Mir Harness, 2026-10-16): the repo-maintenance item-22 skill change, its test and the adopter-payload rehash are held on local branch `maint/repo-maintenance-item-22` (b181541), not main, by Main/owner choice D1 pending an owner-approved release merge. ADR-86 permits reconciling the lock to a committed implementation without requiring a release.
Recommendation for D1: retain the hold until the owner authorizes the release merge.

Next action: matrix pass 2026-10-16: reviewed and committed by Mir Harness Main.
```

### Fail-first evidence

Before changing the hook or skills, ran the two affected node IDs in
`tests/test_plugin_skill_packages.py` with `uv run pytest -q -p no:cacheprovider`,
the requested external UV_CACHE_DIR, external TMPDIR and bytecode disabled.
Result: **2 failed in 0.10s** (exit 1).

```text
FAILED test_lifecycle_hook_plugin_uses_one_exact_shared_hook_file
E AssertionError: existing continuity-only stdout differs from the requested method message.
FAILED test_should_package_portable_default_work_method_in_order
E AssertionError: assert reference.is_file()
2 failed in 0.10s
```

The displayed errors summarize the real pytest output; no production change
preceded this run. Assertions cover exact stdout, the byte budget, the reference
in an isolated package copy, ordered table rows, portable content and skill pointers.

### Superseded intent (verbatim)

```json
{
  "goal": "Re-verify Mir Yoke against the owner-directed 22-item repository maintenance checklist and apply minimal evidenced improvements.",
  "goal_type": "maintenance",
  "scope": "This repository matrix pass only; no commit, release, consumer write, live database write, secret access, service restart, uv sync or generated-file refresh. Mir Harness Main owns delivery and generated inventory rebinding.",
  "priority": "normal",
  "updated": "2026-10-16",
  "history": [
    {
      "goal": "Fix the five Linux release-runner test failures without weakening their behavioral guarantees.",
      "updated": "2026-10-16",
      "status": "complete",
      "evidence": "tasks/change_log.md#linux-release-runner-fixtures-2026-10-16"
    },
    {
      "goal": "Prepare the Mir Yoke 0.13.1 release working tree with version metadata and migration notes only.",
      "updated": "2026-10-16",
      "status": "complete",
      "evidence": "tasks/change_log.md#0131-release-preparation-2026-10-16"
    },
    {
      "goal": "Close ontology impact and isolated distribution gaps and scope E06/E08 evidence.",
      "updated": "2026-10-16",
      "status": "complete",
      "evidence": "tasks/change_log.md#ontology-gap-development-2026-10-16"
    },
    {
      "goal": "Make local validation and fresh-checkout validate workflow commands pass while retaining the memory render guard.",
      "updated": "2026-10-16",
      "status": "complete",
      "evidence": "tasks/change_log.md#local-and-ci-validation-fixes-2026-10-16"
    },
    {
      "goal": "Prevent automatic consistency tests from rendering live agent memory.",
      "updated": "2026-10-16",
      "status": "complete",
      "evidence": "tasks/change_log.md#automatic-memory-render-guard-2026-10-16"
    },
    {
      "goal": "Prepare the Mir Yoke 0.13.0 release working tree with version metadata and migration notes only.",
      "updated": "2026-10-16",
      "status": "complete",
      "evidence": "tasks/change_log.md#0130-release-preparation-2026-10-16"
    },
    {
      "goal": "Correct E03 and E07 covered check references using existing executable behavior tests.",
      "updated": "2026-10-16",
      "status": "complete",
      "evidence": "tasks/change_log.md#superseded-cursor-covered-label-fix-before-0130-preparation-2026-10-16"
    },
    {
      "goal": "Retain repeatable Yoke-domain selection/evidence use and resolve declared relation target-freshness ownership.",
      "updated": "2026-10-16",
      "status": "complete",
      "evidence": "tasks/change_log.md#ontology-rejudgment-g08g13-2026-10-16"
    }
  ],
  "status": "complete",
  "evidence": "tasks/change_log.md#matrix-pass-2026-10-16",
  "authority": "Current owner maintenance brief; parent-supplied Mir Harness directive dated 2026-10-16 (ADR-91)."
}
```

### Implementation and evaluation

- Added the portable seven-step table, proportional application and inapplicability
  rule, role ownership and repository-declared cross-cutting practices to the existing
  lifecycle skill package. No host paths, private decision citations, assumed CLI,
  fleet or memory store appear in the reference.
- Kept the original MESSAGE sentence and appended one sentence with the seven-step
  order, fresh evidence completion rule and reference name. MESSAGE is **395 UTF-8
  bytes**, stdout including LF is **396 bytes**; the handler source is 597 bytes.
  Both runtimes still discover the same hooks/hooks.json and handler.
- Added one design pointer, with no duplicated table. Verify needs no additional
  pointer for this bounded change.
- Updated the capability validator's exact reviewed handler literal to match;
  its separate source-size ceiling is 1024 bytes while the stdout test requires
  fewer than 600 bytes. Exact source equality and all other admission checks remain.
  This source coupling was exposed by the first implementation check (2 failed,
  9 passed in 0.21s), before updating the validator.
- Packaging and security iteration: 90 passed, 29 failed in 6.53s. Every failure
  was a stale active-package acknowledgement or an expectation masked by it.
- Full first gate: `uv run pytest -q -p no:cacheprovider` returned exit 1,
  **1994 passed, 70 failed in 266.42s**. One is the supplied pre-existing
  capability-lock test; 68 concern the newly stale lifecycle acknowledgement;
  one public-surface failure detected forbidden path prefixes in the new test
  source. Changed only the new assertion spelling to construct the same prefixes
  at runtime, following the existing public-surface test. The scanner is unchanged.
- After that correction, `uv run pytest -q -p no:cacheprovider
  tests/test_plugin_skill_packages.py tests/test_public_template_surface.py`:
  **14 passed in 0.23s**. The full gate is rerun below against this correction.
- `uv run ruff check`: exit 0, All checks passed.
- `uv run python scripts/verify_codex_sync.py`: exit 0, Codex derivatives match
  Claude sources; generation for comparison used external temporary output only.
  No repository .codex files or instruction derivatives were written.
- `python3 scripts/verify_context_paths.py`: 9 files / 77 path references passed.
- `python3 scripts/mir_ontology.py mapping`: 0 errors / 0 warnings, 1.1.0;
  strict Git impact: exit 0, no stale refs or selected checks. The map's
  /concepts/Task and /vocabularies/9 cover task records; /concepts/Evidence,
  /concepts/Assessment and /vocabularies/5 cover operation-scoped capability
  diagnostics. A passing format check is not runtime acceptance or release proof.
  The unchanged map SHA-256 is
  c20fbf3bdb910d3872b1f66730b56e0f34e8fa00c707e91eedd458c25a374340.

### Packaging boundary and remaining Main work

The documented command `uv run python -m tools.template_assets --write-adopter-payload`
regenerates the adopter inventory, includes the new reference and refreshes affected
file hashes. No skill names, package names, versions or manifests changed; catalog
and generated derivative parity need no new entries. Re-run the same inventory
command after final records and after any subsequent Main changes.

A separate admission record in config/capability-sources.json now needs review:
active_package_digest_acknowledgements.mir-lifecycle-hooks still records
0a5e1ba21fd2bd284af2ac483f0764e594b7deadcfe76052d799c277a86d20e1,
but the actual tree is
589b09e6d612e89ed2f4723efc054ee11ce318b8cc33343ad3b9578173a96ee3.
The admission rule requires a reviewed acknowledgement (the lifecycle-hook
architecture decision, section 2.3). No dedicated acknowledgement generator was
found in the CLI, scripts or tools. The earlier release-preparation record documents
using mir.core.capabilities.manager._tree_digest, but the current request restricts
hash changes to documented generator commands. A question about using that existing
routine is pending; the acknowledgement has not been hand-edited or bypassed.
This is a newly affected record, separate from the pre-existing capability-lock issue.

Main must review the diff, resolve the acknowledgement update procedure, update that
record after review and regenerate the inventory, then rerun the full default suite.
The unchanged .mir/capability-lock.json still needs binding to the committed source
at the authorized D1 release step, followed by another inventory refresh and gate.
Current mir-core tree digest is
ddf58c3d36d3093ce2421f0c2a340550f2b1332d1ce38fdc7b6b41a4cd01accf.
Fresh-session discovery on other computers is parent-supplied transport evidence;
local tests establish package/output contracts only. Runtime delivery, trust and
new native-session observations remain with authorized Main operations.

### Request matrix

| Deliverable | State | Evidence |
| --- | --- | --- |
| 1 Portable method and skill link | PASS | Seven ordered rows, isolated-copy assertions and manual content review. |
| 2 Bounded identical message | PASS | Exact stdout test; 395 bytes, 396 with LF; shared hook registration unchanged. |
| 3 Design pointer | PASS | One skill-qualified reference; asserted by packaging test. |
| 4 Fail-first tests | PASS | Initial 2 failures precede implementation; corrected package/public checks 14 passed. |
| 5 Generated records and release rebindings | PARTIAL | Adopter inventory regenerated; admission acknowledgement pending procedure clarification; capability lock remains D1. |
| 6 Plan/change-log records | PASS | Single cursor, preserved prior cursor/intent, this evidence log and Main disposition. |

Coverage: 6/6 cells examined; **5/6 complete**, open cell 5 is the admission
acknowledgement. Delivery disposition: **reviewed and committed by Mir Harness Main**
is the required next Main action, not a claim that this writer committed.
No commit, push, tag, release, consumer write, secret read, live database write or
repository .codex write occurred. Owner D1 remains unchanged: retain the branch
hold until the owner authorizes the release merge (recommended).


## Superseded continuity before matrix pass 2026-10-17

Preserved verbatim; current cursor: `tasks/plan.md`.

### tasks/plan.md

```markdown
# Plan

## Active task: portable default work method (2026-10-17)

Authority: the current parent-supplied owner direction, recorded in `tasks/intent.json`.
Intent: make the default work method available on any adopting computer through
one shared lifecycle message and a portable skill reference, including delegated
Codex sessions. The parent observation establishes the selected transport only;
local checks cannot prove new native-session discovery.

Request matrix (deliverables 1-6):
- [x] 1. Portable seven-step reference and runtime-continuity skill link.
- [x] 2. Shared bounded MESSAGE, preserving its existing sentence; record bytes.
- [x] 3. One design-skill pointer to the method order.
- [x] 4. Fail-first packaging, ordered-step, portability and byte-budget tests.
- [x] 5. Documented inventory regeneration; identify release-time rebindings.
- [x] 6. Plan and change-log evidence with the Main delivery disposition.

Writer limits (historical): stay on `maint/repo-maintenance-item-22`; no commit, push, tag, release,
consumer writes, secrets, live memory writes or generated `.codex/**` writes.
Use the specified external uv cache and external task scratch.

Evidence: `tasks/change_log.md#portable-default-work-method-2026-10-17`.
Delivery disposition: reviewed and committed by Mir Harness Main.
This is the required Main follow-up, not a claim that this writer committed.
Main disposition (2026-10-17): owner Discord 1560695634611409009 authorized pushing this change alone, releasing it as 0.13.2 and activating it on the managing host. Main moved it from `maint/repo-maintenance-item-22` onto `main`, refreshed the lifecycle-hooks digest acknowledgement with the dedicated validator from a cache-free copy (589b09e6…), and regenerated the adopter payload on `main`. The item-22, verify and runner changes stay held on that branch (D1).

D1 disposition (2026-10-17): owner Discord 1560822145624580200 accepted the recommendation to release the held item-22 skill, the verify request-matrix rule and the runner distribution-check extraction together. Main cherry-picked 26d2f42 and 1a24dc0 from `maint/repo-maintenance-item-22` onto `main` (history rewrite of the shared branch is not used), prepared 0.13.3, rebound the lock from the git-archive tree, tagged and activated it; evidence: `tasks/change_log.md#0133-release-2026-10-17`. Consumers refresh their ontology-runner byte copy after activation.

### Bounded design

This cursor is the design authority for this change. Keep the hook a constant-only,
read-only emitter shared by both runtimes; put the full method in its existing
skill package. Link from design by skill name, without a cross-package file path.
The known paths and fixed output make direct execution sufficient; no delegation,
new runtime machinery, standalone decision record or memory/graph write is needed.
The historical spec snapshot is not the authority for this package change.

Evaluation: exact shared output and byte budget; isolated packaged reference,
ordered steps and portability constraints; full default suite, Ruff and whitespace.
The lock is rebound in the 0.13.2 bind commit. Regenerate only
the adopter inventory through its documented generator after final records.

### Current acceptance

5/6 deliverables complete; cell 5 is open because the lifecycle package digest
acknowledgement is stale and its update procedure awaits clarification under the
request's generator-only constraint. The adopter inventory is generated; the
capability lock remains for the authorized D1 binding. MESSAGE: 395 bytes (396
including LF). Full first gate: 1994 passed / 70 failed; the public-prefix test
source issue was corrected and its package/public recheck passed 14/14.
See the evidence log for the final gate and Main's exact remaining actions.
```

### tasks/intent.json

```json
{
  "goal": "Make the default work method portable across adopting computers and both runtimes, including delegated Codex sessions.",
  "goal_type": "maintenance",
  "scope": "This repository only: portable lifecycle skill reference, bounded shared MESSAGE, design pointer, fail-first tests, documented inventory regeneration and records. No commit, push, tag, release, consumer write, secret read, live memory write or generated .codex/** write.",
  "priority": "normal",
  "updated": "2026-10-17",
  "history": [
    {
      "goal": "Re-verify Mir Yoke against the owner-directed 22-item repository maintenance checklist and apply minimal evidenced improvements.",
      "updated": "2026-10-16",
      "status": "complete",
      "evidence": "tasks/change_log.md#matrix-pass-2026-10-16"
    },
    {
      "goal": "Fix the five Linux release-runner test failures without weakening their behavioral guarantees.",
      "updated": "2026-10-16",
      "status": "complete",
      "evidence": "tasks/change_log.md#linux-release-runner-fixtures-2026-10-16"
    },
    {
      "goal": "Prepare the Mir Yoke 0.13.1 release working tree with version metadata and migration notes only.",
      "updated": "2026-10-16",
      "status": "complete",
      "evidence": "tasks/change_log.md#0131-release-preparation-2026-10-16"
    },
    {
      "goal": "Close ontology impact and isolated distribution gaps and scope E06/E08 evidence.",
      "updated": "2026-10-16",
      "status": "complete",
      "evidence": "tasks/change_log.md#ontology-gap-development-2026-10-16"
    },
    {
      "goal": "Make local validation and fresh-checkout validate workflow commands pass while retaining the memory render guard.",
      "updated": "2026-10-16",
      "status": "complete",
      "evidence": "tasks/change_log.md#local-and-ci-validation-fixes-2026-10-16"
    },
    {
      "goal": "Prevent automatic consistency tests from rendering live agent memory.",
      "updated": "2026-10-16",
      "status": "complete",
      "evidence": "tasks/change_log.md#automatic-memory-render-guard-2026-10-16"
    },
    {
      "goal": "Prepare the Mir Yoke 0.13.0 release working tree with version metadata and migration notes only.",
      "updated": "2026-10-16",
      "status": "complete",
      "evidence": "tasks/change_log.md#0130-release-preparation-2026-10-16"
    },
    {
      "goal": "Correct E03 and E07 covered check references using existing executable behavior tests.",
      "updated": "2026-10-16",
      "status": "complete",
      "evidence": "tasks/change_log.md#superseded-cursor-covered-label-fix-before-0130-preparation-2026-10-16"
    },
    {
      "goal": "Retain repeatable Yoke-domain selection/evidence use and resolve declared relation target-freshness ownership.",
      "updated": "2026-10-16",
      "status": "complete",
      "evidence": "tasks/change_log.md#ontology-rejudgment-g08g13-2026-10-16"
    }
  ],
  "status": "in_progress",
  "evidence": "tasks/change_log.md#portable-default-work-method-2026-10-17",
  "authority": "Current parent-supplied owner direction: same effect on every adopting computer, both runtimes and delegated Codex threads; Mir Harness Main owns review, re-run and commit; owner Discord 1560695634611409009 authorized push, the 0.13.2 release and host activation for this change alone."
}
```

### tasks/checklist.md

```markdown
# Checklist

Status projection for `tasks/plan.md`: matrix evidence checked for 22/22 items;
19/22 PASS or IMPROVED at writer time, owner D1 remains. Mir Harness Main (2026-10-17) regenerated the adopter inventory (`python -m tools.template_assets --write-adopter-payload`) and re-ran the host gate: 2062 passed, ruff clean; items 16 and 18 PASS, 21/22 complete, D1 remains owner-only.
Full pytest: 2058 passed / 4 failed. Removing this run's stray renderer bytecode
resolved one failure; the four-test recheck returned 1 passed / 3 inventory failures.
Ruff, 77 path references, ontology mapping/strict impact and read-only parity passed.
Native fresh-session/trust observations are parent-supplied; local synthetic
SessionStart/UserPromptSubmit outputs match across both runtimes.
The canonical D1 disposition is in `tasks/plan.md`; no held branch was edited.
Evidence and verbatim prior projection: `tasks/change_log.md#matrix-pass-2026-10-16`.
Next action: matrix pass 2026-10-16: reviewed and committed by Mir Harness Main.
```

### tasks/handoffs/session-handoff-LATEST.md

Main moved this resume-pointer text on acceptance (verbatim):

```markdown
Read `tasks/checklist.md` for status and
`tasks/change_log.md#matrix-pass-2026-10-16` for this pass.
Superseded handoff text is preserved verbatim at
`tasks/change_log.md#matrix-pass-2026-10-16`.
No commit, release, live database write or generated `.codex/**` edit is authorized.
Assessment coverage is 22/22; successful closure is 21/22 after Main acceptance
(inventory rebound, host gate 2062 passed); D1 remains in the canonical cursor. Parent-supplied
native-session evidence and current synthetic probes are distinguished in the log.
Next action: matrix pass 2026-10-16: reviewed and committed by Mir Harness Main.
```

## Matrix pass 2026-10-17

Authority: owner Discord 1560953913631318118 (2026-10-17), relayed by Mir Harness
Main with its fleet directive. Intent/design authority: tasks/plan.md.
Yesterday's verdicts were treated as a baseline, never as current proof.
Start revision: 61f74e6. The sole pre-existing dirty path,
tasks/handoffs/session-handoff-LATEST.md, retains its initial bytes.

### Evidence checked now

All uv commands use UV_CACHE_DIR="$OWNER_UV_CACHE".
Scratch/TMPDIR, Ruff cache and pytest basetemp use the external directory
$MAINTENANCE_SCRATCH (owner-specified external SSD).
Python probes use PYTHONDONTWRITEBYTECODE=1; pytest disables cacheprovider.
Official parity uses disposable generated output there; checked-in Codex is unchanged.

- Contract/profile/architecture/spec read, with ADR-86/90 boundaries: historical spec
  remains superseded-reference; no consumer authority, discovery or write.
- python3 scripts/verify_context_paths.py: 9 files / 77 refs PASS.
  Read-only asset classification: 887/887, no unclassified/duplicate/prohibited entries.
- uv run python scripts/verify_codex_sync.py: PASS, "OK: Codex derivatives match
  Claude sources". Additional pure validators found zero issues; all 17 manifest
  mappings resolve, root bodies match and the nested Starter pair passes.
  Twelve agent names/descriptions match; Codex mirrors omit model pins.
  In-memory render_hooks equals both configurations; all 11 hook scripts exist.
  StopFailure is intentionally Claude-only; SessionEnd timeouts are 60s/3s.
  No project MCP file or Codex MCP table is declared.
- uv run python scripts/verify_repo_agent_management.py: all schema, wiring,
  catalog, pack, specialist and repositories_dir checks PASS; 0 non-compliant dispatches.
  Effective Main/default/nine category routes match current Harness central TOML.
  Tiers, native_spawn, pins and delegation compare exactly; cap 8/depth 2.
  SHA256 of central bytes then repository bytes matches routing source_sha256:
  74d4018756fcf6d8b839643fc3243582baa51a62d4fd03ad45e8364fd86a8362.
  An initial probe compared the wrong JSON levels; corrected schema-aware checks pass.
- Current versions: Claude 2.1.302, Codex 0.163.0. Each plugin list reports four
  enabled Mir packages at 0.13.3. All 46 package source files match each runtime
  installation byte-for-byte; all 18 skills have name/description frontmatter.
  Codex reported a PATH-alias permission warning but its commands exited 0.
- Synthetic stdin executed the registered SessionStart commands with CODEX_THREAD_ID
  removed and MIR_RUNTIME set per runtime: exit 0, empty stderr, identical 550 B
  beginning "="; SHA256 a3b6e93ee355a65eb3f8d159b87b145ac3744d65421febf861a862a85d2ffd88.
  Nontrivial UserPromptSubmit: identical 119 B, exit 0, empty stderr; SHA256
  5e28830d3e9dd05df38a66f279adb3afc338c9fcb0ae78572b5cd706f181f4d5.
  The initial empty-prompt probe returned 0 B under its documented short-prompt skip.
- Shared continuity hook in both environments: identical 396 B including LF,
  beginning "M"; SHA256 e06c666f1501e00ec07e0f31f8d7cdd21d16f48ff284de7ba7f19d91cbbc1853.
  All outputs stay below 10 KB and avoid Codex's "[" first-byte problem.
  Repository startup is intentionally task-blind (ADR-53); task retrieval is
  on demand. Its SessionStart script has no native-memory-index branch.
- Parent-supplied fresh-session evidence, not re-observed here: Mir Harness
  tasks/reports/method-delivery-2026-10-17/ reports method delivery to fresh Claude
  and delegated Codex in all 16 repositories; native-memory index reaches Codex in
  every repository with that branch and adds nothing to Claude. Main must check
  actual loaded base registration/trust and fresh-session acceptance.
  The inspected host ~/.codex/hooks.json exposes no direct SessionStart groups;
  this alone does not establish which base-hook wiring the host actually loads.
- Stable DB/WAL/SHM copies on scratch passed live before/after size/mtime/hash
  equality. SQLite online backup of that scratch copy yielded an isolated
  348160 B snapshot. Immutable snapshot: integrity_check=ok, FK=0; 21 facts,
  12 entities, 1 content item, 0 conflicts/fact_links/missing source or entity refs.
  The source docs/knowledge/srr-code-relations.md matches stored text_hash
  f47eaa303dddfe54aaa6b9d6bd6f15812d4f3b46b97442bdf3aa352cad02b827.
  Snapshot render functions match tracked memory-map/lessons sections.
  uv run mir memory query SRR --limit 3 --db <snapshot>: "SRR code relations".
  uv run mir memory reconcile-missing --dry-run --project-root . --db <snapshot>:
  would_expire=0. Optional sqlite-vec is absent; supported FTS5 works.
  No live DB connection, apply, checkpoint, repair or projection write occurred.
- uv run mir relations query CR-006 --purpose implementation --json: 7 edges,
  not truncated; 5 unavailable historical endpoints explicitly skipped.
  Scope declared_spec_relations_only; graph SHA256
  a26d2f530c0acd26cad958982ec89acaea7a21f7b2fc8232266c0730ee1829a5.
  uv run mir loop --help: exit 0; optional explicit CLI; no standing process started.
- python3 scripts/mir_ontology.py mapping: 0 errors/0 warnings, contract/map 1.1.0.
  impact --git-diff --strict: exit 0, Task/intent vocabulary affected, no selected
  checks, stale refs or undeclared check links. Q1 lookup returns three relevant refs.
  Semantic anchors: map /concepts/Agent, /concepts/Task, /relations,
  /vocabularies/2, /vocabularies/4, /vocabularies/9, /domain/invariants, /questions/0.
  Historical readiness, stored validity, task status and current proof stay separate.
- uv audit --frozen: 28 packages, no known vulnerabilities/adverse statuses.
  uv pip list --outdated --format json: 14 newer versions observed; no upgrade.
  License metadata inspected for 27 installed distributions including this project.
  Bounded signature scan: 887 tracked text files excluding protected secrets/DBs;
  eight matches are seven explicit fixture lines and one archived filename false positive.
  No credential values recorded; this is not a comprehensive security certification.
- CLAUDE.md before=after 40 lines/3587 B; AGENTS.md 42 lines/3676 B.
  Single cursor/projection/resume/log retained. The three replaced continuity
  documents compare verbatim with the archived originals above.
- D1: git cherry v0.13.3 maint/repo-maintenance-item-22 reports "-" for both
  26d2f42 and 1a24dc0; cherry-pick-aware right-only log is empty.
  The branch is not a literal ancestor, but all unique patches are included.
  Item-22/verify/runner sources have no diff against v0.13.3.
  Canonical runner SHA256 f10d7116298f98c9df53ac0b4165f54199b2d1a893653dced36614c0bcf4b6be.
  The root runner is intentionally a checkout adapter, not a consumer byte copy.

### Per-item matrix

Assessment 22/22; closure 19/22. Items 13, 19 and 21 require Main.

| # | verdict | evidence checked now | change |
|---|---|---|---|
| 1 | PASS | Profile/architecture read; 77 refs; 887 assets; official parity PASS. | No source contract drift. |
| 2 | PASS | Eleven hook scripts; matching render; four enabled packages; no project MCP. | No dead-entry repair needed. |
| 3 | IMPROVED | Cursor retained stale 5/6 acceptance; checklist still retained delivered D1. | Intent/cursor/checklist now describe this pass and observed containment. |
| 4 | IMPROVED | Three replaced continuity documents match archived originals verbatim. | Existing log preserves superseded text with pointers. |
| 5 | PASS | CLAUDE 40/3587 B; AGENTS 42/3676 B; single cursor/projection/resume/log. | No startup growth or competing report. |
| 6 | PASS | WAL-inclusive scratch snapshot ok/FK 0; 21 facts/12 entities; valid source; expiry 0. | No repair; live DB/WAL/SHM unchanged. |
| 7 | PASS | Official parity and exact hook render PASS; safety bounds retained. | No new constraint or owner-removed hook. |
| 8 | PASS | 18 skills; 12 mirrors; 46 files equal per runtime; item 22 present; D1 included. | Stale hold removed only from current status; history preserved. |
| 9 | PASS | Official root/nested/agent derivatives match; instruction sizes unchanged. | No instruction/checked-in Codex write. |
| 10 | PASS | Snapshot projection matches memory-map/lessons; canonical ADR/rule homes read. | No rule/lesson deletion or duplicate home. |
| 11 | PASS | Architecture matches four-file Starter, Kit, optional CLI, four packages and inert references. | No architectural machinery added. |
| 12 | PASS | Combined source SHA, effective routes and four policy sections match; management PASS. | No routing or pin change. |
| 13 | NEEDS MAIN | Single roles retained; excluded dirty handoff still states yesterday/D1. | Main must curate that existing handoff; writer preserved its initial hash. |
| 14 | PASS | Q1 resolves three refs; snapshot FTS5 SRR query returns relevant title. | No live MK dependency added. |
| 15 | PASS | Method 396 B/startup 550 B/prompt 119 B match across runtimes; docs unchanged. | No context growth. |
| 16 | PASS | Clean full suite: 2064/2064 PASS; related focused contracts 41/41 PASS; earlier failures and corrections recorded below. | Inventory regenerated and public-log paths generalized; no implementation behavior change. |
| 17 | PASS | Audit 28 packages clean; 27 license records; scan hits only fixtures/archive filename. | No dependency upgrade or guard relaxation. |
| 18 | IMPROVED | Initial inventory differed in lock, dirty handoff and four own records; lock test PASS. | Official adopter generator refreshes hashes; capability/routing locks unchanged. |
| 19 | NEEDS MAIN | Current CLI/plugins, installed bytes and synthetic hooks PASS; parent fresh evidence scoped above. | Main must confirm loaded base hooks/trust and fresh-session acceptance. |
| 20 | PASS | D1 patch containment checked against v0.13.3; ADR-86/90 boundaries unchanged. | No new owner choice; operational follow-up is not a policy decision. |
| 21 | NEEDS MAIN | Equal rules/workflows/hooks/synthetic outputs; no project MCP. | Current host trust and fresh sessions require Main; parent evidence remains separate. |
| 22 | PASS | Agent: 18 skills/12 mirrors/routes; Loop: method tests/help; Graph: healthy snapshot/7 edges; Ontology: mapping/impact/Q1. | Existing supplier surfaces suffice; continuity/inventory repairs are the smallest useful improvement. |

### Integrity and Main follow-up

No capability source changed. No capability-lock/receipt/signature rebind is needed.
The existing commit-bound lock regression passes. Unchanged SHA256:
- Map: c20fbf3bdb910d3872b1f66730b56e0f34e8fa00c707e91eedd458c25a374340.
- Capability lock: a6bb9709f319177648891e18d28e2010538b9c2778d8d940e43aa56ca9cba378.
- Routing lock: 2211b125f2ade567c5b08e712e8b6052adc901739ce6b2a41b804b6e051fce65.

Main must curate the existing dirty handoff, then refresh its inventory hash with
UV_CACHE_DIR="$OWNER_UV_CACHE" uv run python -m tools.template_assets --write-adopter-payload.
Main owns current Codex hook trust/base registration/fresh-session probes, review
and any separately authorized commit. OWNER: none; D1 is delivered by patch equivalence.
No commit/push/tag/release/restart/deploy, secret/consumer/live-DB write was performed.

### Fail-first and gate commands

FAIL-FIRST: no implementation behavior changed; regression-test authoring is
not applicable. The existing inventory/slim assertions failed before their
documented regeneration; no assertion or guard was weakened.

- Full baseline command: uv run pytest -q -p no:cacheprovider --basetemp=<scratch>/pytest-full:
  2061 passed / 3 failed in 319.05s. The three failures were:
  tests/test_advanced_reference_templates.py::test_should_remove_reference_snapshot_when_adopter_payload_is_built;
  tests/test_greenfield_slim_integration.py::test_should_leave_minimal_starter_and_project_owned_changes_when_candidate_is_slimmed;
  tests/test_template_asset_classification.py::test_should_match_exact_adopter_payload_when_release_inventory_is_generated.
  Direct inventory comparison named six stale entries: capability lock (already
  committed), excluded dirty handoff, and this pass's four task documents.
  No sandbox-induced failing test was observed.
- Focused command: uv run pytest -q -p no:cacheprovider
  tests/test_repo_maintenance_skill.py tests/test_verify_skill.py
  tests/test_compact_lifecycle_hooks.py tests/test_common_harness_template.py
  tests/test_mir_ontology.py
  tests/test_capability_cli.py::test_repository_lock_is_portable_and_matches_managed_trees
  --basetemp=<scratch>/pytest-focused: 41 passed in 7.46s.
- uv run ruff check --cache-dir <scratch>/ruff: all checks passed.
- Official adopter generator and final full gate follow after these record writes.


### Public-log fail-first correction

The unpublished evidence draft accidentally included host-absolute paths in
three new lines. The existing public-surface test reproduced this before correction:
uv run pytest -q -p no:cacheprovider
tests/test_public_template_surface.py::test_should_expose_no_private_absolute_path_when_public_surfaces_are_scanned
--basetemp=<scratch>/public-red: 1 failed in 0.07s, naming tasks/change_log.md.
The log now uses OWNER_UV_CACHE and MAINTENANCE_SCRATCH placeholders; the actual
commands still used the owner's specified external paths. This is a correction
to this pass's draft, not removal of a historical rule, decision or lesson.

- Public-log correction recheck: same public-surface node plus
  tests/test_template_asset_classification.py::test_should_match_exact_adopter_payload_when_release_inventory_is_generated,
  --basetemp=<scratch>/public-green: 2 passed in 0.19s after official regeneration.
- Second full command (same options, --basetemp=<scratch>/pytest-final):
  2063 passed / 1 failed in 275.30s. Its sole failure was the public-surface node
  observed before the correction above; the original three inventory failures passed.
  A clean full run is being executed after the corrected record and regenerated inventory.


### Final full gate and disposition

After the public-log correction and official inventory regeneration, the same full
command with --basetemp=<scratch>/pytest-clean passed: 2064 passed / 0 failed
in 236.08s. No test was excluded; default tests/ and tools/ discovery remained active.
The intentional live-memory render exclusion inside the existing consistency test
was retained; memory projections were verified independently on the WAL snapshot.

Ruff, 77 context references, ontology mapping (0/0) and strict impact also passed
after the correction. No sandbox-induced test failure remains. The final remaining
record edits only project these observed results; inventory is regenerated afterward.
Assessment is 22/22, closure 19/22 (16 PASS, 3 IMPROVED, 3 NEEDS MAIN).
The open cells are 13 (excluded dirty handoff), 19 and 21 (native runtime/trust).

- After outcome-only cursor/checklist/log writes and inventory regeneration, the
  four affected nodes (public path, advanced reference inventory, greenfield slim,
  exact adopter inventory), with --basetemp=<scratch>/final-records, passed:
  4 passed in 4.58s. No implementation/source behavior changed after the clean run.
- Final assertions: exactly 22 ordered rows (16 PASS/3 IMPROVED/3 NEEDS MAIN);
  all three superseded continuity documents remain verbatim; initial handoff
  SHA256 preserved; live DB/WAL/SHM content, size and mtime unchanged;
  map and capability/routing digests unchanged. Exactly five own files changed:
  tasks/plan.md, tasks/intent.json, tasks/checklist.md, tasks/change_log.md,
  config/adopter-payload.json. The sixth dirty path is the excluded existing handoff.
  git diff --check passes. Final inventory is regenerated after this evidence write.

## Superseded cursor before ontology reachability (2026-10-17)

### Previous active cursor (verbatim)

```markdown
# Plan

## Active task: repository maintenance re-verification (2026-10-17)

Authority: owner Discord 1560953913631318118 (2026-10-17), relayed by Mir Harness Main;
parent-supplied directive `tasks/directives/repo-maintenance-fleet-2026-10-17.md`
in Mir Harness. This cursor is the intent and bounded design authority.

Re-verify all 22 `mir-core:repo-maintenance` items against evidence observed now,
then make the smallest useful improvement. Prior verdicts are a baseline only.
Preserve accepted ADRs, owner decisions and unrelated work. No commit, delivery,
restart, secret read, consumer write, live DB write or generated `.codex/**` write.
Existing dirty `tasks/handoffs/session-handoff-LATEST.md` is excluded from edits.

### Bounded design and evaluation

Inspect declared surfaces, take a WAL-inclusive scratch snapshot for memory checks,
use synthetic hooks plus explicitly parent-supplied fresh-session evidence, and
record 22 dated matrix rows in `tasks/change_log.md#matrix-pass-2026-10-17`.
Use existing checks first; any behavior fix requires observed fail-first coverage.
Documentation-only continuity corrections need direct consistency checks.
Run the full pytest/Ruff gate, read-only parity checks and ontology mapping/impact.
Main owns forbidden generated writes, host-only probes and final acceptance/commit.

### Current acceptance

22/22 evaluated; 19/22 closed. Full pytest: 2064 passed, no failures.
Items 13, 19 and 21 need Main: curate the preserved dirty handoff and confirm
actual runtime/base-hook trust in fresh sessions. Current status projection:
`tasks/checklist.md`; sole evidence log: `tasks/change_log.md`; existing resume
pointer: `tasks/handoffs/session-handoff-LATEST.md` (preserved for Main).
D1 is contained in v0.13.3 by patch equivalence: both branch-only commits are
reported by git cherry with '-'; the branch itself is not an ancestor. No owner
choice remains. Current gate results and all 22 rows are in the evidence log.
Prior cursor, intent and checklist are preserved verbatim in
`tasks/change_log.md#superseded-continuity-before-matrix-pass-2026-10-17`.
```

### Previous intent (verbatim)

```json
{
  "goal": "Re-verify all 22 repository-maintenance items against current evidence and apply minimal evidenced improvements.",
  "goal_type": "maintenance",
  "scope": "Mir Yoke only; no commit, push, tag, release, restart, secret access, consumer write, live memory write or generated .codex/** write. Preserve the pre-existing dirty handoff.",
  "priority": "normal",
  "updated": "2026-10-17",
  "history": [
    {
      "goal": "Make the default work method portable across adopting computers and both runtimes, including delegated Codex sessions.",
      "updated": "2026-10-17",
      "evidence": "tasks/change_log.md#portable-default-work-method-2026-10-17",
      "status": "superseded",
      "archive": "tasks/change_log.md#superseded-continuity-before-matrix-pass-2026-10-17"
    },
    {
      "goal": "Re-verify Mir Yoke against the owner-directed 22-item repository maintenance checklist and apply minimal evidenced improvements.",
      "updated": "2026-10-16",
      "status": "complete",
      "evidence": "tasks/change_log.md#matrix-pass-2026-10-16"
    },
    {
      "goal": "Fix the five Linux release-runner test failures without weakening their behavioral guarantees.",
      "updated": "2026-10-16",
      "status": "complete",
      "evidence": "tasks/change_log.md#linux-release-runner-fixtures-2026-10-16"
    },
    {
      "goal": "Prepare the Mir Yoke 0.13.1 release working tree with version metadata and migration notes only.",
      "updated": "2026-10-16",
      "status": "complete",
      "evidence": "tasks/change_log.md#0131-release-preparation-2026-10-16"
    },
    {
      "goal": "Close ontology impact and isolated distribution gaps and scope E06/E08 evidence.",
      "updated": "2026-10-16",
      "status": "complete",
      "evidence": "tasks/change_log.md#ontology-gap-development-2026-10-16"
    },
    {
      "goal": "Make local validation and fresh-checkout validate workflow commands pass while retaining the memory render guard.",
      "updated": "2026-10-16",
      "status": "complete",
      "evidence": "tasks/change_log.md#local-and-ci-validation-fixes-2026-10-16"
    },
    {
      "goal": "Prevent automatic consistency tests from rendering live agent memory.",
      "updated": "2026-10-16",
      "status": "complete",
      "evidence": "tasks/change_log.md#automatic-memory-render-guard-2026-10-16"
    },
    {
      "goal": "Prepare the Mir Yoke 0.13.0 release working tree with version metadata and migration notes only.",
      "updated": "2026-10-16",
      "status": "complete",
      "evidence": "tasks/change_log.md#0130-release-preparation-2026-10-16"
    },
    {
      "goal": "Correct E03 and E07 covered check references using existing executable behavior tests.",
      "updated": "2026-10-16",
      "status": "complete",
      "evidence": "tasks/change_log.md#superseded-cursor-covered-label-fix-before-0130-preparation-2026-10-16"
    },
    {
      "goal": "Retain repeatable Yoke-domain selection/evidence use and resolve declared relation target-freshness ownership.",
      "updated": "2026-10-16",
      "status": "complete",
      "evidence": "tasks/change_log.md#ontology-rejudgment-g08g13-2026-10-16"
    }
  ],
  "status": "in_progress",
  "evidence": "tasks/change_log.md#matrix-pass-2026-10-17",
  "authority": "Owner Discord 1560953913631318118 (2026-10-17), parent-supplied Mir Harness fleet maintenance directive."
}
```

### Previous status projection (verbatim)

```markdown
# Checklist

Status projection for tasks/plan.md: 22/22 evaluated, 19/22 closed.
Full pytest: 2064 passed, 0 failed; Ruff, official Codex parity, context paths
and ontology mapping/strict impact passed. The adopter inventory is regenerated.
Items 13, 19 and 21 require Main: curate the excluded dirty handoff and confirm
native sessions/current base-hook trust. Parent fresh evidence is scoped in the log.
D1 is delivered in v0.13.3 by patch equivalence; no owner choice remains.
Evidence: tasks/change_log.md#matrix-pass-2026-10-17.
Prior projection: tasks/change_log.md#superseded-continuity-before-matrix-pass-2026-10-17.
```

## Superseded cursor before ontology handoff packet (2026-10-18)

### Previous plan (verbatim)

```markdown
# Plan

## Active task: 0.13.4 release preparation (2026-10-17)

Authority: owner Discord 1561020393568079954 (2026-10-17), via Mir Harness Main, and directive `ontology-engineering-settlement-2026-10-17` (parent-supplied). This cursor is the intent and bounded design authority for commit A content only. The release brief supersedes the previous no-version-change restriction. Previous cursor: `tasks/change_log.md#superseded-cursor-before-0134-release-preparation-2026-10-17`.

Mirror e20d6fa release surfaces at 0.13.4. Move only the ontology-reachability note from Unreleased, follow the migration-entry pattern, refresh the lifecycle acknowledgement from a cache-free copy, and regenerate the adopter payload. Generate Codex derivatives in external scratch; repository `.codex/**` writes remain Main-owned. No capability-lock changes, commits, tags, pushes, publishing or activation here.

Request matrix: (1) version surfaces and cache-free acknowledgement, (2) release and migration notes, (3) adopter generation and scratch Codex parity, (4) required verification with only the repository lock failure expected, (5) records and Main handoff. Existing release/package checks cover these metadata-only edits; no new implementation tests or tasks/tdd.json changes are needed.

Main remaining: review and regenerate repository Codex derivatives, commit A, bind `.mir/capability-lock.json` to A in separate commit B, then rerun the lock check and perform authorized tag, push, publish, capability update/attest/finalize.

Evidence: `tasks/change_log.md#0134-release-preparation-2026-10-17`. All five request-matrix cells were evaluated; 4/5 are closed. The full-gate cell remains open only for Main to bind the release lock in B. Full pytest: 2080 passed, 1 expected repository-lock failure in 240.27s. Ruff, scratch Codex generation/parity, context paths (77) and Korean-text checks (5) passed. Final record-dependent adopter hashes are regenerated and checked separately. No repository Codex files or capability lock were changed.
```

### Previous intent (verbatim)

```json
{
  "goal": "Make mir-core:ontology reachable from ordinary meaning-sensitive work and agent handoffs.",
  "goal_type": "maintenance",
  "scope": "Supplier-owned Mir Yoke sources only; no commit, delivery, version bump, release/attestation changes, activation, restart, secrets, live DB access or repository .codex/** writes.",
  "priority": "normal",
  "updated": "2026-10-17",
  "history": [
    {
      "goal": "Re-verify all 22 repository-maintenance items against current evidence and apply minimal evidenced improvements.",
      "updated": "2026-10-17",
      "status": "superseded",
      "archive": "tasks/change_log.md#superseded-cursor-before-ontology-reachability-2026-10-17"
    },
    {
      "goal": "Make the default work method portable across adopting computers and both runtimes, including delegated Codex sessions.",
      "updated": "2026-10-17",
      "evidence": "tasks/change_log.md#portable-default-work-method-2026-10-17",
      "status": "superseded",
      "archive": "tasks/change_log.md#superseded-continuity-before-matrix-pass-2026-10-17"
    },
    {
      "goal": "Re-verify Mir Yoke against the owner-directed 22-item repository maintenance checklist and apply minimal evidenced improvements.",
      "updated": "2026-10-16",
      "status": "complete",
      "evidence": "tasks/change_log.md#matrix-pass-2026-10-16"
    },
    {
      "goal": "Fix the five Linux release-runner test failures without weakening their behavioral guarantees.",
      "updated": "2026-10-16",
      "status": "complete",
      "evidence": "tasks/change_log.md#linux-release-runner-fixtures-2026-10-16"
    },
    {
      "goal": "Prepare the Mir Yoke 0.13.1 release working tree with version metadata and migration notes only.",
      "updated": "2026-10-16",
      "status": "complete",
      "evidence": "tasks/change_log.md#0131-release-preparation-2026-10-16"
    },
    {
      "goal": "Close ontology impact and isolated distribution gaps and scope E06/E08 evidence.",
      "updated": "2026-10-16",
      "status": "complete",
      "evidence": "tasks/change_log.md#ontology-gap-development-2026-10-16"
    },
    {
      "goal": "Make local validation and fresh-checkout validate workflow commands pass while retaining the memory render guard.",
      "updated": "2026-10-16",
      "status": "complete",
      "evidence": "tasks/change_log.md#local-and-ci-validation-fixes-2026-10-16"
    },
    {
      "goal": "Prevent automatic consistency tests from rendering live agent memory.",
      "updated": "2026-10-16",
      "status": "complete",
      "evidence": "tasks/change_log.md#automatic-memory-render-guard-2026-10-16"
    },
    {
      "goal": "Prepare the Mir Yoke 0.13.0 release working tree with version metadata and migration notes only.",
      "updated": "2026-10-16",
      "status": "complete",
      "evidence": "tasks/change_log.md#0130-release-preparation-2026-10-16"
    },
    {
      "goal": "Correct E03 and E07 covered check references using existing executable behavior tests.",
      "updated": "2026-10-16",
      "status": "complete",
      "evidence": "tasks/change_log.md#superseded-cursor-covered-label-fix-before-0130-preparation-2026-10-16"
    },
    {
      "goal": "Retain repeatable Yoke-domain selection/evidence use and resolve declared relation target-freshness ownership.",
      "updated": "2026-10-16",
      "status": "complete",
      "evidence": "tasks/change_log.md#ontology-rejudgment-g08g13-2026-10-16"
    }
  ],
  "status": "in_progress",
  "evidence": "tasks/change_log.md#ontology-reachability-2026-10-17",
  "authority": "Owner Discord 1560995198857777253; parent-supplied Mir Harness directive ontology-engineering-settlement-2026-10-17."
}
```

## Superseded cursor before 0.13.5 release preparation (2026-10-18)

```markdown
# Plan

## Active task: ontology handoff packet (2026-10-18)

Intent authority: current Mir Harness Main writer brief, recorded in this single active cursor.
Make the six-field handoff packet visible in the ontology skill body, preserve owner authority,
and report actual client results/reasons and the applied configuration source.
Prior plan and intent are preserved in
`tasks/change_log.md#superseded-cursor-before-ontology-handoff-packet-2026-10-18`.

Bounded design: add a compact Handoff section without changing the description, add one sentence
to knowledge-supply guidance, add fail-first tests in the existing style and an Unreleased note,
and regenerate the adopter payload through the documented command. No version bump, commit,
release, network call, live DB write or repository `.codex/**` write is authorized.

Request matrix: (1) body packet/self-check/authority, (2) actual client result/config guidance,
(3) tests, changelog and required generated payload. Evidence:
`tasks/change_log.md#ontology-handoff-packet-2026-10-18`.

Completion: 3/3 done. Fail-first 11 failures became 11 passes; ontology/package gates passed
271 tests, adopter/classification checks passed 28 tests, and Ruff and Codex parity passed.
Final record hashes are included in adopter regeneration and exact inventory verification.
No owner decision or delivery action is part of this task.
```

## Superseded cursor before 0.13.6 release preparation (2026-10-18)

```markdown
# Plan

## Active task: namespace fence and activation scope (2026-10-18)

Intent authority: current Mir Harness Main writer brief, owner Discord 1561086355767824457
(2026-10-18), active Harness run `ontology-engineering-settlement-2026-10-17`, parent-supplied.
This single active cursor is the bounded design authority for this task.
Previous cursor: `tasks/change_log.md#superseded-cursor-before-namespace-fence-and-activation-scope-2026-10-18`.

Implement only the MK client's fail-closed output namespace fence, the Claude activation
verifier's explicit returned `user` scope check, and their regression tests/reference/changelog.
Keep unavailable/empty exit contracts, content-free refusals and feedback behavior. No version
bump, commit, push, tag, release, network, activation, live database, secret/consumer access,
or repository `.codex/**` writes. Main owns derivative regeneration and the later 0.13.6 release.

Bounded design: retain only nodes/citations within explicit requested namespaces, otherwise
`ns:core`, `ns:shared-ops`, `ns:fleet-ops`, `ns:skills`; missing namespace fails closed.
Record a content-free filtering reason in degradation, including when all nodes are dropped.
Apply the fence to every query response, preserving refusal status.
Compare the single enabled Claude inventory record's scope to `user` before path/digest checks.
Use the existing synthetic MCP fixture and isolated synthetic CLI inventory; run tests first.

Request matrix: (1) requested/default namespace and citation isolation plus degradation,
(2) unchanged empty/unavailable/refusal/feedback contracts, (3) user-scope positive/negative
inventory verification, (4) one-line reference and Unreleased notes, (5) relevant verification,
canonical records and generated-parity assessment within the sandbox constraints.
Previous pass: 5/5 evaluated, 4/5 closed. Behavior tests: 323 passed; surface checks: 37 passed.
Cell 5 remains open only for the release-coupled capability-lock digest gate (1 failure).
Ruff, mapping/strict impact, context paths and scratch-only Codex parity passed.
Main remaining: bind the modified plugin tree in the later 0.13.6 release, then rerun the
repository-lock check and release gate. No lock or repository Codex derivatives were written.
Evidence: `tasks/change_log.md#namespace-fence-and-activation-scope-2026-10-18`.

Continuation authority: Main's current namespace-fence degradation-shape writer brief.
Use MK's real `degradation` list shape in the fixture and fail-first regressions. When filtering
drops nodes or citations, append a separate `{"scope":"client","reasons":["namespace_filtered"]}`
entry, creating the list only when absent and preserving every supplier entry. Keep no-echo,
refusal and filtered-empty contracts. Clarify the guide's shape clause, refresh adopter payload
digests with the documented generator, and run the full suite offline. Update the existing
evidence entry; leave the release lock and repository `.codex/**` files to Main.
Continuation matrix: (1) recorded fail-first, (2) list append/preservation and client contracts,
(3) accurate guide clause, (4) payload parity, (5) full-suite evidence and remaining lock gate.
Continuation status: 5/5 writer requests evidenced. Fail-first reproduced the list `setdefault`
AttributeError (1 failed, 281 deselected); corrected regressions passed (44 passed, 249 deselected).
Full suite: 2138 passed, 1 failed in 244.93s. The only failure is the explicitly deferred
`test_repository_lock_is_portable_and_matches_managed_trees`; Main owns release binding.
Payload generation passed for all 887 classified files before the full suite; regenerate after
these final evidence edits and check exact parity again. Mapping/strict impact and scoped Ruff
passed. No release-lock or repository `.codex/**` writes were made.
```

## Superseded cursor before always-delivered handoff authority (2026-10-18)

```markdown
# Plan

## Active task: 0.13.6 release preparation (2026-10-18)

Intent authority: current Mir Harness Main writer brief, owner Discord 1561086355767824457
and earlier delivery direction, parent-supplied. This single active cursor owns the bounded
preparation design; this writer is authorized for content only, without commit or delivery.
Release change `b42ec20`; mirror the 19-file preparation set and method of `5276401`.
Previous cursor: `tasks/change_log.md#superseded-cursor-before-0136-release-preparation-2026-10-18`.

Bounded design: align release versions and lifecycle-hooks acknowledgement, move only the
namespace-fence/Claude user-scope Fixed notes into v0.13.6 dated 2026-10-18, append migration
notes, and regenerate adopter payload after final records using the documented command.
Existing tests cover metadata edits; no new behavior or tests are needed. Use the existing
request matrix here instead of changing the unrelated historical tasks/tdd.json ledger.
No network, commit, tag, push, activation, consumer or live database write. Preserve
`.mir/capability-lock.json` and repository `.codex/**`; Main owns their later handling.

Request matrix: (1) version surfaces and acknowledgement, (2) changelog/migration,
(3) adopter payload parity, (4) full offline suite with only the deferred repository-lock
failure permitted, (5) canonical records and changed-file handoff.
Completion: 5/5 evaluated, 4/5 closed. Full offline suite: 2138 passed, 1 failed in 234.69s;
only `test_repository_lock_is_portable_and_matches_managed_trees` remains open until Main
binds the lock in commit B. Focused checks passed 30 tests; Ruff, Codex parity, context paths
and strict ontology impact passed. Final record hashes are regenerated into adopter payload
and checked exactly after this update. Main owns final repository derivatives, A/B commits,
lock/full-gate verification and subsequent delivery.
Evidence: `tasks/change_log.md#0136-release-preparation-2026-10-18`.
```
