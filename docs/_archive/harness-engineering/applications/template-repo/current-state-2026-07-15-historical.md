---
status: snapshot-live
date: 2026-07-15
scope: public template startup context, dual-CLI parity, and closeout state
template_commit: 72882eb6de4fa815abcc6c5a0256efcd9053fb8d
template_version: 0.7.1
verifier_overall: pass
verifier_major: 0
verifier_minor: 0
phase_docs_present: 13
phase_docs_required: 13
schema_present: 19
schema_required: 19
---

# Mir Yoke Current State — 0.7.1

## Current baseline

- The public template is repository-agnostic and sanitized. Private fleet topology, paths, and
  operator records remain outside the public contract.
- `CLAUDE.md` is the compact startup source; `AGENTS.md`, `.codex/`, and `.agents/` are generated.
- Claude and Codex share the opened-Main contract. Codex-first is a delegated-lane preference, not
  a direct-work gate.
- `.mir/repo-profile.toml` owns detailed identity and boundary values.
- Closeout updates one `tasks/handoffs/session-handoff-LATEST.md`; it does not create timestamped
  session summaries.

## Measured evidence

| Check | Result |
|---|---|
| Root startup instructions | 7,735 bytes total (`CLAUDE.md` 3,740; `AGENTS.md` 3,995) |
| Codex prompt-input JSON | 22,963 bytes with all 12 repository skills discovered |
| SessionStart stdout | 491 bytes |
| Codex derivatives | pass |
| Context paths | pass, 6 files / 68 references |
| Registry and catalog | pass |
| Public applied-state checks 1–8 | pass, no findings |
| Full regression | 564 passed, 1 skipped |

## Residual review items

- Whole-repository Ruff still reports 47 pre-existing findings in untouched legacy surfaces;
  changed Python scopes pass Ruff.
- A local ignored `.mir/memory.db` can make the R11 generated-memory projection check warn. A clean
  public clone has no canonical DB until the adopter initializes it, so the check skips there.
- Root instruction and generator surfaces are repository-fit rollout metadata, not blanket
  verbatim parity inputs for downstream repositories.

## Next release action

- Publish the parity metadata commit anchored to content commit `72882eb`; tag only if the release
  process requires a tag.
