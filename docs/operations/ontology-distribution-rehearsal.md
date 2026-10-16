# Isolated ontology distribution rehearsal interface

The caller owns compatibility preflight, explicit apply decisions, map snapshots and map rollback.
`CapabilityManager` owns package validation, digest binding, explicit consumer updates and local
apply-failure rollback. Package installation alone does not validate domain semantics or establish
fresh-session discovery. No live updater or local-file transport is added to the production CLI.

Use only temporary supplier, provider, consumer, user and runtime homes. Set `TMPDIR` to the
fixture scratch directory before Python starts. Never pass the live provider or account homes.
The supplier copies only the manager's declared export paths, not repository databases or secrets.

The existing Python interface is:

```python
manager = CapabilityManager(
    consumer_root,
    capability_home=fixture_provider,
    user_home=fixture_user,
    codex_home=fixture_codex,
    git=fixture_transport,
    command_runner=fixture_runtime_runner,
    which=fixture_which,
)
manager.sync(profile, apply=True)       # establish the fixture baseline
preview = manager.update(profile)      # dry run; inspect ready_to_apply
result = manager.update(profile, apply=True)
```

`fixture_transport.resolve(url, ref)` returns a full 40-character revision id.
`export(url, ref, commit, paths, destination)` copies **that revision's** declared paths to the
new destination. Keep immutable baseline and candidate trees keyed by revision; switching the
selected revision must not change exports of an earlier commit. Keep configured HTTPS source
identity intact: injection replaces transport, not source policy. Stub runtime commands and
executable discovery so no installed runtime, Git fetch or network is used.

The supplier's `plugins/mir-core/skills/ontology/references/common-contract.json` is packaged as
part of `mir-core`. Inspect `plugins.mir-core.sha256` in each consumer's capability lock and the
provider receipt against the actual materialized package. An advancing consumer leaves peers'
local integrations pending; each peer must explicitly call `update(..., apply=True)` to catch up.
Reverse the supplier revision and explicitly update each consumer to restore package bytes/digests.
Restore each caller-owned map snapshot separately, then revalidate against the restored contract.
Lock timestamps and binding receipts may change on a successful reverse update; assert restored
source revision, package bytes/digests and exact map bytes rather than old timestamp equality.

Before any candidate apply, run the candidate checker with the candidate `--contract` against
**both** temporary consumers: `impact --paths <declared-source> --strict --json`. Reject nonzero
exit or `ok=false`. After apply and rollback, run `mapping` against the materialized contract.
Retain command/operation, consumer, exit/result and digest receipts. An apply exception reporting
`local rollback was incomplete` must fail the rehearsal, even if package bytes were restored.
Check peer locks/maps and unrelated files around each local operation.

Executable examples live in
`tests/test_capability_security.py#test_should_rehearse_ontology_distribution_and_rollback_in_fixtures`:

```sh
uv run pytest -q -s tests/test_capability_security.py -k rehearse_ontology \
  --deselect tests/test_harness_consistency.py
```

The three scenarios cover compatible distribution and reverse update across distinct profiles,
rejected semantic compatibility before apply, and an injected incomplete derivative rollback.
The caller's separate orchestration script should use this interface; this test is supplier-side
fixture evidence, not a release, consumer delivery or live updater receipt.
