---
adr: 69
status: accepted
date: 2026-07-05
amended: 2026-07-15
source: sanitized-template-summary
amended_by: [adr-73]
---

# ADR-69 — Raw Codex Exec Ban

## Current Decision

- Raw `codex exec` is prohibited in every delegated route because of its demonstrated hang class.
- Claude-to-Codex delegation uses MCP.
- Codex-to-Codex breadth uses the native sub-agent lane.
- Isolated in-repository mutation may use MCP-backed `mir_executor --dispatch`.
- Missing MCP or native routing never permits a raw-exec fallback.

## ADR-73 Precedence

The ban applies when delegation is selected; delegation itself is proportional. A missing preferred
lane degrades that route rather than blocking the entire task when safe direct, native, MCP, or
manual work remains available under the repository contract.

The shell hook is a narrow recognizer for obvious direct command forms. It is not a general shell
parser and must not expand into one.
