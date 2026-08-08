from __future__ import annotations

import json
from pathlib import Path

from mir.cli import bootstrap_adoption as adoption_cli

ROOT = Path(__file__).resolve().parents[1]


# @spec CR-003 FR-006 IR-002 QR-002
def test_should_make_zero_writes_when_existing_repository_contract_is_missing(
    tmp_path, capsys
) -> None:
    before = sorted(tmp_path.rglob("*"))
    code = adoption_cli.main(["--project-root", str(tmp_path), "--json", "--apply"])
    report = json.loads(capsys.readouterr().out)

    assert code == 2
    assert report["changed_paths"] == []
    assert sorted(tmp_path.rglob("*")) == before


# @spec CR-003 IR-002
def test_should_expose_only_single_root_explicit_apply_mutation_flags() -> None:
    bootstrap = __import__("mir.cli.bootstrap", fromlist=["_parse"])
    adoption = __import__("mir.cli.bootstrap_adoption", fromlist=["_parse"])
    capability = __import__("mir.cli.capability", fromlist=["_parser"])

    assert bootstrap._parse(["--profile", "code_app"]).project_root is not None
    assert adoption._parse([]).apply is False
    parsed = capability._parser().parse_args(["sync"])
    assert parsed.apply is False
    assert parsed.project_root is not None


# @spec CR-003 QR-004
def test_should_never_infer_authority_from_a_local_catalog() -> None:
    hook = (ROOT / ".claude/hooks/pre-commit-verification.sh").read_text(
        encoding="utf-8"
    )

    assert "_MIR_FLEET_MANAGER" not in hook
    assert "repo-agent-management.json" not in hook
