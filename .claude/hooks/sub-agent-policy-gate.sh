#!/bin/bash
# Repository-local Agent/Task gate. Consumers may explicitly adopt this launcher.
# Mir Yoke does not deploy it to other repositories.
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"
for _mir_native_gate in "$PROJECT_DIR/.mir/bin/delegation-gate" "$PROJECT_DIR/.mir/bin/delegation-gate.exe"; do
  if [ -f "$_mir_native_gate" ] && [ -x "$_mir_native_gate" ] && [ ! -L "$_mir_native_gate" ]; then
    # Keep stdin attached, including trailing newlines and non-text bytes.
    ( exec "$_mir_native_gate" )
    case "$?" in
      0) exit 0 ;;
      2) exit 2 ;;
    esac
    echo "[mir BLOCKED] native delegation-gate failed to launch or declined; delegation blocked." >&2
    exit 2
  fi
done
echo "[mir BLOCKED] native delegation-gate is missing or invalid; delegation blocked." >&2
exit 2
