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
        "error_cases": [{"id": "E01", "status": "covered", "check": "model.md:2"}],
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
    assert imports <= {"__future__", "argparse", "hashlib", "json", "pathlib", "re", "sys"}


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
