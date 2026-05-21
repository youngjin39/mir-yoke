---
title: Flutter app product harness
pattern_kind: archetype
source_repository: <flutter-app-product-source>
license: Apache-2.0
created: 2026-05-20
adoption_targets:
  archetypes: [app_product_flutter]
  management_modes: [upstream-managed]
notes: Full Codex execution authority across documented Flutter boundaries.
---

<!-- generated:start -->

## Why this pattern

For repositories that are real Flutter app products with established
structure (`lib/`, `test/`, `integration_test/`, `scripts/`, Firebase
config), the bounded-review posture is too narrow — Codex needs full
execution authority to run TDD cycles, integration tests, and
platform-specific glue.

## What lands in `.mir/repo-profile.toml`

```toml
repository_type   = "code_app"
rollout_class     = "migrate"
overlay_archetype = "app_product_flutter"

[ownership]
codex_role             = "execution_plane"
codex_default_enabled  = true
allow_role_override    = true
override_requires_record = true

[paths]
code_paths       = ["lib/**", "test/**", "integration_test/**", "scripts/**"]
non_code_paths   = [".claude/docs/**", "commands/**"]
protected_paths  = ["firestore.rules", ".claude/agent-memory/**"]
generated_paths  = ["**/*.g.dart", "**/*.freezed.dart"]
```

`rollout_class = "migrate"` opens the full harness migration.
`codex_role = "execution_plane"` removes any bounded-review lock.
`code_paths` includes `integration_test/**` and `scripts/**` so Codex
can author both Flutter integration tests and platform scripts.

## What lands in `.mir/boundary.md`

```
Allowed:
- implementation
- review
- verification
- localized app, game, test, and tooling fixes inside the documented boundaries

Blocked:
- repo rewrite
- command-system replacement
- per-agent memory rewrite
- runtime policy takeover
```

## When to adopt

Adopt this pattern when **all** of the following hold:
- The repository is a Flutter (or analogous app-platform) product
  with established directory shape.
- Codex full execution authority will not let it touch the platform
  policy surface (Firebase rules, agent-memory state).
- TDD authorship inside `lib/` and `integration_test/` is welcome.

Do **not** adopt when:
- The repository is curriculum / narrative — see `bounded-review-plane.md`.
- The repository does not yet have a stable `lib/` + `test/` shape —
  wait for the structure to settle first.

## Transplant adaptation

1. Replace the boundary "runtime policy takeover" entry with the
   recipient's actual platform policy surface (e.g., for an Apple
   Game Center title: `GameCenter ranking-policy takeover`).
2. Verify `code_paths` includes every directory Codex needs to author
   — omitting `scripts/` is a common mistake.
3. Verify `generated_paths` lists the recipient's actual codegen
   extensions so the harness does not complain about generator output
   drift.

<!-- generated:end -->
