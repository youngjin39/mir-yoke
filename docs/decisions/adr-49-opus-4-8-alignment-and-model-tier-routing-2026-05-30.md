---
status: superseded
updated: 2026-10-01
---

# ADR-49 — Opus 4.8 Alignment and Task-Weight Model-Tier Routing (superseded)

This decision's advisory task-weight table mapped task classes to local model tiers and reasoning
efforts. Sub-agent model and effort now come only from Mir Harness: its ADR-88 and the 2026-10-01
amendment deploy each repository's routing as the generated `config/model-routing.lock.json`,
and Claude agent `model:` / `effort:` frontmatter is projected from that lock. No repository-local
routing table remains current.

The full record is preserved at
`docs/_archive/decisions/adr-49-opus-4-8-alignment-and-model-tier-routing-2026-05-30-historical.md`.

Successor: **Mir Harness ADR-88** (2026-10-01 amendment), not the same-numbered Mir Yoke ADR-88.
Owner authority: Discord messages 1554888004391141437 and 1554891421851320331.
