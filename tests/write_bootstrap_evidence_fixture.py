"""Create deterministic architecture artifacts for the clean-clone CI bootstrap test."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    lock = json.loads((ROOT / ".mir" / "capability-lock.json").read_text(encoding="utf-8"))
    spec = ROOT / "spec"
    spec.mkdir(exist_ok=True)
    (spec / "STATE.md").write_text("# CI bootstrap specification state\n", encoding="utf-8")
    (spec / "index.yaml").write_text("version: 1\n", encoding="utf-8")
    (spec / "graph.yaml").write_text("nodes: []\n", encoding="utf-8")
    evidence = {
        "schema_version": 1,
        "sequence": ["mir-core:design", "mir-core:spec-architect"],
        "capability_commit": lock["source"]["commit"],
        "outputs": ["spec/STATE.md", "spec/index.yaml", "spec/graph.yaml"],
    }
    (spec / "bootstrap-evidence.json").write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
