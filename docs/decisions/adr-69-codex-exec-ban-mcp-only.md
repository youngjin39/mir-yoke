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


## Amendment 2026-09-23 — Codex transport (owner decision A1)

Codex CLI 0.154.0 removed `codex mcp-server`. By owner decision A1 on 2026-09-23 (Discord, recorded in the Mir Harness run `claude-orchestration-codex-execution-restore-2026-09-23`; applied here by owner instruction of the same day), Claude-main delegates to Codex through the user-scope official Codex plugin (`codex@openai-codex`: `codex:codex-rescue` or `/codex:rescue`, passing `--model`/`--effort` from the central routing policy), and `tools/mir_executor` dispatches through `codex app-server`. Where this record names MCP as the Claude-to-Codex or `mir_executor` transport, read that transport. The raw `codex exec` ban and every other decision in this record are unchanged.
