---
status: superseded
date: 2026-05-23
updated: 2026-09-02
scope: historical bootstrap interview spec pointer
---

# Bootstrap Interview Spec — Historical Pointer

The former document specified an expansion of a bootstrap command-line interview that was designed but never built. It listed the six fields the existing module then collected, named the gaps an audit had found, and proposed three categories of replacement fields covering identity, customization and operation, each with a prompt string, a type and a validation rule. It added three invocation modes — interactive, argument-driven and a manifest file whose format it gave in full — five output artifacts spanning a control-plane config file, a mirrored config copy inside the target repository for self-recovery, a new row appended to a central state file with every phase defaulted to pending, regenerated startup derivatives, and a registration notice pushed to a chat channel, plus schema, cross-field and verifier gates. The module it was to extend, the state file and the notification path are not in this repository.

The recipe now collects what it needs in one prompt against the user's target and writes only bounded project-owned files there, with no control-plane config, no central row and no notice emitted anywhere. Current authority is ADR-83 (the four-file starter, the Project Agent Kit recipe and the optional installed CLI are the only adoption layers), ADR-84 (upgrade guidance; it already classifies this whole directory as history), ADR-85 (agent contracts), ADR-86 (Mir Harness maintains this repository) and ADR-81 (the Starter). Fleet rollout, hash conformance, direct deployment, drift enforcement and notification behaviour are cancelled and named only to forbid their return. The current replacement guide is `docs/operations/harness-engineering-upgrade.md`.

A new session must not execute the historical procedure. The complete original is preserved in [the archive](../../../_archive/harness-engineering/applications/template-repo/bootstrap-interview-spec-2026-05-23-historical.md).
