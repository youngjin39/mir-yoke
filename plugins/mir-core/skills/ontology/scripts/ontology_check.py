"""Read-only semantic contract and project mapping checks; Python 3.9, stdlib only."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
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
        if not self.text(value, at, "needs a ref"):
            return
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
        return target

    def covered_check(self, value, at, root):
        target = self.ref(value, at, root)
        if target is None:
            return
        if not target.is_file():
            self.error(at, "check ref must name a file")
            return
        path, separator, name = value.partition("#")
        line = re.search(r":(\d+)$", path)
        text = target.read_text(encoding="utf-8")
        if line:
            number = int(line[1])
            if number < 1:
                self.error(at, "check line must be positive")
            elif number > len(text.splitlines()):
                self.error(at, "check line exceeds file line count")
        if separator and (not name or name.rsplit(".", 1)[-1] not in text):
            self.error(at, "check name not found")
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
        relation_ids = {entry["id"] for entry in contract["relations"]}
        for i, raw_relation in enumerate(self.array(mapping.get("relations"), "/relations")):
            at = pointer("/relations", i)
            relation = self.object(raw_relation, at)
            self.text(relation.get("local"), at + "/local", "needs a non-empty local relation")
            if ("common" in relation) == ("local_only" in relation):
                self.error(at, "relation needs either common or local_only")
            elif "common" in relation:
                common = relation["common"]
                if not isinstance(common, str) or common not in relation_ids:
                    self.error(at + "/common", "unknown relation")
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
        if supply.get("memory_keeper") == "connected" and "binding" not in supply:
            self.error("/knowledge_supply/binding", "connected needs a binding ref")
        elif "binding" in supply:
            self.ref(supply["binding"], "/knowledge_supply/binding", root)
        self.refs(mapping.get("entrypoints"), "/entrypoints", root)
        return declaration.get("version")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    contract_parser = commands.add_parser("contract", help="check the distributed contract")
    mapping_parser = commands.add_parser("mapping", help="check a project-owned mapping")
    for command in (contract_parser, mapping_parser):
        command.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    mapping_parser.add_argument("--repo", type=Path, required=True)
    mapping_parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    checker = Checker()
    contract_version = None
    mapping_version = None
    io_problem = False
    try:
        payload = args.contract.read_bytes()
        contract = checker.contract(json.loads(payload))
        contract_version = contract.get("version")
        if args.command == "mapping" and not checker.errors:
            root = args.repo.resolve()
            if not root.is_dir():
                raise OSError("repository root is not a directory")
            text = (root / ".mir/ontology-map.json").read_text(encoding="utf-8")
            size = len(text.encode("utf-8"))
            if size > MAPPING_BUDGET:
                checker.warn("/", f"mapping is {size} bytes, over the {MAPPING_BUDGET}-byte budget")
            mapping = json.loads(text)
            mapping_version = checker.mapping(mapping, contract, payload, root)
    except (OSError, UnicodeError, ValueError, RuntimeError) as exc:
        checker.error("", "IO problem: " + str(exc))
        io_problem = True
    report = {
        "ok": not checker.errors,
        "errors": checker.errors,
        "warnings": checker.warnings,
        "contract_version": contract_version,
        "mapping_version": mapping_version,
    }
    if getattr(args, "json", False):
        print(json.dumps(report))
    else:
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
