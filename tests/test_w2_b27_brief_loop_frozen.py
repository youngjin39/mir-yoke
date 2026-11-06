"""Frozen unmodified Python oracle for dispatch briefs, interrupts and loop CLI."""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import signal
from pathlib import Path
from types import SimpleNamespace as NS
from unittest import mock

import pytest

from mir.cli import loop
from mir.core.conductor import dispatch_brief as brief
from mir.core.engine import interrupt_handler as interrupt

FIXTURE = Path(__file__).parent / "../native/handoff-packet/tests/fixtures/w2/b27-brief-loop.json"
BASE = dict(intent="  Ship change!  ", scope=("src/a", "tests/a"), success_criteria=("pass",),
            role_binding="executor", budget={})


def compact(value):
    if isinstance(value, str) and len(value) > 400:
        return dict(length=len(value), sha256=hashlib.sha256(value.encode()).hexdigest(),
                    first=value[:120], last=value[-120:])
    if isinstance(value, dict):
        return {k: compact(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [compact(v) for v in value]
    return value


def observe(case, tmp):
    with mock.patch.object(signal, "signal") as install, mock.patch.object(signal, "getsignal"):
        try:
            return {"value": compact(dict(result=case(tmp), signal_calls=install.call_count))}
        except Exception as exc:  # noqa: BLE001 - freeze reference errors
            return {"error": [type(exc).__name__, compact(str(exc).replace(str(tmp), "<tmp>"))]}


def build(tmp, updates=None, **kwargs):
    task = brief.TaskSpec(**(BASE | (updates or {})))
    return brief.build_dispatch_brief(task, family_slug="generic", **kwargs)


def brief_case(updates=None, **kwargs):
    def run(tmp):
        obj = build(tmp, updates, **kwargs)
        paths = [brief.persist_dispatch_brief(obj, repo_root=tmp),
                 brief.persist_dispatch_brief(obj, repo_root=tmp, dispatch_root=tmp / "custom")]
        return [obj.model_dump(mode="json"), brief.codex_args_from_dispatch_brief(obj),
                [[str(p.relative_to(tmp)), p.read_bytes().hex(),
                  brief.load_dispatch_brief(p).model_dump(mode="json")] for p in paths]]
    return run


def persistence_failure(tmp):
    obj = build(tmp)
    with mock.patch.object(brief.os, "replace", side_effect=OSError("replace failed")):
        result = observe(lambda t: brief.persist_dispatch_brief(obj, repo_root=t), tmp)
    return [result, [str(p.relative_to(tmp)) for p in tmp.rglob("*") if p.is_file()]]


def invalid_load(tmp):
    path = tmp / "bad"
    path.write_text("{")
    return brief.load_dispatch_brief(path)


def fields(tmp):
    data = build(tmp).model_dump(mode="json")
    return {key: {kind: observe(lambda t, d=d: brief.DispatchBrief(**d).model_dump(), tmp)
                  for kind, d in [("absent", {k: v for k, v in data.items() if k != key}),
                                  ("null", data | {key: None}), ("empty", data | {key: ""})]}
            for key in data}


def snapshot_case(method="stash", code=0, out="", ref="stash@{0}", restore=False,
                  err=" failure \n"):
    def run(tmp):
        (tmp / ".git").mkdir()
        child = tmp / "child"
        child.mkdir()
        with mock.patch.object(interrupt.subprocess, "run", return_value=NS(
                returncode=code, stdout=out, stderr=err)) as git:
            snap = interrupt.Snapshot(method, ref, tmp)
            result = observe(lambda t: interrupt.restore_snapshot(snap)
                             if restore else interrupt.take_snapshot(method, child, "label"), tmp)
            if "value" in result and isinstance(result["value"]["result"], interrupt.Snapshot):
                snap = result["value"]["result"]
                result["value"]["result"] = [snap.method, snap.ref, "."]
            return [result, [[c.args[0], str(c.kwargs["cwd"].relative_to(tmp)),
                              c.kwargs["check"], c.kwargs["capture_output"], c.kwargs["text"]]
                             for c in git.call_args_list]]
    return run


def interrupts(tmp):
    rows = {}
    for state in interrupt.RunState:
        for failure in (None, "restore", "transition", "cancel"):
            transitions, stderr = [], io.StringIO()
            def transition(target, transitions=transitions, failure=failure):
                transitions.append(target.value)
                if failure == "cancel":
                    raise KeyboardInterrupt("cancelled")
                if failure == "transition":
                    raise RuntimeError("transition failed")
            with mock.patch.object(interrupt, "restore_snapshot", side_effect=(
                    interrupt.InterruptError("failure") if failure == "restore" else None)), \
                    contextlib.redirect_stderr(stderr):
                try:
                    result = observe(
                        lambda t, s=state, f=transition: interrupt.handle_interrupt(s, 0, f), tmp)
                except KeyboardInterrupt as exc:
                    result = {"cancel": [type(exc).__name__, str(exc)]}
            rows[f"{state.value}/{failure}"] = [result, transitions, stderr.getvalue()]
    transitions = []
    for _ in range(2):
        interrupt.handle_interrupt(interrupt.RunState.ACT, None, transitions.append)
    return [rows, transitions]


def cli(text, commands):
    def run(tmp):
        plan = tmp / "tasks/plan.md"
        plan.parent.mkdir()
        if text is not None:
            plan.write_bytes(text.encode())
        results = []
        with contextlib.chdir(tmp):
            for argv in commands:
                out, err = io.StringIO(), io.StringIO()
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    try:
                        status = loop.main(argv)
                    except SystemExit as exc:
                        status = ["SystemExit", exc.code]
                    except Exception as exc:  # noqa: BLE001 - preserve CLI boundary
                        status = [type(exc).__name__, str(exc).replace(str(tmp), "<tmp>")]
                results.append([status, out.getvalue(), err.getvalue(),
                                {str(p.relative_to(tmp)): p.read_bytes().hex()
                                 for p in sorted(tmp.rglob("*")) if p.is_file()}])
        return results
    return run


NEXT = [["next"], ["next", "--json"]]
MARK = lambda status, step="1": ["mark", "--step", step, "--status", status]  # noqa: E731
PLAN = "# Plan\n\n## Active\n"
CASES = {
    "brief.default": brief_case(),
    "brief.full": brief_case(dict(fingerprint="pin", phase_tag="Phase 2", stack="rust"),
                             change_id="C/1", verification_commands=("b", "a", "b"), phase_ref="p"),
    "brief.fields": fields,
    "brief.invalid": lambda tmp: [observe(lambda t, d=d: brief.DispatchBrief(
        **(build(t).model_dump() | d)), tmp) for d in [{"version": 2}, {"resume_state_ref": "bad"},
        {"extra": 1}, {"source_refs": {"task_spec": "t", "phase": "p", "plan": "bad"}}]],
    "brief.invalid_load": invalid_load,
    "brief.persistence_failure": persistence_failure,
    "brief.constants": lambda tmp: [brief._ROLE_TO_TARGET_AGENT, brief.__all__],
    "brief.derive": lambda tmp: [[brief._derive_task_id(NS(fingerprint=f, intent=i)),
                                 brief._derive_slice_id(NS(phase_tag=p, role_binding=r),
                                                       change_id=c),
                                 brief._slugify(i)] for f, i, p, r, c in [
                                     (None, "---", None, "!", None), ("PIN", "AB", "P", "r", "!!!"),
                                     (None, "\u00c9 \u4e2d" * 40, "", "r", "x" * 81)]],
    "brief.commands": lambda tmp: [brief.verification_commands_from_tdd_entry(e) for e in [
        NS(), NS(categories=None), NS(categories={"a": None, "b": [], "c": {"command": ""},
        "d": {"command": 3}, "e": {"command": "b"}, "f": {"command": "a"},
        "g": {"command": "b"}, "h": {"command": " "}})]],
    "interrupt.matrix": interrupts,
    "interrupt.find_missing": lambda tmp: interrupt.find_repo_root(tmp),
    "loop.arguments": cli("", [["--help"], [], ["bad"], ["mark"], MARK("bad"), MARK("DONE", "x"),
                               ["next", "--bad"], ["next", "--help"], ["mark", "--help"]]),
    "loop.missing": cli(None, NEXT + [MARK("DONE")]),
    "loop.empty": cli("", NEXT + [MARK("DONE")]),
    "loop.malformed": cli('{"steps": [}', NEXT + [MARK("DONE")]),
    "loop.prose": cli(PLAN + "plain\n", NEXT),
    "loop.complete": cli("## Work COMPLETE\n", NEXT),
    "loop.ties": cli(PLAN + "Step 2: TODO\nStep 1: TODO\nStep 2: FAILED\n",
                     NEXT + [MARK("DONE", "2")] + NEXT),
    "loop.crlf": cli(PLAN + "Step 1: TODO | brief=b\r\nStep 2: TODO\r\n",
                     [MARK("FAILED") + ["--reason", "r"]] + NEXT),
    "interrupt.snapshot.stash.1.stderr": snapshot_case("stash", 1, "",
                                                       err="No local changes to save\n"),
    "loop.set_field": lambda tmp: [loop._set_field(line, key, "2") for line, key in (
        ("Step 1: TODO | a=1\r\n", "a"), ("Step 1: TODO\r\n", "b"), ("Step 1: TODO | a=1\n", "a"),
        ("Step 1: TODO", "a"), ("a=1 | a=1", "a"))],
    "loop.replay": cli(PLAN + "Step 1: TODO | brief=b | tdd=change#unit | attempts=bad\n",
                       [MARK("IN_PROGRESS"), MARK("IN_PROGRESS"),
                        MARK("FAILED") + ["--reason", "why"],
                        MARK("FAILED"), MARK("IN_PROGRESS"), MARK("DONE"), MARK("DONE"),
                        MARK("FAILED"), MARK("DONE", "999")] + NEXT),
}
for role in ("executor", "reviewer", "planner", "tester"):
    CASES[f"brief.role.{role}"] = brief_case(dict(role_binding=role, scope=("<unspecified>",)))
for size in (0, 1, 8000, 8001):
    CASES[f"brief.intent.{size}"] = brief_case(dict(intent="x" * size))
for method, code, out in [("stash", 0, ""), ("stash", 1, ""),
                          ("stash", 1, "No local changes to save"),
                          ("worktree", 0, ""), ("unknown", 0, "")]:
    CASES[f"interrupt.snapshot.{method}.{code}.{bool(out)}"] = snapshot_case(method, code, out)
for method, ref, code in [("stash", "", 0), ("stash", "ref", 0), ("stash", "ref", 1),
                          ("worktree", "ref", 0), ("unknown", "ref", 0)]:
    CASES[f"interrupt.restore.{method}.{ref}.{code}"] = snapshot_case(
        method, code, ref=ref, restore=True)
for status in (*loop.MARK_STATUSES, "CLOSED"):
    CASES[f"loop.status.{status}"] = cli(PLAN + f"Step 1: {status} | tdd=# | attempts=-2\r\n", NEXT)

RECORDS = json.loads(FIXTURE.read_text()) if FIXTURE.exists() else {}


def test_every_case_has_a_frozen_record():
    assert sorted(RECORDS) == sorted(CASES)


@pytest.mark.parametrize("name", sorted(CASES))
def test_reference_matches_frozen_record(name, tmp_path):
    assert observe(CASES[name], tmp_path) == RECORDS[name]
