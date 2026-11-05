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
    if payload.get("schema_version") not in (1, 2):
        raise HookDefinitionError("schema_version must be 1 or 2")
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


def _windows_command(runtime: str, shell: str, subcommand: str) -> str:
    """Build a selected Windows shell guard; Windows execution is unverified."""
    if shell in {"powershell", "pwsh"}:
        unavailable = (
            "[Console]::Error.WriteLine('mir-project-hooks: native hook unavailable'); exit 0"
        )
        root = (
            "$mirRoot=$env:CLAUDE_PROJECT_DIR; "
            if runtime == "claude"
            else (
                "$mirRoot=git rev-parse --show-toplevel 2>$null; "
                f"if ($LASTEXITCODE -ne 0) {{ {unavailable} }}; "
            )
        )
        body = (
            "if ($env:MIR_NATIVE_HOOKS -eq '0') { exit 0 }; "
            "try { " + root + f"if ([string]::IsNullOrWhiteSpace($mirRoot)) {{ {unavailable} }}; "
            "$mirDir=Join-Path $mirRoot '.mir'; "
            "$mirBinDir=Join-Path $mirDir 'bin'; "
            "$mirBinary=Join-Path $mirBinDir 'project-hooks.exe'; "
            "foreach ($mirPath in @($mirDir,$mirBinDir,$mirBinary)) { "
            "$mirItem=Get-Item -LiteralPath $mirPath -Force -ErrorAction Stop; "
            "if (($mirItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) "
            f"{{ {unavailable} }} "
            "}; "
            "if (!(Test-Path -LiteralPath $mirDir -PathType Container) -or "
            "!(Test-Path -LiteralPath $mirBinDir -PathType Container) -or "
            "!(Test-Path -LiteralPath $mirBinary -PathType Leaf)) "
            f"{{ {unavailable} }}; "
            "$env:CLAUDE_PROJECT_DIR=$mirRoot; "
            "$null | & $mirBinary --mir-warmup >$null 2>&1; "
            f"if ($LASTEXITCODE -ne 0) {{ {unavailable} }}; "
            f"& $mirBinary {subcommand}; $mirStatus=$LASTEXITCODE; "
            f"if ($mirStatus -in @(64,126,127)) {{ {unavailable} }}; "
            "exit $mirStatus "
            f"}} catch {{ {unavailable} }}"
        )
        return body
    if shell == "cmd":
        unavailable = "(echo mir-project-hooks: native hook unavailable 1>&2 & exit /b 0)"
        root = (
            'set "_mir_root=%CLAUDE_PROJECT_DIR%"'
            if runtime == "claude"
            else (
                'set "_mir_root=" & for /f "delims=" %R in '
                "('git rev-parse --show-toplevel 2^>nul') do "
                'set "_mir_root=%R"'
            )
        )
        body = (
            'if "!MIR_NATIVE_HOOKS!"=="0" exit /b 0 & '
            + f"if not defined _mir_root {unavailable} & "
            'set "_mir_binary=!_mir_root!\\.mir\\bin\\project-hooks.exe" & '
            'for %A in ("!_mir_root!\\.mir" "!_mir_root!\\.mir\\bin" '
            '"!_mir_binary!") do ('
            'set "_mir_attr=%~aA" & '
            f"if not defined _mir_attr {unavailable} & "
            f'if not "!_mir_attr:l=!"=="!_mir_attr!" {unavailable}'
            ") & "
            'for %A in ("!_mir_binary!") do ('
            'set "_mir_attr=%~aA" & '
            f'if "!_mir_attr:~0,1!"=="d" {unavailable}'
            ") & "
            'if not exist "!_mir_root!\\.mir\\bin\\." '
            + unavailable
            + ' & set "CLAUDE_PROJECT_DIR=!_mir_root!" & '
            '"!_mir_binary!" --mir-warmup <nul >nul 2>&1 & '
            'set "_mir_status=!errorlevel!" & '
            f'if not "!_mir_status!"=="0" {unavailable} & '
            f'"!_mir_binary!" {subcommand} & '
            'set "_mir_status=!errorlevel!" & '
            f'if "!_mir_status!"=="64" {unavailable} & '
            f'if "!_mir_status!"=="126" {unavailable} & '
            f'if "!_mir_status!"=="127" {unavailable} & '
            "exit /b !_mir_status!"
        )
        return f'cmd /d /v:off /s /c "{root} & cmd /d /v:on /s /c "{body}""'
    raise HookDefinitionError(f"unsupported Windows shell: {shell}")


def _native_command(runtime: str, subcommand: str, platform: str, shell: str | None) -> str:
    if platform == "windows" and shell != "git-bash":
        return _windows_command(runtime, shell, subcommand)
    binary = ".mir/bin/project-hooks" + (".exe" if platform == "windows" else "")
    root = (
        'project_root="${CLAUDE_PROJECT_DIR:-}"; '
        if runtime == "claude"
        else 'project_root="$(git rev-parse --show-toplevel 2>/dev/null)" || project_root=""; '
    )
    unavailable = "printf '%s\\n' 'project-hooks: native unavailable' >&2; exit 0"
    return (
        root
        + 'if [ -z "$project_root" ] || [ "${MIR_NATIVE_HOOKS:-1}" = 0 ]; then '
        + unavailable
        + "; fi; "
        + f'native="$project_root/{binary}"; '
        + 'if [ -f "$native" ] && [ -x "$native" ] && [ ! -L "$native" ] && '
        + '[ ! -L "$project_root/.mir" ] && [ ! -L "$project_root/.mir/bin" ] && '
        + '"$native" --mir-warmup </dev/null >/dev/null 2>&1; then '
        + f'CLAUDE_PROJECT_DIR="$project_root" "$native" {subcommand}; result=$?; '
        + 'case "$result" in 64|126|127) '
        + unavailable
        + ';; *) exit "$result";; esac; else '
        + unavailable
        + "; fi"
    )


def _native_subcommand(hook: dict, event: str, group: dict, version: int) -> str:
    native = hook["native"]
    expected = {
        "PreCompact": "pre-compact",
        "PostCompact": "post-compact",
        "SessionStart": "compact-resume",
        "SessionEnd": "session-end",
    }
    if (
        version != 2
        or not isinstance(native, dict)
        or set(native) != {"executable", "args"}
        or native["executable"] != ".mir/bin/project-hooks"
        or event not in expected
        or native["args"] != [expected[event]]
        or (event == "SessionStart" and group.get("matcher") != "^compact$")
    ):
        raise HookDefinitionError(
            "native hook must declare the exact project-hooks event argv in v2"
        )
    return expected[event]


def _render_group(
    group: dict[str, Any], runtime: str, event: str, version: int, platform: str, shell: str | None
) -> dict[str, Any] | None:
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
        if (
            not isinstance(hook, dict)
            or ("script" in hook) == ("native" in hook)
            or set(hook) - {"script", "native", "timeout", "timeout_overrides", "statusMessage"}
        ):
            raise HookDefinitionError("hook must declare exactly one of script or native")
        script = hook.get("script")
        timeout = hook.get("timeout")
        timeout_overrides = hook.get("timeout_overrides", {})
        status = hook.get("statusMessage")
        script_path = PurePosixPath(script) if isinstance(script, str) else None
        if "script" in hook and (
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
        if not all(type(value) is int and value > 0 for value in timeout_overrides.values()):
            raise HookDefinitionError("hook timeout override must be a positive integer")
        if not isinstance(status, str) or not status:
            raise HookDefinitionError("hook statusMessage must be non-empty")
        command = (
            _native_command(
                runtime, _native_subcommand(hook, event, group, version), platform, shell
            )
            if "native" in hook
            else _command(script, runtime)
        )
        runtime_timeout = timeout_overrides.get(runtime, timeout)
        rendered_hooks.append(
            {
                "type": "command",
                "command": command,
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


def render_hooks(
    definition: dict[str, Any], runtime: str, *, platform: str = "posix", shell: str | None = None
) -> dict[str, Any]:
    """Return one runtime hook configuration."""
    if (
        platform not in {"posix", "windows"}
        or (platform == "windows" and shell not in {"git-bash", "powershell", "pwsh", "cmd"})
        or (platform == "posix" and shell is not None)
    ):
        raise HookDefinitionError("select an explicit supported platform/shell profile")
    version = definition.get("schema_version")
    if type(version) is not int or version not in (1, 2):
        raise HookDefinitionError("schema_version must be 1 or 2")
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
            if (rendered := _render_group(group, runtime, event, version, platform, shell))
            is not None
        ]
        if rendered_groups:
            rendered_events[event] = rendered_groups

    payload: dict[str, Any] = {"hooks": rendered_events}
    if runtime == "codex" and definition.get("codex_notes"):
        notes = definition["codex_notes"]
        if not isinstance(notes, list) or not all(isinstance(item, str) for item in notes):
            raise HookDefinitionError("codex_notes must be an array of strings")
        payload = {"description": " ".join(notes), **payload}
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
    parser.add_argument("--platform", default="posix", choices=["posix", "windows"])
    parser.add_argument("--shell", choices=["git-bash", "powershell", "pwsh", "cmd"])
    args = parser.parse_args(argv)

    try:
        definition = _load_definition(args.definition)
        outputs = {
            args.output_root / path: _serialized(
                render_hooks(definition, runtime, platform=args.platform, shell=args.shell)
            )
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
