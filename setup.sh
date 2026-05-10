#!/bin/bash
# setup.sh — bootstrap claude-codex-harness in a fresh or existing repo.
#
# Idempotent. Run as many times as you like. Does not overwrite existing files.

set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

say() { printf '%s\n' "$*"; }

say "claude-codex-harness setup ▸ root=$ROOT"

# 1. Make every hook executable.
if [ -d .claude/hooks ]; then
  chmod +x .claude/hooks/*.sh 2>/dev/null || true
  say "✓ hook scripts marked executable"
fi

# 2. Ensure tasks/tdd.json exists with the empty schema. Do not overwrite.
if [ ! -f tasks/tdd.json ]; then
  mkdir -p tasks
  cat > tasks/tdd.json <<'JSON'
{
  "version": 1,
  "changes": []
}
JSON
  say "✓ tasks/tdd.json created (empty)"
else
  say "• tasks/tdd.json already present — left as-is"
fi

# 3. Ensure tasks/plan.md exists.
if [ ! -f tasks/plan.md ]; then
  cat > tasks/plan.md <<'MD'
# Plan

## P0 — bootstrap

Step P0: IN_PROGRESS | scope=initial template install. First real plan entry goes here.
MD
  say "✓ tasks/plan.md created"
else
  say "• tasks/plan.md already present — left as-is"
fi

# 4. Reminder banner.
say
say "Next:"
say "  • Open this directory in Claude Code:  claude ."
say "  • Or in Codex CLI:                     codex"
say "  • Edit .ai-harness/deny-list.yaml to add patterns specific to your project."
say "  • Edit CLAUDE.md and AGENTS.md to set the role policy."
say
say "Both CLIs will auto-load the hooks on next launch."
