---
phase: 4
sub_topic: approval_ui
status: design-v1
related: [adr-44, phase-4-application.md, approval.schema.json]
date: 2026-05-24
round: R18
---

# Phase-4 Approval UI — Discord Plugin Delegation

> **R18-T09 deliverable**. Documents why your-harness does NOT implement an
> interactive CLI approval prompt, and how Discord plugin reply fills the
> approval channel role.

## 1. Decision (per phase-4 application doc §3-9)

> §3-9. `approval` UI interactive mode — explicit decision to sunset (CLI environment + Discord
> plugin delegation) or minimal CLI prompt

**R18 decision**: explicit sunset of interactive CLI approval prompt. Discord
plugin reply tool (`mcp__plugin_discord_discord__reply`) is the approval
channel for all NEED_APPROVAL state transitions.

## 2. Rationale

**Why not implement CLI prompt?**

- Claude Code CLI runs as long-lived autonomous session. An interactive prompt
  would block the entire run until user types — defeating the autonomy.
- User is on Discord (remote channel). Typing into local CLI is not the user's
  primary interaction surface.
- Multiple concurrent runs (parallel families) would create overlapping CLI
  prompts that user cannot disambiguate.
- The user's directive (2026-05-24): "your-harness runs only on user command."
  NEED_APPROVAL fits this naturally: your-harness asks, user replies via Discord,
  your-harness proceeds.

**Why Discord plugin reply?**

- Discord is the user's already-active channel for instructing your-harness.
- `mcp__plugin_discord_discord__reply` already routes to the user (push
  notification on mobile).
- Reply contains text the user types — usable as approval payload.
- chat_id ↔ approval_id binding via inbound message metadata.

## 3. Protocol

### 3-1. NEED_APPROVAL request

When 13-state SM transitions PLAN → NEED_APPROVAL (or ACT → NEED_APPROVAL
for risky tool calls), `run_orchestrator.transition()` writes a new approval
record to `tasks/approvals/{approval_id}.json` matching
`docs/templates/_schema/approval.schema.json`:

```json
{
  "approval_id": "01J...",
  "run_id": "01J...",
  "status": "PENDING",
  "risk_level": "high",
  "auto_policy": "user_required",
  "requested_at": "2026-05-24T...",
  "discord_chat_id": "1494369577524662333",
  "discord_message_id_request": "1507..."
}
```

Concurrently, your-harness sends a Discord reply with the approval ask:

```
## Approval Required (approval_id: 01J...)

Run: 01J...
Risk: high
Action: <human-readable summary of what will happen>

Reply with: APPROVE 01J... | DENY 01J... | DELAY 01J... <reason>
```

### 3-2. User reply parsing

Inbound Discord message → `session-start.sh` or a dedicated
`approval-watcher.py` parses the user's reply for the patterns:

- `APPROVE <approval_id>` → set `approval.status = APPROVED`,
  `approved_at = now`, write back. Run resumes NEED_APPROVAL → ACT.
- `DENY <approval_id>` → set `approval.status = DENIED`, run transitions to
  CANCELLING → ROLLBACK → INTERRUPTED.
- `DELAY <approval_id> <reason>` → set `approval.status = DELAYED`, run
  transitions to BLOCKED with `blocked_reason = "user delayed: <reason>"`.

User can also reply with a free-form answer; your-harness prompts for clarification
once. If user does not reply within `auto_policy.timeout_minutes` (default
60), action depends on `auto_policy.on_timeout`:
- `deny` (default for high risk) → DENIED + INTERRUPTED
- `proceed` (only for low risk if user pre-authorized) → APPROVED
- `escalate` → another Discord ping + extend deadline

### 3-3. Concurrent approvals

Multiple runs may be in NEED_APPROVAL simultaneously. your-harness sends one Discord
message per pending approval, each tagged with its `approval_id`. User uses
the explicit approval_id in their reply to disambiguate.

## 4. Schema integration

`docs/templates/_schema/approval.schema.json` already supports:
- `discord_chat_id` (string, optional)
- `discord_message_id_request` (string, optional, ULID-or-discord-snowflake)
- `discord_message_id_response` (string, optional — set after user replies)

No schema changes required.

## 5. Implementation status

| Component | Status |
|---|---|
| `approval.schema.json` | ✅ exists (R7+) |
| Discord plugin reply tool | ✅ available via Claude Code MCP plugin |
| Discord plugin fetch_messages | ✅ available |
| `tools/run_orchestrator/approval_gate.py` | ⏳ R19+ (post-R18, when 13-state cutover) |
| `session-start.sh` reply parser | ⏳ R19+ |
| Auto-policy timeout watchdog | ⏳ R20+ (depends on cron policy decision) |

R18 ships **the design + schema readiness**. R19+ ships the implementation
when 13-state cutover happens.

## 6. Sealed family + personal SE-product family considerations

- **Sealed family** (example-stock, example-learning, and other sealed repos):
  approval flow disabled (sealed policy). All actions in sealed family auto-approve
  since user runs them manually anyway.
- **Personal SE-product family** (example-personal, example-learning): approval flow off by default
  per family_type personal SE-product strictness matrix (`enabled_phases=[0,1,7,8]` excludes
  phase-4 SM). Personal SE-product family acts always autonomous; user reviews after the fact.

## 7. Non-decisions (explicitly out of scope)

- **NOT building** a web UI for approvals (Discord is sufficient).
- **NOT supporting** Slack / Telegram / email as approval channels (would
  require parallel watchers).
- **NOT auto-approving** based on tool risk heuristics (auto_policy is
  user-configured, not learned).
- **NOT persisting** approval history in `memory.db` for now (text logs in
  `tasks/approvals/` directory suffice).

## 8. Verification

R18-T10 (round close) verifies:

1. `tasks/approvals/` directory exists (empty placeholder OK).
2. `approval.schema.json` has Discord fields documented.
3. This doc accepted as R18-T09 artifact.
4. No CLI prompt code introduced in R18.

## 9. Related

- [[ADR-44]] 13-state SM migration (parent ADR)
- `phase-4-application.md` §3-9 (the decision lattice)
- `phase-4-state-machine.md` §1 (NEED_APPROVAL state in SM)
- `docs/templates/_schema/approval.schema.json` (the schema)
