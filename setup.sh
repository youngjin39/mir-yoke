#!/bin/bash
# setup.sh — bootstrap mir-yoke in a fresh or existing repo.
#
# Idempotent. Run as many times as you like. Does not overwrite existing files.
# Warns when placeholder values remain from the template (see §Placeholder guard below).

set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

say() { printf '%s\n' "$*"; }
warn() { printf '[WARN] %s\n' "$*" >&2; }
die() { printf '[ERROR] %s\n' "$*" >&2; exit 1; }

say "mir-yoke setup ▸ root=$ROOT"

# 1. Make every hook executable.
if [ -d .claude/hooks ]; then
  chmod +x .claude/hooks/*.sh 2>/dev/null || true
  say "✓ hook scripts marked executable"
fi
# 1b. Sync Python deps so `uv run mir …` and the verifiers work offline.
if command -v uv >/dev/null 2>&1; then
  uv sync --quiet 2>/dev/null && say "✓ python deps synced (uv)" || say "• uv sync skipped (run 'uv sync' manually)"
else
  warn "uv not found — install uv, then 'uv sync', for the mir CLI + verifiers"
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
  mkdir -p tasks
  cat > tasks/plan.md <<'MD'
# Plan

## P0 — bootstrap

Step P0: IN_PROGRESS | scope=initial template install. First real plan entry goes here.
MD
  say "✓ tasks/plan.md created"
else
  say "• tasks/plan.md already present — left as-is"
fi

# 4. Ensure .mir/repo-profile.toml exists (placeholder — edit before first use).
if [ ! -f .mir/repo-profile.toml ]; then
  mkdir -p .mir
  cat > .mir/repo-profile.toml <<'TOML'
# repo-profile.toml — family identity file.
# Replace ALL placeholder values before committing. setup.sh warns while any remain.

[repo]
slug = "your-harness"
display_name = "Your Harness"
repository_type = "starter_template"
rollout_class = "bootstrap_only"
overlay_archetype = "template_transitional"
status = "active"
purpose = "Describe the repository's purpose in one sentence."
technology_stack = []
profile_base_commit = "unverified"
profile_verified_at = ""

[ownership]
main_role = "control_plane"
delegated_execution = "codex_first"
main_agent_contract = "shared_parity"
codex_backend_role = "code_tdd_review_plane"
codex_default_enabled = true
allow_role_override = true
override_requires_record = true

[paths]
code_paths = ["tools/", "src/", "scripts/"]
non_code_paths = ["docs/", "README.md", "CLAUDE.md", "AGENTS.md"]
protected_paths = [".env", ".env.*", "secrets/**"]
generated_paths = []
architecture_refs = ["ARCHITECTURE.md"]
configuration_paths = ["pyproject.toml", "config/"]
verification_paths = ["tests/"]
workflow_refs = ["CLAUDE.md", ".ai-harness/"]
exception_refs = [".mir/boundary.md", ".mir-preserve.toml"]

[preserve]
skills = []
claude_sections = []
agent_memory_paths = []
commands = []
extra_docs = []

[boundaries]
live_runtime = []
secrets = [".env", ".env.*"]
data_sensitivity = "low"
release_window = "anytime"
external_services = []

[execution]
delegated_execution_contract = "subagents_codex_first"
delegation_required_tasks = ["adopter_wide_template_contract_or_bootstrap_change", "release_review"]
delegation_recommended_tasks = ["tools_or_src_implementation", "tests", "independent_review"]
main_direct_tasks = ["placeholder_or_profile_check", "small_documentation_change", "final_publish_judgment"]
codex_allowed_modes = ["code", "review", "tdd"]
codex_blocked_modes = []
review_scope = ["tools/", "src/", "tests/"]
tdd_scope = ["tools/", "src/"]
non_code_profile = "common_ai_only"

[gates]
requires_phase_gate = false
requires_secrets_vault = false
requires_dynamic_egress = false
requires_release_window = false
requires_external_store = false
TOML
  say "✓ .mir/repo-profile.toml created (placeholder — edit before committing)"
else
  say "• .mir/repo-profile.toml already present — left as-is"
fi

# 5. Placeholder guard — warn loudly if template defaults remain.
PLACEHOLDER_HITS=0

if grep -q 'slug = "your-harness"' .mir/repo-profile.toml 2>/dev/null; then
  warn ".mir/repo-profile.toml: slug is still \"your-harness\" — set a real project slug"
  PLACEHOLDER_HITS=$((PLACEHOLDER_HITS + 1))
fi

if grep -q 'display_name = "Your Harness"' .mir/repo-profile.toml 2>/dev/null; then
  warn ".mir/repo-profile.toml: display_name is still \"Your Harness\" — set your project name"
  PLACEHOLDER_HITS=$((PLACEHOLDER_HITS + 1))
fi

if [ "$PLACEHOLDER_HITS" -gt 0 ]; then
  say
  say "  $PLACEHOLDER_HITS placeholder(s) remain. Edit the files listed above before first commit."
  say "  Re-run setup.sh after editing to verify all placeholders are cleared."
fi

# 6. Post-clone checklist banner.
say
say "Post-clone setup checklist:"
say "  [1] Set slug/display_name in .mir/repo-profile.toml (placeholder guard above catches leftovers)"
say "  [2] Update CLAUDE.md only when shared startup invariants differ"
say "  [3] Run: bash scripts/generate_codex_derivatives.sh"
say "  [4] Run: ./setup.sh          (verify placeholder guard passes — 0 warnings)"
say "  [5] Run: uv run mir migrate up   (initialize memory store)"
say "  [6] Run: uv run python scripts/verify_context_paths.py (verify harness path wiring)"
say "  [7] Open in Claude Code:     claude ."
say "  [8] Or in Codex CLI:         codex"
say
say "Both CLIs auto-load hooks on next launch."
