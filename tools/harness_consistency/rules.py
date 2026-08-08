from __future__ import annotations

import ast
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

from tools.harness_consistency.models import Finding
from tools.template_assets import AssetManifestError, classify_tracked_files, load_manifest

_REPOSITORIES_INDEX_RE = re.compile(r"\[\s*['\"]repositories['\"]\s*\]")
_EMPTY_ADR_REFERENCES = {"", "null", "(none)", "[]"}


def _project_path(project_root: Path, path: str) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return project_root / candidate


def _relative_location(project_root: Path, path: Path) -> str:
    try:
        return path.relative_to(project_root).as_posix()
    except ValueError:
        return path.as_posix()


def _trim_output(stdout: str, stderr: str, max_lines: int = 5) -> str:
    output = "\n".join(part for part in (stdout, stderr) if part)
    return "\n".join(output.splitlines()[-max_lines:]).strip()


# @spec FR-003
def template_asset_classification(project_root: Path, rule_inputs: dict) -> list[Finding]:
    manifest_path = _project_path(
        project_root,
        rule_inputs.get("manifest_path", "config/template-assets.json"),
    )
    try:
        classify_tracked_files(project_root, load_manifest(manifest_path))
    except (AssetManifestError, OSError, ValueError) as exc:
        return [
            Finding(
                rule_id="R18",
                rule_name="template_asset_classification",
                severity="ERROR",
                message=str(exc),
                location=_relative_location(project_root, manifest_path),
                drift_class=8,
            )
        ]
    return []


def _frontmatter_values(path: Path) -> dict[str, list[str]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    delimiter_indexes = [index for index, line in enumerate(lines) if line.strip() == "---"]
    if len(delimiter_indexes) < 2:
        return {}

    start, end = delimiter_indexes[0], delimiter_indexes[1]
    values: dict[str, list[str]] = {}
    current_key: str | None = None
    for raw_line in lines[start + 1 : end]:
        stripped = raw_line.strip()
        if not stripped:
            continue

        if stripped.startswith("- ") and current_key:
            values.setdefault(current_key, []).append(stripped.removeprefix("- ").strip())
            continue

        if ":" not in stripped:
            current_key = None
            continue

        key, value = stripped.split(":", 1)
        current_key = key.strip()
        values.setdefault(current_key, [])
        value = value.strip()
        if value:
            values[current_key].append(value)
    return values


def _frontmatter_status(path: Path) -> str | None:
    lines = path.read_text(encoding="utf-8").splitlines()
    delimiter_indexes = [index for index, line in enumerate(lines) if line.strip() == "---"]
    if len(delimiter_indexes) < 2:
        return None

    start, end = delimiter_indexes[0], delimiter_indexes[1]
    for line in lines[start + 1 : end]:
        stripped = line.strip()
        if not stripped.startswith("status:"):
            continue
        value = stripped.removeprefix("status:").strip()
        if not value:
            return None
        return value.split()[0]
    return None


def adr_status_enum(project_root: Path, rule_inputs: dict) -> list[Finding]:
    schema_path = _project_path(project_root, rule_inputs["enum_schema"])
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    allowed_values = schema.get(rule_inputs["enum_key"])
    if not allowed_values:
        return [
            Finding(
                rule_id="R5",
                rule_name="adr_status_enum",
                severity="ERROR",
                message=f"status enum source missing: {rule_inputs['enum_key']}",
                location=_relative_location(project_root, schema_path),
                drift_class=3,
            )
        ]
    allowed = set(allowed_values)

    findings: list[Finding] = []
    for adr_path in sorted(project_root.glob(rule_inputs["adr_glob"])):
        status = _frontmatter_status(adr_path)
        if status in allowed:
            continue

        display_status = status if status else "missing"
        relpath = _relative_location(project_root, adr_path)
        findings.append(
            Finding(
                rule_id="R5",
                rule_name="adr_status_enum",
                severity="ERROR",
                message=f"ADR status is not in enum: {display_status}",
                location=f"{relpath}: {display_status}",
                drift_class=3,
            )
        )
    return findings


def context_path_references(project_root: Path, rule_inputs: dict) -> list[Finding]:
    script_input = rule_inputs["script"]
    script = _project_path(project_root, script_input)
    script_arg = str(script if Path(script_input).is_absolute() else Path(script_input))
    proc = subprocess.run(
        [sys.executable, script_arg, *rule_inputs.get("args", [])],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode == 0:
        return []

    message = _trim_output(proc.stdout, proc.stderr) or f"command exited with {proc.returncode}"
    return [
        Finding(
            rule_id="R2",
            rule_name="context_path_references",
            severity="ERROR",
            message=message,
            location=_relative_location(project_root, script),
            drift_class=1,
        )
    ]


def single_family_source(project_root: Path, rule_inputs: dict) -> list[Finding]:
    required_symbol = rule_inputs["required_symbol"]
    findings: list[Finding] = []
    for source_file in rule_inputs["source_files"]:
        path = _project_path(project_root, source_file)
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        if required_symbol in text:
            continue

        findings.append(
            Finding(
                rule_id="R3",
                rule_name="single_family_source",
                severity="ERROR",
                message=f"Family source does not use required symbol: {required_symbol}",
                location=_relative_location(project_root, path),
                drift_class=2,
            )
        )
    return findings


def _is_catalog_loader_usage_skipped(
    relpath: str,
    path: Path,
    exclude_substrings: list[str],
) -> bool:
    if any(excluded in relpath for excluded in exclude_substrings):
        return True
    if "tests" in path.parts:
        return True
    return path.name.startswith("test_")


def catalog_loader_usage(project_root: Path, rule_inputs: dict) -> list[Finding]:
    findings: list[Finding] = []
    exclude_substrings = rule_inputs.get("exclude_substrings", [])
    for scan_dir in rule_inputs["scan_dirs"]:
        root = _project_path(project_root, scan_dir)
        if not root.exists():
            continue

        for path in sorted(root.rglob("*.py")):
            relpath = _relative_location(project_root, path)
            if _is_catalog_loader_usage_skipped(relpath, path, exclude_substrings):
                continue

            text = path.read_text(encoding="utf-8")
            if not _REPOSITORIES_INDEX_RE.search(text) or "load_catalog" in text:
                continue

            findings.append(
                Finding(
                    rule_id="R4",
                    rule_name="catalog_loader_usage",
                    severity="ERROR",
                    message='Catalog ["repositories"] access does not use load_catalog',
                    location=relpath,
                    drift_class=2,
                )
            )
    return findings


def _adr_reference_tokens(values: list[str]) -> list[str]:
    tokens: list[str] = []
    for raw_value in values:
        value = raw_value.strip()
        if value.lower() in _EMPTY_ADR_REFERENCES:
            continue
        if value.startswith("[") and value.endswith("]"):
            value = value[1:-1]

        for part in value.split(","):
            token = part.strip()
            if token.startswith("- "):
                token = token.removeprefix("- ").strip()
            token = token.strip("[]").strip().strip("'\"")
            token = Path(token).name
            if token.endswith(".md"):
                token = token.removesuffix(".md")
            if token.lower() in _EMPTY_ADR_REFERENCES:
                continue
            if token:
                tokens.append(token)
    return tokens


def _resolve_adr_targets(values: list[str], existing_stems: set[str]) -> tuple[set[str], list[str]]:
    resolved: set[str] = set()
    dangling: list[str] = []
    for token in _adr_reference_tokens(values):
        matches = sorted(stem for stem in existing_stems if stem.startswith(token))
        if not matches:
            dangling.append(token)
            continue
        resolved.update(matches)
    return resolved, dangling


def adr_supersession_graph(project_root: Path, rule_inputs: dict) -> list[Finding]:
    adr_paths = sorted(project_root.glob(rule_inputs["adr_glob"]))
    existing_stems = {path.stem for path in adr_paths}
    frontmatters = {path.stem: _frontmatter_values(path) for path in adr_paths}
    path_by_stem = {path.stem: path for path in adr_paths}

    supersedes: dict[str, set[str]] = {}
    superseded_by: dict[str, set[str]] = {}
    dangling_supersedes: dict[str, list[str]] = {}
    for stem, values in frontmatters.items():
        supersedes[stem], dangling_supersedes[stem] = _resolve_adr_targets(
            values.get("supersedes", []),
            existing_stems,
        )
        superseded_by[stem], _ = _resolve_adr_targets(
            values.get("superseded_by", []),
            existing_stems,
        )

    findings: list[Finding] = []
    for stem, dangling_targets in sorted(dangling_supersedes.items()):
        relpath = _relative_location(project_root, path_by_stem[stem])
        for target in dangling_targets:
            findings.append(
                Finding(
                    rule_id="R6",
                    rule_name="adr_supersession_graph",
                    severity="ERROR",
                    message=f"ADR supersedes missing target: {target}",
                    location=f"{relpath}: supersedes {target}",
                    drift_class=3,
                )
            )

    for stem, target_stems in sorted(supersedes.items()):
        relpath = _relative_location(project_root, path_by_stem[stem])
        for target_stem in sorted(target_stems):
            if stem in superseded_by.get(target_stem, set()):
                continue
            findings.append(
                Finding(
                    rule_id="R6",
                    rule_name="adr_supersession_graph",
                    severity="ERROR",
                    message="ADR supersession missing reciprocal superseded_by",
                    location=f"{relpath}: supersedes {target_stem}",
                    drift_class=3,
                )
            )

    for stem, values in sorted(frontmatters.items()):
        statuses = values.get("status", [])
        status = statuses[0].split()[0].lower() if statuses else ""
        if status != "accepted" or not superseded_by.get(stem):
            continue
        relpath = _relative_location(project_root, path_by_stem[stem])
        findings.append(
            Finding(
                rule_id="R6",
                rule_name="adr_supersession_graph",
                severity="ERROR",
                message="ADR is accepted but has superseded_by",
                location=relpath,
                drift_class=3,
            )
        )
    return findings


def architecture_contract(project_root: Path, rule_inputs: dict) -> list[Finding]:
    module = rule_inputs["module"]
    subcommand = rule_inputs["subcommand"]
    proc = subprocess.run(
        [sys.executable, "-m", module, subcommand],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode == 0:
        return []

    message = _trim_output(proc.stdout, proc.stderr) or f"command exited with {proc.returncode}"
    return [
        Finding(
            rule_id="R13",
            rule_name="architecture_contract",
            severity="ERROR",
            message=message,
            location=f"{module} {subcommand}",
            drift_class=6,
        )
    ]


def settings_dual_fire_dedup(project_root: Path, rule_inputs: dict) -> list[Finding]:
    pairs: dict[tuple[str, str], set[str]] = {}

    for settings_file in rule_inputs["settings_files"]:
        path = _project_path(project_root, settings_file)
        if not path.exists():
            continue

        relpath = _relative_location(project_root, path)
        settings = json.loads(path.read_text(encoding="utf-8"))
        for event, hook_groups in settings.get("hooks", {}).items():
            for hook_group in hook_groups:
                for hook in hook_group.get("hooks", []):
                    command = hook.get("command")
                    if not command:
                        continue
                    pairs.setdefault((event, command), set()).add(relpath)

    findings: list[Finding] = []
    for (event, command), files in sorted(pairs.items()):
        if len(files) <= 1:
            continue

        file_list = ", ".join(sorted(files))
        findings.append(
            Finding(
                rule_id="R10",
                rule_name="settings_dual_fire_dedup",
                severity="ERROR",
                message=f"Hook command is registered in multiple settings files: {command}",
                location=f"{event}: {command} ({file_list})",
                drift_class=4,
            )
        )
    return findings


def _python_docstring_lines(text: str) -> set[int]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return set()

    docstring_lines: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not node.body:
            continue
        first_statement = node.body[0]
        if not isinstance(first_statement, ast.Expr):
            continue
        if not isinstance(first_statement.value, ast.Constant):
            continue
        if not isinstance(first_statement.value.value, str):
            continue
        start = first_statement.lineno
        end = getattr(first_statement, "end_lineno", start)
        docstring_lines.update(range(start, end + 1))
    return docstring_lines


def _removed_symbol_search_lines(path: Path, text: str) -> list[str]:
    docstring_lines = _python_docstring_lines(text) if path.suffix == ".py" else set()
    search_lines: list[str] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if lineno in docstring_lines:
            continue
        if line.lstrip().startswith("#"):
            continue
        search_lines.append(line)
    return search_lines


def _line_contains_removed_symbol(line: str, symbol: str) -> bool:
    if symbol.startswith("class "):
        class_name = re.escape(symbol.removeprefix("class ").strip())
        return re.search(rf"^\s*class\s+{class_name}\b", line) is not None
    return symbol in line


def removed_symbol_references(project_root: Path, rule_inputs: dict) -> list[Finding]:
    findings: list[Finding] = []
    allowed_path_substrings = rule_inputs.get("allowed_path_substrings", [])
    retired_symbols = rule_inputs.get("retired_symbols", [])

    for scan_dir in rule_inputs["scan_dirs"]:
        root = _project_path(project_root, scan_dir)
        if not root.exists():
            continue

        for file_glob in rule_inputs["file_globs"]:
            for path in sorted(root.rglob(file_glob)):
                if not path.is_file():
                    continue

                relpath = _relative_location(project_root, path)
                if any(allowed in relpath for allowed in allowed_path_substrings):
                    continue
                if "tests" in path.parts or path.name.startswith("test_"):
                    continue

                text = path.read_text(encoding="utf-8")
                search_lines = _removed_symbol_search_lines(path, text)
                for symbol in retired_symbols:
                    symbol_found = any(
                        _line_contains_removed_symbol(line, symbol) for line in search_lines
                    )
                    if not symbol_found:
                        continue
                    findings.append(
                        Finding(
                            rule_id="R1",
                            rule_name="removed_symbol_references",
                            severity="ERROR",
                            message=f"Retired symbol reference found: {symbol}",
                            location=f"{relpath}: {symbol}",
                            drift_class=1,
                        )
                    )
    return findings


def hook_file_reachability(project_root: Path, rule_inputs: dict) -> list[Finding]:
    hooks_root = _project_path(project_root, rule_inputs["hooks_dir"])
    if not hooks_root.exists():
        return []

    archive_exclude = rule_inputs.get("archive_exclude", "")
    candidates: set[Path] = set()
    for file_glob in rule_inputs["file_globs"]:
        for path in hooks_root.rglob(file_glob):
            if not path.is_file():
                continue
            relpath = _relative_location(project_root, path)
            if archive_exclude and archive_exclude in relpath:
                continue
            if "__pycache__" in relpath:
                continue
            candidates.add(path)

    settings_text = ""
    for settings_file in rule_inputs["settings_files"]:
        path = _project_path(project_root, settings_file)
        if path.exists():
            settings_text += "\n" + path.read_text(encoding="utf-8")

    reachable = {path for path in candidates if path.name in settings_text}
    hook_texts = {path: path.read_text(encoding="utf-8") for path in candidates}

    changed = True
    while changed:
        changed = False
        reachable_text = "\n".join(hook_texts[path] for path in sorted(reachable))
        for path in candidates - reachable:
            if path.name not in reachable_text:
                continue
            reachable.add(path)
            changed = True

    manual_trigger_allowlist = set(rule_inputs.get("manual_trigger_allowlist", []))
    findings: list[Finding] = []
    for path in sorted(candidates - reachable):
        relpath = _relative_location(project_root, path)
        if relpath in manual_trigger_allowlist:
            continue
        findings.append(
            Finding(
                rule_id="R8",
                rule_name="hook_file_reachability",
                severity="ERROR",
                message=f"Unreachable/orphan hook file: {path.name}",
                location=relpath,
                drift_class=4,
            )
        )
    return findings


def wired_gate_liveness(project_root: Path, rule_inputs: dict) -> list[Finding]:
    findings: list[Finding] = []
    for gate in rule_inputs["gates"]:
        requires_path = gate["requires_path"]
        if _project_path(project_root, requires_path).exists():
            continue

        hook = gate["hook"]
        findings.append(
            Finding(
                rule_id="R12",
                rule_name="wired_gate_liveness",
                severity="ERROR",
                message=f"gate {hook} BLOCK path depends on missing {requires_path}",
                location=f"{hook} -> {requires_path}",
                drift_class=1,
            )
        )
    return findings


def archived_source_phase_doc(project_root: Path, rule_inputs: dict) -> list[Finding]:
    findings: list[Finding] = []
    settings_text_by_file: dict[Path, str] = {}
    for settings_file in rule_inputs["settings_files"]:
        path = _project_path(project_root, settings_file)
        if path.exists():
            settings_text_by_file[path] = path.read_text(encoding="utf-8")

    archive_dir = _project_path(project_root, rule_inputs["hook_archive_dir"])
    if archive_dir.exists():
        for archive_file in sorted(path for path in archive_dir.iterdir() if path.is_file()):
            basename = archive_file.name
            for settings_file, settings_text in sorted(settings_text_by_file.items()):
                if basename not in settings_text:
                    continue
                findings.append(
                    Finding(
                        rule_id="R14",
                        rule_name="archived_source_phase_doc",
                        severity="ERROR",
                        message=f"Archived hook is wired live again: {basename}",
                        location=(
                            f"{_relative_location(project_root, archive_file)} wired in "
                            f"{_relative_location(project_root, settings_file)}"
                        ),
                        drift_class=6,
                    )
                )

    archived_hook_names = [name.lower() for name in rule_inputs["archived_hook_names"]]
    live_claim_keywords = [keyword.lower() for keyword in rule_inputs["live_claim_keywords"]]
    exempt_token = rule_inputs["exempt_token"].lower()
    for phase_doc_glob in rule_inputs["phase_doc_globs"]:
        for path in sorted(project_root.glob(phase_doc_glob)):
            if not path.is_file():
                continue
            relpath = _relative_location(project_root, path)
            for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                lower_line = line.lower()
                if exempt_token in lower_line:
                    continue
                if not any(hook_name in lower_line for hook_name in archived_hook_names):
                    continue
                if not any(keyword in lower_line for keyword in live_claim_keywords):
                    continue
                findings.append(
                    Finding(
                        rule_id="R14",
                        rule_name="archived_source_phase_doc",
                        severity="ERROR",
                        message="Phase doc claims archived hook is live",
                        location=f"{relpath}:{lineno}",
                        drift_class=6,
                    )
                )
    return findings


def _find_schema_constraint(value: object, schema_field: str, schema_key: str) -> int | None:
    if isinstance(value, dict):
        field_value = value.get(schema_field)
        if isinstance(field_value, dict) and schema_key in field_value:
            return int(field_value[schema_key])

        for child_value in value.values():
            result = _find_schema_constraint(child_value, schema_field, schema_key)
            if result is not None:
                return result
        return None

    if isinstance(value, list):
        for child_value in value:
            result = _find_schema_constraint(child_value, schema_field, schema_key)
            if result is not None:
                return result
    return None


def code_schema_constraint_agreement(project_root: Path, rule_inputs: dict) -> list[Finding]:
    findings: list[Finding] = []
    for pair in rule_inputs["pairs"]:
        python_path = _project_path(project_root, pair["python_file"])
        schema_path = _project_path(project_root, pair["schema_file"])
        rel_python_path = _relative_location(project_root, python_path)
        rel_schema_path = _relative_location(project_root, schema_path)

        python_text = python_path.read_text(encoding="utf-8") if python_path.exists() else ""
        match = re.search(pair["python_regex"], python_text)
        if match is None:
            findings.append(
                Finding(
                    rule_id="R15",
                    rule_name="code_schema_constraint_agreement",
                    severity="ERROR",
                    message=f"{rel_python_path} constraint not found",
                    location=rel_python_path,
                    drift_class=7,
                )
            )
            continue
        python_value = int(match.group(1))

        schema = json.loads(schema_path.read_text(encoding="utf-8")) if schema_path.exists() else {}
        schema_value = _find_schema_constraint(
            schema,
            pair["schema_field"],
            pair["schema_key"],
        )
        if schema_value is None:
            findings.append(
                Finding(
                    rule_id="R15",
                    rule_name="code_schema_constraint_agreement",
                    severity="ERROR",
                    message=(
                        f"{rel_schema_path} constraint not found: "
                        f"{pair['schema_field']}.{pair['schema_key']}"
                    ),
                    location=rel_schema_path,
                    drift_class=7,
                )
            )
            continue

        if python_value == schema_value:
            continue
        findings.append(
            Finding(
                rule_id="R15",
                rule_name="code_schema_constraint_agreement",
                severity="ERROR",
                message=(
                    f"{rel_python_path} constant {python_value} vs {rel_schema_path} "
                    f"{pair['schema_field']}.{pair['schema_key']} {schema_value} disagree"
                ),
                location=f"{rel_python_path} -> {rel_schema_path}",
                drift_class=7,
            )
        )
    return findings


def adr_artifact_present(project_root: Path, rule_inputs: dict) -> list[Finding]:
    findings: list[Finding] = []
    for adr_prefix, artifact_path in sorted(rule_inputs["artifact_map"].items()):
        path = _project_path(project_root, artifact_path)
        if path.exists():
            continue
        findings.append(
            Finding(
                rule_id="R7",
                rule_name="adr_artifact_present",
                severity="WARN",
                message=f"accepted ADR {adr_prefix} artifact missing {artifact_path}",
                location=artifact_path,
                drift_class=3,
            )
        )
    return findings


def hook_tier_declaration(project_root: Path, rule_inputs: dict) -> list[Finding]:
    hooks_root = _project_path(project_root, rule_inputs["hooks_dir"])
    marker_prefix = rule_inputs["marker_prefix"]
    findings: list[Finding] = []

    for hook_basename, expected_tier in sorted(rule_inputs["expected_tiers"].items()):
        path = hooks_root / hook_basename
        if not path.exists():
            continue

        declared_tiers: list[str] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if marker_prefix not in line or "=" not in line:
                continue
            match = re.search(r"=\s*(['\"])(.*?)\1", line)
            if match:
                declared_tiers.append(match.group(2))

        if expected_tier in declared_tiers:
            continue

        tier_display = ", ".join(declared_tiers) if declared_tiers else "none"
        findings.append(
            Finding(
                rule_id="R9",
                rule_name="hook_tier_declaration",
                severity="WARN",
                message=(
                    f"declared tier(s) {tier_display} do not include expected {expected_tier}"
                ),
                location=hook_basename,
                drift_class=4,
            )
        )
    return findings


def _marked_block(text: str, marker_begin: str, marker_end: str) -> str:
    begin_index = text.find(marker_begin)
    if begin_index == -1:
        return text

    content_start = begin_index + len(marker_begin)
    end_index = text.find(marker_end, content_start)
    if end_index == -1:
        return text
    return text[content_start:end_index]


def _normalized_generated_block(text: str) -> str:
    lines = [line.rstrip() for line in text.splitlines()]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines)


def generated_marker_rerender(project_root: Path, rule_inputs: dict) -> list[Finding]:
    findings: list[Finding] = []
    for surface in rule_inputs["surfaces"]:
        source = _project_path(project_root, surface["source"])
        if surface.get("skip_if_source_absent") and not source.exists():
            continue

        rel_file = surface["file"]
        try:
            proc = subprocess.run(
                [sys.executable, "-m", surface["render_module"], *surface["render_args"]],
                cwd=project_root,
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError as exc:
            findings.append(
                Finding(
                    rule_id="R11",
                    rule_name="generated_marker_rerender",
                    severity="WARN",
                    message=f"render failed: {exc}",
                    location=rel_file,
                    drift_class=5,
                )
            )
            continue

        if proc.returncode != 0:
            message = (
                _trim_output(proc.stdout, proc.stderr)
                or f"command exited with {proc.returncode}"
            )
            findings.append(
                Finding(
                    rule_id="R11",
                    rule_name="generated_marker_rerender",
                    severity="WARN",
                    message=f"render failed: {message}",
                    location=rel_file,
                    drift_class=5,
                )
            )
            continue

        committed_path = _project_path(project_root, rel_file)
        if not committed_path.exists():
            findings.append(
                Finding(
                    rule_id="R11",
                    rule_name="generated_marker_rerender",
                    severity="WARN",
                    message="committed generated surface missing",
                    location=rel_file,
                    drift_class=5,
                )
            )
            continue

        marker_begin = surface["marker_begin"]
        marker_end = surface["marker_end"]
        committed_block = _normalized_generated_block(
            _marked_block(committed_path.read_text(encoding="utf-8"), marker_begin, marker_end)
        )
        rendered_block = _normalized_generated_block(
            _marked_block(proc.stdout, marker_begin, marker_end)
        )
        if committed_block == rendered_block:
            continue

        findings.append(
            Finding(
                rule_id="R11",
                rule_name="generated_marker_rerender",
                severity="WARN",
                message="generated block drifted from a fresh render",
                location=rel_file,
                drift_class=5,
            )
        )
    return findings


def agent_surface_contract(project_root: Path, rule_inputs: dict) -> list[Finding]:
    """R17: declared-must-exist / registered-must-run for 6 agent surface classes.

    Sub-checks:
    1. cited_paths:    backtick-quoted slashed paths in CLAUDE.md must exist on disk unless
                       explicitly declared as generated after bootstrap.
    2. hook_scripts:   .sh/.py tokens in hook commands must exist; bare (no interpreter
                       prefix) scripts must also be executable.
    3. agents_front:   .claude/agents/*.md (excluding README*/INDEX*/RECOVERY*) must
                       start with --- frontmatter containing 'name:'.
    4. skills_struct:  each directory under every configured skill root must contain SKILL.md.
    5. mirror_contract: if AGENTS.md exists, the mirror_heading must appear in both
                        CLAUDE.md and AGENTS.md.
    6. marker_pairs:   marker_surfaces files must have equal counts of
                       {memory_marker}:start and {memory_marker}:end; 0/0 is a finding.
    """
    findings: list[Finding] = []

    # ---- 1. cited_paths -------------------------------------------------------
    claude_md_rel = rule_inputs.get("claude_md", "CLAUDE.md")
    claude_md_path = project_root / claude_md_rel
    if claude_md_path.exists():
        content = claude_md_path.read_text(encoding="utf-8")
        generated_cited_paths = set(rule_inputs.get("generated_cited_paths", []))
        # Match backtick-quoted tokens that contain at least one slash and end in a
        # recognised extension. Exclude placeholders containing {}, <>, or a
        # leading slash (absolute paths are not project-relative citations).
        _CITED_PATH_RE = re.compile(
            r"`([^`]*?/[^`]*?\.(?:md|yaml|yml|json|sh|py|toml))`"
        )
        for m in _CITED_PATH_RE.finditer(content):
            token = m.group(1)
            # Skip inline commands (contain spaces) — only bare paths, not commands
            if " " in token:
                continue
            # Skip placeholders
            if any(c in token for c in ("{", "}", "<", ">")):
                continue
            # Skip glob patterns — documentation globs describe file sets, not literal paths
            if any(c in token for c in ("*", "?")):
                continue
            if token.startswith("/"):
                continue
            if token in generated_cited_paths:
                continue
            target = project_root / token
            if not target.exists():
                findings.append(
                    Finding(
                        rule_id="R17",
                        rule_name="agent_surface_contract",
                        severity="ERROR",
                        message=(
                            f"cited_paths: {token} referenced in {claude_md_rel} does not exist"
                        ),
                        location=claude_md_rel,
                        drift_class=8,
                    )
                )

    # ---- 2. hook_scripts ------------------------------------------------------
    _INTERPRETERS = {"bash", "sh", "zsh", "python", "python3", "uv"}
    _SCRIPT_TOKEN_RE = re.compile(r"\S+\.(?:sh|py)\b")
    settings_files = rule_inputs.get("settings_files", [
        ".claude/settings.json",
        ".claude/settings.local.json",
    ])
    for sf_rel in settings_files:
        sf_path = project_root / sf_rel
        if not sf_path.exists():
            continue
        try:
            sf_data = json.loads(sf_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        hooks_block = sf_data.get("hooks", {})
        # Flatten all command strings from hooks block (dict of lists of hook dicts)
        commands: list[str] = []
        if isinstance(hooks_block, dict):
            for _event, entries in hooks_block.items():
                if not isinstance(entries, list):
                    continue
                for entry in entries:
                    if not isinstance(entry, dict):
                        continue
                    # entries can be list-of-hook-groups or direct hook dict
                    sub_hooks = entry.get("hooks", [entry])
                    if not isinstance(sub_hooks, list):
                        sub_hooks = [entry]
                    for h in sub_hooks:
                        if not isinstance(h, dict):
                            continue
                        cmd = h.get("command", "")
                        if cmd:
                            commands.append(cmd)
        for cmd in commands:
            # Resolve $CLAUDE_PROJECT_DIR or ${CLAUDE_PROJECT_DIR}
            cmd_resolved = cmd.replace("$CLAUDE_PROJECT_DIR", str(project_root))
            cmd_resolved = cmd_resolved.replace("${CLAUDE_PROJECT_DIR}", str(project_root))
            tokens = shlex.split(cmd_resolved)
            if not tokens:
                continue
            first_token = tokens[0]
            has_interpreter = first_token in _INTERPRETERS
            # Find all .sh/.py tokens in the command
            for token in tokens:
                if not _SCRIPT_TOKEN_RE.search(token):
                    continue
                # Strip surrounding quotes that may come from shell quoting
                clean_token = token.strip("\"'")
                # Resolve path: if relative, relative to project_root
                script_path = Path(clean_token)
                if not script_path.is_absolute():
                    script_path = project_root / clean_token
                if not script_path.exists():
                    findings.append(
                        Finding(
                            rule_id="R17",
                            rule_name="agent_surface_contract",
                            severity="ERROR",
                            message=(
                                f"hook_scripts: command references missing script {clean_token} "
                                f"(in {sf_rel})"
                            ),
                            location=sf_rel,
                            drift_class=8,
                        )
                    )
                elif not has_interpreter and not os.access(script_path, os.X_OK):
                    findings.append(
                        Finding(
                            rule_id="R17",
                            rule_name="agent_surface_contract",
                            severity="ERROR",
                            message=(
                                f"hook_scripts: script {clean_token} exists but lacks exec bit "
                                f"(bare command, no interpreter prefix) in {sf_rel}"
                            ),
                            location=sf_rel,
                            drift_class=8,
                        )
                    )

    # ---- 3. agents_frontmatter ------------------------------------------------
    agents_dir_rel = rule_inputs.get("agents_dir", ".claude/agents")
    agents_dir = project_root / agents_dir_rel
    _EXCLUDE_PREFIXES = ("README", "INDEX", "RECOVERY")
    if agents_dir.is_dir():
        for agent_file in sorted(agents_dir.glob("*.md")):
            if agent_file.name.startswith(_EXCLUDE_PREFIXES):
                continue
            lines = agent_file.read_text(encoding="utf-8").splitlines()
            rel = _relative_location(project_root, agent_file)
            # Must start with --- and have a closing --- with 'name:' inside
            if not lines or lines[0].strip() != "---":
                findings.append(
                    Finding(
                        rule_id="R17",
                        rule_name="agent_surface_contract",
                        severity="ERROR",
                        message=(
                            f"agents_frontmatter: {agent_file.name} missing opening --- frontmatter"
                        ),
                        location=rel,
                        drift_class=8,
                    )
                )
                continue
            # Find closing ---
            close_idx = None
            for i, ln in enumerate(lines[1:], 1):
                if ln.strip() == "---":
                    close_idx = i
                    break
            if close_idx is None:
                findings.append(
                    Finding(
                        rule_id="R17",
                        rule_name="agent_surface_contract",
                        severity="ERROR",
                        message=(
                            f"agents_frontmatter: {agent_file.name} frontmatter block not closed"
                        ),
                        location=rel,
                        drift_class=8,
                    )
                )
                continue
            fm_block = "\n".join(lines[1:close_idx])
            if not re.search(r"^name\s*:", fm_block, re.MULTILINE):
                findings.append(
                    Finding(
                        rule_id="R17",
                        rule_name="agent_surface_contract",
                        severity="ERROR",
                        message=(
                            f"agents_frontmatter: {agent_file.name} frontmatter "
                            f"missing 'name:' field"
                        ),
                        location=rel,
                        drift_class=8,
                    )
                )

    # ---- 4. skills_structure --------------------------------------------------
    skills_dirs_rel = rule_inputs.get("skills_dirs")
    if skills_dirs_rel is None:
        skills_dirs_rel = [rule_inputs.get("skills_dir", ".claude/skills")]
    for skills_dir_rel in skills_dirs_rel:
        skills_dir = project_root / skills_dir_rel
        if not skills_dir.is_dir():
            continue
        for skill_subdir in sorted(skills_dir.iterdir()):
            if not skill_subdir.is_dir():
                continue
            skill_md = skill_subdir / "SKILL.md"
            if not skill_md.exists():
                rel = _relative_location(project_root, skill_subdir)
                findings.append(
                    Finding(
                        rule_id="R17",
                        rule_name="agent_surface_contract",
                        severity="ERROR",
                        message=(
                            f"skills_structure: skill directory {skill_subdir.name} has no SKILL.md"
                        ),
                        location=rel,
                        drift_class=8,
                    )
                )

    # ---- 5. mirror_contract ---------------------------------------------------
    agents_md_rel = rule_inputs.get("agents_md", "AGENTS.md")
    agents_md_path = project_root / agents_md_rel
    mirror_heading = rule_inputs.get("mirror_heading", "## Memory (DB-canonical")
    if agents_md_path.exists() and claude_md_path.exists():
        claude_text = claude_md_path.read_text(encoding="utf-8")
        agents_text = agents_md_path.read_text(encoding="utf-8")
        if mirror_heading in claude_text and mirror_heading not in agents_text:
            findings.append(
                Finding(
                    rule_id="R17",
                    rule_name="agent_surface_contract",
                    severity="ERROR",
                    message=(
                        f"mirror_contract: '{mirror_heading}' present in {claude_md_rel} "
                        f"but missing from AGENTS.md"
                    ),
                    location=agents_md_rel,
                    drift_class=8,
                )
            )

    # ---- 6. marker_pairs ------------------------------------------------------
    memory_marker = rule_inputs.get("memory_marker", "mir:generated")
    marker_start = f"{memory_marker}:start"
    marker_end = f"{memory_marker}:end"
    marker_surfaces = rule_inputs.get("marker_surfaces", [
        "docs/memory-map.md",
        "tasks/lessons.md",
    ])
    for surface_rel in marker_surfaces:
        surface_path = project_root / surface_rel
        if not surface_path.exists():
            # absent optional surface is OK (lessons.md may not exist in new repos)
            continue
        text = surface_path.read_text(encoding="utf-8")
        count_start = text.count(marker_start)
        count_end = text.count(marker_end)
        if count_start == 0 and count_end == 0:
            findings.append(
                Finding(
                    rule_id="R17",
                    rule_name="agent_surface_contract",
                    severity="ERROR",
                    message=(
                        f"marker_pairs: {surface_rel} has no {memory_marker} markers "
                        f"(expected at least one start/end pair)"
                    ),
                    location=surface_rel,
                    drift_class=8,
                )
            )
        elif count_start != count_end:
            findings.append(
                Finding(
                    rule_id="R17",
                    rule_name="agent_surface_contract",
                    severity="ERROR",
                    message=(
                        f"marker_pairs: {surface_rel} has unbalanced {memory_marker} markers "
                        f"(start={count_start}, end={count_end})"
                    ),
                    location=surface_rel,
                    drift_class=8,
                )
            )

    return findings


RULES = {
    "adr_artifact_present": adr_artifact_present,
    "adr_status_enum": adr_status_enum,
    "architecture_contract": architecture_contract,
    "adr_supersession_graph": adr_supersession_graph,
    "catalog_loader_usage": catalog_loader_usage,
    "archived_source_phase_doc": archived_source_phase_doc,
    "code_schema_constraint_agreement": code_schema_constraint_agreement,
    "context_path_references": context_path_references,
    "generated_marker_rerender": generated_marker_rerender,
    "hook_file_reachability": hook_file_reachability,
    "hook_tier_declaration": hook_tier_declaration,
    "removed_symbol_references": removed_symbol_references,
    "settings_dual_fire_dedup": settings_dual_fire_dedup,
    "single_family_source": single_family_source,
    "wired_gate_liveness": wired_gate_liveness,
    "template_asset_classification": template_asset_classification,
    "agent_surface_contract": agent_surface_contract,
}
