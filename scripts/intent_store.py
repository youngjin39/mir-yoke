from __future__ import annotations

import argparse
import json
from pathlib import Path

HISTORY_LIMIT = 3


def _normalize_history(history: object) -> list[dict]:
    if not isinstance(history, list):
        return []
    normalized: list[dict] = []
    for item in history:
        if not isinstance(item, dict):
            continue
        entry = dict(item)
        if entry.get("completed") is not True and not entry.get("status"):
            entry["status"] = "superseded"
        normalized.append(entry)
    return normalized


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _append_archive(path: Path, entries: list[dict]) -> None:
    if not entries:
        return
    payload: dict = {"history": []}
    if path.exists():
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            payload = loaded
    existing = _normalize_history(payload.get("history"))
    for entry in entries:
        if entry not in existing:
            existing.append(entry)
    payload["history"] = existing
    _write_json(path, payload)


def compact_intent_file(path: str | Path) -> dict:
    """Keep recent intent history and archive older resolved entries."""
    intent_path = Path(path)
    intent = json.loads(intent_path.read_text(encoding="utf-8"))
    if not isinstance(intent, dict):
        raise ValueError("intent JSON must be an object")
    history = _normalize_history(intent.get("history"))
    archived = history[:-HISTORY_LIMIT] if len(history) > HISTORY_LIMIT else []
    intent["history"] = history[-HISTORY_LIMIT:]
    _append_archive(intent_path.parent / "archive" / "intent-history.json", archived)
    _write_json(intent_path, intent)
    return intent


def append_goal(intent: dict, new_goal: str, updated: str) -> dict:
    """Return a new intent dict without silently overwriting the prior goal."""
    next_intent = dict(intent)
    history = _normalize_history(intent.get("history"))
    current_goal = str(intent.get("goal") or "").strip()
    next_intent["history"] = history
    if current_goal:
        next_intent["history"] = [
            *history,
            {
                "goal": intent.get("goal"),
                "updated": intent.get("updated"),
                "status": "superseded",
            },
        ]
    next_intent["goal"] = new_goal
    next_intent["updated"] = updated
    return next_intent


def set_goal(path: str | Path, new_goal: str, updated: str) -> dict:
    intent_path = Path(path)
    intent = json.loads(intent_path.read_text(encoding="utf-8"))
    if not isinstance(intent, dict):
        raise ValueError("intent JSON must be an object")
    _write_json(intent_path, append_goal(intent, new_goal, updated))
    return compact_intent_file(intent_path)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Update the current session intent goal.")
    parser.add_argument("path", nargs="?", default="tasks/intent.json")
    parser.add_argument("--goal", required=True)
    parser.add_argument("--updated", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    set_goal(args.path, args.goal, args.updated)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
