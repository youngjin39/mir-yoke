"""Final guidance gaps: provenance, bounded delivery and two-runtime registration."""

import json
import re
from pathlib import Path

import pytest

from mir.core.capabilities.config import load_capability_config
from scripts.verify_codex_sync import PLUGIN_SKILLS

ROOT = Path(__file__).resolve().parents[1]
IDEAS = " (ideas only, no license; wording original)"
KOREAN = "bear2u/natural-korean-skills at 2a4f1fc" + IDEAS
CASES = (
    ("mir-content/korean-writing", "contextual-revision.md", KOREAN,
     ("fluent-korean", "no-ai-slop",
      "\uc9c4\ub2e8", "\ubcf4\uc874", "\uc218\uc815", "\uc804\ud6c4")),
    *[("mir-content/korean-writing", genre + ".md", KOREAN,
       ("\uba54\ubaa8", "\ub3c5\uc790", "\uc644\ub8cc", "\ud655\uc778")) for genre in (
           "business", "technical-runbooks", "blogs", "essays", "public-notices",
           "minutes-slides")],
    ("mir-core/app-investigation", "bounded-investigation.md",
     "morluto/rea at cd10ee1 (MIT)",
     ("feature", "artifact", "already-installed", "already-authorized", "static inference",
      "runtime observation", "behavior contract", "Unknown", "contradictions", "permitted")),
    ("mir-core/automation", "recovery-and-reframing.md", "Q00/ouroboros at 5520a3e",
     ("transient", "structural", "semantic", "pipefail", "SPINNING", "OSCILLATION",
      "NO_DRIFT", "DIMINISHING_RETURNS", "hacker", "researcher", "simplifier",
      "architect", "contrarian", "report-only", "Main")),
    ("mir-code/code-review", "repository-audit-and-debt.md",
     "DietrichGebert/ponytail at 09c434a",
     ("ordinary", "diff", "load assumptions", "hot-path", "lean", "ponytail:", "custom")),
    ("mir-core/governance", "skill-patch-from-traces.md", "microsoft/SkillOpt at 84b36cd",
     ("learning-safe", "evaluator internals", "per-skill", "subset", "raw", "held-out")),
    ("mir-core/efficiency", "observed-cache-misses.md",
     "bugbug9999/token-diet at 82ac6a7" + IDEAS,
     ("observed", "cached", "model", "prefix", "schema", "Unknown", "TTL", "no keep-alive")),
    ("mir-core/verify", "three-document-fidelity.md", "fn-opt/dryforge at f5aa6d7",
     ("artifact-only", "no dialogue context", "executable", "fresh reviewer", "advisory")),
    ("mir-core/memory-evaluation", "synthetic-visual-cases.md",
     "xiaowu0162/LongMemEval-V2 at 2cc8c54",
     ("synthetic", "screenshot", "text-only", "visual evidence", "gold", "no-memory")),
    ("mir-core/design", "product-prd.md", "Q00/ouroboros at 5520a3e",
     ("PRD", "user", "problem", "non-goals", "success", "acceptance", "brownfield")),
)


@pytest.mark.parametrize("target,reference,provenance,terms", CASES)
def test_should_deliver_bounded_guidance_with_provenance_and_pointer(
    target, reference, provenance, terms,
):
    plugin, skill = target.split("/")
    root = ROOT / "plugins" / plugin / "skills" / skill
    text = (root / "references" / reference).read_text(encoding="utf-8")
    assert f"Inspired by {provenance}." in text
    normalized = " ".join(text.lower().split())
    for term in terms:
        assert term.lower() in normalized, term
    assert len(text.splitlines()) < 50
    entrypoint = (root / "SKILL.md").read_text(encoding="utf-8")
    assert f"](references/{reference})" in entrypoint
    for link in re.findall(r"\]\((references/[^)]+)\)", entrypoint):
        assert (root / link).is_file(), link


@pytest.mark.parametrize("plugin,skill", [
    ("mir-content", "korean-writing"), ("mir-core", "app-investigation"),
])
def test_should_register_compact_opt_in_skills_for_both_runtimes(plugin, skill):
    root = ROOT / "plugins" / plugin / "skills" / skill
    text = (root / "SKILL.md").read_text(encoding="utf-8")
    assert text.startswith(f"---\nname: {skill}\ndescription:")
    assert len(text.splitlines()) < 50
    config = load_capability_config(ROOT / "config/capability-sources.json")
    assert skill in config.plugin_skills[plugin]
    assert skill in PLUGIN_SKILLS[plugin]
    catalog = json.loads((ROOT / "config/repo-agent-management.json").read_text())
    entry = catalog["catalog"]["skills"][skill]
    assert entry["source_path"] == f"plugins/{plugin}/skills/{skill}/"
    assert entry["status"] == "active"
    assert entry["scope"] == "universal"
    assert all(p.suffix == ".md" for p in root.rglob("*") if p.is_file())

