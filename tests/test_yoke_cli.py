from __future__ import annotations

import json
from pathlib import Path

from mir.cli.yoke import main

ROOT = Path(__file__).resolve().parents[1]


def test_should_build_distribution_when_yoke_build_is_called(
    tmp_path: Path,
    capsys,
) -> None:
    output = tmp_path / "dist"

    status = main(
        [
            "build",
            "--source-root",
            str(ROOT),
            "--output-dir",
            str(output),
            "--version",
            "0.9.0-test",
            "--json",
        ]
    )

    assert status == 0
    assert json.loads(capsys.readouterr().out)["artifact_count"] == 5
    assert (output / "manifest.json").is_file()


def test_should_write_plan_without_mutating_target_when_yoke_plan_is_called(
    tmp_path: Path,
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    output = tmp_path / "plan.json"

    status = main(
        [
            "plan",
            str(target),
            "--source-root",
            str(ROOT),
            "--profile",
            "code",
            "--output",
            str(output),
            "--json",
        ]
    )

    assert status == 0
    assert output.is_file()
    assert list(target.iterdir()) == []


def test_should_apply_saved_plan_when_yoke_apply_is_called(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    output = tmp_path / "plan.json"
    assert main(
        [
            "plan",
            str(target),
            "--source-root",
            str(ROOT),
            "--output",
            str(output),
            "--json",
        ]
    ) == 0

    status = main(
        [
            "apply",
            str(target),
            "--source-root",
            str(ROOT),
            "--plan",
            str(output),
            "--json",
        ]
    )

    assert status == 0
    assert (target / "HARNESS.md").is_file()
    assert (target / ".mir/local-state.json").is_file()


def test_should_install_provider_by_digest_when_yoke_provider_is_called(
    tmp_path: Path,
    capsys,
) -> None:
    status = main(
        [
            "provider",
            "install",
            "--source-root",
            str(ROOT),
            "--provider-home",
            str(tmp_path / "providers-home"),
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    installed = Path(payload["provider"])
    assert status == 0
    assert installed.parent == tmp_path / "providers-home/providers"
    assert installed.name == payload["content_digest"]
