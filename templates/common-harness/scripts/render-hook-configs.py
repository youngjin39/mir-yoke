#!/usr/bin/env python3
"""Render Claude and Codex hook registrations from one project definition."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any

DEFAULT_DEFINITION = Path("harness/project-hooks.json")
OUTPUT_PATHS = {
    "claude": Path(".claude/settings.json"),
    "codex": Path(".codex/hooks.json"),
}
RUNTIMES = frozenset(OUTPUT_PATHS)


class HookDefinitionError(ValueError):
    """The canonical hook definition is not renderable."""


def _load_definition(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        raise HookDefinitionError("schema_version must be 1")
    events = payload.get("events")
    if not isinstance(events, dict) or not events:
        raise HookDefinitionError("events must be a non-empty object")
    return payload


def _command(script: str, runtime: str) -> str:
    if runtime == "claude":
        return f'bash "${{CLAUDE_PROJECT_DIR}}/{script}"'
    return (
        'project_root="$(git rev-parse --show-toplevel)" && '
        f'CLAUDE_PROJECT_DIR="$project_root" bash "$project_root/{script}"'
    )


def _render_group(group: dict[str, Any], runtime: str) -> dict[str, Any] | None:
    declared_runtimes = group.get("runtimes")
    if not isinstance(declared_runtimes, list) or not declared_runtimes:
        raise HookDefinitionError("every hook group must declare runtimes")
    if not set(declared_runtimes) <= RUNTIMES:
        raise HookDefinitionError("hook group declares an unsupported runtime")
    if runtime not in declared_runtimes:
        return None

    hooks = group.get("hooks")
    if not isinstance(hooks, list) or not hooks:
        raise HookDefinitionError("every hook group must contain hooks")
    rendered_hooks: list[dict[str, Any]] = []
    for hook in hooks:
        script = hook.get("script")
        timeout = hook.get("timeout")
        timeout_overrides = hook.get("timeout_overrides", {})
        status = hook.get("statusMessage")
        script_path = PurePosixPath(script) if isinstance(script, str) else None
        if (
            script_path is None
            or not script.startswith(".claude/hooks/")
            or script_path.as_posix() != script
            or ".." in script_path.parts
        ):
            raise HookDefinitionError("hook script must be below .claude/hooks/")
        if type(timeout) is not int or timeout <= 0:
            raise HookDefinitionError("hook timeout must be a positive integer")
        if not isinstance(timeout_overrides, dict) or not set(timeout_overrides) <= RUNTIMES:
            raise HookDefinitionError("hook timeout_overrides must use supported runtime keys")
        if not all(
            type(value) is int and value > 0 for value in timeout_overrides.values()
        ):
            raise HookDefinitionError("hook timeout override must be a positive integer")
        if not isinstance(status, str) or not status:
            raise HookDefinitionError("hook statusMessage must be non-empty")
        runtime_timeout = timeout_overrides.get(runtime, timeout)
        rendered_hooks.append(
            {
                "type": "command",
                "command": _command(script, runtime),
                "timeout": runtime_timeout,
                "statusMessage": status,
            }
        )

    rendered: dict[str, Any] = {"hooks": rendered_hooks}
    matcher = group.get("matcher")
    if matcher is not None:
        if not isinstance(matcher, str) or not matcher:
            raise HookDefinitionError("matcher must be a non-empty string")
        rendered = {"matcher": matcher, **rendered}
    return rendered


def render_hooks(definition: dict[str, Any], runtime: str) -> dict[str, Any]:
    """Return one runtime hook configuration."""
    if runtime not in RUNTIMES:
        raise HookDefinitionError(f"unsupported runtime: {runtime}")
    rendered_events: dict[str, list[dict[str, Any]]] = {}
    for event, groups in definition["events"].items():
        if not isinstance(event, str) or not event:
            raise HookDefinitionError("event names must be non-empty strings")
        if not isinstance(groups, list) or not groups:
            raise HookDefinitionError(f"event {event} must contain hook groups")
        rendered_groups = [
            rendered
            for group in groups
            if (rendered := _render_group(group, runtime)) is not None
        ]
        if rendered_groups:
            rendered_events[event] = rendered_groups

    payload: dict[str, Any] = {"hooks": rendered_events}
    if runtime == "codex" and definition.get("codex_notes"):
        notes = definition["codex_notes"]
        if not isinstance(notes, list) or not all(isinstance(item, str) for item in notes):
            raise HookDefinitionError("codex_notes must be an array of strings")
        payload = {"//": notes, **payload}
    return payload


def _serialized(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def _atomic_write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.close(descriptor)
        temp_path = Path(temp_name)
        temp_path.write_text(body, encoding="utf-8")
        os.replace(temp_path, path)
    finally:
        Path(temp_name).unlink(missing_ok=True)


def _check(outputs: dict[Path, str]) -> int:
    drift = [
        path
        for path, body in outputs.items()
        if not path.is_file() or path.read_text(encoding="utf-8") != body
    ]
    if drift:
        for path in drift:
            print(f"hook config drift: {path}")
        return 1
    print("hook config parity: pass")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--definition", type=Path, default=DEFAULT_DEFINITION)
    parser.add_argument("--output-root", type=Path, default=Path.cwd())
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    try:
        definition = _load_definition(args.definition)
        outputs = {
            args.output_root / path: _serialized(render_hooks(definition, runtime))
            for runtime, path in OUTPUT_PATHS.items()
        }
        if args.check:
            return _check(outputs)
        for path, body in outputs.items():
            _atomic_write(path, body)
    except (HookDefinitionError, json.JSONDecodeError, OSError) as exc:
        print(f"hook config render failed: {exc}")
        return 1
    print("hook configs rendered")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
