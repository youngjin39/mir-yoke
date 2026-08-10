---
title: Public Harness Decision Index
status: accepted
updated: 2026-08-10
---

# Public Harness Decision Index

Mir Yoke is a public template and reference repository. It has no provider runtime and no standing
authority over consumer repositories. It is an agent-guided baseline, not a universal installer.
`starter/` is the only supported consumer payload and does not require advanced automation.

## Current Authority

1. [ADR-81](adr-81-minimal-starter-support-boundary.md) defines `starter/` as the only supported
   consumer payload and removes automation, plugins, hooks, memory, specs, and delegation from the
   readiness contract.
2. [ADR-78](adr-78-public-template-identity-and-non-authority.md) defines the public-template
   identity and repository-local authority boundary.
3. [ADR-73](adr-73-proportional-guidance-first-harness.md) defines proportional local work,
   delegation, review, and verification.

The [role policy](role-policy.md) is optional advanced reference material. It is not part of the
four-file starter; a consumer owns any locally adopted role or delegation policy.

ADR-74 through ADR-77, ADR-79, and ADR-80 describe retained advanced or superseded bootstrap
mechanics. ADR-81 removes them from the supported consumer contract; their code and prose remain
reference or maintainer material only.

## Historical Decisions

Central rollout, back-propagation, direct-apply, fleet catalog, template parity, watchdog, and
deployment decisions are non-authoritative history. Start at
[`docs/history/centralization`](../history/centralization/README.md); the original ADR files remain
here so links and Git history stay intact.
