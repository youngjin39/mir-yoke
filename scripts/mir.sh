#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
RECEIPT="$ROOT/.mir/bootstrap-receipt.json"

sha256_file() {
  if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | awk '{print $1}'
  elif command -v shasum >/dev/null 2>&1; then shasum -a 256 "$1" | awk '{print $1}'
  else return 1
  fi
}

command -v jq >/dev/null 2>&1 || {
  printf '[mir launcher] jq is required\n' >&2
  exit 127
}
[ -f "$RECEIPT" ] || {
  printf '[mir launcher] bootstrap receipt is missing; run setup.sh (inside WSL on Windows hosts)\n' >&2
  exit 1
}
MIR_CLI="$(jq -r '.cli.executable // empty' "$RECEIPT")"
EXPECTED_HASH="$(jq -r '.cli.sha256 // empty' "$RECEIPT")"
RUNTIME_MANIFEST="$(jq -r '.cli.runtime_manifest // empty' "$RECEIPT")"
[ -n "$MIR_CLI" ] && [ -x "$MIR_CLI" ] || {
  printf '[mir launcher] external Mir CLI is unavailable; rerun setup.sh (inside WSL on Windows hosts)\n' >&2
  exit 1
}
[ -n "$EXPECTED_HASH" ] && [ "$(sha256_file "$MIR_CLI" 2>/dev/null || true)" = "$EXPECTED_HASH" ] || {
  printf '[mir launcher] external Mir CLI hash changed; rerun setup.sh (inside WSL on Windows hosts)\n' >&2
  exit 1
}
verify_runtime() {
  local verifier verifier_hash verdict=64
  verifier="$(jq -r '.cli.runtime_verifier.path // empty' "$RECEIPT")"
  verifier_hash="$(jq -r '.cli.runtime_verifier.sha256 // empty' "$RECEIPT")"
  if [ "${MIR_NATIVE_HOOKS:-1}" != "0" ] && [ -n "$verifier" ] && [ -n "$verifier_hash" ]; then
    [[ "$verifier" = /* ]] || verifier="$ROOT/$verifier"
    if [ -f "$verifier" ] && [ ! -L "$verifier" ] && [ -x "$verifier" ] && \
      [ "$(sha256_file "$verifier" 2>/dev/null || true)" = "$verifier_hash" ]; then
      "$verifier" "$@" >/dev/null 2>&1 && verdict=0 || verdict=$?
      case "$verdict" in
        0) return 0 ;;
        2) return 1 ;; # Same changed-runtime verdict as Python verification.
      esac
    fi
  fi
  "$MIR_CLI" runtime-manifest verify "$@" >/dev/null 2>&1
}
if [ -n "$RUNTIME_MANIFEST" ]; then
  RUNTIME_ROOT="$(cd -- "$(dirname -- "$MIR_CLI")/.." 2>/dev/null && pwd -P || true)"
  RUNTIME_MANIFEST_HASH="$(jq -r '.cli.runtime_manifest_sha256 // empty' "$RECEIPT")"
  [ -n "$RUNTIME_ROOT" ] && [ "$RUNTIME_MANIFEST" = "$RUNTIME_ROOT/runtime-manifest.json" ] && \
    [ -f "$RUNTIME_MANIFEST" ] && [ ! -L "$RUNTIME_MANIFEST" ] && \
    [ "$(sha256_file "$RUNTIME_MANIFEST" 2>/dev/null || true)" = "$RUNTIME_MANIFEST_HASH" ] && \
    verify_runtime --runtime-root "$RUNTIME_ROOT" \
      --manifest "$RUNTIME_MANIFEST" \
      --source-url "$(jq -r '.cli.source_url // empty' "$RECEIPT")" \
      --source-commit "$(jq -r '.cli.source_commit // empty' "$RECEIPT")" \
      --constraints-sha256 "$(jq -r '.cli.constraints_sha256 // empty' "$RECEIPT")" \
      >/dev/null 2>&1 || {
      printf '[mir launcher] external Mir CLI runtime changed; rerun setup.sh (inside WSL on Windows hosts)\n' >&2
      exit 1
    }
fi
exec "$MIR_CLI" "$@"
