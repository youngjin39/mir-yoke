---
name: repo-maintenance
description: "Periodic maintenance checkup of an agent-operated repository across twenty-one fixed items: consistency, operating base, documents, archiving, context, database/memory/graph inspection and repair, Claude/Codex harness consistency, skills and agents, instruction docs, rules and lessons, architecture, delegation and routing, continuity, work-context retrieval, token efficiency, test health, code/security/dependencies, integrity evidence, runtime behavior, open decisions, and parity when either CLI is Main.\n\nTrigger: repository maintenance, periodic check, repo checkup, fleet maintenance, clean up and improve the repository"
---

# Repository Maintenance

## Use When
- The owner asks for a full maintenance pass over one repository or every managed repository.
- A previous pass needs re-verification against actual files and command output.

## Bounds
- Read, review and status requests stay read-only. A fix request authorizes in-scope edits and relevant checks only.
- Commit, push, tag, release, protected paths, secrets and memory-store writes follow the repository's
  own authority rules. Use only documented commands for memory and generated files.
- Move stale or duplicate material verbatim to the repository's log or archive and leave a pointer.
  Never delete a rule, decision or lesson.
- Relaxing a constraint means removing duplication, dead checks or gates for removed features. It never weakens a safety guard.
- Parity repairs may add non-blocking context or logging, or remove leftovers. Never add restrictions, recreate owner-removed hooks, or block previously allowed behavior.
- A change that contradicts an accepted decision record or recorded owner intent is listed for the owner, not applied.
- Use a concept (fleet registry, bootstrap receipt, memory store, provider lock) only when the repository declares it.

## Checklist
Apply each item proportionately. Mark it done, no change needed (with evidence), or skipped (with a reason).
1. Consistency: profile and declared paths and commands match reality; docs match code; references resolve; generator parity holds.
2. Operating base: scripts, configs and hooks for removed features; dead entries.
3. Documents: plans, checklists and decision records state current facts. History is not rewritten.
4. Archiving: stale explanations, detailed history and duplicates move to the log or archive.
5. Context: always-loaded files stay minimal and procedures load on demand. Keep a single active cursor.
6. Database, memory and relation graph: inspect and repair integrity, size, stale or missing-source records and relation-graph defects through documented commands; read a stable snapshot of the database including WAL state left by open connections before diagnosing or repairing it.
7. Harness: excessive, duplicated or dead constraints are relaxed; Claude/Codex harness consistency is improved within Bounds.
8. Skills and agents: unused or duplicate capabilities, stale model or tool references, broken frontmatter.
9. Instruction docs: CLAUDE.md and AGENTS.md stay within size limits and carry the same rules for both runtimes.
10. Rules and lessons: each rule has one home, and lessons live in the declared location.
11. Architecture: the overview matches the actual layout and lists no removed components.
12. Delegation: model routing, delegation lanes and sub-agent limits follow the governing policy.
13. Continuity: one cursor, one resume pointer, one status projection and one evidence log.
14. Work context: one retrieval smoke query returns relevant anchors when retrieval is supported.
15. Token efficiency: session-start and hook output size, always-loaded file sizes, oversized routine reads.
16. Test health: the whole suite runs by default, stays hermetic, is not flaky under load, and new regression tests fail without their fix.
17. Code, security, dependencies: real defects, secret exposure, vulnerable or outdated dependencies, licenses.
18. Integrity evidence: locks, ledgers, receipts, audit chains and profile baselines are rebound through their documented commands after edits. Never fabricate provenance.
19. Runtime behavior: hooks fire, plugins and skills load, tool servers connect, and CLI versions match. Static documentation is not proof.
20. Open decisions: every pending owner decision is listed once, with both sides and the item it blocks.
21. Main-runtime parity: either Claude CLI or Codex CLI is Main and recognizes the same current rules, memory, design records, hooks, workflows and user intent. Check:
    - CLAUDE.md versus generated AGENTS.md, including nested instructions, carries the same rules and current design-record references.
    - Both register equivalent hook events and commands; list runtime-only events (Claude StopFailure, Codex-only events) as documented exemptions.
    - SessionStart delivers the same cursor, intent and native-memory index in both; compare observed content, not just configured paths.
    - The same skills and workflows load in both, and MCP bindings match.
    - Codex hook trust is current; untrusted or modified hooks block Codex-side enforcement. Refresh it through a documented trust command when the control plane provides one; otherwise record the gap without creating a new gate.
    - Prefer a synthetic payload or fresh session observation for these probes (item 19). Static docs are not proof; report unavailable runtime evidence as blocked or an evidenced exemption.

## Workflow
1. Record the request in the repository's active cursor, then read its contract and profile.
2. Start from a clean or snapshotted worktree so changes can be attributed.
3. Run the checklist. When available, use `mir-core:governance`, `mir-core:verify`, `mir-code:testing` and
   `mir-code:code-review` for item procedures. For many repositories, handle each one under its own contract.
4. Verify with the repository's documented tests and gates. Re-run them yourself before accepting delegated work.
5. Report against all twenty-one items using the evidence below.

## Report
Report per item, then list changed files, before/after instruction-doc sizes, checks with pass/fail counts,
fail-first evidence, integrity evidence to rebind, owner decisions and residual risks.
