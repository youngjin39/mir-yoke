---
name: graphify
description: Automated knowledge graph for large codebases + doc corpora. ~70x fewer tokens per query via graph-first navigation instead of raw file grep. Complements, does not replace, a curated knowledge layer.
triggers: [graphify, knowledge graph, large codebase search, god nodes, graph report]
---

# Graphify

External tool: https://github.com/safishamsi/graphify (MIT). A different
philosophy from a hand-curated wiki: **automated extraction, graph-first
navigation**. Use it as an automated read-optimization layer that sits
alongside (not instead of) any curated knowledge docs you keep.

## When to fire
- Repo has 500+ files OR a corpus of papers/PDFs/images you need to query
- `grep`/`Glob` over raw files would burn too many tokens
- User asks "what's in this codebase", "find everything related to X", "summarize the architecture"
- `GRAPH_REPORT.md` or `graph.json` already exists at repo root -> prefer graph navigation

## Skip when
- Repo has <50 files (overhead not worth it)
- Single-purpose small project / simple mobile app
- Early setup phases with no corpus to index yet

## Prerequisites
- Graphify installed: `pip install graphifyy && graphify install` (package name is **graphifyy** -- two y's, not graphify)
- `/graphify` command available in Claude Code
- Python 3.10+

## Procedure

### First-time indexing
```bash
graphify            # builds graph.json + GRAPH_REPORT.md + cache/
graphify --wiki     # also generates Wikipedia-style index.md + community pages
```
Output files (repo root):
- `graph.json` -- persistent queryable graph
- `GRAPH_REPORT.md` -- god nodes + communities + connections summary
- `graph.html` -- interactive visual
- `cache/` -- SHA256 incremental cache
- `index.md` (with `--wiki`) -- entry point for generated wiki

### Querying (via /graphify command)
Use the `/graphify` slash command. It redirects Claude to read `GRAPH_REPORT.md` + `graph.json` before touching raw files.

### Re-indexing triggers
- After a major refactor / large merge
- When `GRAPH_REPORT.md` timestamp > 7 days for actively developed repos
- When querying returns stale god nodes (symbol now removed/renamed)

## Integration with the harness

### PreToolUse hook coexistence
Graphify installs its own PreToolUse hook in `~/.claude/settings.json` (global)
that intercepts Glob/Grep and surfaces: *"graphify: Knowledge graph exists.
Read GRAPH_REPORT.md first."* If your project already defines its own
PreToolUse hook, both fire and there is no conflict -- they serve different
purposes (Graphify = routing hint, your hook = safety guardrail).

### Relationship to a curated knowledge layer
- **Graphify** = automated read-optimization layer. Machine-generated graph + wiki pages. Frequently refreshed.
- **Curated docs** (whatever knowledge store you keep, e.g. under `docs/`) = human-curated, high signal, rarely refreshed.

**Boundary rule**: Graphify's auto-generated `index.md` and community pages live
at **repo root** (where Graphify writes them) and are treated as **raw
sources**. Do NOT copy them directly into your curated docs. If a Graphify page
contains insight worth preserving long-term, distill it by hand into your
curated knowledge store with a citation back to Graphify.

### When both are active
1. Agent receives query
2. Graphify's hook fires -> agent reads `GRAPH_REPORT.md` first
3. Agent identifies god nodes / relevant communities
4. Agent reads targeted raw files (not full grep)
5. If the finding is worth curating -> distill it by hand into your curated docs
6. Lint/health-check your curated docs periodically (Graphify output is not linted -- it's machine-generated and self-refreshes)

## Hard rules
- **Never** edit Graphify output files (`graph.json`, `GRAPH_REPORT.md`, `graph.html`, auto `index.md`). They are rebuilt by `graphify`; edits will be lost and may corrupt the cache.
- **Never** mix Graphify's auto-wiki pages into your curated docs directly. Distill them by hand first.
- **Never** trust stale graphs. If `GRAPH_REPORT.md` is older than the most recent major commit touching core modules -> re-run `graphify`.
- If `/graphify` is not installed and the user asks for it -> hand back the install command, do not attempt auto-install (pip global install is user-terminal work).
- Do not commit `cache/` -- add to `.gitignore`. Other Graphify outputs (`graph.json`, `GRAPH_REPORT.md`) may be committed if the team wants shared graph state.

## Output format
When querying via Graphify:
```
GRAPHIFY: read GRAPH_REPORT.md -> god_nodes=[A, B, C] -> targeted_reads=[file1:range, file2:range]
Answer: {your synthesis with inline citations}
```
