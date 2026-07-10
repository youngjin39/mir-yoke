# global-rules/

Baseline coding rules extracted so they can live in your **global** agent config, shared across
every repository you work in — not just this project.

- `CLAUDE.global.md` — merge into `~/.claude/CLAUDE.md` (Claude Code, global).
- `AGENTS.global.md` — merge into `~/.codex/AGENTS.md` (Codex CLI, global).

## Why

Claude Code and Codex CLI each merge a **global** rules file with the **project-local** one. This
project's `CLAUDE.md` / `AGENTS.md` are self-sufficient for the harness. These global-baseline
files are optional: they carry universal coding discipline (think before coding, simplicity first,
surgical changes, goal-driven execution, remote-channel etiquette) that you likely want on EVERY
repo. They contain no project-, machine-, or deployment-specific content — safe to adopt as-is.

## Use

```bash
# review, then merge into your global config (do not blindly overwrite an existing global file):
cat global-rules/CLAUDE.global.md   # -> merge relevant sections into ~/.claude/CLAUDE.md
cat global-rules/AGENTS.global.md   # -> merge relevant sections into ~/.codex/AGENTS.md
```

Keep the two in sync — they are mirrors of the same rules for the two CLIs.
