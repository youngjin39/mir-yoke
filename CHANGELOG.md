# Changelog

All notable changes to `mir-yoke` will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html) from `v0.1.0` onward.

Pre-`v0.1.0` entries (below) used date-format headings (`## 2026.05.x`) and are kept for historical reference. All future entries use the `## [vN.M.X] — YYYY-MM-DD — title` format.

## [Unreleased]

## [v0.13.28] — 2026-10-24 — Guidance capability gap fills

### Added

- Seven optional references extend existing design, bluebricks, code-review,
  automation and verify skills, preserving their existing text.
- Design-tree frontier interviews and text-only fallback briefs; explicit installed
  dependency and readable adapter rungs with safeguards; requested repository audit
  and manual shortcut debt guidance; report-only SPINNING; optional three-document
  fidelity audit; and an advisory consensus panel for disputed high-impact reviews.
- Fresh methodology text credits mattpocock/skills 5beb35b (MIT),
  DietrichGebert/ponytail 09c434a (MIT), fn-opt/dryforge f5aa6d7 (Apache-2.0)
  and ADR-58 items 1, 4 and 5b. No upstream code is included or executed.
- Focused reference, provenance and pointer tests. No new scripts, hooks, commands,
  agents, universal document requirement or model-judged acceptance gate.


## [v0.13.27] — 2026-10-24 — Common writing skills

### Added

- Add `mir-content:no-ai-slop` from petergyang/no-ai-slop at 000650b (MIT),
  preserving edit/detect behaviour and the upstream eval under references.
- Add `mir-content:fluent-korean` from the approved snflkd policy at ce8683f
  (MIT), retaining every Korean-output rule and the attribution notice.
- Register both skills for Claude Code and Codex through the shared plugin tree;
  existing profile packs and global policies remain unchanged.

- Second slice: add optional controlled-experiment, instruction-change evaluation
  and trace-derived skill-patch references to testing, efficiency and governance.
- Add owner-requested `mir-core:memory-evaluation` with evidence, privacy and
  accuracy/latency comparisons. All five borrows are fresh methodology text only;
  no runtime, autonomous adoption or model-judged hard gate is introduced.

## [v0.13.26] — 2026-10-23 — Behaviour scenarios

### Changed

- Add changed-flow behaviour scenarios to the portable default work method and
  its existing request matrix, preserving proportional guidance without a new gate.
- Map scenarios to executed production and platform checks in testing; review
  missing or invalid rows, producer mocks, concrete defects and state/async fixes.
- Add a short scenario reminder to both identical SessionStart message sources.

## [v0.13.25] — 2026-10-23 — Interpreter tools under command bans

### Fixed

- Count and deny direct code interpreters and static nested shell/interpreter
  calls in code-mode exec during command-forbidden handoff turns. Preserve
  read-only tool discovery, non-interpreter calls and command-permitted turns.
- Name interpreters in command-ban guidance while preserving the separate,
  unchanged file-only prohibition sentence from 0.13.23.
- Require forbidden execution to be disclosed as a compliance failure at Stop,
  including the bounded second repair. Interpreter reads cannot justify verified
  paths/pins; do not demand a false no-reader statement after such execution.

## [v0.13.24] — 2026-10-23 — Round-j handoff checker defects

### Fixed

- Accept parenthetical bilingual qualified-target labels in recipient detection,
  author target checks and namespace checks; retain individual base-pin accounting.
- Include qualified-target namespace mismatches in the bounded second/final repair,
  including mismatches first exposed after repairing the target label.
- Accept recipient pin labels in Markdown table cells. Exclude version strings,
  qualified IDs and structured pin keys from verified-path scanning, and keep reason
  prose and summary sha256/revision headers out of pin-label requirements.

## [v0.13.23] — 2026-10-23 — File-only bans no longer read as command bans

### Fixed

- 0.13.22 supplied one sentence naming shell and file-writing tools whenever the owner forbade
  commands or file changes. Round j P3 agents at three command-permitted targets (owner forbids
  file changes only) read it as a shell ban, ran no pins runner and could not pin cited sources.
  The supply now names shell tools only under a command ban and file-writing tools only under a
  file-change ban.

## [v0.13.22] — 2026-10-23 — Round-i handoff checker defects (prepared source)

### Fixed

- Extract quoted English/Korean prose exclusions and unquoted uppercase identifiers
  with explicit do-not-forward/include wording, retaining explicit Exclude sections,
  allowed identifiers and redacted whole-artifact diagnostics.
- Account for Codex code-mode exec calls and static nested shell commands;
  preserve owner scope and tools across native HookPrompt retries, deduplicating
  feedback by hook run ID within the existing two-block bound.
- Ignore quoted/fenced command examples when deciding owner command bans while
  retaining unlabelled English owner prohibitions.
- Reject qualified-target namespaces that differ from the local map unless a
  reviewed alias is declared; read only and fail open on map errors.
- Supply forbidden-tool attempt guidance and deny file-writing tools on
  handoff turns with unqualified file-change bans. Scoped file prohibitions
  preserve legitimate edits. Existing PreToolUse registration suffices.
- Leave versions, handler SHA admission, tree digests, payloads, locks and generated
  derivatives to Main's release chain. Offline fixtures establish no activation.

## [v0.13.21] — 2026-10-23 — Complete handoff repairs (prepared source)

### Fixed

- End every Stop repair reason with an explicit instruction to resend the
  complete corrected final artifact; supply the same rule once on prompt submit.
  This changes instructions only, without heuristics for partial answers.
- Accept this-turn HEAD-file Reads and repository-local Read/Grep/Glob references
  for HEAD/root pins when commands are forbidden, including recipient accounting.
  Reject unrelated outside-root reads and retain contract-file reference checks
  and computation requirements when commands are permitted.
- Leave versions, handler SHA admission, tree digests, payloads, locks and generated
  derivatives unchanged for Main's release chain. Offline tests do not prove activation.

## [v0.13.20] — 2026-10-22 — Residual handoff checks (prepared source)

### Fixed

- Check excluded content, extra grants, unsupported verified pin/path claims and
  abbreviated full-value hex pins without a runner when commands are forbidden;
  translated field headings do not create missing-English-label defects.
- Supply recipient accounting for qualified English/Korean packets without pins;
  require all eight base labels and every named pin, computing evidence for
  verified digests/revisions/HEAD, and a limitation when no local tool was used.
- Permit a second deterministic repair block only with exactly one prior native
  handler block in the current turn; never block a third time. Preserve supplied
  pins headers literally, including when fresh observation times differ.
- Preserve Python 3.9 support and optional `tomllib`. Version and integrity
  metadata remain unchanged pending Main's release chain.

## [v0.13.19] — 2026-10-22 — Handoff hooks run on Python 3.9

- `handoff_packet.py` imported `tomllib` (Python 3.11+) unconditionally. Claude runs plugin hooks with the first
  `python3` on PATH, which is macOS `/usr/bin/python3` 3.9 on the Mir host, so every 0.13.18 UserPromptSubmit,
  PreToolUse and Stop call crashed at import and failed open (observed in all seven Claude round-h captures). The
  import is now optional; without it the profile protected-path filter is skipped and every other check runs.
- Regression test blocks `tomllib` and runs all three events; the handoff suite also passes with the handler on
  `/usr/bin/python3` (67 failures before the fix).

## [v0.13.18] — 2026-10-22 — Handoff owner boundaries and recipient accounting

### Fixed

- Recognize Korean no-command constructions for both supply and Stop runners; omit denied,
  not-read and profile-protected/secret paths from cited-source harvesting.
- Avoid prohibition-scope and negative-subordinate-clause false positives. Accept equivalent
  colon/bullet labels, same-line evidence/time, optional field/pin prefixes and normalized
  restrictions; keep read-only and explicitly future-authorized wording out of extra grants.

### Added

- One-shot recipient pin-label and this-turn tool-reference checks, with explicit reader
  limitations when commands are forbidden, and one-sentence prompt-submit guidance.
- Shared stateless PreToolUse shell denial for owner no-command handoff turns, admitted by
  ADR-90 amendment 2026-10-22b. Offline tests cover native transcript shapes and deny output;
  Main still owns release metadata, handler/digest admission and live-runtime verification.

## [v0.13.17] — 2026-10-22 — Handoff Stop check asks for each cited source pin

### Changed

- In round f, five packets cited code and test files without their digests because the owner
  prompts named no `Sources:` and the supplied pin block therefore had no source entries. Stop now
  runs the repository runner once more for the existing repository files a packet cites beyond
  the supplied sources (protected, excluded, symlinked, map and runner paths skipped; at most 32)
  and blocks once, naming each file whose sha256 or last-change revision is absent. Supply asks
  for these pins up front. Both runner calls share the 8-second hook budget; a late second call
  fails open with the usual warning.

## [v0.13.16] — 2026-10-22 — Handoff Stop check reads the native final message

### Fixed

- In round f, 5 of 10 Claude runs ended without the Stop check: the transcript did not yet hold
  the turn's final message, so the handler saw an earlier progress note and treated the turn as
  having no packet. Stop now checks the native payload's `last_assistant_message` when it is
  present and nonempty, and falls back to the transcript tail otherwise.

## [v0.13.15] — 2026-10-22 — Handoff Stop check recognizes translated packets

### Fixed

- The Stop check skipped a packet whose labels were translated (round f, quietleaf: Korean
  headings, pins re-fenced without the `handoff pins:` marker, enlarged authority). A packet is
  now also recognized by forwarded pin keys (`pin_inventory`, `mapping_sha256`) or a handoff
  heading line, so such packets get the one-shot repair. Plain replies stay untouched.

## [v0.13.14] — 2026-10-22 — Mechanical handoff packet preparation

### Added

- Prepared deterministic, offline UserPromptSubmit pin/owner-boundary supply and
  one-shot Stop packet checks for Claude/Codex native hook payloads, with fail-open
  warnings, stateless transcript-tail recomputation and per-field/per-pin self-checks.
- Registered both events in the common hook definition and amended ADR-90/schema-4
  exact handler admission. Documented detection, English/Korean authority checks,
  read/inspect defaults, exclusions, prompt hashes, budgets and runtime limits.
- Main review: Korean detection also covers instruction-text (jisimun/ingyemun) requests and
  the object-first "pass to another agent" form; prose prohibitions are copied per sentence and
  cover the -ji mal forms. Checked against the ten round-e P3 owner texts (10/10 detected).

### Delivery boundary

- SessionStart remains the fixed reminder with its 2-second budget. Source event
  registration is prepared; Main owns generated surfaces, digest acknowledgements
  and lock binding before activation. No adapter or persistent state is required.
- No live-runtime or behavioral probe result is claimed by offline packet tests.

## [v0.13.13] — 2026-10-21 — Bound handoff authority to the current grant

### Changed

- Bound handoff may-lists to the owner's current grant by verb, with ungranted
  actions listed separately and author restrictions enforced while composing briefs.
- Required full HEADs and digests, individual map/contract identity pins and a final
  per-field and per-pin completeness and verification inventory.
- Preserved existing handoff rules and the fixed SessionStart reminder.

## [v0.13.12] — 2026-10-21 — Complete handoff pin inventory

### Added

- Added opt-in handoff pin availability inventories and explicit last-change commit
  typing while preserving mapping validation and existing pin values.

### Changed

- Clarified permission-aware pin acquisition, complete pin forwarding, recipient
  attribution and owner data restrictions across the entire handoff artifact.
- Kept the fixed SessionStart reminder and its reviewed source mirror within budget.

## [v0.13.11] — 2026-10-21 — One-command handoff pins

### Added

- Added opt-in ontology `mapping --handoff <paths>` text/JSON blocks with repository,
  source and map/contract pins, UTC observation time and explicit unknowns.

### Changed

- Named the one-command handoff pins block in SessionStart and ontology Handoff guidance.

## [v0.13.10] — 2026-10-20 — Mapping handoff pins

### Added

- Extended ontology `mapping` reports with the map path, loaded contract ID and full
  file SHA-256 digests alongside existing versions, with a Handoff hint for obtaining pins.

## [v0.13.9] — 2026-10-19 — Mapping budget 32 KiB

### Changed

- Raised the ontology mapping size warning from 12,288 to 32,768 bytes so growing agent
  repositories keep meaning instead of compressing maps to the limit; what to keep is unchanged.

## [v0.13.8] — 2026-10-19 — Inline handoff fields

### Changed

- Named all six ontology handoff fields inline in SessionStart, including status axes,
  current pins and a final self-check naming missing fields or pins as unknowns.

## [v0.13.7] — 2026-10-18 — Handoff authority

### Changed

- Extended the always-delivered SessionStart reminder to preserve owner-granted handoff
  authority and require the ontology handoff fields with missing fields named as unknowns.



### Added

- Added the dual-runtime `mir-lifecycle-hooks` plugin with one exact, read-only `SessionStart`
  reminder and the `runtime-continuity` skill.
- Added a dry-run-first user-runtime installer for centrally authored Claude/Codex agents and
  Claude commands, with explicit homes, divergence protection, and digest receipts.
- Added submission-ready Codex upstream text for namespaced plugin agents and command aliases,
  linked to the existing agent-plugin request instead of opening a duplicate.
- Added schema-3 dual-runtime capability management for commit-pinned Claude commands, Codex skill
  mappings, and explicit target-local hook and MCP integration ownership.
- Extended the real-CLI plugin probe to verify configured plugin and skill inventories from two
  independent consumer working directories in isolated Claude and Codex homes.
- Added one canonical hook definition and deterministic Claude/Codex renderers for PreCompact,
  PostCompact, and compact-resume lifecycle handling.
- Added the same bounded compact lifecycle to the Project Agent Kit common harness, including
  atomic handoff refresh, ignored runtime evidence, and nested-working-directory coverage.
- Added a current, reference-only harness engineering upgrade guide for repository governance,
  context and token efficiency, memory, embeddings, agents, skills, hooks, and runtime parity.
- Added bounded active-fact retrieval, repository-declared historical document globs, and explicit
  `mir context sync --reindex-missing-vectors` coverage and resume behavior.
- Added the synced `tools/mir_executor` common base (through common v3.8) with optional local
  hooks and data, a common file manifest, and explicit sync and drift checks.
- Committed the Mir Harness-deployed `config/model-routing.lock.json`; executor routing reads it
  first and falls back to the rendered policy.

### Changed

- Updated executor common v3.8 to ignore agent-route model/effort when the route's
  declared backend differs from the resolved dispatch backend. Explicit user model/effort
  overrides retain precedence. Forced modes reject automatically routed models recognized
  as belonging to the opposite backend before starting a runner; category/default policy
  routes declare no backend, so this guard uses Claude aliases and claude-*/gpt-* prefixes.
  Unknown model names remain usable; common manifests remain schema version 1.
- Updated executor common v3.7 to refuse symlink destinations for private worktree
  writes and symlink files/directories when copying artifacts. Agent-route backends
  retain precedence over project/default backends while explicit CLI backend
  requests keep policy-permitted precedence. Restored unconditional forced-mode
  selection, including force_codex with a conflicting Claude agent route;
  common manifests remain schema version 1.
- Updated executor common v3.6 to redact quoted secret assignments (`"api_key": "..."`),
  `*_KEY` names such as `SECRET_KEY`, `Authorization: Basic` values and string values whose
  dict key names a secret.
- Updated executor common v3.5 to reject malformed agent criteria with a clear error,
  qualify Mir Harness ADR-88 references, and fix repository-owned test cleanup of
  temporary worktree bases; clarified lock-first policy precedence in its test docstring.
- Hardened the same executor common v3.5 increment against internal-turn response-ID
  collisions and unissued response IDs. Excessively nested JSON lines are ignored;
  unexpected stdout-reader failure or EOF releases pending calls without a timeout.
- Retired the unused code-path configuration helper and its generated Codex copy after
  owner choice B removed the profile enforcement block. Adopters no longer receive either
  component; the consolidated local safety guard remains unchanged.
- Opened only the schema-4 `skills-hooks` package shape after proving Codex 0.152.1 accepts hook
  plugins; exact handler bytes, hook inventory, and package digest are now required before runtime
  registration. MCP admission remains closed because neither runtime has a registered Yoke server.
- Made agents, skills, hooks, MCP servers, and commands explicit Yoke-managed surface classes while
  preserving runtime-native delivery and ADR-88's closed active-package admission gate.
- Made capability-source package classes explicit and skills-only. Hook and MCP kinds now remain
  fail-closed until separately named packages implement kind-specific validation and fresh digest
  acknowledgement under ADR-88.
- Constrained skills-only manifests to runtime-specific key allowlists, revalidated legacy locked
  trees under current policy, and bound validated local-only marketplace inventories into new locks
  and active-provider receipts before runtime registration.
- Validated plugin versions before installation and separated selected installed plugins from the
  all-materialized digest inventory so receipt downgrade and rollback cannot expand activation.
- Versioned new capability locks and active receipts as schema 2 so removal of their marketplace
  or materialized-plugin bindings fails closed while genuine schema-1 consumers remain readable.
- Bound the schema-2 receipt's selected installed set to independent registry state and validate it
  against materialized digests before rollback, preventing receipt-only activation expansion.
- Revalidate restored marketplace semantics, marketplace digests, and every materialized plugin
  before rollback registration, so rejected provider state never reaches a host command.
- Cross-check rollback receipt schema against the restored lock and registry, preventing a
  receipt-only downgrade from bypassing the schema-2 selected-set binding.
- Kept generated Claude and Codex hook registrations synchronized from project-owned JSON sources
  instead of maintaining runtime configurations independently.
- Extended Project Agent Kit schema and evidence validation so compact lifecycle behavior is
  verified without making owner-run Claude/Codex example repositories a release prerequisite.
- Changed generated Codex roots and write-capable agents to inherit the operator-selected
  permission policy, retained read-only reviewer sandboxes, rejected legacy/profile mixing during
  bootstrap, and replaced deprecated hook and concurrency aliases with current keys.
- Made semantic history reclassification metadata-only so unchanged chunk, FTS, vector, and
  vector-timestamp state is preserved.
- Limited the current optional vector table to its actual 1024-dimensional contract; other
  dimensions now fail before indexing.
- Bound vector writes and resumable backfill to one persisted complete encoder fingerprint.

### Fixed

- Used each host's default `hooks/hooks.json` discovery instead of also declaring the conventional
  path in plugin manifests, preventing Claude from loading the common hook twice while preserving
  stable Codex hook discovery.
- Preserved Yoke-only provider agents during capability updates by classifying them separately
  from the Profile-selected cross-runtime agent union.
- Migrated the existing global capability state through the compatible schema path, activated all
  four packages in Claude and Codex, and recorded fresh skill-catalog and trusted-hook attestations
  before marking the provider READY.

- Fixed shared hook adapters so current Codex `apply_patch` payloads in
  `tool_input.command` receive path safety, post-edit inspection, and durable-memory sync.
- Fixed default `context pull` so active durable facts are available even when no document
  archive is registered, while inactive facts and documents remain behind `--history`.
- Preserved fact subject/provenance identifiers, quarantined instruction-like and
  credential-shaped memory facts before context rendering, and redacted detected credential values
  from post-edit hook output.
- Added bounded Codex `SessionEnd` generation and documented project and hook trust as
  prerequisites for hook-based behavior.
- Rejected symlinked or non-canonical managed targets before overwrite, required declared hook
  projections for readiness, and bound schema-3 sources to current schema-2 state evidence.
- Made host activation equal the union of registered consumer selections, rejected unexpected
  enabled Yoke plugins, and restored the exact prior union after a failed profile update.
- Moved registry snapshots and validation under the apply guard and restored local/runtime state
  for catchable process interruptions.
- Recompute the active plugin union from every same-commit consumer during status validation and
  require exact registry, receipt, materialized digest, and current project-lock agreement.
- Reject hidden extra Codex plugin enablement, symlinked `.mir` lock redirection, and stale
  attestation or finalization writes by using complete persistent-set checks and one apply guard.
- Revalidate the complete consumer union before rollback commands, reject project derivative roots
  with symlinked ancestors, and confine verified Codex cache paths to a symlink-free runtime home.
- Bind every schema-2 registry consumer to its canonical on-disk project lock, validate exact nested
  generation and cleanup targets, and retain an initialization-time Codex-home containment anchor.
- Enroll schema-3 consumers with a 256-bit binding across the project lock, registry, and mode-0600
  provider ledger, and pin project/Codex roots by device and inode against replacement races.
- Reject partial consumer enrollment instead of silently issuing a new binding, verify the ledger's
  regular-file 0600 mode on every read, and require both Claude and Codex for activation readiness.
- Make the schema-3 dual-runtime list exact and pin the capability-home root by canonical identity,
  device, and inode before guards, state access, rollback, or runtime registration.
- Redacted maintainer-identity strings and private repository slugs that were still present in
  this public repository, and corrected the 0.5.0 sanitize-gate note that had claimed the
  substitution table used placeholder forms on both sides. `sanitize-glossary.md` now names the
  class of each removed string instead of the literal — a table that enumerates the strings it
  exists to remove is itself a disclosure — and one missed substitution in a
  `families-overview.md` description field is generalized. These edits change the current tree
  only; the strings remain in this repository's Git history.
- Generalized the attribution comment in `scripts/generate_codex_derivatives.sh` to name the upstream
  license without naming a retired repository. The line had carried a deleted family slug and a
  distribution namespace in the `placeholder (real-slug)` shape that the harness failure-pattern
  ledger names as a leak mechanism, and an earlier commit message in this branch defended keeping it
  on the incorrect premise that the namespace belonged to a third party. The Apache-2.0 notice is
  preserved; only the private identifiers are gone.
- Extended the `sanitization` gate to credential shapes and to every text file it can reach. It had
  been catching the identifier that leaked while missing the shapes that outrank it — a platform
  webhook URL and a bot token are matchable from form alone, so no secret is named to detect them.
  Its file list is now a skip list of binary and generated suffixes instead of a fixed allow list,
  which had left 19 tracked files unscanned including two PowerShell scripts, a `.jsonl` log, and the
  two `.example` configurations — the same class of file the leaked identifier came from. Enumeration
  now uses `git ls-files`, matching the sibling surface contract so the two gates agree on what the
  public surface is. Proven end to end rather than asserted: a synthetic credential in a
  `.toml.example` file makes the gate exit 1, and removing it returns exit 0.
- Widened the release gate step named `sanitization` past its single Hangul check, and redacted the
  five strings it had been unable to see: a platform channel id in an approval example, and four
  unsubstituted private repository slugs in a schema description and three application documents.
  The new checks are pattern-based — a detector in a public repository that listed the private
  strings it looks for would be the disclosure it exists to prevent, which is why the Hangul range
  in that file is already built from code points rather than literals. Both new checks are also
  called from the module's `__main__`, because the gate runs the file as a script and a test absent
  from that block does not run in the gate. The Apache-2.0 attribution line in
  `scripts/generate_codex_derivatives.sh` is deliberately untouched: it credits an upstream project,
  and stripping attribution is not sanitization.
- Added the archive exclusion to the `harness_a.toml` that `mir bootstrap` generates, so a new
  project no longer indexes its own `docs/_archive/` as current material. The template and the
  maintainer configuration already carried it; the generator, which is what every new project
  actually receives, did not.

## [v0.13.6] — 2026-10-18 — Namespace fence and activation scope

### Fixed

- Filtered MK client response nodes and citations by requested namespaces, defaulting to the
  documented federation set, with a content-free degradation reason and unchanged empty exits.
- Rejected Claude activation inventories whose installed package scope is missing or differs
  from `user`, as required by ADR-89.

### Changed

- Aligned all four dual-runtime plugin versions and the optional CLI package to `0.13.6`.

## [v0.13.5] — 2026-10-18 — Ontology handoff packet

### Changed

- Put the six-field ontology handoff packet, missing-pin self-check and owner authority limits
  in the skill body; require actual knowledge-client results, reasons and applied config sources.
- Aligned all four dual-runtime plugin versions and the optional CLI package to `0.13.5`.

## [v0.13.4] — 2026-10-17 — Ontology reachability

### Changed

- Made `mir-core:ontology` discoverable from ordinary questions about identity, knowledge,
  current or historical status, evidence validity, authority, relation direction and agent handoffs;
  documented the minimum parent/child handoff packet and extended the existing bluebricks route.
- Stated that an unavailable knowledge-supply result must not be bypassed by changing its
  configuration or environment (a pilot agent unset the variable to force a connection).
- Aligned all four dual-runtime plugin versions and the optional CLI package to `0.13.4`.

## [v0.13.3] — 2026-10-17 — Item 22 and the request matrix

### Added

- `mir-core:repo-maintenance` adds checklist item 22: proportionate Agent, Loop, Graph and
  Ontology engineering.

### Changed

- `mir-core:verify` turns a request over several targets or items into one claim per target ×
  item and reports `N/M` with the open claims instead of a completion claim.
- The ontology runner extracts its active-distribution checks into `select_active_distribution`
  (no behavior change); consumers refresh their byte copy of the runner.
- Aligned all four dual-runtime plugin versions and the optional CLI package to `0.13.3`.

## [v0.13.2] — 2026-10-17 — Portable default work method

### Added

- The `runtime-continuity` skill packages the portable seven-step default work method
  (`references/default-work-method.md`): intent, design, TDD, eval with a request matrix,
  develop, repeat until tests pass, finish only when every matrix cell has current evidence.

### Changed

- The shared `mir-lifecycle-hooks` SessionStart line also states the method order and the
  completion rule, so every adopting computer and runtime, including delegated Codex threads,
  receives it once; the reviewed handler budget is 1024 bytes.
- `mir-core:design` points to the method order.
- Aligned all four dual-runtime plugin versions and the optional CLI package to `0.13.2`.

## [v0.13.1] — 2026-10-16 — Invariant checks and isolated distribution rehearsal

### Fixed

- Validate declared `domain.invariants[].check` refs during mapping; unresolved refs now report
  mapping errors instead of silently omitting verification links.
- Excluded transient Python bytecode and test/lint caches from capability tree digests while
  preserving existing clean-tree lock digests.
- Enabled full Git history for public CLI CI checks and refreshed stale adopter inventory hashes.
- Prevented automatic consistency tests from rendering live agent memory; render coverage uses
  synthetic fixtures.

### Added

- Ontology impact selects declared checks for affected domain invariants in `checks_to_run`,
  deduplicates them and reports missing check links without executing checks.
- Added isolated supplier/two-consumer distribution and rollback rehearsal coverage and
  `docs/operations/ontology-distribution-rehearsal.md`.

### Changed

- Aligned all four dual-runtime plugin versions and the optional CLI package to `0.13.1`.
- Release metadata checks recognize the explicit `v0.13.1` changelog heading.

## [0.13.0] — 2026-10-16 — Canonical ontology runner and strict reference validation

### Fixed

- Validate common relation IDs and version-gated endpoints in `domain.relations` using the same
  rules as top-level relations; entries without `common` retain ref-only validation.
- `mk_query.py` no longer reports a delivered pack as unavailable when a sandbox answers
  EPERM while the client reaps the server's process group.

### Added

- Added a byte-identical consumer ontology runner that selects active Claude/Codex distributions,
  rejects runtime version disagreement and missing active paths, and explains selection with `--which`.
- Resolve symbol anchors in every mapping ref; retain informational legacy line counts and reject
  line refs into changed files during strict Git impact. Re-anchored Yoke's own map.
- Added Yoke's checkout ontology runner, pytest mapping/strict-impact gate and optional
  on-demand MK guidance, with scoped error-case checks and soft-outage independence.

### Changed

- Aligned all four dual-runtime plugin versions and the optional CLI package to `0.13.0`.

## [0.12.0] — 2026-10-15 — Ontology contract 1.1.0, impact and on-demand knowledge supply

### Added

- `ontology_check.py impact`: changed paths select affected map entries, the covered checks to run
  and stale refs; `--strict` fails on stale refs or an invalid map, for repository verify paths.
- `ontology_check.py lookup`: a bounded query over map questions, concepts and identities.
- `mk_query.py`: a standard-library, on-demand Memory Keeper stdio client (one query per spawn,
  host-local configuration only, soft degradation on missing configuration, timeout, error or
  empty result).

### Changed

- Distributes contract `mir.common-semantics` 1.1.0 (additive): mappings validated against 1.1.0
  declare `from`/`to` concept types on common relations, checked against the contract.
- A covered error case must resolve to an existing file, line or test name; a document warns.
- The checker warns when a mapping exceeds the 12,288-byte index budget; Yoke's own map shrank to it.
- The knowledge-supply guide follows Memory Keeper's real `federation_serve`/`feedback` interface.
- Aligned all four dual-runtime plugin versions and the optional CLI package to `0.12.0`.

## [0.11.0] — 2026-10-14 — Ontology semantic contract skill

### Added

- Added the optional `mir-core:ontology` skill for explicit semantic contracts covering identity,
  relation and status meaning, provenance, impact analysis, and project-owned mappings.
- Added a Python 3.9 standard-library mapping checker and a byte-identical distribution of the
  owner-managed common semantic contract within the skill package. The checker uses explicit
  local inputs and produces deterministic findings; the contract owner remains authoritative.

### Changed

- Aligned all four dual-runtime plugin versions and the optional CLI package to `0.11.0`.

## [0.10.8] — 2026-10-11 — Reference application profile skill

### Added

- `mir-core:reference-app-profile` — extracts a reference program's shipped metadata (stack,
  permissions, signing and sandbox, integrations and endpoints, security policy, storage, updates)
  into a fixed profile with Confirmed/Inferred/Unknown labels; metadata only, no decompilation,
  code tracing or target launch.

## [0.10.7] — 2026-09-24 — Twenty-one-item maintenance checklist

### Changed

- Strengthened `mir-core:repo-maintenance` to twenty-one items with documented database/memory/graph
  repairs, explicit Claude/Codex harness consistency, and checkable Main-runtime parity probes.
  Parity repairs remain non-blocking and cannot recreate owner-removed hooks.
- The maintainer's advisory `UserPromptSubmit` hint now registers for Codex as well as Claude
  (ADR-84 amendment); `StopFailure` stays Claude-only because Codex has no such event.

## [0.10.6] — 2026-09-23 — Repository maintenance checklist skill

### Added

- `mir-core:repo-maintenance`: the owner-defined twenty-item periodic maintenance checklist for
  agent-operated repositories (consistency through open decisions, including test health,
  code/security/dependencies, integrity evidence and runtime behavior). It sequences the existing
  governance, verify, testing and code-review skills. It stays read-only unless a fix is requested and never
  fabricates provenance or weakens a safety guard.

## [0.10.5] — 2026-09-23 — Codex plugin and app-server transport records

### Changed

- ADR-69 and ADR-85 carry a dated amendment: Claude reaches Codex through the official Codex plugin
  (`codex:codex-rescue` / `/codex:rescue`) and `mir_executor` dispatches through `codex app-server`,
  replacing the removed `codex mcp-server` lane.
- Under `force_codex`, the sub-agent policy gate admits only the official `codex:codex-rescue` plugin
  agent; every other named agent stays blocked.
- Agent dispatch rules, guard and shim messages, and executor docstrings name the plugin/app-server
  lanes. The raw `codex exec` ban is unchanged.

### Fixed

- The setup-wrapper test isolates `XDG_DATA_HOME` so host data never leaks into the fixture.

## [0.10.4] — 2026-09-21 — Explicit SRR provider selection

### Fixed

- Require delivery-selected provider and target-root paths for portable SRR commands, avoiding
  ambiguous repository-local consoles while retaining ordinary-search fallback when unsupported.
- Make relation-ingest guidance enter the declared target root before resolving whitelisted source
  paths, and fail before invoking a provider when that root is unavailable.

## [0.10.3] — 2026-09-21 — Selective SRR scope and direct dependency defaults

### Changed

- Focus common skill selection on known-anchor implementation, verification and direct dependencies;
  keep broad impact exploration for explicit requests and ordinary search for known answer locations.
- Default omitted dependency depth to one hop in YAML/memory queries and dependency facets within bundles; preserve
  explicit deeper traversal and the existing three-hop default for other purposes.
- Preserve compact source-validated evidence, existing memory/body retrieval and the database schema.

## [0.10.2] — 2026-09-19 — Anchor-scoped SQL relation selection

### Changed

- Resolve memory anchors and select purpose-specific SQL neighborhoods before validating source
  evidence, so disconnected project growth does not exhaust a small query's relationship budget.
- Keep independent bundle frontiers, directional traversal, source/snapshot guards and compact
  source proofs; report unexamined boundary candidates without reading their source bodies.
- Preserve ordinary memory search, ingestion, embeddings, body retrieval and existing schema.

## [0.10.1] — 2026-09-18 — Stable selective retrieval and compact evidence

### Fixed

- Charge rejected source reads to the aggregate validation budget and report incomplete relation
  views explicitly. Preserve memory scope and validation notices when falling back to search.
- Detect database/WAL/journal changes around immutable snapshot reads and discard unstable results.
- Document provider writer/reader routing when a consumer still has an older repository-local CLI.

### Added

- Optional bounded authored summary/reason fields alongside backward-compatible triple declarations.
- Compact source evidence with real declaration locations and explicit authored/generated basis;
  agents choose the needed original span instead of receiving complete source bodies.

## [0.10.0] — 2026-09-18 — Source-backed memory relations

### Added

- Opt-in `memory_relations` Markdown declarations for explicit implementation, verification and
  dependency relationships, represented in existing entity-object facts and stated provenance.
- Read-only `--memory` query/bundle retrieval from the owning root's canonical database, with
  bounded output, current-source validation and memory/source provenance.

### Changed

- Reconcile relation evidence per source, retaining independent sources, multiple targets and
  history; preserve atomic validation failures and idempotent source re-ingestion.
- Keep ordinary YAML retrieval and embedding lifecycle independent. No new relation table,
  natural-language inference, similarity-based promotion or automatic historical backfill.

## [0.9.2] — 2026-09-18 — SRR applicability and dynamic-memory guidance

### Changed

- Clarified bounded project/subsystem orientation, implementation/verification, change impact,
  declared dependencies, decision/evidence and history use cases, with explicit portable-reader
  versus native-adapter boundaries.
- Documented reuse of existing entity/fact/link/provenance stores, source-validated relation
  admission, asynchronous embedding, idempotent updates and source-driven invalidation.
  Re-embedding does not invalidate verified source-backed relations. No automatic DB writer,
  extraction, new CLI purpose, or performance guarantee is introduced.

## [0.9.1] — 2026-09-18 — Selective relation retrieval

### Added

- Added the on-demand `mir-core:selective-relations` skill for bounded selective relation retrieval
  (SRR), with `mir-code:bluebricks` and `mir-content:knowledge` pointers for applicable work.

### Changed

- Refresh managed native plugin caches during provider updates and rollback so install/add cannot
  silently retain an older package behind a successful command exit.
- Documented SRR as declared, provenance-bearing relationship discovery. It does not promise token
  savings, require a per-repository database migration, or generate a graph.

## [0.9.0] — 2026-08-11 — Project Agent Kit boundary

### Added

- Added the supported `recipes/project-agent-kit/` user journey. One short purpose prompt now routes
  the target agent to a project brief, local harness, repository-unique read-only reviewer, real
  lint/build/test Git hook, and verified initial commit before development planning.
- Added ADR-83 and contract tests for the Starter, recipe, portable plugin provider, reference
  corpus, Git boundary, and clean-room release evidence.
- Added a two-phase clean-room observer and release validator that recompute target bundles, declared
  commands, original Git/hook state, provider/outside snapshots, and sanitized runtime transcripts
  for owner-run post-release acceptance.

### Changed

- Kept `starter/` as the only consumer payload while making the Project Agent Kit a separate
  supported guidance surface with a project-owned common harness and required SQLite+FTS5 memory.
- Restored the public v0.8 `mir` command surface as an optional installed v0.9 tool. Installation
  grants no target authority, and the standard Project Agent Kit never copies its source.
- Generalized common plugins so they do not require Mir CLI, `.ai-harness`, fleet phases, a shared
  wiki, a particular browser command, or a fixed Starter-compliance count.
- Kept namespaced plugins optional and separated the installed CLI from generated target files.
- Moved release-time dual-runtime clean-room evidence out of the tag gate. Repository validation
  publishes the GitHub Release first; the owner performs external generated-repository acceptance
  afterward with the verifier still available.
- Replaced the platform bootstrap CI path with supported-surface and isolated-plugin validation.

### Removed

- Removed active product planes, capability packs, advisory profiles, distribution archives, and
  target-writing `yoke` plan/apply composition. Their files are preserved only as inert reference
  templates.
- Removed provider-side greenfield bootstrap from the standard new-project contract. Owners may
  still select the restored installed `mir bootstrap` path explicitly.

## [0.8.0] — 2026-08-06 — Portable project bootstrap

### Added

- Added dual Claude/Codex marketplaces with namespaced `mir-core`, `mir-code`, and `mir-content`
  plugins, including `spec-architect` in every project profile.
- Added an exact-SHA Git capability lock, read-only update checks, explicit verified updates,
  global consumer conflict protection, and project-local managed agent packs.
- Added a cross-platform Python bootstrap coordinator with Unix and PowerShell wrappers, a
  two-phase restart/finalize contract, and Windows Git Bash readiness checks.
- Added a required SQLite+FTS5 memory doctor, tracked-Markdown archive indexing, automatic durable
  edit synchronization, and optional/required vector validation modes.

### Changed

- Moved common skills out of raw project directories into one plugin-owned canonical tree and
  replaced generated hook symlinks with real copies.
- Made tracked Markdown the portable memory source of truth and `.mir/memory.db` a machine-local,
  rebuildable query index.
- Made `sqlite-vec` an optional dependency so the required non-vector memory baseline installs on
  macOS, Windows, and Linux.

### Security

- Capability updates reject credential-bearing URLs, unsafe refs and paths, symlinks, submodules,
  executable remote content, duplicate skill providers, conflicting global versions, and locally
  diverged managed agents.
- Bootstrap stages database changes and refuses ready receipts when memory, plugin activation,
  runtime hashes, architecture initialization, or required platform prerequisites are unproven.

### Verification

- Plugin manifests and isolated closure, capability lifecycle and security, bootstrap transaction,
  memory doctor and vector coverage, derivative parity, full regression, and a macOS/Linux/Windows
  clean-clone workflow are release gates.

## [0.7.1] — 2026-07-15 — Compact startup context and canonical closeout

### Changed

- Reduced `CLAUDE.md` and generated `AGENTS.md` to outcomes, canonical sources, authority
  boundaries, evidence, completion, and a compact role summary.
- Moved detailed workflow and role values behind on-demand documents and `.mir/repo-profile.toml`.
- Switched Codex project skills to discoverable directory symlinks and removed duplicated skill,
  agent, and hook catalogs from startup instructions.
- Made startup document budgets static test evidence instead of a missing per-session CLI call.
- Updated bootstrap and preservation guidance so generated `AGENTS.md` is never edited directly.

### Fixed

- Removed dead global-backup and nonfunctional profile-compiler work from public SessionStart.
- Replaced timestamped closeout summaries with one canonical
  `tasks/handoffs/session-handoff-LATEST.md` and wired Claude `SessionEnd` to it.
- Aligned catalog compatibility and hook-policy summaries with the ADR-73 proportional shared-Main
  contract.
- Replaced stale applied-state role-policy strings and broken compact-document section selectors.

### Verification

- Codex derivative, closeout, context-path, registry, applied-state, sanitize, focused startup, and
  full regression checks are release gates for this patch.

## [0.7.0] — 2026-07-15 — Proportional dual-CLI operating baseline

### Changed

- Adopted the ADR-73 proportional operating contract: bounded Main-direct work is valid, while
  delegation, worktrees, TDD matrices, independent review, monitoring, and broad suites are selected
  when their risk reduction justifies their cost.
- Retained the ADR-69 raw-`codex exec` ban while treating unavailable preferred lanes as lane-local
  limitations when another safe in-scope path remains.
- Made aged-run monitoring observe-only and cleanup terminal-only; retained the server-side CI and
  protected-branch prerequisite for multi-contributor use.
- Aligned the public agent/skill catalog to revision v3.8 with 12 consolidated skills, including
  `memory-gc`.
- Refreshed the public decision index and compact current ADR summaries without importing private
  fleet state, family paths, or private review history.

### Fixed

- Prevented `.claude/agents/README.md` from generating the invalid
  `.codex/agents/.toml` manifest target.
- Removed private-language task aliases from the public context classifier and restored the
  `changed_selected_count` freshness field.
- Reconciled README guidance with the checked-in `unrestricted` sub-agent policy default.

### Verification

- Codex derivatives are regenerated from Claude sources and checked by
  `scripts/verify_codex_sync.py`.
- Template applied-state, sanitize, context-path, focused test, and parity-generation checks are
  required before the release commit is tagged.

## [0.6.0] — 2026-06-28 — Sub-agent execution policy (force_codex) + delegated-execution gate

Added the `force_codex` sub-agent execution policy to the template:

- `config/sub-agent-policy.json` global switch (`force_codex` / `select` / `per_project` /
  `unrestricted`) with a `MIR_SUB_AGENT_POLICY` home-server overlay, fail-closed to `force_codex`.
- `.claude/hooks/sub-agent-policy-gate.sh` — a slug-free, family-invariant PreToolUse hook that
  hard-blocks Claude `Agent`/`Task` sub-agent spawns under `force_codex` (`exit 2`), with a
  `MIR_R3_FALLBACK=1` escape, wired via a new `^(Agent|Task)$` settings entry.
- README: new "Sub-agent execution policy & delegated execution" section + a "Using the harness —
  the loop" usage guide.

## [0.5.0] — 2026-06-13 — Template completeness release

Closed the template completeness gap: a fresh `git clone` now yields an
immediately applicable harness with the full docs/harness-engineering set,
a post-clone setup checklist, and all missing harness components.

### Added

- `docs/harness-engineering/`: ported 62 files from prompt_DEV 2026-06-11 baseline
  (phases 0–14, applications, appendix, mir-roles, active-agents gap, context-surface
  reduction, phase-N-baseline stubs, sanitize-glossary). Total: 79 tracked files.
- `## Template Purpose` section in `CLAUDE.md` — post-clone instructions and
  component inventory (sanitized from prompt_DEV a052747).
- `setup.sh`: placeholder guard — warns while `slug = "your-harness"` or
  `display_name = "Your Harness"` remain in `.mir/repo-profile.toml`, or while
  `family= "your-harness"` remains in `session-start.sh`. Post-clone checklist
  banner (8-step path to working harness).
- `.mir/repo-profile.toml`: auto-created by setup.sh on first run (placeholder values).
- `.mir-preserve.toml`: lists preserved dirs/sections so fleet rollout skips template
  harness-engineering + decision docs.
- `.mir/boundary.md`: generic allowed/blocked policy for this template.
- `.claude/skills/memory-gc/SKILL.md`: GC scan skill (user-triggered only).
- `.claude/hooks/_lib/invocation_log.sh`: phase-6 usage telemetry helper.
- `.claude/hooks/_lib/tier_dispatch.sh`: tier-routing helper (block/suggest/warn).

### Changed

- `CHANGELOG.md` and `VERSION`: bumped to 0.5.0 per ADR-40 release procedure.
- Phase docs (phase-0 through phase-12 + README): editorial English wording rewrites
  (no structural changes).

### Sanitize gate

All content under `docs/harness-engineering/` passes the sanitize gate (0 sensitive
hits), including `applications/template-repo/sanitize-glossary.md`, whose mapping
table uses placeholder forms (e.g. `/path/to/project/`) on both sides.

> **Correction (2026-09-02):** the sentence above was not true when written. The
> substitution table's left column held the literal maintainer identity strings and
> fourteen real repository slugs, not placeholder forms, and one
> `families-overview.md` description field kept a real slug. Both are redacted in
> the current tree; see the Unreleased entry. Left in place rather than rewritten,
> because a released note that silently becomes correct hides that the gate reported
> a pass it had not earned.

## [0.4.0] — 2026-05-25 — Applied-state baseline completion

Raised the public template working tree to an applied-state baseline that
satisfies the template verifier.

### Added

- `docs/harness-engineering/phase-0-baseline.md` through
  `phase-12-baseline.md`
- `docs/templates/_schema/design_doc.schema.json`
- `docs/templates/_schema/fleet_harness_state.schema.json`
- `docs/templates/_schema/family_config.schema.json`
- `docs/templates/_schema/report_contract.schema.json`
- `docs/templates/_schema/tdd.schema.json`
- `docs/templates/_schema/mir_agent_self_health.schema.json`
- concise ADR parity stubs for missing baseline decision numbers required by
  the applied-state verifier

### Changed

- Sanitized schema descriptions to keep the public template English-only.
- `verify_template_applied_state.py` now passes against the working tree.

### Notes

- This release is recorded in the workspace before a follow-up commit/tag.

## [0.3.0] — 2026-05-24 — Phase-4 state machine modules

Synced the phase-4 state machine implementation.

### Added

- `tools/run_orchestrator/state_machine.py` — 13-state SM (`RunState`
  StrEnum: IDLE/DISCOVER/PLAN/NEED_APPROVAL/ACT/VERIFY/REPORT/DONE/REPLAN/
  BLOCKED/CANCELLING/ROLLBACK/INTERRUPTED) + `RUN_TRANSITIONS` table.
- `tools/run_orchestrator/run_orchestrator.py` — `run_state.json` driver
  (init_run + transition + get_current_state + record_tool_event) with
  ULID generation + atomic write + jsonschema validation.
- `tools/run_orchestrator/approval_gate.py` — Discord-delegated approval
  (request_approval + parse_reply + apply_decision). Zero network calls.
- `tools/hooks/validate_tool_contract.py` — pre-tool-use hook validator
  (env-gated by `MIR_TOOL_CONTRACT_REQUIRED` or `MIR_TOOL_CONTRACT_LOG`).
- `src/mir/core/engine/structured_error.py` — `StructuredError` frozen
  dataclass + `ErrorType` StrEnum (7 members) for unified error format.
- `src/mir/core/engine/tool_contract.py` — `ToolContract` 4-field obligatory
  metadata (idempotency_key, precondition, dry_run, side_effect_summary).
- `src/mir/core/engine/interrupt_handler.py` — git stash-based atomic
  rollback for ACT→CANCELLING→ROLLBACK→INTERRUPTED transitions.

### Changed

- `docs/templates/_schema/run_state.schema.json` — added `session_id` +
  `current_step_id` (optional ULID per phase-4 5-tier execution unit spec).
- `docs/templates/_schema/tool_event.schema.json` — added `turn_id`
  (REQUIRED ULID) + `step_id` (optional).
- `docs/templates/_schema/task_state.schema.json` — added
  `origin_session_id` (optional ULID).
- `docs/templates/_schema/approval.schema.json` — added DENIED/DELAYED to
  status enum + auto_policy oneOf + discord_chat_id / denial_reason /
  delay_reason fields.

### Notes

- Phase-4 state machine is opt-in via `python -m tools.run_orchestrator --use-13-state`.
- Default `cli.py` behavior remains 7-state (backward compat per ADR-44).
- Tool contract validation is OFF by default; activate via
  `.claude/settings.json` env `MIR_TOOL_CONTRACT_REQUIRED=1` (enforce) or
  `MIR_TOOL_CONTRACT_LOG=1` (advisory only).
- This release consolidates the phase-4 state-machine work.
- 0 Korean leakage across all synced surfaces.

## [0.2.0] — 2026-05-24 — R17 fleet rollout hook sync

Synced upstream the source harness repo hook updates from the R17 fleet phase rollout.

### Changed

- `.claude/hooks/mir-stop.sh` — updated to match upstream R17 baseline.
- `.claude/hooks/pre-commit-verification.sh` — updated to match upstream R17 baseline.
- `.claude/hooks/pre-tool-use.sh` — updated to match upstream R17 baseline (includes phase-2 enforcement domain pinning + code-path config helper).
- `.claude/hooks/session-start.sh` — updated to match upstream R17 baseline.
- `.claude/hooks/stop-failure-audit.sh` — updated to match upstream R17 baseline.
- `.claude/hooks/tdd-task-created.sh` / `tdd-task-completed.sh` — updated to match upstream R17 baseline.

### Added

- `.claude/hooks/lib/code-path-config.py` — helper for per-family enforced code-path resolution + ADR-23 dogfooding exemption check.

### Notes

- 0 Korean leakage verified across all synced hook surfaces.
- Synced hooks are versioned in the source repo; backups are not included in the template.
- This release consolidates the R17 hook sync.

## [0.1.0] — 2026-05-23 — PROMOTE-R5a (schemas + light ADR)

Initial semver release. First sanitized promotion of upstream harness-engineering work to the public template.

### Added

- `VERSION` (`0.1.0`) — initial semver version artifact (per ADR-40 §Versioning Policy).
- `MIGRATION.md` skeleton — empty migration log, ready for first MAJOR bump.
- `docs/templates/_schema/` — 13 R5-era schemas (all 0-Korean, English-clean):
  - `adr.schema.json`
  - `agent_frontmatter.schema.json` (re-promote — previously already present)
  - `approval.schema.json`
  - `arch.schema.json`
  - `memory_entry.schema.json`
  - `phase.schema.json`
  - `prd.schema.json`
  - `review-rounds.schema.json`
  - `run_state.schema.json`
  - `s4_input.schema.json`
  - `skill.schema.json`
  - `task_state.schema.json`
  - `tool_event.schema.json`
- `docs/decisions/adr-18-orchestrator-runtime-guard.md` — sanitized v4 (R3/R4 audit absorbed). Korean memory quotation (4 lines) translated to English. Naming convention aligned with template (no date suffix).

### Changed

- `CHANGELOG.md` format migrated to [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) (`## [vN.M.X] — YYYY-MM-DD — title`). Pre-`0.1.0` entries below preserved verbatim.

### Deprecated

- (none)

### Removed

- (none)

### Fixed

- (none)

### Security

- (none)

### Notes for adopters

- PROMOTE-R5a deliberately ships **schemas + 1 light ADR + versioning artifacts only**. The Korean-heavy `docs/harness-engineering/` directory (24 docs × 70-180 Korean lines each) is deferred to a follow-up round once an LLM-assisted sanitize pipeline (`scripts/sanitize_for_template.py`, upstream R11) is available. Hand-translating 24 docs accurately exceeds a single-round budget.
- See upstream [`docs/harness-engineering/applications/template-repo/current-state.md`](https://github.com/youngjin39/mir-yoke/blob/main/) (placeholder link; doc lives upstream until R11 promote) for the full physical-vs-design gap snapshot.
- New JSON Schemas are all `additionalProperties: false` (Draft 2020-12). Validate your family configs with `python -m jsonschema -i config/repos/<name>.json docs/templates/_schema/<schema>.json`.

---

## Pre-0.1.0 (date-format entries, historical reference)

## 2026.05.2 — fleet governance + sub-agent definitions + pattern catalogue

- Added `docs/governance/principles.md` — six fleet-governance principles
  (autonomy / direct-management / skills+tools / per-repo recording /
  catalogue cross-pollination / unused-component archive).
- Added `docs/governance/fleet-observation.md` — public design summary
  of the Facts/Checks/Scorecards 3-layer inspection pipeline, bucket
  decision matrix, S2 autonomous-fix safety net, S3 advisory handoff,
  and S4 import wave rollout (canary → wave 1 → rollback).
- Added four reference sub-agent definitions under `.claude/agents/`:
  `executor-agent` (Codex execution lane), `quality-agent` (Claude
  fallback review), `codex-final-reviewer` (Codex primary review),
  `fleet-doc-steward` (CLAUDE.md / AGENTS.md drift governance).
- Seeded `docs/patterns/` catalogue with three transplant-ready
  reference patterns + auto-generated `INDEX.md`:
  `bounded-review-plane.md` (curriculum / docs workspaces),
  `app-product-flutter.md` (Flutter app product),
  `content-workspace.md` (narrative / score authoring).

## 2026.05.1 — content expansion

- Expanded README comparison section into a 7-row matrix (vs Claude Code default, Codex CLI default, superpowers, Archon, OpenHarness, claude-code-skills, hand-rolled CLAUDE.md). Names the unique slice this template fills.
- Added 3 examples: `examples/fix-bug/`, `examples/refactor/`, `examples/multi-round-review/` — the last is an anonymized walkthrough of a real multi-round adversarial review that landed a 500-LOC change in 3 rounds.
- Added 3 skills: `deep-interview` (ambiguity gate), `git-commit` (commit hygiene + safety rules), `project-doctor` (health check / drift report).

## 2026.05 — initial public release

- Dual-CLI harness: Claude Code + Codex CLI, identical hook scripts on the 8 shared events.
- 5 hook scripts: `pre-tool-use`, `post-edit-check`, `session-start`, `session-end`, `pre-compact`, plus the `tdd-guard` helper.
- 5 built-in skills: `design`, `writing-plans`, `testing`, `code-review`, `verification`.
- `.ai-harness/` rule set: common rules, development rules, deny-list, TDD matrix, session closeout, failure patterns.
- `tasks/` + `docs/` working ledger.
- Worked example: `examples/add-feature/`.
