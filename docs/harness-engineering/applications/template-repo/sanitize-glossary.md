---
status: design-v1
date: 2026-05-23
scope: source repo → template sanitize glossary + substitution patterns + exempt file list
audience: the template maintainer + R11 sanitize_for_template.py developer
priority: R10-R1 added (resolves Slice 2 BLOCKING #4)
---

# Sanitize Glossary (source → Template)

> **Purpose**: Korean→English glossary + family-specific→generic substitution table + exempt file list consumed by `scripts/sanitize_for_template.py` (R11). The authoritative Korean→English mapping is the `KOREAN_GLOSSARY` dict in code; this document is the human-readable, English-only spec. R10-R1 added.

## 0.5 Design Goals (R10-R1 anchor)

**3-axis contribution**:
- **Axis I**: Block the source harness repo Korean / family-specific expressions from leaking into the template
- **Axis II**: Guarantee the template "applied state" is English-only + generic
- **Axis III**: Zero Korean dependency when the fleet adopts the template

**Inter-phase contract**:
- **Input** (consumed): all the source harness repo landed changes (commit hash)
- **Output** (produced): sanitized text → phase-10 stage 2 sync may proceed

## 1. The 3 Sanitize Layers

| Layer | Target | Processing |
|---|---|---|
| **L1 Detection** | all user-facing strings (.md, comments in .sh/.py) | Hangul detection + family-specific term detection |
| **L2 Translation** | detected Korean strings | auto-substitute via the §2 glossary; unmapped terms go to user review |
| **L3 Generalization** | detected family-specific expressions | generic substitution via the §3 table |

## 2. Korean → English Glossary (mandatory)

The authoritative Korean→English mapping is the `KOREAN_GLOSSARY` dict in `scripts/sanitize_for_template.py` (~42 entries). It is applied to user-facing strings (markdown body, code comments). To keep this public-facing spec English-only (Axis II), the Korean source keys are kept ONLY in the code dict and are not duplicated here. The English outputs it produces are:

`harness`, `harness engineering`, `added (newly)`, `aligned / compatible`, `extended`, `updated`, `applied / applies`, `not landed`, `landed`, `absent / missing`, `flaw / defect`, `omission / missing`, `decision`, `mandatory`, `recommended`, `user`, `user-explicit`, `source of truth (SoT)`, `enforce / enforcement`, `not enforced (opt-in only)`, `recommend / recommendation`, `autonomous`, `not autonomous`, `verification`, `review`, `procedure`, `proceed / in progress`, `complete`, `insufficient`, `conflict`, `resolved`, `contradiction`, `definition`, `timing / point in time`, `artifact`, `flow`, `violation`, `block`, `exempt / exemption`, `sealed`, `notify / notification`, `this (document reference)`.

### 2-1. Unmapped Handling
When an unmapped Korean term is detected:
1. `sanitize_for_template.py` enters `--review` mode
2. user-explicit review — decide the mapping, then add it to the code `KOREAN_GLOSSARY`
3. the glossary update needs no ADR (table maintenance)

### 2-2. Exempt Korean
Korean in these areas is preserved (sanitize NOT applied):
- `archive/` (historical record)
- the reference-docs directory (raw input; the source harness repo only)
- Korean slugs under `memory/` (reflexive reference)
- the "Korean quotation" section of an ADR
- user quotes (e.g. a dated user-explicit quote)

## 3. Family-Specific → Generic Substitution

Auto-substitute the source harness repo family-specific terms with the template's generic expressions.

### 3-1. Identity Substitution
| the source harness repo pattern | Template generic | Note |
|---|---|---|
| `<your-project>`, `<your-project-lower>` | `your-harness` | single name → generic |
| `the source harness repo` | `your-harness-self` | self-reference |
| `<your-project>-as-agent` | `your-harness-agent` | agent reference |
| your harness (localized display form) | `your harness` | Korean → English + generic |
| `<your-project>` (standalone noun) | `your-harness` | careful — overlap risk |
| `youngjin39` (user GitHub) | `<template-owner>` | remove personal identity |
| `MaJu` | (removed) | personal identity |
| `LG Electronics` | (removed) | personal identity |
| `Seoul` | (removed) | personal identity |

### 3-2. Path Substitution
| the source harness repo path | Template generic |
|---|---|
| the the source harness repo project path | `<your-harness-path>/` |
| the user home directory | `~/` or `<user-home>/` |
| the public template repo path | `<this-repo>` |
| the the source harness repo agent-home path | `~/.claude/` |

### 3-3. Family Reference Substitution
the source harness repo references to other families (used as examples only):
- the 14 family slugs (grownote / hermes / home-hub / memory-keeper / minesweeper / mir-harness / musinsa-brand / my-life / quietleaf / shortmoviedirector / stockdirector / storydirector / write-score / claude-codex-harness)
- in the template: all replaced with `<example-family>` or distinct example family names (`example-product`, `example-code-app`, `example-meta`, `example-hybrid`, `example-content`)
- generalize every reference outside user quotes / examples

### 3-4. Discord Channel Substitution
| the source harness repo pattern | Template generic |
|---|---|
| a literal `chat_id="..."` | `<your-discord-channel-id>` |
| a literal `user="..."` | `<example-user>` |
| a literal channel id | (removed) |

## 4. Exempt Files List

These files are NOT sanitized (preserved):

| File | Reason |
|---|---|
| `LICENSE` | legal, do not modify |
| `archive/**/*` | historical record |
| the reference-docs directory (`**/*`) | raw input |
| `memory/MEMORY.md` | excluded — not committed to the template |
| `memory/**/*.md` | excluded — not committed to the template |
| `config/repos/*.json` (all families) | excluded — not committed to the template |
| `config/fleet-harness-state.json` | excluded — source-repo-side state |
| `config/fleet-drift-log/**/*` | excluded — source-repo-side log |
| `tasks/*.json` (active ledger) | excluded |
| `.git/`, `.venv/`, `node_modules/`, `__pycache__/` | tooling cache |
| `.DS_Store` | system file |

## 5. Test Harness (R11)

`tests/test_sanitize.py` (template-repo side):
```python
def test_no_korean_in_template():
    # runs the no-Korean-in-user-facing check from ci.md §3-4

def test_no_mir_self_paths():
    # asserts 0 occurrences of the the source harness repo absolute path pattern

def test_no_personal_identity():
    # asserts 0 occurrences of "youngjin39", "MaJu", "LG Electronics", "Seoul"

def test_no_family_specific_names():
    # asserts 0 family-name references (except example / quote regions)
```

`scripts/sanitize_for_template.py` `--dry-run` mode:
- Korean detection report
- unmapped term list (review queue)
- substitution diff preview
- exempt file skip log

## 6. Sanitize Procedure (aligned with [phase-10 §3-3](../../phase-10-rollout-pipeline.md))

```bash
# 1. diff (the source harness repo → template changes)
python scripts/verify_codex_sync.py --diff

# 2. sanitize dry-run (validate changes)
python scripts/sanitize_for_template.py --dry-run --target <template-repo-path>

# 3. user review (decide unmapped terms)
# via Discord or manual

# 4. sanitize apply
python scripts/sanitize_for_template.py --apply --target ...

# 5. verify test_no_korean / test_no_mir_self_paths pass
cd <template-repo-path> && python tests/test_sanitize.py
```

## 7. Glossary Maintenance

Updating the §2/§3 tables of this doc:
- new Korean term appears → add to the code `KOREAN_GLOSSARY` (user-explicit review)
- new family / path appears → add to §3
- the glossary update needs no ADR — doc PR only

## 8. Adoption State (2026-05-23)

| Item | State |
|---|---|
| this glossary | **R10-R1 landed** |
| `scripts/sanitize_for_template.py` | landed (R11 code) |
| `tests/test_sanitize.py` | partially landed (R8 partial, R11 reinforced) |
| Dry-run mode | landed (R11) |

## 9. Exit Criterion

1. Korean glossary ≥40 entries ✓
2. Family-specific substitution ≥10 patterns ✓
3. Exempt list ≥10 entries ✓
4. Test harness spec (R11) ✓
5. Sanitize procedure (5-step) ✓
6. Glossary maintenance procedure ✓
7. user review passed

## 10. Next Step

R11 — `scripts/sanitize_for_template.py` code landed + glossary applied + dry-run mode.
