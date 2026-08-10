#!/usr/bin/env bash
set -euo pipefail

export MIR_CODEX_MAIN=1
export MIR_CODEX_SESSION_ID="${MIR_CODEX_SESSION_ID:-loop-driver-$$}"

MAX_ITERS="${MIR_LOOP_MAX_ITERS:-20}"
LOCK_PATH="${MIR_LOOP_LOCK:-tasks/loop.lock}"

mkdir -p "$(dirname "$LOCK_PATH")"
if ! mkdir "$LOCK_PATH" 2>/dev/null; then
  holder="$(cat "$LOCK_PATH/pid" 2>/dev/null || true)"
  if [[ "$holder" =~ ^[0-9]+$ ]] && ! kill -0 "$holder" 2>/dev/null; then
    if [ "$(find "$LOCK_PATH" -mindepth 1 -maxdepth 1 ! -name pid -print -quit 2>/dev/null)" = "" ]; then
      rm -f "$LOCK_PATH/pid"
      rmdir "$LOCK_PATH" 2>/dev/null || true
    fi
    mkdir "$LOCK_PATH" 2>/dev/null || {
      echo "[loop_driver] another loop driver holds $LOCK_PATH" >&2
      exit 2
    }
  else
    echo "[loop_driver] another loop driver holds $LOCK_PATH" >&2
    exit 2
  fi
fi
printf '%s\n' "$$" > "$LOCK_PATH/pid"
cleanup_lock() {
  rm -f "$LOCK_PATH/pid"
  rmdir "$LOCK_PATH" 2>/dev/null || true
}
trap cleanup_lock EXIT
trap 'exit 130' HUP INT TERM

json_field() {
  local payload="$1"
  local field="$2"
  printf '%s' "$payload" | jq -r --arg field "$field" '.[$field] // ""'
}

for ((iter = 1; iter <= MAX_ITERS; iter++)); do
  next_json="$(scripts/mir.sh loop next --json)"
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
          scripts/mir.sh loop mark --step "$step_id" --status BLOCKED \
            --reason missing_machine_refs
        fi
        exit 2
      fi

      if [ -z "$brief" ]; then
        echo "[loop_driver] blocked: missing brief ref for step $step_id" >&2
        scripts/mir.sh loop mark --step "$step_id" --status BLOCKED \
          --reason missing_brief
        exit 2
      fi

      scripts/mir.sh loop mark --step "$step_id" --status IN_PROGRESS

      prompt="Read DispatchBrief $brief and execute exactly one bounded step. Do not edit tasks/plan.md cursor; scripts/loop_driver.sh updates it. Respect all repository hooks and verification gates."
      codex_args="$(printf '%q' "$prompt")"
      verify_cmd="$(
        jq -r --arg id "$change_id" --arg category "$category" '
          ([.changes[]? | select(.id == $id)][0] // .[$id] // {}) as $change
          | $change.categories[$category].command // ""
        ' tasks/tdd.json
      )"

      if [ -z "$verify_cmd" ]; then
        echo "[loop_driver] blocked: missing verification command for $change_id/$category" >&2
        scripts/mir.sh loop mark --step "$step_id" --status BLOCKED \
          --reason missing_verification_command
        exit 2
      fi

      if scripts/mir.sh executor execute --background --dispatch \
        --change-id "$change_id" \
        --category "$category" \
        --repo-root . \
        --codex-args "$codex_args" \
        --allow-path app/ \
        --allow-path apps/ \
        --allow-path packages/ \
        --allow-path pipelines/ \
        --allow-path infra/ \
        --allow-path content/ \
        --allow-path docs/ \
        --allow-path scripts/ \
        --allow-path tests/ \
        --allow-path tasks/tdd.json \
        --verify-cmd "$verify_cmd"; then
        scripts/mir.sh loop mark --step "$step_id" --status DONE
      else
        rc=$?
        scripts/mir.sh loop mark --step "$step_id" --status FAILED \
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
