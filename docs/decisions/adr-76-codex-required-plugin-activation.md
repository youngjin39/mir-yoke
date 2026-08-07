---
title: Codex-Required Global Plugin Activation
status: accepted
date: 2026-08-07
---

# ADR-76 — Codex-Required Global Plugin Activation

## Context

ADR-74 and ADR-75 originally required installation and operator-observed skill-catalog receipts
from both Claude Code and Codex before global plugin activation. That coupled readiness to a Claude
restart even when Codex was the selected and verified control-plane runtime. The operator explicitly
chose to skip the Claude activation gate and finalize from genuine Codex evidence.

This decision changes only activation evidence. It does not remove Claude manifests, Claude
installation attempts, Claude status reporting, or Claude's ability to record an optional runtime
observation.

## Decision

`config/capability-sources.json` owns a non-empty
`policy.activation_required_runtimes` list. The current portable policy contains only
`codex-cli-desktop`.

The capability manager:

1. attempts and reports installation evidence for every supported host runtime;
2. blocks synchronization, discovery completion, finalization, and ready status only when a
   runtime in the configured required set lacks valid evidence;
3. continues to report optional Claude installation and discovery failures without treating them
   as activation blockers;
4. requires the Codex installed-cache digest, persistent marketplace configuration, new
   runtime-exported session ID, and complete operator-observed skill catalog exactly as before; and
5. rejects an empty, duplicate, or unknown required-runtime list.

The host collision inventory and one-version provider rules from ADR-75 remain unchanged.

## Consequences

A Codex-only host can reach `ready` without installing, restarting, or attesting Claude Code.
Adopters may still use Claude and record its evidence, but Claude readiness is advisory under this
policy. A missing or invalid required Codex installation or discovery receipt remains fail-closed.

This decision supersedes only the dual-runtime activation requirement in ADR-74 and ADR-75.

## Acceptance criteria

1. Codex-only installation plus a complete new-session discovery receipt can finalize activation.
2. Missing Claude installation or discovery remains visible and does not block finalization.
3. Missing Codex installation or discovery blocks synchronization or finalization.
4. Status output identifies the configured required runtime set.
5. Invalid required-runtime configuration is rejected before capability operations.
