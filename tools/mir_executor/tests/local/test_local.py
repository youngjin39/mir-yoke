"""Yoke's optional application-schema extension stays outside the common sync."""
import json
import pathlib

import pytest

from tools.mir_executor.local_hooks import invoke_hook

ROOT = pathlib.Path(__file__).resolve().parents[4]


def test_should_validate_yoke_brief_files(tmp_path):
    path = tmp_path / 'brief.json'
    payload = {
        'version': 1, 'task_id': 'task', 'phase_id': 'phase', 'slice_id': 'slice',
        'target_agent': 'executor-agent', 'user_intent': 'intent', 'expanded_goal': 'goal',
        'owned_scope': ['src/'], 'out_of_scope': [], 'verification_commands': ['pytest'],
        'stop_conditions': ['Stop outside scope'], 'handoff_refs': [], 'tdd_change_refs': [],
        'resume_state_ref': 'tasks/dispatch/task/slice.json',
        'source_refs': {'task_spec': 'task', 'plan': 'tasks/plan.md', 'phase': 'tasks/phase.json'},
    }
    path.write_text(json.dumps(payload))
    brief = invoke_hook(ROOT, 'validate_brief', path, ROOT)
    assert brief.expanded_goal == 'goal'


def test_should_reject_invalid_yoke_brief_files(tmp_path):
    path = tmp_path / 'brief.json'
    path.write_text('{"expanded_goal":"goal"}')
    with pytest.raises(ValueError):
        invoke_hook(ROOT, 'validate_brief', path, ROOT)
