# Contributing to mir-yoke

Thanks for the interest. This template's job is to stay small and copy-pasteable. Please keep that in mind when proposing changes.

## What we want

- **New deny-list patterns.** Anything you have seen an AI assistant accidentally do that you wish it could not have done. Add an entry to `.ai-harness/deny-list.yaml`. Include a real-world reason in the `reason:` field — patterns without context get pruned later.
- **New common skills.** Trigger-loaded Markdown bodies under
  `plugins/<provider>/skills/<name>/SKILL.md`. Each skill must be self-contained inside its plugin,
  have a clear responsibility, and list precise triggers. Project-only examples may use a uniquely
  named repository-local skill; do not duplicate a common plugin skill name.
- **Examples.** Real workflows under `examples/`. Show the prompt, the hook output, and the resulting tasks/tdd.json entry.
- **Hook tests.** Bash test harnesses under `tests/` (you can add this directory) that run the hooks against synthetic stdin payloads.
- **Documentation that explains *why*.** Every gate exists to prevent a specific failure mode. If you can name the failure mode in one sentence, the doc gets clearer.

## What we do not want

- **Universal-OS installer scope.** Automated greenfield bootstrap supports macOS, Linux, and WSL.
  Do not reintroduce native-Windows installation or ready-state claims without a new accepted
  product-boundary decision and corresponding safety evidence.
- **Project-specific runtime code.** This is a template, not a binary. Python modules, Rust crates, Node packages — all out of scope. If you want to ship code, fork and add it; don't push it back here.
- **Unlabeled CLI-specific features.** Runtime differences belong behind explicit capability gates.
  The plugin baseline supports Claude Code and Codex CLI/desktop; Codex IDE extensions are not part
  of the current plugin readiness claim.
- **Secret-bearing examples.** Even a fake-looking AWS key in a sample config is going to trip somebody's leak scanner. Use obviously-bogus literals like `EXAMPLE_KEY_DO_NOT_USE`.
- **Replacing markdown rules with prose-only docs.** The point of this template is that rules are executable. Adding rules without a hook to enforce them is the failure mode we are trying to avoid.

## Workflow

1. Fork the repo.
2. Branch from `main`. Use a descriptive name: `add-rust-deny-patterns`, `skill/refactor-helper`, `docs/why-tdd-matrix`.
3. Make your change. Run the existing hook tests if any are present.
4. Open a PR. Describe the failure mode you are guarding against (for deny-list / hook PRs) or the workflow you are documenting (for skill / example PRs).
5. Squash on merge. The history is meant to be readable end-to-end.

## Versioning

Tags are date-suffixed (`2026.05`, `2026.11`). The template aims for forward-compat; if you need to break a hook contract, bump the year in the version and document the migration in `CHANGELOG.md`.

## Code of conduct

Be direct. Be kind. Skip the LinkedIn voice.

## License

By contributing you agree that your contributions will be licensed under the MIT License (see LICENSE).
