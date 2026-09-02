---
status: design-v1
date: 2026-05-23
scope: cross-cutting security baseline
audience: your-harness operators + external family adopters
---

# Security Baseline — Cross-cutting 5 Security Surfaces

> **Purpose**: Consolidate security concerns across phases. Integrate security items scattered across the 9-phase blueprint into one place and add missing areas. Apply OWASP LLM Top 10 + Agentic ASI Top 10 (2026) in the harness context.

## 1. Five Security Surfaces

| # | Surface | Primary Threat | Section |
|---|---|---|---|
| 1 | **Prompt Injection** (direct + indirect) | External instructions embedded in LLM input | §2 |
| 2 | **Tool Sandboxing** | Tool permission abuse, arbitrary command execution | §3 |
| 3 | **Supply Chain** | External OSS / MCP server / dependency tampering | §4 |
| 4 | **Memory Poisoning** | Malicious instructions embedded in persistent memory | §5 |
| 5 | **Inter-Agent Trust** | Agent A's output flows into agent B as trusted input | §6 |

## 2. Prompt Injection Defense

Details in [`../phase-2-enforcement.md`](../phase-2-enforcement.md) §3-4. This section is a cross-cutting summary.

### Application Surface Matrix

| Surface | Direct injection | Indirect injection | Enforcement level |
|---|---|---|---|
| WebFetch / WebSearch results | – | ○ | enforced |
| External OSS borrow-from blocks | – | ○ | enforced |
| MCP server responses | – | ○ | enforced |
| External file reads | – | ○ | warn |
| **Discord plugin** | – | – | **off (user command channel — intentional exemption)** |
| Direct user input | – | – | off |
| Memory SoT | – | ○ | enforced (coupled with §5) |

### Block Patterns
See regex list in [`../phase-2-enforcement.md`](../phase-2-enforcement.md) §3-4.

### Meaning of the Discord Exemption

> The Discord plugin is the command channel through which the user operates this harness. Without the exemption, user commands themselves would be blocked. This exemption is an intentional design decision.

The risk of Discord messages being exploited as a prompt injection channel is mitigated by two paths: (a) the user has no intent to attack themselves; (b) when Discord messages quote external content (e.g., raw text from an external URL), that external content is processed through the WebFetch flow, which is enforced.

## 3. Tool Sandboxing

### Permission Model

| Tool Type | Default Permission | Escalation Condition |
|---|---|---|
| Read (read, glob, grep) | All `*` | – |
| Edit / Write | Family scope only (`tools/`, `src/`, `docs/`, `tasks/`, etc.) | – |
| Bash | deny-list pass patterns only | Dangerous commands require user confirm |
| WebFetch | Hostname allow-list | Must pass injection validator |
| WebSearch | – | Rate limit |
| MCP tool | Per-server registration | Server provenance check |
| Discord reply | `mcp__plugin_discord_discord__reply` only | Must pass pairing |

### Per-call Permission Scope (R4 new recommendation)

The current deny-list is a pattern-based blanket block. A more sophisticated model: per-call permission scope.

```yaml
tool_call:
  tool: bash
  command: "git push origin main"
  required_scope:
    - git_write
    - remote_main_branch
  precondition:
    - ci_passed: true
    - approval_id: <ref>
```

ADR candidate 31 (R4 new). Currently sufficient with deny-list + Codex execution lane routing.

### Sandbox Intensity

| Intensity | Behavior | Application |
|---|---|---|
| process-level | Single sandbox HOME isolation | Current your-harness operation |
| chroot / namespace | Filesystem isolation | Per-family sandbox HOME |
| container | docker / podman | External OSS borrow experiments |
| hardware (gVisor / firecracker) | – | **Retired** (excessive for single-user scale) |

## 4. Supply Chain

### External Dependency Categories

| Category | Examples | Policy |
|---|---|---|
| Python packages | sqlite-vec, mlx, jsonschema | `requirements.txt` + version lock + vuln scan |
| MCP server | Official only | "Official MCP only" |
| OSS borrow | superpowers, OpenHarness, etc. | BORROWED-FROM block required |
| External model / tool | Claude Code, Codex CLI | Provider trust assumed |
| Memory wikycore | Shared wiki | Owner verification |

### Verification Obligations

1. **Maintain SBOM** — `requirements.txt` + system dependencies listed in `setup.sh`
2. **Vulnerability scanning** — dep-auditor subagent quarterly cadence
3. **MCP server provenance** — user confirm required on `.mcp.json` changes
4. **BORROWED-FROM tracking** — source / sha / path / sym annotation for all borrowed OSS code
5. **Transitive dep audit** — audit not just direct dependencies but also indirect ones

## 5. Memory Poisoning

### Threat Model

External input → memory SoT → next session's LLM input. A time-delayed form of injection.

| Entry Path | Risk Level |
|---|---|
| Storing WebFetch results in memory | High |
| Storing MCP server responses in memory | High |
| Quoting external OSS borrowed code in memory | Medium |
| Direct user input to memory | Low (user trusted) |
| Discord message stored in memory | Low (user trusted) |

### Defense

1. **Source annotation on memory entries** (`owner` / `sot` fields in [`../templates/_schema/memory_entry.schema.json`](../../templates/_schema/memory_entry.schema.json))
2. **External-source memory in separate namespace** — `external/` prefix is an **operational convention** (not a formal schema field). Future schema addition of `source` or `namespace` field under consideration — ADR candidate 32 (R4-R1 new).
3. **Re-fire prompt injection validator on memory injection** (apply patterns from [`../phase-2-enforcement.md`](../phase-2-enforcement.md) §3-4 to the memory inject path)
4. **Use `status: deprecated`** — immediately deprecate suspicious entries
5. **Lifetime field** (`valid_until`) — 30-day default for external-source memory

### Phase 3 + Phase 8 Integration
- Phase 3 §13 R4 Exit Criterion: lifetime field required
- Phase 8 §6 lifetime cleanup cron: automatically archives deprecated/expired entries

## 6. Inter-Agent Trust

### Threat Model

When agent A's output flows into agent B as input, if A outputs malicious instructions (directly or through external influence), B receives them as trusted input.

### Adjacent Agent Paths in your-harness

| From | To | Trust |
|---|---|---|
| main-orchestrator → executor-agent | (Claude → Codex) | high — Claude itself |
| executor-agent → codex-final-reviewer | (Codex → Codex) | high — same lane |
| codex-final-reviewer → quality-agent | (Codex → Claude) | medium — verification lane |
| WebFetch agent → executor-agent | – | **low** — external content passes through |
| MCP plugin → main-orchestrator | – | **low** — external server |
| user ↔ main-orchestrator | (Discord) | high — user themselves |

### Handoff Contract Reinforcement (R4 new recommendation)

Add the following fields to the handoff contract in [`../phase-5-subagents.md`](../phase-5-subagents.md) §4:

```yaml
handoff:
  from_agent: <name>
  to_agent: <name>
  trust_level: high | medium | low
  sanitize_required: bool   # must be true if low
  output_schema: <ref>      # format validation
  prompt_injection_check: bool   # re-validate when to_agent quotes this
```

Low-trust input does not flow directly as instruction to to_agent but is **wrapped in a quoted block** (e.g., `quoted_content`).

### Security Aspect of Worker Isolation

The Worker Isolation 4-step in [`../phase-5-subagents.md`](../phase-5-subagents.md) §5 provides both self-evaluation avoidance and security benefits:
- Code written by Claude is verified by Codex → higher likelihood of catching malicious code Claude inadvertently writes
- Code written by Codex is merge-judged by Claude → higher likelihood of catching code Codex writes under external OSS influence

## 7. Security Aspect of SE-meta Self-Stop Protection

A security violation in your-harness = SE-meta self-stop. Automatic verification:

- If prompt injection validator blocks your-harness's own work → immediate stop
- Memory poisoning detected → isolate affected entries + user notification + temporarily halt all family autonomous operations
- Supply chain threat (dependency package vuln) detected → temporarily disable enabled_phases for affected phases

## 8. External Family Propagation Matrix (security surface axis — sub-view of [`exceptions.md`](exceptions.md) §3)

**SoT relationship** (R5-R1 explicit): This table is a **sub-view of the [`exceptions.md`](exceptions.md) §3 per-phase matrix reorganized along the security surface axis**. exceptions.md §3 is the source of truth; §8 here provides only the cross-cutting view. In case of conflict, exceptions.md §3 takes precedence.

| Surface | SE-meta (your-harness) | code_app | SE-product | hybrid_pipeline | content_app |
|---|---|---|---|---|---|
| Prompt Injection | enforced | enforced | enforced | enforced | enforced (same Discord exemption) |
| Tool Sandboxing | enforced | enforced | enforced | warn | warn (personal/content domain) |
| Supply Chain | enforced | enforced | enforced | enforced | enforced |
| Memory Poisoning | enforced | enforced | enforced | enforced | enforced |
| Inter-Agent Trust | enforced | enforced | warn | warn | off (single agent possible) |

Security is nearly enforced regardless of family type. The limited relaxation for hybrid_pipeline/content_app is a tradeoff between operational burden and risk.

## 9. your-harness Application Priority

| Step | Work | Dependencies | Estimate |
|---|---|---|---|
| SB-1 | Prompt injection validator implementation (Phase 2 §3-4) | – | 4h | scripted (R29-T08 land, advisory — `src/mir/core/engine/workflow/prompt_injection_advisory.py`) |
| SB-2 | Hostname allow-list policy (WebFetch) | SB-1 | 2h | scripted (R29-T10 land, advisory — `tools/security/webfetch_hostname.py` + `config/webfetch_hostname_allowlist.yaml`) |
| SB-3 | Memory entry source annotation + external namespace | Phase 3 | 3h |
| SB-4 | dep-auditor quarterly cadence established | – | 1h (cron) |
| SB-5 | Missing BORROWED-FROM block detection hook | – | 3h |
| SB-6 | Inter-agent trust handoff contract field addition | Phase 5 | 3h |
| SB-7 | sanitize_required automatic wrap | SB-6 | 3h |

Total estimate: 19h.

## 10. Per-Family Propagation Exceptions

See §8 matrix above.

Additional specifics:
- `example-infra` (code_app) → all enforced, infrastructure security first
- `example-notes` / `example-game` (SE-product) → all enforced
- `example-content` (hybrid_pipeline) → Tool Sandboxing / Inter-Agent Trust only at warn level
- `example-personal` (personal/content workspace) → personal context memory stays enforced, but user confirm cadence is relaxed

## 11. External References

- OWASP LLM Top 10 (2026) — LLM01 Prompt Injection, LLM03 Training Data Poisoning, etc.
- OWASP Agentic ASI Top 10 (2026) — A1 Memory Poisoning, A8 Inter-Agent Trust, etc.
- NeuralTrust ASI Top 10 (2026) — output validation / semantic firewall
- Anthropic Claude Code official — tool permission, MCP server provenance
- Project hard requirements — harness-specific security decisions

## 12. Change History

- 2026-05-23: Initial draft. Incorporates R3 verification P7 recommendations. 5 surfaces + Discord exemption explicit + external family matrix.
