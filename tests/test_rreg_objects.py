"""Retained Python registry objects: pinned identity, ordering and error contracts."""
from __future__ import annotations

import json
import runpy
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures/rreg"
HELPERS = runpy.run_path(str(FIXTURES / "capture.py"))
FROZEN = json.loads((FIXTURES / "objects.json").read_text())
# Mutations touch staged copies only, never production source or installed metadata.
MUTANTS = [
    ("src/mir/core/registry/base.py", "return sorted(self._discover().keys())",
     "return list(self._discover().keys())"),
    ("src/mir/core/registry/base.py", "if self._cache is None:", "if True:"),
    ("src/mir/core/registry/base.py", "self._cache = None", "pass"),
    ("src/mir/core/registry/base.py", "if not self.GROUP:", "if False:"),
    ("src/mir/core/registry/base.py", "raise KeyError(", "raise ValueError("),
    ("src/mir/core/registry/base.py", "ep.load()", "ep.value"),
    ("src/mir/core/registry/base.py", "group=self.GROUP", 'group="wrong"'),
    ("src/mir/core/registry/base.py", "in entry_points(group=self.GROUP)",
     "in reversed(entry_points(group=self.GROUP))"),
    ("src/mir/core/registry/agents.py", 'GROUP = "mir.agents"', 'GROUP = "mir.skills"'),
    ("src/mir/core/registry/embedding_backends.py", 'GROUP = "mir.embedding_backends"',
     'GROUP = "mir.skills"'),
    ("src/mir/core/registry/skills.py", 'GROUP = "mir.skills"', 'GROUP = "mir.agents"'),
    ("src/mir/core/registry/providers.py", 'GROUP = "mir.providers"', 'GROUP = "mir.skills"'),
    ("src/mir/core/registry/providers.py", "if name not in allowed:", "if False:"),
    ("src/mir/core/registry/providers.py", "if not (isinstance(cls, type) and",
     "if False and (isinstance(cls, type) and"),
    ("src/mir/core/registry/providers.py", "inspect.iscoroutinefunction(m)", "False"),
    ("src/mir/core/registry/providers.py", "issubclass(cls, MirProviderAdapter)", "True"),
    ("src/mir/core/registry/providers.py", "return cls(**kwargs)", "return cls()"),
    ("src/rreg_plugin.py", 'model="omega"', 'model="mutated"'),
]


def stage(root: Path) -> None:
    def read(relative):
        source = ROOT / relative
        assert source.resolve().is_relative_to(ROOT)
        return source.read_bytes() if source.is_file() else None
    HELPERS["stage"](root, read)


def require_contract(root: Path) -> None:
    result = HELPERS["probe"](root)
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert FROZEN["reference_pin"] == HELPERS["PIN"]
    assert json.loads(result.stdout) == FROZEN["record"]


def test_retained_registry_object_contract(tmp_path: Path) -> None:
    stage(tmp_path)
    require_contract(tmp_path)


@pytest.mark.parametrize("relative,old,new", MUTANTS)
def test_behavioral_mutant_is_rejected(tmp_path: Path, relative, old, new) -> None:
    stage(tmp_path)
    path = tmp_path / relative
    original = path.read_text()
    assert old in original
    path.write_text(original.replace(old, new))
    with pytest.raises(AssertionError):
        require_contract(tmp_path)


def test_current_worktree_import_provenance(tmp_path: Path) -> None:
    # Shared venv editable metadata points elsewhere; isolate and pin this source tree.
    code = HELPERS["PROBE"].split("from mir.core import registry as R")[0] + """
import mir.core.registry
for name, module in list(sys.modules.items()):
    if name == "mir" or name.startswith("mir."):
        assert Path(module.__file__).resolve().is_relative_to(root / "src"), name
"""
    result = subprocess.run(
        [sys.executable, "-I", "-B", "-c", code, str(ROOT)], cwd=tmp_path,
        env={"HOME": str(tmp_path)}, text=True, capture_output=True, timeout=30)
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
