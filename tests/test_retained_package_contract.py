"""F01-Y: isolated retained-package contracts; capture only from the pinned revision."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FROZEN = ROOT / "tests/fixtures/retained_package_closure.json"
PIN = "5906400250462673691bbb72b66db91d0cb4e556"
# Only this explicitly listed closure is copied; imports cannot borrow other mir modules.
PROBE = r'''
import hashlib
import importlib
import importlib.resources
import importlib.abc
import importlib.machinery
import importlib.util
import json
import sys
from pathlib import Path

root = Path(sys.argv[1]).resolve()
route = sys.argv[2]
manifest = json.loads(sys.argv[3])
sys.path.insert(0, str(root / "src"))

class ConfinedMir(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "mir" or fullname.startswith("mir."):
            spec = importlib.machinery.PathFinder.find_spec(fullname, path)
            assert spec and spec.origin, "missing retained module: " + fullname
            assert Path(spec.origin).resolve().is_relative_to(root), fullname
            return spec
sys.meta_path.insert(0, ConfinedMir())

def guard(event, args):
    if event in {"socket.__new__", "socket.connect", "subprocess.Popen", "os.system",
                 "sqlite3.connect"}:
        raise AssertionError("forbidden side effect: " + event)
sys.addaudithook(guard)

def contained(module):
    assert Path(module.__file__).resolve().is_relative_to(root), module.__name__

result = {"modules": [], "exports": {}, "resources": {}}
if route == "mcp":
    path = root / "plugins/mir-mcp/mir_mcp.py"
    spec = importlib.util.spec_from_file_location("mir_mcp", path)
    server = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(server)
    contained(server)
    modules = server.load_modules()
    for module in modules:
        contained(module)
    assert callable(modules[0].main) and callable(modules[1].main)
    result["modules"] = [server.__name__] + [m.__name__ for m in modules]
    contract = modules[0].DEFAULT_CONTRACT
    assert json.loads(contract.read_bytes())["contract_id"] == "mir.common-semantics"
else:
    for name in manifest["routes"][route]:
        module = importlib.import_module(name)
        contained(module)
        if hasattr(module, "__path__"):
            assert module.__spec__.submodule_search_locations is not None
            result["exports"][name] = sorted(getattr(module, "__all__", []))
            for symbol in result["exports"][name]:
                assert getattr(module, symbol) is not None
    # Exact import set proves that no undeclared mir dependency is available or loaded.
    for name, module in sorted(sys.modules.items()):
        if name == "mir" or name.startswith("mir."):
            contained(module)
            result["modules"].append(name)
    package = importlib.import_module("mir.core.adoption")
    assert package.BoundaryError.__module__ == "mir.core.adoption.boundary"
    assert callable(package.apply_adopter_slim)
    package = importlib.import_module("mir.core.capabilities")
    assert package.CapabilityManager.__module__ == "mir.core.capabilities.manager"
    resource = importlib.resources.files("mir").joinpath("resources/capability-sources.json")
    assert isinstance(json.loads(resource.read_bytes()), dict)
for source, destination in manifest["resources"][route].items():
    data = (root / destination).read_bytes()
    result["resources"][destination] = hashlib.sha256(data).hexdigest()
print(json.dumps(result, sort_keys=True))
'''


def stage(destination, manifest, route, pin=None):
    """Materialize exact source files, including every package initializer and resource."""
    paths = dict.fromkeys(manifest["files"][route])
    mapping = {path: path for path in paths}
    mapping.update(manifest["resources"][route])
    for source, target in mapping.items():
        data = (subprocess.run(
            ["git", "show", f"{pin}:{source}"], cwd=ROOT, check=True, capture_output=True,
        ).stdout if pin else (ROOT / source).read_bytes())
        path = destination / target
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    (destination / "home").mkdir()


def probe(root, manifest, route):
    return subprocess.run(
        [sys.executable, "-I", "-B", "-c", PROBE, str(root), route, json.dumps(manifest)],
        cwd=root, env={"HOME": str(root / "home"), "PATH": "", "UV_OFFLINE": "1"},
        capture_output=True, text=True, timeout=30,
    )


def check(result, expected):
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout) == expected


@pytest.fixture
def manifest():
    return json.loads(FROZEN.read_text())


@pytest.mark.parametrize("route", ["bridge", "cli", "mcp"])
def test_retained_package_contract(tmp_path, manifest, route):
    stage(tmp_path, manifest, route)
    check(probe(tmp_path, manifest, route), manifest["expected"][route])


# Every retained module, initializer and resource is independently indispensable.
CASES = json.loads(FROZEN.read_text())
MUTANTS = [(route, path) for route in ("bridge", "cli", "mcp")
           for path in CASES["files"][route]]
MUTANTS += [(route, path) for route in ("bridge", "cli", "mcp")
            for path in CASES["resources"][route].values()]


@pytest.mark.parametrize(("route", "path"), MUTANTS)
def test_contract_rejects_missing_file(tmp_path, manifest, route, path):
    stage(tmp_path, manifest, route)
    (tmp_path / path).unlink()
    with pytest.raises(AssertionError):
        check(probe(tmp_path, manifest, route), manifest["expected"][route])


@pytest.mark.parametrize("path", [
    "src/mir/core/adoption/__init__.py", "src/mir/core/capabilities/__init__.py",
])
def test_contract_rejects_empty_initializer(tmp_path, manifest, path):
    stage(tmp_path, manifest, "bridge")
    (tmp_path / path).write_text("")
    with pytest.raises(AssertionError):
        check(probe(tmp_path, manifest, "bridge"), manifest["expected"]["bridge"])


def capture():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scratch", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--red", action="store_true")
    args = parser.parse_args()
    manifest = json.loads(FROZEN.read_text())
    assert manifest["reference_pin"] == PIN
    for route in ("bridge", "cli", "mcp"):
        target = args.scratch.resolve() / route
        target.mkdir(parents=True, exist_ok=False)
        stage(target, manifest, route, PIN)
        if args.red:
            broken = ("src/mir/core/adoption/__init__.py" if route != "mcp"
                      else "plugins/mir-mcp/shared/relations_query.py")
            (target / broken).write_text("")
        result = probe(target, manifest, route)
        if args.red:
            # Exercise the same positive assertion against damaged retained packages.
            check(result, manifest["expected"][route])
        assert result.returncode == 0, result.stderr
        assert result.stderr == ""
        manifest.setdefault("expected", {})[route] = json.loads(result.stdout)
    args.output.write_text("{\n" + ",\n".join(
        "  " + json.dumps(key) + ": " + json.dumps(value)
        for key, value in manifest.items()
    ) + "\n}\n")


if __name__ == "__main__":
    capture()
