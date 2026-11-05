"""Captured profile authority and complete hook composition through the native CLI."""

from __future__ import annotations

import json
import runpy
from pathlib import Path

import pytest

HUB = runpy.run_path(str(Path(__file__).with_name("test_executor_hub_native_parity.py")))
P1, DISPATCH, SUPPORT = HUB["P1"], HUB["DISPATCH"], HUB["SUPPORT"]
binary = HUB["binary"]
GOLDEN = json.loads((Path(__file__).parent / "fixtures/executor_home_profile.json").read_text())


def test_oracle_pins_and_runtime():
    assert GOLDEN["sha256"] == {
        "local": "bbc061e3bcb9f10460235f1b22ea72f9cf60f8ebd6a5e3f2300b686105686d06",
        "contracts": "c00e7b5545c1e3c6a4fc7b3b727053543454a74754ea7346dcdfc564e266b6cc",
        "loader": "e98022cc667a33ba7181d476b1a4114e8b01cf6187c6476215ae63b39a5095dd",
        "authority": "271663b1d529632700b9eefc1bf60f7ac3a5ad04375bfd688b39602c94c3b083",
    }
    assert set(GOLDEN["runtime"]) == {"python", "pydantic", "unicode"}


def seed(root, bridge, case):
    launcher, environment, args = DISPATCH["seed"](root, "success", SUPPORT)
    for path in (root / "server.py", launcher):
        if path.suffix != ".cmd":
            source = path.read_text().replace(
                "    elif method == 'turn/start':",
                "    elif method == 'turn/start':\n"
                "        (root / 'rendered-prompt').write_text("
                "request['params']['input'][0]['text'])",
            )
            path.write_text(source)
    config_path = root / "config/mir-executor.local.json"
    config = json.loads(config_path.read_text())
    if bridge:
        (root / "tools/mir_executor/local.py").write_text(GOLDEN["oracle_source"])
    else:
        (root / "tools/mir_executor/local.py").unlink()
        config["native_policy"] = dict(
            version=1,
            brief_profile={"name": "capability_v1"},
            brief_controls={"mode": "authorized_exact"},
            verifier_aliases={"configuration_root": "initial"},
            job_identity={"name": "scope_capabilities_v1"},
        )
    config_path.write_text(json.dumps(config))
    (root / "brief.json").write_text(case["raw"])
    profile = root / ".mir/repo-profile.toml"
    profile.parent.mkdir(exist_ok=True)
    if case["profile"] is not None:
        profile.write_text(case["profile"])
    else:
        profile.unlink(missing_ok=True)
    return launcher, environment, args


@pytest.mark.parametrize("case", GOLDEN["cases"], ids=lambda case: case["name"])
@pytest.mark.parametrize("resume", [False, True])
def test_cli_matches_owner(binary, tmp_path, case, resume):
    values = []
    for bridge in (True, False):
        root = tmp_path / ("bridge" if bridge else "native")
        launcher, environment, args = seed(root, bridge, case)
        if resume:
            args = DISPATCH["resume"](root, "current")
        result = P1["invoke"](binary, root, environment, args)
        values.append(HUB["snapshot"](root, launcher, result, True))
        values[-1]["provider_prompt_bytes"] = (
            (root / "rendered-prompt").read_bytes()
            if (root / "rendered-prompt").exists() else None
        )
        if "kind" in case:
            assert result.returncode == 1, values[-1]
            assert case["message"].encode() in result.stderr
            assert not (root / "provider-methods").exists()
        if not resume and "kind" in case:
            assert not (root / "tasks/jobs.db").exists()
        if result.returncode == 0 and "rendered" in case:
            assert case["rendered"] in values[-1]["artifacts"].values()
    assert values[0] == values[1], values


@pytest.mark.parametrize("hook", ["validate_brief", "render_brief", "pre_execute", "job_identity"])
def test_duplicates_fail_closed(binary, tmp_path, hook):
    root = tmp_path / "native"
    _, environment, args = seed(root, False, GOLDEN["cases"][0])
    (root / "tools/mir_executor/local.py").write_text(
        "from pathlib import Path\n"
        '(Path(__file__).resolve().parents[2] / "unexpected-import").touch()\n'
        f"def {hook}(*args): pass\n"
    )
    result = P1["invoke"](binary, root, environment, args)
    assert result.returncode == 1
    assert hook.encode() in result.stderr
    for path in ("unexpected-import", "provider-methods", "tasks/jobs.db"):
        assert not (root / path).exists()


def test_undeclared_keeps_python(binary, tmp_path):
    root = tmp_path / "python"
    _, environment, args = seed(root, True, GOLDEN["cases"][0])
    with (root / "tools/mir_executor/local.py").open("a") as source:
        source.write('\ndef pre_execute(args, root):\n    raise ValueError("python-owned")\n')
    result = P1["invoke"](binary, root, environment, args)
    assert result.returncode == 1
    assert b"python-owned" in result.stderr
    assert not (root / "provider-methods").exists()
