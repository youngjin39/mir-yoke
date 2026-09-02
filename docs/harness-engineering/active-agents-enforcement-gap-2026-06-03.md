---
status: superseded
date: 2026-06-03
updated: 2026-09-02
scope: historical dispatch enforcement gap pointer
---

# Known Limitation: `active_agents` Dispatch Enforcement is Prompt-Only — Historical Pointer

This note recorded that the per-repository `active_agents` dispatch allow-list was enforced only by an orchestrator prompt convention plus a post-hoc advisory audit reading a prompt-emitted dispatch log, and it explained why the naive hard gates failed: no code path mapped an agent slug to a spawn, the pre-tool-use payload exposed no stable sub-agent type to condition on, and allow-versus-deny precedence was unverified. It proposed a deferred safe approach — a scoped deny-list covering catalog specialists outside the effective allow-list, a safelist for built-in agents, generation into a managed permissions block, and an isolated precedence spike first — and accepted the gap as a documented soft contract until then.

Authority for this repository now sits with ADR-83 (the product boundary: the four-file starter, the Project Agent Kit recipe, and the optional installed CLI are the only adoption layers), ADR-84 (upgrade guidance, which already classifies this whole directory as history), ADR-85 (agent contracts), ADR-86 (Mir Harness maintains this repository), and ADR-81 (the Starter). Fleet rollout, drift enforcement, central direct-apply, daemons and notifications are cancelled and are named here only to forbid their return. The current replacement guide is `docs/operations/harness-engineering-upgrade.md`.

A new session must not execute the historical procedure. The complete original is preserved in [the archive](../_archive/harness-engineering/active-agents-enforcement-gap-2026-06-03-historical.md).
