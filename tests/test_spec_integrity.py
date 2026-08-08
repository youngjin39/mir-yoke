from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "spec"
REQ_ID = re.compile(r"^(?:CR|FR|IR|QR)-\d{3}$")
NODE_ID = re.compile(
    r"^(?:FEAT|CR|FR|IR|QR|UC|IF|IT|MOD|RC|CN|SR|DS|ADR|TASK|CHK|GAP|CONFLICT)-[A-Z0-9-]+$"
)


def _load(relative: str):
    return yaml.safe_load((SPEC / relative).read_text(encoding="utf-8"))


def _records(pattern: str, key: str | None = None) -> list[dict]:
    records: list[dict] = []
    for path in sorted(SPEC.glob(pattern)):
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        records.extend(payload[key] if key else [payload])
    return records


def _all_tbd_values(value) -> list[int]:
    found: list[int] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "tbd":
                found.append(item)
            found.extend(_all_tbd_values(item))
    elif isinstance(value, list):
        for item in value:
            found.extend(_all_tbd_values(item))
    return found


# @spec QR-004
def test_should_keep_spec_index_graph_and_coverage_consistent() -> None:
    index = _load("index.yaml")
    requirements = _records("req/*.yaml", "requirements")
    features = _records("feat/*.yaml")
    use_cases = _records("uc/*.yaml")
    interfaces = _records("iface/*.yaml")
    modules = _records("mod/*.yaml")
    tasks = _load("tasks.yaml")["tasks"]
    gaps = _load("gaps.yaml")["gaps"]

    assert index["counts"]["requirements"] == {
        "total": len(requirements),
        **{
            status: Counter(item["status"] for item in requirements)[status]
            for status in ("ready", "incomplete", "blocked")
        },
    }
    assert index["counts"]["features"] == {
        "total": len(features),
        **{
            status: Counter(item["status"] for item in features)[status]
            for status in ("done", "building", "planned", "deprecated")
        },
    }
    assert index["counts"]["use_cases"] == len(use_cases)
    assert index["counts"]["interfaces"] == len(interfaces)
    assert index["counts"]["modules"] == len(modules)
    assert index["counts"]["tasks"] == {
        "total": len(tasks),
        **{
            status: Counter(item["status"] for item in tasks)[status]
            for status in ("todo", "doing", "done", "blocked")
        },
    }
    assert index["counts"]["gaps"] == {
        "total": len(gaps),
        "blocking": sum(bool(item["blocking"]) for item in gaps),
    }
    assert all(value == 0 for value in _all_tbd_values(_load("coverage.yaml")))


# @spec QR-004
def test_should_bind_every_ready_requirement_to_feature_module_test_and_anchor() -> None:
    requirements = _records("req/*.yaml", "requirements")
    requirement_ids = {item["id"] for item in requirements}
    features = _records("feat/*.yaml")
    use_cases = _records("uc/*.yaml")
    interfaces = _records("iface/*.yaml")
    modules = _records("mod/*.yaml")
    tasks = _load("tasks.yaml")["tasks"]
    checks = _load("checks.yaml")["checks"]
    gaps = _load("gaps.yaml")["gaps"]
    concepts = _records("concepts/*.yaml")
    data_stores = _load("views/data.yaml")["stores"]

    defined = {
        item["id"]
        for group in (
            requirements,
            features,
            use_cases,
            interfaces,
            modules,
            tasks,
            checks,
            gaps,
            concepts,
            data_stores,
        )
        for item in group
    }
    defined.update(item["id"] for interface in interfaces for item in interface.get("items", []))
    edges = _load("graph.yaml")["edges"]

    for source, relation, target in edges:
        if NODE_ID.match(str(source)):
            assert source in defined, source
        if NODE_ID.match(str(target)):
            assert target in defined, target
        if relation in {"implemented_in", "verified_by"}:
            path = str(target).split("::", 1)[0]
            assert (ROOT / path).exists(), target
            if "::" in str(target):
                symbol = str(target).split("::", 1)[1]
                assert f"def {symbol}(" in (ROOT / path).read_text(encoding="utf-8")

    relations = {(source, relation) for source, relation, _ in edges}
    for requirement in requirements:
        requirement_id = requirement["id"]
        assert REQ_ID.match(requirement_id)
        assert requirement["status"] == "ready"
        assert any(
            source.startswith("FEAT-") and relation == "has_req" and target == requirement_id
            for source, relation, target in edges
        )
        assert (requirement_id, "realized_by") in relations
        assert (requirement_id, "verified_by") in relations

    anchor_text = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for base in (ROOT / "src", ROOT / "tools", ROOT / "scripts", ROOT / "tests")
        for path in base.rglob("*")
        if path.is_file() and path.suffix in {".py", ".sh"}
    )
    anchored = set(re.findall(r"(?:CR|FR|IR|QR)-\d{3}", anchor_text))
    assert anchored >= requirement_ids
