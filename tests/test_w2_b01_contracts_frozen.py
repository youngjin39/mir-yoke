"""Frozen unmodified Python contracts; never recapture expectations from a port.

Each default has a named omission case. Compact JSON keeps the full model boundary
within the fixture diff budget. Validation errors exclude version-dependent URLs.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from mir.core.contracts import (
    AgentProfile,
    CompiledJob,
    ConductorMode,
    DiscordEvent,
    GateBlocked,
    PathFingerprint,
    ProviderResult,
    RouteDecision,
    TaskSpec,
    ValidationResult,
)
from mir.core.contracts.dispatch_brief import DispatchBrief, DispatchBriefSourceRefs
from mir.core.contracts.gate import STANDARD_CODES

FIXTURE = Path(__file__).parent / "../native/handoff-packet/tests/fixtures/w2/b01-contracts.json"
AGENT = dict(name="agent", slug="family", model="sonnet", description="d",
             system_prompt="s", context_budget_tokens=1000)
SPEC = dict(intent="work", scope=["src/**"], success_criteria=["pass"],
            role_binding="executor", budget={"tokens": "1"})
ROUTE = dict(type=None, mode="deterministic", signals={"file": "true"},
             executor_provider="provider", reviewer_provider=None)
REFS = dict(task_spec="spec:1", phase="phase:1")
BRIEF = dict(task_id="task", slice_id="slice", target_agent="agent", user_intent="work",
             expanded_goal="finish", owned_scope=["src/**"], verification_commands=["check"],
             stop_conditions=["blocked"], resume_state_ref="tasks/dispatch/task/slice.json",
             source_refs=REFS)
MINIMAL = {
    AgentProfile: AGENT,
    CompiledJob: dict(spec=SPEC, route=ROUTE, resolved_files={}, required_tools=[],
                      session_plan={}, guides_plan={}, budget={}, workdir="work", role="executor",
                      session_uuid="session"),
    DiscordEvent: dict(chat_id="chat", message_id="message", user="agent", user_id="id",
                       timestamp="time", content="hello"),
    DispatchBrief: BRIEF, DispatchBriefSourceRefs: REFS,
    PathFingerprint: dict(path="src/a", inode=0), ValidationResult: dict(ok=True),
    ProviderResult: dict(status="success", exit_code=0, stdout_tail="", stderr_tail="",
                         wall_seconds=0, session_uuid="session", provider="provider"),
    RouteDecision: ROUTE, TaskSpec: SPEC,
}
FULL = {
    AgentProfile: dict(role_binding="reviewer", tools=["tool"], forbidden_tools=["deny"],
                      temperature=2, max_output_tokens=16000, stop_sequences=["stop"],
                      allowed_files=["src/**"], provenance={"source": "ref"}),
    CompiledJob: dict(resolved_files={"src/a": "sha"}, required_tools=["tool"],
                     session_plan={"executor": "session"}, guides_plan={"check": ["check"]},
                     budget={"tokens": "2"}),
    DiscordEvent: dict(attachments=[{"path": "asset"}], reply_to="parent", source="other"),
    DispatchBrief: dict(phase_id="phase", out_of_scope=["docs/**"], handoff_refs=["ref"],
                        tdd_change_refs=["test"], source_refs={**REFS, "plan": "tasks/plan.md"}),
    DispatchBriefSourceRefs: dict(plan="tasks/plan.md"),
    PathFingerprint: dict(inode="2", sha256="sha"),
    ValidationResult: dict(ok="false", reason="warning", rule_id="rule"),
    ProviderResult: dict(artifacts=[{"path": "asset"}], tokens_used={"input": "2"},
                         argv_snapshot=["tool"], exit_code="1", wall_seconds="1.5"),
    RouteDecision: dict(type="feature", mode="supervisor_needed", reviewer_provider="reviewer"),
    TaskSpec: dict(target_files=[{"path": "src/a"}], expected_symbols=["symbol"],
                   required_tools=["tool"], stack="python", parent_task_id="2", fingerprint="sha",
                   phase_tag="phase", extensions={"nested": [1, True, None]}),
}


def _model(model, data, operation="dump"):
    def run(tmp):
        value = model(**data)
        if operation == "json":
            return value.model_dump_json()
        if operation == "frozen":
            setattr(value, next(iter(model.model_fields)), None)
        if operation == "delete":
            delattr(value, next(iter(model.model_fields)))
        if operation == "automatic_finalization_allowed":
            return value.automatic_finalization_allowed
        return value.model_dump(mode="json")
    return run


CASES = {}
for model, minimal in MINIMAL.items():
    prefix = model.__name__
    full = {**minimal, **FULL[model]}
    for label, data in (("minimal", minimal), ("full", full), ("missing", {}),
                        ("extra", {**minimal, "unexpected": 1})):
        CASES[f"{prefix}.{label}"] = _model(model, data)
    for operation in ("json", "frozen", "delete"):
        CASES[f"{prefix}.{operation}"] = _model(model, full, operation)
    for field, info in model.model_fields.items():
        if not info.is_required():
            CASES[f"{prefix}.default.{field}"] = _model(
                model, {key: value for key, value in full.items() if key != field})
        if info.annotation is str:
            CASES[f"{prefix}.int_to_str.{field}"] = _model(model, {**minimal, field: 7})


def _variants(model, field, values):
    for index, value in enumerate(values):
        CASES[f"{model.__name__}.{field}.{index}"] = _model(
            model, {**MINIMAL[model], field: value})


_variants(AgentProfile, "model", ["opus", "haiku", "invalid"])
_variants(AgentProfile, "role_binding", ["conductor", "planner", "tester", "invalid"])
_variants(AgentProfile, "context_budget_tokens", [999, 200000, 200001, "1000", "bad"])
_variants(AgentProfile, "temperature", [-0.1, 0, 2.1, "0.5"])
_variants(AgentProfile, "max_output_tokens", [255, 256, 16001, "256"])
_variants(PathFingerprint, "inode", [-1, "bad"])
_variants(ValidationResult, "ok", ["true", "yes", "0", "bad", None])
_variants(ProviderResult, "status", ["failed", "timeout", "cancelled", "invalid"])
_variants(ProviderResult, "wall_seconds", [-0.1, "bad"])
_variants(ProviderResult, "exit_code", ["bad"])
for field in ("stdout_tail", "stderr_tail"):
    _variants(ProviderResult, field, ["x" * 16384, "x" * 16385])
_variants(RouteDecision, "type", ["bugfix", "refactor", "security", "research", "unknown", "bad"])
_variants(RouteDecision, "mode", ["bad"])
_variants(RouteDecision, "signals", [{"file": "false"}, {"file": "bad"}])
_variants(TaskSpec, "intent", ["", "x" * 8000, "x" * 8001])
_variants(TaskSpec, "scope", [[], "src/**"])
_variants(TaskSpec, "success_criteria", [[]])
_variants(TaskSpec, "role_binding", ["reviewer", "planner", "tester", "invalid", "executor\n"])
_variants(TaskSpec, "parent_task_id", ["bad"])
_variants(TaskSpec, "budget", [{"tokens": "bad"}])
_variants(DispatchBrief, "version", ["1", 2])
_variants(DispatchBrief, "resume_state_ref", ["wrong"])
_variants(DispatchBrief, "source_refs", [{**REFS, "plan": "wrong"}])
for field in ("task_id", "slice_id", "target_agent", "user_intent", "expanded_goal",
              "resume_state_ref"):
    _variants(DispatchBrief, field, [""])
for field in ("owned_scope", "verification_commands", "stop_conditions"):
    _variants(DispatchBrief, field, [[]])
for field in ("task_spec", "phase"):
    _variants(DispatchBriefSourceRefs, field, [""])

def _coerce(model, field, values):
    for index, value in enumerate(values):
        CASES[f"{model.__name__}.coerce.{field}.{index}"] = _model(
            model, {**MINIMAL[model], field: value})


_coerce(AgentProfile, "tools", [5, "tool", [1], None, ["a", "b"]])
_coerce(AgentProfile, "provenance", [{"a": 1}, [], None, {"a": None}])
_coerce(AgentProfile, "context_budget_tokens",
        [1500.0, 1500.5, True, " 1500 ", None, "1_000", "1e3"])
_coerce(AgentProfile, "temperature", [True, None, "bad", " 1 ", "inf", 1])
_coerce(AgentProfile, "name", [None, ["x"], 1.5, True])
_coerce(RouteDecision, "signals", [{"f": 1}, {"f": 0}, {"f": 2}, {"f": "yes"}, {"f": "on"},
                                   {"f": None}, {"f": 1.0}, []])
_coerce(RouteDecision, "reviewer_provider", [5, None])
_coerce(DiscordEvent, "attachments", [[1], ["x"], [{}], {"path": "a"}, None, "ab"])
_coerce(DiscordEvent, "reply_to", [5, None])
_coerce(ProviderResult, "exit_code", [1.0, 1.5, True, " 2 ", None])
_coerce(ProviderResult, "tokens_used", [{"a": "x"}, {"a": 1.5}, {"a": True}, []])
_coerce(ProviderResult, "wall_seconds", [True, " 1.5 "])
CASES["ProviderResult.coerce.wall_seconds_inf"] = lambda tmp: repr(
    ProviderResult(**{**MINIMAL[ProviderResult], "wall_seconds": "inf"}).wall_seconds)
_coerce(ProviderResult, "argv_snapshot", [[1], "ab", None])
_coerce(ProviderResult, "stdout_tail", [None, 5])
CASES["TaskSpec.json_unicode"] = _model(TaskSpec, {**SPEC, "intent": "\u00e9\n"}, "json")
CASES["DispatchBrief.validator_precedence"] = _model(
    DispatchBrief, {**BRIEF, "version": 2, "resume_state_ref": "wrong"})
CASES["DispatchBrief.automatic_finalization_allowed"] = _model(
    DispatchBrief, BRIEF, "automatic_finalization_allowed")


def _fork(overrides):
    return lambda tmp: AgentProfile(**AGENT).fork(**overrides).model_dump(mode="json")


CASES.update({
    "AgentProfile.fork.unchanged": _fork({}),
    "AgentProfile.fork.valid": _fork({"name": "fork", "temperature": 1}),
    "AgentProfile.fork.unvalidated": _fork({"context_budget_tokens": -1}),
    "AgentProfile.fork.extra": _fork({"unexpected": 1}),
    "ConductorMode.values": lambda tmp: [member.value for member in ConductorMode],
    "ConductorMode.invalid": lambda tmp: ConductorMode("invalid"),
    "GateBlocked.default": lambda tmp: str(GateBlocked("policy_deny")),
    "GateBlocked.full": lambda tmp: [GateBlocked("custom", "detail").code,
                                     GateBlocked("custom", "detail").detail,
                                     str(GateBlocked("custom", "detail"))],
    "GateBlocked.codes": lambda tmp: sorted(STANDARD_CODES),
})
for member in ConductorMode:
    CASES[f"ConductorMode.{member.value}"] = (
        lambda tmp, value=member.value: str(ConductorMode(value)))


def observe(case, tmp: Path) -> dict:
    try:
        return {"value": case(tmp)}
    except ValidationError as exc:
        return {"error": [type(exc).__name__, [
            {"type": error["type"], "loc": list(error["loc"]), "msg": error["msg"]}
            for error in exc.errors()]]}
    except Exception as exc:  # noqa: BLE001 - freeze reference exception class and text
        return {"error": [type(exc).__name__, str(exc)]}


RECORDS = json.loads(FIXTURE.read_text(encoding="ascii")) if FIXTURE.exists() else {}


def test_every_case_has_a_frozen_record():
    assert sorted(RECORDS) == sorted(CASES)


@pytest.mark.parametrize("name", sorted(CASES))
def test_reference_matches_frozen_record(name, tmp_path):
    assert observe(CASES[name], tmp_path) == RECORDS[name]
