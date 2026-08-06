---
title: Memory map — keyword index
description: Generated index over portable, tracked memory documents.
---

# Memory map

> Durable cross-machine memory is authored in tracked Markdown. `.mir/memory.db` is a required,
> machine-local SQLite+FTS5 query index that can be rebuilt from those documents.
> The keyword index below is a **generated projection** inside the `mir:generated` markers — never hand-edit it.
> Frontmatter required on every memory doc: title, keywords, related, created, last_used.

## Search protocol

1. Query the DB: `mir memory query <keyword>` (FTS5), or scan the generated index below.
2. Read only matched files.
3. If a file has a `related` field, consider loading related files too.
4. No match → skip — do not load the entire docs/ tree.

## Save protocol

1. Create memory file: `docs/<category>/<topic>.md` with frontmatter:
   ```yaml
   ---
   title: {title}
   keywords: [keyword1, keyword2, ...]
   related: [other-file.md, ...]
   created: {YYYY-MM-DD}
   last_used: {YYYY-MM-DD}
   ---
   ```
2. Synchronize tracked archives: `mir context sync`.
3. Regenerate the index: `mir memory render --target memory-map --apply --output-path docs/memory-map.md`.
4. The keyword index below is **DB-generated** — do not hand-edit it; update the tracked source,
   synchronize, and re-render instead.

## Promotion

- Pattern fires twice → capture the durable lesson in tracked Markdown, synchronize it, and then
  render the derived projections. A DB-only fact is machine-local and will not follow the repository
  to another computer.

<!-- mir:generated:start -->
## Keyword → File Index (DB projection)

| Keyword | File | Title |
|---|---|---|
| (no ingested documents) | — | — |
<!-- mir:generated:end -->
