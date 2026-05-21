---
title: Bounded Codex review plane
pattern_kind: rollout_class
source_repository: <curriculum-workspace-source>
license: Apache-2.0
created: 2026-05-20
adoption_targets:
  archetypes: [learning_low_code, template_transitional]
  management_modes: [upstream-managed, bounded-managed]
notes: Codex narrowed to review/docs-structure; harness migration skipped.
---

<!-- generated:start -->

## Why this pattern

Some repositories are content / curriculum workspaces, not application
code bases. The protected runtime is curriculum continuity and source
authority — not a build pipeline. Letting Codex run a full execution
plane would let it rewrite curriculum material under the guise of
"fixing tests."

This pattern narrows Codex to **review-style work only** and freezes
the harness migration class so the standard rollout overlay never
applies on top.

## What lands in `.mir/repo-profile.toml`

```toml
repository_type   = "learning_workspace"
rollout_class     = "skip_migrate_codex_active"
overlay_archetype = "learning_low_code"

[ownership]
codex_role             = "bounded_review_plane"
codex_default_enabled  = true
allow_role_override    = true
override_requires_record = true
```

`rollout_class = "skip_migrate_codex_active"` means "do not migrate
this repo's harness, but Codex is still allowed in." `codex_role =
"bounded_review_plane"` is the contractual lock that downstream review
tools honor.

## What lands in `.mir/boundary.md`

```
Allowed:
- learning workflow maintenance
- wiki/source structure review
- generic harness alignment
- bounded Codex review/docs-structure work

Blocked:
- pretending this is a normal code app
- enabling code-only hooks before real code paths exist
- applying app-product, code-first, or infra-runtime migration overlays
```

## When to adopt

Adopt this pattern when **all** of the following hold:
- The repository's protected runtime is curriculum / docs / narrative
  — not code.
- A "fix the tests" prompt could rewrite curriculum material rather
  than test scaffolding.
- The repository already has a peer-review or editorial pipeline that
  supersedes Codex test authorship.

Do **not** adopt when the repository ships code (app, service, etc.) —
use the `app-product-*` pattern family or a similar production-grade
pattern instead.

## Transplant adaptation

1. Replace the boundary `Notes:` content with the recipient's own
   protected-runtime statement.
2. Verify the recipient's `overlay_archetype` is in this pattern's
   `adoption_targets.archetypes` list; if not, treat the pattern as
   inspiration only and open a fresh decision record.
3. After adoption, the rollout-class settled check should not fire as
   long as the recipient stays in `skip_migrate_codex_active`. A check
   that does fire is a signal to either complete the migration or
   re-classify.

<!-- generated:end -->
