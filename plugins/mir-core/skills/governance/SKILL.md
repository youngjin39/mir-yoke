---
name: governance
description: "Fleet governance and instruction-doc ops (CLAUDE.md/AGENTS.md mgmt, fleet-wide governance review, project doctor, agent registry optimization).\n\nTrigger: CLAUDE.md, AGENTS.md, fleet governance, instruction doc, project doctor, registry optimization, fleet ops\n\nAbsorbs: fleet-instruction-doc-ops, fleet-governance-advisory, project-doctor, claude-agents-optimizer"
---

# Governance

## Use When
- When managing CLAUDE.md or AGENTS.md across the fleet.
- When running fleet-wide governance advisory reviews.
- When diagnosing project health or memory integrity.
- When optimizing the agent registry.
- When checking that terse-output wording stays source-of-truth-safe, review-safe, and limited to the intended rollout phase.

## Absorbed legacy skills
- fleet-instruction-doc-ops — Manage and optimize CLAUDE.md and AGENTS.md across the repository fleet.
- fleet-governance-advisory — Analyze fleet observation findings and produce advisory plans for bucket-3/4 check results.
- project-doctor — Project health check + memory integrity.
- claude-agents-optimizer — Agent registry optimization.

## Workflow
1. Locate the repository-local instruction source of truth and identify generated derivatives before proposing an edit.
2. Inventory ownership, protected paths, permission boundaries, required checks, agent roles, hooks, memory state, and cross-runtime parity.
3. During project-doctor work, compare the Profile identity with the repository payload. If a product Profile retains Mir Yoke provider or maintainer markers, run the repository-local consistency check when available and classify `R20 adopter_payload_boundary` as a blocking contract violation.
4. For R20 in a greenfield Phase 1 repository, stop product implementation and complete the documented Phase 2 finalize. Its copied external CLI and hash-bound slim transaction must quarantine only unchanged provider assets, verify the remaining tree, roll back on failure, and record ready last. Never delete the provider tree manually merely to clear the finding. Existing-repository adoption stays read-only or receipt-only and does not invoke slim.
5. Classify remaining findings as blocking contract violations, actionable drift, advisory improvements, or intentional local exceptions.
6. Change canonical sources first, regenerate derivatives with the repository command, and preserve project-specific policy that is narrower than fleet defaults.
7. Verify instruction size, generated-file parity, agent registry uniqueness, hook executability, memory integrity, and adopter payload boundaries with concrete evidence.
8. For fleet work, produce target-specific prompts and evidence; never treat central observation as authority to mutate another repository.
9. Keep output concise without weakening safety, review ownership, or verifier requirements.
