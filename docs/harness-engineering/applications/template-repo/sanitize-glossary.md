---
status: design-v1
date: 2026-05-23
scope: your-harness → template sanitize glossary + substitution patterns + exempt file list
audience: your-harness Role B (Template Maintainer) + R11 sanitize_for_template.py developer
priority: R10-R1 newly established (resolves Slice 2 BLOCKING #4)
---

# Sanitize Glossary (your-harness → Template)

> **Purpose**: Korean→English glossary + family-specific→generic substitution table + exempt file list for use by `scripts/sanitize_for_template.py` (R11). R10-R1 newly established.

## 0.5 Design Goals (R10-R1 anchor)

**3-axis contribution**:
- **Axis I**: Block Korean / family-specific expressions in your-harness from leaking to template
- **Axis II**: Guarantee template "applied state" is English-only + generic
- **Axis III**: Zero Korean dependency risk when fleet adopts

**Inter-phase contract**:
- **Input** (consumed): all changes from your-harness land (commit hash)
- **Output** (produced): sanitized text → phase-10 stage 2 sync can proceed

## 1. Sanitize 3 Layers

| Layer | Target | Processing |
|---|---|---|
| **L1 Detection** | all user-facing strings (.md, comments in .sh/.py) | Hangul detection + family-specific term detection |
| **L2 Translation** | detected Korean strings | auto-substitute based on §2 glossary below; unmapped items go to user review |
| **L3 Generalization** | detected family-specific expressions | generic substitution based on §3 substitution table below |

## 2. Korean → English Glossary (mandatory)

Lookup table for Korean occurrences in user-facing strings (markdown body, code comments).

| Korean | English | Context |
|---|---|---|
| 하네스 | harness | core term |
| 하네스 엔지니어링 | harness engineering | core term |
| 신설 | added (newly) | section heading / changelog |
| 정합 | aligned / compatible | concept |
| 확장 | extended | changelog |
| 갱신 | updated | changelog |
| 적용 | applied / applies | concept |
| 미land | not landed | status |
| land 됨 | landed | status |
| 부재 | absent / missing | status |
| 결함 | flaw / defect | audit |
| 누락 | omission / missing | audit |
| 결정 | decision | concept |
| 의무 | mandatory | rule |
| 권고 | recommended | rule |
| 사용자 | user | role |
| 사용자 명시 | user-explicit | rule |
| 진실원천 | source of truth (SoT) | concept |
| 강제 | enforce / enforcement | rule |
| 강제 X | not enforced (opt-in only) | rule |
| 추천 | recommend / recommendation | concept |
| 자율 | autonomous | concept |
| 자율 X | not autonomous | concept |
| 검증 | verification | concept |
| 검토 | review | concept |
| 절차 | procedure | concept |
| 진행 | proceed / in progress | status |
| 완료 | complete | status |
| 부족 | insufficient | audit |
| 충돌 | conflict | concept |
| 해소 | resolved | audit |
| 모순 | contradiction | audit |
| 정의 | definition | concept |
| 시점 | timing / point in time | concept |
| 산출물 | artifact | concept |
| 흐름 | flow | concept |
| 위반 | violation | rule |
| 차단 | block | rule |
| 면제 | exempt / exemption | rule |
| 봉인 | sealed | family policy |
| 통보 | notify / notification | concept |
| 본 | this (in "this doc", "this phase") | document reference |

### 2-1. Handling Unmapped Terms
When unmapped Korean is detected:
1. sanitize_for_template.py enters `--review` mode
2. User explicit review — decide mapping then add to this glossary
3. Glossary updates do not require an ADR (table maintenance only)

### 2-2. Korean Text Exempt from Sanitize
Korean in the following areas is preserved (sanitize NOT applied):
- `archive/` (historical, preserved)
- `참고 문서/` (raw input, preserved)
- Korean slugs in `memory/` (reflexive reference)
- "Korean citation" sections in ADRs
- User quotes (e.g., "user-explicit (2026-05-23): ...")

## 3. Family-Specific → Generic Substitution

Auto-substitute family-specific terms from your-harness with generic expressions for the template.

### 3-1. Identity Substitution
| your-harness pattern | Template generic | Note |
|---|---|---|
| `Mir-harness`, `mir-harness` | `your-harness` | single name → generic name |
| `Mir-self` | `your-harness-self` | preserve self-reference |
| `Mir-as-agent` | `your-harness-agent` | agent reference |
| `your harness` (Korean) | `your harness` | Korean → English + generic |
| `Mir` (standalone, noun) | `your-harness` | careful — overlap risk |
| `youngjin39` (user GitHub) | `<your-org>` | remove personal identity |
| `<personal-name>` | (removed) | personal identity |
| `<personal-org>` | (removed) | personal identity |
| `<personal-location>` | (removed) | personal identity |

### 3-2. Path Substitution
| your-harness path | Template generic |
|---|---|
| `<your-harness-path>/` | `<your-harness-path>/` |
| `/Users/ai_agent/` | `~/` or `<user-home>/` |
| `<this-repo>` | `<this-repo>` |
| `~/.claude/` | `~/.claude/` |

### 3-3. Family Reference Substitution
When your-harness explicitly references other families (used as examples only):
- All active family slugs (example-notes, example-game, example-brand, example-app, example-personal, example-video, example-content, example-story, example-stock, example-learning, example-infra, example-service, example-harness, memory-keeper)
- In template: replace all with `<example-family>` or separate example family names (`example-product`, `example-code-app`, `example-meta`, `example-hybrid`, `example-content`)
- Generalize all references outside user quotes / examples

### 3-4. Discord Channel Substitution
| your-harness pattern | Template generic |
|---|---|
| `chat_id="<your-discord-channel-id>"` | `<your-discord-channel-id>` |
| `user="<example-user>"` | `<example-user>` |
| Private channel IDs | (removed) |

## 4. Exempt Files List

The following files are exempt from sanitize (preserved):

| File | Reason |
|---|---|
| `LICENSE` | Legal obligation, do not modify |
| `archive/**/*` | Historical record, preserved |
| `참고 문서/**/*` | Raw input, preserved |
| `memory/MEMORY.md` | (excluded, not committed to template) |
| `memory/**/*.md` | (excluded, not committed to template) |
| `config/repos/*.json` (all families) | (excluded, not committed to template) |
| `config/fleet-harness-state.json` | (excluded, your-harness-side state) |
| `config/fleet-drift-log/**/*` | (excluded, your-harness-side log) |
| `tasks/*.json` (current progress ledger) | (excluded) |
| `.git/`, `.venv/`, `node_modules/`, `__pycache__/` | tooling cache |
| `.DS_Store` | system file |

## 5. Test Harness (R11)

`tests/test_sanitize.py` (template repo side):
```python
def test_no_korean_in_template():
    # run test_no_korean_in_user_facing.py from ci.md §3-4

def test_no_private_paths():
    # verify zero occurrences of private harness path patterns

def test_no_personal_identity():
    # verify zero occurrences of personal identity strings

def test_no_family_specific_names():
    # verify zero private family name references (except example/quote areas)
```

`scripts/sanitize_for_template.py` `--dry-run` mode:
- Korean detection report
- Unmapped term list (review queue)
- Substitution diff preview
- Exempt file skip log

## 6. Sanitize Procedure (aligned with [phase-10 §3-3](../../phase-10-rollout-pipeline.md))

```bash
# 1. diff (your-harness → template changes)
python scripts/verify_codex_sync.py --diff

# 2. sanitize dry-run (verify changes)
python scripts/sanitize_for_template.py --dry-run --target <this-repo>

# 3. user review (decide unmapped terms)
# Discord or manual

# 4. sanitize apply
python scripts/sanitize_for_template.py --apply --target <this-repo>

# 5. verify test_no_korean / test_no_private_paths pass
cd <this-repo> && python tests/test_sanitize.py
```

## 7. Glossary Maintenance

Updating §2/§3 tables in this doc:
- New Korean term appears → add to §2 (user explicit review)
- New family / path appears → add to §3
- Glossary updates do not require an ADR — this doc PR only

## 8. your-harness Application Status (2026-05-23)

| Item | Status |
|---|---|
| This glossary | **this R10-R1 land** |
| `scripts/sanitize_for_template.py` | **not yet** (R11 code) |
| `tests/test_sanitize.py` | **partially landed** (some parts from R8 land, R11 reinforcement pending) |
| Dry-run mode | **not yet** (R11) |

## 9. Exit Criterion

1. Korean glossary ≥40 entries ✓
2. Family-specific substitution ≥10 patterns ✓
3. Exempt list ≥10 entries ✓
4. Test harness spec (R11 specified) ✓
5. Sanitize procedure (5-step) ✓
6. Glossary maintenance procedure ✓
7. User review passed

## 10. Next Steps

R11 — `scripts/sanitize_for_template.py` code land + glossary application + dry-run mode.
