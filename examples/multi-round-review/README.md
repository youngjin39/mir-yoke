# Historical example — multi-round adversarial review

For current work, follow the two-round cap on routine reviews per slice in the [default work method](../../plugins/mir-lifecycle-hooks/skills/runtime-continuity/references/default-work-method.md#cross-cutting-practices).

A workflow for landing a non-trivial change with high confidence: spawn several independent reviewers in parallel, prioritize their findings, fix in small chunks, re-review.

This pattern is a real-world recipe — it is what we used to land a 400-line architectural decision spec plus its first implementation spike. The first review caught 27 findings; the second review caught 18 more; the third was clean. Every fix was atomic and tested.

> **Scenario**: You just landed a non-trivial implementation (~500 LOC) for a feature that has both architectural implications and concurrency concerns. Standard single-pass review is unlikely to catch everything. You want adversarial coverage.

## Walk-through

### 1. Frame the review domains

Decide what kinds of issues matter for this change. Common decomposition:

- **R1: Design vs implementation gap** — does the code do what the spec says?
- **R2: Code quality / logic** — correctness, error handling, edge cases
- **R3: Hook / integration / config** — interaction with the rest of the system
- **R4: Test coverage** — are the right things tested, are tests brittle?
- **R5: Cross-cutting / blast radius** — what else does this touch?
- **R6: Schema / data integrity** — for changes that write to a store

For your project, the domains may be different. The principle: pick 4-6 lenses that are *orthogonal*. If two lenses overlap heavily, drop one.

### 2. Spawn N reviewers in parallel (one per domain)

The orchestrator (Claude Code in our case) launches one sub-agent per domain. Each agent receives:

- a one-paragraph scope (what their lens is)
- the file paths that are in-scope
- the design document the implementation should match
- the output format (severity-tagged finding list, file:line, suggested fix)
- a word budget (300-500 words to keep findings sharp)

Agents run **independently** — they do not see each other's findings. This is the point: independence catches things consensus misses.

### 3. Aggregate + prioritize

Once all agents return, combine the findings into one list. Tag each with:

- **CRITICAL** — data loss, security boundary breach, atomicity violation
- **HIGH** — incorrect common-case behavior
- **MEDIUM** — incorrect edge-case behavior
- **LOW** — style, minor naming
- **INFO** — observation, no action needed

Common patterns:

- A finding shows up from two reviewers independently → it is real, prioritize higher.
- A finding shows up from only one reviewer → check the evidence; might be a misread of the diff.
- A finding contradicts another → resolve before fixing; the disagreement might be the actual issue.

### 4. Fix in small chunks, ordered by severity

Do not fix all 20 findings at once. Fix in this order:

1. CRITICAL items first (one fix → test → next).
2. HIGH items next.
3. MEDIUM and LOW batched together if they are mechanical.
4. INFO items: convert to follow-up tasks, do not fix in this pass.

Each fix gets:

- Its own ledger entry update (or a new entry if scope expands).
- Its own test (when applicable).
- A short verification step before moving to the next.

### 5. Spawn a verifier (different sub-agent)

After all fixes are applied, spawn ONE more sub-agent — the verifier — to read the diff and confirm:

- Every finding has been addressed (table: finding → addressed-yes/no).
- The regression suite still passes.
- Lint / type-check are clean.
- No NEW findings were introduced by the fixes themselves.

If the verifier turns up any **new** finding, treat that as a fresh round-2 review; do not just patch and ship. The new finding is evidence that fix #N introduced an issue that round-1 reviewers could not see.

### 6. Repeat until clean

A round is "clean" when the verifier returns zero new findings of severity HIGH or higher. LOW / INFO observations can be deferred to a follow-up issue.

For our 500-LOC change, the round counts were:

| Round | Findings | Fixes | New tests | Final verifier verdict |
|---|---|---|---|---|
| 1 | 27 | 11 | 4 | PASS with 1 MEDIUM (data artifact) |
| 2 | 18 | 8 | 4 | PASS with 2 LOW (informational) |
| 3 | 5 | 3 | 3 | PASS, ship |

Each round produced a commit. Each commit's message named the round and listed the findings addressed.

## Pattern annotations

### Why parallel?

Sequential reviewers anchor on each other's findings. Two reviewers reading the same diff back-to-back will frequently agree on the obvious issues and miss the same non-obvious ones. Parallel reviewers, each given a different lens, catch a wider distribution.

### Why N=4-6, not N=12?

Past N=6, returns diminish sharply. The marginal reviewer mostly duplicates findings already raised. Worse, larger panels increase the orchestrator's aggregation cost — the orchestrator now spends most of its tokens on dedup instead of fixing. 4-6 is the sweet spot we observed.

### Why a separate verifier?

The orchestrator who applied the fixes is anchored. Asking the same orchestrator "did you fix it correctly?" gets you "yes" almost regardless. A fresh sub-agent reads the diff cold and reports what it sees.

### Where the harness helps

- The TDD-guard ensures every fix has a ledger entry (fixes cannot land off-the-books).
- The pre-commit verification re-runs the ledger commands for each fix's commit.
- The deny-list catches the failure mode where the agent gets frustrated mid-round and tries to bypass with `git commit --no-verify`.

## When to use this pattern

- The change is non-trivial (>200 LOC or crosses 2+ architectural boundaries).
- The cost of a bug is high (production data, security, irreversible state).
- You have more than one reviewer (sub-agents count).
- You can afford 2-3 review rounds before merging.

## When NOT to use it

- Small bug fixes with one obvious root cause (single-pass review is enough).
- Refactors that your test suite already proves are safe (the suite IS the review).
- Time-sensitive hotfixes (do the hotfix, then run multi-round review *after* it lands as a follow-up).

## Output artifacts

A clean run leaves you with:

- N round-1 review files (one per reviewer)
- One aggregation file (the priority-ordered finding list)
- M commits (one per fix)
- One verifier file per round
- A final closeout in `tasks/plan.md` summarizing the round counts and total fixes
