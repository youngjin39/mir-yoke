---
title: Content workspace harness
pattern_kind: archetype
source_repository: <content-workspace-source>
license: Apache-2.0
created: 2026-05-20
adoption_targets:
  archetypes: [content_workspace, hybrid_pipeline]
  management_modes: [upstream-managed, bounded-managed]
notes: Narrative / content authoring repository; Codex active but narrowed.
---

<!-- generated:start -->

## Why this pattern

Some repositories produce narrative or scored content rather than
code — essays, scripts, scores, prompts. A `hybrid_pipeline`
classification is too generous in practice: Codex would treat content
drafts as code and try to "refactor" them.

This pattern names the repository as a `content_workspace`, keeps
the rollout in `skip_migrate_codex_active`, and ignores the local
virtual environment directory.

## What lands in `.mir/repo-profile.toml`

```toml
repository_type   = "content_workspace"
rollout_class     = "skip_migrate_codex_active"
overlay_archetype = "hybrid_pipeline"
```

`repository_type = "content_workspace"` is the lock — the harness
compiler keeps Codex from treating drafts as code. `rollout_class
= "skip_migrate_codex_active"` matches the bounded-review-plane
stance but for content rather than curriculum.

## What lands in `.gitignore`

```
.venv/
```

Add the Python virtual environment glob if the workspace mixes
content with local Python tooling (notebooks, generators). Keep the
rest of `.gitignore` untouched.

## When to adopt

Adopt this pattern when:
- The repository's primary output is narrative / score / prompt /
  lyric, not shippable software.
- A "fix" prompt could damage author intent if Codex were granted
  full authorship.
- The repository still wants Codex available for narrowly-defined
  review tasks (grammar pass, fact-checking, prompt linting).

Do **not** adopt when:
- The repository is a code app — use `app-product-flutter.md` (or
  its language-specific successor).
- The repository is teaching material — use
  `bounded-review-plane.md` instead; the curriculum protection
  clause is stronger.

## Transplant adaptation

1. Confirm the recipient repository's primary artifact is content
   (not code). The classification needs to match practice, not
   aspiration.
2. If the repository has author-owned drafts that must never be
   auto-edited, add an explicit `protected_paths` entry in
   `.mir/repo-profile.toml` (mirroring the `app-product-flutter.md`
   policy-surface pattern).
3. Validate via fleet refresh that the rollout-class settled check
   does not fire — the `skip_migrate_codex_active` value is
   intentional and should be permanent until the repository's
   nature changes.

<!-- generated:end -->
