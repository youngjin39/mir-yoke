#!/bin/bash
# Derived from the Mir harness reference implementation.
# Attribution: claude-starter (yojini/claude-starter, Apache-2.0)
# Modifications:
#   - Mir-specific manifest path (.codex-sync/manifest.json — same)
#   - Common skills are plugin-owned and never generated as repo-local copies.
#   - Agent TOML mirrors are generated from .claude/agents source.
#   - Claude and Codex hooks render from config/project-hooks.json.
#   - hooks = true added to [features] in write_config_toml

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

value = result.get(key, "")
patterns = {
    "name": re.compile(r"^[a-z][a-z0-9-]*$"),
    "disallowedTools": re.compile(r"^[A-Z][A-Za-z]+(?:,\s*[A-Z][A-Za-z]+)*$"),
}
pattern = patterns.get(key)
if value and pattern is not None and pattern.fullmatch(value) is None:
    print(f"ERROR: {path}: invalid {key} frontmatter value", file=sys.stderr)
    raise SystemExit(2)

sys.stdout.write(value)
PY
}

agent_sources() {
  if [ -f ".mir/repo-profile.toml" ] \
    && grep -Eq '^overlay_archetype = "product_adopter"$' ".mir/repo-profile.toml" \
    && command -v jq >/dev/null 2>&1 \
    && jq -e '.catalog.agents | type == "object"' \
      "config/repo-agent-management.json" >/dev/null 2>&1; then
    jq -r '.catalog.agents[] | .source_path // empty' \
      "config/repo-agent-management.json" | LC_ALL=C sort
    return
  fi
  printf '%s\n' .claude/agents/*.md | LC_ALL=C sort
}

validate_agent_frontmatter_sources() {
  local src
  while IFS= read -r src; do
    [ -n "$src" ] || continue
    extract_frontmatter_field "$src" "name" >/dev/null
    extract_frontmatter_field "$src" "disallowedTools" >/dev/null
  done < <(agent_sources)
}

# Fail before creating or replacing any derivative when patterned agent metadata is invalid.
validate_agent_frontmatter_sources

mkdir -p "$OUTPUT_ROOT/.codex/agents" "$OUTPUT_ROOT/.codex/hooks" "$OUTPUT_ROOT/.codex-sync"
mkdir -p "$OUTPUT_ROOT/.claude/hooks/lib"

# Keep the Codex hook library portable on Windows: generate a real directory copy.
rm -rf -- "$OUTPUT_ROOT/.codex/hooks/lib"
cp -R ".claude/hooks/lib" "$OUTPUT_ROOT/.codex/hooks/lib"

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
        "## Specialist Scope-Pattern Routing (catalog routing ADR)"
        "## Sub-agent dispatch policy"
        "## Post-Dispatch Evidence"
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
    "  - `SessionEnd` saves the latest session snapshot for continuity. This preserves state, not proof of completion.": "  - [Claude] `SessionEnd` saves the latest session snapshot for continuity. This preserves state, not proof of completion. [Codex] The generated trusted SessionEnd hook refreshes the same canonical handoff within the Codex timeout.",
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
  {
    echo "<!-- GENERATED FILE: edit CLAUDE.md and rerun scripts/generate_codex_derivatives.sh -->"
    echo
    body_without_frontmatter CLAUDE.md
  } > "$OUTPUT_ROOT/AGENTS.md"
}

nested_claude_sources() {
  local root
  for root in scripts src starter tests tools; do
    [ -d "$root" ] || continue
    find "$root" -type f -name CLAUDE.md -print
  done | LC_ALL=C sort
}

write_nested_agents_md() {
  local src target
  while IFS= read -r src; do
    [ -n "$src" ] || continue
    target="${src%CLAUDE.md}AGENTS.md"
    mkdir -p "$OUTPUT_ROOT/$(dirname "$target")"
    {
      if [ "$src" = "starter/CLAUDE.md" ]; then
        echo "<!-- Mir Yoke publication derivative. After adoption, this repository owns this file and HARNESS.md remains canonical. -->"
      else
        echo "<!-- GENERATED FILE: edit $src and rerun scripts/generate_codex_derivatives.sh -->"
      fi
      echo
      body_without_frontmatter "$src" | sed 's/CLAUDE\.md/AGENTS.md/g'
    } > "$OUTPUT_ROOT/$target"
  done < <(nested_claude_sources)
}

write_config_toml() {
  {
    echo "# GENERATED FILE: edit scripts/generate_codex_derivatives.sh or .mcp.json and rerun the generator"
    echo
    echo 'web_search = "cached"'
    echo 'personality = "pragmatic"'
    echo 'project_doc_max_bytes = 32768'
    echo
    echo '[features]'
    echo 'hooks = true'
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

write_codex_readme() {
  cat > "$OUTPUT_ROOT/.codex/README.md" <<'EOF'
<!-- GENERATED FILE: edit config/project-hooks.json or scripts/generate_codex_derivatives.sh and regenerate. -->

# Codex runtime

`.codex/hooks.json` is generated from `config/project-hooks.json`. The same definition renders
Claude and Codex registrations, while runtime-specific events and timeout limits remain explicit.

## Trust boundary

Project-local Codex configuration loads only after the project is trusted. Non-managed hooks also
require review of their current hash before they run. Use `/hooks` to inspect sources and trust or
disable each hook. Until both trust steps are complete, hook-based safety and continuity behavior is
inactive; repository instructions and explicit verification remain authoritative.

## Permission boundary

The generated root configuration does not select `approval_policy`.
It does not select `sandbox_mode`, `sandbox_workspace_write`, `default_permissions`, or agent routing defaults.
Operator-owned user or managed configuration remains authoritative for approval, permissions,
default sub-agent models and effort, concurrency, and native collaboration enablement.
Write-capable generated agents inherit that selection; mechanically read-only reviewers retain
`sandbox_mode = "read-only"`.

## Maintained events

`PreToolUse`, `PermissionRequest`, `PostToolUse`, `SessionStart`, `PreCompact`,
`PostCompact`, `Stop`, and `SessionEnd` are generated for Codex. Maintainer `SessionEnd`
uses Codex's three-second limit. `UserPromptSubmit` and `StopFailure` remain Claude-only by
repository policy; the compact-only Project Agent Kit template intentionally ships only its compact
lifecycle.

## Wire format

Shared adapters parse `tool_name` and `tool_input`. Current Codex `apply_patch` sends the
unified patch in `tool_input.command`; maintained adapters accept that field first and retain older
`input`, `patch`, and `content` fallbacks for compatible runtimes.

Regenerate with `scripts/generate_codex_derivatives.sh`. Do not edit generated Codex files directly.
EOF
}

write_hook_configs() {
  local renderer="templates/common-harness/scripts/render-hook-configs.py"
  local definition="config/project-hooks.json"
  if [ ! -f "$renderer" ] || [ ! -f "$definition" ]; then
    return 0
  fi
  uv run python "$renderer" \
    --definition "$definition" \
    --output-root "$OUTPUT_ROOT"
}

write_agent_toml() {
  local src="$1"
  local name description developer_instructions out sandbox_mode disallowed_tools normalized_disallowed_tools
  name="$(extract_frontmatter_field "$src" "name")"
  [ -n "$name" ] || return 0  # skip non-agent sources (e.g. README.md: no name frontmatter)
  description="$(extract_frontmatter_field "$src" "description")"
  developer_instructions="$(
    emit_agent_sections_for_codex "$src" "$name" \
      | escape_toml_multiline
  )"
  disallowed_tools="$(extract_frontmatter_field "$src" "disallowedTools")"
  # ADR-09 round 3 fix: do NOT emit execution_backend to .codex/agents/*.toml.
  # Codex CLI has a strict TOML schema (Rust serde, no #[serde(unknown_fields)])
  # and rejects unknown fields with "Ignoring malformed agent role definition",
  # which causes Codex to discard the entire agent role. execution_backend is
  # Claude-side dispatch metadata and lives only in .claude/agents/*.md frontmatter.
  out="$OUTPUT_ROOT/.codex/agents/${name}.toml"
  sandbox_mode=""
  # ADR-85: read-only agents that declare both exact comma-delimited `Write`
  # and `Edit` tokens get a `read-only` Codex sandbox. Tool-name substrings
  # such as `Writer` and `NotebookEdit` do not grant read-only sandboxing.
  normalized_disallowed_tools="${disallowed_tools//[[:space:]]/}"
  case ",$normalized_disallowed_tools," in
    *,Write,*)
      case ",$normalized_disallowed_tools," in
        *,Edit,*) sandbox_mode="read-only" ;;
      esac
      ;;
  esac
  {
    echo "# GENERATED FILE: edit $src and rerun scripts/generate_codex_derivatives.sh"
    echo "name = \"$name\""
    echo "description = \"$description\""
    if [ -n "$sandbox_mode" ]; then
      echo "sandbox_mode = \"$sandbox_mode\""
    fi
    echo 'developer_instructions = """'
    echo "Use \`AGENTS.md\` as the shared repository contract."
    echo "Apply only the agent-specific behavior below; do not restate the root contract."
    if [ -n "$disallowed_tools" ]; then
      echo "Do not use these tools in this generated Codex mirror: $disallowed_tools."
    fi
    echo
    printf '%s\n' "$developer_instructions"
    echo '"""'
  } > "$out"
}

write_manifest_json() {
  local tmp
  tmp="$(mktemp)"
  {
    echo '{'
    echo '  "version": 1,'
    echo '  "strategy": "one-way-claude-to-codex",'
    echo '  "generated_by": "scripts/generate_codex_derivatives.sh",'
    echo '  "notes": "Common skills are provided once through namespaced plugins; no repo-local skill derivatives.",'
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

    append_mapping "CLAUDE.md" '["AGENTS.md"]' "content" "Main Codex instructions"

    local nested_src nested_target
    while IFS= read -r nested_src; do
      [ -n "$nested_src" ] || continue
      nested_target="${nested_src%CLAUDE.md}AGENTS.md"
      append_mapping "$nested_src" "[\"$nested_target\"]" "content" "Path-scoped Codex instructions"
    done < <(nested_claude_sources)

    local src name
    while IFS= read -r src; do
      [ -n "$src" ] || continue
      name="$(extract_frontmatter_field "$src" "name")"
      [ -n "$name" ] || continue
      append_mapping "$src" "[\".codex/agents/${name}.toml\"]" "content" "Generated custom agent"
    done < <(agent_sources)

    append_mapping "__CONFIG_SOURCES__" '[".codex/config.toml"]' "config" "Generated project-owned Codex options and optional MCP settings"

    if [ -f "config/project-hooks.json" ] && [ -f "templates/common-harness/scripts/render-hook-configs.py" ]; then
      append_mapping "config/project-hooks.json" '[".claude/settings.json", ".codex/hooks.json"]' "config" "Generated dual-runtime hook registrations"
    fi

    append_mapping "scripts/generate_codex_derivatives.sh" '[".codex/README.md"]' "content" "Generated Codex runtime and hook-trust guide"

    append_mapping ".claude/hooks/lib" '[".codex/hooks/lib"]' "directory" "Portable Codex hook library copy"

    echo
    echo '  ]'
    echo '}'
  } > "$tmp"

  local config_source_label="scripts\\/generate_codex_derivatives.sh"
  if [ -f ".mcp.json" ]; then
    config_source_label="${config_source_label} + .mcp.json"
  fi
  perl -0pi -e "s/\"source\": \"__CONFIG_SOURCES__\"/\"source\": \"$config_source_label\"/g" "$tmp"
  mv "$tmp" "$OUTPUT_ROOT/.codex-sync/manifest.json"
}

write_agents_md
write_nested_agents_md
write_config_toml
write_codex_readme
write_hook_configs

# Remove legacy raw skill providers. Common skills now live only under plugins/*/skills.
rm -rf -- "$OUTPUT_ROOT/.agents/skills"
rm -rf -- "$OUTPUT_ROOT/.codex-sync/staging/.agents/skills"

# Agent TOMLs are a complete mirror of the currently selected Claude agent pack.
# Recreate the managed directory so agents removed by a profile switch cannot remain active.
rm -rf -- "$OUTPUT_ROOT/.codex/agents"
mkdir -p "$OUTPUT_ROOT/.codex/agents"

while IFS= read -r src; do
  [ -n "$src" ] || continue
  name="$(extract_frontmatter_field "$src" "name")"
  [ -n "$name" ] || continue
  write_agent_toml "$src"
done < <(agent_sources)

write_manifest_json

echo "Generated Codex derivatives:"
echo "  $OUTPUT_ROOT/AGENTS.md"
echo "  $OUTPUT_ROOT/{scripts,src,tests,tools}/**/AGENTS.md"
echo "  $OUTPUT_ROOT/.codex/config.toml"
echo "  $OUTPUT_ROOT/.codex/README.md"
echo "  $OUTPUT_ROOT/{.claude/settings.json,.codex/hooks.json} (generated from config/project-hooks.json)"
echo "  $OUTPUT_ROOT/.codex/agents/*.toml"
echo "  $OUTPUT_ROOT/.codex/hooks/lib (portable directory copy)"
echo "  $OUTPUT_ROOT/.agents/skills (REMOVED — common skills are plugin-owned)"
echo "  $OUTPUT_ROOT/.codex-sync/staging/.agents/skills (REMOVED)"
echo "  $OUTPUT_ROOT/.codex-sync/manifest.json"
echo "  profile=$DERIVATION_PROFILE"
