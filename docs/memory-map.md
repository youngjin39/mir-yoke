---
title: Memory map — keyword index
description: Maps keywords to docs/ files so the agent only loads what is needed.
---

# Memory map

The agent reads this file on session start to decide which docs/ files to pull
into context. Empty index = nothing loaded = no token waste.

## Search protocol

1. Scan the keyword table.
2. Read only matched files.
3. If no match, skip — do not load the entire docs/ tree.

## Save protocol

When a new doc lands under `docs/<category>/`, add a row to the table below.
A doc without an index entry is invisible to future sessions.

## Keyword → file mapping

| Keywords | Category | File |
|---|---|---|
| (empty — add rows as docs/ grows) | | |

## Promotion

- Pattern fires twice → write a row in `tasks/lessons.md`.
- Pattern fires across two projects → consider promoting to a personal `~/.claude/global-memory/` or to this template.
