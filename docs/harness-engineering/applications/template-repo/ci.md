---
status: superseded
date: 2026-05-23
updated: 2026-09-02
scope: historical template CI health pointer
---

# Template CI + Pre-commit + Health Check — Historical Pointer

The former document specified the template repository's own quality gates as three workflows given in full: a per-pull-request validation set covering schema self-validation, link integrity, hook executability, a sanitization scan and an applied-state parity check; a tag-triggered release job that read a version file, extracted a changelog entry and posted release notes to an outbound webhook stored as a repository secret; and a daily scheduled health job that ran a health tool and raised a priority alert to the same channel on degradation. Around them it specified three pre-commit hooks including a protected-paths guard, five test files given as inline code, and a health-check tool with a command surface, a per-check output schema and a failure-to-action mapping in which several failures blocked the release job outright. That health tool and its drift check against a private source repository do not exist here.

The checks that matter now are the ones this repository's own test suite and verifier scripts actually run against a change, and no release notification is emitted to any channel. Current authority is ADR-83 (the four-file starter, the Project Agent Kit recipe and the optional installed CLI are the only adoption layers), ADR-84 (upgrade guidance; it already classifies this whole directory as history), ADR-85 (agent contracts), ADR-86 (Mir Harness maintains this repository) and ADR-81 (the Starter). Fleet rollout, hash conformance, direct deployment, drift enforcement and notification behaviour are cancelled and named only to forbid their return. The current replacement guide is `docs/operations/harness-engineering-upgrade.md`.

A new session must not execute the historical procedure. The complete original is preserved in [the archive](../../../_archive/harness-engineering/applications/template-repo/ci-2026-05-23-historical.md).
