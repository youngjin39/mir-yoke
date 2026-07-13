#!/usr/bin/env bash
set -euo pipefail

export MIR_CODEX_MAIN=1
export MIR_CODEX_SESSION_ID="${MIR_CODEX_SESSION_ID:-loop-driver-$$}"

MAX_ITERS="${MIR_LOOP_MAX_ITERS:-20}"
LOCK_PATH="${MIR_LOOP_LOCK:-tasks/loop.lock}"

mkdir -p "$(dirname "$LOCK_PATH")"
exec 9>"$LOCK_PATH"
if ! flock -n 9; then
  echo "[loop_driver] another loop driver holds $LOCK_PATH" >&2
  exit 2
fi

json_field() {
  local payload="$1"
  local field="$2"
  MIR_LOOP_JSON="$payload" uv run python - "$field" <<'PY'
import json
import os
import sys

data = json.loads(os.environ["MIR_LOOP_JSON"])
value = data.get(sys.argv[1])
print("" if value is None else value)
PY
}

for ((iter = 1; iter <= MAX_ITERS; iter++)); do
  next_json="$(uv run mir loop next --json)"
  status="$(json_field "$next_json" status)"

  case "$status" in
    COMPLETE)
      exit 0
      ;;
    BLOCKED)
      echo "[loop_driver] blocked: $(json_field "$next_json" reason)" >&2
      exit 2
      ;;
    FAILED)
      echo "[loop_driver] failed step requires operator or brief revision: $(json_field "$next_json" reason)" >&2
      exit 1
      ;;
    STEP)
      step_id="$(json_field "$next_json" step_id)"
      brief="$(json_field "$next_json" brief)"
      change_id="$(json_field "$next_json" tdd_change_id)"
      category="$(json_field "$next_json" tdd_category)"

      if [ -z "$step_id" ] || [ -z "$change_id" ] || [ -z "$category" ]; then
        echo "[loop_driver] blocked: missing step tdd refs in $next_json" >&2
        if [ -n "$step_id" ]; then
          uv run mir loop mark --step "$step_id" --status BLOCKED \
            --reason missing_machine_refs
        fi
        exit 2
      fi

      if [ -z "$brief" ]; then
        echo "[loop_driver] blocked: missing brief ref for step $step_id" >&2
        uv run mir loop mark --step "$step_id" --status BLOCKED \
          --reason missing_brief
        exit 2
      fi

      uv run mir loop mark --step "$step_id" --status IN_PROGRESS

      prompt="Read DispatchBrief $brief and execute exactly one bounded step. Do not edit tasks/plan.md cursor; scripts/loop_driver.sh updates it. Respect all repository hooks and verification gates."
      codex_args="$(printf '%q' "$prompt")"
      verify_cmd="$(
        TDD_CHANGE_ID="$change_id" TDD_CATEGORY="$category" uv run python - <<'PY'
import json
import os
from pathlib import Path

data = json.loads(Path("tasks/tdd.json").read_text(encoding="utf-8"))
change = {}
if isinstance(data, dict):
    for candidate in data.get("changes", []):
        if isinstance(candidate, dict) and candidate.get("id") == os.environ["TDD_CHANGE_ID"]:
            change = candidate
            break
    if not change:
        candidate = data.get(os.environ["TDD_CHANGE_ID"], {})
        change = candidate if isinstance(candidate, dict) else {}
categories = change.get("categories", {}) if isinstance(change, dict) else {}
category = categories.get(os.environ["TDD_CATEGORY"], {})
command = category.get("command", "") if isinstance(category, dict) else ""
print(command or "uv run ruff check")
PY
      )"

      if uv run python -m tools.mir_executor execute --background --dispatch \
        --change-id "$change_id" \
        --category "$category" \
        --repo-root . \
        --codex-args "$codex_args" \
        --allow-path tools/ \
        --allow-path src/ \
        --allow-path scripts/ \
        --allow-path tests/ \
        --allow-path tasks/tdd.json \
        --verify-cmd "$verify_cmd"; then
        uv run mir loop mark --step "$step_id" --status DONE
      else
        rc=$?
        uv run mir loop mark --step "$step_id" --status FAILED \
          --reason "executor_rc=$rc"
        exit "$rc"
      fi
      ;;
    *)
      echo "[loop_driver] unknown status: $status" >&2
      exit 2
      ;;
  esac
done

echo "[loop_driver] blocked: max iterations reached ($MAX_ITERS)" >&2
exit 2
