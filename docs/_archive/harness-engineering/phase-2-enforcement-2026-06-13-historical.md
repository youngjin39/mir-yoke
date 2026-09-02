---
phase: 2
title: Enforcement
status: consolidated-v1
depends_on: phase-1-start-harness
---

# Phase 2 -- Enforcement

> **Purpose**: Enforce critical rules via code, not prose. Four enforcement bindings: hook / script / validator / deny-list.

## 0.5 Design Goals (R9 anchor)

**3-axis contribution**:
- **Axis I (self-harness hardening)**: 4 hook types + deny-list + Codex execution lane routing (100% applied to self)
- **Axis II (public template sync)**: template hook catalog (per-family hook set cherry-pick base, sanitize required)
- **Axis III (fleet central management)**: per-family hook on/off + strictness override (see applications/exceptions.md section 3 matrix)

**Inter-phase contract**:
- **Input** (consumes): phase-1 (task_type + risk_level + required_checks 5-element declaration)
- **Output** (provides): hook firing result + Codex lane invocation + deny-list block -> phase-4 state transition trigger

## 1. Core Principle

> Rules that truly matter must not live only in documentation.

Documentation advises; code blocks. Both together constitute enforcement.

## 2. Documentation vs Code Enforcement Matrix

| Item | Documentation | Code |
|---|---|---|
| Coding conventions | yes | partial (linter) |
| Test requirement | advisory only | **required** (pre-commit hook) |
| Forbidden path edits | advisory only | **required** (pre-edit hook) |
| Dangerous command execution | advisory only | **required** (deny-list) |
| Report format | yes | optional |
| Review checklist | yes | partial (validator) |
| Secret exposure | advisory only | **required** (validator) |

## 3. Four Enforcement Bindings

### 3-1. Pre-edit hook
Blocks before file modification.
- Blocks edits to forbidden directories
- Blocks start if task state file is absent
- Confirms active task / run pointer
- Checks SM (phase-4 state machine) for ACT-eligible state

### 3-2. Post-edit verify hook
Runs automatically after file modification.
- Format check
- Lint
- Minimal test execution
- On failure, records state as `NEEDS_FIX` (phase-4 section run_state)
- Prevents completion report bypass while in failure state

### 3-3. Validator script
Static pattern detection.
- Unauthorized imports / forbidden API
- Dead code / duplicate blocks
- Secret patterns (`API_KEY|SECRET|TOKEN|PASSWORD`)
- Unauthorized path modifications
- Security patterns (eval, exec, system shell)
- **Prompt injection patterns** (see section 3-4)

### 3-4. Prompt Injection Defense (added in R4)

Blocks direct and indirect injection when external content flows into LLM input.

#### Applicable surfaces
| Surface | Applied | Reason |
|---|---|---|
| **WebFetch / WebSearch results** | enforced | External pages may embed instructions |
| **External OSS borrowed code** | enforced | OSS README/comments may embed injection |
| **MCP server responses** | enforced | External server may return instructions |
| **External file reads** (outside trusted dirs) | warn | User trust zone |
| **Discord plugin messages** | **exempt (off)** | User direct command channel, trusted |
| **User direct input** | exempt (off) | User intent |
| **Memory SoT** | enforced | Poisoning defense |

#### Block patterns (regex)
```yaml
prompt_injection_patterns:
  - "ignore (all )?previous (instructions?|context|messages?)"
  - "you are now (a different|the new|an?) "
  - "system( prompt)? override"
  - "disregard (the |all )?(above|prior|earlier) "
  - "new instructions?:"
  - "<\|im_start\|>"
  - "\[INST\]"
  - "begin (a )?new (conversation|session|task)"
  - "forget (everything|all|your)"
```

#### Indirect injection additional verification
- WebFetch results: (1) pattern detected -> block (2) even without detection, check hostname allow-list (3) if suspicious, show raw text to user and confirm
- MCP server responses: check server provenance + treat as `approval: required`

#### Enforcement severity stages
- First week: warn (measure false positives)
- After stabilization: enforced

#### Discord exemption rationale
> Discord plugin is the user command channel for operating this harness. Exempting it prevents user commands from being blocked. This exemption is intentional; all other external surfaces get enforced coverage.

#### Implementation status
9 regex patterns (PI-01~PI-09) scripted in advisory mode, WebFetch-only. Detect function returns `list[InjectionMatch]`; exempt when `source in {"cli", "discord"}`.
Tests: 19/19 PASS. Enforce flip deferred until 1-2 week false-positive data collected.

### 3-5. Deny-list
Blocks before execution. Patterns registered in `deny-list.yaml`.

| Pattern | Severity |
|---|---|
| `git push --force` (main branch) | block |
| Recursive directory removal | block |
| Destructive DDL on production DB | block |
| Editing merged migrations | block |
| `API_KEY\|SECRET\|TOKEN\|PASSWORD` plaintext | block |
| Arbitrary log file reads | warn |
| Production DB access | block |

## 4. Three Severity Stages (warn -> suggest -> block)

Escalate gradually when introducing new hooks. Starting at block kills development flow.

| Severity | Behavior | When to apply |
|---|---|---|
| warn | log only, execution continues | Immediately after introducing new rule |
| suggest | request user confirmation | After 1 week of operation and false-positive validation |
| block | block + return failure | After stability confirmed |

**Exception**: Dangerous commands (force push / destructive DDL / secret exposure) start at block.

## 5. Circuit Breaker

Force-stop a task when the same error repeats n times.

```yaml
# Design intent: this YAML maps 1:1 with run_state.retry_count fields (4 counters).
retry_budget:
  total_attempts: 3
  verify_failures: 2
  patch_conflicts: 1
  tool_failures_same_type: 2
```

Exceeding n -> request user intervention or trigger the phase-7 "3 failures -> forced structural redesign" circuit.

## 6. Codex + Claude Role Enforcement

Worker Isolation from phase-5 viewed from the enforcement side.

| Role | Author | Verifier |
|---|---|---|
| Code changes | Codex executor lane | codex-final-reviewer + Claude merge judgment |
| Design / planning | Claude | sub-agent review |
| ADR | Claude | quality-agent |

Claude direct Edit/Write on code surfaces (`src/`, `tools/`) is blocked by hook.

## 7. 7-Level Safety Layer (conceptual)

General model for hooks. Place auth/authz/monitoring at 7 points in the LLM cycle.

1. Before model input (before-LLM)
2. After model tool-use inference (after-LLM)
3. Before tool function call (before-tool)
4. Inside tool function
5. After tool response (after-tool)
6. Before tool response enters LLM input
7. After final answer generation (safety filter)

The pre-tool-use hook corresponds to point 3; post-edit verify corresponds to point 5.

## 8. Enforcement Domain vs Advisory Domain

Clarifies which of the phase-0 5 layers to enforce vs advise.

| Domain | Enforced | Reason |
|---|---|---|
| `src/`, `tools/` code paths | yes | TDD ledger + Codex execution lane routing |
| pre-commit lint/test | yes | Prevents skipping verification |
| `.claude/agents/`, `.claude/skills/`, `docs/`, `tasks/` | no (advisory) | Allow fast iteration and experimentation |
| ADR cadence | no (cadence reminder only) | Human judgment domain |

Collapsing this separation makes the harness heavy without protecting real work.

## 9. Prohibitions

- Documentation saying "do not X" without a hook backing it
- Completing work while in failure state
- Code modification without tests
- Deferring verification to human review later
- Setting all hooks to block from day one (freezes development)

## 10. Application Status

| Item | Status | Location |
|---|---|---|
| Pre-edit hook | landed | `.claude/hooks/pre-tool-use.sh` (BLOCK) |
| Post-edit verify | landed | `pre-commit-verification.sh` |
| TDD ledger | landed | `tdd-guard.sh` + `tdd-matrix-guard.py` |
| Validator script | landed | `scripts/verify_*` |
| Deny-list | landed | `.ai-harness/deny-list.yaml` expanded + `pre-tool-use.sh` enforced |
| 3 severity stages | landed | `tier_dispatch.sh` + `pre-commit-verification.sh` + `pre-tool-use.sh` |
| Circuit Breaker | landed | `src/.../circuit_breaker.py` + `mcp_gateway.py` |
| 7-Level Safety Layer | partial | points 3 and 5 only |
| Enforcement vs Advisory separation | landed | CLAUDE.md Hook Policy Boundary |
| Prompt injection defense | landed (advisory-first) | 9 regex patterns, Discord/CLI exempt |

**Gap**: No phase-level closeout gaps. Future hardening backlog: expand prompt injection surface coverage and deny-list family tuning.

## 11. Exit Criterion

The pre-edit hook must measurably block at least one forbidden-path edit attempt; the post-edit verify hook must measurably fire a failure report on at least one intentional lint/test failure. At least one dangerous command (force push / secret pattern) must be blocked by the deny-list in testing.

Regression tests verify all three: pre-edit block, post-edit failure fire, deny-list block.

## 12. Next Step

Parallel options: [Phase 3 -- Memory & Context](phase-3-memory-context.md) or [Phase 4 -- State Machine](phase-4-state-machine.md).
