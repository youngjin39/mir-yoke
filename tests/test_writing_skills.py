"""Pinned-source fidelity and dual-runtime delivery for the writing skills."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest

from mir.core.capabilities.config import load_capability_config
from mir.core.capabilities.manager import _validate_plugin
from scripts.verify_codex_sync import PLUGIN_SKILLS

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "mir-content"
SKILLS = PLUGIN / "skills"


def test_should_preserve_no_ai_slop_upstream_behaviour_when_packaged() -> None:
    text = (SKILLS / "no-ai-slop" / "SKILL.md").read_text(encoding="utf-8")
    upstream, local_adaptation = text.split("\n## Provenance\n", 1)
    assert (
        "Korean-language drafts, diagnosis and revision route to `mir-content:korean-writing`; "
        "no-ai-slop's word and pattern lists are English."
    ) in local_adaptation
    routing = " Korean-language text routes to `mir-content:korean-writing`."
    assert routing in upstream.splitlines()[2]
    upstream = upstream.replace(routing, "", 1)
    upstream = upstream.replace("references/eval.md", "eval.md")
    # Reverse approved description routing and technical-terminology edits; verify
    # the rest of petergyang/no-ai-slop 000650b remains byte-for-byte faithful.
    exception = (
        ' Exempt meaningful technical terms and proper names, such as a project or product name'
        ' and "test harness".'
    )
    assert exception in upstream
    upstream = upstream.replace(exception, "").replace(
        "Banned as ornamental phrasing:", "Banned outright:",
    )
    assert hashlib.sha256(upstream.encode()).hexdigest() == (
        "992b365f51a2f62cf4c1c5ed22049a9ee551dfea677550c1a72b371c0ceadd62"
    )
    assert "`references/eval.md`" in text
    assert not (SKILLS / "no-ai-slop" / "agents" / "openai.yaml").exists()


def test_should_preserve_upstream_eval_except_contextual_exceptions() -> None:
    evaluation = SKILLS / "no-ai-slop" / "references" / "eval.md"
    text = evaluation.read_text(encoding="utf-8")
    adapted = (
        "1. Are ornamental banned words, empty filler phrases, often-empty adverbs, "
        "and inflated claims removed, preserving quoted examples, meaningful technical "
        "terms and proper names, and adverbs and phrases that carry emphasis, uncertainty, "
        "contrast, self-awareness, or the writer's natural spoken rhythm?"
    )
    assert adapted in text
    upstream = text.replace(adapted, (
        "1. Are banned words, filler phrases, often-empty adverbs, and inflated claims "
        "removed unless quoted as examples?"
    ))
    assert hashlib.sha256(upstream.encode()).hexdigest() == (
        "8ad8d83ed1abe7fc054ad74966bfca64fc182bc71f59d701b24b962c39d11ad7"
    )


def test_should_retain_the_entire_fluent_korean_policy_and_attribution() -> None:
    text = (SKILLS / "fluent-korean" / "SKILL.md").read_text(encoding="utf-8")
    frontmatter, body = text.removeprefix("---\n").split("\n---\n\n", 1)
    assert re.search(r"^name: fluent-korean$", frontmatter, re.MULTILINE)
    assert "Korean user-facing output" in frontmatter
    assert "Korean deliverables" in frontmatter
    # Approved global-policy snapshot, adapted from snflkd/fluent-korean ce8683f.
    assert hashlib.sha256(body.encode()).hexdigest() == (
        "7109372ce9d6e8569c923568856788400d0e8032c60dfc66fad0a0e9baec7f32"
    )


@pytest.mark.parametrize("skill,author,revision", [
    ("no-ai-slop", "Peter Yang", "000650b156983f5159695b441477f4e63b25dc85"),
    ("fluent-korean", "snflkd", "ce8683f0eba8cddb91de4dcd151425ff73e60498"),
])
def test_should_keep_mit_notices_and_pinned_provenance(skill, author, revision) -> None:
    root = SKILLS / skill
    notice = "\n".join(path.read_text() for path in root.rglob("*") if path.is_file())
    assert "MIT License" in notice
    assert f"Copyright (c) 2026 {author}" in notice
    assert "Permission is hereby granted, free of charge" in notice
    assert "THE SOFTWARE IS PROVIDED" in notice
    assert revision in notice


@pytest.mark.parametrize("skill", ["no-ai-slop", "fluent-korean"])
def test_should_register_one_common_provider_for_both_runtimes(skill: str) -> None:
    config = load_capability_config(ROOT / "config" / "capability-sources.json")
    assert skill in config.plugin_skills["mir-content"]
    assert skill in PLUGIN_SKILLS["mir-content"]
    catalog = json.loads((ROOT / "config" / "repo-agent-management.json").read_text())
    entry = catalog["catalog"]["skills"][skill]
    assert entry["status"] == "active"
    assert entry["scope"] == "universal"
    assert entry["source_path"] == f"plugins/mir-content/skills/{skill}/"
    assert config.runtime_support["supported"] == ["claude-code", "codex-cli", "codex-desktop"]
    digest = _validate_plugin(PLUGIN, "mir-content", package_kind="skills")
    assert re.fullmatch(r"[0-9a-f]{64}", digest)


@pytest.mark.parametrize("profile,includes_content", [
    ("hybrid_pipeline", True), ("content_workspace", True),
    ("code_app", False), ("infra_runtime", False),
])
def test_should_preserve_existing_profile_reachability(profile, includes_content) -> None:
    config = load_capability_config(ROOT / "config" / "capability-sources.json")
    _, pack = config.resolve_profile(profile)
    assert ("mir-content" in pack.plugins) is includes_content
