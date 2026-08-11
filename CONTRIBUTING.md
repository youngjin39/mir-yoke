# Contributing to Mir Yoke

Mir Yoke maintains a small Starter, one explicit Project Agent Kit user journey, portable plugins,
and retrievable reference evidence. Keep those boundaries clear.

## Useful contributions

- **Starter or recipe evidence.** Add a concrete target scenario and the smallest contract test that
  catches a real adoption failure.
- **Portable common skills.** Author under `plugins/<provider>/skills/<name>/SKILL.md`. A common
  skill must load from its own package and cannot require Mir CLI or repository-local files.
- **Project-specific examples.** Use a repository-unique skill or agent slug; never shadow a common
  plugin provider.
- **Narrow safety patterns.** Document the exact destructive or credential-bearing shape being
  prevented and include a synthetic test.
- **Explanations with a failure mode.** State why a gate exists and how its evidence proves the
  affected behavior.

## Out of scope

- Provider-side target discovery, installers, composers, receipts, rollout, or drift enforcement.
- Fixed project payloads, product code, or stack-specific application templates inside Mir Yoke.
- Secret-bearing examples or environment-specific credentials.
- Runtime claims that are not labeled and tested for both Claude and Codex.
- No-op verification that treats placeholders, missing tools, or skipped commands as passes.

## Workflow

1. Branch from `main` with a descriptive name.
2. Change canonical sources before generated derivatives.
3. Run the smallest affected test, generated parity, and broader checks required by the changed
   support boundary.
4. For a one-prompt reproducibility claim, use `scripts/observe_project_agent_kit.py prepare` before
   each separate Claude and Codex clean-room run, then use its `collect` command to write the bounded
   evidence under `release-evidence/project-agent-kit/<version>/`. The observer recomputes the target
   Git state and real checks, and redacts private paths and credential-like values from the public
   transcript. Run `uv run python scripts/verify_project_agent_kit_evidence.py`; a release tag fails
   without both valid runtime records.
5. Open a PR that names the guarded failure mode and remaining compatibility risk.

Mir Yoke follows Semantic Versioning. Breaking a Starter, recipe, plugin, or generated-surface
contract requires an explicit decision and migration note.

Contributions are licensed under the MIT License.
