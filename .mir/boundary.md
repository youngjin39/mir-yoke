# Boundary: Claude+Codex Harness Template

Allowed:
- harness engineering doc updates and phase doc additions
- template CLAUDE.md/AGENTS.md structural improvements
- .ai-harness/ rule updates when standards change
- session-start.sh template updates with local validation
- .mir-preserve.toml and repo-profile.toml placeholder maintenance
- code review and TDD for tools/, tests/
- architecture and design review for harness components

Blocked:
- adding project-specific implementation code (template stays generic)
- adding project-specific docs outside of harness reference material
- removing docs/harness-engineering/ content without replacing with newer material
- making family-specific profile values permanent (they must remain placeholder/example)
- discovering, scanning, or mutating another repository without a current user instruction naming
  that single target and scope
- fleet rollout, hash-conformance, direct deployment, or notification behavior
- modifying .ai-harness/ rules without a design phase
- deleting ADR files (supersede only)
- hook behavior changes without TDD ledger entry
