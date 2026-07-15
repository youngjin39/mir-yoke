from __future__ import annotations

import json

from scripts.intent_store import append_goal, set_goal


def test_append_goal_preserves_the_previous_goal() -> None:
    result = append_goal(
        {"goal": "Old goal", "updated": "2026-07-15"},
        "New goal",
        "2026-07-16",
    )

    assert result["history"] == [
        {"goal": "Old goal", "updated": "2026-07-15", "status": "superseded"}
    ]


def test_append_goal_skips_an_empty_template_placeholder() -> None:
    result = append_goal(
        {"goal": "", "updated": "2026-06-11"},
        "First real goal",
        "2026-07-16",
    )

    assert result["history"] == []


def test_set_goal_keeps_three_recent_entries_and_archives_older(tmp_path) -> None:
    intent_path = tmp_path / "tasks" / "intent.json"
    intent_path.parent.mkdir()
    intent_path.write_text(
        json.dumps(
            {
                "goal": "Current",
                "updated": "2026-07-15",
                "history": [
                    {"goal": f"Old {index}", "updated": f"2026-07-{index:02d}"}
                    for index in range(1, 4)
                ],
            }
        ),
        encoding="utf-8",
    )

    set_goal(intent_path, "Next", "2026-07-16")

    live = json.loads(intent_path.read_text(encoding="utf-8"))
    archive = json.loads(
        (intent_path.parent / "archive" / "intent-history.json").read_text(
            encoding="utf-8"
        )
    )
    assert [item["goal"] for item in live["history"]] == ["Old 2", "Old 3", "Current"]
    assert [item["goal"] for item in archive["history"]] == ["Old 1"]
