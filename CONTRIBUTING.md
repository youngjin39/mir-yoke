# Contributing to mir-yoke

Thanks for the interest. Mir Yoke keeps its required core small while preserving higher-assurance
capabilities behind explicit pack boundaries. Contributions must keep those two concerns distinct.

## What we want

- **Core contract improvements.** Keep `starter/` to its four Markdown files and preserve its
  runtime-independent, agent-guided adoption path.
- **Capability pack improvements.** Update `packs/<id>/pack.json`, its payload, declared retained
  source, support level, compatibility, and focused verification together.
- **New deny-list patterns.** Add evidence-backed patterns to `.ai-harness/deny-list.yaml` and keep
  runtime-neutral consumer checks in the safety-pack payload.
- **New common skills.** Trigger-loaded Markdown bodies under
  `plugins/<provider>/skills/<name>/SKILL.md`. Each skill must be self-contained inside its plugin,
  have a clear responsibility, and list precise triggers. Project-only examples may use a uniquely
  named repository-local skill; do not duplicate a common plugin skill name.
- **Examples.** Real workflows under `examples/`. Show the prompt, the hook output, and the resulting tasks/tdd.json entry.
- **Hook and composer tests.** Test synthetic tool payloads, target conflicts, transaction rollback,
  and provider digest changes under `tests/`.
- **Documentation that explains *why*.** Every gate exists to prevent a specific failure mode. If you can name the failure mode in one sentence, the doc gets clearer.

## What we do not want

- **Universal mandatory installation.** The core must not require a CLI, plugin, hook, memory,
  specification lattice, restart, or operating-system-specific bootstrap.
- **Unclassified runtime code.** Runtime code belongs to a declared optional pack or a documented
  maintainer-only surface with focused tests; it never silently expands the core.
- **Unlabeled CLI-specific features.** Runtime differences belong behind explicit capability gates.
  The plugin baseline supports Claude Code and Codex CLI/desktop; Codex IDE extensions are not part
  of the current plugin readiness claim.
- **Secret-bearing examples.** Even a fake-looking AWS key in a sample config is going to trip somebody's leak scanner. Use obviously-bogus literals like `EXAMPLE_KEY_DO_NOT_USE`.
- **Destructive legacy cleanup.** Existing bootstrap, memory, executor, plugin, hook, and spec paths
  are preserved until an explicit migration and deprecation decision authorizes removal.
- **Provider authority.** Do not add target discovery, background rollout, Git mutation, or external
  release actions to local composition.

## Workflow

1. Fork the repo.
2. Branch from `main`. Use a descriptive name: `add-rust-deny-patterns`, `skill/refactor-helper`, `docs/why-tdd-matrix`.
3. Make your change. Run the smallest core, pack, distribution, or preserved-platform tests that can
   fail for the affected behavior.
4. Open a PR. Describe the failure mode you are guarding against (for deny-list / hook PRs) or the workflow you are documenting (for skill / example PRs).
5. Squash on merge. The history is meant to be readable end-to-end.

## Versioning

The repository uses Semantic Versioning. Keep `VERSION`, `pyproject.toml`, plugin manifests,
`CHANGELOG.md`, deterministic artifact names, and the release tag aligned. A release candidate must
pass clean-candidate readiness before a tag or GitHub Release is created.

## Code of conduct

Be direct. Be kind. Skip the LinkedIn voice.

## License

By contributing you agree that your contributions will be licensed under the MIT License (see LICENSE).
