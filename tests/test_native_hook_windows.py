"""Structural Windows rendering checks; these do not execute Windows shells.

Windows parsing, native stdin forwarding, hook-client dispatch and process timing
still require validation on a Windows host.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_RENDERER = (
    Path(__file__).resolve().parents[1]
    / "templates/common-harness/scripts/render-hook-configs.py"
)
_SPEC = importlib.util.spec_from_file_location("native_hook_windows_renderer", _RENDERER)
assert _SPEC is not None and _SPEC.loader is not None
renderer = importlib.util.module_from_spec(_SPEC)
exec(compile(_SPEC.loader.get_source(_SPEC.name), str(_SPEC.origin), "exec"), renderer.__dict__)


def command(runtime: str, shell: str) -> str:
    definition = {
        "schema_version": 2,
        "events": {
            "PreCompact": [
                {
                    "runtimes": ["claude", "codex"],
                    "hooks": [
                        {
                            "native": {
                                "executable": ".mir/bin/project-hooks",
                                "args": ["pre-compact"],
                            },
                            "timeout": 60,
                            "statusMessage": "Project PreCompact checkpoint",
                        }
                    ],
                }
            ]
        },
    }
    payload = renderer.render_hooks(
        definition, runtime, platform="windows", shell=shell
    )
    hook = payload["hooks"]["PreCompact"][0]["hooks"][0]
    assert hook["timeout"] == 60
    assert hook["statusMessage"] == "Project PreCompact checkpoint"
    return hook["command"]


@pytest.mark.parametrize("runtime", ["claude", "codex"])
@pytest.mark.parametrize("shell", ["powershell", "pwsh", "cmd", "git-bash"])
def test_windows_commands_use_fixed_project_executable(runtime, shell):
    rendered = command(runtime, shell)
    assert "project-hooks.exe" in rendered
    assert "pre-compact" in rendered
    assert "--mir-warmup" in rendered
    assert "CLAUDE_PROJECT_DIR" in rendered
    assert "MIR_NATIVE_HOOKS" in rendered
    assert "unavailable" in rendered
    assert "python" not in rendered.lower()
    assert "curl" not in rendered.lower()
    assert "Invoke-WebRequest" not in rendered
    if runtime == "codex":
        assert "rev-parse" in rendered
        assert "--show-toplevel" in rendered
    else:
        assert "rev-parse" not in rendered


@pytest.mark.parametrize("shell", ["powershell", "pwsh"])
def test_powershell_guards_and_stdin_are_shell_specific(shell):
    rendered = command("codex", shell)
    assert "-Command" not in rendered
    assert "ReparsePoint" in rendered
    assert "Container" in rendered or "Directory" in rendered
    assert "$LASTEXITCODE" in rendered
    assert "$null" in rendered
    assert "2>&1" in rendered
    assert "64" in rendered and "126" in rendered and "127" in rendered
    assert "& $mirBinary pre-compact" in rendered
    assert "exit $mirStatus" in rendered


def test_cmd_has_own_guard_and_null_stdin_probe():
    rendered = command("codex", "cmd")
    assert rendered.startswith("cmd /d /v:off /s /c ")
    assert "cmd /d /v:on /s /c" in rendered
    assert "for /f" in rendered.lower()
    assert "%~a" in rendered
    assert ":l=" in rendered
    assert "<nul" in rendered.lower()
    assert ">nul 2>&1" in rendered.lower()
    assert "exit /b !_mir_status!" in rendered
    assert "64" in rendered and "126" in rendered and "127" in rendered
    assert "$env:" not in rendered
    assert "$LASTEXITCODE" not in rendered
    assert "Test-Path" not in rendered
    assert "powershell" not in rendered.lower()


def test_windows_native_requires_explicit_shell():
    with pytest.raises(renderer.HookDefinitionError):
        renderer.render_hooks(
            {"schema_version": 2, "events": {}}, "codex", platform="windows"
        )
