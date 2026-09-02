---
status: superseded
date: 2026-05-24
updated: 2026-09-02
scope: historical tool-call gateway runbook pointer
---

# MCP Gateway Runbook — Historical Pointer

This runbook documented a tool-call gateway placed between the agent's MCP client and downstream servers: a policy registry returning
allow, deny or audit decisions with optional per-agent scoping, an append-only audit log that recorded argument keys but never values,
two stub transport forwarders, a check/audit-tail/route command line, and a forty-three test inventory. The `tools/mcp_gateway/`
package, its policy file and its schema do not exist in this repository.

Current authority is ADR-83 (the four-file Starter, the Project Agent Kit recipe and the optional installed CLI are the only adoption
layers), ADR-84, which already classifies this whole directory as history, ADR-85 (agent contracts), ADR-86 (Mir Harness maintains this
repository) and ADR-81 (the Starter). Fleet rollout, hash conformance, direct deployment, drift enforcement and notification behaviour are
cancelled and named only to forbid their return; the current replacement guide is `docs/operations/harness-engineering-upgrade.md`.

A new session must not execute the historical procedure. The complete original is preserved in
[the archive](../../../_archive/harness-engineering/applications/example-harness/mcp-gateway-runbook-2026-05-24-historical.md).
