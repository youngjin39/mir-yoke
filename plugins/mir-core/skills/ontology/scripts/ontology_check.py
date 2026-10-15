"""Read-only semantic contract and project mapping checks; Python 3.9, stdlib only."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath, PureWindowsPath

DEFAULT_CONTRACT = Path(__file__).resolve().parent.parent / "references/common-contract.json"
NUMBER = r"(?:0|[1-9][0-9]*)"
CORE = rf"{NUMBER}\.{NUMBER}\.{NUMBER}"
SEMVER = re.compile(
    rf"({NUMBER})\.({NUMBER})\.({NUMBER})"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
)
VERSION_RANGE = re.compile(rf">=({CORE}) <({CORE})")
MAPPING_BUDGET = 12288


def version_key(value):
    """SemVer precedence, including numeric prerelease identifiers and build metadata."""
    match = SEMVER.fullmatch(value) if isinstance(value, str) else None
    if not match:
        return None
    prerelease = match[4]
    parts = []
    if prerelease:
        for part in prerelease.split("."):
            if part.isdigit():
                if len(part) > 1 and part.startswith("0"):
                    return None
                parts.append((0, int(part)))
            else:
                parts.append((1, part))
    else:
        parts.append((2, ""))
    return (int(match[1]), int(match[2]), int(match[3]), tuple(parts))


def pointer(base, key):
    return base + "/" + str(key).replace("~", "~0").replace("/", "~1")


class Checker:
    def __init__(self):
        self.errors = []
        self.warnings = []
        self.checked_refs = set()
        self.line_refs = set()

    def error(self, at, message):
        self.errors.append({"pointer": at, "message": message})

    def warn(self, at, message):
        self.warnings.append({"pointer": at, "message": message})

    def object(self, value, at):
        if not isinstance(value, dict):
            self.error(at, "expected an object")
            return {}
        return value

    def array(self, value, at):
        if not isinstance(value, list):
            self.error(at, "expected a list")
            return []
        return value

    def text(self, value, at, message="expected a non-empty string"):
        if not isinstance(value, str) or not value.strip():
            self.error(at, message)
            return False
        return True

    def ref(self, value, at, root):
        self.checked_refs.add(at)
        if not self.text(value, at, "needs a ref"):
            return
        path, separator, name = value.partition("#")
        if re.search(r":\d+$", path):
            self.line_refs.add(at)
        raw_path = re.sub(r":\d+$", "", value.split("#", 1)[0])
        if PurePosixPath(raw_path).is_absolute() or PureWindowsPath(raw_path).is_absolute():
            self.error(at, "absolute ref is not allowed")
            return
        if not raw_path or "\\" in raw_path or PureWindowsPath(raw_path).drive:
            self.error(at, "ref must be repo-relative")
            return
        if ".." in PurePosixPath(raw_path).parts:
            self.error(at, "ref escapes repository: parent traversal is not allowed")
            return
        target = (root / raw_path).resolve()
        try:
            target.relative_to(root)
        except ValueError:
            self.error(at, "ref escapes repository")
            return
        if not target.exists():
            self.error(at, "ref path does not exist")
            return
        if separator and (
            not target.is_file()
            or not resolves_symbol(target.read_text(encoding="utf-8"), name, target.suffix.lower())
        ):
            self.error(at, "symbol anchor not found (check name not found): " + name)
        return target

    def covered_check(self, value, at, root):
        target = self.ref(value, at, root)
        if target is None:
            return
        if not target.is_file():
            self.error(at, "check ref must name a file")
            return
        path = value.split("#", 1)[0]
        line = re.search(r":(\d+)$", path)
        text = target.read_text(encoding="utf-8")
        if line:
            number = int(line[1])
            if number < 1:
                self.error(at, "check line must be positive")
            elif number > len(text.splitlines()):
                self.error(at, "check line exceeds file line count")
        if target.suffix.lower() in (".md", ".txt", ".rst"):
            self.warn(at, "covered needs a repeatable check; a document is not one")

    def refs(self, value, at, root):
        for i, ref in enumerate(self.array(value, at)):
            location = pointer(at, i)
            if isinstance(ref, dict):
                self.ref(ref.get("ref"), pointer(location, "ref"), root)
            else:
                self.ref(ref, location, root)

    def ids(self, contract, key):
        found = set()
        for i, raw in enumerate(self.array(contract.get(key), "/" + key)):
            at = pointer("/" + key, i)
            entry = self.object(raw, at)
            value = entry.get("id")
            if self.text(value, at + "/id"):
                if value in found:
                    self.error(at + "/id", "duplicate id: " + value)
                found.add(value)
        return found

    def contract(self, raw):
        contract = self.object(raw, "")
        if contract.get("schema") != "mir-semantic-contract/v1":
            self.error("/schema", "invalid contract schema")
        if version_key(contract.get("version")) is None:
            self.error("/version", "invalid semver")
        rules = self.ids(contract, "rules")
        concepts = self.ids(contract, "concepts")
        self.ids(contract, "relations")
        self.ids(contract, "error_cases")
        for i, relation in enumerate(self.array(contract.get("relations"), "/relations")):
            if not isinstance(relation, dict):
                continue
            for side in ("from", "to"):
                at = pointer("/relations", i) + "/" + side
                for j, concept in enumerate(self.array(relation.get(side), at)):
                    if not isinstance(concept, str) or concept not in concepts | {"*"}:
                        self.error(pointer(at, j), "unknown endpoint concept")
        for i, case in enumerate(self.array(contract.get("error_cases"), "/error_cases")):
            if not isinstance(case, dict):
                continue
            at = pointer("/error_cases", i) + "/rules"
            for j, rule in enumerate(self.array(case.get("rules"), at)):
                if not isinstance(rule, str) or rule not in rules:
                    self.error(pointer(at, j), "unknown rule")
        axes = self.object(contract.get("axes"), "/axes")
        if not axes:
            self.error("/axes", "axes need non-empty value maps")
        for axis, raw_axis in axes.items():
            at = pointer("/axes", axis)
            axis_object = self.object(raw_axis, at)
            values = axis_object.get("values")
            if not isinstance(values, dict) or not values:
                self.error(at + "/values", "axis needs a non-empty value map")
        spec = self.object(contract.get("mapping"), "/mapping")
        for key in ("required_keys", "knowledge_supply_values"):
            for i, value in enumerate(self.array(spec.get(key), "/mapping/" + key)):
                self.text(value, pointer("/mapping/" + key, i))
        return contract

    def common_relation(self, relation, at, contract, endpoints_required):
        endpoint_rules = {entry["id"]: entry for entry in contract["relations"]}
        common = relation["common"]
        if not isinstance(common, str) or common not in endpoint_rules:
            self.error(at + "/common", "unknown relation")
        elif endpoints_required:
            concept_ids = {entry["id"] for entry in contract["concepts"]}
            for side in ("from", "to"):
                value = relation.get(side)
                allowed = endpoint_rules[common][side]
                values = ["*"] if value == "*" else self.array(value, at + "/" + side)
                if not values:
                    self.error(at + "/" + side, "needs non-empty endpoints")
                for j, endpoint in enumerate(values):
                    if (
                        not isinstance(endpoint, str)
                        or (endpoint not in concept_ids and value != "*")
                        or ("*" not in allowed and endpoint not in allowed)
                    ):
                        self.error(pointer(at + "/" + side, j), "endpoint not allowed")

    def mapping(self, raw, contract, contract_bytes, root):
        mapping = self.object(raw, "")
        for key in contract["mapping"]["required_keys"]:
            if key not in mapping:
                self.error(pointer("", key), "missing required key")
        if mapping.get("schema") != "mir-semantic-mapping/v1":
            self.error("/schema", "invalid mapping schema")
        declaration = self.object(mapping.get("contract"), "/contract")
        if declaration.get("id") != contract.get("contract_id"):
            self.error("/contract/id", "contract id mismatch")
        if version_key(declaration.get("version")) is None:
            self.error("/contract/version", "invalid semver")
        range_text = declaration.get("version_range")
        match = VERSION_RANGE.fullmatch(range_text) if isinstance(range_text, str) else None
        if not match or version_key(match[1]) >= version_key(match[2]):
            self.error("/contract/version_range", "invalid version_range; use >=A.B.C <X.Y.Z")
        elif not version_key(match[1]) <= version_key(contract["version"]) < version_key(match[2]):
            self.error("/contract/version_range", "version mismatch (E10): contract outside range")
        elif version_key(declaration.get("version")) is not None:
            validated = version_key(declaration["version"])
            if not version_key(match[1]) <= validated < version_key(match[2]):
                self.error("/contract/version", "validated version outside its range (E10)")
            elif validated > version_key(contract["version"]):
                self.error(
                    "/contract/version", "validated version is newer than the loaded contract (E10)"
                )
            elif validated < version_key(contract["version"]):
                self.warn(
                    "/contract/version", "validated against an older contract; re-validate (E10)"
                )
        if "sha256" in declaration:
            if declaration["sha256"] != hashlib.sha256(contract_bytes).hexdigest():
                self.warn("/contract/sha256", "contract sha256 differs from loaded file")
        profile = root / ".mir/repo-profile.toml"
        if not profile.is_file():
            self.error("/namespace", "missing Profile: .mir/repo-profile.toml")
        else:
            slug = re.search(
                r'^\s*slug\s*=\s*"([^"\n]+)"\s*(?:#.*)?$',
                profile.read_text(encoding="utf-8"),
                re.MULTILINE,
            )
            if not slug:
                self.error("/namespace", 'Profile needs a slug = "..." key')
            elif mapping.get("namespace") != slug[1]:
                self.error("/namespace", "namespace mismatch with repository Profile slug")
        self.refs(mapping.get("canonical_index"), "/canonical_index", root)
        concepts = self.object(mapping.get("concepts"), "/concepts")
        for concept in contract["concepts"]:
            name = concept["id"]
            at = pointer("/concepts", name)
            if name not in concepts:
                self.error(at, "missing concept: " + name)
                continue
            entry = self.object(concepts[name], at)
            status = entry.get("status")
            if status not in ("mapped", "absent", "not_applicable"):
                self.error(at + "/status", "invalid concept status")
            elif status == "mapped":
                local = self.array(entry.get("local"), at + "/local")
                if not local:
                    self.error(at + "/local", "mapped needs a non-empty local list")
                for i, raw_local in enumerate(local):
                    local_at = pointer(at + "/local", i)
                    item = self.object(raw_local, local_at)
                    self.text(item.get("name"), local_at + "/name")
                    self.ref(item.get("ref"), local_at + "/ref", root)
            else:
                self.text(entry.get("reason"), at + "/reason", "needs a non-empty reason")
        for i, raw_vocab in enumerate(self.array(mapping.get("vocabularies"), "/vocabularies")):
            at = pointer("/vocabularies", i)
            vocab = self.object(raw_vocab, at)
            self.text(vocab.get("name"), at + "/name")
            self.ref(vocab.get("ref"), at + "/ref", root)
            for word, raw_values in self.object(vocab.get("values"), at + "/values").items():
                value_at = pointer(at + "/values", word)
                values = self.object(raw_values, value_at)
                if "local_only" in values:
                    self.text(values["local_only"], value_at + "/local_only")
                    if len(values) != 1:
                        self.error(value_at, "local_only cannot be combined with axes")
                    continue
                if not values:
                    self.error(value_at, "value needs a non-empty axis map")
                for axis, value in values.items():
                    if axis not in contract["axes"]:
                        self.error(pointer(value_at, axis), "unknown axis")
                    elif (
                        not isinstance(value, str) or value not in contract["axes"][axis]["values"]
                    ):
                        self.error(pointer(value_at, axis), "unknown axis value")
        validated = version_key(declaration.get("version"))
        endpoints_required = validated is not None and validated >= version_key("1.1.0")
        for i, raw_relation in enumerate(self.array(mapping.get("relations"), "/relations")):
            at = pointer("/relations", i)
            relation = self.object(raw_relation, at)
            self.text(relation.get("local"), at + "/local", "needs a non-empty local relation")
            if ("common" in relation) == ("local_only" in relation):
                self.error(at, "relation needs either common or local_only")
            elif "common" in relation:
                self.common_relation(relation, at, contract, endpoints_required)
            else:
                self.text(relation["local_only"], at + "/local_only")
            if "ref" in relation:
                self.ref(relation["ref"], at + "/ref", root)
        domain = self.object(mapping.get("domain"), "/domain")
        for key in ("concepts", "relations", "invariants"):
            at = "/domain/" + key
            for i, raw_entry in enumerate(self.array(domain.get(key), at)):
                entry_at = pointer(at, i)
                entry = self.object(raw_entry, entry_at)
                self.ref(entry.get("ref"), entry_at + "/ref", root)
                if key == "relations" and "common" in entry:
                    self.common_relation(entry, entry_at, contract, endpoints_required)
        questions = self.array(mapping.get("questions"), "/questions")
        if not questions:
            self.error("/questions", "at least one question is required")
        elif len(questions) < 3:
            self.warn("/questions", "fewer than three domain questions")
        for i, raw_question in enumerate(questions):
            at = pointer("/questions", i)
            question = self.object(raw_question, at)
            for key in ("id", "question"):
                self.text(question.get(key), at + "/" + key)
            self.refs(question.get("evidence"), at + "/evidence", root)
        case_ids = {case["id"] for case in contract["error_cases"]}
        for i, raw_case in enumerate(self.array(mapping.get("error_cases"), "/error_cases")):
            at = pointer("/error_cases", i)
            case = self.object(raw_case, at)
            case_id = case.get("id")
            if not isinstance(case_id, str) or case_id not in case_ids:
                self.error(at + "/id", "unknown error case")
            status = case.get("status")
            if status not in ("covered", "planned", "not_applicable"):
                self.error(at + "/status", "invalid error case status")
            if status == "covered" and "check" not in case:
                self.error(at + "/check", "covered needs a check ref")
            elif status == "covered":
                self.covered_check(case["check"], at + "/check", root)
            elif "check" in case:
                self.ref(case["check"], at + "/check", root)
        supply = self.object(mapping.get("knowledge_supply"), "/knowledge_supply")
        if supply.get("memory_keeper") not in contract["mapping"]["knowledge_supply_values"]:
            self.error("/knowledge_supply/memory_keeper", "invalid knowledge supply value")
        if (
            supply.get("memory_keeper") == "connected"
            and "binding" not in supply
            and not endpoints_required
        ):
            self.error("/knowledge_supply/binding", "connected needs a binding ref")
        elif "binding" in supply:
            if not endpoints_required:
                self.ref(supply["binding"], "/knowledge_supply/binding", root)
            elif supply["binding"] not in ("on_demand_stdio", "resident_stdio"):
                self.error("/knowledge_supply/binding", "invalid binding value")
        self.refs(mapping.get("entrypoints"), "/entrypoints", root)
        # Local extensions (for example domain identity schemes) use the same resolver.
        for at, entry in map_entries(mapping):
            for location, ref in entry_refs(entry, at):
                if location not in self.checked_refs:
                    self.ref(ref, location, root)
        return declaration.get("version")


def resolves_symbol(text, name, suffix):
    """Resolve declared names, not arbitrary mentions; keep dotted check-name compatibility."""
    if not name:
        return False
    candidates = {name, name.rsplit(".", 1)[-1]}
    if suffix in (".md", ".markdown", ".mdx"):
        text = re.sub(r"<!--[\s\S]*?-->", "", text)
        seen = set()
        fence = None
        unfenced = []
        for line in text.splitlines():
            marker = re.match(r"^ {0,3}(`{3,}|~{3,})", line)
            if marker:
                if fence is None:
                    fence = marker[1]
                elif marker[1][0] == fence[0] and len(marker[1]) >= len(fence):
                    fence = None
                continue
            if fence is not None:
                continue
            unfenced.append(line)
            heading = re.match(r"^ {0,3}#{1,6}\s+(.+?)\s*#*\s*$", line)
            if heading:
                title = heading[1]
                slug = re.sub(r"[^\w -]", "", title.lower()).replace(" ", "-")
                unique, count = slug, 0
                while unique in seen:
                    count += 1
                    unique = slug + "-" + str(count)
                seen.add(unique)
                if name == unique or title in candidates:
                    return True
        text = "\n".join(unfenced)
    if suffix == ".json":
        try:
            document = json.loads(text)
        except ValueError:
            return False
        if "/" in name or "~" in name:
            value = document
            for part in name.removeprefix("/").split("/"):
                if re.search(r"~(?![01])", part):
                    return False
                key = part.replace("~1", "/").replace("~0", "~")
                if isinstance(value, dict) and key in value:
                    value = value[key]
                elif (isinstance(value, list) and re.fullmatch(NUMBER, key)
                      and int(key) < len(value)):
                    value = value[int(key)]
                else:
                    return False
            return True
        values = [document]
        while values:
            value = values.pop()
            if isinstance(value, dict):
                if candidates.intersection(value):
                    return True
                values.extend(value.values())
            elif isinstance(value, list):
                values.extend(value)
        return False
    modifiers = r"(?:(?:export|default|public|private|protected|static|async|pub|open)\s+)*"
    if suffix in (".kt", ".kts", ".dart"):
        text = re.sub(r"/\*[\s\S]*?\*/|//[^\n]*", "", text)
        modifiers = r"(?:(?:\w+|@[\w.]+(?:\([^\n]*?\))?)\s+)*"
    for candidate in candidates:
        symbol = re.escape(candidate)
        boundary = r"(?![\w$])"
        if suffix in (".kt", ".kts", ".dart"):
            boundary = r"(?=\s*(?:[({:<=>]|\b(?:extends|implements|with)\b|$))"
        definitions = (
            rf"^\s*{modifiers}"
            r"(?:def|class|function|const|let|var|interface|type|enum|struct|fn|func|val|fun|object)"
            rf"\s+(?:<[^>\n]+>\s*)?{symbol}{boundary}"
        )
        assignment = rf"^\s*{symbol}\s*(?::|=(?!=))"
        toml_key = rf"^\s*[\"']?{symbol}[\"']?\s*=(?!=)"
        table = rf"^\s*\[\[?\s*{symbol}\s*\]\]?\s*(?:#.*)?$"
        test = rf"^\s*(?:test|it|describe)\s*\(\s*[\"']{symbol}[\"']"
        patterns = [definitions, assignment, toml_key, table, test]
        if suffix in (".sh", ".bash", ".zsh"):
            patterns.append(rf"^\s*(?:function\s+)?{symbol}\s*\(\s*\)\s*\{{")
            patterns.append(rf"^\s*function\s+{symbol}\s*\{{")
        if any(re.search(pattern, text, re.MULTILINE) for pattern in patterns):
            return True
    return False


def map_entries(mapping):
    """Yield bounded, selectable entries; preserve JSON pointers for maintenance."""
    for section in (
        "canonical_index",
        "concepts",
        "relations",
        "domain",
        "questions",
        "error_cases",
        "vocabularies",
        "entrypoints",
        "knowledge_supply",
    ):
        value = mapping.get(section)
        if section == "domain" and isinstance(value, dict):
            for kind, entries in value.items():
                if isinstance(entries, list):
                    for i, entry in enumerate(entries):
                        yield pointer(pointer("/domain", kind), i), entry
        elif section == "concepts" and isinstance(value, dict):
            for key, entry in value.items():
                yield pointer("/concepts", key), entry
        elif isinstance(value, list):
            for i, entry in enumerate(value):
                yield pointer("/" + section, i), entry
        elif section == "knowledge_supply" and isinstance(value, dict):
            yield "/knowledge_supply", value


def entry_refs(entry, at):
    """Read only declared refs, never interpret free text as a path."""
    if isinstance(entry, str):
        yield at, entry
    elif isinstance(entry, list):
        for i, item in enumerate(entry):
            yield from entry_refs(item, pointer(at, i))
    elif isinstance(entry, dict):
        for key, value in entry.items():
            location = pointer(at, key)
            if key in ("ref", "check") and isinstance(value, str):
                yield location, value
            elif key == "binding" and isinstance(value, str):
                if value not in ("on_demand_stdio", "resident_stdio"):
                    yield location, value
            elif key == "evidence" and isinstance(value, list):
                yield from entry_refs(value, location)
            elif isinstance(value, (dict, list)):
                # Strings in other lists (endpoints, axis values) are not refs.
                if isinstance(value, dict):
                    yield from entry_refs(value, location)
                else:
                    for i, item in enumerate(value):
                        if isinstance(item, (dict, list)):
                            yield from entry_refs(item, pointer(location, i))


def ref_path(ref):
    return re.sub(r":\d+$", "", ref.split("#", 1)[0])


def touches(path, changed):
    path = PurePosixPath(path).as_posix().removeprefix("./")
    return any(item == path or item.startswith(path.rstrip("/") + "/") for item in changed)


def changed_paths(args, root):
    if args.paths is not None:
        paths = []
        for raw in args.paths:
            path = Path(raw)
            if path.is_absolute():
                path = path.relative_to(root)
            if ".." in path.parts:
                raise ValueError("changed paths must stay within the repository")
            paths.append(path.as_posix())
        return sorted(set(paths))
    # Union staged-versus-base and unstaged paths: net worktree diffs can hide
    # staged edits reverted in the worktree. No rename folding; preserve both names.
    if args.git_diff.startswith("-"):
        raise ValueError("git diff BASE must be a revision, not an option")
    paths = set()
    for revision in (["--cached", args.git_diff], []):
        result = subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "diff",
                "--no-ext-diff",
                "--no-textconv",
                "--no-renames",
                "--name-only",
                "-z",
                *revision,
                "--",
            ],
            capture_output=True,
            timeout=10,
            check=False,
        )
        if result.returncode:
            raise ValueError(
                "git diff failed: " + result.stderr.decode("utf-8", errors="replace").strip()
            )
        paths.update(result.stdout.decode("utf-8", errors="surrogateescape").split("\0"))
    return sorted(paths - {""})


def impact(mapping, root, changed, git_diff=False):
    affected = []
    affected_paths = set()
    stale = []
    for at, entry in map_entries(mapping):
        refs = list(entry_refs(entry, at))
        if any(touches(ref_path(ref), changed) for _, ref in refs):
            affected.append({"pointer": at, "refs": [ref for _, ref in refs]})
            affected_paths.update(ref_path(ref) for _, ref in refs)
        for location, ref in refs:
            check = Checker()
            if git_diff and re.search(r":\d+$", ref.split("#", 1)[0]) and touches(
                ref_path(ref), changed
            ):
                stale.append({
                    "pointer": location, "ref": ref,
                    "message": "re-anchor to a symbol: " + at,
                })
            try:
                if (
                    at.startswith("/error_cases/")
                    and location.endswith("/check")
                    and isinstance(entry, dict)
                    and entry.get("status") == "covered"
                ):
                    check.covered_check(ref, location, root)
                else:
                    check.ref(ref, location, root)
            except (OSError, UnicodeError, ValueError, RuntimeError):
                check.error(location, "ref could not be resolved")
            for finding in check.errors:
                stale.append({**finding, "ref": ref})
    checks = set()
    cases = mapping.get("error_cases", [])
    for case in cases if isinstance(cases, list) else []:
        if isinstance(case, dict) and case.get("status") == "covered":
            ref = case.get("check")
            if isinstance(ref, str) and (
                touches(ref_path(ref), changed)
                or any(touches(path, [ref_path(ref)]) for path in affected_paths)
            ):
                checks.add(ref)
    return {
        "changed_paths": changed,
        "affected_entries": affected,
        "checks_to_run": sorted(checks),
        "stale_refs": stale,
        "revalidate": ".mir/ontology-map.json" in changed,
    }


def lookup(mapping, query, limit):
    terms = set(re.findall(r"[^\W_]+", query.casefold(), re.UNICODE))
    matches = []
    for at, entry in map_entries(mapping):
        if not at.startswith(("/questions/", "/concepts/", "/domain/")):
            continue
        text = json.dumps(entry, ensure_ascii=False)
        words = set(re.findall(r"[^\W_]+", (at + " " + text).casefold(), re.UNICODE))
        score = len(terms & words)
        if score:
            refs = list(dict.fromkeys(ref for _, ref in entry_refs(entry, at)))
            matches.append({"pointer": at, "score": score, "entry": entry, "evidence": refs})
    matches.sort(key=lambda entry: -entry["score"])
    return {"contract": mapping.get("contract", {}), "matches": matches[:limit]}


def positive_int(raw):
    value = int(raw)
    if value < 1:
        raise argparse.ArgumentTypeError("must be positive")
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    contract_parser = commands.add_parser("contract", help="check the distributed contract")
    mapping_parser = commands.add_parser("mapping", help="check a project-owned mapping")
    impact_parser = commands.add_parser(
        "impact", help="select affected entries and checks; never run them"
    )
    lookup_parser = commands.add_parser("lookup", help="retrieve bounded local map evidence")
    for command in (contract_parser, mapping_parser, impact_parser, lookup_parser):
        command.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    for command in (mapping_parser, impact_parser, lookup_parser):
        command.add_argument("--repo", type=Path, required=True)
        command.add_argument("--json", action="store_true")
    changes = impact_parser.add_mutually_exclusive_group(required=True)
    changes.add_argument("--paths", nargs="+")
    changes.add_argument("--git-diff", nargs="?", const="HEAD", metavar="BASE")
    impact_parser.add_argument("--strict", action="store_true")
    lookup_parser.add_argument("query")
    lookup_parser.add_argument("--limit", type=positive_int, default=3)
    args = parser.parse_args(argv)
    checker = Checker()
    contract_version = None
    mapping_version = None
    io_problem = False
    selection = None
    try:
        payload = args.contract.read_bytes()
        contract = checker.contract(json.loads(payload))
        contract_version = contract.get("version")
        if args.command != "contract" and not checker.errors:
            root = args.repo.resolve()
            if not root.is_dir():
                raise OSError("repository root is not a directory")
            if args.command == "impact":
                selection = impact({}, root, changed_paths(args, root))
            try:
                text = (root / ".mir/ontology-map.json").read_text(encoding="utf-8")
            except FileNotFoundError:
                if args.command != "impact":
                    raise
                checker.error("", "mapping file is missing")
                text = "{}"
            size = len(text.encode("utf-8"))
            if size > MAPPING_BUDGET:
                checker.warn("/", f"mapping is {size} bytes, over the {MAPPING_BUDGET}-byte budget")
            try:
                mapping = json.loads(text)
            except json.JSONDecodeError:
                if args.command != "impact":
                    raise
                checker.error("", "mapping is invalid JSON")
                mapping = {}
            mapping_version = checker.mapping(mapping, contract, payload, root)
            if not isinstance(mapping, dict):
                mapping = {}
            if args.command == "impact":
                selection = impact(
                    mapping, root, selection["changed_paths"], git_diff=args.git_diff is not None
                )
            elif args.command == "lookup":
                selection = lookup(mapping, args.query, args.limit)
    except (OSError, UnicodeError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        checker.error("", "IO problem: " + str(exc))
        io_problem = True
    report = {
        "ok": not checker.errors,
        "errors": checker.errors,
        "warnings": checker.warnings,
        "contract_version": contract_version,
        "mapping_version": mapping_version,
        "line_ref_count": len(checker.line_refs),
    }
    if args.command in ("impact", "lookup"):
        report.update(selection or {})
        if getattr(args, "json", False):
            print(json.dumps(report))
        elif selection is not None:
            if args.command == "impact":
                print("affected entries:")
                for entry in selection["affected_entries"]:
                    print("  " + entry["pointer"] + ": " + ", ".join(entry["refs"]))
                print("checks to run (selection only):")
                for ref in selection["checks_to_run"]:
                    print("  " + ref)
                print("stale refs:")
                for entry in selection["stale_refs"]:
                    print("  " + entry["pointer"] + ": " + entry["ref"] + ": " + entry["message"])
                if selection["revalidate"]:
                    print("map changed: re-validate")
            else:
                declaration = selection["contract"]
                print(str(declaration.get("id")) + " " + str(declaration.get("version")))
                for entry in selection["matches"]:
                    print(entry["pointer"] + ": " + json.dumps(entry["entry"], ensure_ascii=False))
                    print("  evidence: " + ", ".join(entry["evidence"]))
        if not getattr(args, "json", False):
            for finding in checker.errors:
                print("ERROR " + finding["pointer"] + ": " + finding["message"])
        if io_problem:
            return 2
        return int(
            args.command == "impact"
            and args.strict
            and (bool(checker.errors) or bool((selection or {}).get("stale_refs")))
        )
    if getattr(args, "json", False):
        print(json.dumps(report))
    else:
        if args.command == "mapping":
            print(f"INFO {len(checker.line_refs)} line-number refs (1.x compatibility)")
        for label, findings in (("ERROR", checker.errors), ("WARN", checker.warnings)):
            for finding in findings:
                print(label + " " + finding["pointer"] + ": " + finding["message"])
        print(
            f"{len(checker.errors)} errors, {len(checker.warnings)} warnings; "
            f"contract {contract_version}, mapping {mapping_version}"
        )
    return 2 if io_problem else int(bool(checker.errors))


if __name__ == "__main__":
    sys.exit(main())
