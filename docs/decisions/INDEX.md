---
title: Public Harness Decision Index
status: accepted
updated: 2026-08-10
---

# Public Harness Decision Index

Mir Yoke is a public template and reference repository. It has no provider runtime and no standing
authority over consumer repositories. It is an agent-guided baseline, not a universal installer.
`starter/` is the only required and default consumer payload and does not require advanced
automation. Declared capability packs are optional and carry their own support level.

## Current Authority

1. [ADR-82](adr-82-product-planes-capability-packs-and-composition.md) defines the four product
   planes, optional capability packs, advisory profiles, deterministic distribution, and
   preservation-first composition while retaining the existing platform.
2. [ADR-81](adr-81-minimal-starter-support-boundary.md) defines `starter/` as the only required
   default payload and removes advanced automation from the minimum readiness contract.
3. [ADR-78](adr-78-public-template-identity-and-non-authority.md) defines the public-template
   identity and repository-local authority boundary.
4. [ADR-73](adr-73-proportional-guidance-first-harness.md) defines proportional local work,
   delegation, review, and verification.

The [role policy](role-policy.md) is optional advanced reference material. It is not part of the
four-file starter; a consumer owns any locally adopted role or delegation policy.

ADR-74 through ADR-77, ADR-79, and ADR-80 describe retained advanced bootstrap mechanics. ADR-81
removes them from the minimum contract; ADR-82 maps their implementation into explicit optional
packs without making the old full bootstrap path a default.

## Historical Decisions

Central rollout, back-propagation, direct-apply, fleet catalog, template parity, watchdog, and
deployment decisions are non-authoritative history. Start at
[`docs/history/centralization`](../history/centralization/README.md); the original ADR files remain
here so links and Git history stay intact.
