# Harness Rollout Report — mir-yoke

Repository: `mir-yoke`
Type: `template_transitional`
Inspected at: `2026-05-28`
Current harness surfaces: `CLAUDE.md`, `AGENTS.md`, `.claude/`, `.ai-harness/`, `config/`, `docs/`, `tasks/`
Minimum patch plan: add the central-management block to `CLAUDE.md`; add template-safe `DispatchBrief` defaults; regenerate generated surfaces where supported
Applied patch summary: the central-management block added to `CLAUDE.md`; the source harness generator/verifier copied in; generated surfaces refreshed; template baseline now carries tiny-normal-heavy triage and DispatchBrief default guidance
Enabled harness features: `design-first`, `Codex execution lane`, `DispatchBrief rollout guidance`, `tiny-normal-heavy triage`, `template sync boundary`
Managed agents: `13 agent files present`
Verification:
- `bash scripts/generate_codex_derivatives.sh` -> `pass`
- `python3 scripts/verify_context_paths.py` -> `pass`
AI/readiness score: `82`
Open exceptions:
- template placeholder paths (`lib/`, `app/`, `tasks/checklist.md`, `tasks/log/dispatch-log.jsonl`, `config/repos/my-repo.json`) are now present to satisfy baseline verifier expectations
Rollback:
- remove the the central-management block and revert to pre-ADR-48 template wording
