"""Remaining 0.13.31 guidance contracts, independent of Git history."""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def target(relative):
    plugin, path = relative.split("/", 1)
    return ROOT / "plugins" / plugin / "skills" / path


def read(relative):
    return " ".join(target(relative).read_text(encoding="utf-8").split())


@pytest.mark.parametrize(
    "path,required,removed",
    [
        (
            "mir-core/app-investigation/references/bounded-investigation.md",
            (
                "stable identity",
                "digests",
                "source maps",
                "exported names",
                "manifest identifiers",
                "never minified names or ordinal position",
                "both versions are fully covered",
                "otherwise label additions or removals Unknown",
                "dd02d8f",
                "cd10ee1",
                "9e6c624",
            ),
            (),
        ),
        (
            "mir-content/korean-writing/references/business.md",
            (
                "\uc8fc\uac04 \ubcf4\uace0",
                "\ub05d\ub0b8 \uc77c",
                "\uc9c4\ud589 \uc911\uc778 \uc77c",
                "\uc704\ud5d8 \uc694\uc778",
                "\uc9c0\uc6d0 \uc694\uccad",
                "\uc694\uccad \uba54\uc77c",
                "\uccab \ubb38\uc7a5",
                "\uc694\uccad \ub0b4\uc6a9\uacfc \ud68c\uc2e0 \uae30\ud55c",
                "\ud68c\uc758 \uc81c\uc548",
                "\ubaa9\uc801",
                "\ucc38\uc11d \ub300\uc0c1",
                "\ud6c4\ubcf4 \uc2dc\uac01",
                "\uc18c\uc694 \uc2dc\uac04",
                "\uc7a5\uc18c\ub098 \uc811\uc18d \ubc29\ubc95",
            ),
            (),
        ),
        (
            "mir-content/korean-writing/references/public-notices.md",
            (
                "\ubcf4\ub3c4\uc790\ub8cc",
                "\uccab \ubb38\uc7a5",
                "\ud575\uc2ec \uc0ac\uc2e4",
                "\uc815\ubcf4 \ucd9c\ucc98\uc640 \ub2f4\ub2f9 \uc5f0\ub77d\ucc98",
                "\ubbfc\uc6d0 \ud68c\uc2e0",
                "\uc9c8\ubb38\uc5d0 \uc9c1\uc811 \ub2f5",
                "\uc870\uce58 \ub0b4\uc6a9\uacfc \uc644\ub8cc \uc608\uc815\uc77c",
                "\uac10\uc815\uc744 \uc9d0\uc791",
                "\uacf5\ubb38",
                "\ubb38\uc11c\ubc88\ud638",
                "\uc2dc\ud589\uc77c",
                "\uacb0\uc7ac\uc790",
                "[\ud655\uc778 \ud544\uc694:",
            ),
            (),
        ),
        (
            "mir-code/bluebricks/references/sufficient-solution.md",
            (".ai-harness/development-ai-rules.md:15-20",),
            ("development-ai-rules.md:18-23",),
        ),
        (
            "mir-core/automation/references/spinning-report.md",
            (
                "Mir Yoke's own executor implements this signature",
                "consumers apply the rule manually",
                "equal signatures have the same root cause",
            ),
            ("tools/mir_executor/dispatch.py:503",),
        ),
        (
            "mir-core/design/SKILL.md",
            ("Second-pass reinforcements (dryforge):",),
            ("central directive 2026-07-25",),
        ),
        (
            "mir-core/verify/SKILL.md",
            ("## Evidence-claim discipline", "counts as a failure, not a pass"),
            ("central directive 2026-07-25",),
        ),
        (
            "mir-core/spec-architect/references/00-completeness.md",
            ("skill's Intent Extraction section.",),
            ("ADR-70", "ADR-78"),
        ),
        (
            "mir-core/automation/references/recovery-and-reframing.md",
            ("Q00/ouroboros at 5520a3e", "re-checked at 7783d9f on 2026-10-24"),
            (),
        ),
        (
            "mir-core/design/references/product-prd.md",
            ("Q00/ouroboros at 5520a3e", "re-checked at 7783d9f on 2026-10-24"),
            (),
        ),
        (
            "mir-core/efficiency/references/instruction-change-evaluation.md",
            ("token-diet at 82ac6a7 (ideas only, no license; wording original)",),
            ("token-diet at 82ac6a7.",),
        ),
        (
            "mir-core/spec-architect/SKILL.md",
            ("general project management except drafting issues from an approved spec",),
            ("general project management.",),
        ),
        (
            "mir-content/no-ai-slop/SKILL.md",
            ('proper names, such as a project or product name and "test harness".',),
            ('"Mir Harness"',),
        ),
        (
            "mir-lifecycle-hooks/runtime-continuity/references/handoff-packet.md",
            ("[bounded design](handoff-design.md)", "local CLI guards", "The source prepares"),
            (
                "Harness active cursor",
                "1562831233971392553",
                "tasks/plan.md",
                "env-read-gate.sh",
                "0.13.22 source",
                "pre-tool-use.sh",
            ),
        ),
        (
            "mir-lifecycle-hooks/runtime-continuity/references/handoff-design.md",
            (
                "stateless",
                "bounded",
                "no agent authority",
                "project's ontology mapping",
                "when present",
            ),
            (),
        ),
        (
            "mir-content/fluent-korean/SKILL.md",
            (
                "\uc77c\uc0c1\uc801\uc778 \ubb38\uc5b4\uc5d0\uc11c \ud1b5\uc6a9\ub418\uace0",
                "\uad00\uc6a9 \ud45c\ud604\uc73c\ub85c \uc815\ucc29\ub418\uc5b4 \uc788\uc5b4\uc11c",
                "\uc77c\ubc18\uc801\uc778 \uc5b4\ud718\ub85c \ubc14\uafb8\uba74 "
                "\uc624\ud788\ub824 \uc5b4\uc0c9\ud574\uc9c0\ub294 \ud45c\ud604\uc740 "
                "\uadf8\ub300\ub85c \uc0ac\uc6a9\ud569\ub2c8\ub2e4.",
                "Adapted for Mir Yoke and Codex global guidance from:",
            ),
            ("Adapted for Codex global guidance from:",),
        ),
        (
            "mir-code/testing/references/controlled-experiments.md",
            (
                "exceeds its declared budget or timeout",
                "stop it and record a failed attempt",
                "never score it",
            ),
            (),
        ),
        (
            "mir-core/verify/SKILL.md",
            (
                "no runnable verification command",
                "decision with a recommendation to Main or the owner",
            ),
            (),
        ),
    ],
)
def test_should_close_remaining_guidance_items(path, required, removed):
    text = read(path)
    for phrase in required:
        assert phrase in text, phrase
    for phrase in removed:
        assert phrase not in text, phrase


@pytest.mark.parametrize(
    "path",
    [
        "mir-core/app-investigation/references/bounded-investigation.md",
        "mir-content/korean-writing/references/business.md",
        "mir-content/korean-writing/references/public-notices.md",
        "mir-code/bluebricks/references/sufficient-solution.md",
        "mir-core/automation/references/spinning-report.md",
        "mir-core/automation/references/recovery-and-reframing.md",
        "mir-core/design/references/product-prd.md",
        "mir-core/efficiency/references/instruction-change-evaluation.md",
        "mir-code/testing/references/controlled-experiments.md",
        "mir-lifecycle-hooks/runtime-continuity/references/handoff-design.md",
    ],
)
def test_should_keep_remaining_short_references_below_fifty_lines(path):
    assert len(target(path).read_text(encoding="utf-8").splitlines()) < 50
