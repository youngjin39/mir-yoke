"""Exercise the actual reference-child argv without running a live command."""

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize("name,count", [("e6", 3), ("e8", 1)])
def test_reference_children_use_isolated_utf8_without_bytecode(tmp_path, name, count):
    source = Path(f"native/handoff-packet/tests/fixtures/generate_y_{name}.py")
    tree = ast.parse(source.read_text(encoding="utf-8"))
    wrapper = tmp_path / "probe.py"
    wrapper.write_text(
        "import json, sys\n"
        "print(json.dumps([sys.flags.isolated, sys.flags.utf8_mode, "
        "sys.dont_write_bytecode, '모델'], ensure_ascii=False))\n",
        encoding="utf-8",
    )
    calls = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "subprocess"
        and node.func.attr == "run"
    ]
    assert len(calls) == count
    for call in calls:
        argv = eval(compile(ast.Expression(call.args[0]), str(source), "eval"), {
            "sys": sys, "wrapper": wrapper, "host": "127.0.0.1",
            "args": ["seed"], "mode": "probe", "argv": [],
        })
        result = subprocess.run(
            argv, cwd=tmp_path, capture_output=True, check=True,
            env={**{key: value for key, value in os.environ.items()
                    if key in {"SystemRoot", "WINDIR"}},
                 "HOME": str(tmp_path), "USERPROFILE": str(tmp_path),
                 "LC_ALL": "en_US.UTF-8"},
        )
        assert json.loads(result.stdout.decode("utf-8")) == [1, 1, True, "모델"]
