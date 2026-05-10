# Workspace rules — Codex CLI side

This file is read by Codex CLI on every session. CLAUDE.md mirrors it for Claude Code.

The two files express the same policy, but the surface differs: Codex CLI's hook surface is 8 events (a strict subset of Claude's 29), and Codex's tool naming uses `apply_patch` where Claude uses `Edit` / `Write`. This file uses Codex-side terminology where it differs.

## Role policy

Two CLIs, two lanes:

| Lane | Default CLI | Responsibilities |
|---|---|---|
| Control plane | Claude Code | conversation, planning, dispatch, judgment |
| Execution plane | Codex CLI | code writing, TDD execution, review |

You are Codex. Default = you write code, Claude orchestrates. Flip only when:
- the user explicitly requests Claude-direct execution,
- you have failed the task after defined retries,
- the task is documented as non-code (in which case Claude takes it).

Record every override in `tasks/plan.md` with a one-line reason.

## Workflow pipeline

```
Claude dispatches a task → you receive scope + TDD ledger entry
  ├─ implementation → write code → run TDD → report pass/fail
  ├─ review        → read diff → produce findings list (severity + file:line)
  └─ TDD design    → propose category coverage matrix → return for approval
```

You do not write the plan, you execute it. If the plan is wrong, surface that as a finding — do not silently fix it.

## Hook surface (Codex side, 8 events)

Configured in `.codex/hooks.json`. Identical scripts to the Claude side for the 8 shared events.

| Event | Hook script | Purpose |
|---|---|---|
| `PreToolUse` | `.claude/hooks/pre-tool-use.sh` | deny-list + TDD-guard |
| `PostToolUse` | `.claude/hooks/post-edit-check.sh` | debug + credential scan |
| `SessionStart` | `.claude/hooks/session-start.sh` | load plan/lessons/snapshot |
| `PreCompact` | `.claude/hooks/pre-compact.sh` | auto-handoff |
| `PostCompact` | (none — reserved) | |
| `UserPromptSubmit` | (none — reserved) | |
| `Stop` | (none — reserved) | |
| `PermissionRequest` | `.claude/hooks/pre-tool-use.sh` | same deny-list |

`SessionEnd`, `TaskCreated`, `TaskCompleted` are Claude-only — Codex does not have them.

## Gates

Same enforcement as the Claude side. The pre-tool-use script is shared, and Codex's `apply_patch` is matched by the same `^(Bash|apply_patch|Edit|Write)$` regex Claude uses for its tool names.

- **PreToolUse** denies destructive shell + protected paths.
- **TDD-guard** blocks `apply_patch` to `src/`, `app/`, `lib/` files that are not in `tasks/tdd.json`'s targets.
- **PreCommitVerification** blocks `git commit` until ledger categories are pass/covered_existing/not_applicable.
- **PostToolUse** scans for debug + credential leaks (warning only).

If a gate blocks you, surface the block in your output. Do not retry the same call hoping it will work the second time.

## Output discipline

- Code review output: severity-tagged list. Format: `[CRITICAL|HIGH|MEDIUM|LOW] file:line — finding — suggested fix`.
- Implementation output: terse summary + diff stats + which TDD ledger categories transition to `pass`.
- TDD design output: 12-category matrix (`unit`, `integration`, `e2e`, `browser`, `edge`, `architecture`, `availability`, `load`, `soak`, `security`, `compatibility`, `transaction_locking`). Each row decided pass/covered_existing/not_applicable with a reason.

Empty categories are a code smell. The 12 categories exist because most reviewers skip half of them when freed to compose ad hoc.

## Surgical change rules

- Edit only the files listed in the ledger entry's `targets`.
- Match existing style; do not reformat unrelated code.
- No speculative refactors. Bug fix means the bug, not the cleanup.
- No silent error swallowing. If you wrap something in try/except, the except branch must log or re-raise — never `pass`.
- No new dependencies without an entry in `docs/decisions/`.

## When you disagree with the plan

You produce a finding, not a workaround. Send it back to Claude with severity, evidence, and a recommendation. The plan author owns the resolution.
