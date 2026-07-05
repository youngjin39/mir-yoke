#!/usr/bin/env sh
# codex-shim.sh — ADR-59 L1 chokepoint.
#
# Every codex invocation routes through this shim so NO call escapes a
# monitorable lifecycle record.  The shim:
#   1. Captures start time, pid, caller.
#   2. Rejects raw `codex exec` per ADR-69.
#   3. Runs the REAL codex binary (CODEX_REAL_BIN — never resolves "codex"
#      via PATH to avoid recursion) for supported MCP/non-exec subcommands.
#   4. Appends one bounded JSON event line to tasks/codex-exec-events.jsonl.
#   5. Exits with the real codex exit code or the ADR-69 block code.
#
# Activation (set in harness env or .env):
#   export CODEX_REAL_BIN="<path-to-codex>"
#   export CODEX_BIN="$(pwd)/scripts/codex-shim.sh"          # routes MirExecutor
#   PATH="$(pwd)/scripts/codex-shim-dir:$PATH"               # routes shutil.which
#
# MCP-backed clients honor CODEX_BIN when a shimmed Codex binary is required.
# See ADR-59 §5.1 for the full wiring rationale.
set -eu

# ---------------------------------------------------------------------------
# Guard: refuse to run without CODEX_REAL_BIN so the shim never silently
# loops back to itself via PATH.
# ---------------------------------------------------------------------------
if [ -z "${CODEX_REAL_BIN:-}" ]; then
    printf '[codex-shim] CODEX_REAL_BIN is not set — cannot resolve the real codex binary.\n' >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Collect start metadata.
# ---------------------------------------------------------------------------
_SHIM_START_EPOCH="$(date +%s 2>/dev/null || echo 0)"
_SHIM_PID="$$"
_SHIM_CALLER="${MIR_CODEX_CALLER:-unknown}"

_json_escape_string() {
    printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g' | tr -d '\n\r\t'
}

# Locate the events file (repo-relative: tasks/codex-exec-events.jsonl).
# Prefer CODEX_EVENTS_FILE env override for tests; fall back to repo-relative.
if [ -n "${CODEX_EVENTS_FILE:-}" ]; then
    _EVENTS_FILE="$CODEX_EVENTS_FILE"
else
    # Walk up from the shim's own location to find the repo root (has tasks/).
    _SHIM_DIR="$(cd -- "$(dirname -- "$0")" && pwd)"
    _REPO_ROOT="$(dirname -- "$_SHIM_DIR")"
    _EVENTS_FILE="$_REPO_ROOT/tasks/codex-exec-events.jsonl"
fi

# Create the file if absent (append-only).
if [ ! -f "$_EVENTS_FILE" ]; then
    mkdir -p "$(dirname -- "$_EVENTS_FILE")"
    touch "$_EVENTS_FILE"
fi

# ---------------------------------------------------------------------------
# Run the real codex binary for supported subcommands.
# Raw `codex exec` is banned by ADR-69; MCP-backed clients use `mcp-server codex`.
# NEVER resolve "codex" via PATH here — use CODEX_REAL_BIN only.
# ---------------------------------------------------------------------------
# Capture stderr to a temp file so we can compute error_sig after exit.
_STDERR_TMP="$(mktemp /tmp/codex-shim-stderr.XXXXXX)"

_SHIM_EXIT=0
case "${1:-}" in
  exec|e)
    printf '[codex-shim] ADR-69: raw codex exec is banned; use Codex MCP or mir_executor --dispatch.\n' >"$_STDERR_TMP"
    _SHIM_EXIT=2
    ;;
  *)
    "$CODEX_REAL_BIN" "$@" 2>"$_STDERR_TMP" || _SHIM_EXIT=$?
    ;;
esac

# Derive signal name if exit code > 128 (shell convention: 128+signum).
_SHIM_SIGNAL=""
if [ "$_SHIM_EXIT" -gt 128 ] 2>/dev/null; then
    _SIGNUM=$(( _SHIM_EXIT - 128 ))
    _SHIM_SIGNAL="SIG${_SIGNUM}"
fi

# Duration in whole seconds.
_SHIM_END_EPOCH="$(date +%s 2>/dev/null || echo 0)"
_SHIM_DURATION=$(( _SHIM_END_EPOCH - _SHIM_START_EPOCH ))

# error_sig: first 12 hex chars of sha256 over the last 20 lines of stderr.
# Use shasum (macOS) or sha256sum (Linux); fallback to empty string.
_ERROR_SIG=""
if [ -s "$_STDERR_TMP" ]; then
    _STDERR_TAIL="$(tail -n 20 "$_STDERR_TMP")"
    if command -v shasum >/dev/null 2>&1; then
        _ERROR_SIG="$(printf '%s' "$_STDERR_TAIL" | shasum -a 256 | cut -c1-12)"
    elif command -v sha256sum >/dev/null 2>&1; then
        _ERROR_SIG="$(printf '%s' "$_STDERR_TAIL" | sha256sum | cut -c1-12)"
    fi
fi

# ISO-8601 timestamp (seconds precision, POSIX-safe).
_TS="$(date -u '+%Y-%m-%dT%H:%M:%SZ' 2>/dev/null || echo '')"
_SHIM_CALLER_ESC="$(_json_escape_string "$_SHIM_CALLER")"
_ERROR_SIG_ESC="$(_json_escape_string "$_ERROR_SIG")"

# ---------------------------------------------------------------------------
# Append ONE JSON event line (append-only; no cursor; boundary D).
# Field order: ts, pid, caller, exit_code, signal, duration_s, error_sig.
# Pure POSIX printf — no jq dependency.
# ---------------------------------------------------------------------------
printf '{"ts":"%s","pid":%s,"caller":"%s","exit_code":%s,"signal":"%s","duration_s":%s,"error_sig":"%s"}\n' \
    "$_TS" \
    "$_SHIM_PID" \
    "$_SHIM_CALLER_ESC" \
    "$_SHIM_EXIT" \
    "$_SHIM_SIGNAL" \
    "$_SHIM_DURATION" \
    "$_ERROR_SIG_ESC" \
    >> "$_EVENTS_FILE"

# Clean up stderr temp file.
rm -f "$_STDERR_TMP"

# Preserve real codex exit code.
exit "$_SHIM_EXIT"
