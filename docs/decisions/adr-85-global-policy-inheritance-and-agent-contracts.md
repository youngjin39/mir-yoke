---
title: Global Policy Inheritance and Cross-Runtime Agent Contracts
type: template-adr
created: 2026-08-29
status: accepted
amends: [adr-09, adr-84]
schema: docs/templates/_schema/adr.schema.json
---

# ADR-85 — Global Policy Inheritance and Cross-Runtime Agent Contracts

## 1. Context

Mir Yoke is a public template, not an operator policy bundle. Its generated project Codex
configuration nevertheless selects an approval policy, native-agent concurrency and depth, and
native collaboration enablement. Project configuration has higher precedence than user-global
configuration, so those generated values can override an operator's evaluated fleet policy.

The maintainer agent sources also retain one deprecated native-tool loading sequence and fixed
thread/depth assumptions. Read-only Codex sandbox generation partly depends on agent slugs instead
of source metadata. Existing repositories may additionally keep local skill registry entries after
the same common skills move to plugin delivery.

## 2. Decision

### 2.1 Operator-owned global policy

Generated project Codex configuration will not select `approval_policy`, a root `[agents]` table,
or `features.multi_agent`. Approval, permissions, native collaboration enablement, default
sub-agent model and effort, context inheritance, concurrency, and lifecycle limits belong to the
operator-owned global policy or another higher authority selected by the operator. Mir Yoke keeps
only project-owned options such as hook activation and project documentation limits.

### 2.2 Runtime-neutral agent contracts

Maintainer agents will use the supported MCP or native collaboration operations exposed by the
current host. They will not prescribe a deferred tool lookup, a named legacy tool bundle, a fixed
spawn/wait/close sequence, or repository-owned thread and depth constants. Category routing is
resolved through `scripts/mir.sh policy resolve --category <category>` and explicit fields are
passed when the active policy requires them.

Read-only behavior is authored in agent frontmatter. The generator maps
`disallowedTools: Write, Edit` to a read-only Codex sandbox and does not infer permissions from an
agent slug. An authorized edit request for a read-only advisor is returned to the control-plane
main rather than executed by that advisor.

### 2.3 Cross-runtime model boundary

Claude model frontmatter and Codex custom-agent pins are separate runtime surfaces. This decision
does not remove the maintainer pack's Claude `model:` fields or make the Claude agent schema more
permissive. Generated Codex custom agents remain unpinned by omitting `model` and
`model_reasoning_effort`, so active global routing can apply unless a separately evaluated Codex
exception is intentionally authored.

### 2.4 Externally supplied skills

Mir Yoke continues to publish common skills only through namespaced plugins. Existing repository
registries that still describe those skills as local must mark them `external` with an `external`
source path, or remove the entries when their schema discovers runtime capabilities directly.
Maintainers must not recreate raw local skill directories merely to satisfy an obsolete registry.

## 3. Source and generation boundaries

- Author agent behavior in `.claude/agents/*.md`.
- Author Codex generation in `scripts/generate_codex_derivatives.sh`.
- Generate `AGENTS.md`, `.codex/`, and `.codex-sync/manifest.json`; do not hand-edit them.
- Keep Starter and Project Agent Kit payloads unchanged.
- Reconcile `.mir/capability-lock.json` only against a committed source revision because the lock
  proves Git object content, not uncommitted worktree bytes.

## 4. Consequences

- User-global or managed Codex policy is no longer shadowed by the public template.
- Native agent contracts remain valid across hosts with different collaboration operations.
- Read-only enforcement is reviewable at the canonical source instead of hidden in slug logic.
- Claude-specific routing can be evaluated independently without weakening Codex global routing.
- Legacy skill registries receive an explicit migration path without duplicating plugin bodies.

## 5. Out of scope

- Selecting global model routes, concurrency values, approval behavior, or permission profiles.
- Removing Claude model pins or changing the agent frontmatter schema and loader.
- Reintroducing local copies of common plugin skills.
- Updating the Starter, Project Agent Kit, consumer repositories, tags, or releases.

## 6. Verification

- Generated root Codex configuration omits approval and native-agent routing defaults.
- Generated Codex custom-agent TOML files omit model pins.
- Generated orchestrator and executor contracts contain no deprecated native-tool sequence or
  hard-coded thread/depth values.
- A slug alone cannot produce a read-only sandbox, while read-only frontmatter does.
- Bootstrap validation accepts a project Codex configuration without `approval_policy`.
- Decision authority, asset classification, external-skill integration, link integrity, generated
  parity, capability lock, and focused tests pass within their stated authority boundary.
