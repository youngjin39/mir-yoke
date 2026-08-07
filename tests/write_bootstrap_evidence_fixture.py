"""Create deterministic architecture artifacts for the clean-clone CI bootstrap test."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    lock = json.loads((ROOT / ".mir" / "capability-lock.json").read_text(encoding="utf-8"))
    spec = ROOT / "spec"
    spec.mkdir(exist_ok=True)
    (spec / "STATE.md").write_text(
        "# CI bootstrap specification state\n\nAll requirements ready.\n", encoding="utf-8"
    )
    (spec / "index.yaml").write_text(
        "version: 1\nrequirements:\n  - id: REQ-001\n    status: ready\n",
        encoding="utf-8",
    )
    (spec / "graph.yaml").write_text(
        "nodes:\n  - id: REQ-001\nedges: []\n", encoding="utf-8"
    )
    (spec / "gaps.yaml").write_text("gaps: []\n", encoding="utf-8")
    evidence = {
        "schema_version": 2,
        "sequence": ["mir-core:design", "mir-core:spec-architect"],
        "capability_commit": lock["source"]["commit"],
        "outputs": [
            "spec/STATE.md",
            "spec/index.yaml",
            "spec/graph.yaml",
            "spec/gaps.yaml",
        ],
        "coverage": {
            "l1": {"total": 1, "filled": 1, "derived": 0, "na": 0, "tbd": 0},
            "l2": {"total": 1, "filled": 1, "derived": 0, "na": 0, "tbd": 0},
            "l3": {"total": 9, "filled": 9, "derived": 0, "na": 0, "tbd": 0},
            "l4": {"total": 10, "filled": 10, "derived": 0, "na": 0, "tbd": 0},
            "ai_ready": {"ready": 1, "incomplete": 0, "blocked": 0},
        },
        "open_gaps": 0,
        "full_review": {
            "project_structure": "pass",
            "memory": "pass",
            "discoverability": "pass",
            "requirements": "pass",
            "organization": "pass",
        },
    }
    (spec / "bootstrap-evidence.json").write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
