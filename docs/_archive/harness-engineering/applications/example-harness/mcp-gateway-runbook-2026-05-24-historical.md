---
title: "MCP Gateway Runbook — example-harness Application"
keywords: [mcp-gateway, policy, tool-call, audit-log, proxy, forwarder, registry, allow-deny, agent-scope, cli]
created: "2026-05-24"
last_used: "2026-06-07"
type: runbook
---
# MCP Gateway Runbook — example-harness Application

Operational reference for the MCP gateway stack deployed in the your-harness project
(`tools/mcp_gateway/`).

---

## §1 Architecture Overview

The MCP gateway sits between the Claude Code MCP client (upstream) and downstream MCP
servers. It enforces tool-call policy, appends an audit log, and (stub-level) records
would-be downstream calls via transport adapters.

```
Claude Code (MCP client)
        |
        v
  tools/mcp_gateway/
    ├── registry.py       # policy load + evaluate(tool, agent) -> Decision
    ├── server.py         # MCPGateway.handle_tool_call (async) — applies policy + audit
    ├── audit.py          # AuditLogger — append-only JSONL, keys-only (no argument values)
    ├── proxy.py          # MCPProxy.route() — gateway + forwarder dispatch
    ├── forwarder.py      # StdioForwarder / HTTPForwarder stubs
    └── cli.py            # python -m tools.mcp_gateway check|audit-tail|route
        |
        v
  Downstream MCP servers (stdio / sse / http)
```

Policy decisions: `allow` | `deny` | `audit` (audit = allow + always log).
Per-agent scoping: tool rules may carry `"scope": "specific"` + `"agents": [...]` to
restrict the rule to named agents; others fall through to `default_policy`.

---

## §2 Policy Configuration

Policy lives in `config/mcp_gateway_policy.json`. Schema:
`docs/templates/_schema/mcp_gateway_policy.schema.json`.

Key fields:

| Field | Description |
|---|---|
| `version` | Always 1 for the current schema |
| `default_policy` | `"allow"` \| `"deny"` \| `"audit"` — applies when no tool rule matches |
| `tools` | Per-tool override map |
| `tools.<name>.policy` | `"allow"` \| `"deny"` \| `"audit"` |
| `tools.<name>.scope` | `"specific"` to gate on `agents` list; omit for wildcard |
| `tools.<name>.agents` | List of agent ids when `scope == "specific"` |
| `tools.<name>.reason` | Human-readable rationale string |

Example — deny shell_exec for all, allow Bash only for executor-agent:

```json
{
  "version": 1,
  "default_policy": "allow",
  "tools": {
    "shell_exec": {"policy": "deny", "reason": "no raw shell"},
    "Bash": {
      "policy": "allow",
      "scope": "specific",
      "agents": ["executor-agent", "codex-final-reviewer"],
      "reason": "Bash allowed for approved execution agents only"
    }
  }
}
```

---

## §3 CLI Usage

```bash
# Check if a tool call is allowed (text output)
python -m tools.mcp_gateway check --tool Bash --agent executor-agent

# Check with JSON output and custom policy
python -m tools.mcp_gateway check --tool shell_exec --format json \
  --policy config/mcp_gateway_policy.json

# Tail the last N audit entries
python -m tools.mcp_gateway audit-tail -n 20 --audit-log /tmp/mcp_audit.jsonl

# Route a tool call to a target (resolves target from settings.json mcpServers)
python -m tools.mcp_gateway route \
  --tool Bash \
  --agent executor-agent \
  --target filesystem \
  --settings ~/.claude/settings.json \
  --format json
```

Exit codes:
- `0` — allowed
- `1` — denied (check subcommand only)

---

## §4 Audit Log

The audit log (`audit_log_path` in `GatewayConfig`, default `logs/mcp_audit.jsonl`) is
append-only JSONL. Each entry contains:

```json
{
  "ts": "2026-05-24T00:00:00+00:00",
  "tool_name": "Bash",
  "agent": "executor-agent",
  "policy": "allow",
  "allowed": true,
  "reason": "Bash allowed for all agents (deny-list + design-complete-gate apply at L2)",
  "rule_matched": "Bash",
  "argument_keys": ["cmd"]
}
```

Privacy guarantee: argument **values** are never written to the log. Only the keys are
recorded. This is enforced in `AuditLogger.record()` — the `arguments` param is
key-extracted before persistence.

---

## §5 Forwarder Stubs

`tools/mcp_gateway/forwarder.py` provides two stub transport adapters:

- `StdioForwarder(command, args)` — records the would-be subprocess call; does not
  spawn a process.
- `HTTPForwarder(url)` — records the would-be HTTP request; does not open a connection.

Both return `ForwardResult(success=True, status="forwarded_stub", ...)` with a
`calls_recorded` list capturing transport metadata. Argument keys (not values) are
captured for audit purposes.

Wiring a stub into `MCPProxy.route()`:
1. Policy decision is `allow` or `audit`.
2. `target_name` matches a key in `MCPProxy.targets`.
3. The `ProxyTarget.transport` field selects the forwarder class.
4. `result["downstream_status"]` is set to `"forwarded_stub"`.
5. `result["forward_result"]` contains transport, success, and calls_recorded.

When no target is provided or the policy is `deny`, `downstream_status` is `"stub"` and
no `forward_result` key is emitted.

To promote a forwarder from stub to live, subclass `Forwarder` and implement
`forward()` to perform the actual subprocess spawn or HTTP call.

---

## §6 Testing

```bash
# Unit + integration tests for the full MCP gateway stack
python3.11 -m pytest tools/mcp_gateway/tests/ -v

# E2E integration tests (8 in-memory tests, no real MCP server)
python3.11 -m pytest tests/test_mcp_gateway_integration.py -v

# Combined (acceptance target — 43 pass)
python3.11 -m pytest tools/mcp_gateway/tests/ tests/test_mcp_gateway_integration.py -v

# Lint
ruff check tools/mcp_gateway/ tests/test_mcp_gateway_integration.py

# Smoke test
echo '{"mcpServers": {"stub": {"command": "python", "args": ["-m", "stub_server"]}}}' \
  > /tmp/smoke_settings.json
python3.11 -m tools.mcp_gateway route \
  --tool Bash --agent codex-final-reviewer \
  --target stub --settings /tmp/smoke_settings.json --format json
# Expected: downstream_status == "forwarded_stub"
```

Test inventory:

| Suite | Location | Count |
|---|---|---|
| Registry unit | `tools/mcp_gateway/tests/test_registry.py` | 8 |
| Server unit | `tools/mcp_gateway/tests/test_server.py` | 8 |
| Audit unit | `tools/mcp_gateway/tests/test_audit.py` | 6 |
| Proxy unit | `tools/mcp_gateway/tests/test_proxy.py` | 7 |
| CLI subprocess | `tools/mcp_gateway/tests/test_cli.py` | 6 |
| E2E integration | `tests/test_mcp_gateway_integration.py` | 8 |
| **Total** | | **43** |
