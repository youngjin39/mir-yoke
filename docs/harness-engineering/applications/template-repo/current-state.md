---
status: snapshot-live
date: 2026-05-25
scope: template-harness physical state measured after baseline raise
audience: your-harness Role B (Template Maintainer) + user
template_commit: abb202a
template_version: 0.4.0
verifier_overall: pass
verifier_major: 0
verifier_minor: 0
phase_docs_present: 13
phase_docs_required: 13
schema_present: 19
schema_required: 19
---

# Template Repo Current State — template-harness (2026-05-25 live snapshot)

> **Purpose**: Honestly pin the current physical state of the public template. Records whether the template backlog from phase-13 closure was actually resolved following R30 follow-up application.

> **Conclusion**: The template workspace has been raised to the `v0.4.0` baseline, and `verify_template_applied_state.py` returns `pass`. Phase docs (13), schemas (19), ADR parity baseline, versioning, sanitize, catalog drift, and main-agent parity / delegated Codex-first role-policy baseline all satisfy verifier criteria.

## 1. Git / Versioning State

| Item | Measured value |
|---|---|
| HEAD commit | `abb202a` |
| VERSION | `0.4.0` present |
| CHANGELOG.md | present |
| MIGRATION.md | present |
| verifier overall | `pass` |
| verifier major / minor | `0 / 0` |

## 2. What Is Physically Present

| Surface | State |
|---|---|
| `VERSION`, `CHANGELOG.md`, `MIGRATION.md` | present |
| `docs/templates/_schema/` | 19 / 19 present |
| `docs/decisions/` | verifier baseline parity present |
| `.claude/` runtime surface | present |
| `docs/harness-engineering/phase-0..12` | 13 / 13 present |
| `CLAUDE.md` / `AGENTS.md` role policy | main-agent parity + delegated Codex-first baseline present |
| `docs/templates/repo-profile.template.toml` | `shared_parity` + `subagents_codex_first` present |

## 3. Remaining Physical Gaps

No verifier-blocking physical gaps remain in the current workspace state.

### Remaining follow-up items outside verifier scope

- create a commit/tag that records the `0.4.0` working-tree baseline
- replace concise ADR stubs with fuller public summaries where needed

## 4. Phase-13 Closure Interpretation

phase-13 now closes in the stronger sense:

- current template verdict: **applied**
- reason: physical phase docs, required schemas, ADR parity baseline, sanitize, versioning, and role-policy parity all pass the verifier
- allowed claim: `template phase-0..12 adopted`
- closure lane `phase-13` remains adopted because truth sources still align

## 5. Next Step After Closure

The next closeout path is operational, not physical:

1. commit/tag the `0.4.0` baseline
2. keep template CI green on future promotes
3. replace any concise placeholder ADR text where deeper public detail becomes useful

## 6. Change Log

- 2026-05-25 R30: stale 2026-05-23 snapshot replaced with live measured snapshot for phase-13 closure.
- 2026-05-25 R30 follow-up: template physical baseline raised to verifier-clean `pass`; snapshot updated to applied state.
