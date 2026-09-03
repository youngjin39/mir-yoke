---
title: Global Plugin Migration Gate for Existing Repositories
status: accepted
date: 2026-08-07
amended_by: [adr-89]
---

# ADR-75 — Global Plugin Migration Gate for Existing Repositories

> **2026-09-03 discovery amendment:** ADR-89 requires the real-CLI acceptance probe to verify the
> configured plugin and skill digests from two independent consumer working directories after the
> provider checkout becomes unavailable.

## Context

ADR-74 makes common Mir skills user-scoped, namespaced plugins and rejects a same-name raw skill
under a user or project skill directory. That is sufficient for a clean bootstrap, but it does not
make a legacy host safe to migrate. Enabling a plugin is user-global: a plugin activated for one
repository is visible when another repository starts a new runtime session. Checking only the
repository that invokes `mir capability sync --apply` can therefore miss collisions in sibling
repositories that have not registered as consumers yet.

Local same-name skills also cannot be classified by a digest comparison alone. A local `design`
skill may be an obsolete common copy, a deliberate repository specialization, or a source-owned
implementation. Automatically deleting or replacing it would cross repository authority and could
silently change behavior.

## Decision

The first global provider activation on a host is gated by a complete inventory of every active
repository that the operator intends to open under that user account. The migration follows four
ordered phases:

1. **Inventory:** collect repository roots and report same-name skill slugs from `.claude/skills`
   and `.agents/skills`. This phase is read-only and treats slug presence—not content equality—as
   the collision signal.
2. **Disposition:** the repository owner assigns every collision one of `adopt_global`,
   `rename_local`, or `local_authority_exception`. `adopt_global` removes the raw copy only after a
   recoverable backup or commit exists. `rename_local` gives a specialization a repository-unique
   slug and updates its references. `local_authority_exception` keeps the repository outside the
   global consumer set until its overlap is resolved.
3. **Activation:** only when the inventory has zero unresolved collisions may one canary profile
   run `mir capability sync --apply`. A failed or incomplete inventory blocks activation for the
   whole user, not only for the current repository.
4. **Runtime proof:** restart Claude Code and start a new Codex session. From each runtime, the
   operator records a `mir capability attest` receipt containing the session ID exported by that
   runtime and the namespaced skills observed in its injected catalog. The manager rejects
   operator-supplied session IDs, but the observed skill names remain an operator attestation rather
   than a cryptographically authenticated runtime API. Codex evidence also requires a persistent user marketplace entry,
   enabled plugin entries, and hash-matching copies under `CODEX_HOME/plugins/cache`; a marketplace
   `source.path` is not an installed copy. Only then may `mir capability finalize --apply
   --after-restart` promote the consumer. Repeat registration per repository without installing
   another provider copy.

The capability manager remains fail-closed for the current repository. A fleet control plane or
operator-owned host ledger supplies the cross-repository inventory; Mir Yoke does not discover or
mutate arbitrary sibling repositories by itself. The operational sequence and rollback boundary
are defined in `docs/operations/global-plugin-migration.md`.

## Alternatives

- **Enable the provider and fix collisions as they appear:** rejected because a new session in an
  uninspected repository could load duplicate instructions before the collision is noticed.
- **Delete local skills whose files match the provider:** rejected because content equality does
  not establish ownership, intent, or future update authority.
- **Copy common skills into every repository:** rejected by ADR-74 because copies drift and lose
  one-version provenance.

## Consequences

Clean new repositories can bootstrap normally. Existing multi-repository hosts need a one-time
inventory and repository-local reconciliation before the first global activation. Hosts with an
unresolved local-authority repository cannot claim global plugin readiness; they may continue with
their existing local skills while the provider remains disabled. No migration command may delete,
rename, commit, or push repository content automatically.

## Acceptance criteria

1. The host inventory covers every active repository root and records a disposition for every
   same-name slug before first activation.
2. The activation gate fails while any disposition is unresolved or any selected skill surface is
   dirty.
3. A local specialization is preserved under a unique slug with its references updated.
4. After restart, both supported runtimes report one enabled provider instance whose installed-tree
   digest matches the project lock and have complete operator-observed namespaced-skill discovery
   receipts bound to new runtime-exported sessions.
5. Rollback disables the provider before any raw same-name skill is restored.
