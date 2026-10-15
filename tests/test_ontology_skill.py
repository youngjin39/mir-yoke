"""Portable semantic contract distribution and deterministic mapping regressions."""

from __future__ import annotations

import ast
import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "plugins/mir-core/skills/ontology"
CHECKER = SKILL / "scripts/ontology_check.py"
CONTRACT = SKILL / "references/common-contract.json"
# Owner source is optional in a public checkout; never use it at runtime.
OWNER_CONTRACT = ROOT.parents[1] / ("09." + "Mini_Harness") / "config/ontology/common-contract.json"
CONCEPTS = (
    "Project Agent Capability Requirement Concept Artifact Decision Task Run Evidence "
    "Assessment Policy"
).split()


@pytest.fixture
def mapping_repo(tmp_path: Path) -> tuple[Path, dict]:
    (tmp_path / ".mir").mkdir()
    (tmp_path / ".mir/repo-profile.toml").write_text('[repo]\nslug = "example-notes"\n')
    (tmp_path / "check.py").write_text("def test_x():\n    pass\n")
    (tmp_path / "model.md").write_text("# Model\nGeneric model and checks.\n")
    mapping = {
        "schema": "mir-semantic-mapping/v1",
        "contract": {
            "id": "mir.common-semantics",
            "version": "1.0.0",
            "version_range": ">=1.0.0 <2.0.0",
        },
        "namespace": "example-notes",
        "canonical_index": ["model.md"],
        "concepts": {
            concept: {"status": "absent", "reason": "No local record yet."} for concept in CONCEPTS
        },
        "vocabularies": [
            {
                "name": "note state",
                "ref": "model.md:2",
                "values": {
                    "published": {"lifecycle": "accepted", "temporal": "current"},
                    "pinned": {"local_only": "Presentation preference."},
                },
            }
        ],
        "relations": [{"local": "cites", "common": "derived_from", "ref": "model.md"}],
        "domain": {
            "concepts": [{"name": "Note", "ref": "model.md#Model"}],
            "relations": [{"name": "cites", "ref": "model.md"}],
            "invariants": [{"rule": "A note keeps its id.", "ref": "model.md"}],
        },
        "questions": [
            {
                "id": f"Q{i}",
                "question": f"Which notes answer question {i}?",
                "evidence": ["model.md"],
            }
            for i in range(1, 4)
        ],
        "error_cases": [{"id": "E01", "status": "covered", "check": "check.py:2"}],
        "knowledge_supply": {"memory_keeper": "connected", "binding": "model.md"},
        "entrypoints": ["model.md"],
    }
    mapping["concepts"]["Artifact"] = {
        "status": "mapped",
        "local": [{"name": "Note", "ref": "model.md"}],
    }
    return tmp_path, mapping


def run_mapping(repo: Path, mapping: dict, *args: str) -> subprocess.CompletedProcess:
    (repo / ".mir/ontology-map.json").write_text(json.dumps(mapping))
    if "--contract" not in args:
        # Pin legacy regressions independently of the owner's parallel distribution update.
        legacy = json.loads(CONTRACT.read_text())
        legacy["version"] = "1.0.0"
        legacy_path = repo / "legacy-contract.json"
        legacy_path.write_text(json.dumps(legacy))
        args = (*args, "--contract", str(legacy_path))
    return subprocess.run(
        [sys.executable, str(CHECKER), "mapping", "--repo", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_contract_distribution_is_byte_identical_to_owner() -> None:
    if not OWNER_CONTRACT.is_file():
        pytest.skip("Mir Harness owner contract is absent in this public checkout.")
    assert CONTRACT.read_bytes() == OWNER_CONTRACT.read_bytes()
    assert (
        hashlib.sha256(CONTRACT.read_bytes()).hexdigest()
        in (SKILL / "references/SOURCE.md").read_text()
    )


def test_contract_self_check_passes() -> None:
    result = subprocess.run(
        [sys.executable, str(CHECKER), "contract"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "0 errors" in result.stdout


def test_checker_uses_python39_syntax_and_standard_library_only() -> None:
    tree = ast.parse(CHECKER.read_text(), feature_version=(3, 9))
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.add(node.module.split(".")[0])
    assert imports <= {
        "__future__",
        "argparse",
        "hashlib",
        "json",
        "pathlib",
        "re",
        "sys",
        "subprocess",
    }


def test_valid_mapping_passes(mapping_repo: tuple[Path, dict]) -> None:
    result = run_mapping(*mapping_repo, "--json")
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report == {
        "ok": True,
        "errors": [],
        "warnings": [],
        "contract_version": "1.0.0",
        "mapping_version": "1.0.0",
    }


@pytest.mark.parametrize(
    ("pointer", "replacement", "message"),
    [
        (("concepts", "Project"), None, "missing concept"),
        (("concepts", "Project", "status"), "ready", "invalid concept status"),
        (("vocabularies", 0, "values", "published"), {"state": "accepted"}, "unknown axis"),
        (("vocabularies", 0, "values", "published"), {"lifecycle": "ready"}, "unknown axis value"),
        (("relations", 0, "common"), "related_to", "unknown relation"),
        (("entrypoints", 0), "missing.md", "ref path does not exist"),
        (("entrypoints", 0), "../model.md", "ref escapes repository"),
        (("entrypoints", 0), "/model.md", "absolute ref"),
        (("contract", "version_range"), ">=2.0.0 <3.0.0", "version mismatch (E10)"),
        (("contract", "version"), "1.0.1", "newer than the loaded contract (E10)"),
        (("contract", "version"), "2.0.0", "validated version outside its range (E10)"),
        (("namespace",), "another-project", "namespace mismatch"),
        (("error_cases", 0, "check"), None, "covered needs a check ref"),
        (("knowledge_supply", "binding"), None, "connected needs a binding ref"),
        (("canonical_index",), None, "missing required key"),
        (("contract", "version_range"), "^1.0", "invalid version_range"),
        (("contract", "version"), "1", "invalid semver"),
        (("contract", "id"), "another-contract", "contract id mismatch"),
        (("concepts", "Artifact", "local"), [], "mapped needs a non-empty local list"),
        (("concepts", "Project", "reason"), "", "needs a non-empty reason"),
        (("error_cases", 0, "id"), "E99", "unknown error case"),
        (("error_cases", 0, "status"), "passed", "invalid error case status"),
        (("knowledge_supply", "memory_keeper"), "available", "invalid knowledge supply"),
        (("domain", "concepts", 0, "ref"), None, "needs a ref"),
        (("questions",), [], "at least one question"),
        (("vocabularies", 0, "values", "published"), {}, "non-empty axis map"),
        (("relations", 0, "local"), "", "non-empty local"),
        (("domain", "invariants"), {}, "expected a list"),
    ],
)
def test_invalid_mapping_fails_with_specific_message(
    mapping_repo: tuple[Path, dict],
    pointer: tuple,
    replacement: object,
    message: str,
) -> None:
    repo, original = mapping_repo
    mapping = copy.deepcopy(original)
    target = mapping
    for key in pointer[:-1]:
        target = target[key]
    if replacement is None:
        del target[pointer[-1]]
    else:
        target[pointer[-1]] = replacement
    result = run_mapping(repo, mapping)
    assert result.returncode == 1, result.stdout + result.stderr
    assert message in result.stdout
    assert "ERROR /" in result.stdout


def test_warnings_do_not_fail_mapping(mapping_repo: tuple[Path, dict]) -> None:
    repo, mapping = mapping_repo
    mapping["questions"] = mapping["questions"][:1]
    mapping["contract"]["sha256"] = "0" * 64
    result = run_mapping(repo, mapping, "--json")
    assert result.returncode == 0
    report = json.loads(result.stdout)
    assert report["ok"] and not report["errors"]
    assert len(report["warnings"]) == 2


def test_older_validated_version_is_a_warning(mapping_repo: tuple[Path, dict]) -> None:
    repo, mapping = mapping_repo
    contract = json.loads(CONTRACT.read_text())
    contract["version"] = "1.1.0"
    path = repo / "contract.json"
    path.write_text(json.dumps(contract))
    result = run_mapping(repo, mapping, "--contract", str(path))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "WARN /contract/version" in result.stdout
    assert "re-validate (E10)" in result.stdout


def test_oversized_mapping_warns_but_passes(mapping_repo: tuple[Path, dict]) -> None:
    repo, mapping = mapping_repo
    mapping["concepts"]["Project"]["notes"] = "x" * 13000
    result = run_mapping(repo, mapping)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "WARN /: mapping is" in result.stdout
    assert "over the 12288-byte budget" in result.stdout


def test_missing_profile_is_mapping_error(mapping_repo: tuple[Path, dict]) -> None:
    repo, mapping = mapping_repo
    (repo / ".mir/repo-profile.toml").unlink()
    result = run_mapping(repo, mapping)
    assert result.returncode == 1
    assert "missing Profile" in result.stdout


def test_symlink_ref_cannot_escape_repo(mapping_repo: tuple[Path, dict], tmp_path: Path) -> None:
    repo, mapping = mapping_repo
    (repo / "outside").symlink_to(ROOT, target_is_directory=True)
    mapping["entrypoints"] = ["outside/README.md"]
    result = run_mapping(repo, mapping)
    assert result.returncode == 1
    assert "ref escapes repository" in result.stdout


@pytest.mark.parametrize(
    ("key", "replacement", "message"),
    [
        ("schema", "bad", "invalid contract schema"),
        ("version", "1.0", "invalid semver"),
        ("axes", {"lifecycle": {"values": {}}}, "non-empty value map"),
        (
            "relations",
            [{"id": "bad", "from": ["NoConcept"], "to": ["*"]}],
            "unknown endpoint concept",
        ),
        ("error_cases", [{"id": "E01", "rules": ["NO-RULE"]}], "unknown rule"),
        ("concepts", [{"id": "Project"}, {"id": "Project"}], "duplicate id"),
    ],
)
def test_invalid_contract_fails(tmp_path: Path, key: str, replacement: object, message: str):
    contract = json.loads(CONTRACT.read_text())
    contract[key] = replacement
    path = tmp_path / "contract.json"
    path.write_text(json.dumps(contract))
    result = subprocess.run(
        [sys.executable, str(CHECKER), "contract", "--contract", str(path)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert message in result.stdout


def test_missing_mapping_is_io_exit(mapping_repo: tuple[Path, dict]) -> None:
    repo, _ = mapping_repo
    result = subprocess.run(
        [sys.executable, str(CHECKER), "mapping", "--repo", str(repo), "--json"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert not json.loads(result.stdout)["ok"]


@pytest.mark.parametrize(
    ("key", "replacement", "message"),
    [
        ("required_keys", [{}], "expected a non-empty string"),
        ("knowledge_supply_values", None, "expected a list"),
    ],
)
def test_malformed_contract_mapping_spec_is_reported(
    tmp_path: Path,
    key: str,
    replacement: object,
    message: str,
) -> None:
    contract = json.loads(CONTRACT.read_text())
    contract["mapping"][key] = replacement
    path = tmp_path / "contract.json"
    path.write_text(json.dumps(contract))
    result = subprocess.run(
        [sys.executable, str(CHECKER), "contract", "--contract", str(path)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert message in result.stdout


def test_semver_prerelease_obeys_range(mapping_repo: tuple[Path, dict]) -> None:
    repo, mapping = mapping_repo
    contract = json.loads(CONTRACT.read_text())
    contract["version"] = "1.0.0-rc.1+build"
    path = repo / "contract.json"
    path.write_text(json.dumps(contract))
    result = run_mapping(repo, mapping, "--contract", str(path))
    assert result.returncode == 1
    assert "version mismatch (E10)" in result.stdout


def test_invalid_json_is_io_problem(mapping_repo: tuple[Path, dict]) -> None:
    repo, _ = mapping_repo
    (repo / ".mir/ontology-map.json").write_text("{")
    result = subprocess.run(
        [sys.executable, str(CHECKER), "mapping", "--repo", str(repo), "--json"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "IO problem" in json.loads(result.stdout)["errors"][0]["message"]


def test_symlink_loop_ref_reports_io_json(mapping_repo: tuple[Path, dict]) -> None:
    repo, mapping = mapping_repo
    (repo / "loop").symlink_to("loop")
    mapping["canonical_index"] = ["loop"]
    result = run_mapping(repo, mapping, "--json")
    assert result.returncode == 2
    assert "IO problem" in json.loads(result.stdout)["errors"][0]["message"]
    assert not result.stderr


@pytest.mark.parametrize(
    "ref", ["check.py", "check.py:1", "check.py:2", "check.py#test_x", "check.py#Class.test_x"]
)
def test_should_accept_existing_covered_check(mapping_repo, ref):
    repo, mapping = mapping_repo
    mapping["error_cases"][0]["check"] = ref
    result = run_mapping(repo, mapping, "--json")
    assert result.returncode == 0, result.stdout
    assert json.loads(result.stdout)["warnings"] == []


@pytest.mark.parametrize(
    ("ref", "message"),
    [
        ("missing.py", "ref path does not exist"),
        ("check.py:3", "check line exceeds file line count"),
        ("check.py:999999", "check line exceeds file line count"),
        ("check.py:0", "check line must be positive"),
        ("check.py#Class.test_missing", "check name not found"),
        ("/check.py", "absolute ref"),
        ("C:/check.py", "absolute ref"),
        ("../check.py", "ref escapes repository"),
        ("nested/../check.py", "ref escapes repository"),
        (".", "check ref must name a file"),
    ],
)
def test_should_reject_invalid_covered_check(mapping_repo, ref, message):
    repo, mapping = mapping_repo
    mapping["error_cases"][0]["check"] = ref
    result = run_mapping(repo, mapping, "--json")
    assert result.returncode == 1, result.stdout
    assert any(
        finding["pointer"] == "/error_cases/0/check" and message in finding["message"]
        for finding in json.loads(result.stdout)["errors"]
    )


@pytest.mark.parametrize("suffix", [".md", ".txt", ".rst"])
def test_should_warn_when_covered_check_is_document(mapping_repo, suffix):
    repo, mapping = mapping_repo
    (repo / ("check" + suffix)).write_text("test_x\n")
    mapping["error_cases"][0]["check"] = "check" + suffix + "#Class.test_x"
    result = run_mapping(repo, mapping, "--json")
    assert result.returncode == 0, result.stdout
    assert json.loads(result.stdout)["warnings"] == [
        {
            "pointer": "/error_cases/0/check",
            "message": "covered needs a repeatable check; a document is not one",
        }
    ]


def test_should_reject_covered_check_symlink_escape(mapping_repo):
    repo, mapping = mapping_repo
    (repo / "outside").symlink_to(ROOT, target_is_directory=True)
    mapping["error_cases"][0]["check"] = "outside/tests/test_ontology_skill.py"
    result = run_mapping(repo, mapping)
    assert result.returncode == 1
    assert "ERROR /error_cases/0/check: ref escapes repository" in result.stdout


@pytest.fixture
def contract11(mapping_repo):
    repo, mapping = mapping_repo
    contract = json.loads(CONTRACT.read_text())
    contract["version"] = "1.1.0"
    path = repo / "contract.json"
    path.write_text(json.dumps(contract))
    mapping["contract"]["version"] = "1.1.0"
    mapping["knowledge_supply"] = {"memory_keeper": "connected", "binding": "on_demand_stdio"}
    mapping["relations"] = [
        {
            "local": "builds",
            "common": "realized_by",
            "from": ["Requirement"],
            "to": ["Artifact"],
            "ref": "model.md",
        }
    ]
    return repo, mapping, path


@pytest.mark.parametrize(
    ("side", "value"),
    [
        ("from", None),
        ("to", None),
        ("from", ["Artifact"]),
        ("to", ["Run"]),
        ("from", "*"),
        ("to", ["*"]),
        ("from", ["Unknown"]),
        ("to", []),
        ("from", "Requirement"),
        ("from", [None]),
    ],
)
def test_should_reject_invalid_endpoints_at_11(contract11, side, value):
    repo, mapping, contract = contract11
    if value is None:
        del mapping["relations"][0][side]
    else:
        mapping["relations"][0][side] = value
    result = run_mapping(repo, mapping, "--contract", str(contract), "--json")
    assert result.returncode == 1, result.stdout
    assert any(
        e["pointer"].startswith("/relations/0/" + side) for e in json.loads(result.stdout)["errors"]
    )


@pytest.mark.parametrize(
    "relation",
    [
        {"common": "realized_by", "from": ["Requirement", "Capability"], "to": ["Artifact"]},
        {"common": "depends_on", "from": "*", "to": ["Project"]},
        {"common": "depends_on", "from": ["Requirement"], "to": "*"},
        {"local_only": "Local meaning needs no endpoints."},
    ],
)
def test_should_accept_allowed_endpoints_at_11(contract11, relation):
    repo, mapping, contract = contract11
    mapping["relations"] = [{"local": "example", **relation}]
    result = run_mapping(repo, mapping, "--contract", str(contract))
    assert result.returncode == 0, result.stdout


@pytest.mark.parametrize("binding", ["on_demand_stdio", "resident_stdio", None])
def test_should_accept_optional_stdio_binding_at_11(contract11, binding):
    repo, mapping, contract = contract11
    if binding is None:
        del mapping["knowledge_supply"]["binding"]
    else:
        mapping["knowledge_supply"]["binding"] = binding
    result = run_mapping(repo, mapping, "--contract", str(contract))
    assert result.returncode == 0, result.stdout


def test_should_reject_unknown_binding_at_11(contract11):
    repo, mapping, contract = contract11
    mapping["knowledge_supply"]["binding"] = "model.md"
    result = run_mapping(repo, mapping, "--contract", str(contract), "--json")
    assert result.returncode == 1
    assert any("invalid binding" in e["message"] for e in json.loads(result.stdout)["errors"])


def run_query(repo, command, *args):
    return subprocess.run(
        [sys.executable, str(CHECKER), command, "--repo", str(repo), *args],
        text=True,
        capture_output=True,
    )


def test_should_select_affected_entries_and_owned_checks(mapping_repo):
    repo, mapping = mapping_repo
    (repo / "check.py").write_text(
        "from pathlib import Path\nPath('ran-check').write_text('executed')\n"
        "def test_x():\n    pass\n"
    )
    mapping["concepts"]["Artifact"]["local"].append({"name": "Check", "ref": "check.py"})
    run_mapping(repo, mapping)
    result = run_query(repo, "impact", "--paths", "model.md", "--json")
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    pointers = {e["pointer"] for e in report["affected_entries"]}
    assert {
        "/canonical_index/0",
        "/concepts/Artifact",
        "/relations/0",
        "/domain/concepts/0",
        "/questions/0",
    } <= pointers
    assert report["checks_to_run"] == ["check.py:2"]
    assert report["stale_refs"] == []
    assert not report["revalidate"]
    assert not (repo / "ran-check").exists()


def test_should_report_deleted_refs_and_strict_failure(mapping_repo):
    repo, mapping = mapping_repo
    run_mapping(repo, mapping)
    (repo / "model.md").unlink()
    normal = run_query(repo, "impact", "--paths", "model.md", "--json")
    strict = run_query(repo, "impact", "--paths", "model.md", "--strict", "--json")
    assert normal.returncode == 0, normal.stderr
    assert strict.returncode == 1
    assert json.loads(normal.stdout)["stale_refs"]
    assert not json.loads(strict.stdout)["ok"]


def test_should_revalidate_changed_map_and_select_changed_check(mapping_repo):
    repo, mapping = mapping_repo
    run_mapping(repo, mapping)
    result = run_query(repo, "impact", "--paths", ".mir/ontology-map.json", "check.py")
    assert result.returncode == 0, result.stderr
    assert "re-validate" in result.stdout
    assert "checks to run" in result.stdout and "check.py:2" in result.stdout


def test_should_fail_strict_when_mapping_is_invalid_without_stale_refs(mapping_repo):
    repo, mapping = mapping_repo
    mapping["namespace"] = "wrong"
    run_mapping(repo, mapping)
    result = run_query(repo, "impact", "--paths", "unrelated.py", "--strict", "--json")
    assert result.returncode == 1, result.stderr
    assert json.loads(result.stdout)["stale_refs"] == []


def test_should_include_staged_unstaged_deletions_and_rename_sources(mapping_repo):
    repo, mapping = mapping_repo
    run_mapping(repo, mapping)
    # An alternate index and empty tree exercise Git without creating any commit.
    import os

    env = {**os.environ, "GIT_INDEX_FILE": str(repo / ".git/fixture-index")}

    def git(*args):
        return subprocess.run(
            ["git", "-C", str(repo), *args], env=env, text=True, capture_output=True, check=True
        ).stdout.strip()

    git("init", "-q")
    git("add", ".")
    tree = git("write-tree")
    (repo / "model.md").rename(repo / "renamed model.md")
    git("add", "-A")
    (repo / "check.py").write_text("def test_x():\n    return 1\n")
    result = subprocess.run(
        [sys.executable, str(CHECKER), "impact", "--repo", str(repo), "--git-diff", tree, "--json"],
        env=env,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert {"model.md", "renamed model.md", "check.py"} <= set(report["changed_paths"])
    assert report["checks_to_run"] == ["check.py:2"]
    assert report["stale_refs"]


def test_should_match_directory_refs_and_leave_unrelated_entries_unselected(mapping_repo):
    repo, mapping = mapping_repo
    (repo / "docs").mkdir()
    (repo / "docs/note.md").write_text("note")
    mapping["canonical_index"].append("docs")
    run_mapping(repo, mapping)
    report = json.loads(run_query(repo, "impact", "--paths", "docs/note.md", "--json").stdout)
    assert [e["pointer"] for e in report["affected_entries"]] == ["/canonical_index/1"]
    assert report["checks_to_run"] == []


def test_should_lookup_ranked_bounded_evidence_without_dumping_map(mapping_repo):
    repo, mapping = mapping_repo
    run_mapping(repo, mapping)
    result = run_query(repo, "lookup", "notes model", "--limit", "2", "--json")
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["contract"] == mapping["contract"]
    assert len(report["matches"]) == 2
    assert all(m["evidence"] for m in report["matches"])
    assert "vocabularies" not in report
    assert json.loads(run_query(repo, "lookup", "zzzz", "--json").stdout)["matches"] == []
    assert run_query(repo, "lookup", "notes", "--limit", "0").returncode == 2
    text = run_query(repo, "lookup", "Note", "--limit", "3").stdout
    assert "mir.common-semantics" in text and "1.0.0" in text and "model.md" in text


MK_CLIENT = SKILL / "scripts/mk_query.py"
FAKE_MCP = ROOT / "tests/fixtures/ontology_mcp_server.py"


@pytest.fixture
def mk_client(tmp_path, monkeypatch):
    host = tmp_path / "host"
    host.mkdir()
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setenv("HOME", str(host))
    config = host / ".mir/knowledge-supply.json"
    config.parent.mkdir()
    monkeypatch.setenv("MIR_KNOWLEDGE_SUPPLY_CONFIG", str(config))

    def run(mode="normal", soft=True, extra=(), timeout=2):
        config.write_text(
            json.dumps(
                {
                    "memory_keeper": {
                        "command": [sys.executable, str(FAKE_MCP), mode],
                        "cwd": str(host),
                        "timeout_sec": timeout,
                    }
                }
            )
        )
        return subprocess.run(
            [
                sys.executable,
                str(MK_CLIENT),
                "--repo",
                str(repo),
                *(["--soft"] if soft else []),
                *extra,
            ],
            text=True,
            capture_output=True,
            timeout=8,
        )

    return run, config, host, repo


@pytest.mark.parametrize("mode", ["normal", "text"])
def test_should_return_pack_and_reap_server(mk_client, mode):
    import os

    run, config, host, repo = mk_client
    result = run(mode, extra=("query", "ontology", "--namespaces", "ns:core", "--k", "2"))
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["schema_version"] == "mir-context-pack-v1"
    messages = [json.loads(line) for line in (host / "messages.jsonl").read_text().splitlines()]
    assert messages[0]["params"]["clientInfo"]["name"] == "repo-agent"
    assert messages[1]["method"] == "notifications/initialized"
    assert messages[2]["params"] == {
        "name": "federation_serve",
        "arguments": {"query": "ontology", "namespaces": ["ns:core"], "k": 2},
    }
    with pytest.raises(ProcessLookupError):
        os.kill(int((host / "pid").read_text()), 0)


@pytest.mark.parametrize(
    ("mode", "status"),
    [
        ("empty", "empty"),
        ("error", "unavailable"),
        ("tool_error", "unavailable"),
        ("timeout", "unavailable"),
        ("init_timeout", "unavailable"),
        ("malformed", "unavailable"),
    ],
)
@pytest.mark.parametrize("soft", [True, False])
def test_should_degrade_independently_and_reap_on_failure(mk_client, mode, status, soft):
    import os

    run, config, host, repo = mk_client
    result = run(mode, soft=soft, extra=("query", "ontology"), timeout=0.3)
    assert result.returncode == (0 if soft else 2), result.stderr
    assert json.loads(result.stdout)["status"] == status
    assert json.loads(result.stdout)["reason"]
    with pytest.raises(ProcessLookupError):
        os.kill(int((host / "pid").read_text()), 0)


def test_should_pass_personal_namespace_refusal_unchanged(mk_client):
    run, config, host, repo = mk_client
    result = run("refusal", extra=("query", "ontology", "--namespaces", "ns:personal"))
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "status": "refused",
        "reason": "personal namespace is unavailable",
        "namespace": "ns:personal",
    }


def test_should_degrade_without_config_or_on_spawn_failure(mk_client, monkeypatch):
    run, config, host, repo = mk_client
    for soft in (True, False):
        result = subprocess.run(
            [
                sys.executable,
                str(MK_CLIENT),
                "--repo",
                str(repo),
                *(["--soft"] if soft else []),
                "query",
                "ontology",
            ],
            text=True,
            capture_output=True,
        )
        assert result.returncode == (0 if soft else 2), result.stderr
        assert json.loads(result.stdout)["status"] == "unavailable"
    run(extra=("query", "ontology"))
    data = json.loads(config.read_text())
    data["memory_keeper"]["command"] = ["missing-ontology-mcp-command"]
    config.write_text(json.dumps(data))
    result = subprocess.run(
        [sys.executable, str(MK_CLIENT), "--repo", str(repo), "--soft", "query", "ontology"],
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["status"] == "unavailable"


def test_should_use_home_config_and_feedback(mk_client, monkeypatch):
    run, config, host, repo = mk_client
    run(extra=("query", "ontology"))
    monkeypatch.delenv("MIR_KNOWLEDGE_SUPPLY_CONFIG")
    result = subprocess.run(
        [sys.executable, str(MK_CLIENT), "--repo", str(repo), "feedback", "federation:42", "used"],
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"node_ref": "federation:42", "verdict": "used"}


def test_should_refuse_repository_config_without_spawning(mk_client, monkeypatch):
    run, config, host, repo = mk_client
    run(extra=("query", "ontology"))
    (host / "pid").unlink()
    local = repo / "knowledge-supply.json"
    local.write_text(config.read_text())
    monkeypatch.setenv("MIR_KNOWLEDGE_SUPPLY_CONFIG", str(local))
    result = subprocess.run(
        [sys.executable, str(MK_CLIENT), "--repo", str(repo), "--soft", "query", "ontology"],
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["status"] == "unavailable"
    assert not (host / "pid").exists()


@pytest.mark.parametrize("raw", ["{", "[]", '{"error_cases": null}'])
def test_should_report_invalid_map_in_impact_without_traceback(mapping_repo, raw):
    repo, mapping = mapping_repo
    (repo / ".mir/ontology-map.json").write_text(raw)
    for strict in (False, True):
        result = run_query(
            repo,
            "impact",
            "--paths",
            ".mir/ontology-map.json",
            "--json",
            *(["--strict"] if strict else []),
        )
        assert result.returncode == (1 if strict else 0), result.stderr
        report = json.loads(result.stdout)
        assert not report["ok"] and report["revalidate"]
        assert not result.stderr


def test_should_reject_wildcard_array_even_for_unrestricted_relation(contract11):
    repo, mapping, contract = contract11
    mapping["relations"][0].update(common="depends_on", **{"from": ["*"], "to": "*"})
    result = run_mapping(repo, mapping, "--contract", str(contract), "--json")
    assert result.returncode == 1
    assert any(
        e["pointer"].startswith("/relations/0/from") for e in json.loads(result.stdout)["errors"]
    )


def test_should_use_head_when_git_diff_base_is_omitted(mapping_repo, monkeypatch, capsys):
    import importlib.util

    repo, mapping = mapping_repo
    run_mapping(repo, mapping)
    spec = importlib.util.spec_from_file_location("ontology_checker", CHECKER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    calls = []

    def fake_git(args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, b"check.py\0", b"")

    monkeypatch.setattr(module.subprocess, "run", fake_git)
    assert module.main(["impact", "--repo", str(repo), "--git-diff", "--json"]) == 0
    assert calls[0][-2:] == ["HEAD", "--"]
    assert json.loads(capsys.readouterr().out)["checks_to_run"] == ["check.py:2"]


@pytest.mark.parametrize("mode", ["empty_object", "empty_content"])
def test_should_report_empty_mcp_result(mk_client, mode):
    run, config, host, repo = mk_client
    result = run(mode, extra=("query", "ontology"))
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["status"] == "empty"


def test_should_run_client_from_isolated_skill_copy(mk_client, tmp_path):
    import shutil

    run, config, host, repo = mk_client
    run(extra=("query", "ontology"))
    isolated = tmp_path / "isolated"
    shutil.copytree(SKILL, isolated)
    result = subprocess.run(
        [
            sys.executable,
            str(isolated / "scripts/mk_query.py"),
            "--repo",
            str(repo),
            "query",
            "ontology",
        ],
        cwd=host,
        text=True,
        capture_output=True,
        timeout=8,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["nodes"]


def test_should_use_only_python39_stdlib_in_mk_client():
    tree = ast.parse(MK_CLIENT.read_text(), feature_version=(3, 9))
    allowed = {
        "__future__",
        "argparse",
        "json",
        "math",
        "os",
        "pathlib",
        "queue",
        "signal",
        "subprocess",
        "sys",
        "threading",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(alias.name.split(".")[0] in allowed for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.module.split(".")[0] in allowed


def test_should_include_paths_when_staged_and_unstaged_edits_cancel(mapping_repo):
    import os

    repo, mapping = mapping_repo
    run_mapping(repo, mapping)
    env = {**os.environ, "GIT_INDEX_FILE": str(repo / ".git/fixture-index")}

    def git(*args):
        return subprocess.run(
            ["git", "-C", str(repo), *args], env=env, text=True, capture_output=True, check=True
        ).stdout.strip()

    git("init", "-q")
    git("add", ".")
    tree = git("write-tree")
    original = (repo / "model.md").read_text()
    (repo / "model.md").write_text("staged different text")
    git("add", "model.md")
    (repo / "model.md").write_text(original)
    result = subprocess.run(
        [sys.executable, str(CHECKER), "impact", "--repo", str(repo), "--git-diff", tree, "--json"],
        env=env,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    assert "model.md" in json.loads(result.stdout)["changed_paths"]


def test_should_treat_planned_check_as_an_ordinary_ref(mapping_repo):
    repo, mapping = mapping_repo
    mapping["error_cases"][0].update(status="planned", check="check.py#future_check")
    assert run_mapping(repo, mapping).returncode == 0
    result = run_query(repo, "impact", "--paths", "model.md", "--strict", "--json")
    assert result.returncode == 0, result.stdout
    assert json.loads(result.stdout)["stale_refs"] == []
    assert json.loads(result.stdout)["checks_to_run"] == []


def test_should_preserve_refusal_even_with_empty_nodes(mk_client):
    run, config, host, repo = mk_client
    result = run("refusal_empty", extra=("query", "ontology", "--namespaces", "ns:personal"))
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "status": "refused",
        "reason": "personal namespace is unavailable",
        "namespace": "ns:personal",
        "nodes": [],
    }


def test_should_preserve_legacy_binding_ref_validation(mapping_repo):
    repo, mapping = mapping_repo
    mapping["knowledge_supply"]["binding"] = "on_demand_stdio"
    result = run_mapping(repo, mapping)
    assert result.returncode == 1
    assert "ref path does not exist" in result.stdout


def test_should_report_deleted_map_as_strict_validation_failure(mapping_repo):
    repo, mapping = mapping_repo
    for strict in (False, True):
        result = run_query(
            repo,
            "impact",
            "--paths",
            ".mir/ontology-map.json",
            "--json",
            *(["--strict"] if strict else []),
        )
        assert result.returncode == (1 if strict else 0), result.stdout
        report = json.loads(result.stdout)
        assert report["revalidate"] and not report["ok"]
