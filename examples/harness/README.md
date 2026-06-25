# Example-harness catalog

Opt-in **signature harness modules** you can overlay on the common base after
cloning. Where the sibling folders (`../add-feature/`, `../fix-bug/`, …) are
*walk-throughs of the workflow*, the modules here are *reusable harness bundles*
distilled from real projects — pick the ones that match your repo type and leave
the rest.

The idea: one common base + a few selected example-harness modules = a tailored
starting point for a new project, instead of re-deriving the same skills/agents
each time.

## How to apply (clone → compose)

1. Start from the **common base** — the harness already at the repo root after
   you clone (`.claude/`, `.ai-harness/`, `config/`, …).
2. Browse **[`catalog.json`](catalog.json)** (machine-readable index) or the
   table below, and pick modules whose `suited_repo_type` matches your project.
3. For each chosen module, copy `examples/harness/<name>/harness/*` into your
   own `.claude/` (and any `config/` snippets it ships), then read that module's
   `README.md` for wiring notes.
4. Modules are **opt-in** — nothing is applied automatically. Copy only what you
   want; skip the rest.

## Catalog index

Each module ships a `harness/` snippet directory, a `README.md`, and a
`manifest.toml`. `catalog.json` is the authoritative machine-readable list;
entries appear there as each module is extracted and sanitized.

| module | suited repo-type | summary | status |
|---|---|---|---|
| flutter-app-pack | flutter_se_product | Flutter app build / perf / security / test / UI harness bundle | planned |
| ops-self-evolution | ops_platform | Self-evolution + execution-governance ops harness | planned |
| market-strategy | product_market | Market-research / positioning / GTM strategy skills | planned |
| publishing-pipeline | content_pipeline | Compile → publish → social-draft content pipeline | planned |
| video-gen | video_pipeline | Short-form video generation pipeline config | planned |
| graph-knowledge | personal_knowledge | Knowledge-graph + note-integration skills | planned |
| ffmpeg-media | media_product | ffmpeg media-processing defaults | planned |

`status: planned` means the module is catalogued but its `harness/` snippet has
not been published yet. A module flips to listed in `catalog.json` once its
directory lands.

## Adding a module

New signature harness patterns graduate into this catalog as they prove reusable
across more than one project. Each module is **sanitized** before publishing —
no family names, local paths, secrets, or non-English text. Extraction and the
catalog update are a single step: add `examples/harness/<name>/` and append the
entry to `catalog.json`.
