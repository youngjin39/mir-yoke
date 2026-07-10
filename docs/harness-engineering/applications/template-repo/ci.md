---
status: design-v1
date: 2026-05-23
scope: template repo (template-harness) CI + pre-commit + health check
audience: your-harness Role B (Template Maintainer)
priority: R10-T02 newly established (ADR-40 §Health Check + Template Repo CI spec)
---

# Template CI + Pre-commit + Health Check

> **Purpose**: Self CI / pre-commit / daily health check spec for the `template-harness` template repo. Role B validates template health daily and per-PR.

## 0.5 Design Goals (R10 anchor)

**3-axis contribution**:
- **Axis I (your-harness strengthening)**: your-harness-as-agent (Role B) automates template self quality verification
- **Axis II (Public template sync)**: ensures template repo is a first-class maintained artifact via CI → resolves Slice A "passive sync target" defect
- **Axis III (Fleet central management + back-propagation)**: daily template health report is the fleet-wide trust base

**Inter-phase contract**:
- **Input** (consumed): every PR + daily cron to template repo
- **Output** (produced): CI verdict + daily health report → Discord alert (on failure) + ADR-40 maintenance trigger

## 1. 3 CI Workflows (`.github/workflows/`)

### 1-1. `validate.yml` — every PR
```yaml
name: validate
on:
  pull_request:
    branches: [main]
jobs:
  schema:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.11' }
      - run: pip install jsonschema
      - run: python tests/test_schema_validity.py
  link_check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: python tests/test_link_integrity.py
  hook_exec:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: python tests/test_hook_executability.py
  sanitize:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: python tests/test_no_korean_in_user_facing.py
  role_policy_parity:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: python scripts/verify_template_applied_state.py --format json >/tmp/template-applied-state.json
```

### 1-2. `release.yml` — every version tag
```yaml
name: release
on:
  push:
    tags: ['v*']
jobs:
  notify_fleet:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Read VERSION
        run: echo "VERSION=$(cat VERSION)" >> $GITHUB_ENV
      - name: Extract CHANGELOG entry
        run: python scripts/extract_changelog_entry.py $VERSION > /tmp/release_notes.md
      - name: Notify your-harness fleet (Discord webhook)
        env: { DISCORD_WEBHOOK: ${{ secrets.HARNESS_FLEET_DISCORD }} }
        run: python scripts/notify_discord.py /tmp/release_notes.md
```

### 1-3. `daily_health.yml` — daily cron 04:00 UTC
```yaml
name: daily_health
on:
  schedule: [{ cron: '0 4 * * *' }]
  workflow_dispatch:
jobs:
  health:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: python tools/template_health.py --report /tmp/health.json
      - name: Notify your-harness if degraded
        if: failure()
        run: python scripts/notify_discord.py /tmp/health.json --priority
```

## 2. Pre-commit (`.claude/hooks/`)

Template repo's own hooks (separate from your-harness hooks).

### 2-1. `pre-commit-verification.sh`
```bash
#!/bin/bash
set -e
# Lint (markdown + python + bash + json)
python tests/test_schema_validity.py
python tests/test_link_integrity.py
python tests/test_no_korean_in_user_facing.py
echo "[template pre-commit] PASS"
```

### 2-2. `pre-edit.sh`
- Different signal than your-harness pre-edit: fires when template-side contributor (user OR your-harness Role B) directly edits
- Code surface protection: `MIR_FAMILY_CODE_PATHS` does not apply to template, so not used
- Instead, `template_protected_paths.yaml` (R11):
  - `VERSION` (single line only)
  - `CHANGELOG.md` (KeepAChangelog format only)
  - `MIGRATION.md` (MAJOR section only)

### 2-3. `tdd-guard.sh`
- Enforced when new test added to template `tests/`
- Same philosophy as your-harness `tdd-guard.sh`, different scope only

## 3. Tests (`tests/`)

### 3-1. `test_schema_validity.py`
Self-validation for all `docs/templates/_schema/*.json`.

```python
import json, jsonschema
from pathlib import Path

def test_all_schemas_self_validate():
    schema_dir = Path("docs/templates/_schema")
    for schema_file in schema_dir.glob("*.schema.json"):
        schema = json.load(open(schema_file))
        # Validate JSON Schema itself (Draft 2020-12)
        jsonschema.Draft202012Validator.check_schema(schema)
```

### 3-2. `test_link_integrity.py`
Verify resolve for all markdown links and `@import` references.

```python
import re
from pathlib import Path

def test_all_links_resolve():
    md_files = list(Path("docs").rglob("*.md"))
    md_files += list(Path("applications").rglob("*.md") if Path("applications").exists() else [])

    pattern = re.compile(r'\[.*?\]\(([^)]+)\)')
    broken = []
    for md in md_files:
        content = md.read_text()
        for match in pattern.finditer(content):
            link = match.group(1).split("#")[0]
            if link.startswith(("http://", "https://", "mailto:")): continue
            target = (md.parent / link).resolve()
            if not target.exists():
                broken.append((str(md), link))
    assert not broken, f"Broken links: {broken[:10]}"
```

### 3-3. `test_hook_executability.py`
Syntax + permissions for all `.claude/hooks/*.sh`.

```python
import subprocess, stat
from pathlib import Path

def test_all_hooks_executable():
    hooks = list(Path(".claude/hooks").glob("*.sh"))
    for hook in hooks:
        mode = hook.stat().st_mode
        assert mode & stat.S_IXUSR, f"{hook} not executable"
        result = subprocess.run(["bash", "-n", str(hook)], capture_output=True)
        assert result.returncode == 0, f"{hook} syntax error: {result.stderr.decode()}"
```

### 3-4. `test_no_korean_in_user_facing.py`
Sanitize verifier — verify zero Korean Hangul traces.

```python
import re
from pathlib import Path

HANGUL = re.compile(r'[가-힯ᄀ-ᇿ㄰-㆏]')

def test_no_korean_in_template():
    # template = English-only public mirror
    md_files = list(Path(".").rglob("*.md"))
    for md in md_files:
        if md.parts[0] in {"archive", ".git"}: continue
        content = md.read_text()
        matches = HANGUL.findall(content)
        assert not matches, f"{md}: Korean detected ({matches[:5]})"
```

### 3-5. `test_phase_doc_completeness.py`
phase-N-*.md must have §0.5 + Exit Criterion + application status table.

```python
import re
from pathlib import Path

def test_all_phase_docs_have_required_sections():
    phase_docs = list(Path("docs/harness-engineering").glob("phase-*.md"))
    for doc in phase_docs:
        content = doc.read_text()
        assert "## 0.5" in content, f"{doc}: missing §0.5 Design Goals"
        assert "Exit Criterion" in content, f"{doc}: missing Exit Criterion"
        assert "applied" in content.lower() or "land" in content.lower(), \
            f"{doc}: missing application status"
```

## 4. Daily Health Check Tool (`tools/template_health.py`)

This §4 is the spec; code lands on both your-harness side and template side in R11.

### 4-1. CLI
```bash
python tools/template_health.py --report <output.json>
python tools/template_health.py --check-link    # link only
python tools/template_health.py --check-schema  # schema only
python tools/template_health.py --check-drift   # drift from your-harness
```

### 4-2. Output schema (per-check)
```json
{
  "checked_at": "2026-05-24T04:00:00Z",
  "template_version": "1.3.0",
  "checks": {
    "link_integrity": { "status": "pass", "broken": [] },
    "schema_validity": { "status": "pass", "failed": [] },
    "hook_executability": { "status": "pass", "failed": [] },
    "korean_sanitize": { "status": "pass", "matches": [] },
    "phase_doc_completeness": { "status": "pass", "missing": [] },
    "role_policy_parity": { "status": "pass", "missing": [] },
    "drift_from_your_harness": { "status": "minor", "behind_by": "v0.0.2" }
  },
  "overall": "pass",
  "next_action": null
}
```

### 4-3. Failure → Action
| Check fail | Action |
|---|---|
| link_integrity | Discord alert + Role B fix PR |
| schema_validity | block release.yml + immediate Role B fix |
| hook_executability | block release.yml + immediate fix |
| korean_sanitize | block release.yml + re-run sanitize |
| phase_doc_completeness | Role B fix advisory |
| role_policy_parity | block promote; regenerate CLAUDE.md / AGENTS.md and repo-profile template baseline |
| drift_from_your_harness.major | Role B performs your-harness → template promote |

## 5. R10 / R11 Separation

| Area | R10 (this doc) | R11 (code land) |
|---|---|---|
| Workflow yaml spec | ✅ | actual `.github/workflows/{validate,release,daily_health}.yml` |
| Test file spec | ✅ | actual `tests/test_*.py` write + pytest run |
| Hook spec | ✅ | actual `.claude/hooks/{pre-commit-verification,pre-edit,tdd-guard}.sh` |
| template_health.py spec | ✅ | actual `tools/template_health.py` code |
| Discord webhook integration | ✅ doc | secrets registration + webhook call code |

## 6. your-harness Application Status (updated R24-T05 2026-05-24)

| Item | Status |
|---|---|
| Template CI workflows | **landed** (template repo `.github/workflows/validate.yml`, `release.yml`, `daily_health.yml` v0.3.0 + pushed externally) |
| Template tests | **landed** (template repo `tests/` 5 files — test_schema_validity, test_link_integrity, test_hook_executability, test_phase_doc_completeness, test_no_korean_in_user_facing) |
| Template hooks | **partially landed** (template repo `.claude/hooks/` v0.3.0 partial + bundle apply) |
| `template_health.py` | **landed** (`tools/fleet_observe/template_health.py` — 8 health checks implemented, R11 land) |
| This CI/test/hook spec | **this R10-T02 land** |

## 7. Exit Criterion

1. 3 workflow (validate / release / daily_health) spec ✓
2. 3 pre-commit hook spec ✓
3. 5 test file spec ✓
4. `template_health.py` CLI + output schema + failure→action mapping ✓
5. R10/R11 separation ✓
6. Public template CI verifies main-agent parity + delegated Codex-first role-policy baseline
7. User review passed

## 8. Next Steps

[`upgrade-runbook.md`](upgrade-runbook.md) — template upgrade procedure from the family (receiving) side.
