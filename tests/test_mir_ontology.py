"""The maintainer pytest gate consumes Yoke's own ontology map without MK."""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts/mir_ontology.py"


def run(repo, *args, env=None):
    return subprocess.run(
        [sys.executable, str(repo / "scripts/mir_ontology.py"), *args],
        capture_output=True, text=True, env=env,
    )


def gate(repo):
    for args in (("mapping",), ("impact", "--git-diff", "--strict")):
        result = run(repo, *args)
        print(result.stdout, end="")
        assert result.returncode == 0, result.stdout + result.stderr
        if args == ("mapping",):
            assert "0 errors, 0 warnings" in result.stdout, result.stdout
    return result.stdout


def test_should_validate_mapping_and_print_selected_checks():
    output = gate(ROOT)
    assert "checks to run" in output


@pytest.fixture
def own_repo(tmp_path):
    """Copy only declared source refs; fixture Git must never inherit the outer tree."""
    repo = tmp_path / "yoke"
    repo.mkdir()
    mapping = json.loads((ROOT / ".mir/ontology-map.json").read_text())

    def refs(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key in {"ref", "check"}:
                    yield item
                elif key in {"canonical_index", "entrypoints", "evidence"}:
                    yield from item
                else:
                    yield from refs(item)
        elif isinstance(value, list):
            for item in value:
                yield from refs(item)

    for ref in {*refs(mapping), ".mir/ontology-map.json", "scripts/mir_ontology.py"}:
        relative = re.split(r"#|:\d", ref)[0]
        source, target = ROOT / relative, repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            target.mkdir(exist_ok=True)
        else:
            shutil.copyfile(source, target)
    shutil.copytree(
        ROOT / "plugins/mir-core/skills/ontology",
        repo / "plugins/mir-core/skills/ontology", dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    for args in (
        ("init",), ("add", "."),
        ("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
         "-c", "commit.gpgsign=false", "commit", "-m", "Fixture baseline"),
    ):
        subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)
    return repo


@pytest.mark.parametrize("failure", ["stale", "version", "direction", "endpoint"])
def test_should_fail_gate_when_own_map_is_stale_or_incompatible(own_repo, failure):
    gate(own_repo)
    if failure == "stale":
        (own_repo / "ARCHITECTURE.md").unlink()
        impact = run(own_repo, "impact", "--git-diff", "--strict")
        assert impact.returncode == 1 and "ARCHITECTURE.md" in impact.stdout
    else:
        path = own_repo / ".mir/ontology-map.json"
        mapping = json.loads(path.read_text())
        if failure == "version":
            mapping["contract"]["version"] = "99.0.0"
        elif failure == "direction":
            relation = mapping["relations"][0]
            relation["from"], relation["to"] = relation["to"], relation["from"]
        else:
            mapping["relations"][0]["from"] = ["Run"]
        path.write_text(json.dumps(mapping))
    with pytest.raises(AssertionError):
        gate(own_repo)


def test_should_select_own_checks_without_execution(own_repo):
    check = own_repo / "tests/test_mir_ontology.py"
    check.write_text(check.read_text() + '\nraise RuntimeError("Must not execute selection")\n')
    output = gate(own_repo)
    assert "tests/test_mir_ontology.py#test_should_select_own_checks_without_execution" in output
    assert "selection only" in output


def test_should_continue_local_gate_when_mk_config_is_missing(own_repo):
    env = dict(os.environ, MIR_KNOWLEDGE_SUPPLY_CONFIG=str(own_repo.parent / "missing.json"))
    result = run(own_repo, "mk", "query", "cross-project evidence", "--soft", env=env)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["status"] == "unavailable"
    assert "checks to run" in gate(own_repo)


def test_should_forward_lookup_and_report_missing_distribution(own_repo):
    result = run(own_repo, "lookup", "capability", "--limit", "1", "--json")
    assert result.returncode == 0, result.stderr
    json.loads(result.stdout)
    shutil.rmtree(own_repo / "plugins/mir-core/skills/ontology/scripts")
    result = run(own_repo, "mapping")
    assert result.returncode == 2
    assert "ontology distribution" in result.stderr
