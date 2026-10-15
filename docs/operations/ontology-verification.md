# Maintainer ontology verification

The pytest gate in `tests/test_mir_ontology.py` runs the released checker through
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
uses its released checkout scripts. Missing distributions exit 2.

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
