"""Capture the unchanged Python policy and backend selection oracle."""

from __future__ import annotations

import contextlib
import dataclasses
import io
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from tools.mir_executor import cli, policy  # noqa: E402

cases = []
for mode in (
    "select",
    "force_codex",
    "force_claude",
    "obey_user",
    "user_command_priority",
    "unrestricted",
    "per_project",
    "unknown",
    "",
    None,
):
    for project in ({}, {"demo": "claude"}, [], None):
        for central in (False, True):
            data = {
                "mode": mode,
                "per_project": project,
                "routing": {
                    "default": {"model": "gpt-fixture", "reasoning_effort": "medium"},
                    "by_category": {
                        "unit": {
                            "model": "ignored",
                            "prefer": [None, {"model": " opus ", "reasoning_effort": " high "}],
                        }
                    },
                },
            }
            if central:
                data["delegation"] = {"mode": "obey_user", "default_backend": "claude"}
            warning = io.StringIO()
            with contextlib.redirect_stderr(warning):
                resolved = policy._resolve_policy(data)
            expected = dataclasses.asdict(resolved)
            expected["warning"] = warning.getvalue()
            expected["route"] = resolved.resolve_category("unit")
            expected["fallback"] = resolved.resolve_category("missing")
            expected["backend"] = cli._resolve_dispatch_backend(
                resolved, requested_backend="codex", repo_slug="demo"
            )
            cases.append({"data": data, "expected": expected})
for routing in (
    None,
    [],
    {},
    {"default_model": " x ", "default_reasoning_effort": " low "},
    {"default": [], "by_category": {"unit": {"prefer": [{}, {"model": "x"}]}}},
    {"by_category": {"unit": {"prefer": [{"reasoning_effort": "high"}]}}},
):
    data = {"mode": "select", "routing": routing}
    resolved = policy._resolve_policy(data)
    expected = dataclasses.asdict(resolved)
    expected.update(
        warning="",
        route=resolved.resolve_category("unit"),
        fallback=resolved.resolve_category("missing"),
        backend="codex",
    )
    cases.append({"data": data, "expected": expected})
pathlib.Path(__file__).with_name("executor_policy.json").write_text(
    json.dumps(cases, ensure_ascii=True, indent=2) + "\n"
)
print(f"captured {len(cases)} policy cases")

# File-loading precedence and diagnostic cases are independent of host policy.
import os  # noqa: E402
from unittest.mock import patch  # noqa: E402

scratch = pathlib.Path(os.environ["E2B_SCRATCH"]) / "load-oracle"
(scratch / "config").mkdir(parents=True, exist_ok=True)
(scratch / "account/.mir/model-routing").mkdir(parents=True, exist_ok=True)
loading = []
for local, lock, overlay in (
    (None, None, None),
    ('{"mode":"force_codex"}', None, '{"mode":"force_claude"}'),
    ('{"mode":"force_claude"}', '{"policy":{"mode":"force_codex"}}', "bad"),
    ('{"mode":"unknown"}', None, None),
    ('{"delegation":{"mode":"obey_user"}}', None, None),
    ("[]", None, None),
    ("{", None, None),
    ('{"mode":', None, None),
    ('{"mode": invalid}', None, None),
    ("{}", '{"policy":null}', None),
    ("{}", "[]", None),
    ("{}", None, "[]"),
    ('{"monitoring":{"a":1}}', '{"policy":{"monitoring":{"b":2}}}', None),
):
    for relative, text in (
        ("config/sub-agent-policy.json", local),
        ("config/model-routing.lock.json", lock),
        ("account/.mir/model-routing/sub-agent-policy.json", overlay),
    ):
        path = scratch / relative
        if text is None:
            path.unlink(missing_ok=True)
        else:
            path.write_text(text)
    warning = io.StringIO()
    with (
        patch.dict(os.environ, {"MIR_SUB_AGENT_POLICY": ""}),
        patch.object(
            policy,
            "default_global_policy_path",
            return_value=(scratch / "account/.mir/model-routing/sub-agent-policy.json"),
        ),
        contextlib.redirect_stderr(warning),
    ):
        resolved = policy.load_sub_agent_policy(scratch)
    expected = dataclasses.asdict(resolved)
    expected["warning"] = warning.getvalue()
    loading.append({"local": local, "lock": lock, "overlay": overlay, "expected": expected})
pathlib.Path(__file__).with_name("executor_policy_load.json").write_text(
    json.dumps(loading, ensure_ascii=True, indent=2) + "\n"
)
print(f"captured {len(loading)} policy loading cases")
