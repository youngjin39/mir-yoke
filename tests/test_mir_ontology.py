"""The maintainer pytest gate consumes Yoke's own ontology map without MK."""

import json
import os
import re
import shutil
import subprocess
import sys
from hashlib import sha256
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


def test_should_use_own_domain_evidence_in_bounded_handoff(own_repo):
    """Selection/evidence rehearsal, not a live agent or runtime quality comparison."""
    mapping_path = own_repo / ".mir/ontology-map.json"
    mapping = json.loads(mapping_path.read_text())
    question = mapping["questions"][0]
    assert question["id"] == "Q1"
    selected = run(own_repo, "lookup", question["question"], "--limit", "1", "--json")
    assert selected.returncode == 0, selected.stderr
    lookup = json.loads(selected.stdout)
    match, = lookup["matches"]
    assert match["pointer"] == "/questions/0"
    assert match["entry"] == question
    assert match["evidence"] == question["evidence"]
    assert lookup["contract"]["version"] == "1.1.0"

    # Same source bytes and question for both arms; the map adds provenance,
    # not a fabricated improvement in the raw profile answer.
    sources = {ref: (own_repo / ref).read_text() for ref in question["evidence"]}
    instruction = own_repo / "plugins/mir-core/skills/ontology/SKILL.md"
    apply_step = instruction.read_text().split("5. Apply the finding", 1)[1].split("6.", 1)[0]
    packet = {
        "question": question["question"], "sources": sources,
        "source_sha256": {ref: sha256(text.encode()).hexdigest()
                          for ref, text in sources.items()},
        "contract": lookup["contract"],
        "map_sha256": sha256(mapping_path.read_bytes()).hexdigest(),
        "selection": match,
        "instruction": "plugins/mir-core/skills/ontology/SKILL.md",
        "instruction_sha256": sha256(instruction.read_bytes()).hexdigest(),
        "instruction_excerpt": "5. Apply the finding" + apply_step,
        "implementation_sha256": sha256(
            (own_repo / "src/mir/core/capabilities/config.py").read_bytes()
        ).hexdigest(),
        "runtime": {"kind": "isolated-python-fixture", "version": sys.version},
        "checker_sha256": sha256(
            (own_repo / "plugins/mir-core/skills/ontology/scripts/ontology_check.py").read_bytes()
        ).hexdigest(),
    }
    # The child receives only Q1 and three bounded source bodies, not the map,
    # supplier checkout, MK, credentials, installation or live discovery receipts.
    child = r'''
import json, runpy, sys
from hashlib import sha256
from pathlib import Path
p = json.load(sys.stdin)
assert p["contract"]["id"] == "mir.common-semantics"
assert p["contract"]["version"] == "1.1.0"
assert "existing design, implementation, knowledge or review" in p["instruction_excerpt"]
assert "grant no authority" in p["instruction_excerpt"]
implementation = Path("src/mir/core/capabilities/config.py").read_bytes()
assert sha256(implementation).hexdigest() == p["implementation_sha256"]
assert len(p["sources"]) == 3
for ref, text in p["sources"].items():
    assert sha256(text.encode()).hexdigest() == p["source_sha256"][ref]
    assert Path(ref).read_text() == text
config = runpy.run_path("src/mir/core/capabilities/config.py")["load_capability_config"](
    Path("config/capability-sources.json"))
profiles = {}
for alias in ("code", "content"):
    name, pack = config.resolve_profile(alias)
    profiles[alias] = {"profile": name, "plugins": list(pack.plugins)}
selection = p["selection"]
if selection is not None:
    assert selection["entry"]["question"] == p["question"]
    assert selection["evidence"] == list(p["sources"])
    assert "Repository-unique instructions" in p["sources"][selection["evidence"][1]]
print(json.dumps({
    "received": p, "profiles": profiles,
    "integration_owner": config.component_policy["project_integration"],
    "integration_delivery": {key: value["delivery"]
                             for key, value in config.project_integrations.items()},
    "evidence_basis": [] if selection is None else selection["evidence"],
    "scope": "synthetic selection/evidence only",
    "uncertainty": ["No installation, loading, tools, live agent or runtime discovery observed"],
}))
'''

    def receive(payload):
        return subprocess.run(
            [sys.executable, "-I", "-c", child], cwd=own_repo,
            input=json.dumps(payload), capture_output=True, text=True,
        )

    baseline = receive({**packet, "selection": None})
    handed = receive(packet)
    assert baseline.returncode == handed.returncode == 0, baseline.stderr + handed.stderr
    without_map, with_map = json.loads(baseline.stdout), json.loads(handed.stdout)
    assert with_map["received"] == packet  # Actual child-received version/provenance.
    for key in ("question", "sources", "source_sha256", "runtime"):
        assert without_map["received"][key] == with_map["received"][key]
    assert without_map["profiles"] == with_map["profiles"] == {
        "code": {"profile": "code_app",
                 "plugins": ["mir-core", "mir-code", "mir-lifecycle-hooks"]},
        "content": {"profile": "content_workspace",
                    "plugins": ["mir-core", "mir-content", "mir-lifecycle-hooks"]},
    }
    assert without_map["evidence_basis"] == []
    assert with_map["evidence_basis"] == question["evidence"]
    assert with_map["integration_owner"] == "target-local-only"
    assert with_map["integration_delivery"] == {
        "hooks": "target-local-generated", "mcp_servers": "target-local-opt-in-generated",
    }
    assert with_map["scope"] == "synthetic selection/evidence only"
    assert len(json.dumps(packet).encode()) < 64 * 1024
    assert with_map["uncertainty"] == without_map["uncertainty"]
    incompatible = {**packet, "contract": {**packet["contract"], "version": "99.0.0"}}
    assert receive(incompatible).returncode != 0
    assert receive({**packet, "source_sha256": dict.fromkeys(sources, "stale")}).returncode != 0

    # The existing maintainer workflow must select this proof after its domain
    # source changes. It selects a check; it does not execute or accept it.
    source = own_repo / "docs/decisions/adr-90-role-plugins-and-common-hooks.md"
    source.write_text(source.read_text() + "\n")
    impact = run(own_repo, "impact", "--git-diff", "--strict")
    assert impact.returncode == 0, impact.stdout + impact.stderr
    check = "tests/test_mir_ontology.py#test_should_use_own_domain_evidence_in_bounded_handoff"
    assert check in impact.stdout
    assert "/domain/invariants/2" in impact.stdout
    print(json.dumps({
        "question": packet["question"], "map_sha256": packet["map_sha256"],
        "contract": packet["contract"], "runtime": packet["runtime"],
        "source_sha256": packet["source_sha256"],
        "checker_sha256": packet["checker_sha256"],
        "instruction_sha256": packet["instruction_sha256"],
        "implementation_sha256": packet["implementation_sha256"],
        "selection": match["pointer"], "profiles": with_map["profiles"],
        "integration_owner": with_map["integration_owner"],
        "scope": with_map["scope"], "uncertainty": with_map["uncertainty"],
    }, sort_keys=True))


def test_should_forward_h1_inventory_in_checkout_without_mk():
    result = run(ROOT, "mapping", "--json", "--handoff", "scripts/mir_ontology.py")
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["mapping_version"] == report["contract_version"] == "1.1.0"
    block = report["handoff"]
    assert block["sources"][0]["sha256"] == sha256(RUNNER.read_bytes()).hexdigest()
    assert any(item["pointer"] == "/sources/0/sha256" for item in block["pin_inventory"])
    assert result.stderr == ""
