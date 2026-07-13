#!/bin/bash
# tier_dispatch.sh — shared tier-routing helper for Mir hooks.
# Usage: source this file, then call emit_tier_result <hook_id> <tier> <msg>
# tier: block | suggest | warn
# For suggest tier: prints guidance and returns 0.
# For warn tier: exits 0, prints to stderr.
# For block tier: exits 2, prints to stderr.
#
# record_suggest_bypass helper writes to tasks/audit/suggest_bypass.jsonl
# _MIR_PROJECT_DIR must be set (or falls back to CLAUDE_PROJECT_DIR or .)

_mir_record_suggest_bypass() {
    local hook_id="$1" reason="$2"
    local proj_dir="${_MIR_PROJECT_DIR:-${CLAUDE_PROJECT_DIR:-.}}"
    local audit_dir="$proj_dir/tasks/audit"
    mkdir -p "$audit_dir"
    local ts
    ts="$(python3 -c 'import datetime; print(datetime.datetime.now(datetime.timezone.utc).isoformat())' 2>/dev/null || date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf '{"ts":"%s","hook_id":"%s","reason":"%s"}\n' "$ts" "$hook_id" "$reason" >> "$audit_dir/suggest_bypass.jsonl"
}

emit_tier_result() {
    local hook_id="$1" tier="$2" msg="$3"
    case "$tier" in
        warn)
            echo "[hook WARN] $hook_id: $msg" >&2
            exit 0
            ;;
        suggest)
            echo "[hook SUGGEST] $hook_id: $msg" >&2
            return 0
            ;;
        block)
            echo "[hook BLOCK] $hook_id: $msg" >&2
            exit 2
            ;;
        *)
            echo "[hook UNKNOWN-TIER] $hook_id tier=$tier: $msg" >&2
            exit 2
            ;;
    esac
}
