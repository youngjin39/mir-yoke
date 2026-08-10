# Bluebrick: Composition

## Purpose

Compose the smallest selected Mir Yoke core and pack payload into one explicit repository without
overwriting repository-owned work.

## Public Interface

`yoke provider install`, `yoke plan`, `yoke apply`, `profiles/*.toml`, ignored
`.mir/local-state.json`, and ignored `.mir/yoke-receipts/`.

## Rules and Hazards

Profiles are advisory. Planning is read-only and classifies every target as create, identical, or
conflict. The target must be outside provider source. Apply verifies the plan digest, provider
content digest, source digests, and target preconditions before staging. A conflict is never
overwritten. The transaction writes only planned new files and tool-owned local receipt/state; on
failure it removes its creations and restores prior local bytes. Provider installations use
`providers/<content-digest>` and never a host-global active alias.

## Dependencies and Validation

Depends on Contract and Distribution catalog validation. Verify non-mutating plan, conflict
refusal, provider-change refusal, local receipt boundaries, rollback, safe paths, and simultaneous
multi-version provider installations.
