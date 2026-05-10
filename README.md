# claude-codex-harness

**An enforcement-first harness template for the Claude Code + Codex CLI pair.**

A reusable starting point for teams who want their AI coding assistants to follow rules — not just hope they do. Hooks block destructive shell, gate code-path edits behind a TDD ledger, and run the same verification on both Claude Code and Codex CLI.

If you have ever asked an AI to "be careful" and watched it overwrite a config file anyway, this is the answer: replace politely-worded prompts with executable guards.

---

## What this is

A directory layout + hook scripts + rule documents you copy into a new (or existing) repository so that Claude Code and Codex CLI behave like team members under the same playbook.

What you get out of the box:

- **Pre-tool-use guard** — denies destructive shell patterns and protected paths before the tool runs.
- **Post-edit checks** — flag debug statements and credential leaks immediately after every Edit/Write.
- **Composite TDD ledger** — implementation edits are blocked unless `tasks/tdd.json` has a planning entry covering the file.
- **Pre-commit verification** — the planning entry's verification commands must pass before the commit lands.
- **Session lifecycle** — auto-loaded plan/lessons/memory at session start, auto-saved snapshots at session end, auto-handoff at compact.
- **Skill triggers** — five built-in skills for `design`, `writing-plans`, `testing`, `code-review`, and `verification` that load only when triggered (saves tokens).
- **Dual CLI parity** — the same hooks fire from both Claude Code (`.claude/settings.json`) and Codex CLI (`.codex/hooks.json`). The wire format is shared, so you author once.

What this is **not**: a runtime, a framework, or a service. There is no daemon. There is no SaaS. The harness is just files in your repo. If you delete the directory, your project goes back to behaving like it did before.

---

## Why dual CLI?

Claude Code and Codex CLI overlap in capability but differ in token budget, scoping, and review style. Most non-trivial work benefits from using both: one for control-plane (planning, design, judgment) and the other for execution (code writing, TDD, review). This template assumes you will run both — and pins the rules so they cannot drift apart.

The eight hook events that exist on both sides — `PreToolUse`, `PostToolUse`, `PreCompact`, `PostCompact`, `SessionStart`, `UserPromptSubmit`, `Stop`, `PermissionRequest` — get the same script. Claude Code's additional 21 events get Claude-only enforcement (e.g. `TaskCreated` / `TaskCompleted` for TDD).

---

## Quick start (5 minutes)

```bash
# 1. Clone or copy the template into your repo.
git clone https://github.com/<you>/claude-codex-harness.git my-project
cd my-project

# 2. Run the setup script.
./setup.sh

# 3. Open the project in Claude Code.
claude .

# 4. Or in Codex CLI.
codex
```

The setup script:
- Makes the hook scripts executable
- Creates an empty `tasks/tdd.json` if one is not present
- Prints a one-line summary of what just got installed

Both CLIs will pick up the hooks on next launch. No daemon, no background process.

---

## Project layout

```
.
├── CLAUDE.md                   # Claude Code workspace rules (orchestration, role policy, gates)
├── AGENTS.md                   # Codex CLI mirror — same rules, Codex-flavored
├── setup.sh                    # one-command bootstrap
├── README.md                   # (this file)
├── LICENSE                     # MIT
├── CONTRIBUTING.md             # how to extend the template
│
├── .claude/                    # Claude Code surface
│   ├── settings.json           #   hook + permission config (29 events available)
│   ├── hooks/                  #   shell scripts (PreToolUse, PostToolUse, ...)
│   ├── skills/                 #   trigger-loaded skill bodies
│   └── agents/                 #   sub-agent personas
│
├── .codex/                     # Codex CLI surface
│   └── hooks.json              #   8-trigger mirror of .claude/settings.json
│
├── .ai-harness/                # the rules (CLI-agnostic)
│   ├── common-ai-rules.md      #   loaded on every task
│   ├── development-ai-rules.md #   loaded on code tasks
│   ├── deny-list.yaml          #   destructive patterns the hook blocks
│   ├── tdd-matrix.md           #   the 12-category TDD ledger spec
│   ├── session-closeout.md     #   end-of-session checklist
│   └── failure-patterns.md     #   recurring AI mistakes worth pinning
│
├── tasks/                      # the working ledger
│   ├── plan.md                 #   current phase summary
│   ├── tdd.json                #   composite TDD ledger (the gate)
│   ├── change_log.md           #   what changed and why
│   ├── lessons.md              #   patterns promoted to rules
│   ├── sessions/               #   session snapshots
│   └── handoffs/               #   inter-session handoffs
│
├── docs/                       # long-term memory
│   ├── memory-map.md           #   keyword → file index
│   ├── decisions/              #   ADRs
│   ├── architecture/           #   system structure
│   ├── patterns/               #   recurring patterns
│   └── references/             #   external repo analyses
│
└── examples/                   # short walk-throughs
```

---

## How the gates work

### Pre-tool-use (input-stage)
Before Claude Code or Codex CLI runs `Bash`, `Edit`, `Write`, or `apply_patch`, the hook reads the deny-list and:
- **blocks** patterns marked `severity: block` (e.g. `rm -rf /`, `git push --force`)
- **warns** on `severity: warn`
- exits 0 otherwise

### Post-edit-check
After every Edit/Write, the hook scans the changed file for debug statements (`console.log`, `print(` in non-test code) and credential-shaped strings (AWS keys, JWTs, etc.). Flags are surfaced to the agent so it has a chance to clean up before commit.

### TDD-guard
Implementation files (anything under `src/`, `app/`, or `lib/` ending in `.py`/`.ts`/`.go`/...) are blocked from editing unless `tasks/tdd.json` contains a `change` entry whose `targets` list the file. Planning is required *before* coding.

### Pre-commit verification
On `git commit`, the hook walks the changed files, finds the matching ledger entry, and runs its `categories.*.command` strings. If any test that is marked `pass` does not actually pass, the commit is blocked.

The ledger has 12 categories — `unit`, `integration`, `e2e`, `browser`, `edge`, `architecture`, `availability`, `load`, `soak`, `security`, `compatibility`, `transaction_locking`. Each is either `pass` (with a runnable command), `covered_existing`, or `not_applicable` (with a written reason). The 12 categories are deliberately broader than typical TDD; the goal is to make the agent notice the dimensions it would otherwise skip.

---

## Customizing for your project

Three files carry the project-specific knobs:

1. **`.ai-harness/deny-list.yaml`** — add or remove patterns the pre-tool-use hook blocks. Each entry has `id`, `pattern` (regex), `severity` (`block` / `warn`), and `reason`.
2. **`CLAUDE.md`** — set the role policy (which CLI handles what), the orchestration preset table, and the project-specific gates.
3. **`AGENTS.md`** — Codex's view. Should mirror CLAUDE.md but in Codex-flavored language.

Everything else is convention. You can rename `tasks/` to `state/`, drop `docs/patterns/`, replace the skills — the hooks key off paths declared in your CLAUDE.md / AGENTS.md, not magic constants.

---

## Comparison

This template is opinionated about one specific thing: **enforcement**. It exists because advisory rules in markdown — "please don't push to main", "remember to write tests" — are read by AI agents the same way humans read EULAs. Rules need to be code that runs, not text that gets glanced at.

If you want a more general Claude Code starter (skills + memory but no enforcement gates), look at the original [Claude Code Prompt Harness](https://github.com/anthropics/claude-code) inspiration tree. If you want a multi-agent runtime, look at frameworks like Archon or OpenHarness. This template sits earlier in the stack: a clean playbook two CLIs can both follow.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Issues and PRs welcome — particularly adding new deny-list patterns, new skills, and new examples. Avoid implementation-specific code; this is a template, not a runtime.

## License

MIT — see [LICENSE](LICENSE). Use it, fork it, strip it for parts.
