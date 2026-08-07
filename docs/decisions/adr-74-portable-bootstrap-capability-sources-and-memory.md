---
title: Portable Bootstrap, Capability Sources, and Required Memory
status: accepted
date: 2026-08-06
---

# ADR-74 — Portable Bootstrap, Capability Sources, and Required Memory

## Context

Mir Yoke is intended to start a new repository on macOS, Windows, or Linux with the same minimum
agent harness. The current bootstrap only recommends memory initialization, materializes common
skills inside each repository, relies on Bash, and does not retain a trusted Git provenance record
for later skill or agent updates. Those properties allow a prose-first project to omit architecture
skills, create duplicate user/repository skill names, and finish setup without working memory.

## Decision

### 1. Cross-runtime capability provider

Common reusable skills are distributed from this Git repository as three namespaced plugins:

- `mir-core`: architecture, specification, governance, orchestration, verification, and maintenance
  skills required by every project.
- `mir-code`: code architecture, testing, and code-review skills.
- `mir-content`: knowledge and UI/content design skills.

Each plugin owns one self-contained `skills/` tree and exposes both `.claude-plugin/plugin.json`
and `.codex-plugin/plugin.json`. Claude Code and Codex CLI/desktop therefore load identical files
while their plugin namespaces prevent collisions. Codex IDE extensions do not currently load these
plugins and are outside the ready claim. Common plugin skills are not copied into repository-local
`.claude/skills` or `.agents/skills`. Repository-specific skills must use distinct names.

Plugin validation copies each plugin alone into a temporary cache-shaped directory and rejects any
missing relative reference or required script. A manifest's presence is not installation evidence;
Claude and Codex marketplace discovery and activation are verified separately.

Project-coupled agents, hooks, permissions, orchestration policy, and sub-agent policy remain local
and are generated as ordinary files. They are not activated from an unreviewed remote source.

### 2. Git provenance and update boundary

`config/capability-sources.json` records the trusted source URL, branch used for update discovery,
allowed plugins and agents, and project-type pack selection. `.mir/capability-lock.json` records
the exact resolved commit and selected tree hashes for reproducible setup on another machine.
The user-scoped provider registry records every consuming project and its required digest. Only one
version of a named global plugin may be active for a user; an update that conflicts with another
registered consumer is refused until those projects are deliberately reconciled.

The capability command has distinct operations:

- `status`: local, read-only lock and provider inspection.
- `check`: read-only remote comparison; it never changes the lock or active provider.
- `sync`: materialize and register only the currently locked commit.
- `update`: show the candidate commit and tree changes.
- `update --apply`: explicitly accept, lock, and activate a verified candidate.

Git is invoked without a shell. Credential-bearing URLs, traversal, absolute paths, symlinks,
submodules, and capabilities outside the declared plugin/agent allowlist are rejected. Remote
hooks, executable scripts, MCP servers, and permissions are never imported by capability sync.
Allowlisted agent Markdown may be updated only through explicit apply when its local content still
matches the prior lock; local divergence blocks replacement and is reported for manual merge or a
project-specific rename.

### 3. Required portable memory

Every completed bootstrap MUST have at least one working memory backend. The portable baseline is
a repository-local SQLite database with FTS5. It is required, works without a vector extension or
network service, and can be rebuilt from tracked Markdown archives on a new computer.

Bootstrap creates `harness_a.toml`, configures at least the `docs`, `tasks`, and `.ai-harness`
archives, applies migrations, indexes the archives, renders the tracked projections, and runs a
memory doctor. Completion is refused unless integrity, current schema, required tables, FTS5, an
insert/query rollback probe, and at least one successfully indexed archive are proven.

Vector and embedding modes are independent extensions:

- `off` (default): SQLite+FTS5 is ready; vector availability is informational.
- `optional`: vector failures are recorded as degraded but do not invalidate memory readiness.
- `required`: endpoint, dimensional, normalization, and indexing failures block bootstrap.

Tracked authored Markdown is the durable cross-machine memory source of truth. The live database
is a machine-local runtime query index/state store, and the bootstrap receipt is machine-local
evidence. Durable facts are authored in tracked documents and deterministically re-indexed.
Repositories may share
read-only tracked Markdown sources and an optional embedding endpoint. A shared network database or
vector service is not implemented by this release and must not be inferred from the local engine.

### 4. One bootstrap implementation

A Python bootstrap coordinator owns all behavior. `setup.sh` and `setup.ps1` are thin wrappers.
On Windows, PowerShell is the native bootstrap entrypoint while Git Bash is a declared prerequisite
for the existing hook runtime. A missing Bash runtime blocks readiness. Tracked runtime artifacts
must contain no symlinks.
The coordinator validates the selected `code_app`, `hybrid_pipeline`, `infra_runtime`, or
`content_workspace` profile and proves these surfaces before writing a ready receipt:

- memory and projections;
- common global plugin pack;
- project-local agents and both runtime manifests;
- hooks and permissions;
- orchestration and sub-agent policy;
- capability source and exact lock provenance.

Bootstrap has two activation phases because installed plugin state cannot become visible uniformly
inside the session that performed the install. Phase one performs a no-write preflight, installs or
verifies the pinned provider, and exits with `restart_required`. After Claude reload or a new Codex
session, phase two proves active provider hashes, then requires the initial project structure pass
to invoke `mir-core:design` followed by `mir-core:spec-architect` regardless of whether the first
product request was code or prose. Finalize requires non-empty `spec/STATE.md`, `spec/index.yaml`,
and `spec/graph.yaml` plus tracked JSON evidence that binds that sequence and those outputs to the
pinned capability commit; a boolean attestation alone cannot produce a ready receipt.

Phase two validates staged configuration/database/provider state,
atomically replaces only generated outputs, and writes the receipt last. Existing authored
configuration is preserved or reported as a conflict. Failed runs cannot leave a ready receipt,
and newly registered global state is rolled back where the host CLI supports a bounded reversal.

The first task type never changes the architecture baseline. This does not require every later
prose or fiction edit to invoke `spec-architect`; it requires the first project structure/spec pass
before normal work begins. The selected project profile controls optional packs.

### 5. External-first machine storage

External storage is an optional host profile, not a repository path committed into the template.
When selected, the repository and its project-local `.venv` stay on the external volume, while one
shared storage root on the same filesystem owns the uv cache, uv-managed Python installations, uv
tool environments, and Mir capability provider. Bootstrap records the resolved paths and refuses
the profile when the project and storage root are on different filesystems, because that would
force uv to copy cached package data instead of using its native clone/link mode.

The template uses environment-variable configuration as the portable contract. A macOS operator
may use user-home symbolic links as machine-specific entrypoints, but no tracked harness artifact
or cross-project skill/plugin provider depends on a symlink. Credentials, auth state, and small
launcher links stay in the user home; moving complete Claude or Codex homes is outside this profile.

## Rejected alternatives

- User-directory symlinks as capability distribution: they are not portable to native Windows and
  can target the wrong clone. A host-local storage entrypoint is allowed but never required.
- Same-name user and repository copies: Claude may shadow one while Codex may expose both.
- Repository copies for all common skills: they drift independently and lose global provenance.
- Automatic activation of the newest branch head: it executes mutable remote instructions without
  a reviewable trust boundary.
- Vector-only memory: it makes the minimum bootstrap depend on models, endpoints, and platform
  wheels that are not universally available.

## Acceptance criteria

1. Clean macOS, Windows PowerShell, and Linux runs call the same coordinator and create equivalent
   ready receipts without relying on symlinks.
2. Each selected common skill is loaded from exactly one namespaced plugin provider per runtime;
   `spec-architect` is present for every profile.
3. Bootstrap without sqlite-vec or an embedding server produces a current, integrity-checked,
   FTS-searchable database and indexed tracked archives. FTS5 is a hard platform prerequisite.
4. Missing tools, malformed configuration, zero archives, migration/sync/projection/doctor failure,
   provider collision, or unverified capability content prevents a ready receipt.
5. A pinned lock reproduces the same plugin hashes after the source branch advances; remote checks
   do not mutate files, locks, or runtime configuration.
6. Doctor proves a configured and registered archive, non-zero indexed documents/chunks, and a
   known tracked token retrievable through FTS; an empty archive is not readiness evidence.
7. Code and content profiles select the appropriate optional plugin and local agent packs.
8. A conflicting global provider digest, locally diverged managed agent, or unsupported Codex IDE
   surface is reported rather than silently overwritten or claimed ready.
9. A clean-clone release test validates manifests, isolated plugin closure, duplicate-provider
   rules, exact locked sync, wrapper parity, memory readiness, and the complete regression suite.
10. A baseline DB path outside the repository and an archive symlink escaping its declared root are
    rejected before any read or write. Required vector mode proves complete vector coverage rather
    than only extension or endpoint availability.
11. An explicit external storage root is used before dependency synchronization and readiness
    evidence proves the uv cache and project environment are on the same filesystem.

## Consequences

The template gains a strict setup dependency on Python 3.12+, `uv`, Git, Claude Code, and Codex CLI
for dual-runtime global plugin activation. Local status remains available offline; synchronization
and update checks require the configured Git source. Existing adopters using raw common skill copies need a migration
that removes or renames those copies before enabling the plugins.
