---
status: superseded
date: 2026-05-23
updated: 2026-09-02
scope: historical incident response runbook pointer
---

# Incident Response Runbook — Historical Pointer

The former document was a cross-repository incident runbook. It named six incident classes, treated detection as a pre-condition fed by a set of autonomous-execution triggers, then defined a four-phase response of contain, eradicate, recover and postmortem, with a postmortem template including a tripwire retrospective and mandatory feedback obligations. It set a severity table with explicit containment, eradication and recovery service-level times, then differentiated those times per repository class — doubling the containment window for creative pipeline work, forbidding automatic escalation in personal-domain repositories, and auto-escalating anything touching the control plane itself. It closed with a worked sample incident, an implementation queue with hour estimates, and a per-class propagation table. Its advisory log, its trigger wiring and its containment-downgrade hook are not present here.

No incident obligation now crosses a repository boundary and no response time is owed to or by a consumer: whoever operates a repository owns its incidents and its postmortems. Current authority is ADR-83 (the four-file starter, the Project Agent Kit recipe and the optional installed CLI are the only adoption layers), ADR-84 (upgrade guidance; it already classifies this whole directory as history), ADR-85 (agent contracts), ADR-86 (Mir Harness maintains this repository) and ADR-81 (the Starter). Fleet rollout, hash conformance, direct deployment, drift enforcement and notification behaviour are cancelled and named only to forbid their return. The current replacement guide is `docs/operations/harness-engineering-upgrade.md`.

A new session must not execute the historical procedure. The complete original is preserved in [the archive](../../_archive/harness-engineering/applications/incident-response-2026-05-23-historical.md).
