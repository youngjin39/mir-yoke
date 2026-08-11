from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest

from scripts.observe_project_agent_kit import collect, prepare
from scripts.verify_project_agent_kit_evidence import (
    _verify_run_artifacts,
    _verify_target_checkout,
    content_hashes,
    tracked_tree_sha256,
    validate_evidence_payload,
    verify_evidence_root,
)

ROOT = Path(__file__).resolve().parents[1]


def _evidence(
    runtime: str,
    prompt_template_sha256: str,
    purpose_sha256: str,
    rendered_prompt_sha256: str,
    recipe_sha256: str,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "runtime": {"name": runtime, "version": "verified-runtime-version"},
        "binding": {
            "prompt_template_sha256": prompt_template_sha256,
            "purpose_sha256": purpose_sha256,
            "rendered_prompt_sha256": rendered_prompt_sha256,
            "recipe_sha256": recipe_sha256,
            "provider_revision": _git(ROOT, "rev-parse", "HEAD"),
        },
        "observation": {
            "run_id": f"{runtime}-clean-room",
            "before_empty": True,
            "outside_existing_worktree": True,
            "provider_before_sha256": "a" * 64,
            "provider_after_sha256": "a" * 64,
            "outside_before_sha256": "b" * 64,
            "outside_after_sha256": "b" * 64,
            "target_tree_sha256": "c" * 64,
            "target_bundle_sha256": "f" * 64,
            "verification_log_sha256": "d" * 64,
            "runtime_log_sha256": "1" * 64,
        },
        "result": {
            "ready_marker": "READY_FOR_DEVELOPMENT_PLANNING",
            "artifacts": "pass",
            "generated_parity": "pass",
            "read_only_reviewer": "pass",
            "lint_exit_code": 0,
            "build_exit_code": 0,
            "test_exit_code": 0,
            "hook_direct_exit_code": 0,
            "hook_commit_invocations": 1,
            "branch": "main",
            "commit_count": 1,
            "commit_message": "chore(harness): bootstrap project agent kit",
            "initial_commit": "e" * 40,
            "worktree_clean": True,
            "remote_count": 0,
            "product_implementation_files": 0,
        },
    }


def test_published_prompt_file_matches_the_root_short_prompt() -> None:
    prompt = (ROOT / "recipes/project-agent-kit/prompt.txt").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert prompt.strip() in readme


def test_evidence_binds_to_the_published_prompt_and_recipe() -> None:
    prompt_template_sha256, purpose_sha256, rendered_prompt_sha256, recipe_sha256 = (
        content_hashes(ROOT)
    )
    payload = _evidence(
        "claude",
        prompt_template_sha256,
        purpose_sha256,
        rendered_prompt_sha256,
        recipe_sha256,
    )

    validate_evidence_payload(
        payload,
        expected_runtime="claude",
        prompt_template_sha256=prompt_template_sha256,
        purpose_sha256=purpose_sha256,
        rendered_prompt_sha256=rendered_prompt_sha256,
        recipe_sha256=recipe_sha256,
    )


@pytest.mark.parametrize(
    ("path", "value"),
    (
        (("binding", "prompt_template_sha256"), "0" * 64),
        (("binding", "rendered_prompt_sha256"), "0" * 64),
        (("binding", "recipe_sha256"), "0" * 64),
        (("observation", "before_empty"), False),
        (("observation", "outside_existing_worktree"), False),
        (("observation", "provider_after_sha256"), "0" * 64),
        (("observation", "outside_after_sha256"), "0" * 64),
        (("result", "read_only_reviewer"), "fail"),
        (("result", "lint_exit_code"), 1),
        (("result", "hook_commit_invocations"), 0),
        (("result", "commit_count"), 2),
        (("result", "remote_count"), 1),
        (("result", "product_implementation_files"), 1),
    ),
)
def test_evidence_rejects_unproven_clean_room_claims(
    path: tuple[str, str], value: object
) -> None:
    prompt_template_sha256, purpose_sha256, rendered_prompt_sha256, recipe_sha256 = (
        content_hashes(ROOT)
    )
    payload = _evidence(
        "claude",
        prompt_template_sha256,
        purpose_sha256,
        rendered_prompt_sha256,
        recipe_sha256,
    )
    changed = copy.deepcopy(payload)
    changed[path[0]][path[1]] = value  # type: ignore[index]

    with pytest.raises(ValueError):
        validate_evidence_payload(
            changed,
            expected_runtime="claude",
            prompt_template_sha256=prompt_template_sha256,
            purpose_sha256=purpose_sha256,
            rendered_prompt_sha256=rendered_prompt_sha256,
            recipe_sha256=recipe_sha256,
        )


def test_release_evidence_requires_one_claude_and_one_codex_run(tmp_path: Path) -> None:
    prompt_template_sha256, purpose_sha256, rendered_prompt_sha256, recipe_sha256 = (
        content_hashes(ROOT)
    )
    for runtime in ("claude", "codex"):
        _write_run_evidence(tmp_path, runtime)

    evidence_root = tmp_path / "evidence"
    report = verify_evidence_root(evidence_root, ROOT)
    assert report == {
        "prompt_template_sha256": prompt_template_sha256,
        "purpose_sha256": purpose_sha256,
        "rendered_prompt_sha256": rendered_prompt_sha256,
        "recipe_sha256": recipe_sha256,
        "runtimes": ["claude", "codex"],
    }

    (evidence_root / "codex" / "evidence.json").unlink()
    with pytest.raises(ValueError, match="missing clean-room evidence"):
        verify_evidence_root(evidence_root, ROOT)


def _git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _refresh_artifact_hash(run_root: Path, artifact: str, field: str) -> dict[str, object]:
    evidence_path = run_root / "evidence.json"
    payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    payload["observation"][field] = hashlib.sha256(  # type: ignore[index]
        (run_root / artifact).read_bytes()
    ).hexdigest()
    evidence_path.write_text(json.dumps(payload), encoding="utf-8")
    return payload


def _build_valid_target(target: Path, invalid_case: str | None = None) -> None:
    slug = "sample"
    _, purpose_sha256, rendered_prompt_sha256, _ = content_hashes(ROOT)
    purpose = (
        ROOT / "release-evidence/project-agent-kit/fixture/purpose.md"
    ).read_text(encoding="utf-8").strip()
    _git(target, "init", "-q", "-b", "main")
    contract = {
        "schema_version": 1,
        "project_slug": slug,
        "intent": {
            "purpose": purpose,
            "purpose_sha256": purpose_sha256,
            "rendered_prompt_sha256": rendered_prompt_sha256,
        },
        "provider": {
            "url": "https://github.com/youngjin39/mir-yoke",
            "revision": _git(ROOT, "rev-parse", "HEAD"),
        },
        "foundation": {
            "manifest": "pyproject.toml",
            "lockfile": "uv.lock",
            "compile_targets": ["src/harness_probe.py"],
            "smoke_tests": ["tests/test_harness_probe.py"],
        },
        "generation": {
            "canonical": [
                ".claude/skills/sample-code-review/SKILL.md",
                ".claude/agents/sample-code-reviewer.md",
            ],
            "generated": [
                ".agents/skills/sample-code-review/SKILL.md",
                ".codex/agents/sample-code-reviewer.toml",
            ],
        },
        "commands": {
            "generated_parity": [
                "python3",
                "scripts/generate_agent_derivatives.py",
                "--check",
            ],
            "lint": ["scripts/verify.sh", "lint"],
            "build": ["scripts/verify.sh", "build"],
            "test": ["scripts/verify.sh", "test"],
        },
    }
    project = (
        "# Sample project\n\n"
        f"{purpose}\n\n"
        "## Users\nRepository maintainers.\n\n"
        "## Success conditions\nThe future product goals are measurable.\n\n"
        "## Non-goals\nNo product implementation during bootstrap.\n\n"
        "## Assumptions\nPython 3.12 and uv are available.\n\n"
        "## Open product decisions\nCommand UX remains open for later planning.\n"
    )
    canonical_skill = (
        "---\nname: sample-code-review\n"
        "description: Review the sample project foundation using recorded checks.\n"
        "---\n\n# Sample code review\n\n"
        "Canonical source: .claude/skills/sample-code-review/SKILL.md\n\n"
        "Inspect PROJECT.md, HARNESS.md, pyproject.toml, src/harness_probe.py, and "
        "tests/test_harness_probe.py. Review risks against scripts/verify.sh evidence.\n"
    )
    claude_agent = (
        "---\nname: sample-code-reviewer\n"
        "description: Read-only evidence reviewer for the sample project.\n"
        "tools: Read, Glob, Grep\n"
        "disallowedTools: Write, Edit\n---\n\n"
        "Inspect PROJECT.md, HARNESS.md, the bounded diff, and recorded evidence. "
        "Return Sound or Changes requested without modifying files.\n"
    )
    agent_digest = hashlib.sha256(claude_agent.encode()).hexdigest()
    codex_agent = (
        "# Generated from .claude/agents/sample-code-reviewer.md\n"
        f"# Source SHA-256: {agent_digest}\n"
        'name = "sample-code-reviewer"\n'
        'description = "Read-only evidence reviewer for the sample project."\n'
        'developer_instructions = "Inspect the bounded diff and report Sound or '
        'Changes requested."\n'
        'sandbox_mode = "read-only"\n'
    )
    files = {
        "PROJECT.md": project,
        "HARNESS.md": (
            "# Harness\n\n## Outcome\nPreserve a reliable project foundation.\n\n"
            "## Authority\nThe current user owns repository writes.\n\n"
            "## Protected paths\nCredentials and generated files are protected.\n\n"
            "## Generated paths\nCodex reviewer surfaces are generated.\n\n"
            "## Verification\nRun `scripts/verify.sh` before changes.\n"
        ),
        "CLAUDE.md": "Read and follow HARNESS.md.\n",
        "AGENTS.md": "Read and follow HARNESS.md.\n",
        "README.md": "# Sample project foundation\n",
        ".gitignore": ".cache/\n.harness-runtime/\n__pycache__/\n*.pyc\n",
        "docs/harness-bootstrap.md": (
            "# Bootstrap provenance\n\n"
            "Source: https://github.com/youngjin39/mir-yoke\n"
            f"Revision: {_git(ROOT, 'rev-parse', 'HEAD')}\n"
        ),
        "harness/project-agent-kit.json": json.dumps(contract, indent=2) + "\n",
        "pyproject.toml": "[project]\nname = \"sample-foundation\"\nversion = \"0.0.0\"\n",
        "uv.lock": "version = 1\nrevision = 1\nrequires-python = \">=3.11\"\n",
        "src/harness_probe.py": "def harness_probe() -> str:\n    return \"ready\"\n",
        "tests/test_harness_probe.py": (
            "import runpy\n\n"
            "namespace = runpy.run_path('src/harness_probe.py')\n"
            "assert namespace['harness_probe']() == \"ready\"\n"
        ),
        "scripts/generate_agent_derivatives.py": (
            "#!/usr/bin/env python3\n"
            "import argparse\n"
            "import hashlib\n"
            "from pathlib import Path\n\n"
            "parser = argparse.ArgumentParser()\n"
            "parser.add_argument('--check', action='store_true')\n"
            "args = parser.parse_args()\n"
            "skill_source = Path('.claude/skills/sample-code-review/SKILL.md')\n"
            "skill_generated = Path('.agents/skills/sample-code-review/SKILL.md')\n"
            "agent_source = Path('.claude/agents/sample-code-reviewer.md')\n"
            "agent_generated = Path('.codex/agents/sample-code-reviewer.toml')\n"
            "agent_digest = hashlib.sha256(agent_source.read_bytes()).hexdigest()\n"
            "expected_agent = (\n"
            "    '# Generated from .claude/agents/sample-code-reviewer.md\\n'\n"
            "    f'# Source SHA-256: {agent_digest}\\n'\n"
            "    'name = \\\"sample-code-reviewer\\\"\\n'\n"
            "    'description = \\\"Read-only evidence reviewer for the sample project.\\\"\\n'\n"
            "    'developer_instructions = \\\"Inspect the bounded diff and report Sound or '\n"
            "    'Changes requested.\\\"\\n'\n"
            "    'sandbox_mode = \\\"read-only\\\"\\n'\n"
            ")\n"
            "if args.check:\n"
            "    skill_ok = skill_generated.read_bytes() == skill_source.read_bytes()\n"
            "    agent_ok = (\n"
            "        agent_source.is_file() and agent_generated.read_text() == expected_agent\n"
            "    )\n"
            "    raise SystemExit(0 if skill_ok and agent_ok else 1)\n"
            "skill_generated.parent.mkdir(parents=True, exist_ok=True)\n"
            "skill_generated.write_bytes(skill_source.read_bytes())\n"
            "agent_generated.parent.mkdir(parents=True, exist_ok=True)\n"
            "agent_generated.write_text(expected_agent)\n"
        ),
        "scripts/verify.sh": (
            "#!/bin/sh\n"
            "set -eu\n"
            "case \"${1:-all}\" in\n"
            "  lint) python3 -m py_compile src/harness_probe.py tests/test_harness_probe.py ;;\n"
            "  build) test -s pyproject.toml && test -s uv.lock && "
            "python3 -m py_compile src/harness_probe.py ;;\n"
            "  test) python3 tests/test_harness_probe.py ;;\n"
            "  all) \"$0\" lint && \"$0\" build && \"$0\" test ;;\n"
            "  *) exit 2 ;;\n"
            "esac\n"
        ),
        ".githooks/pre-commit": (
            "#!/bin/sh\n"
            "set -eu\n"
            "phase=${PROJECT_AGENT_KIT_HOOK_PHASE:-commit}\n"
            "case \"$phase\" in direct|commit) ;; *) exit 2 ;; esac\n"
            "root=$(git rev-parse --show-toplevel)\n"
            "\"$root/scripts/verify.sh\"\n"
            "log=$(git rev-parse --git-path project-agent-kit-pre-commit.log)\n"
            "printf '%s:0\\n' \"$phase\" >> \"$log\"\n"
        ),
        ".claude/agents/sample-code-reviewer.md": claude_agent,
        ".codex/agents/sample-code-reviewer.toml": codex_agent,
        ".claude/skills/sample-code-review/SKILL.md": canonical_skill,
    }
    files[".agents/skills/sample-code-review/SKILL.md"] = files[
        ".claude/skills/sample-code-review/SKILL.md"
    ]
    if invalid_case == "noop-verifier":
        files["scripts/verify.sh"] = (
            "#!/bin/sh\n# lint build test placeholder with enough padding for inspection\n"
            "# This intentionally represents an invalid verification implementation.\n"
            "exit 0\n"
        )
    elif invalid_case == "product-file":
        files["src/product_api.py"] = "def product_api():\n    return {}\n"
    elif invalid_case == "skill-frontmatter":
        skill = "---\nname: sample-code-review\n---\n\n# Review\n"
        files[".claude/skills/sample-code-review/SKILL.md"] = skill
        files[".agents/skills/sample-code-review/SKILL.md"] = skill
    elif invalid_case == "generic-skill":
        skill = (
            "---\nname: sample-code-review\n"
            "description: Review repository changes using available evidence.\n"
            "---\n\n# Review\n\n"
            "Canonical source: .claude/skills/sample-code-review/SKILL.md\n\n"
            "Inspect the changed files carefully and report concrete findings by severity.\n"
        )
        files[".claude/skills/sample-code-review/SKILL.md"] = skill
        files[".agents/skills/sample-code-review/SKILL.md"] = skill
    elif invalid_case == "purpose-loss":
        files["PROJECT.md"] = project.replace(purpose, "A different purpose.")
    elif invalid_case == "provider-revision":
        changed_contract = copy.deepcopy(contract)
        changed_contract["provider"]["revision"] = "f" * 40
        files["harness/project-agent-kit.json"] = (
            json.dumps(changed_contract, indent=2) + "\n"
        )
        files["docs/harness-bootstrap.md"] = files["docs/harness-bootstrap.md"].replace(
            _git(ROOT, "rev-parse", "HEAD"), "f" * 40
        )
    elif invalid_case == "product-in-probe":
        files["src/harness_probe.py"] = (
            "PRODUCT_ENDPOINT = 'https://example.invalid'\n\n"
            "def harness_probe() -> str:\n"
            "    return \"ready\"\n"
        )
    for relative, body in files.items():
        path = target / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    for relative in (
        "scripts/generate_agent_derivatives.py",
        "scripts/verify.sh",
        ".githooks/pre-commit",
    ):
        (target / relative).chmod(0o755)
    _git(target, "config", "core.hooksPath", ".githooks")
    direct_environment = os.environ.copy()
    direct_environment["PROJECT_AGENT_KIT_HOOK_PHASE"] = "direct"
    subprocess.run(
        [".githooks/pre-commit"],
        cwd=target,
        env=direct_environment,
        check=True,
    )
    _git(target, "add", "-A")
    environment = os.environ.copy()
    environment.update(
        {
            "GIT_AUTHOR_NAME": "Evidence Test",
            "GIT_AUTHOR_EMAIL": "evidence@invalid",
            "GIT_COMMITTER_NAME": "Evidence Test",
            "GIT_COMMITTER_EMAIL": "evidence@invalid",
        }
    )
    subprocess.run(
        ["git", "commit", "-q", "-m", "chore(harness): bootstrap project agent kit"],
        cwd=target,
        env=environment,
        check=True,
    )


def _write_run_evidence(workspace: Path, runtime: str) -> Path:
    evidence_root = workspace / "evidence"
    target = workspace / f"target-{runtime}"
    target.mkdir(parents=True)
    state_dir = workspace / f"state-{runtime}"
    outside = workspace / f"outside-{runtime}"
    outside.mkdir(parents=True)
    global_config = workspace / "observer-gitconfig"
    global_config.write_text(
        "[user]\n\tname = Evidence Test\n\temail = evidence@invalid\n",
        encoding="utf-8",
    )
    previous_global = os.environ.get("GIT_CONFIG_GLOBAL")
    os.environ["GIT_CONFIG_GLOBAL"] = str(global_config)
    try:
        prepare(target, state_dir, [outside])
        _build_valid_target(target)
        runtime_log = state_dir / "runtime-source.log"
        runtime_log.write_text(
            f"{runtime} completed the clean-room run\nREADY_FOR_DEVELOPMENT_PLANNING\n",
            encoding="utf-8",
        )
        collect(
            state_dir,
            evidence_root,
            runtime,
            "verified-runtime-version",
            f"{runtime}-clean-room",
            runtime_log,
        )
    finally:
        if previous_global is None:
            os.environ.pop("GIT_CONFIG_GLOBAL", None)
        else:
            os.environ["GIT_CONFIG_GLOBAL"] = previous_global
    return evidence_root


@pytest.mark.parametrize(
    "case",
    (
        "noop-verifier",
        "product-file",
        "skill-frontmatter",
        "generic-skill",
        "purpose-loss",
        "provider-revision",
        "product-in-probe",
    ),
)
def test_release_evidence_rejects_an_invalid_bundled_kit(
    tmp_path: Path, case: str
) -> None:
    target = tmp_path / case
    target.mkdir()
    _build_valid_target(target, case)
    prompt_template, purpose, rendered_prompt, recipe = content_hashes(ROOT)
    payload = _evidence("claude", prompt_template, purpose, rendered_prompt, recipe)
    result = payload["result"]
    observation = payload["observation"]
    assert isinstance(result, dict)
    assert isinstance(observation, dict)
    result["initial_commit"] = _git(target, "rev-parse", "HEAD")
    observation["target_tree_sha256"] = tracked_tree_sha256(target)

    with pytest.raises(ValueError):
        _verify_target_checkout(target, payload)


def test_release_evidence_recomputes_artifact_hashes(tmp_path: Path) -> None:
    for runtime in ("claude", "codex"):
        _write_run_evidence(tmp_path, runtime)
    evidence_root = tmp_path / "evidence"
    (evidence_root / "claude" / "verification.json").write_text(
        "{}\n", encoding="utf-8"
    )

    with pytest.raises(ValueError, match="verification_log_sha256"):
        verify_evidence_root(evidence_root, ROOT)


def test_release_evidence_rejects_unobserved_git_configuration(tmp_path: Path) -> None:
    evidence_root = _write_run_evidence(tmp_path, "claude")
    run_root = evidence_root / "claude"
    verification_path = run_root / "verification.json"
    original = json.loads(verification_path.read_text(encoding="utf-8"))
    variants = []
    missing_hook = copy.deepcopy(original)
    missing_hook["git"]["core_hooks_path"] = ""
    variants.append(missing_hook)
    unsafe_local = copy.deepcopy(original)
    unsafe_local["git"]["local_config_keys"].append("core.sshcommand")
    variants.append(unsafe_local)
    for changed in variants:
        verification_path.write_text(json.dumps(changed), encoding="utf-8")
        payload = _refresh_artifact_hash(
            run_root, "verification.json", "verification_log_sha256"
        )
        with pytest.raises(ValueError):
            _verify_run_artifacts(run_root, payload, ROOT)


def test_release_evidence_rejects_sensitive_runtime_transcript(tmp_path: Path) -> None:
    evidence_root = _write_run_evidence(tmp_path, "claude")
    run_root = evidence_root / "claude"
    (run_root / "runtime.log").write_text(
        "path=/" + "Users/private/project\nREADY_FOR_DEVELOPMENT_PLANNING\n",
        encoding="utf-8",
    )
    payload = _refresh_artifact_hash(run_root, "runtime.log", "runtime_log_sha256")

    with pytest.raises(ValueError, match="private local path"):
        _verify_run_artifacts(run_root, payload, ROOT)


def test_release_evidence_has_a_dedicated_maintainer_classification() -> None:
    manifest = json.loads((ROOT / "config/template-assets.json").read_text())
    rule = next(
        rule
        for rule in manifest["rules"]
        if rule["id"] == "project-agent-kit-release-evidence"
    )

    assert rule["classification"] == "template-maintainer-tool"
    assert rule["include"] == ["release-evidence/project-agent-kit/**"]
    maintainer = next(rule for rule in manifest["rules"] if rule["id"] == "maintainer-tools")
    retained = next(
        rule for rule in manifest["rules"] if rule["id"] == "retained-platform-corpus"
    )
    assert "scripts/observe_project_agent_kit.py" in maintainer["include"]
    assert "scripts/observe_project_agent_kit.py" in retained["exclude"]
