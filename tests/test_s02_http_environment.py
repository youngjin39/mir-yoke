"""Exercise capture environments without importing or running an oracle."""

import ast
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

FIXTURES = Path(__file__).resolve().parents[1] / "native/handoff-packet/tests/fixtures"


@pytest.mark.parametrize("name", ["e6", "e8", "e10_http", "e12c", "e14c"])
def test_capture_child_environment(name, tmp_path):
    tree = ast.parse((FIXTURES / f"generate_y_{name}.py").read_text(encoding="utf-8"))
    host = {"SystemRoot": os.environ.get("SystemRoot", "synthetic-os-root"),
            "WINDIR": os.environ.get("WINDIR", "synthetic-windir"),
            "HOME": "live-home", "USERPROFILE": "live-profile", "PYTHONPATH": "live-python"}
    scope = dict(os=SimpleNamespace(name="nt", environ=host, defpath=os.defpath),
                 root=tmp_path, work=tmp_path, pattern="*", pem=tmp_path / "invalid.pem",
                 str=str)
    # Only evaluate literal environment construction, never generator setup/callers.
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "os_env" for t in node.targets
        ):
            scope["os_env"] = eval(compile(ast.Expression(node.value), "<os-env>", "eval"),
                                   scope)
    environments = [node for node in ast.walk(tree) if isinstance(node, (ast.Dict, ast.Call))
                    and ((isinstance(node, ast.Dict) and any(
                        isinstance(k, ast.Constant) and k.value == "HOME" for k in node.keys))
                         or (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                             and node.func.id == "dict"
                             and any(k.arg == "HOME" for k in node.keywords)))]
    assert environments
    for expression in environments:
        env = eval(compile(ast.Expression(expression), "<child-env>", "eval"), scope)
        child = subprocess.run(
            [sys.executable, "-I", "-c", "import json, os; print(json.dumps(dict(os.environ)))"],
            cwd=tmp_path, env=env, capture_output=True, check=True,
        )
        observed = {k.upper(): v for k, v in json.loads(child.stdout).items()}
        for key in ("SystemRoot", "WINDIR"):
            assert observed[key.upper()] == host[key], name
        assert observed["HOME"] == observed["USERPROFILE"] == str(tmp_path)
        assert observed["PYTHONIOENCODING"] == "utf-8"
        assert "PYTHONPATH" not in observed


@pytest.mark.parametrize("name", ["e6", "e8", "e10_http", "e14c"])
def test_capture_keeps_windows_stdlib_extensions(name, tmp_path):
    tree = ast.parse((FIXTURES / f"generate_y_{name}.py").read_text(encoding="utf-8"))
    wrapper = next(n.value for n in ast.walk(tree)
                   if isinstance(n, ast.Constant) and isinstance(n.value, str)
                   and "sys.path[:]" in n.value)
    statements = [n for n in ast.parse(wrapper).body
                  if (isinstance(n, ast.Assign) and ast.unparse(n.targets[0]) == "sys.path[:]")
                  or (isinstance(n, ast.If) and ast.unparse(n.test) == "sys.platform == 'win32'")]
    runtime = SimpleNamespace(path=[], platform="win32", base_prefix=str(tmp_path / "python"))
    scope = dict(sys=runtime, pathlib=SimpleNamespace(Path=Path), str=str,
                 root=tmp_path, stdlib=str(tmp_path / "python/Lib"))
    exec(compile(ast.Module(body=statements, type_ignores=[]), "<stdlib-path>", "exec"), scope)
    assert str(tmp_path / "python/DLLs") in runtime.path
