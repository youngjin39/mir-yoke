"""Capture finite DispatchBrief profile results from supplied Python contracts."""

from __future__ import annotations

import argparse
import json
import runpy
from pathlib import Path


def capture(source: Path, typed: bool) -> list[dict]:
    model = runpy.run_path(str(source))["DispatchBrief"]
    good = dict(
        task_id="task",
        slice_id="slice",
        target_agent="executor-agent",
        user_intent="Implement a bounded change.",
        expanded_goal="Update the owned module.",
        owned_scope=["src/module.rs"],
        stop_conditions=["Stop outside the owned scope."],
        resume_state_ref="tasks/dispatch/task/slice.json",
        source_refs=dict(task_spec="runtime://project/task", phase="tasks/phase.json"),
    )
    good["verification_ids" if typed else "verification_commands"] = [
        "git-diff-check" if typed else "cargo test"
    ]
    cases = [
        ("valid", good),
        ("missing_all", {}),
        ("unicode", dict(good, user_intent="\ud55c\uae00 caf\u00e9 \U0001f600")),
    ]
    for field, values in {
        "version": [
            None,
            "bad",
            "1",
            "2.0",
            1.2,
            True,
            3,
            " +1 ",
            "1_0",
            "01",
            "_1",
            "1_",
            "1__0",
            "1.0_0",
            "1_0.0",
            "1.00",
            "١",
            10**40,
            float("nan"),
            float("inf"),
            "1" * 4301,
        ],
        "task_id": [None, 1, "", "  "],
        "phase_id": [None, 1, ""],
        "owned_scope": [None, "src", [], [1, None], [1, "src"], [""]],
        "source_refs": [
            None,
            [],
            {},
            {"task_spec": "", "phase": 2, "extra": 1},
            {"task_spec": "x", "phase": "p", "plan": 1},
            {"task_spec": "x", "phase": "p", "plan": "other"},
            float("nan"),
            10**40,
        ],
        "verification_commands": [[], [1], ["cargo test"]],
        "resume_state_ref": ["other", ""],
    }.items():
        for index, value in enumerate(values):
            cases.append((f"{field}_{index}", dict(good, **{field: value})))
    cases.append(("extra", dict(good, z_extra=1, a_extra="value")))
    cases.append(
        ("multiple", dict(good, task_id=1, owned_scope=[], source_refs={}, expanded_goal=""))
    )
    if typed:
        for index, value in enumerate(
            [[], ["unknown"], ["zzz", "aaa", "zzz"], [1], ["python-tests", "ruff"]]
        ):
            cases.append((f"verification_ids_{index}", dict(good, verification_ids=value)))
        cases.extend(
            [
                (
                    "legacy_v1",
                    dict(
                        good, version=1, verification_ids=[], verification_commands=["cargo test"]
                    ),
                ),
                ("legacy_v1_ids", dict(good, version=1, verification_commands=["cargo test"])),
                ("v2_commands", dict(good, verification_commands=["cargo test"])),
            ]
        )
    result = []
    for name, payload in cases:
        raw = json.dumps(payload, ensure_ascii=True)
        try:
            parsed = model(**json.loads(raw))
            outcome = {"value": parsed.model_dump(mode="json")}
        except Exception as error:
            outcome = {"kind": type(error).__name__, "message": str(error)}
        result.append(dict(name=name, text=raw, **outcome))
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--typed", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.write_text(
        json.dumps(
            {"base_v1": capture(args.base, False), "closed_verifier_v2": capture(args.typed, True)},
            indent=2,
            ensure_ascii=True,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
