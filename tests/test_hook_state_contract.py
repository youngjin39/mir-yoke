from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest

from mir.cli import bootstrap_adoption as adoption_cli

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / ".claude/hooks/_lib/bootstrap-gate.sh"
SETTINGS = ".claude/settings.json"


def _shell(function: str, path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-c", '. "$1"; "$2" "$3"', "bash", str(HELPER), function, str(path)],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "MIR_NATIVE_HOOKS": "0"},
    )


@pytest.mark.parametrize(
    "command",
    [
        "echo ordinary",
        'echo \\n \\t \\\\ "quoted"',
        "echo \uac00 \U0001f680 \u007f \u0085 \u2028",
    ],
)
def test_settings_digest_matches_sorted_jq_with_exactly_one_newline(tmp_path, command):
    settings = tmp_path / "settings.json"
    settings.write_text(
        json.dumps({"theme": "dark", "hooks": {"Z": [{"command": command}], "A": []}}),
        encoding="utf-8",
    )
    canonical = subprocess.run(
        ["jq", "-S", "-c", "{hooks: .hooks}", str(settings)],
        capture_output=True,
        check=True,
    ).stdout
    assert canonical.endswith(b"\n") and not canonical.endswith(b"\n\n")
    expected = hashlib.sha256(canonical).hexdigest()
    assert adoption_cli.evidence_digest(SETTINGS, settings) == expected
    shell = _shell("_mir_bootstrap_settings_hook_sha256", settings)
    assert shell.returncode == 0, shell.stderr
    assert shell.stdout == expected + "\n"


@pytest.mark.parametrize("number", ["1.0", "1e-7", "9007199254740993", "-0.0"])
def test_settings_digest_matches_jq_number_serialization(tmp_path, number):
    settings = tmp_path / "settings.json"
    settings.write_text('{"hooks":{"value":' + number + "}}", encoding="utf-8")
    shell = _shell("_mir_bootstrap_settings_hook_sha256", settings)
    assert shell.returncode == 0, shell.stderr
    assert adoption_cli.evidence_digest(SETTINGS, settings) + "\n" == shell.stdout


@pytest.mark.parametrize("body", ["[]", "null", "{}", '{"hooks":{}}', '{"hooks":[]}', "{"])
def test_settings_digest_rejects_missing_empty_and_malformed_hooks(tmp_path, body):
    settings = tmp_path / "settings.json"
    settings.write_text(body, encoding="utf-8")
    assert _shell("_mir_bootstrap_settings_hook_sha256", settings).returncode != 0
    with pytest.raises(adoption_cli.AdoptionError):
        adoption_cli.evidence_digest(SETTINGS, settings)


def _adoption_fixture(root: Path, *, whole_file: bool = False) -> Path:
    settings = root / SETTINGS
    settings.parent.mkdir(parents=True)
    settings.write_text('{"hooks":{"SessionStart":[{"command":"echo safe"}]},"theme":"dark"}\n')
    manifest = root / "config/bootstrap-adoption.json"
    manifest.parent.mkdir()
    manifest.write_text(
        json.dumps(
            {
                "mir_yoke_source_commit": "a" * 40,
                "surfaces": {"bootstrap_start_gate": {"evidence_paths": [SETTINGS]}},
            }
        )
    )
    receipt = {
        "status": "ready",
        "mode": "existing_repository_adoption",
        "source": {"mir_yoke_commit": "a" * 40},
        "manifest": {"sha256": hashlib.sha256(manifest.read_bytes()).hexdigest()},
        "evidence": [
            {
                "path": SETTINGS,
                "sha256": (
                    hashlib.sha256(settings.read_bytes()).hexdigest()
                    if whole_file
                    else hashlib.sha256(
                        b'{"hooks":{"SessionStart":[{"command":"echo safe"}]}}\n'
                    ).hexdigest()
                ),
            }
        ],
    }
    (root / ".mir").mkdir()
    (root / ".mir/bootstrap-receipt.json").write_text(json.dumps(receipt))
    return settings


def test_hook_scoped_receipt_survives_preference_and_key_order_changes(tmp_path):
    settings = _adoption_fixture(tmp_path)
    assert _shell("mir_bootstrap_gate_state", tmp_path).stdout == "ready\n"
    settings.write_text('{"theme":"light","hooks":{"SessionStart":[{"command":"echo safe"}]}}')
    assert _shell("mir_bootstrap_gate_state", tmp_path).stdout == "ready\n"
    settings.write_text('{"hooks":{"SessionStart":[{"command":"echo changed"}]}}')
    verdict = _shell("mir_bootstrap_gate_state", tmp_path)
    assert (verdict.returncode, verdict.stdout) == (1, "invalid\n")


def test_old_whole_file_receipts_remain_valid(tmp_path):
    settings = _adoption_fixture(tmp_path, whole_file=True)
    assert _shell("mir_bootstrap_gate_state", tmp_path).stdout == "ready\n"
    settings.write_text('{"hooks":{"SessionStart":[{"command":"echo changed"}]}}')
    assert _shell("mir_bootstrap_gate_state", tmp_path).stdout == "invalid\n"


@pytest.mark.parametrize("body", ["[]", "{}", '{"hooks":{}}', "{"])
def test_bad_settings_fail_closed_with_hook_scoped_receipts(tmp_path, body):
    settings = _adoption_fixture(tmp_path)
    settings.write_text(body)
    assert _shell("mir_bootstrap_gate_state", tmp_path).stdout == "invalid\n"


def test_receipt_collection_hashes_only_claude_settings_by_hooks(tmp_path):
    settings = _adoption_fixture(tmp_path)
    other = tmp_path / ".codex/hooks.json"
    other.parent.mkdir()
    other.write_bytes(settings.read_bytes())
    evidence = adoption_cli._evidence_digests(
        tmp_path,
        {
            "gate": {"evidence_paths": [SETTINGS, ".codex/hooks.json"]},
        },
    )
    hashes = {row["path"]: row["sha256"] for row in evidence}
    assert (
        hashes[SETTINGS]
        == hashlib.sha256(b'{"hooks":{"SessionStart":[{"command":"echo safe"}]}}\n').hexdigest()
    )
    assert hashes[".codex/hooks.json"] == hashlib.sha256(other.read_bytes()).hexdigest()


def test_settings_digest_reports_unavailable_jq(tmp_path, monkeypatch):
    settings = tmp_path / "settings.json"
    settings.write_text('{"hooks":{"SessionStart":[]}}')
    monkeypatch.setenv("PATH", str(tmp_path / "missing-bin"))
    with pytest.raises(adoption_cli.AdoptionError, match="cannot digest settings"):
        adoption_cli.evidence_digest(SETTINGS, settings)
