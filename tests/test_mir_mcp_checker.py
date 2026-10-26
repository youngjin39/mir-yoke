"""Guarded canonical checker seams used by the independent MCP package."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "plugins/mir-core/skills/ontology/scripts/ontology_check.py"


@pytest.fixture
def checker():
    spec = importlib.util.spec_from_file_location("guarded_ontology_checker", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    # Compile from source so a test never writes __pycache__ into a plugin tree.
    exec(compile(SCRIPT.read_bytes(), str(SCRIPT), "exec"), module.__dict__)
    return module


class GuardFailure(RuntimeError):
    pass


class MemoryReader:
    """No target files exist: successful reads must use this supplied boundary."""

    def __init__(self, root, files=None, denied=()):
        self.root = root
        self.files = files or {}
        self.denied = set(denied)
        self.calls = []

    def path(self, relative, allow_missing=False):
        self.calls.append(("path", relative))
        if relative in self.denied:
            raise GuardFailure("sentinel refusal")
        return self.root / relative

    def exists(self, relative):
        self.path(relative, allow_missing=True)
        self.calls.append(("exists", relative))
        return relative in self.files

    def read(self, relative):
        self.path(relative)
        self.calls.append(("read", relative))
        return self.files[relative]


def mapping_for(contract):
    return {
        "schema": "mir-semantic-mapping/v1",
        "namespace": "test",
        "contract": {"id": contract["contract_id"], "version": contract["version"],
                     "version_range": ">=1.0.0 <2.0.0"},
        "canonical_index": [],
        "concepts": {entry["id"]: {"status": "absent", "reason": "not used"}
                     for entry in contract["concepts"]},
        "relations": [], "vocabularies": [], "entrypoints": [], "error_cases": [],
        "domain": {"concepts": [], "relations": [], "invariants": []},
        "questions": [{"id": str(i), "question": "question", "evidence": []}
                      for i in range(3)],
        "knowledge_supply": {
            "memory_keeper": contract["mapping"]["knowledge_supply_values"][0]},
    }


def test_should_use_guarded_reader_for_ref_symbols_checks_and_profile(checker, tmp_path,
                                                                    monkeypatch):
    payload = checker.DEFAULT_CONTRACT.read_bytes()
    contract = json.loads(payload)
    io = MemoryReader(tmp_path, {
        "model.py": b"def declared():\r\n    pass\r\n",
        ".mir/repo-profile.toml": b'slug = "test"\n',
    })
    subject = checker.Checker(io=io)

    def forbid(*args, **kwargs):
        raise AssertionError("unguarded filesystem access")

    with monkeypatch.context() as blocked:
        for name in ("read_bytes", "read_text", "resolve", "exists", "is_file"):
            blocked.setattr(Path, name, forbid)
        subject.ref("model.py#declared", "/ref", tmp_path)
        subject.covered_check("model.py:2", "/check", tmp_path)
        subject.mapping(mapping_for(contract), contract, payload, tmp_path)
        checker.impact({"domain": {"concepts": [{"ref": "model.py#declared"}]}},
                       tmp_path, ["model.py"], io=io)
    assert subject.errors == []
    assert ("read", "model.py") in io.calls
    assert ("read", ".mir/repo-profile.toml") in io.calls


@pytest.mark.parametrize("operation", ["ref", "covered_check", "mapping", "impact", "lookup"])
def test_should_propagate_guard_refusals_from_every_indirect_path(checker, tmp_path, operation):
    io = MemoryReader(tmp_path, denied={"secrets/value.txt", ".mir/repo-profile.toml"})
    mapping = {"domain": {"concepts": [{"name": "needle", "ref": "secrets/value.txt"}]}}
    with pytest.raises(GuardFailure, match="sentinel refusal"):
        if operation in ("ref", "covered_check"):
            getattr(checker.Checker(io=io), operation)("secrets/value.txt", "/ref", tmp_path)
        elif operation == "mapping":
            payload = checker.DEFAULT_CONTRACT.read_bytes()
            contract = json.loads(payload)
            checker.Checker(io=io).mapping(mapping_for(contract), contract, payload, tmp_path)
        elif operation == "impact":
            checker.impact(mapping, tmp_path, ["unrelated.py"], io=io)
        else:
            checker.lookup(mapping, "needle", 3, io=io)


def test_should_guard_only_projected_lookup_refs_and_allow_missing(checker, tmp_path):
    io = MemoryReader(tmp_path, denied={"secrets/value.txt"})
    mapping = {"domain": {"concepts": [
        {"name": "needle", "ref": "missing.py#declared"},
        {"name": "unrelated", "ref": "secrets/value.txt"},
    ]}}
    result = checker.lookup(mapping, "needle", 1, io=io)
    assert result["matches"][0]["evidence"] == ["missing.py#declared"]
    assert ("path", "missing.py") in io.calls
    assert all(relative != "secrets/value.txt" for _, relative in io.calls)


def test_should_supply_stable_guarded_finding_codes_without_changing_legacy(checker, tmp_path):
    legacy = checker.Checker()
    legacy.ref("", "/ref", tmp_path)
    assert legacy.errors == [{"pointer": "/ref", "message": "needs a ref"}]
    guarded = checker.Checker(io=MemoryReader(tmp_path))
    guarded.ref("", "/ref", tmp_path)
    assert guarded.errors == [
        {"pointer": "/ref", "message": "needs a ref", "code": "E_VALIDATION"}]


def pin_report():
    return dict.fromkeys(("mapping_path", "mapping_version", "mapping_sha256",
                          "contract_id", "contract_version", "contract_sha256"), "declared")


@pytest.mark.parametrize("decoded", [False, True])
def test_should_route_handoff_reads_and_all_git_calls_through_callbacks(checker, tmp_path,
                                                                      monkeypatch, decoded):
    io = MemoryReader(tmp_path, {"model.py": b"current\r\n"})
    calls = []

    def runner(label, *args):
        calls.append((label, args))
        value = {
            "rev-parse": b"a" * 40 + b"\n", "status": b" M model.py\n",
            "log": b"b" * 40 + b"\n", "diff": True,
        }[args[0]]
        if decoded and args[0] in ("rev-parse", "log"):
            return value.decode("ascii").strip()
        return bool(value) if decoded and args[0] == "status" else value

    def forbid(*args, **kwargs):
        raise AssertionError("unguarded filesystem or subprocess access")

    with monkeypatch.context() as blocked:
        for name in ("read_bytes", "read_text", "resolve", "exists", "is_file"):
            blocked.setattr(Path, name, forbid)
        blocked.setattr(checker.subprocess, "run", forbid)
        result = checker.handoff_pins(tmp_path, ["model.py"], pin_report(),
                                      io=io, git_runner=runner)
    assert result["head"] == "a" * 40
    assert result["dirty"] is True
    assert result["sources"][0]["sha256"] == hashlib.sha256(b"current\r\n").hexdigest()
    assert result["sources"][0]["modified_vs_head"] is True
    assert [args for _, args in calls] == [
        ("rev-parse", "--verify", "HEAD"),
        ("status", "--porcelain=v1", "--untracked-files=all", "--ignore-submodules=all"),
        ("log", "-1", "--format=%H", "--", "model.py"),
        ("diff", "--quiet", "--no-ext-diff", "--no-textconv", "--ignore-submodules=all",
         "HEAD", "--", "model.py"),
    ]


@pytest.mark.parametrize("refusal", ["path", "read", "git"])
def test_should_propagate_handoff_guard_refusal(checker, tmp_path, refusal):
    io = MemoryReader(tmp_path, {"model.py": b"safe"},
                      denied={"model.py"} if refusal == "path" else ())

    def runner(label, *args):
        if refusal == "git":
            raise GuardFailure("sentinel refusal")
        return b"a" * 40 if args[0] in ("rev-parse", "log") else b""

    if refusal == "read":
        def denied_read(relative):
            raise GuardFailure("sentinel refusal")
        io.read = denied_read
    with pytest.raises(GuardFailure, match="sentinel refusal"):
        checker.handoff_pins(tmp_path, ["model.py"], pin_report(), io=io, git_runner=runner)


def test_should_require_git_callback_with_guarded_handoff(checker, tmp_path, monkeypatch):
    def forbid(*args, **kwargs):
        raise AssertionError("raw git must not run")

    monkeypatch.setattr(checker.subprocess, "run", forbid)
    with pytest.raises(ValueError, match="git_runner"):
        checker.handoff_pins(tmp_path, [], pin_report(), io=MemoryReader(tmp_path))


@pytest.mark.parametrize("operation", ["ref", "covered_check", "impact"])
def test_should_validate_indirect_json_before_canonical_parser(checker, tmp_path, monkeypatch,
                                                             operation):
    payload = b"[" * 33 + b'{"declared": 1}' + b"]" * 33
    io = MemoryReader(tmp_path, {"deep.json": payload})
    seen = []

    def validate_json(raw):
        seen.append(raw)
        raise GuardFailure("JSON depth refused")

    def forbidden_parser(*args, **kwargs):
        raise AssertionError("canonical JSON parser reached before the policy validator")

    io.validate_json = validate_json
    monkeypatch.setattr(checker.json, "loads", forbidden_parser)
    with pytest.raises(GuardFailure, match="JSON depth refused"):
        if operation == "impact":
            checker.impact({"domain": {"concepts": [{"ref": "deep.json#declared"}]}},
                           tmp_path, ["deep.json"], io=io)
        else:
            getattr(checker.Checker(io=io), operation)("deep.json#declared", "/ref", tmp_path)
    assert seen == [payload.decode("utf-8")]


@pytest.mark.parametrize("validator", [False, True])
def test_should_accept_guarded_json_symbols_with_optional_policy_validator(checker, tmp_path,
                                                                         validator):
    io = MemoryReader(tmp_path, {"model.json": b'{"declared": 1}\r\n'})
    seen = []
    if validator:
        io.validate_json = lambda raw: seen.append(raw)
    subject = checker.Checker(io=io)
    subject.ref("model.json#declared", "/ref", tmp_path)
    assert subject.errors == []
    assert seen == ['{"declared": 1}\n'] if validator else seen == []
