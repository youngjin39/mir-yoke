# Example — add a feature end-to-end

A small worked example of running a new feature through the harness:

> Add a `--reverse` flag to the CLI tool that reverses the output.

## Walk-through

### 1. Design (skill: `design`)

Three alternatives:

| | Alt A: append flag in the existing CLI parser | Alt B: post-process pipe-style | Alt C: new subcommand |
|---|---|---|---|
| Idea | Add `--reverse` to the existing arg parser | Add a generic `--filter reverse` indirection | Split into `cli reverse` subcommand |
| Cost to build | low | medium | medium |
| Cost to maintain | low | high | medium |
| Failure mode | flag collision | filter discoverability | command tree growth |
| Reversibility | yes (revert one diff) | yes | yes |

**Recommendation**: Alt A. Smallest surface, single point of failure, fits the user expectation of `--flag`.

**Counter-narrative**: Alt B generalizes to future filters; if we expect five more, Alt B saves work later.

User picks: **A**.

### 2. Plan (skill: `writing-plans`)

```
Step 1 — add CLI flag
  files: src/cli.py, tests/test_cli.py
  commands:
    - pytest -q tests/test_cli.py
    - python -m mytool --reverse hello
  expected:
    - tests/test_cli.py::test_reverse_flag passes
    - 'olleh' on stdout

Step 2 — wire reverse logic
  files: src/cli.py
  commands:
    - pytest -q tests/test_cli.py
  expected:
    - all 4 tests in test_cli.py pass

Step 3 — verify regression
  files: (none — read-only)
  commands:
    - pytest -q
    - ruff check src/ tests/
  expected:
    - full suite green
    - ruff clean
```

TDD ledger entry:

```jsonc
{
  "id": "add-reverse-flag-2026-05-11",
  "scope": "Add --reverse flag to mytool CLI; reverses stdout output.",
  "targets": ["src/cli.py", "tests/test_cli.py"],
  "categories": {
    "unit": { "status": "planned", "command": "pytest -q tests/test_cli.py", "notes": "covers --reverse path" },
    "integration": { "status": "covered_existing", "notes": "tests/test_cli_integration.py exercises CLI entry" },
    "e2e": { "status": "planned", "command": "python -m mytool --reverse hello", "notes": "stdout=olleh" },
    "browser": { "status": "not_applicable", "reason": "CLI tool, no UI" },
    "edge": { "status": "planned", "command": "pytest -q tests/test_cli.py -k reverse_edge", "notes": "empty input + unicode" },
    "architecture": { "status": "covered_existing", "notes": "no new module boundary" },
    "availability": { "status": "not_applicable", "reason": "no retry / queue" },
    "load": { "status": "not_applicable", "reason": "not on hot path" },
    "soak": { "status": "not_applicable", "reason": "no long-running resource" },
    "security": { "status": "not_applicable", "reason": "no boundary touched" },
    "compatibility": { "status": "covered_existing", "notes": "no API change" },
    "transaction_locking": { "status": "not_applicable", "reason": "single-writer CLI" }
  }
}
```

### 3. Implement (Codex executes)

Codex receives the plan + ledger entry, writes the code + tests. Each `Edit`
fires the pre-tool-use hook; the TDD-guard sees `src/cli.py` is in the entry's
`targets` and lets the edit through.

### 4. Review (skill: `code-review`)

Codex (or a reviewer agent) reads the diff, returns a finding list. Maybe:

```
[LOW] src/cli.py:42 — magic string 'reverse' could be a Reverse(Enum) member
```

User decides whether to roll the fix in or defer.

### 5. Verify (skill: `verification`)

Closeout block with evidence:

```
## Static
- tests: 28 passed (4 new), 0 skipped, 1.2s
- lint: PASS (ruff)
- type-check: PASS (mypy)

## E2E
- python -m mytool --reverse hello → 'olleh' ✅
- python -m mytool --reverse '' → '' ✅
- python -m mytool --reverse 한국어 → '어국한' ✅

## Findings
- (one LOW addressed inline)

## Verdict
PASS — feature complete, ready for commit.
```

### 6. Commit

```bash
git add src/cli.py tests/test_cli.py tasks/tdd.json
git commit
```

The pre-commit hook re-runs the ledger commands. All `pass`. Commit lands.

## What this example shows

- One person (or two CLIs) walked a feature from "I want X" to a green commit in five
  steps. Every step left a paper trail: ledger entry, hook output, test result.
- The harness did not write the code — it just made sure no step got skipped.
