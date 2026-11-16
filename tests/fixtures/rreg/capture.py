"""Pinned R-REGISTRY oracle; only synthetic distributions and staged source imports."""
from __future__ import annotations

import argparse
import configparser
import json
import os
import subprocess
import sys
import tomllib
from pathlib import Path

PIN = "5906400250462673691bbb72b66db91d0cb4e556"
MODULES = [
    "mir", "mir.core", "mir.core.registry", "mir.core.registry.base",
    "mir.core.registry.agents", "mir.core.registry.embedding_backends",
    "mir.core.registry.providers", "mir.core.registry.skills", "mir.core.contracts",
    *["mir.core.contracts." + n for n in (
        "agent_profile", "compiled_job", "conductor_mode", "discord_event", "gate",
        "provider_result", "route_decision", "task_spec")],
    "mir.core.engine", "mir.core.engine.memory", "mir.core.engine.memory.backends",
    "mir.core.engine.memory.backends.omlx_http", "mir.core.config", "mir.core.config.defaults",
    "mir.core.engine.memory.predicates", "mir.core.engine.memory.sanitize",
]
PLUGIN = '''from types import SimpleNamespace
first = SimpleNamespace(name="first", model="alpha")
last = SimpleNamespace(name="last", model="omega")
class Adapter:
    def dispatch(self): pass
    def initialize(self): pass
    def cleanup(self): pass
class Good(Adapter):
    def __init__(self, **kwargs): self.fields = kwargs
class Unrelated:
    def __init__(self, **kwargs): self.fields = kwargs
class Broken(Adapter):
    def __init__(self, **kwargs): raise RuntimeError("constructor failed")
class AsyncDispatch(Adapter):
    async def dispatch(self): pass
class AsyncInitialize(Adapter):
    async def initialize(self): pass
class AsyncCleanup(Adapter):
    async def cleanup(self): pass
class MissingMethods(Good):
    dispatch = initialize = cleanup = None
def __getattr__(name):
    if name == "explodes": raise RuntimeError("entry load failed")
    raise AttributeError(name)
'''
PROBE = r'''
import importlib.abc
import importlib.machinery
import importlib.metadata as md
import json
import os
import sys
import tomllib
from pathlib import Path
from types import ModuleType, SimpleNamespace as NS
root = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(root / "src"))
class OnlyStaged(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname != "mir" and not fullname.startswith("mir."): return None
        spec = importlib.machinery.PathFinder.find_spec(
            fullname, [str(root / "src")] if fullname == "mir" else path)
        if spec is None or spec.origin is None:
            raise ModuleNotFoundError(f"No module named {fullname!r}", name=fullname)
        assert Path(spec.origin).resolve().is_relative_to(root / "src"), fullname
        return spec
sys.meta_path.insert(0, OnlyStaged())
def guard(event, args):
    if event.startswith(("socket.", "sqlite3.connect", "subprocess.", "os.system")):
        raise RuntimeError("forbidden side effect: " + event)
    if event == "open" and isinstance(args[0], (str, bytes)):
        assert ".mir/memory.db" not in os.fsdecode(args[0])
sys.addaudithook(guard)
from mir.core import registry as R
from mir.core.registry import base
import rreg_plugin as P
for name, module in list(sys.modules.items()):
    if name == "mir" or name.startswith("mir."):
        assert Path(module.__file__).resolve().is_relative_to(root / "src"), name
def observe(fn):
    try: return fn()
    except Exception as exc: return [type(exc).__name__, str(exc)]
eps = list(md.Distribution.at(root / "src/rreg-0.dist-info").entry_points)
extra = list(md.Distribution.at(root / "src/extra-0.dist-info").entry_points)
out = {"base": observe(R.EntryPointRegistry), "wrappers": {},
       "declared": tomllib.loads((root / "pyproject.toml").read_text())["project"]["entry-points"]}
shipped = [ep for ep in eps if ep.name == "omlx_http"]
from mir.core.engine.memory.backends.omlx_http import OmlxHttpBackend
out["shipped"] = [[ep.group, ep.name, ep.value, ep.load() is OmlxHttpBackend,
                    ep.load().__name__, sorted(n for n in vars(ep.load()) if not n.startswith('_'))]
                   for ep in shipped]
for cls in (R.AgentRegistry, R.EmbeddingBackendRegistry, R.ProviderRegistry, R.SkillRegistry):
    calls = []
    selected = [ep for ep in eps + extra if ep.group == cls.GROUP and ep.name != "omlx_http"]
    def discover(*, group):
        calls.append(group)
        return [ep for ep in selected if ep.group == group]
    base.entry_points = discover
    reg = cls()
    value = reg.get("z")
    record = [cls.GROUP, reg.all_names(), value is P.last, vars(value),
              reg.get("a") is P.first, reg.has("a"), reg.has("missing"),
              observe(lambda: reg.get("missing")), len(calls)]
    selected = []
    record.append(reg.get("z") is value)
    reg.reset()
    record.extend([reg.all_names(), len(calls)])
    for target in ("rreg_plugin:explodes", "rreg_plugin:absent", "missing_rreg:obj"):
        selected = [md.EntryPoint(name="bad", value=target, group=cls.GROUP)]
        reg.reset()
        before = len(calls)
        record.extend([observe(reg.all_names), observe(reg.all_names), len(calls) - before])
    def failed(*, group): raise OSError("discovery failed")
    base.entry_points = failed
    reg.reset()
    record.append(observe(reg.all_names))
    out["wrappers"][cls.__name__] = record
# Provider ordering with genuine metadata loads; absent worker tested before injecting a fixture.
def create(target, allowed, **kwargs):
    base.entry_points = lambda *, group: [md.EntryPoint(name="p", value=target, group=group)]
    return R.ProviderRegistry().create("p", NS(providers=NS(allowlist=allowed)), **kwargs)
out["provider"] = [observe(lambda: create("rreg_plugin:Good", {})),
                   observe(lambda: create("rreg_plugin:Good", {"p": False})),
                   observe(lambda: create("rreg_plugin:explodes", {}))]
worker = ModuleType("mir.core.worker")
adapter = ModuleType("mir.core.worker.mir_provider_adapter")
adapter.MirProviderAdapter = P.Adapter
sys.modules[worker.__name__] = worker
sys.modules[adapter.__name__] = adapter
for target in ("first", "Unrelated", "Adapter", "AsyncDispatch", "AsyncInitialize",
               "AsyncCleanup", "Broken", "MissingMethods"):
    def run(target=target):
        value = create("rreg_plugin:" + target, {"p": False}, token="value")
        return [type(value).__name__, vars(value)]
    out["provider"].append(observe(run))
obj = create("rreg_plugin:Good", {"p": False}, token="value")
out["provider"].append([type(obj) is P.Good, obj.fields])
for name, module in list(sys.modules.items()):
    if (name == "mir" or name.startswith("mir.")) and module not in (worker, adapter):
        assert Path(module.__file__).resolve().is_relative_to(root / "src"), name
print(json.dumps(out, sort_keys=True, ensure_ascii=True))
'''


def stage(root: Path, read) -> None:
    for module in MODULES:
        stem = "src/" + module.replace(".", "/")
        for relative in (stem + ".py", stem + "/__init__.py"):
            data = read(relative)
            if data is not None:
                break
        else:
            raise AssertionError("missing module: " + module)
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    project = read("pyproject.toml")
    (root / "pyproject.toml").write_bytes(project)
    groups = tomllib.loads(project.decode())["project"]["entry-points"]
    (root / "src/rreg_plugin.py").write_text(PLUGIN)
    for name in ("rreg", "extra"):
        metadata = root / f"src/{name}-0.dist-info"
        metadata.mkdir(exist_ok=True)
        (metadata / "METADATA").write_text(f"Name: {name}\nVersion: 0\n")
        parser = configparser.ConfigParser()
        parser.optionxform = str
        for group in ("mir.agents", "mir.embedding_backends", "mir.providers", "mir.skills"):
            parser[group] = ({**groups.get(group, {}), "z": "rreg_plugin:first",
                              "a": "rreg_plugin:first"} if name == "rreg"
                             else {"z": "rreg_plugin:last"})
        with (metadata / "entry_points.txt").open("w") as stream:
            parser.write(stream)


def probe(root: Path) -> subprocess.CompletedProcess:
    home = root / "home"
    home.mkdir(exist_ok=True)
    return subprocess.run([sys.executable, "-I", "-B", "-c", PROBE, str(root)],
                          cwd=home, env={"HOME": str(home), "PATH": os.defpath},
                          text=True, capture_output=True, timeout=30)


def capture(scratch: Path, output: Path) -> None:
    repo = Path(__file__).resolve().parents[3]

    def read(relative):
        result = subprocess.run(["git", "show", f"{PIN}:{relative}"], cwd=repo,
                                capture_output=True, check=False)
        return result.stdout if result.returncode == 0 else None

    stage(scratch, read)
    result = probe(scratch)
    assert result.returncode == 0, result.stderr
    assert not result.stderr
    record = json.loads(result.stdout)
    assert record["shipped"][0][:2] == ["mir.embedding_backends", "omlx_http"]
    assert all(row[1] == ["a", "z"] and row[10] == [] for row in record["wrappers"].values())
    output.write_text(json.dumps({"reference_pin": PIN, "record": record}, sort_keys=True) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scratch", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    capture(args.scratch.resolve(), args.output.resolve())
