---
status: design-v1
date: 2026-05-25
scope: fleet family overview catalog — all active families
audience: your-harness operators + external adopters
---

# Fleet Families Overview

> Auto-generated family cards. Source of truth: `config/fleet-harness-state.json`.

## 1. SE-meta (Self-referential)

### your-harness

| Field | Value |
|---|---|
| Slug | `your-harness` |
| Family type | SE-meta |
| Sealed | no |
| Path | `<family-repo-path>/your-harness` |
| Active phases | 0–14 |
| Description | The harness itself. Control plane for all other families. |

### template-harness

| Field | Value |
|---|---|
| Slug | `template-harness` |
| Family type | SE-meta |
| Sealed | no |
| Path | `<family-repo-path>/template-harness` |
| Active phases | 0–14 (public template) |
| Description | Public sanitized template. Structural verification only — no operational runs. |

### example-harness

| Field | Value |
|---|---|
| Slug | `example-harness` |
| Family type | SE-meta |
| Sealed | no |
| Path | `<family-repo-path>/example-harness` |
| Active phases | 0–14 |
| Description | Reference implementation accompanying the template. Demonstrates all harness features in a concrete working example. |

## 2. code_app

### example-notes

| Field | Value |
|---|---|
| Slug | `example-notes` |
| Family type | code_app (Flutter) |
| Sealed | no |
| Path | `<family-repo-path>/example-notes` |
| Active phases | 0–9 |
| Baseline AI score | 50 |
| Description | Flutter-based notes app. First external family in the operational verification queue. |

### example-game

| Field | Value |
|---|---|
| Slug | `example-game` |
| Family type | code_app (Flutter) |
| Sealed | no |
| Path | `<family-repo-path>/example-game` |
| Active phases | 0–9 |
| Baseline AI score | 48 |
| Description | Flutter-based game application. Phase A verification target. |

### example-brand

| Field | Value |
|---|---|
| Slug | `example-brand` |
| Family type | code_app |
| Sealed | no |
| Path | `<family-repo-path>/example-brand` |
| Active phases | 0–8 |
| Baseline AI score | 68 |
| Description | Brand/fashion product application. No common harness gate discovered yet; bootstrap discovery required first. |

### example-infra

| Field | Value |
|---|---|
| Slug | `example-infra` |
| Family type | code_app |
| Sealed | no |
| Path | `<family-repo-path>/example-infra` |
| Active phases | 0–9 |
| Baseline AI score | 61 |
| Description | Infrastructure/home-hub application. Phase C — higher blast radius; infra-adjacent runtime. |

### example-service (hermes)

| Field | Value |
|---|---|
| Slug | `example-service` |
| Family type | code_app |
| Sealed | no |
| Path | `<family-repo-path>/example-service-hermes` |
| Active phases | 0–9 |
| Baseline AI score | 58 |
| Description | Service layer application (hermes variant). Phase C — infra/runtime repo. |

## 3. SE-product

### example-app

| Field | Value |
|---|---|
| Slug | `example-app` |
| Family type | SE-product (Flutter) |
| Sealed | no |
| Path | `<family-repo-path>/example-app` |
| Active phases | 0–9 |
| Baseline AI score | 48 |
| Description | Flutter reader application with preserved history. Phase A verification target. |

### example-personal

| Field | Value |
|---|---|
| Slug | `example-personal` |
| Family type | SE-product (personal) |
| Sealed | no |
| Path | `<family-repo-path>/example-personal` |
| Active phases | 0–8 |
| Baseline AI score | 54 |
| Description | Personal life workspace. User autonomy domain — auto critical/high escalation prohibited. |

### example-learning

| Field | Value |
|---|---|
| Slug | `example-learning` |
| Family type | SE-product |
| Sealed | yes |
| Path | `<family-repo-path>/example-learning` |
| Active phases | 0–8 |
| Baseline AI score | 50 |
| Description | Career/learning workspace. Sealed; only bounded operational fixes allowed. Has local score script at `.claude/skills/ai-readiness-cartography/scripts/score.py`. |

## 4. hybrid_pipeline

### example-video

| Field | Value |
|---|---|
| Slug | `example-video` |
| Family type | hybrid_pipeline |
| Sealed | no |
| Path | `<family-repo-path>/example-video` |
| Active phases | 0–9 |
| Baseline AI score | 53 |
| Description | Short video production pipeline. Phase A verification target. |

### example-content

| Field | Value |
|---|---|
| Slug | `example-content` |
| Family type | hybrid_pipeline |
| Sealed | no |
| Path | `<family-repo-path>/example-content` |
| Active phases | 0–9 |
| Baseline AI score | 50 |
| Description | Content writing/scoring pipeline. Phase A verification target. |

### example-story

| Field | Value |
|---|---|
| Slug | `example-story` |
| Family type | hybrid_pipeline |
| Sealed | no |
| Path | `<family-repo-path>/example-story` |
| Active phases | 0–8 |
| Baseline AI score | 39 |
| Description | Story/fiction writing pipeline. Lowest baseline score in fleet; highest improvement potential. |

### example-stock

| Field | Value |
|---|---|
| Slug | `example-stock` |
| Family type | hybrid_pipeline |
| Sealed | yes |
| Path | `<family-repo-path>/example-stock` |
| Active phases | 0–8 |
| Baseline AI score | 56 |
| Description | Stock analysis pipeline. Sealed; Phase B — partial adoption. |

## 5. Sealed Families

| Slug | Sealed since | Reason |
|---|---|---|
| `example-stock` | 2026-05 | Partial adoption; active but restricted to bounded fixes |
| `example-learning` | 2026-05 | Learning workspace; bounded fixes only |
| `example-brand` | 2026-06-11 | Temporarily sealed |
| `example-service` (openclaw) | 2026-05 | Infra/runtime; late-wave only |
| `example-service` (router-control) | 2026-05 | Effectively suspended |

## 6. Special Cases

### memory-keeper

`memory-keeper` is a standalone specialist agent (not a fleet family in the same sense). It operates as a federated second-brain component and is tracked separately from the family catalog.

### example-harness

The `example-harness` directory under `applications/` in the template repository documents the reference harness implementation. It mirrors the structure of `your-harness` (the actual harness) in sanitized form, showing how all features are applied end-to-end.

## 7. Character Clustering

Families share certain traits that determine compatibility for cross-family recommendation and innovation sharing. The clustering follows the `family_type` field above. SE-meta families are compatibility-checked separately; hybrid_pipeline families share media/content pipeline affinity.

| Cluster | Members | Shared trait |
|---|---|---|
| SE-meta | `your-harness`, `template-harness`, `example-harness` | Self-referential or template role |
| Flutter/mobile | `example-notes`, `example-game`, `example-app` | Flutter runtime, pubspec.yaml |
| Content pipeline | `example-video`, `example-content`, `example-story` | Media/text generation pipeline |
| Analysis pipeline | `example-stock` | Data/financial analysis pipeline |
| Infrastructure | `example-infra`, `example-service` | Runtime/service layer |
| Personal workspace | `example-personal`, `example-learning` | User autonomy domain |
| Brand/product | `example-brand` | Product/brand domain |
