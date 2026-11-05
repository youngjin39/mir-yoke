"""Native declarations are dormant until explicitly selected by project owners."""

from __future__ import annotations

import importlib.util
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "hook_renderer",
    ROOT / "templates/common-harness/scripts/render-hook-configs.py",
)
renderer = importlib.util.module_from_spec(spec)
exec(compile(spec.loader.get_source(spec.name), str(spec.origin), "exec"), renderer.__dict__)


def definition():
    return {
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
                            "statusMessage": "Checkpoint",
                        }
                    ],
                }
            ]
        },
    }


def command(runtime="claude"):
    return renderer.render_hooks(definition(), runtime)["hooks"]["PreCompact"][0]["hooks"][0][
        "command"
    ]


@pytest.mark.parametrize(
    "mutation", ["both", "neither", "unknown", "extra_arg", "path", "bool", "raw", "v1"]
)
def test_native_rejects_invalid_declarations(mutation):
    doc = definition()
    hook = doc["events"]["PreCompact"][0]["hooks"][0]
    if mutation == "both":
        hook["script"] = ".claude/hooks/pre-compact.sh"
    elif mutation == "neither":
        del hook["native"]
    elif mutation == "unknown":
        hook["native"]["args"] = ["invocation-log"]
    elif mutation == "extra_arg":
        hook["native"]["args"].append("extra")
    elif mutation == "path":
        hook["native"]["executable"] = "../project-hooks"
    elif mutation == "bool":
        hook["timeout"] = True
    elif mutation == "raw":
        hook["command"] = "arbitrary"
    else:
        doc["schema_version"] = 1
    with pytest.raises(renderer.HookDefinitionError):
        renderer.render_hooks(doc, "claude")


@pytest.mark.parametrize("runtime", ["claude", "codex"])
@pytest.mark.parametrize("exit_code", [0, 2, 42, 64, 126, 127])
def test_native_exact_argv_root_stdin_and_exit(tmp_path, runtime, exit_code):
    project = tmp_path / "space ' quote \u00e9 $root"
    binary = project / ".mir/bin/project-hooks"
    binary.parent.mkdir(parents=True)
    binary.write_text(
        "#!/bin/sh\n"
        'if [ "$1" = --mir-warmup ]; then cat > warmup-input; exit 0; fi\n'
        'printf "%s\\n" "$CLAUDE_PROJECT_DIR" "$#" "$1"\n'
        f"cat; exit {exit_code}\n"
    )
    binary.chmod(0o755)
    subprocess.run(["git", "init", "-q", str(project)], check=True)
    nested = project / "nested"
    nested.mkdir()
    result = subprocess.run(
        ["sh", "-c", command(runtime)],
        cwd=nested,
        env={**os.environ, "CLAUDE_PROJECT_DIR": str(project)},
        input="event-data",
        text=True,
        capture_output=True,
    )
    assert result.returncode == (0 if exit_code in (64, 126, 127) else exit_code)
    assert result.stdout == f"{project}\n1\npre-compact\nevent-data"
    assert (nested / "warmup-input").read_bytes() == b""
    if exit_code in (64, 126, 127):
        assert "unavailable" in result.stderr


@pytest.mark.parametrize(
    "kind", ["missing", "nonexecutable", "invalid", "symlink", "parent_symlink", "warmup"]
)
def test_native_unavailable_fails_open(tmp_path, kind):
    project = tmp_path / "project"
    binary = project / ".mir/bin/project-hooks"
    binary.parent.mkdir(parents=True)
    if kind != "missing":
        binary.write_text("invalid executable" if kind == "invalid" else "#!/bin/sh\nexit 9\n")
        binary.chmod(0o644 if kind == "nonexecutable" else 0o755)
    if kind == "symlink":
        binary.rename(binary.with_name("other"))
        binary.symlink_to("other")
    if kind == "parent_symlink":
        binary.parent.rename(binary.parent.with_name("other"))
        binary.parent.symlink_to("other", target_is_directory=True)
    result = subprocess.run(
        ["sh", "-c", command()],
        cwd=project,
        env={**os.environ, "CLAUDE_PROJECT_DIR": str(project)},
        input="payload",
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0
    assert not result.stdout
    assert "unavailable" in result.stderr


@pytest.mark.parametrize("runtime", ["claude", "codex"])
def test_native_no_root_fails_open(tmp_path, runtime):
    result = subprocess.run(
        ["sh", "-c", command(runtime)],
        cwd=tmp_path,
        env={**os.environ, "CLAUDE_PROJECT_DIR": ""},
        input="payload",
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0
    assert not result.stdout
    assert "unavailable" in result.stderr


@pytest.mark.parametrize(
    "platform,shell", [("windows", None), ("windows", "bash"), ("posix", "cmd")]
)
def test_native_rejects_malformed_platform_profile(platform, shell):
    with pytest.raises(renderer.HookDefinitionError):
        renderer.render_hooks(definition(), "codex", platform=platform, shell=shell)


def test_generator_forwards_render_target(tmp_path, monkeypatch):
    import runpy

    generator = runpy.run_path(str(ROOT / "scripts/generate_codex_derivatives.py"))
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "templates/common-harness/scripts/render-hook-configs.py"
    target.parent.mkdir(parents=True)
    target.write_bytes(
        (ROOT / "templates/common-harness/scripts/render-hook-configs.py").read_bytes()
    )
    source = tmp_path / "config/project-hooks.json"
    source.parent.mkdir()
    import json

    source.write_text(json.dumps(definition()))
    assert generator["write_hooks"](tmp_path / "out", platform="windows", shell="cmd")
    hooks = json.loads((tmp_path / "out/.codex/hooks.json").read_text())
    assert hooks["hooks"]["PreCompact"][0]["hooks"][0]["command"].startswith("cmd /d")


@pytest.mark.parametrize(
    "event,arg,matcher",
    [
        ("PreCompact", "pre-compact", None),
        ("PostCompact", "post-compact", None),
        ("SessionStart", "compact-resume", "^compact$"),
        ("SessionEnd", "session-end", None),
    ],
)
def test_native_event_argv_and_runtime_fields(event, arg, matcher):
    doc = definition()
    group = doc["events"].pop("PreCompact")[0]
    doc["events"][event] = [group]
    group["hooks"][0]["native"]["args"] = [arg]
    group["hooks"][0]["timeout_overrides"] = {"codex": 3}
    if matcher:
        group["matcher"] = matcher
    for runtime, timeout in [("claude", 60), ("codex", 3)]:
        rendered = renderer.render_hooks(doc, runtime)["hooks"][event][0]
        assert rendered.get("matcher") == matcher
        hook = rendered["hooks"][0]
        assert hook["timeout"] == timeout
        assert hook["statusMessage"] == "Checkpoint"
        assert f'"$native" {arg};' in hook["command"]
    if matcher:
        group["matcher"] = ".*"
        with pytest.raises(renderer.HookDefinitionError):
            renderer.render_hooks(doc, "claude")
