# Plan

## Active task: external-capability-gaploop-0.13.30-2026-10-24

Intent authority: Mir Harness cursor run `external-capability-gap-loop-2026-10-24`
(owner Discord 1563396738570780685: proceed with option 1 and keep verifying in a loop
until no gaps remain; parent-supplied). Baseline: 5a1a5ac, Mir Yoke 0.13.29.
Goal: fix the installed-guidance defects of the second final review and fill every
shippable gap from the 14 owner-named upstreams except Paperclip, as guidance only.

Loop: a fresh independent reviewer per round against the candidate tree and fresh
upstream clones (rounds 1-3 Codex; rounds 4-8 headless Claude Opus 5.5 at the owner's
request); Main verified each cited line and accepted only behaviour-changing findings;
a Codex writer applied them in a scratch clone with fail-first contract tests.
Rounds 6-8 found no P1 defect. The owner released after round 8 (Discord
1563488289556664383) and moved always-on fluent-korean for Claude into the global
instruction file instead of a Yoke hook. Superseded per-round cursors are preserved
verbatim in [the evidence log](change_log.md#superseded-0130-round-cursors-2026-10-24).

Scope: guidance under `skills/` plus tests, release metadata and payload. No scripts,
agents, commands, hooks behaviour, runtime policy, autonomous loops or LLM hard gates.
fluent-korean stays byte-identical; no-ai-slop stays byte-faithful apart from the
tested local adaptations; Korean files carry exact-hash exceptions.

Request matrix: each accepted finding (rounds 1-8) has a targeted assertion in
`tests/test_capability_gaploop.py`; release metadata, documentation and payload;
full pytest, Ruff, Codex parity and diff check; ADR-80 bind, release, provider
update, runtime attestation and finalize.
