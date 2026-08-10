# Agent-Guided Starter Adoption

The minimum path is a guidance checklist, not an executable installer. `starter/` is the only
required and default consumer payload. Optional `yoke` composition is a separate owner-invoked
path; it does not make advanced capability a prerequisite. Mir Yoke is not a universal installer.

## 1. Inspect before mutation

The active agent first records:

- the exact repository root and current Git status;
- existing `CLAUDE.md`, `AGENTS.md`, or other instruction files, including nested rules;
- project purpose, primary stack, implementation and content paths;
- generated files and their canonical sources;
- protected paths, credentials, external systems, and approval boundaries; and
- real build, test, lint, typecheck, or inspection commands.

If the repository already has a harness, treat it as repository-owned. Mir Yoke is comparison
material, not overwrite authority.

## 2. Choose the smallest adaptation

| Target state | Agent action |
|---|---|
| Empty repository | Place the four starter files at the root and fill every placeholder. |
| Existing local contract | Preserve it; merge only missing outcome, safety, or verification rules. |
| One runtime only | Keep only that runtime's entrypoint and the canonical `HARNESS.md`. |
| Equivalent native mechanism | Reference it instead of adding a duplicate Mir Yoke mechanism. |
| Unknown policy with material impact | Ask the owner before encoding it. |
| Optional feature without current need | Skip it. |

Do not recursively copy the full Mir Yoke checkout into the target. Do not replace existing root
instructions, `.gitignore`, CI, hooks, task state, or project configuration.

## 3. Fill the local contract

Adapt `starter/HARNESS.md` so it describes the target, not Mir Yoke:

1. state one project outcome and an observable completion rule;
2. name the local sources that reveal current state;
3. record protected and generated paths;
4. keep direct work valid for bounded tasks and scale ceremony with risk; and
5. list commands that actually run in the target repository.

Replace all `{{...}}` placeholders. If a category is genuinely absent, write `none` rather than
inventing a system.

## 4. Verify the result

The adoption is complete when:

- existing instructions and unrelated local changes are preserved;
- the local contract contains no Mir Yoke-specific identity or unresolved placeholder;
- every named path and command exists or is explicitly marked `none`;
- the target's smallest relevant verification passes; and
- the final diff contains only the selected harness files.

## 5. Optional composition

The starter does not require a memory database, plugin, hook, specification tree, sub-agent,
multi-agent routing, receipt, or Mir CLI. Add one only when a concrete problem justifies its cost.
The stable `safety` pack and preview `memory`, `collaboration`, and `assurance` packs expose those
choices without changing the core.

For an explicit target outside the Mir Yoke source checkout:

```bash
uv run yoke plan ../target --profile minimal --pack safety \
  --output /tmp/mir-yoke-plan.json --json
uv run yoke apply ../target --plan /tmp/mir-yoke-plan.json --json
```

Review every conflict in the plan. Apply will not resolve or overwrite it. On success the composed
files belong to the target; only `.mir/local-state.json` and `.mir/yoke-receipts/` remain local.

The retained pre-0.9 `setup.sh`, bootstrap, memory, plugin, executor, and slim paths remain available
for existing users and regression testing. They are not removed, but new projects should prefer
manual core adoption or distribution/composition so they do not inherit provider history.
