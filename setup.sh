#!/usr/bin/env bash
# Thin macOS/Linux/WSL wrapper. The Python coordinator owns bootstrap logic.

set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"

say() { printf '%s\n' "$*"; }
die() { printf '[ERROR] %s\n' "$*" >&2; exit 1; }
sha256_file() {
  if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | awk '{print $1}'
  elif command -v shasum >/dev/null 2>&1; then shasum -a 256 "$1" | awk '{print $1}'
  else return 1
  fi
}
sha256_text() {
  if command -v sha256sum >/dev/null 2>&1; then sha256sum | awk '{print $1}'
  elif command -v shasum >/dev/null 2>&1; then shasum -a 256 | awk '{print $1}'
  else return 1
  fi
}
normalize_git_url() {
  printf '%s' "$1" \
    | sed -E 's#^[A-Za-z]+://##; s#^[^@/]+@##; s#^([^/]+):(22|443)/#\1/#; s#^([^/:]+):#\1/#; s#\.git/?$##; s#/*$##' \
    | tr '[:upper:]' '[:lower:]'
}
canonical_path() {
  local candidate="$1" suffix="" parent leaf
  case "/$candidate/" in
    */../*) return 1 ;;
  esac
  [[ "$candidate" == /* ]] || candidate="$PWD/$candidate"
  while [[ ! -d "$candidate" ]]; do
    leaf="$(basename -- "$candidate")"
    parent="$(dirname -- "$candidate")"
    [[ "$parent" != "$candidate" ]] || return 1
    suffix="/$leaf$suffix"
    candidate="$parent"
  done
  printf '%s%s\n' "$(cd -- "$candidate" && pwd -P)" "$suffix"
}
require_external_path() {
  local label="$1" candidate
  candidate="$(canonical_path "$2")" || die "$label cannot be resolved: $2"
  case "$candidate" in
    "$ROOT"|"$ROOT"/*) die "$label must be outside the project: $candidate" ;;
  esac
  printf '%s\n' "$candidate"
}

PLATFORM_NAME="$(uname -s 2>/dev/null || printf 'unknown')"
case "$PLATFORM_NAME" in
  Darwin|Linux) ;;
  MINGW*|MSYS*|CYGWIN*)
    die "Native Windows automated bootstrap is unsupported. Run setup.sh inside WSL, or use agent-guided existing-repository/reference adaptation."
    ;;
  *)
    die "Automated bootstrap supports macOS, Linux, and WSL; detected $PLATFORM_NAME."
    ;;
esac

STORAGE_ROOT=""
STORAGE_ROOT_PROVIDED=false
EXPECT_STORAGE_ROOT=false
for arg in "$@"; do
  if "$EXPECT_STORAGE_ROOT"; then
    STORAGE_ROOT="$arg"
    EXPECT_STORAGE_ROOT=false
    continue
  fi
  case "$arg" in
    --storage-root)
      STORAGE_ROOT_PROVIDED=true
      EXPECT_STORAGE_ROOT=true
      ;;
    --storage-root=*)
      STORAGE_ROOT_PROVIDED=true
      STORAGE_ROOT="${arg#--storage-root=}"
      ;;
  esac
done
"$EXPECT_STORAGE_ROOT" && die "--storage-root requires a path"
if "$STORAGE_ROOT_PROVIDED" && [[ -z "$STORAGE_ROOT" ]]; then
  die "--storage-root requires a non-empty path"
fi
if [[ -n "$STORAGE_ROOT" ]]; then
  STORAGE_ROOT="$(require_external_path "external storage root" "$STORAGE_ROOT")"
fi

configure_external_storage() {
  local runtime_id="$1"
  mkdir -p -- \
    "$STORAGE_ROOT/uv/cache" \
    "$STORAGE_ROOT/uv/python" \
    "$STORAGE_ROOT/mir/capabilities" \
    "$STORAGE_ROOT/mir/cli/$runtime_id/tools" \
    "$STORAGE_ROOT/mir/cli/$runtime_id/bin"
  STORAGE_ROOT="$(cd -- "$STORAGE_ROOT" && pwd -P)"
  export UV_CACHE_DIR="$STORAGE_ROOT/uv/cache"
  export UV_PYTHON_INSTALL_DIR="$STORAGE_ROOT/uv/python"
  export MIR_CAPABILITY_HOME="$STORAGE_ROOT/mir/capabilities"
  export UV_PROJECT_ENVIRONMENT="$ROOT/.venv"
  RUNTIME_ROOT="$STORAGE_ROOT/mir/cli/$runtime_id"
  export UV_TOOL_DIR="$RUNTIME_ROOT/tools"
  export UV_TOOL_BIN_DIR="$RUNTIME_ROOT/bin"
  say "external-first storage ▸ root=$STORAGE_ROOT"
}

say "mir-yoke setup ▸ root=$ROOT"
command -v jq >/dev/null 2>&1 || die "jq is required to resolve the pinned Mir CLI"
command -v git >/dev/null 2>&1 || die "git is required to verify product source-control ownership"

CONFIG_SOURCE_URL="$(jq -r '.source.url // empty' "$ROOT/config/capability-sources.json" 2>/dev/null || true)"
SOURCE_URL_HINT="$CONFIG_SOURCE_URL"
if [[ -z "$SOURCE_URL_HINT" ]]; then
  SOURCE_URL_HINT="$(jq -r '.source.url // empty' "$ROOT/.mir/capability-lock.json" 2>/dev/null || true)"
fi
if [[ -n "$SOURCE_URL_HINT" ]]; then
  PROVIDER_ID="$(normalize_git_url "$SOURCE_URL_HINT")"
  while IFS= read -r REMOTE_NAME; do
    [[ -n "$REMOTE_NAME" ]] || continue
    while IFS= read -r PUSH_URL; do
      [[ -n "$PUSH_URL" ]] || continue
      if [[ "$(normalize_git_url "$PUSH_URL")" == "$PROVIDER_ID" ]]; then
        die "Git push remote '$REMOTE_NAME' still targets the Mir Yoke provider. Rename it (for example: git remote rename origin mir-yoke-upstream), disable provider pushes (git remote set-url --push mir-yoke-upstream DISABLED), then optionally add a product-owned origin."
      fi
    done < <(git -C "$ROOT" remote get-url --push --all "$REMOTE_NAME" 2>/dev/null || true)
  done < <(git -C "$ROOT" remote 2>/dev/null || true)
fi

MIR_CLI=""
if [[ -f "$ROOT/.mir/bootstrap-receipt.json" ]]; then
  RECEIPT_CLI="$(jq -r '.cli.executable // empty' "$ROOT/.mir/bootstrap-receipt.json" 2>/dev/null || true)"
  RECEIPT_CLI_HASH="$(jq -r '.cli.sha256 // empty' "$ROOT/.mir/bootstrap-receipt.json" 2>/dev/null || true)"
  if [[ -n "$RECEIPT_CLI" && -x "$RECEIPT_CLI" && "$RECEIPT_CLI" != "$ROOT"/* ]]; then
    ACTUAL_CLI_HASH="$(sha256_file "$RECEIPT_CLI" || true)"
    if [[ -n "$RECEIPT_CLI_HASH" && "$ACTUAL_CLI_HASH" == "$RECEIPT_CLI_HASH" ]]; then
      RECEIPT_RUNTIME_ID="$(jq -r '.cli.runtime_id // empty' "$ROOT/.mir/bootstrap-receipt.json")"
      export MIR_BOOTSTRAP_SOURCE_URL="$(jq -r '.cli.source_url // empty' "$ROOT/.mir/bootstrap-receipt.json")"
      export MIR_BOOTSTRAP_SOURCE_COMMIT="$(jq -r '.cli.source_commit // empty' "$ROOT/.mir/bootstrap-receipt.json")"
      export MIR_BOOTSTRAP_SOURCE_LOCK_SHA256="$(jq -r '.cli.source_lock_sha256 // empty' "$ROOT/.mir/bootstrap-receipt.json")"
      export MIR_BOOTSTRAP_CONSTRAINTS_SHA256="$(jq -r '.cli.constraints_sha256 // empty' "$ROOT/.mir/bootstrap-receipt.json")"
      RECEIPT_RUNTIME_MANIFEST="$(jq -r '.cli.runtime_manifest // empty' "$ROOT/.mir/bootstrap-receipt.json")"
      RECEIPT_RUNTIME_MANIFEST_SHA256="$(jq -r '.cli.runtime_manifest_sha256 // empty' "$ROOT/.mir/bootstrap-receipt.json")"
      CURRENT_SOURCE_URL="$(jq -r '.source.url // empty' "$ROOT/.mir/capability-lock.json" 2>/dev/null || true)"
      CURRENT_SOURCE_COMMIT="$(jq -r '.source.commit // empty' "$ROOT/.mir/capability-lock.json" 2>/dev/null || true)"
      CURRENT_CONSTRAINTS_SHA256="$(sha256_file "$ROOT/config/cli-runtime-constraints.txt" 2>/dev/null || true)"
      EXPECTED_RUNTIME_ID="$(printf '%s\n%s\n%s\n' "$ROOT" "$CURRENT_SOURCE_URL" "$CURRENT_SOURCE_COMMIT" | sha256_text 2>/dev/null || true)"
      EXPECTED_RUNTIME_ID="${EXPECTED_RUNTIME_ID:0:24}"
      if [[ -n "$EXPECTED_RUNTIME_ID" \
        && "$RECEIPT_RUNTIME_ID" == "$EXPECTED_RUNTIME_ID" \
        && -n "$MIR_BOOTSTRAP_SOURCE_URL" \
        && -n "$CONFIG_SOURCE_URL" \
        && "$(normalize_git_url "$CURRENT_SOURCE_URL")" == "$(normalize_git_url "$CONFIG_SOURCE_URL")" \
        && "$(normalize_git_url "$CURRENT_SOURCE_URL")" == "$(normalize_git_url "$MIR_BOOTSTRAP_SOURCE_URL")" \
        && "$CURRENT_SOURCE_COMMIT" == "$MIR_BOOTSTRAP_SOURCE_COMMIT" \
        && "$CURRENT_CONSTRAINTS_SHA256" == "$MIR_BOOTSTRAP_CONSTRAINTS_SHA256" ]]; then
        if [[ -n "$STORAGE_ROOT" ]]; then
          EXPECTED_RUNTIME_ROOT="$STORAGE_ROOT/mir/cli/$EXPECTED_RUNTIME_ID"
        else
          DATA_HOME="${XDG_DATA_HOME:-${HOME:?HOME is required}/.local/share}"
          DATA_HOME="$(require_external_path "host-default Mir runtime" "$DATA_HOME")"
          EXPECTED_RUNTIME_ROOT="$DATA_HOME/mir-yoke/cli/$EXPECTED_RUNTIME_ID"
        fi
        if [[ "$RECEIPT_CLI" == "$EXPECTED_RUNTIME_ROOT/bin/mir" \
          && "$RECEIPT_RUNTIME_MANIFEST" == "$EXPECTED_RUNTIME_ROOT/runtime-manifest.json" \
          && -f "$RECEIPT_RUNTIME_MANIFEST" \
          && "$(sha256_file "$RECEIPT_RUNTIME_MANIFEST" 2>/dev/null || true)" == "$RECEIPT_RUNTIME_MANIFEST_SHA256" ]]; then
          if "$RECEIPT_CLI" runtime-manifest verify \
            --runtime-root "$EXPECTED_RUNTIME_ROOT" \
            --manifest "$RECEIPT_RUNTIME_MANIFEST" \
            --source-url "$CURRENT_SOURCE_URL" \
            --source-commit "$CURRENT_SOURCE_COMMIT" \
            --constraints-sha256 "$CURRENT_CONSTRAINTS_SHA256" >/dev/null 2>&1; then
            MIR_CLI="$RECEIPT_CLI"
            export MIR_BOOTSTRAP_RUNTIME_ID="$EXPECTED_RUNTIME_ID"
            export MIR_BOOTSTRAP_RUNTIME_MANIFEST="$RECEIPT_RUNTIME_MANIFEST"
            export MIR_BOOTSTRAP_RUNTIME_MANIFEST_SHA256="$RECEIPT_RUNTIME_MANIFEST_SHA256"
          fi
        fi
      fi
      if [[ -n "$MIR_CLI" && -n "$STORAGE_ROOT" ]]; then
        configure_external_storage "$MIR_BOOTSTRAP_RUNTIME_ID"
      fi
      [[ -z "$MIR_CLI" ]] || say "reusing receipt-bound external Mir CLI"
    fi
  fi
fi

if [[ -z "$MIR_CLI" ]]; then
  command -v uv >/dev/null 2>&1 || die "uv is required: https://docs.astral.sh/uv/"
  SOURCE_URL="$(jq -er '.source.url' "$ROOT/.mir/capability-lock.json")" \
    || die "cannot read the tracked Mir CLI source URL from .mir/capability-lock.json"
  SOURCE_COMMIT="$(jq -er '.source.commit' "$ROOT/.mir/capability-lock.json")" \
    || die "cannot read the tracked Mir CLI commit from .mir/capability-lock.json"
  [[ "$SOURCE_URL" == https://* ]] || die "Mir CLI source must use HTTPS"
  [[ "$SOURCE_URL" != *"@"* ]] || die "Mir CLI source must not contain credentials"
  [[ -n "$CONFIG_SOURCE_URL" ]] \
    || die "cannot read the canonical Mir CLI source from config/capability-sources.json"
  [[ "$SOURCE_URL" == "$CONFIG_SOURCE_URL" ]] \
    || die "tracked Mir CLI source conflicts with config/capability-sources.json"
  [[ "$SOURCE_COMMIT" =~ ^[0-9a-fA-F]{40,64}$ ]] \
    || die "Mir CLI source commit is invalid"
  [[ -f "$ROOT/config/cli-runtime-constraints.txt" ]] \
    || die "tracked Mir CLI dependency constraints are missing"
  TOOL_SOURCE="git+$SOURCE_URL@$SOURCE_COMMIT"
  RUNTIME_ID="$(printf '%s\n%s\n%s\n' "$ROOT" "$SOURCE_URL" "$SOURCE_COMMIT" | sha256_text)"
  [[ -n "$RUNTIME_ID" ]] || die "sha256sum or shasum is required to isolate the Mir CLI runtime"
  RUNTIME_ID="${RUNTIME_ID:0:24}"
  if [[ -n "$STORAGE_ROOT" ]]; then
    configure_external_storage "$RUNTIME_ID"
  else
    DATA_HOME="${XDG_DATA_HOME:-${HOME:?HOME is required}/.local/share}"
    DATA_HOME="$(require_external_path "host-default Mir runtime" "$DATA_HOME")"
    RUNTIME_ROOT="$DATA_HOME/mir-yoke/cli/$RUNTIME_ID"
    mkdir -p -- "$RUNTIME_ROOT/tools" "$RUNTIME_ROOT/bin"
  fi
  export UV_TOOL_DIR="$RUNTIME_ROOT/tools"
  export UV_TOOL_BIN_DIR="$RUNTIME_ROOT/bin"
  export UV_PROJECT_ENVIRONMENT="$ROOT/.venv"
  say "installing copied Mir CLI outside the project"
  uv tool install --force --link-mode copy \
    --constraints "$ROOT/config/cli-runtime-constraints.txt" "$TOOL_SOURCE"
  MIR_TOOL_BIN="$(uv tool dir --bin)"
  MIR_CLI="$MIR_TOOL_BIN/mir"
  [[ "$MIR_CLI" == "$RUNTIME_ROOT/bin/mir" ]] \
    || die "uv installed the Mir CLI outside the project-specific runtime: $MIR_CLI"
  export MIR_BOOTSTRAP_RUNTIME_ID="$RUNTIME_ID"
  export MIR_BOOTSTRAP_SOURCE_URL="$SOURCE_URL"
  export MIR_BOOTSTRAP_SOURCE_COMMIT="$SOURCE_COMMIT"
  export MIR_BOOTSTRAP_SOURCE_LOCK_SHA256="$(sha256_file "$ROOT/.mir/capability-lock.json")"
  export MIR_BOOTSTRAP_CONSTRAINTS_SHA256="$(sha256_file "$ROOT/config/cli-runtime-constraints.txt")"
  RUNTIME_MANIFEST="$RUNTIME_ROOT/runtime-manifest.json"
  "$MIR_CLI" runtime-manifest create \
    --runtime-root "$RUNTIME_ROOT" \
    --manifest "$RUNTIME_MANIFEST" \
    --source-url "$SOURCE_URL" \
    --source-commit "$SOURCE_COMMIT" \
    --constraints-sha256 "$MIR_BOOTSTRAP_CONSTRAINTS_SHA256" >/dev/null
  [[ -f "$RUNTIME_MANIFEST" ]] || die "installed Mir CLI did not create its runtime manifest"
  export MIR_BOOTSTRAP_RUNTIME_MANIFEST="$RUNTIME_MANIFEST"
  export MIR_BOOTSTRAP_RUNTIME_MANIFEST_SHA256="$(sha256_file "$RUNTIME_MANIFEST")"
fi
[[ -x "$MIR_CLI" ]] || die "installed Mir CLI is unavailable: $MIR_CLI"
export MIR_BOOTSTRAP_CLI_PATH="$MIR_CLI"

say "running portable bootstrap coordinator"
"$MIR_CLI" bootstrap --project-root "$ROOT" "$@"
