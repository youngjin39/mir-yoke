---
status: superseded
date: 2026-05-23
updated: 2026-09-02
scope: historical partial cherry-pick model pointer
---

# Template Cherry-Pick — Central Template + Partial Selection Copy Model — Historical Pointer

The former document defined a five-layer partial-copy model in which one central reference implementation held every phase, skill, agent, hook and configuration snippet, and every other repository selected a subset through fields in a per-repository config file. It gave the selection mechanism for each layer with worked config fragments, a rule that additions had to come from the central reference, a separate path for capabilities a repository authored itself, an effective-phase table per repository class, a six-step selection procedure, a consistency verifier that auto-disabled dangling selections, a sync policy that force-pushed hook security fixes to every repository including those that had opted out of everything else, with a channel notification and no revert window, a bidirectional reverse-absorption path, and a self-stop clause asserting that if the central reference broke, every dependent repository halted.

There is no central reference with standing over consumers and no forced sync: a user copies the four-file Starter or runs the recipe against their own target, and a fix reaches them only when they choose to take it. Current authority is ADR-83 (the four-file starter, the Project Agent Kit recipe and the optional installed CLI are the only adoption layers), ADR-84 (upgrade guidance; it already classifies this whole directory as history), ADR-85 (agent contracts), ADR-86 (Mir Harness maintains this repository) and ADR-81 (the Starter). Fleet rollout, hash conformance, direct deployment, drift enforcement and notification behaviour are cancelled and named only to forbid their return. The current replacement guide is `docs/operations/harness-engineering-upgrade.md`.

A new session must not execute the historical procedure. The complete original is preserved in [the archive](../../_archive/harness-engineering/applications/template-cherrypick-2026-05-23-historical.md).
