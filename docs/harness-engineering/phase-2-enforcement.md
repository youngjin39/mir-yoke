---
phase: 2
title: Enforcement
status: consolidated-v1
depends_on: phase-1-start-harness
---

# Phase 2 — Enforcement

> **Purpose**: Enforce critical rules via code, not prose. 4 enforcement binding types: hook / script / validator / deny-list.

## 0.5 Design Goals (R9 anchor)

> This phase's connection to the [3-axis fleet goals](applications/fleet-catalog.md). When adding a new phase or cherry-picking for a family, the `design` skill (R9-T11) requires `design_goals` as a mandatory input.

**3-axis contribution**:
- **Axis I (your-harness hardening)**: 4 hook types + deny-list + Codex execution lane routing (100% applied to your-harness)
- **Axis II (public template sync)**: template hook catalog (family cherry-pick base, sanitization required)
- **Axis III (fleet central governance / back-propagation)**: per-family hook on/off + strictness override ([exceptions.md §3](applications/exceptions.md) matrix)

**Inter-phase contract**:
- **Input** (consumes): phase-1 (task_type + risk_level + required_checks 5 elements)
- **Output** (provides): hook firing results + Codex lane invocation + deny-list blocks → phase-4 state transition trigger

## 1. Core Principle

> Truly important rules must not live only in documents.

Documents guide; code blocks. Both together make enforcement.

## 2. Documentation vs Code Enforcement Matrix

| Item | Document | Code |
|---|---|---|
| Coding conventions | ○ | partial (linter) |
| Test requirement | guide only | **required** (pre-commit hook) |
| Prohibited path modification | guide only | **required** (pre-edit hook) |
| Dangerous command execution | guide only | **required** (deny-list) |
| Report format | ○ | optional |
| Review checklist | ○ | partial (validator) |
| Secret exposure | guide only | **required** (validator) |

## 3. 4 Enforcement Bindings

### 3-1. Pre-edit hook
Block immediately before file modification.
- Block modification of prohibited directories
- Block start when task state file is absent
- Confirm active task / run pointer
- Confirm SM is in ACT-capable state ([[phase-4-state-machine]])

### 3-2. Post-edit verify hook
Auto-run immediately after file modification.
- Format check
- lint
- Minimal test execution
- Record state as `NEEDS_FIX` on failure ([[phase-4-state-machine]] §run_state)
- Prohibit completion report bypass in failure state

### 3-3. Validator script
Static pattern detection.
- Unauthorized imports / forbidden API
- Dead code / duplicate blocks
- Secret patterns (`API_KEY|SECRET|TOKEN|PASSWORD`)
- Unauthorized path modification
- Security patterns (eval, exec, system shell)
- **Prompt Injection patterns** (§3-4)

### 3-4. Prompt Injection Defense (R4)

Block direct and indirect injection when external content flows into LLM input.

#### Applicable surfaces
| Surface | Applied | Reason |
|---|---|---|
| **WebFetch / WebSearch results** | enforced | External web pages may embed instructions |
| **External OSS borrowed code / borrow-from blocks** | enforced | OSS README/comments may embed injection |
| **MCP server responses** | enforced | External servers may return instructions |
| **External file reads** (outside trusted directory) | warn | User trust domain |
| **Discord plugin messages** | **exempt (off)** | User direct command channel, owner-trusted |
| **User direct input** | exempt (off) | User intent |
| **Memory SoT** | enforced | Defense against poisoning ([[phase-3-memory-context]] §13) |

#### Block patterns (regex)
```yaml
prompt_injection_patterns:
  - "ignore (all )?previous (instructions?|context|messages?)"
  - "you are now (a different|the new|an?) "
  - "system( prompt)? override"
  - "disregard (the |all )?(above|prior|earlier) "
  - "new instructions?:"
  - "<\\|im_start\\|>"
  - "\\[INST\\]"
  - "begin (a )?new (conversation|session|task)"
  - "forget (everything|all|your)"
```

#### Indirect injection additional checks
- WebFetch results: (1) detect above patterns → block (2) even without detection, check hostname allow-list (3) if suspicious, show raw text to user then confirm
- MCP server responses: verify server provenance + handle as `approval: required`

#### Application intensity stages
- First week: warn (measure false positives)
- After stabilization: enforced

#### Discord exemption rationale preserved
> The Discord plugin is the command channel through which the user drives this harness. Not exempting it would block user commands themselves. This exemption is an intentional decision; all other external surfaces apply enforced mode.

### 3-5. Deny-list
Block immediately before execution. Register patterns in `deny-list.yaml`.

| Pattern | Intensity |
|---|---|
| `git push --force` (main branch) | block |
| Recursive filesystem wipe | block |
| Destructive schema operations (production) | block |
| Editing merged migrations | block |
| Plain-text secrets (API keys, passwords) | block |
| Arbitrary log file reads | warn |
| Production DB access | block |

## 4. 3 Intensity Levels (warn → suggest → block)

When introducing new hooks, escalate gradually. Starting with block from the beginning kills development flow.

| Intensity | Behavior | Application timing |
|---|---|---|
| warn | Log only, execution continues | Immediately after new rule introduction |
| suggest | Request user confirmation | After 1 week of operation + false positive verification |
| block | Block + return failure | After stability confirmed |

**Exception**: Dangerous commands (force push / schema destruction / secret exposure) are block from the start.

## 5. Circuit Breaker

Force stop work when the same error repeats n times.

```yaml
# Design intent: this YAML is the SM-side semantic classification,
# aligned 1:1 with the run_state.retry_count field (4 counters).
retry_budget:
  total_attempts: 3
  verify_failures: 2
  patch_conflicts: 1
  tool_failures_same_type: 2
```

Exceeding n → request user intervention or trigger the 3-failure → forced architectural redesign circuit in [[phase-7-fleet-expansion]] §3.

**Code gap**: The 4 counter names in this §5 YAML match the `retry_count` object in `run_state.schema.json`. However, the current implementation (`tools/.../circuit_breaker.py`) uses different parameters (`consecutive_threshold`, `window_size`, `window_failure_rate`) — code modification deferred since it is in a sealed area. This §5 YAML is **design intent** and requires sealed schema update when applied to code.

## 6. Codex+Claude Role Enforcement

Table of [[phase-5-subagents]] Worker Isolation from the enforcement perspective.

| Role | Author | Verifier |
|---|---|---|
| code changes | Codex executor lane | codex-final-reviewer + Claude merge judgment |
| design/planning | Claude | sub-agent review |
| ADR | Claude | quality-agent |

Claude direct Edit/Write on code surfaces (`src/`, `tools/`) is blocked by hook (your-harness policy).

## 7. 7-Step Safety Layer (concept)

General model for hooks. Place authentication, authorization, and monitoring at 7 points in the LLM cycle.

1. Immediately before model input (before-LLM)
2. Immediately after model's tool use reasoning (after-LLM)
3. Immediately before tool function call (before-tool)
4. Inside tool function
5. Immediately after tool response (after-tool)
6. Immediately before tool response enters LLM input
7. Immediately after final answer generation (safety filter)

The `.claude/hooks/pre-tool-use.sh` corresponds to point 3, `post-edit-verify` to point 5.

## 8. Enforcement Area vs Advisory Area

Of the 5 layers in [[phase-0-foundations]] §3, makes clear which to enforce and which to guide only.

| Area | Enforced | Reason |
|---|---|---|
| `src/`, `tools/` code path | ○ | TDD ledger + Codex execution lane routing |
| pre-commit lint/test | ○ | Block verification gaps |
| `.claude/agents/`, `.claude/skills/`, `docs/`, `tasks/` | ✕ (advisory) | Allow rapid iteration and experimentation |
| ADR cadence | ✕ (cadence reminder only) | Human judgment domain |

If this separation breaks, the harness is merely heavy and actual work gets blocked.

## 9. Prohibitions

- Placing only "don't do this" text without hook presence
- Completing with a success report from a failure state
- Completing code modification without tests
- Deferring to humans to check later
- Setting all hooks to block from the start (freezes development)

## 10. Application State

| Item | Status | Location |
|---|---|---|
| pre-edit hook | land | `.claude/hooks/pre-tool-use.sh` (BLOCK) |
| post-edit verify | land | `pre-commit-verification.sh` |
| TDD ledger | land | `tdd-guard.sh` + `tdd-matrix-guard.py` |
| Validator script | land | `scripts/verify_*` |
| Deny-list | land | `.ai-harness/deny-list.yaml` expanded + `pre-tool-use.sh` enforced |
| 3 intensity levels | land | `tier_dispatch.sh` + `pre-commit-verification.sh` + `pre-tool-use.sh` |
| Circuit Breaker | land | `src/.../circuit_breaker.py` + `mcp_gateway.py` |
| 7-step Safety Layer | partial land | points 3 and 5 only |
| Enforcement vs Advisory separation | land | CLAUDE.md Hook Policy Boundary |
| **Prompt Injection defense (§3-4)** | land (advisory-first) | `src/.../prompt_injection_advisory.py` (9 regex), `artifact_sanitizer.py`, `intent_verification.py`. Discord/CLI exempt policy maintained. |
| **3 intensity level hook code** | land | `hook_chain.py` + `.claude/hooks/_lib/tier_dispatch.sh` provide suggest-tier bypass/logging. |

**Gap**: From phase-level closeout perspective: none. Future hardening backlog is prompt-injection additional surface expansion and deny-list family-tuning only.

## 11. Exit Criterion

pre-edit hook actually blocks at least 1 attempt to modify a prohibited path, and post-edit verify fires at least 1 failure report on an intentional lint/test failure case. Deny-list blocks at least 1 dangerous command (force push / secret pattern) actually observed.

**R7-A-W3 supplement (machine verification)**:
- pre-edit hook block: regression tests landed ✓
- post-edit verify failure firing: `pre-commit-verification.sh` regression landed ✓
- deny-list block: `tests/test_hook_scripts.py` regression landed ✓
- 3-intensity hook behavior: `tests/test_hook_tier_application.py` + `tests/test_hook_scripts.py` regression landed ✓

## 11-1. Prompt Cache Impact (R7-A-W4)

Changes to hook bindings in this phase affect [Phase 3 §6 Cache Stability](phase-3-memory-context.md). Obligations:

- **Prohibit mid-session modification of hook definition files** — if hook body is exposed as part of system prompt, prefix changes → cache miss
- **Batch deny-list pattern additions** — add multiple patterns in 1 commit, avoid frequent commits
- **Apply 3-intensity transitions (warn → suggest → block) between sessions** — changing intensity mid-session changes cache prefix

Violations of this §11-1 are detected at Phase 6 §2 metric 8.

## 12. Next Steps

Parallel options: [Phase 3 — Memory & Context](phase-3-memory-context.md) or [Phase 4 — State Machine](phase-4-state-machine.md).
