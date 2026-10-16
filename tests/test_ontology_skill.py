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
        "line_ref_count": 2,
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
    (repo / ("check" + suffix)).write_text("def test_x(): pass\n")
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
@pytest.mark.parametrize("section", ["relations", "domain"])
def test_should_reject_invalid_endpoints_at_11(contract11, side, value, section):
    repo, mapping, contract = contract11
    relation = mapping["relations"][0]
    at = "/relations/0/"
    if section == "domain":
        mapping["domain"]["relations"] = [relation]
        at = "/domain" + at
    if value is None:
        del relation[side]
    else:
        relation[side] = value
    if section == "domain":
        mapping["relations"] = []
    result = run_mapping(repo, mapping, "--contract", str(contract), "--json")
    assert result.returncode == 1, result.stdout
    assert any(
        e["pointer"].startswith(at + side) for e in json.loads(result.stdout)["errors"]
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
@pytest.mark.parametrize("section", ["relations", "domain"])
def test_should_accept_allowed_endpoints_at_11(contract11, relation, section):
    repo, mapping, contract = contract11
    entry = {"local": "example", "name": "example", "ref": "model.md", **relation}
    if section == "domain":
        mapping["domain"]["relations"] = [entry]
    else:
        mapping["relations"] = [entry]
    result = run_mapping(repo, mapping, "--contract", str(contract))
    assert result.returncode == 0, result.stdout


@pytest.mark.parametrize("version", ["1.0.0", "1.1.0"])
@pytest.mark.parametrize("common", ["unknown_relation", None, ["part_of"]])
def test_should_reject_unknown_common_when_declared_in_domain_relation(contract11, version, common):
    repo, mapping, contract = contract11
    mapping["contract"]["version"] = version
    mapping["knowledge_supply"] = {"memory_keeper": "not_connected"}
    mapping["domain"]["relations"][0].update(
        common=common, **{"from": ["Project"], "to": ["Project"]}
    )
    result = run_mapping(repo, mapping, "--contract", str(contract), "--json")
    assert result.returncode == 1, result.stdout
    assert {"pointer": "/domain/relations/0/common", "message": "unknown relation"} in json.loads(
        result.stdout
    )["errors"]


def test_should_reject_local_concept_endpoint_when_declared_in_domain_relation(contract11):
    repo, mapping, contract = contract11
    mapping["domain"]["concepts"][0]["id"] = "Note"
    mapping["domain"]["relations"][0].update(
        common="depends_on", **{"from": ["Note"], "to": ["Artifact"]}
    )
    result = run_mapping(repo, mapping, "--contract", str(contract), "--json")
    assert result.returncode == 1, result.stdout
    errors = json.loads(result.stdout)["errors"]
    assert {"pointer": "/domain/relations/0/from/0", "message": "endpoint not allowed"} in errors


@pytest.mark.parametrize("valid_ref", [True, False])
def test_should_check_only_ref_when_domain_relation_has_no_common(contract11, valid_ref):
    repo, mapping, contract = contract11
    mapping["domain"]["relations"] = [
        {"ref": "model.md" if valid_ref else "missing.md", "from": [], "to": ["Unknown"]}
    ]
    result = run_mapping(repo, mapping, "--contract", str(contract), "--json")
    assert result.returncode == (0 if valid_ref else 1), result.stdout
    errors = json.loads(result.stdout)["errors"]
    assert [error["pointer"] for error in errors] == (
        [] if valid_ref else ["/domain/relations/0/ref"]
    )


def test_should_preserve_legacy_endpoints_when_domain_relation_declares_common(contract11):
    repo, mapping, contract = contract11
    mapping["contract"]["version"] = "1.0.0"
    mapping["knowledge_supply"] = {"memory_keeper": "not_connected"}
    mapping["domain"]["relations"][0].update(
        common="realized_by", **{"from": ["Unknown"], "to": []}
    )
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
    # Keep the alternate index inside an independently committed fixture repository.
    import os

    env = {**os.environ, "GIT_INDEX_FILE": str(repo / ".git/fixture-index")}

    def git(*args):
        return subprocess.run(
            ["git", "-C", str(repo), *args], env=env, text=True, capture_output=True, check=True
        ).stdout.strip()

    git("init", "-q")
    git("add", ".")
    git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
        "-c", "commit.gpgsign=false", "commit", "-qm", "Fixture baseline")
    tree = "HEAD"
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


@pytest.mark.parametrize("section", ["relations", "domain"])
def test_should_reject_wildcard_array_even_for_unrestricted_relation(contract11, section):
    repo, mapping, contract = contract11
    mapping["relations"][0].update(common="depends_on", **{"from": ["*"], "to": "*"})
    at = "/relations/0/from"
    if section == "domain":
        mapping["domain"]["relations"] = mapping["relations"]
        mapping["relations"] = []
        at = "/domain" + at
    result = run_mapping(repo, mapping, "--contract", str(contract), "--json")
    assert result.returncode == 1
    assert any(
        e["pointer"].startswith(at) for e in json.loads(result.stdout)["errors"]
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
        "pwd",
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
    git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
        "-c", "commit.gpgsign=false", "commit", "-qm", "Fixture baseline")
    tree = "HEAD"
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
    (repo / "check.py").write_text("def future_check(): pass\n")
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


def test_should_fall_back_to_account_home_when_home_is_an_agent_home(tmp_path, monkeypatch):
    import importlib.util
    import types

    agent_home = tmp_path / "agent-home"
    agent_home.mkdir()
    account = tmp_path / "account"
    (account / ".mir").mkdir(parents=True)
    (account / ".mir/knowledge-supply.json").write_text(
        json.dumps(
            {"memory_keeper": {"command": [sys.executable, "-c", "pass"], "cwd": str(account)}}
        )
    )
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setenv("HOME", str(agent_home))
    monkeypatch.delenv("MIR_KNOWLEDGE_SUPPLY_CONFIG", raising=False)
    spec = importlib.util.spec_from_file_location("mk_query_home", MK_CLIENT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(
        module.pwd, "getpwuid", lambda uid: types.SimpleNamespace(pw_dir=str(account))
    )
    command, _cwd, timeout = module.load_config(repo.resolve())
    assert command == [sys.executable, "-c", "pass"]
    assert timeout == 30


def test_should_not_pass_secrets_or_unrelated_environment_to_the_server(mk_client, monkeypatch):
    run, config, host, repo = mk_client
    monkeypatch.setenv("OMLX_API_KEY", "fixture-secret")
    monkeypatch.setenv("SOME_SERVICE_TOKEN", "fixture-secret")
    result = run(extra=("query", "ontology"))
    assert result.returncode == 0, result.stderr
    names = set(json.loads((host / "env.json").read_text()))
    assert "PATH" in names
    assert not names & {"OMLX_API_KEY", "SOME_SERVICE_TOKEN", "MIR_KNOWLEDGE_SUPPLY_CONFIG"}


def test_should_return_pack_when_sandbox_denies_signalling_the_reaped_group(tmp_path, monkeypatch):
    import importlib.util

    # Under the Codex seatbelt, killpg on a group whose leader has exited fails with
    # EPERM instead of ESRCH; cleanup must not turn a delivered pack into "unavailable".
    monkeypatch.chdir(tmp_path)
    spec = importlib.util.spec_from_file_location("mk_query_eperm", MK_CLIENT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    def deny(pid, sig):
        raise PermissionError(1, "Operation not permitted")

    monkeypatch.setattr(module.os, "killpg", deny)
    result = module.call(
        [sys.executable, str(FAKE_MCP), "normal"], str(tmp_path), 5,
        "federation_serve", {"query": "ontology"}, "repo-agent",
    )
    assert result["schema_version"] == "mir-context-pack-v1"


@pytest.mark.parametrize("field", [
    ("canonical_index", 0), ("concepts", "Artifact", "local", 0, "ref"),
    ("vocabularies", 0, "ref"), ("relations", 0, "ref"),
    ("domain", "concepts", 0, "ref"), ("domain", "relations", 0, "ref"),
    ("domain", "invariants", 0, "ref"), ("questions", 0, "evidence", 0),
    ("error_cases", 0, "check"), ("knowledge_supply", "binding"), ("entrypoints", 0),
    ("domain", "identity_schemes", 0, "ref"),
])
def test_should_reject_unresolved_symbols_in_every_ref_field(mapping_repo, field):
    repo, mapping = mapping_repo
    mapping["domain"]["identity_schemes"] = [{"ref": "model.md#Model"}]
    cursor = mapping
    for key in field[:-1]:
        cursor = cursor[key]
    cursor[field[-1]] = "check.py#missing_symbol"
    result = run_mapping(repo, mapping, "--json")
    assert result.returncode == 1, result.stdout
    assert any("symbol anchor not found" in e["message"]
               for e in json.loads(result.stdout)["errors"])


@pytest.mark.parametrize("source, anchor", [
    *((f"{keyword} anchor_name() {{}}\n", "anchor_name") for keyword in
      ("def", "class", "function", "const", "let", "var", "interface", "type", "enum",
       "struct", "fn", "func", "val", "fun")),
    ("anchor_name = 1\n", "anchor_name"), ("anchor_name: str\n", "anchor_name"),
    ("async def test_anchor_name(): pass\n", "test_anchor_name"),
    ('test("anchor name", () => {});\n', "anchor name"),
    ("## Anchor heading ##\n", "Anchor heading"),
    ('{"anchor_name": 1}\n', "anchor_name"),
    ('anchor_name = "value"\n', "anchor_name"),
    ('[anchor.table]\n', "anchor.table"),
    ('[[anchor.table]]\n', "anchor.table"),
])
def test_should_resolve_declarations_and_reject_removed_symbols(mapping_repo, source, anchor):
    repo, mapping = mapping_repo
    suffix = ".md" if source.startswith("##") else ".json" if source.startswith("{") else ".txt"
    target = repo / ("symbols" + suffix)
    target.write_text(source)
    mapping["entrypoints"] = [target.name + "#" + anchor]
    valid = run_mapping(repo, mapping, "--json")
    assert valid.returncode == 0, valid.stdout
    # Mentioning the name as prose/comment must not keep a moved definition valid.
    target.write_text('// "' + anchor + '": only an old comment\n')
    missing = run_mapping(repo, mapping, "--json")
    assert missing.returncode == 1, missing.stdout


def test_should_report_legacy_lines_as_information_without_warnings(mapping_repo):
    repo, mapping = mapping_repo
    report = json.loads(run_mapping(repo, mapping, "--json").stdout)
    assert report["errors"] == report["warnings"] == []
    assert report["line_ref_count"] == 2
    assert "INFO 2 line-number refs" in run_mapping(repo, mapping).stdout


@pytest.mark.parametrize("anchor", ["", "test_missing"])
def test_should_reject_empty_or_unresolved_covered_symbols(mapping_repo, anchor):
    repo, mapping = mapping_repo
    (repo / "check.py").write_text("# test_missing is only a comment\ndef test_x(): pass\n")
    mapping["error_cases"][0]["check"] = "check.py#" + anchor
    result = run_mapping(repo, mapping)
    assert result.returncode == 1, result.stdout
    assert "symbol anchor not found" in result.stdout


@pytest.mark.parametrize("kind", ["line", "symbol"])
def test_should_reanchor_changed_lines_and_resolve_changed_symbols(mapping_repo, kind):
    repo, mapping = mapping_repo
    mapping["vocabularies"][0]["ref"] = "model.md#Model"
    mapping["error_cases"][0]["check"] = "check.py#test_x"
    mapping["entrypoints"] = ["check.py:1" if kind == "line" else "check.py#test_x"]
    run_mapping(repo, mapping)
    for args in (("init", "-q"), ("add", "."),
                 ("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                  "-c", "commit.gpgsign=false", "commit", "-qm", "Fixture baseline")):
        subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)
    # An unchanged legacy line stays compatible even under strict Git impact.
    before = run_query(repo, "impact", "--git-diff", "HEAD", "--strict", "--json")
    assert before.returncode == 0, before.stdout
    (repo / "check.py").write_text("# moved down\ndef test_x(): pass\n")
    moved = run_query(repo, "impact", "--git-diff", "HEAD", "--strict", "--json")
    if kind == "line":
        assert moved.returncode == 1, moved.stdout
        assert "re-anchor to a symbol: /entrypoints/0" in moved.stdout
    else:
        assert moved.returncode == 0, moved.stdout
        (repo / "check.py").write_text("def test_other(): pass\n")
        missing = run_query(repo, "impact", "--git-diff", "HEAD", "--strict", "--json")
        assert missing.returncode == 1, missing.stdout
        assert "symbol anchor not found" in missing.stdout



def test_should_not_resolve_python_comments_as_markdown_headings(mapping_repo):
    repo, mapping = mapping_repo
    (repo / "check.py").write_text("# removed_name\ndef test_x(): pass\n")
    mapping["entrypoints"] = ["check.py#removed_name"]
    result = run_mapping(repo, mapping)
    assert result.returncode == 1, result.stdout


@pytest.mark.parametrize("suffix, source, anchor", [
    (".md", "## Authority and scope\n", "authority-and-scope"),
    (".md", "## 6. Component Model\n", "6-component-model"),
    (".md", "## Ninth inspection round (2026-10-12)\n",
     "ninth-inspection-round-2026-10-12"),
    (".md", "## Repeat\n## Repeat\n", "repeat-1"),
    (".md", "## Repeat\n## Repeat-1\n## Repeat\n", "repeat-2"),
    (".json", '{"$defs": {"source_artifact": {}}}', "$defs/source_artifact"),
    (".json", '{"a": {"b": {"c": null}}}', "/a/b/c"),
    (".json", '{"a/b": {"~name": [false]}}', "a~1b/~0name/0"),
    (".json", '{"a/b": {}}', "a~1b"),
    (".kt", "data class AnchorName(val x: Int)\n", "AnchorName"),
    (".kt", "sealed class AnchorName\n", "AnchorName"),
    (".kt", "abstract class AnchorName\n", "AnchorName"),
    (".dart", "final class AnchorName {}\n", "AnchorName"),
    (".kt", "override fun anchorName() {}\n", "anchorName"),
    (".kt", "suspend fun anchorName() {}\n", "anchorName"),
    (".kt", "private suspend fun anchorName() {}\n", "anchorName"),
    (".kt", "internal data class AnchorName(val x: Int)\n", "AnchorName"),
    (".dart", "abstract interface class AnchorName {}\n", "AnchorName"),
    (".dart", "@Deprecated('old') final class AnchorName {}\n", "AnchorName"),
    (".kt", "@Synchronized internal fun <T> anchorName(block: () -> T): T = block()\n",
     "anchorName"),
    (".kt", "object AnchorName {}\n", "AnchorName"),
    (".sh", "anchor_name() {\n  :\n}\n", "anchor_name"),
    (".sh", "anchor_name () {\n  :\n}\n", "anchor_name"),
])
def test_should_resolve_fleet_anchor_forms_and_reject_mentions(
    mapping_repo, suffix, source, anchor,
):
    repo, mapping = mapping_repo
    target = repo / ("fleet" + suffix)
    mapping["entrypoints"] = [target.name + "#" + anchor]
    target.write_text(source)
    valid = run_mapping(repo, mapping, "--json")
    assert valid.returncode == 0, valid.stdout
    if suffix == ".sh":
        for declaration in ("function anchor_name {", "function anchor_name() {"):
            target.write_text(declaration + "\n  :\n}\n")
            assert run_mapping(repo, mapping).returncode == 0
    # Removal must invalidate the same anchor, even if a comment/prose still mentions it.
    mentions = ([f"Prose mentions {anchor}.\n",
                 f"<!--\n{source}\n-->\n", f"```md\n{source}\n```\n"] if suffix == ".md"
                else [json.dumps({"mention": anchor}),
                      '{"elsewhere": {"c": null}, "a": {"b": {"wrong": null}}}']
                if suffix == ".json" else [f"# {anchor}\n", f"// {source}"])
    if suffix in (".kt", ".dart"):
        mentions.extend([f"/*\n{source}\n*/\n",
                         f"A class {anchor} appears in prose.\n"])
    for mention in mentions:
        target.write_text(mention)
        missing = run_mapping(repo, mapping, "--json")
        assert missing.returncode == 1, (mention, missing.stdout)
        assert "symbol anchor not found" in missing.stdout
    # Prefix names and malformed/out-of-range pointers must never count as the exact anchor.
    invalid = ("/a/b/../c", "/a/b/c/child", "a~2b/~0name/0", "a~1b/~0name/01",
               "a~1b/~0name/-", "a~1b/~0name/1") if suffix == ".json" else (anchor + "_missing",)
    target.write_text(source)
    for missing_anchor in invalid:
        mapping["entrypoints"] = [target.name + "#" + missing_anchor]
        assert run_mapping(repo, mapping).returncode == 1


@pytest.mark.parametrize("source", ["docs/adr-091.md", "src/consumer.py"])
def test_should_select_declared_invariant_checks_without_execution(
    mapping_repo, source, monkeypatch,
):
    repo, mapping = mapping_repo
    target = repo / source
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("# Definition\n")
    (repo / "unaffected.md").write_text("# Other\n")
    (repo / "checks.py").write_text(
        "from pathlib import Path\nPath('ran-invariant').touch()\n"
        "def test_invariant(): pass\ndef test_other(): pass\n"
    )
    check = "checks.py#test_invariant"
    mapping["domain"]["invariants"] = [
        {"ref": source, "check": check},
        {"ref": source, "check": check},
        {"ref": "unaffected.md", "check": "checks.py#test_other"},
        {"ref": source},
    ]
    run_mapping(repo, mapping)
    # Exercise the byte-copied consumer runner against the candidate checker too.
    runner = repo / "scripts/mir_ontology.py"
    runner.parent.mkdir()
    runner.write_bytes((SKILL / "scripts/mir_ontology_runner.py").read_bytes())
    monkeypatch.setenv("MIR_ONTOLOGY_CHECKER", str(CHECKER))
    result = subprocess.run(
        [sys.executable, str(runner), "impact", "--paths", source, "--strict", "--json"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout
    report = json.loads(result.stdout)
    assert report["checks_to_run"] == [check]
    assert report["undeclared_check_links"] == [{
        "pointer": "/domain/invariants/3", "ref": source,
        "message": "no check declared; no test link inferred",
    }]
    assert not (repo / "ran-invariant").exists()


@pytest.mark.parametrize("check", ["missing.py#test_x", ".", 7])
def test_should_reject_invalid_declared_invariant_check(mapping_repo, check):
    repo, mapping = mapping_repo
    mapping["domain"]["invariants"][0]["check"] = check
    result = run_mapping(repo, mapping, "--json")
    assert result.returncode == 1, result.stdout
    assert any(e["pointer"] == "/domain/invariants/0/check"
               for e in json.loads(result.stdout)["errors"])
