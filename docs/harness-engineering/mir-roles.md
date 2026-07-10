---
status: design-v1
date: 2026-05-23
scope: Dual-role separation (Tracker + Template Maintainer) + Identity disambiguation
audience: Harness operators + fleet adopters
priority: Resolves single-entity design flaw from prior audit
---

# Harness Roles — Dual-Role Charter + Identity Disambiguation

> **User refinement**: "your-harness = the agent that knows which harness engineering is applied to each repository, and manages the public template repository"

> **Prior audit finding**: A prior review treated the harness as a single entity. This doc resolves that by explicitly separating Role A (Tracker) + Role B (Template Maintainer) and distinguishing the agent-identity from the family-row identity.

## 0.5 Design Goals

**Three-axis contribution**:
- **Axis I (Self-harness strengthening)**: Separate the two roles (tracker + maintainer) into distinct lanes → resolves single-entity assumption structural flaw
- **Axis II (Public template sync)**: Template repo is explicitly the artifact maintained by Role B → applied-state owner confirmed
- **Axis III (Fleet central management)**: Role A tracks all fleet families / Role B maintains template — catalog/runbook separation per lane

**Inter-phase contract**:
- **Input (consumed)**: [phase-9 fleet-catalog](phase-9-fleet-catalog.md) (state cache) + [phase-7 fleet-expansion](phase-7-fleet-expansion.md) (family_type classification) + user refinement
- **Output (provided)**: Role A operational SLA + Role B maintenance charter + identity disambiguation rule → [phase-12 template-lifecycle](phase-12-template-lifecycle.md) + ADR-39 + ADR-40

## 1. Two Roles, One Agent

The harness agent performs **two job lanes** simultaneously.

| Lane | Role name | Responsibility | Artifacts |
|---|---|---|---|
| **A** | Per-Family Tracker | Track and manage harness engineering adoption state across all fleet families | `config/fleet-harness-state.json`, `config/fleet-drift-log/<family>-<ts>.json` |
| **B** | Template Maintainer | Standing maintenance of public template repo (`mir-yoke`) | Template repo VERSION + CI + health check + release notes |

**Key point**: The two lanes have different job scopes, different tools, different failure modes, and different cadences. This doc explicitly separates per-lane SLA, signals, and failure modes.

## 2. Role A — Per-Family Tracker

### 2-1. Charter
> The harness agent tracks all fleet family harness engineering adoption state (which phases / hooks / skills / agents each has adopted) via periodic scan + drift detection + share catalog operation. **Non-forced — observability + recommendation only**.

### 2-2. SLA
| Item | Target | On violation |
|---|---|---|
| State freshness | daily refresh | "stale" label + alert |
| Scan completion | all families < 10 min | partial-scan label + user review |
| Drift detection latency | catalog registration within 24h of innovation | latent_drift advisory |
| Catalog availability | 99% (daily) | downgrade to weekly cadence + cause investigation |

### 2-3. Consumed Signals
| Source | Signal | Location |
|---|---|---|
| Per-family repo | `.claude/{skills,hooks,agents}/*.md` file diff | `<family_path>/.claude/` |
| Per-family config | `config/repos/<family>.json` (harness-side cache) | harness-side |
| Per-family innovation notify | `harness_drift --notify <id>` CLI | manual |
| Phase-6 observability | per-family 7-axis rollup | `tools/fleet_observe/runner.py` output |
| Phase-7 adoption | family_type label changes | `config/repos/<family>.json.family_type` |

### 2-4. Operational Mode
- **Scan-pull** (default): daily cron `fleet_observe scan` reads each family repo path read-only
- **Push-notify** (exception): family owner directly registers via `harness_drift --notify <id>` (quick path for small innovations)
- **Webhook** (deferred): notification on family repo commit — deferred to future release

### 2-5. Failure Modes
| Mode | Action |
|---|---|
| Scan crash | Preserve partial results + alert + next cron retry |
| Network split (family path unreachable) | Update affected family `last_scan_status: unreachable` |
| Lock contention (another process writing state cache) | 60s wait + retry 3 times + alert |
| Disk full | Abort scan + user ops alert |
| Agent down | Role A degraded — manual recovery required. `role_a_runner.py` is an independent process (separate lock, separate cron). Agent session down still allows cron to directly invoke role_a_runner. |

### 2-6. Source-of-Trust Model
- Family-owner `--notify` claims are **not signed** (current version). Spoofing risk exists.
- Mitigation: notify only triggers `recommendations_received[].decision`; cannot directly mutate catalog `adoption.status`.
- Direct mutation only via daily scan (harness read-only).
- Future: HMAC signing or SSH commit signature verification.

## 3. Role B — Template Maintainer

### 3-1. Charter
> The harness agent is the standing maintenance owner of the public template repo (`mir-yoke`). In addition to promoting from self-harness lands, responsibilities include: (a) bug-fix-only PRs (b) link/schema health checks (c) dependency updates (d) security patches (e) deprecation procedures (f) release notes generation.

### 3-2. Maintenance Scope
| Category | Cadence | Tool / Process |
|---|---|---|
| Self-harness → template promote | event-driven (on self-harness land) | phase-10 §3 + `scripts/sanitize_for_template.py` |
| Bug fix only PR | as-needed | template-side commit (skip self-harness absorption) |
| Broken-link health check | daily | `tools/fleet_observe/template_health.py` |
| Schema validation | daily | template's own `tests/test_schema_validity.py` |
| Dependency bump | weekly review, monthly batch | `dep-auditor` agent + manual PR |
| Security patch | event-driven (CVE notification) | priority dispatch + fleet notification |
| Deprecation | monthly review | `applications/template-repo/upgrade-runbook.md` |
| Release notes | every version bump | template repo `CHANGELOG.md` |
| Dependency licensing | quarterly | `dep-auditor` license report |

### 3-3. Versioning Policy (semver)
- **PATCH** (`vN.M.X+1`): drift fix, doc typo, broken link repair, dependency security patch
- **MINOR** (`vN.M+1.0`): new phase / hook / skill, backwards-compatible extension to existing phases
- **MAJOR** (`vN+1.0.0`): breaking change (e.g. phase rename, schema field removal, hook signature change, family_type enum change)

VERSION file: `mir-yoke/VERSION` (single line semver). Git tag: `v<semver>`. CHANGELOG entry required.

See [`applications/template-repo/versioning.md`](applications/template-repo/versioning.md) for details.

### 3-4. Health Check Coverage
- **Internal link integrity**: resolve validation for `@import` and markdown link references
- **Schema validity**: self-validation of all `docs/templates/_schema/*.json`
- **Hook executability**: syntax + permission validation of `.claude/hooks/*.sh`
- **Phase doc completeness**: presence check for §0.5 + Exit Criterion + Apply State table in each phase-N-*.md
- **Cross-doc consistency**: README.md TOC matches actual file inventory

→ `tools/fleet_observe/template_health.py` daily report.

### 3-5. Failure Modes
| Mode | Action |
|---|---|
| Template repo broken (push failure, branch protection violation) | Alert + user review |
| Sanitize verifier fail | Abort promote, sanitize fix round |
| Dependency CVE | Priority patch + version bump (PATCH) + fleet notify |
| Template repo archive / rename / fork | [phase-12 template-lifecycle](phase-12-template-lifecycle.md) §sunset procedure fires |
| Agent down | Role B degraded — template frozen in last-known-good state, user manual maintenance possible. `role_b_runner.py` is an independent process. Role A and Role B lifecycle are separate. |

## 4. Role A vs Role B — Interface

Handoff points between the two lanes.

### 4-1. From catalog perspective
- Role A reads and writes all rows in `fleet-harness-state.json`.
- Role B writes only the `families.mir-yoke` row (template self-row) — Role A scan cannot update the template's internal version.
- Therefore the template row's `template_version` field is **Role B only** (result of self-harness land + sanitize + version bump).

### 4-2. Innovation flow
- Role A detects family innovation → registers in catalog → Discord digest.
- User decides "absorb to self-harness" or "promote to template directly" → decision is **hand-off to Role B's work queue**.
- Role B performs sanitize + sync + version bump → template updated.
- Role A confirms `template_version` updated in template row at next daily scan + auto-updates other family `recommendations_received`.

### 4-3. Failure isolation
- Role A fails (scan crash) → Role B operates normally (template work continues).
- Role B fails (template repo down) → Role A continues tracking other families normally, only template row is stale.
- Agent itself down → both lanes degraded, frozen at last-known-good.

## 5. Identity Disambiguation

### 5-1. Three different identifiers
| Name | Meaning | Location |
|---|---|---|
| **Agent-as-agent** | The agent performing Role A + Role B (LLM session + control plane) | live runtime — Claude session + Codex execution lane |
| **your-harness (family row)** | A row in the catalog — the agent tracking itself as a family | `fleet-harness-state.json.families.your-harness` |
| **Your-harness repo** | The actual code/docs base directory | filesystem |

**For SE-meta self-stop to work**: the your-harness row must match the **objective ledger** of the your-harness repo (`docs/harness-engineering/applications/example-harness/README.md` §2 ledger). **The agent must not over-rate its own row**.

### 5-2. Agent self-health file
The agent's own self-monitoring is separate from the family row. New file:
- Location: `config/agent-self-health.json`
- Contents: Role A's last scan timestamp + scan health, Role B's last template promote + version, failure mode occurrence counts for both lanes
- Updated: on every session entry + after every cron job
- Separate from: family row apply state

The family row is the your-harness repo's apply state; agent-self-health.json is the agent's runtime health. **These two concepts are explicitly separate**.

### 5-3. `mir-yoke` row family_type
The fleet_harness_state schema includes a `family_type` enum with 6 types (SE-meta / code_app / SE-product / hybrid_pipeline / template included). A prior audit flagged "behavior of template type undefined."

This doc defines:
- `family_type: "template"` meaning: **the reference repo maintained by the agent as Role B**. Different control lane from regular fleet families.
- Differences:
  - share-out semantics: template → forward share to all families (Role B sync)
  - share-in: family innovation arriving at template → Role B absorbs + sanitize + version bump
  - dogfooding exemption: template is "reference for applied state", not a dogfooding target (ADR-39 aligned)
  - applied-baseline obligation: all non-`n_a` phases in template must always maintain `adopted` state (Role B responsibility)

## 6. SoT Reconciliation Rule

Resolves a known SoT conflict found in a prior audit:
- `config/fleet-harness-state.json` showing a phase as `"adopted"`
- `docs/harness-engineering/applications/example-harness/README.md` §2 ledger showing the same phase as `pending`

**Rule (SoT precedence)**:
1. **The ledger is the source of truth** — `applications/example-harness/README.md` + each `phase-N-application.md`'s §"Work State" takes precedence
2. `fleet-harness-state.json`'s `families.your-harness.adoption[phase-N].status` **must match the ledger** — auto-synced in each daily scan (once code lands)
3. On conflict discovery:
   - Agent auto-reconciles: ledger → JSON update
   - On user pre-review: ledger updated (user SoT)
4. **`scripts/verify_self_stop.py`** checks at every share recommendation entry:
   - `assert ledger[phase-N].status == "adopted" if recommendation.source_family == "your-harness"`
   - On violation: BLOCK share + user alert

→ SE-meta self-stop runtime guarantee.

This §6 cross-references [`applications/fleet-catalog.md §1-bis`](applications/fleet-catalog.md).

## 7. Apply State

| Item | Spec landed | Operational evidence | Location |
|---|---|---|---|
| Role A scan (`fleet_observe scan`) | yes (§2-4) | partial — manual JSON editing only; runner does not auto-write state | `tools/fleet_observe/runner.py` |
| Role A drift detector | yes (phase-11 §2-2) | not yet — `harness_drift.py` absent | `tools/fleet_observe/harness_drift.py` |
| Role A SLA monitoring | yes (§2-2) | not yet — no heartbeat / alert | future release |
| Role A compatibility matrix operation | yes (phase-9 §5-2) | not yet — no machine-encoded form | `family_compatibility.schema.json` (deferred) |
| Role B template promote (sanitize + sync) | yes (phase-10 §3 + versioning.md) | not yet — `sanitize_for_template.py` absent | `scripts/sanitize_for_template.py` |
| Role B template health check | yes (ci.md §4) | not yet — `template_health.py` absent + no template CI | `tools/fleet_observe/template_health.py` + template repo CI |
| Role B versioning (VERSION file) | yes (versioning.md) | not yet — template `VERSION` file absent, 0 git tags | template repo |
| Role B CHANGELOG management | yes (versioning.md §4) | partial — CHANGELOG.md exists but format violations | template repo `CHANGELOG.md` rewrite |
| Role B MIGRATION.md | yes (versioning.md §1) | not yet — file absent | template repo |
| Role B work queue | yes (§4-2) | yes — backlog doc created with promote items + standing task observations | tasks/plan.md (live items) |
| Identity disambiguation doc | yes (§5 landed) | yes — this §5 + ADR-41 + fleet-catalog §1-bis aligned | this file |
| Agent self-health file | yes (§5-2 spec) | yes — `config/agent-self-health.json` + `tools/fleet_observe/self_health.py` | landed |
| SoT reconciliation rule (§6) | yes (landed) | partial — JSON ↔ ledger reconcile executed 1 time manually. Auto hook pending | §6 + `applications/fleet-catalog.md §1-bis` + `verify_self_stop.py` |
| Template repo current state snapshot | yes (landed) | yes — `applications/template-repo/current-state.md` recorded | — |
| Role A independent runner | yes (landed) | yes — `tools/fleet_observe/role_a_runner.py` + cron plist. 6-test suite PASS. | `tools/fleet_observe/role_a_runner.py` |
| Role B independent runner | yes (landed) | yes — `tools/fleet_observe/role_b_runner.py` + cron plist. 6-test suite PASS. | `tools/fleet_observe/role_b_runner.py` |

## 8. ADR alignment

- ADR-39 — Template Applied-State Charter (accepted)
- ADR-40 — Harness Template-Maintainer Charter (accepted)
- ADR-41 — verify_self_stop hook (design landed, hook code in future release)
- Future ADR candidate — `agent-self-health.json` schema formalization

## 9. Exit Criterion

This doc is done when:
1. Role A SLA table + Role B charter table published.
2. Three identities (agent / family row / repo) explicitly separated.
3. SoT reconciliation rule stated + `verify_self_stop.py` spec cross-referenced.
4. ADR-39/40/41 written.
5. User review passed.

## 10. Next steps

- [phase-12 — Template Lifecycle](phase-12-template-lifecycle.md) — Role B lifecycle (sunset + upgrade migration)
- [`applications/template-repo/`](applications/template-repo/) 4 files — Role B operational runbooks
- [`applications/fleet-catalog.md §1-bis`](applications/fleet-catalog.md) — SoT reconciliation rule measurement
