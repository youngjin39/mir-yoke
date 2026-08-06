---
name: automation
description: "Long-running task control + browser automation.\n\nTrigger: runner, long-running, background, monitor, resume, compact, handoff, browser, scrape, E2E\n\nAbsorbs: runner, browser-automation"
---

# Automation

## Use When
- When a task is long-running or must survive session restart, compact, or handoff.
- When browser automation, scraping, E2E testing, or web-app operation is needed.

## Absorbed legacy skills
- runner — Long-running/background task control for Codex and Claude. Externalize task state to a durable ledger so compact, handoff, and session resume reconnect to the same work instead of relaunching it.
- browser-automation — Real-browser control via agent-browser CLI. Accessibility-tree snapshots for token-efficient page interaction.

## Workflow
1. Give the run a stable identifier and record its goal, owner, current checkpoint, and completion test in a repository-owned task ledger.
2. Before launching work, inspect the ledger and running processes so a resumed session does not duplicate an active run.
3. Persist every external process identifier, output location, last verified checkpoint, and safe resume command. Never rely on chat history as the only state.
4. For browser work, take an accessibility-tree snapshot, perform the smallest action, and verify the resulting page state before the next action.
5. On compact or handoff, update the same ledger with observed evidence, remaining work, and the exact next command.
6. Mark completion only after the recorded completion test passes; otherwise leave a truthful running, paused, or blocked state.
