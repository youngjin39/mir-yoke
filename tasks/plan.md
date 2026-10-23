# Plan

## Active task: external-capability-intake-2026-10-24

### Second slice: owner-approved methodology borrows

Intent/design authority: current owner brief, owner Discord 1563245914133495830
(parent-supplied), and the Harness intake report's exact items and exclusions.
Main already applied the first writing-skill slice to the original repository
(parent-supplied); preserve that complete change in this scratch clone.
Add optional experiment, instruction-evaluation and trace-derived patch references,
and an owner-requested memory-quality evaluation skill, following 0b04d0c registration.
Scenarios: bounded experiments preserve evaluator and authority; shorter instructions
retain task quality; trace patches use held-out cases; memory assessment withholds
answers and compares evidence/latency without store writes or autonomous adoption.
Request matrix: fail-first coverage; all five methodology sets and exclusions;
registration/parity; cumulative 0.13.27 metadata/payload; full checks and patch.
Execution stays in this scratch directory. No lock writes, commits, tags or pushes.
Second-slice result: 5/5 request cells have current evidence. Fail-first focused
checks: 4 failed before content; final new checks: 4 passed in 0.02s; package plus
methodology checks: 20 passed in 0.17s. Full gate: 1 failed, 2723 passed, 1 skipped in 358.65s (0:05:58).
Only test_repository_lock_is_portable_and_matches_managed_trees fails, as allowed
before release binding. Ruff and Codex parity pass. Full checks ran on a byte-identical
verification copy inside this clone's .git, with temporary state outside that copy
but still inside this scratch clone. The original temporary layout caused seven
path-boundary failures; all seven pass in the corrected layout without test changes.
First-slice assets and existing skill bodies are preserved; the lock is unchanged.
Final content/payload check: 5 passed in 0.14s. Regenerate the payload after this
ledger update; deliver the cumulative binary diff as mir-yoke-0.13.27-full.patch
in the scratch implementation directory. Main owns any later application or release.
First-slice evidence below remains historical.

Main application (2026-10-24): the cumulative patch is applied to the original
repository (uncommitted). Main host-env re-run: full suite 1 failed (only the
pre-bind capability-lock test), 2724 passed, 0 skipped; Ruff and Codex parity pass;
fail-first re-shown (methodology 4 failed without content, writing 5 failed without
skills; 15 passed with both). Owner kept fluent-korean as a Korean-language skill
with the exact body-hash exemption (Discord 1563250595219898399, parent-supplied).
Commit, ADR-80 bind, tag/push, provider update and attestation await the owner.

Main acceptance and release (2026-10-24, owner Discord 1563261254473355326 approving options 1, 2 and 3, parent-supplied):
- Commits: 4f1c924 source; bind 50411d8 (full suite 2725 passed), tagged v0.13.27, pushed, GitHub release created.
- Provider update from the enrolled 0.13.26 provider-update lock (cfbf106) was accepted (dry run ready_to_apply, then applied); recorded in bda4e97.
- Claude headless session 5a8b843a: runtime init catalog listed all 21 `mir-*` skills; SessionStart printed the Mir continuity line; UserPromptSubmit 5, PreToolUse 5 and Stop 6 runs against 4 non-plugin registrations each.
- Codex sessions: 01a16a1c showed the 21-skill catalog, SessionStart and the UserPromptSubmit packet; 01a16a1d showed the Stop hook_prompt under `mir-lifecycle-hooks/0.13.27`; 01a16a1e-c885 showed all four, including the PreToolUse denial "Owner forbids commands in this handoff turn" for a permitted-looking `echo attest-probe` (agents told only "No commands." obeyed the ban, so the hook never ran).
- Attest: both runtimes runtime_verified with no missing skills or hooks. Finalize: registration active, status ready.

### First slice: preserved preparation record

Authority: owner Discord 1563243323047547173 (parent-supplied), current writer
brief. This single active cursor owns intent and design. Baseline: clean main
at dea069b (0.13.26). Predecessor records are preserved verbatim in
tasks/change_log.md#external-capability-intake-and-01327-preparation-2026-10-24.

Design: follow 0b04d0c registration and release preparation. Preserve the
no-ai-slop upstream behaviour and eval, moving the eval into references; omit
agents/openai.yaml because no existing Yoke skill ships it. Copy the complete
Fluent Korean global policy body and attribution, adding Korean-output trigger
frontmatter. Preserve MIT notices, all rules and existing profile packs.
Register both skills in capability sources, catalog and Codex parity; refresh
all eight plugin manifests, release metadata, lifecycle digest acknowledgement
and the generated adopter payload. No Codex derivative source changes are needed.

Scenarios: both skills are discovered from the same mir-content tree by Claude
and Codex; edit and detect modes retain the upstream eval boundary; Korean output
retains every policy rule and notice. hybrid_pipeline and content_workspace
include the plugin; code_app and infra_runtime continue to exclude it. Contract
and production package/config checks cover these published-source scenarios;
provider installation and live attestation are outside this task.

Request matrix:
1. Fail-first focused tests, then faithful and licensed skill sources.
2. Catalog, capability inventory, package expectations and dual-runtime parity.
3. Complete 0.13.27 release metadata, documentation, digest and generated payload.
4. Full pytest with only the accepted pre-bind capability-lock failure, Ruff and
   Codex sync; read actual output and report every failure.
5. Diff/status evidence and original-repository application.

Execution boundary: the session sandbox permits the authorized scratch copy
but excludes writes to the original repository. Prepare a reviewable patch in
scratch; original-repository application remains open. No commits, tags, pushes,
provider updates, attestation, global-policy edits or capability-lock writes.

Prepared-source result: 4/5 cells have evidence; original application in cell 5
remains open because the sandbox excludes original-repository writes. The final
full suite returned 1 failed, 2719 passed, 1 skipped in 423.22s. Only the accepted
pre-bind capability-lock test fails. The skipped owner-contract comparison has
no owner file at the scratch checkout's relative path. Focused final checks:
35 passed in 0.97s; Ruff and Codex parity pass; script sanitization passes.
Additional required test adjustments: security release version assertion and
an exact path/body-hash Korean policy exception with boundary coverage.
Final ledger edits require one payload regeneration and exact-content checks.
Evidence: tasks/change_log.md#external-capability-intake-and-01327-preparation-2026-10-24.
Main owns original application, verification and any later owner-approved commit;
ADR-80 bind, tag/push, provider update and attestation are outside this task.
