#!/bin/bash
# Derived from the Mir harness reference implementation.
# Attribution: claude-starter (yojini/claude-starter, Apache-2.0)
# Modifications:
#   - Mir-specific manifest path (.codex-sync/manifest.json — same)
#   - Mir skill profiles: core=12 runtime-default skills, full=18 including Starter-derived optional packs
#   - Agent TOML mirrors are generated from .claude/agents source.
#   - write_hooks_json() SKIPPED (repository-owned P0-G hooks.json preserved byte-for-byte)
#   - codex_hooks = true added to [features] in write_config_toml
#   - link_skill_md uses symlinks (claude-starter approach replaces old write_skill_md copy)
#   - FULL_SKILLS expanded to Mir 19: core 12 + Starter-derived optional-pack skills
#     (ai-readiness-cartography, improve-token-efficiency, knowledge-ingest,
#      knowledge-lint, browser-automation, code-review-graph).

set -euo pipefail
shopt -s nullglob

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

OUTPUT_ROOT="${CODEX_DERIVATION_OUTPUT_ROOT:-.}"
DERIVATION_PROFILE="${CODEX_DERIVATION_PROFILE:-core}"
if [ "$OUTPUT_ROOT" = "." ]; then
  OUTPUT_ROOT="$ROOT_DIR"
elif [[ "$OUTPUT_ROOT" != /* ]]; then
  OUTPUT_ROOT="$ROOT_DIR/$OUTPUT_ROOT"
fi

if [ ! -f "CLAUDE.md" ]; then
  echo "ERROR: CLAUDE.md not found in repository root." >&2
  exit 1
fi

mkdir -p "$OUTPUT_ROOT/.codex/agents" "$OUTPUT_ROOT/.codex/hooks" "$OUTPUT_ROOT/.agents/skills" "$OUTPUT_ROOT/.codex-sync"
mkdir -p "$OUTPUT_ROOT/.claude/hooks/lib"

# .codex/hooks/lib must be a symlink to ../../.claude/hooks/lib (canonical shared lib).
# Idempotent: if a real directory exists from a stale checkout, remove it first.
if [ -e "$OUTPUT_ROOT/.codex/hooks/lib" ] && [ ! -L "$OUTPUT_ROOT/.codex/hooks/lib" ]; then
  rm -rf "$OUTPUT_ROOT/.codex/hooks/lib"
fi
if [ ! -L "$OUTPUT_ROOT/.codex/hooks/lib" ]; then
  ln -s ../../.claude/hooks/lib "$OUTPUT_ROOT/.codex/hooks/lib"
fi

# Mir core profile has 12 runtime-default skill groups (ADR-15 §S4 consolidation).
# Each group absorbs one or more legacy slugs; legacy SKILL.md files remain
# dispatchable until P15-I archive moves them under archive/skills/.
CORE_SKILLS=(
  bluebricks
  code-review
  commit
  design
  efficiency
  governance
  knowledge
  memory-gc
  automation
  testing
  ui-design
  verify
)

# Mir full profile is identical to CORE after ADR-15 §S4 consolidation —
# the 12 groups already absorb every legacy Starter-derived skill (P15-D
# catalog: 27 Mir-owned → 12 groups, 1:1 mapped).
FULL_SKILLS=(
  bluebricks
  code-review
  commit
  design
  efficiency
  governance
  knowledge
  memory-gc
  automation
  testing
  ui-design
  verify
)

extract_frontmatter_field() {
  local file="$1"
  local key="$2"
  python3 - "$file" "$key" <<'PY'
from pathlib import Path
import re
import sys

path = Path(sys.argv[1])
key = sys.argv[2]
text = path.read_text(encoding="utf-8")
match = re.match(r"^---\s*\n(.*?)\n---\s*(?:\n|$)", text, re.DOTALL)
if not match:
    raise SystemExit(0)

block = match.group(1)
key_pattern = re.compile(r"^([a-zA-Z_][a-zA-Z0-9_]*):\s*(.*)$")
result: dict[str, str] = {}
current_key = None
current_buffer: list[str] = []
in_quoted_continuation = False


def strip_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value.startswith('"') and value.endswith('"'):
        return value[1:-1]
    return value


for line in block.split("\n"):
    if in_quoted_continuation:
        current_buffer.append(line)
        stripped = line.rstrip()
        if stripped.endswith('"') and not stripped.endswith('\\"'):
            result[current_key] = strip_quotes("\n".join(current_buffer))  # type: ignore[index]
            current_key = None
            current_buffer = []
            in_quoted_continuation = False
        continue

    key_match = key_pattern.match(line)
    if not key_match:
        continue

    parsed_key = key_match.group(1)
    value_part = key_match.group(2)
    stripped = value_part.strip()
    if stripped.startswith('"') and not (stripped.endswith('"') and len(stripped) > 1):
        current_key = parsed_key
        current_buffer = [value_part]
        in_quoted_continuation = True
    else:
        result[parsed_key] = strip_quotes(value_part)

sys.stdout.write(result.get(key, ""))
PY
}

body_without_frontmatter() {
  local file="$1"
  awk '
    BEGIN { in_fm = 0; seen = 0 }
    NR == 1 && $0 == "---" { in_fm = 1; next }
    in_fm && $0 == "---" && seen == 0 { in_fm = 0; seen = 1; next }
    !in_fm { print }
  ' "$file"
}

body_preface_without_frontmatter() {
  local file="$1"
  body_without_frontmatter "$file" | awk '
    /^## / { exit }
    { print }
  '
}

has_exact_heading() {
  local file="$1"
  local heading="$2"
  awk -v heading="$heading" '$0 == heading { found = 1; exit } END { exit found ? 0 : 1 }' "$file"
}

is_canonical_starter_claude() {
  local file="$1"
  has_exact_heading "$file" "## Required Reads" \
    && has_exact_heading "$file" "## Workflow" \
    && has_exact_heading "$file" "## Agent / Skill / Hook Contract"
}

escape_toml_multiline() {
  perl -0pe 's/"""/\\"""/g'
}

selected_skill_names() {
  case "$DERIVATION_PROFILE" in
    core) printf '%s\n' "${CORE_SKILLS[@]}" ;;
    full) printf '%s\n' "${FULL_SKILLS[@]}" ;;
    *)
      echo "ERROR: unsupported CODEX_DERIVATION_PROFILE=$DERIVATION_PROFILE" >&2
      exit 1
      ;;
  esac
}

has_selected_skill() {
  local name="$1"
  selected_skill_names | grep -qx "$name"
}

emit_section() {
  local file="$1"
  local heading="$2"
  awk -v heading="$heading" '
    $0 ~ /^```/ { in_fence = !in_fence }
    $0 == heading { in_section = 1 }
    in_section {
      if (!in_fence && $0 ~ /^## / && $0 != heading) exit
      if (!in_fence && $0 ~ /^<Failure_Modes_To_Avoid>$/) exit
      print
    }
  ' "$file"
}

emit_shared_policy_sections() {
  local file="$1"
  local first=1
  local headings=(
    "## Context Management"
    "## Language Protocol"
    "## Surgical Change Rules"
    "## Token Efficiency"
    "## Principles"
  )

  local heading
  for heading in "${headings[@]}"; do
    if [ "$first" -eq 0 ]; then
      echo
    fi
    emit_section "$file" "$heading"
    first=0
  done
}

emit_runtime_sections() {
  local file="$1"
  local first=1
  local headings=(
    "## Required Reads"
    "## Workflow"
    "## Mode Classification"
    "## Agent / Skill / Hook Contract"
    "## Harness Defaults"
    "## Custom Harness Rules"
    "## Codex Derivation Layer"
    "## Codex Use Boundary"
    "## Skill Trigger Table"
  )

  local heading
  for heading in "${headings[@]}"; do
    if [ "$first" -eq 0 ]; then
      echo
    fi
    emit_section "$file" "$heading"
    first=0
  done
}

emit_agent_sections_for_codex() {
  local src="$1"
  local name="$2"
  local first=1
  local headings=()

  case "$name" in
    main-orchestrator)
      headings=(
        "## Startup Protocol"
        "## Ambiguity Gate"
        "## Task Classification"
        "## Task-Weight Model Routing (ADR-49, advisory)"
        "## Orchestration Presets"
        "## Simple Tasks (direct execution)"
        "## Complex Tasks (pipeline)"
        "## Codex Backend Dispatch Self-Check (ADR-18 §S2 Layer 1)"
        "## Active Agent Resolution (pre-dispatch)"
        "## Specialist Scope-Pattern Routing (ADR-17 §S2 P17-B)"
        "## Sub-agent dispatch policy"
        "## Post-Dispatch Monitoring (ADR-60 R6)"
        "## Post-completion"
        "## Feedback → Learning"
        "## Reporting"
        "## Language"
      )
      ;;
    executor-agent)
      headings=(
        "## Protocol"
        "## Codex CLI invocation (ADR-09 round 4 — lessons from Phase 9A phantom \"stdin issue\")"
        "## State Checkpoint (externalize, don't trust memory — ADR-60 R5)"
        "## Report Format"
        "## Language"
      )
      ;;
    quality-agent)
      headings=(
        "## Adversarial Lens"
        "## Protocol"
        "## Report Format"
        "## Language"
      )
      ;;
    *)
      body_without_frontmatter "$src"
      return
      ;;
  esac

  body_preface_without_frontmatter "$src"

  local heading
  for heading in "${headings[@]}"; do
    echo
    emit_section "$src" "$heading"
  done

  local failure_block
  failure_block="$(body_without_frontmatter "$src" | awk '
    /<Failure_Modes_To_Avoid>/ { in_block = 1 }
    in_block { print }
    /<\/Failure_Modes_To_Avoid>/ { exit }
  ')"
  if [ -n "$failure_block" ]; then
    echo
    printf '%s\n' "$failure_block"
  fi
}

emit_codex_agent_skill_hook_contract() {
  local file="$1"
  emit_section "$file" "## Agent / Skill / Hook Contract" | python3 -c '
import sys
text = sys.stdin.read()
replacements = {
    "- Hooks own automatic enforcement and state:": "- Hooks describe Claude automatic behavior and the Codex mirror obligations for the same outcomes:",
    "  - `SessionStart` loads startup context (`tasks/plan.md`, `tasks/lessons.md`, `docs/memory-map.md`, latest session snapshot when present); treat that context as authoritative, then read more only when the task requires it.": "  - [Claude] `SessionStart` loads startup context (`tasks/plan.md`, `tasks/lessons.md`, `docs/memory-map.md`, latest session snapshot when present); treat that context as authoritative, then read more only when the task requires it. [Codex] Read the same startup files manually before acting.",
    "  - `PreCompact` creates a handoff skeleton before context reduction; review and complete it before compacting. This is advisory; the hook does not block compaction.": "  - [Claude] `PreCompact` creates a handoff skeleton before context reduction; review and complete it before compacting. This is advisory; the hook does not block compaction. [Codex] Before invoking compaction, manually create a handoff document in `tasks/handoffs/` mirroring the PreCompact contract.",
    "  - `PreToolUse` enforces path safety before edits/commands.": "  - [Claude] `PreToolUse` enforces path safety before edits/commands. [Codex] Apply the same blocked-intent rules through the instruction contract and verifier-backed drift checks.",
    "  - `TddGuard` enforces the test-first rule for edits to existing implementation files when related tests are detectable.": "  - [Claude] `TddGuard` enforces the test-first rule for edits to existing implementation files when related tests are detectable. [Codex] Apply the same test-first rule through the instruction contract and verifier-backed drift checks.",
    "  - `PostToolUse` inspects edits for debug leftovers and credential leaks.": "  - [Claude] `PostToolUse` inspects edits for debug leftovers and credential leaks. [Codex] Treat the same review as mandatory manual post-edit work.",
    "  - `SessionEnd` saves the latest session snapshot for continuity. This preserves state, not proof of completion.": "  - [Claude] `SessionEnd` saves the latest session snapshot for continuity. This preserves state, not proof of completion. [Codex] At session end, manually create a session snapshot in `tasks/sessions/` mirroring the SessionEnd contract.",
}
for old, new in replacements.items():
    text = text.replace(old, new)
sys.stdout.write(text)
'
}

emit_codex_required_reads() {
  local file="$1"
  emit_section "$file" "## Required Reads" | python3 -c '
import sys
text = sys.stdin.read()
text = text.replace(
    "12. `docs/operations/claude-runtime.md` when task flow, hooks, or memory behavior matters",
    "12. `docs/operations/codex-runtime.md` when task flow, generated instructions, or memory behavior matters",
)
sys.stdout.write(text)
'
}

write_agents_md() {
  local skill_list
  skill_list="$(selected_skill_names | tr '\n' ',' | sed 's/,$//' | sed 's/,/, /g')"
  if is_canonical_starter_claude CLAUDE.md; then
    {
      echo "<!-- GENERATED FILE: edit CLAUDE.md and rerun scripts/generate_codex_derivatives.sh -->"
      echo
      echo "# Codex Project Instructions"
      echo
      echo "## Source Of Truth"
      echo "- Edit \`CLAUDE.md\`, \`.claude/agents/*\`, \`.claude/skills/*\`."
      echo "- Do not hand-edit \`AGENTS.md\`, \`.codex/\`, or \`.agents/\`."
      echo
      echo "## Startup"
      echo "- Read the startup context files required by the SessionStart mirror rule before acting."
      echo "- Use generated Codex skills first."
      echo "- If derived files are stale, regenerate from Claude source."
      echo
      echo "- Skills: \`$skill_list\`"
      echo
      emit_codex_required_reads CLAUDE.md
      echo
      emit_section CLAUDE.md "## Workflow"
      echo
      emit_section CLAUDE.md "## Mode Classification"
      echo
      emit_codex_agent_skill_hook_contract CLAUDE.md
      echo
      emit_section CLAUDE.md "## Harness Defaults"
      echo
      emit_section CLAUDE.md "## Custom Harness Rules"
      echo
      emit_section CLAUDE.md "## Codex Derivation Layer"
      echo
      emit_section CLAUDE.md "## Codex Use Boundary"
      echo
      emit_section CLAUDE.md "## Skill Trigger Table"
      echo
      emit_shared_policy_sections CLAUDE.md
    } > "$OUTPUT_ROOT/AGENTS.md"
  else
    {
      echo "<!-- GENERATED FILE: edit CLAUDE.md and rerun scripts/generate_codex_derivatives.sh -->"
      echo
      echo "# Codex Project Instructions"
      echo
      echo
      echo "## Source Of Truth"
      echo "- Edit \`CLAUDE.md\`, \`.claude/agents/*\`, \`.claude/skills/*\`."
      echo "- Do not hand-edit \`AGENTS.md\`, \`.codex/\`, or \`.agents/\`."
      echo
      echo "## Startup"
      echo "- Read the startup context files required by the local Claude workflow before acting."
      echo "- Use generated Codex skills first."
      echo "- If derived files are stale, regenerate from Claude source."
      echo
      echo "- Skills: \`$skill_list\`"
      echo
      cat <<'EOF'
## Main-Agent Orchestration Contract
- The opened CLI (Claude or Codex) is the control_plane main; Codex main carries the same orchestration contract as Claude main.
- Full Startup Protocol, Ambiguity Gate, and Task Classification: `.codex/agents/main-orchestrator.toml` (generated mirror of `.claude/agents/main-orchestrator.md`) - adopt it as your session contract.
- Ambiguity Gate:
  - Specificity signals: file path, function name, numbered steps, or error message.
  - 0 specificity signals -> load `design` skill (interview subtype) and resolve ambiguity before execution.
  - `force:` prefix bypasses the ambiguity gate.
- Task Classification:
  - 0 specificity signals -> design interview -> ambiguity gating.
  - Tiny or bounded work -> execute directly -> smallest useful check -> done.
  - Normal work -> use a short design note only when a material choice exists; execute directly or delegate when useful.
  - Heavy, restartable, or cross-repo work -> persist a plan or `DispatchBrief`; use isolation or delegation when it reduces risk.
- Classify from uncertainty, blast radius, coordination, and reversibility, not step or file count.
- Source-of-truth, protected-scope, and fleet rollout boundaries still apply to harness and generated surfaces.

## Codex Hook-Mirror Obligations
- [Codex] `SessionStart`: read startup context manually before acting (`tasks/plan.md`, `tasks/lessons.md`, and required local workflow docs).
- [Codex] `PreCompact`: before compaction, manually create a handoff document in `tasks/handoffs/` mirroring the PreCompact contract.
- [Codex] `PostToolUse`: after edits, manually review for debug leftovers and credential leaks.
- [Codex] `SessionEnd`: at session end, manually create a session snapshot in `tasks/sessions/` mirroring the SessionEnd contract.
- [Codex] `UserPromptSubmit`: for substantial prompts, run `uv run mir context pull "<query>"` for memory retrieval.
- [Codex] `TaskCreated` / `TaskCompleted`: use `tasks/tdd.json` for broad or high-risk work; lifecycle hooks are advisory.
EOF
      # DEDUP GUARD: only inject if CLAUDE.md does NOT already contain the section.
      # (Some CLAUDE.md variants have it and it arrives via body_without_frontmatter below.)
      if ! grep -q '## Continuation Loop Protocol' CLAUDE.md 2>/dev/null; then
        echo
        cat <<'LOOP_EOF'
## Continuation Loop Protocol
- Use the file-backed loop only for restartable, delegated, or multi-session work.
- `tasks/plan.md` is the sole cursor when used; do not create a second cursor in `run_state.json`.
- Execute coherent independently verifiable work units and update the declared evidence before advancing the cursor.
- A failed step returns control without automatic retry. Retry only after a plausible transient cause or a material brief or approach change.
- `BLOCKED` means no safe in-scope path remains without new authority or repair of an explicit failed requirement.
- Non-LLM automation must preserve protected boundaries and explicitly selected verification.
- `tools/run_orchestrator` remains observer-only; it is not the continuation executor.
LOOP_EOF
      fi
      echo
      body_without_frontmatter CLAUDE.md
    } > "$OUTPUT_ROOT/AGENTS.md"
  fi
}

write_config_toml() {
  local approval_policy="on-request"
  local settings_source=""
  if [ -f ".claude/settings.local.json" ]; then
    settings_source=".claude/settings.local.json"
  elif [ -f ".claude/settings.json" ]; then
    settings_source=".claude/settings.json"
  fi
  if [ -n "$settings_source" ]; then
    local mode
    mode="$(jq -r '.permissions.defaultMode // empty' "$settings_source" 2>/dev/null || true)"
    if [ "$mode" = "bypassPermissions" ]; then
      approval_policy="never"
    else
      local broad_allow
      broad_allow="$(jq -r '
        (.permissions.allow // []) as $paths
        | (
            ($paths | index("Bash(*)") != null) and
            ($paths | index("Read(*)") != null) and
            ($paths | index("Write(*)") != null) and
            ($paths | index("Edit(*)") != null)
          )
      ' "$settings_source" 2>/dev/null || true)"
      if [ "$broad_allow" = "true" ]; then
        approval_policy="never"
      fi
    fi
  fi

  {
    echo "# GENERATED FILE: edit Claude source files and rerun scripts/generate_codex_derivatives.sh"
    echo
    echo "approval_policy = \"$approval_policy\""
    echo 'sandbox_mode = "danger-full-access"'
    echo 'web_search = "cached"'
    echo 'personality = "pragmatic"'
    echo 'project_doc_fallback_filenames = ["AGENTS.md"]'
    echo 'project_doc_max_bytes = 32768'
    echo
    echo '[agents]'
    echo 'max_threads = 6'
    echo 'max_depth = 1'
    echo
    echo '[features]'
    # Keep both keys during the transition window: some local verifiers still assert
    # `codex_hooks = true`, while newer Codex builds prefer `hooks = true`.
    echo 'codex_hooks = true'
    echo 'hooks = true'
    echo 'multi_agent = true'
    echo 'shell_snapshot = true'
    echo 'personality = true'
    echo
    if [ -f ".mcp.json" ]; then
      jq -r '
        .mcpServers
        | to_entries[]
        | "\n[mcp_servers.\"" + .key + "\"]\ncommand = \"" + .value.command + "\"\nargs = [" + ((.value.args // []) | map("\"" + . + "\"") | join(", ")) + "]"
      ' .mcp.json
    fi
  } > "$OUTPUT_ROOT/.codex/config.toml"
}

# write_hooks_json is skipped: .codex/hooks.json is a reviewed repository-owned P0-G artifact.
# Keep it behaviorally aligned with .claude/settings.json when either hook surface changes.
# BORROWED-FROM modification: claude-starter calls write_hooks_json() here; Mir does not.

write_agent_toml() {
  local src="$1"
  local name description developer_instructions out sandbox_mode disallowed_tools
  name="$(extract_frontmatter_field "$src" "name")"
  [ -n "$name" ] || return 0  # skip non-agent sources (e.g. README.md: no name frontmatter)
  description="$(extract_frontmatter_field "$src" "description")"
  developer_instructions="$(emit_agent_sections_for_codex "$src" "$name" | escape_toml_multiline)"
  disallowed_tools="$(extract_frontmatter_field "$src" "disallowedTools")"
  # ADR-09 round 3 fix: do NOT emit execution_backend to .codex/agents/*.toml.
  # Codex CLI has a strict TOML schema (Rust serde, no #[serde(unknown_fields)])
  # and rejects unknown fields with "Ignoring malformed agent role definition",
  # which causes Codex to discard the entire agent role. execution_backend is
  # Claude-side dispatch metadata and lives only in .claude/agents/*.md frontmatter.
  out="$OUTPUT_ROOT/.codex/agents/${name}.toml"
  sandbox_mode="danger-full-access"
  # ADR-09 round 4 — Lens B W3: read-only agents (those declaring
  # `disallowedTools: Write, Edit` in frontmatter) get a `read-only` Codex
  # sandbox so the sandbox enforces the same intent as the disallowedTools hint.
  case "$disallowed_tools" in
    *Write*Edit*|*Edit*Write*)
      sandbox_mode="read-only"
      ;;
  esac
  if [ "$name" = "quality-agent" ]; then
    sandbox_mode="read-only"
  fi

  {
    echo "# GENERATED FILE: edit $src and rerun scripts/generate_codex_derivatives.sh"
    echo "name = \"$name\""
    echo "description = \"$description\""
    echo "sandbox_mode = \"$sandbox_mode\""
    echo 'developer_instructions = """'
    echo "Use \`AGENTS.md\` as the shared runtime contract for startup, workflow, mode classification, hook mirrors, and shared policy."
    echo "Do not duplicate or reinterpret that shared contract here. This file should contain only agent-specific behavior."
    if [ -n "$disallowed_tools" ]; then
      echo "Do not use these tools in this generated Codex mirror: $disallowed_tools."
    fi
    echo
    printf '%s\n' "$developer_instructions"
    echo '"""'
  } > "$out"
}

link_skill_md() {
  local src="$1"
  local rel skill_name live_target staging_target live_link_target staging_link_target
  rel="${src#.claude/skills/}"
  skill_name="$(basename "$(dirname "$src")")"

  # Live .agents/skills/<X>/SKILL.md → ../../../.claude/skills/<X>/SKILL.md
  live_target="$OUTPUT_ROOT/.agents/skills/$rel"
  mkdir -p "$OUTPUT_ROOT/.agents/skills/$skill_name"
  live_link_target="../../../.claude/skills/$skill_name/SKILL.md"
  if [ -e "$live_target" ] && [ ! -L "$live_target" ]; then rm -rf "$live_target"; fi
  if [ ! -L "$live_target" ]; then
    ln -s "$live_link_target" "$live_target"
  fi

  # Staging .codex-sync/staging/.agents/skills/<X>/SKILL.md → ../../../../../.claude/skills/<X>/SKILL.md
  staging_target="$OUTPUT_ROOT/.codex-sync/staging/.agents/skills/$rel"
  mkdir -p "$OUTPUT_ROOT/.codex-sync/staging/.agents/skills/$skill_name"
  staging_link_target="../../../../../.claude/skills/$skill_name/SKILL.md"
  if [ -e "$staging_target" ] && [ ! -L "$staging_target" ]; then rm -rf "$staging_target"; fi
  if [ ! -L "$staging_target" ]; then
    ln -s "$staging_link_target" "$staging_target"
  fi
}

write_manifest_json() {
  local tmp
  tmp="$(mktemp)"
  {
    echo '{'
    echo '  "version": 1,'
    echo '  "strategy": "one-way-claude-to-codex",'
    echo '  "generated_by": "scripts/generate_codex_derivatives.sh",'
    echo '  "notes": "Profiles: core=12 runtime-default skills, full=18 including Starter-derived optional-pack skills.",'
    echo '  "mappings": ['

    local first=1
    append_mapping() {
      local source="$1"
      shift
      local targets_json="$1"
      shift
      local scope="$1"
      shift
      local notes="$1"
      if [ "$first" -eq 0 ]; then
        echo ','
      fi
      first=0
      printf '    {\n'
      printf '      "source": "%s",\n' "$source"
      printf '      "targets": %s,\n' "$targets_json"
      printf '      "change_scope": "%s",\n' "$scope"
      printf '      "sync_policy": "regenerate",\n'
      printf '      "owner": "project-maintainer",\n'
      printf '      "notes": "%s"\n' "$notes"
      printf '    }'
    }

    append_symlink_mapping() {
      local source="$1"
      shift
      local targets_json="$1"
      shift
      local notes="$1"
      if [ "$first" -eq 0 ]; then
        echo ','
      fi
      first=0
      printf '    {\n'
      printf '      "source": "%s",\n' "$source"
      printf '      "targets": %s,\n' "$targets_json"
      printf '      "change_scope": "symlink",\n'
      printf '      "sync_policy": "symlink",\n'
      printf '      "owner": "project-maintainer",\n'
      printf '      "notes": "%s"\n' "$notes"
      printf '    }'
    }

    append_mapping "CLAUDE.md" '["AGENTS.md"]' "content" "Main Codex instructions"

    local src rel name
    while IFS= read -r src; do
      [ -n "$src" ] || continue
      name="$(extract_frontmatter_field "$src" "name")"
      append_mapping "$src" "[\".codex/agents/${name}.toml\"]" "content" "Generated custom agent"
    done < <(printf '%s\n' .claude/agents/*.md | LC_ALL=C sort)

    while IFS= read -r src; do
      [ -n "$src" ] || continue
      rel="${src#.claude/skills/}"
      name="$(basename "$(dirname "$src")")"
      if ! has_selected_skill "$name"; then
        continue
      fi
      append_symlink_mapping "$src" "[\".agents/skills/${rel}\"]" "Symlinked Codex skill (symlink to .claude/skills/${name}/SKILL.md)"
    done < <(printf '%s\n' .claude/skills/*/SKILL.md | LC_ALL=C sort)

    if [ -f ".claude/settings.local.json" ] || [ -f ".claude/settings.json" ] || [ -f ".mcp.json" ]; then
      append_mapping "__CONFIG_SOURCES__" '[".codex/config.toml"]' "config" "Semantic mapping from Claude permissions and MCP settings"
    fi

    # Shared hook lib: peer source (not regenerated); .codex/hooks/lib is a symlink to .claude/hooks/lib.
    append_symlink_mapping ".claude/hooks/lib" '[".codex/hooks/lib"]' "Shared hook policy lib; .codex/hooks/lib symlinks to .claude/hooks/lib (peer source)"

    echo
    echo '  ]'
    echo '}'
  } > "$tmp"

  local config_source_label=""
  local label_sep=""
  if [ -f ".claude/settings.local.json" ]; then
    config_source_label="${config_source_label}${label_sep}.claude\\/settings.local.json"
    label_sep=" + "
  elif [ -f ".claude/settings.json" ]; then
    config_source_label="${config_source_label}${label_sep}.claude\\/settings.json"
    label_sep=" + "
  fi
  if [ -f ".mcp.json" ]; then
    config_source_label="${config_source_label}${label_sep}.mcp.json"
  fi
  perl -0pi -e "s/\"source\": \"__CONFIG_SOURCES__\"/\"source\": \"$config_source_label\"/g" "$tmp"
  mv "$tmp" "$OUTPUT_ROOT/.codex-sync/manifest.json"
}

write_agents_md
write_config_toml

find "$OUTPUT_ROOT/.agents/skills" -mindepth 1 -depth -exec rm -rf {} +
if [ -d "$OUTPUT_ROOT/.codex-sync/staging/.agents/skills" ]; then
  find "$OUTPUT_ROOT/.codex-sync/staging/.agents/skills" -mindepth 1 -depth -exec rm -rf {} +
fi

while IFS= read -r src; do
  [ -n "$src" ] || continue
  name="$(extract_frontmatter_field "$src" "name")"
  write_agent_toml "$src"
done < <(printf '%s\n' .claude/agents/*.md | LC_ALL=C sort)

while IFS= read -r src; do
  [ -n "$src" ] || continue
  name="$(basename "$(dirname "$src")")"
  if ! has_selected_skill "$name"; then
    continue
  fi
  link_skill_md "$src"
done < <(printf '%s\n' .claude/skills/*/SKILL.md | LC_ALL=C sort)

write_manifest_json

echo "Generated Codex derivatives:"
echo "  $OUTPUT_ROOT/AGENTS.md"
echo "  $OUTPUT_ROOT/.codex/config.toml"
echo "  $OUTPUT_ROOT/.codex/hooks.json (PRESERVED — P0-G artifact, not regenerated)"
echo "  $OUTPUT_ROOT/.codex/agents/*.toml"
echo "  $OUTPUT_ROOT/.codex/hooks/*.sh (peer source — not regenerated)"
echo "  $OUTPUT_ROOT/.agents/skills/*/SKILL.md (symlinks to .claude/skills/*/SKILL.md)"
echo "  $OUTPUT_ROOT/.codex-sync/manifest.json"
echo "  profile=$DERIVATION_PROFILE"
