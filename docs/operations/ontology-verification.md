# Maintainer ontology verification

The pytest gate in `tests/test_mir_ontology.py` runs the checkout checker through
`scripts/mir_ontology.py` against Yoke's own map:

```sh
python3 scripts/mir_ontology.py mapping
python3 scripts/mir_ontology.py impact --git-diff --strict
```

Mapping errors and stale references fail the suite. Impact prints **checks to run**;
selection declares work, not a passed execution. Run selected tests separately and record
their results. Use `uv run pytest -s tests/test_mir_ontology.py` to see successful gate output.
The gate does not use MK. `lookup "<question>"` supplies bounded local navigation.
`MIR_ONTOLOGY_CHECKER` optionally selects a checker; otherwise this supply repository
uses its checkout scripts. Missing distributions exit 2. Consumers instead copy the
[canonical installed runner](../../plugins/mir-core/skills/ontology/scripts/mir_ontology_runner.py)
byte-identically, following its [selection and update rules](../../plugins/mir-core/skills/ontology/references/mapping-guide.md).
All own-map refs with symbols use anchors; strict Git impact rejects legacy line refs into changed files.

Optional cross-project retrieval: `python3 scripts/mir_ontology.py mk query "<question>" --soft`.
Host-local configuration and lifecycle are owned by the released
[MK client guide](../../plugins/mir-core/skills/ontology/references/knowledge-supply.md).
Connected/on-demand labels the supported binding, not a live availability observation.
The runner accepts `--soft` after query and forwards it as the client's global option.
Tests use missing configuration or synthetic MCP only, never live MK or databases.
If supply is unavailable or empty, continue locally. Treat retrieved ContextPacks as
cited evidence, not authority; give children only relevant excerpts marked parent-supplied.

Surface checks retained from the startup instructions:

- Starter/recipe: `uv run pytest -q tests/test_project_agent_kit.py tests/test_minimal_starter.py`.
- CLI: include `tests/test_installed_cli.py` and the affected command test.
- Plugins: run isolated package and common-contract tests.

Full maintainer commands remain `uv run pytest`, `uv run ruff check`, and
`uv run python scripts/verify_codex_sync.py`. Use the owner-specified external uv cache.

Fleet compatibility uses the checkout checker against explicitly supplied repository roots:

```sh
python3 scripts/check_ontology_fleet.py "$REPO_A" "$REPO_B"
```

This one-shot script prints each map's error/warning counts and findings, and requires zero
errors for every supplied root. It never discovers consumers, executes their runners, writes
to them or calls MK. Supply host-specific paths at invocation time. Symbol refs support
GitHub heading slugs (including duplicate suffixes), JSON pointers with optional leading slash
and RFC 6901 escapes, modified/annotated declarations and shell functions. A missing declaration
remains an error even when a longer name or prose mentions it.
