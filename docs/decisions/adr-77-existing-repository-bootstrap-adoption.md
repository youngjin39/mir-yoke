---
title: Preservation-First Existing-Repository Bootstrap Adoption
status: accepted
date: 2026-08-07
---

# ADR-77 — Preservation-First Existing-Repository Bootstrap Adoption

## Context

ADR-74 defines a greenfield coordinator that may create missing profiles, memory configuration,
content onboarding, and specification files. Applying those creation semantics to a mature
repository can overwrite local policy, rename established archive slugs, or force an existing
specification system into Mir Yoke's starter file shapes. Mature repositories still need honest
evidence for the same seven bootstrap and Phase 2 controls.

## Decision

mir bootstrap-adoption is the existing-repository path. It reads the tracked
config/bootstrap-adoption.json manifest and checks without writing by default. The --apply form
writes only the ignored, machine-local .mir/bootstrap-receipt.json, atomically and only after every
check passes. It never installs or patches hooks, profiles, archives, memory, or specifications.
The greenfield mir bootstrap contract is unchanged.

The manifest binds the repository slug and overlay archetype to .mir/repo-profile.toml, maps
[repo].repository_type and [repo].overlay_archetype to an adoption profile, and records the exact
40-hex Mir Yoke source commit. [execution].non_code_profile is not repository identity and is
intentionally ignored. The repository type governs when type and overlay describe different
dimensions; for example, content_workspace with a hybrid_pipeline overlay remains a content
workspace.

All seven surfaces are explicit. applied means the Mir control is present, repository_owned means
native repository machinery satisfies it, not_applicable is limited to content onboarding for
non-content repositories, and exception is a visible, evidence-backed deviation. An exception
requires a concrete reason, blockers, and existing evidence. It may still produce a ready receipt
so a mature repository is not frozen by the startup gate; the exception is copied into the receipt
and is never silently treated as implementation.

For applied or repository-owned controls, the command proves the startup gate and runtime wiring,
the managed venv/uv Python launcher, live content classifications, and read-only SQLite FTS hits
against existing archive slugs and relative paths. It does not rebuild or modify the database.
Phase 2 accepts native spec evidence: every one of four layers has a positive total, nonnegative
counts sum to that total, and has no TBD items; AI-ready has at least one ready item and no
incomplete or blocked items; open gaps are zero; and all five full-review dimensions pass.
AI-ready counts are deliberately not equated to Layer 1 totals. Applied and repository-owned Phase
2 entries must map their native YAML metadata, gaps, and review files through `native_evidence`.
The command parses those files and requires the manifest coverage, AI-ready, gap count, and review
claims to match them exactly.

The receipt records a SHA-256 digest for the manifest and for the complete set of evidence paths
declared by all surfaces. At every SessionStart or mutation check, the gate compares the source
commit, manifest digest, exact evidence path set, and live evidence digests. A missing, added,
changed, duplicated, absolute, or parent-traversing evidence entry invalidates readiness. The
blocked shell path recognizes complete command forms rather than substring matches and rejects
compound commands, redirection, command substitution, mutating inspection flags, and commands
wrapped around an allowed token.

## Consequences

The portable manifest and evidence remain repository-owned and should be committed. The receipt
remains local and ignored. Repositories must install or repair their own hooks before declaring
them applied or repository-owned. Exceptions preserve operational continuity but remain auditable
technical debt in every regenerated receipt.

## Acceptance criteria

1. A dry run never creates or replaces the receipt and opens memory in SQLite read-only mode.
2. A failed apply preserves any prior receipt byte-for-byte.
3. A passing apply writes a schema-versioned ready receipt bound to the source commit, manifest
   hash, exact declared evidence path set, and live evidence hashes, including query results, all
   dispositions, and Phase 2 exceptions.
4. Existing archive slugs, relative paths, profile policy, and native spec shapes are not mutated.
5. The startup gate routes repositories with the adoption manifest to this command and permits
   only the tracked manifest, content onboarding, spec, and declared evidence edits while blocked;
   its shell allowlist accepts only complete single-command grammar.
6. Applied or repository-owned Phase 2 claims equal the parsed native coverage, AI-ready, gaps,
   and review evidence rather than trusting duplicated manifest counts.
