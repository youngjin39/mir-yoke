# docs/_archive — Cold Historical Records

This subtree holds decision records that are no longer current authority. It exists
so the live `docs/` tree carries only what governs today, while the full text of a
retired decision stays retrievable in version control.

## What is here

- `decisions/` — retired decision records, one file per archived document, named
  `<original-slug>-historical.md`. Every entry is reachable from a compact pointer
  that stays at the document's original path under `docs/decisions/`.

## Why a pointer stays behind

Removing a document outright breaks every reference to it — agent surfaces,
runtime docstrings, other decisions, and the release manifest all cite these
paths. A pointer at the original path keeps those references resolving while the
retired body leaves the live corpus. Mir Harness established this pattern and
enforces it byte-wise; this tree ports it.

## Status values

An archived record keeps the status its authority repository assigned it:
`superseded` when a later decision replaced it, `archived` when it was retired
without a direct successor. A mirrored reference stub carries the same value as the
Mir Harness counterpart it mirrors, not the value it held while it incorrectly
claimed to be current.

## Properties

- **Reversible**: every file arrived through `git mv`, so history is preserved.
- **Not consumer payload**: `config/template-assets.json` classifies this tree as
  `historical`, which `config/adopter-boundary.json` lists in
  `remove_classifications`. Adopters never receive it.
- **Ledger-tracked**: `INDEX.md` records one append-only row per archived item.

Do not add new working documents here. Write them under the live `docs/` tree;
they arrive here only once retired and recorded in the ledger.
