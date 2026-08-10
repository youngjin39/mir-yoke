#!/usr/bin/env bash
# Run hook Python through the project's managed environment. Never use host Python.

set -euo pipefail

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-${MIR_PROJECT_DIR:-.}}"

_mir_sha256_file() {
  if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | awk '{print $1}'
  elif command -v shasum >/dev/null 2>&1; then shasum -a 256 "$1" | awk '{print $1}'
  else return 1
  fi
}

_MIR_RECEIPT="$PROJECT_DIR/.mir/bootstrap-receipt.json"
if command -v jq >/dev/null 2>&1 && [ -f "$_MIR_RECEIPT" ]; then
  if jq -e '.cli | type == "object"' "$_MIR_RECEIPT" >/dev/null 2>&1; then
    _MIR_EXTERNAL_CLI="$(jq -r '.cli.executable // empty' "$_MIR_RECEIPT" 2>/dev/null)"
    _MIR_EXTERNAL_SHA="$(jq -r '.cli.sha256 // empty' "$_MIR_RECEIPT" 2>/dev/null)"
    if [ -n "$_MIR_EXTERNAL_CLI" ] && [ -x "$_MIR_EXTERNAL_CLI" ] && \
       [ -n "$_MIR_EXTERNAL_SHA" ] && \
       [ "$(_mir_sha256_file "$_MIR_EXTERNAL_CLI" 2>/dev/null || true)" = "$_MIR_EXTERNAL_SHA" ]; then
      if [ -n "$(jq -r '.cli.runtime_manifest // empty' "$_MIR_RECEIPT" 2>/dev/null)" ]; then
        _MIR_RUNTIME_ROOT="$(cd -- "$(dirname -- "$_MIR_EXTERNAL_CLI")/.." 2>/dev/null && pwd -P || true)"
        _MIR_RUNTIME_MANIFEST="$(jq -r '.cli.runtime_manifest // empty' "$_MIR_RECEIPT" 2>/dev/null)"
        _MIR_RUNTIME_MANIFEST_SHA="$(jq -r '.cli.runtime_manifest_sha256 // empty' "$_MIR_RECEIPT" 2>/dev/null)"
        if [ -z "$_MIR_RUNTIME_ROOT" ] || \
           [ "$_MIR_RUNTIME_MANIFEST" != "$_MIR_RUNTIME_ROOT/runtime-manifest.json" ] || \
           [ ! -f "$_MIR_RUNTIME_MANIFEST" ] || [ -L "$_MIR_RUNTIME_MANIFEST" ] || \
           [ "$(_mir_sha256_file "$_MIR_RUNTIME_MANIFEST" 2>/dev/null || true)" != "$_MIR_RUNTIME_MANIFEST_SHA" ] || \
           ! "$_MIR_EXTERNAL_CLI" runtime-manifest verify \
             --runtime-root "$_MIR_RUNTIME_ROOT" \
             --manifest "$_MIR_RUNTIME_MANIFEST" \
             --source-url "$(jq -r '.cli.source_url // empty' "$_MIR_RECEIPT")" \
             --source-commit "$(jq -r '.cli.source_commit // empty' "$_MIR_RECEIPT")" \
             --constraints-sha256 "$(jq -r '.cli.constraints_sha256 // empty' "$_MIR_RECEIPT")" \
             >/dev/null 2>&1; then
          printf '[mir hook] receipt-bound external Mir runtime is invalid; rerun setup.sh (inside WSL on Windows hosts)\n' >&2
          exit 127
        fi
      fi
      exec "$_MIR_EXTERNAL_CLI" run-python --project-root "$PROJECT_DIR" -- "$@"
    fi
    printf '[mir hook] receipt-bound external Mir Python is invalid; rerun setup.sh (inside WSL on Windows hosts)\n' >&2
    exit 127
  fi
fi

# Local Python remains a pre-bootstrap and existing-adoption fallback. A greenfield
# receipt with a CLI contract always takes the hash-bound external path above.
if [ -x "$PROJECT_DIR/.venv/bin/python" ]; then
  exec "$PROJECT_DIR/.venv/bin/python" "$@"
fi

if [ -x "$PROJECT_DIR/.venv/Scripts/python.exe" ]; then
  exec "$PROJECT_DIR/.venv/Scripts/python.exe" "$@"
fi

if command -v uv >/dev/null 2>&1; then
  exec uv run --project "$PROJECT_DIR" python "$@"
fi

printf '[mir hook] external Mir Python unavailable; run setup.sh first (inside WSL on Windows hosts)\n' >&2
exit 127
