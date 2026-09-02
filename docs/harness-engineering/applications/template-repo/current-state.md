---
status: superseded
date: 2026-07-15
updated: 2026-09-02
scope: historical template state snapshot pointer
---

# Public Template Current State — Historical Pointer

The former document was a live status snapshot of this repository pinned to one past release. Its frontmatter carried a content commit hash, a version string, an overall verifier verdict with major and minor finding counts, and present-versus-required counts for phase documents and schemas. The body described the startup source and its generated derivatives, the shared main-agent contract, and the single-handoff closeout rule; then it published a measured-evidence table of byte sizes for the root instructions and prompt input, a session-start output size, several check verdicts and a regression pass count; then residual review items covering pre-existing lint findings and a projection check that warns on a local ignored database; then a next release action naming the commit to publish. Every number in it describes that one superseded revision and none has been re-measured since.

Current state is read from this repository itself — its version file, its changelog, and a fresh run of the smallest relevant checks — rather than from a pinned snapshot, and no byte count or verdict in a document should be trusted as live. Current authority is ADR-83 (the four-file starter, the Project Agent Kit recipe and the optional installed CLI are the only adoption layers), ADR-84 (upgrade guidance; it already classifies this whole directory as history), ADR-85 (agent contracts), ADR-86 (Mir Harness maintains this repository) and ADR-81 (the Starter). Fleet rollout, hash conformance, direct deployment, drift enforcement and notification behaviour are cancelled and named only to forbid their return. The current replacement guide is `docs/operations/harness-engineering-upgrade.md`.

A new session must not execute the historical procedure. The complete original is preserved in [the archive](../../../_archive/harness-engineering/applications/template-repo/current-state-2026-07-15-historical.md).
