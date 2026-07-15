# Codex CLI side

`hooks.json` mirrors `.claude/settings.json` for the 8 hook events Codex CLI supports.

## Events

| Event | Active | Script |
|---|---|---|
| `PreToolUse` | yes | `.claude/hooks/pre-tool-use.sh` |
| `PostToolUse` | yes | `.claude/hooks/post-edit-check.sh` |
| `PreCompact` | yes | `.claude/hooks/pre-compact.sh` |
| `PostCompact` | reserved | (none) |
| `SessionStart` | yes | `.claude/hooks/session-start.sh` |
| `UserPromptSubmit` | reserved | (none) |
| `Stop` | reserved | (none) |
| `PermissionRequest` | yes | `.claude/hooks/pre-tool-use.sh` (same deny-list) |

`SessionEnd`, `TaskCreated`, `TaskCompleted` are Claude Code-only and do not exist in Codex CLI.
On an explicit Codex closeout, run `.claude/hooks/session-end.sh` to refresh the same canonical
`tasks/handoffs/session-handoff-LATEST.md` used by Claude.

## Auth and credentials

Codex CLI authenticates separately. Files under `.codex/` like `auth.json` or `credentials.json` should never be committed; the `.gitignore` excludes them.

## Wire format

Codex CLI hooks receive the same JSON wire format on stdin that Claude Code uses. The hook scripts here parse `tool_name`, `tool_input.command`, `tool_input.file_path`, and `tool_input.path` — Codex's `apply_patch` tool puts the file in `tool_input.path`.

## Customization

Edit `hooks.json` directly. Re-running setup.sh does not overwrite it.
