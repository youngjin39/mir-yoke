"""Freeze the resume base-policy diagnostic from isolated pinned Python only.

Regenerate with the repository venv Python and --scratch NEW --output RECORD.
No native executable is loaded; all dependencies and pinned mir sources are staged.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

PIN = "d7ce42656224c719094358f343317907bf6e46a9"
VERSIONS = {
    "pydantic": "2.13.4", "pydantic_core": "2.46.4", "annotated_types": "0.7.0",
    "typing_extensions": "4.16.0", "typing_inspection": "0.4.2",
}
CHILD = r'''
import importlib.metadata
import json
import sys
from pathlib import Path
root = Path(sys.argv[1]).resolve()
sys.path[:0] = [str(root / "src"), str(root / "deps")]
from pydantic import ValidationError
from mir.core.contracts.dispatch_brief import DispatchBrief
versions = json.loads((root / "versions.json").read_text())
assert all(importlib.metadata.version(n) == v for n, v in versions.items())
# Fail closed BEFORE executing the model: no live package may supply any module.
stdlib = Path(sys.base_prefix).resolve()
for name, module in list(sys.modules.items()):
    filename = getattr(module, "__file__", None)
    if not filename or filename.startswith("<"):
        continue
    path = Path(filename).resolve()
    if name == "mir" or name.startswith("mir."):
        assert path.is_relative_to(root / "src"), (name, path)
    else:
        assert path.is_relative_to(root) or (
            path.is_relative_to(stdlib) and "site-packages" not in path.parts
        ), (name, path)
case = next(c for c in json.loads((root / "resume.json").read_text())["cases"]
            if c["name"] == "native-policy-base")
payload = json.loads(bytes.fromhex(case["expected"]["effects"]["files"]["brief.json"]["hex"]))
assert payload == {"expanded_goal": "offline fixture"}
try:
    DispatchBrief(**payload)
except ValidationError as exc:
    assert exc.error_count() == 9
    print(json.dumps({"input": payload, "message": str(exc)}, ensure_ascii=True))
else:
    raise AssertionError("incomplete frozen brief must fail typed validation")
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scratch", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    scratch = args.scratch.resolve()
    scratch.mkdir(parents=True, exist_ok=False)
    sources = subprocess.check_output(
        ["git", "ls-tree", "-r", "--name-only", PIN, "src/mir"], cwd=repo,
    ).decode().splitlines()
    digest = hashlib.sha256()
    for name in sources:
        raw = subprocess.check_output(["git", "show", f"{PIN}:{name}"], cwd=repo)
        target = scratch / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        digest.update(name.encode() + b"\0" + raw)
    for name, version in VERSIONS.items():
        dist = importlib.metadata.distribution(name)
        assert dist.version == version, (name, dist.version)
        for entry in dist.files:
            if ".." in entry.parts:
                continue  # Distribution console scripts are never executed.
            target = scratch / "deps" / entry
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(dist.locate_file(entry), target)
    frozen = repo / "tests/fixtures/executor_resume_stage_d.json"
    shutil.copyfile(frozen, scratch / "resume.json")
    (scratch / "versions.json").write_text(json.dumps(VERSIONS), encoding="ascii")
    result = subprocess.check_output(
        [sys.executable, "-I", "-S", "-B", "-c", CHILD, str(scratch)],
        cwd=scratch, env=dict(os.environ, HOME=str(scratch)),
    )
    record = dict(reference=PIN, sources_sha256=digest.hexdigest(), dependencies=VERSIONS,
                  resume_sha256=hashlib.sha256(frozen.read_bytes()).hexdigest(),
                  **json.loads(result))
    args.output.write_text(json.dumps(record, indent=2, ensure_ascii=True) + "\n",
                           encoding="ascii")


if __name__ == "__main__":
    main()
