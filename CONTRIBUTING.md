# Contributing to Mir Yoke

Mir Yoke maintains a small Starter, one standard Project Agent Kit user journey, an optional
installed `mir` CLI, portable plugins, and retrievable reference evidence. Keep those boundaries
clear.

## Useful contributions

- **Starter or recipe evidence.** Add a concrete target scenario and the smallest contract test that
  catches a real adoption failure.
- **Optional CLI compatibility.** Preserve explicit target authority, installed isolation, and the
  public v0.8 command contract without making the CLI a Starter or Project Agent Kit dependency.
- **Portable common skills.** Author under `plugins/<provider>/skills/<name>/SKILL.md`. A common
  skill must load from its own package and cannot require Mir CLI or repository-local files.
- **Project-specific examples.** Use a repository-unique skill or agent slug; never shadow a common
  plugin provider.
- **Narrow safety patterns.** Document the exact destructive or credential-bearing shape being
  prevented and include a synthetic test.
- **Explanations with a failure mode.** State why a gate exists and how its evidence proves the
  affected behavior.

## Out of scope

- Provider-side target discovery, active `yoke` composers, rollout, or drift enforcement.
- Fixed project payloads, product code, or stack-specific application templates inside Mir Yoke.
- Secret-bearing examples or environment-specific credentials.
- Runtime claims that are not labeled with the exact evidence boundary.
- No-op verification that treats placeholders, missing tools, or skipped commands as passes.

## Workflow

1. Branch from `main` with a descriptive name.
2. Change canonical sources before generated derivatives.
3. Run the smallest affected test, generated parity, and broader checks required by the changed
   support boundary.
4. Release tags run repository validation and publish a GitHub Release; they do not claim an actual
   generated-repository runtime run. After release, the owner performs separate Claude and Codex
   acceptance. The retained `scripts/observe_project_agent_kit.py` and
   `scripts/verify_project_agent_kit_evidence.py` may collect and validate bounded, sanitized
   evidence for that owner acceptance, but the run is not a tag prerequisite.
5. Open a PR that names the guarded failure mode and remaining compatibility risk.

Mir Yoke follows Semantic Versioning. Breaking a Starter, recipe, plugin, or generated-surface
contract requires an explicit decision and migration note.

Contributions are licensed under the MIT License.
