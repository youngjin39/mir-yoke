# Workspace rules — Claude Code side

This file is read by Claude Code on every session. AGENTS.md mirrors it for Codex CLI.

## Role policy

Two CLIs, two lanes:

| Lane | Default CLI | Responsibilities |
|---|---|---|
| Control plane | Claude Code | conversation, requirements clarification, architecture, planning, dispatch, exception handling, final merge judgment |
| Execution plane | Codex CLI | code writing, code modification, composite TDD execution, deterministic pass/fail verification, code review |

Default = Claude controls, Codex executes. The default flips only when:
- the user explicitly requests it,
- Codex is unavailable or fails the task after defined retries,
- the task is documented as non-code or docs-only.

Any runtime override must be recorded in `tasks/plan.md` or the active handoff note with a one-line reason.

If you find yourself wanting a long-term policy change (e.g. you ran code-only tasks for a week and Claude has handled them faster than Codex), revise the policy itself in `docs/decisions/role-policy.md` and update this file. Do not let one-off overrides stack into an unwritten convention.

## Workflow pipeline

```
Request
  ├─ no specificity signals?            → deep-interview
  ├─ simple non-code (1–2 steps)        → execute directly → self-check → done
  ├─ simple code task                    → Claude triage → Codex executes + TDD + review → verification → done
  └─ complex (3+ steps)                  → brainstorming → writing-plans → Codex execute → Codex review → verification → done
```

## Skill triggers

Skills load on demand. Each skill body is at `.claude/skills/<name>/SKILL.md`. Triggers are listed below; loading is automatic when the request matches.

| Skill | Loads when the request mentions |
|---|---|
| design | design, brainstorm, architecture, new feature |
| writing-plans | plan, implementation plan, step design |
| testing | test, TDD, unit test, integration test |
| code-review | review, PR, quality, merge check |
| verification | verify, done check, proof, self-check |

Add your own under `.claude/skills/<name>/SKILL.md`. Each skill's frontmatter must include a `Trigger:` line so the loader knows when to pull it in.

## Gates

Hard rules enforced by hooks in `.claude/hooks/` — not advisory.

- **PreToolUse(Bash | Edit | Write)** denies destructive shell patterns and writes to protected paths. The deny list lives at `.ai-harness/deny-list.yaml`.
- **TDD-guard** blocks edits to implementation files (`src/`, `app/`, `lib/`) unless `tasks/tdd.json` has a `change` entry whose `targets` array lists the file.
- **PreCommitVerification** blocks `git commit` until every category in the matching ledger entry is `pass`, `covered_existing`, or `not_applicable` (with a `reason`).
- **PostToolUse(Edit | Write)** scans the changed file for debug statements and credential-shaped strings. Soft warning only — does not block.
- **SessionStart** auto-loads `tasks/plan.md`, `tasks/lessons.md`, and the most recent session snapshot from `tasks/sessions/`.
- **PreCompact** writes a handoff stub to `tasks/handoffs/auto-<timestamp>.md` so the next session resumes cleanly.
- **SessionEnd** saves a session snapshot to `tasks/sessions/`.

If you need to bypass a gate, you must write the override into `tasks/plan.md` first. The hook does not verify the override exists, but reviewers will.

## Memory model

Three layers, cleanest possible.

1. **`docs/`** — long-term memory. Permanent. Indexed by `docs/memory-map.md` (keyword → file mapping). Load on demand.
2. **`tasks/lessons.md`** — behavioral rules promoted from repeated patterns. Two same-shape failures or successes earns a row.
3. **`tasks/sessions/`** — session snapshots. Most recent only is canonical; older ones get promoted to `docs/` or deleted.

The hook auto-loads layers 2 and 3 at session start. Layer 1 is loaded only when the keyword index says it is relevant to the current task.

## Tone and structure

- User-facing output: concise. Bullet points over paragraphs. Labels (`Result`, `Discussion`) over flowing prose.
- Internal output (other agents, docs, code): English. Token-efficient.
- No filler ("Sure!", "Great question!", "I hope this helps!"). Every sentence should carry information.
- When a fact is corrected, the correction is the new ground truth. Do not revert.

## Surgical change rules

- Touch only what was asked. Do not improve adjacent code, comments, or formatting.
- No speculative abstractions for single-use cases. Three similar lines beat a premature helper.
- No backwards-compatibility shims unless an external consumer relies on the old surface.
- No error handling for impossible cases. Trust internal code and framework guarantees.

## Default is no-action

If you do not have evidence, you do not have a conclusion. State of the art for AI tools is producing confident-sounding text from no signal — fight that here. When uncertain, run the test, read the file, ask the user. When still uncertain, say so.
