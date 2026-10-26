"""Passive stdlib-only reader for the documented three-string YAML edge subset.

Traversal follows mir.core.relations. Injected I/O owns every repository read and
endpoint check; its refusals deliberately propagate to the calling server.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import stat
from hashlib import sha256
from pathlib import Path, PurePosixPath, PureWindowsPath

try:
    import tomllib
except ImportError:  # Python 3.9 and 3.10 keep the fixed protections.
    tomllib = None

DEFAULT_GRAPH = "spec/graph.yaml"
DEFAULT_DEPTH = 3
DEFAULT_MAX_EDGES = 16
MAX_DEPTH = 4
MAX_EDGES = 64
MAX_ANCHOR_CHARS = 4096
MAX_GRAPH_BYTES = 1024 * 1024
MAX_GRAPH_EDGES = 10_000


class RelationsError(ValueError):
    """Stable public error without target-derived details."""

    def __init__(self, code):
        self.code = code
        super().__init__(code)


class Edge:
    def __init__(self, source, relation, target, source_line):
        self.source = source
        self.relation = relation
        self.target = target
        self.source_line = source_line

    def as_dict(self):
        return {
            "source": self.source,
            "relation": self.relation,
            "target": self.target,
            "source_line": self.source_line,
        }


_FORWARD = {
    "implementation": {
        "has_req",
        "refines",
        "realized_by",
        "constrains",
        "implemented_in",
        "exposes",
        "decided_by",
        "governed_by",
    },
    "verification": {"has_req", "refines", "verified_by"},
    "impact": {"affects", "blocks", "verified_by", "decided_by", "governed_by"},
    "dependencies": {"depends_on"},
}
_REVERSE = {
    "implementation": set(),
    "verification": {"implemented_in", "realized_by", "constrains"},
    "impact": {"implemented_in", "realized_by", "constrains", "depends_on", "has_req"},
    "dependencies": set(),
}
_FILE_ENDPOINT_RELATIONS = {"implemented_in", "verified_by"}
_DEFAULT_DEPTHS = {
    "dependencies": 1,
    "implementation": DEFAULT_DEPTH,
    "impact": DEFAULT_DEPTH,
    "verification": DEFAULT_DEPTH,
}


def _endpoint_path(value: str, *, force_file: bool = False):
    path = value.split("::", 1)[0]
    return path if force_file or "/" in path or path.startswith(".") else None


def _normalized_locator(value: str) -> str:
    path, separator, suffix = value.partition("::")
    normalized = "/".join(part for part in PurePosixPath(path).parts if part != ".")
    return normalized + (separator + suffix if separator else "")


def _has_control_characters(value: str) -> bool:
    return any(
        ord(character) < 32 or 127 <= ord(character) <= 159 or character in {"\u2028", "\u2029"}
        for character in value
    )


def _notices(skipped: dict[str, int], extra: list[str]) -> list[str]:
    return [
        *(f"skipped {reason}: {count} edge(s)" for reason, count in sorted(skipped.items())),
        *extra,
    ]


def _result(
    anchor: str,
    purpose: str,
    digest: str,
    source: str,
    edges: list[Edge],
    notices: list[str],
    resolved: list[str],
    *,
    scope: str = "declared_spec_relations_only",
    source_metadata=None,
) -> dict:
    return {
        "anchor": anchor,
        "purpose": purpose,
        "scope": scope,
        "source": source_metadata or {"graph": source, "sha256": digest},
        "edges": [edge.as_dict() for edge in edges],
        "notices": notices,
        "truncated": any(notice.startswith("truncated:") for notice in notices),
        "resolved_anchors": resolved,
    }


def _has_eligible_edge(frontier: set[str], graph: list[Edge], purpose: str) -> bool:
    return any(
        (edge.source in frontier and edge.relation in _FORWARD[purpose])
        or (edge.target in frontier and edge.relation in _REVERSE[purpose])
        for edge in graph
    )


def query_relations(
    anchor, purpose, *, root, graph=DEFAULT_GRAPH, depth=None, max_edges=DEFAULT_MAX_EDGES, io=None
):
    """Retrieve declared relations without reading endpoint contents."""
    if not isinstance(purpose, str) or purpose not in _FORWARD:
        raise RelationsError("E_SCHEMA")
    resolved_depth = _DEFAULT_DEPTHS[purpose] if depth is None else depth
    for value, maximum in ((resolved_depth, MAX_DEPTH), (max_edges, MAX_EDGES)):
        if type(value) is not int or not 1 <= value <= maximum:
            raise RelationsError("E_SCHEMA")
    if not isinstance(anchor, str) or not anchor or _has_control_characters(anchor):
        raise RelationsError("E_SCHEMA")
    try:
        anchor_size = len(anchor.encode("utf-8"))
    except UnicodeEncodeError:
        raise RelationsError("E_SCHEMA") from None
    if anchor_size > MAX_ANCHOR_CHARS:
        raise RelationsError("E_LIMIT")
    reader = LocalReader(root) if io is None else io
    base = reader
    protections = ()
    anchor_path = _endpoint_path(anchor)
    if anchor_path is not None:
        _relative(anchor_path)
        reader.path(anchor_path, allow_missing=True)
    source = _relative(graph).as_posix()
    raw = reader.read(source)
    if len(raw) > MAX_GRAPH_BYTES:
        raise RelationsError("E_LIMIT")
    loaded_graph = _parse_graph(raw)
    digest = sha256(raw).hexdigest()
    _scope = "declared_spec_relations_only"
    _source_metadata = None
    _nodes = None
    nodes = list(
        dict.fromkeys(
            [
                *(item for edge in loaded_graph for item in (edge.source, edge.target)),
                *(_nodes or ()),
            ]
        )
    )
    file_nodes = {edge.target for edge in loaded_graph if edge.relation in _FILE_ENDPOINT_RELATIONS}
    if anchor not in nodes:
        issue = _validate_endpoint(anchor, base, protections=protections)
        if issue:
            raise RelationsError("E_PATH")
    elif anchor in file_nodes:
        issue = _validate_endpoint(anchor, base, force_file=True, protections=protections)
        if issue:
            raise RelationsError("E_PATH")
    resolved = [anchor] if anchor in nodes else []
    if _endpoint_path(anchor) is not None:
        normalized = _normalized_locator(anchor)
        if "::" in anchor:
            resolved = [node for node in nodes if _normalized_locator(node) == normalized]
        else:
            expanded = [
                node
                for node in nodes
                if _endpoint_path(node)
                and "::" in node
                and _normalized_locator(node).split("::", 1)[0] == normalized
            ]
            if expanded:
                resolved = expanded
    if not resolved:
        raise RelationsError("E_SCHEMA")
    notices: list[str] = []
    if len(resolved) > max_edges:
        notices.append(
            f"truncated: anchor expansion omitted {len(resolved) - max_edges} locator(s)"
        )
        resolved = resolved[:max_edges]
    skipped: dict[str, int] = {}
    result: list[Edge] = []
    seen_edges: set[tuple[str, str, str]] = set()
    frontier, seen_nodes = set(resolved), set(resolved)
    for level in range(resolved_depth):
        next_frontier: set[str] = set()
        for edge in loaded_graph:
            forward = edge.source in frontier and edge.relation in _FORWARD[purpose]
            reverse = edge.target in frontier and edge.relation in _REVERSE[purpose]
            if not (forward or reverse):
                continue
            source_path = edge.source.split("::", 1)[0]
            source_issue = (
                _validate_endpoint(edge.source, base, protections=protections)
                if "/" in source_path or source_path.startswith(".")
                else None
            )
            issue = source_issue or _validate_endpoint(
                edge.target,
                base,
                force_file=edge.relation in _FILE_ENDPOINT_RELATIONS,
                protections=protections,
            )
            if issue:
                skipped[issue] = skipped.get(issue, 0) + 1
                continue
            key = (edge.source, edge.relation, edge.target)
            if key not in seen_edges:
                if len(result) >= max_edges:
                    return _result(
                        anchor,
                        purpose,
                        digest,
                        source,
                        result,
                        _notices(
                            skipped,
                            [*notices, "truncated: max-edges reached; frontier remains unexplored"],
                        ),
                        resolved,
                        scope=_scope,
                        source_metadata=_source_metadata,
                    )
                result.append(edge)
                seen_edges.add(key)
            neighbour = edge.target if forward else edge.source
            if neighbour not in seen_nodes:
                seen_nodes.add(neighbour)
                next_frontier.add(neighbour)
        frontier = next_frontier
        if not frontier:
            break
        if level + 1 == resolved_depth and _has_eligible_edge(frontier, loaded_graph, purpose):
            notices.append("truncated: depth reached; frontier remains unexplored")
            break
    return _result(
        anchor,
        purpose,
        digest,
        source,
        result,
        _notices(skipped, notices),
        resolved,
        scope=_scope,
        source_metadata=_source_metadata,
    )


def _relative(value):
    if not isinstance(value, str) or not value or _has_control_characters(value):
        raise RelationsError("E_PATH")
    try:
        path_size = len(value.encode("utf-8"))
    except UnicodeEncodeError:
        raise RelationsError("E_PATH") from None
    if path_size > 4096:
        raise RelationsError("E_LIMIT")
    windows = PureWindowsPath(value)
    pure = PurePosixPath(value.replace("\\", "/"))
    if windows.drive or windows.root or pure.is_absolute() or ".." in pure.parts:
        raise RelationsError("E_PATH")
    if not pure.parts:
        raise RelationsError("E_PATH")
    return pure


_FIXED = (
    ".env*",
    "*.db*",
    "*.sqlite*",
    ".netrc",
    ".npmrc",
    ".pypirc",
    ".git-credentials",
    "credentials*",
    "token.json",
    "tokens.json",
    "id_rsa*",
    "id_ed25519*",
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "*.keystore",
)


class LocalReader:
    """Explicit-root direct-script reader; no environment or endpoint body reads."""

    def __init__(self, root):
        try:
            self.root = Path(root).resolve(strict=True)
        except (OSError, ValueError, TypeError):
            raise RelationsError("E_PATH") from None
        if not self.root.is_dir():
            raise RelationsError("E_PATH")
        self.patterns = ()
        profile = ".mir/repo-profile.toml"
        if tomllib is not None and self.exists(profile):
            raw = self.read(profile)
            if len(raw) > 65536:
                raise RelationsError("E_LIMIT")
            try:
                document = tomllib.loads(raw.decode("utf-8"))
                patterns = []
                for section, key in (
                    ("paths", "protected_paths"),
                    ("boundaries", "secrets"),
                    ("preserve", "agent_memory_paths"),
                ):
                    table = document.get(section, {})
                    if not isinstance(table, dict):
                        raise ValueError
                    values = table.get(key, [])
                    if not isinstance(values, list):
                        raise ValueError
                    patterns.extend(_relative(value).as_posix().lower() for value in values)
                if len(patterns) > 256:
                    raise ValueError
                self.patterns = tuple(patterns)
            except (ValueError, UnicodeDecodeError):
                raise RelationsError("E_FORMAT") from None

    def _protected(self, relative):
        parts = relative.as_posix().lower().split("/")
        if any(part in ("secrets", ".ssh", ".aws", ".gnupg") for part in parts):
            return True
        path = "/".join(parts)
        return any(
            fnmatch.fnmatchcase(part, pattern) for part in parts for pattern in _FIXED
        ) or any(
            fnmatch.fnmatchcase(path, pattern)
            or (
                not any(char in pattern for char in "*?[")
                and path.startswith(pattern.rstrip("/") + "/")
            )
            for pattern in self.patterns
        )

    def path(self, relative, allow_missing=False):
        pure = _relative(relative)
        if self._protected(pure):
            raise RelationsError("E_PROTECTED")
        candidate = self.root.joinpath(*pure.parts)
        try:
            resolved = candidate.resolve(strict=not allow_missing)
            target = resolved.relative_to(self.root)
            if self._protected(target):
                raise RelationsError("E_PROTECTED")
            if resolved.exists() and not stat.S_ISREG(resolved.stat().st_mode):
                raise RelationsError("E_PATH")
            return resolved
        except (OSError, ValueError) as exc:
            if isinstance(exc, RelationsError):
                raise
            raise RelationsError("E_PATH") from None

    def exists(self, relative):
        return self.path(relative, allow_missing=True).is_file()

    def read(self, relative):
        target = self.path(relative)
        try:
            with target.open("rb") as handle:
                raw = handle.read(MAX_GRAPH_BYTES + 1)
        except OSError:
            raise RelationsError("E_IO") from None
        if len(raw) > MAX_GRAPH_BYTES:
            raise RelationsError("E_LIMIT")
        return raw


def _validate_endpoint(value, reader, *, force_file=False, protections=()):
    path = _endpoint_path(value, force_file=force_file)
    if path is None:
        return None
    try:
        relative = _relative(path).as_posix()
    except RelationsError:
        return "unsafe path endpoint"
    # External guard refusals must not turn into a partial successful result.
    if not isinstance(reader, LocalReader):
        reader.path(relative, allow_missing=True)
        if not reader.exists(relative):
            return "unavailable endpoint"
        return None
    try:
        candidate = reader.path(relative, allow_missing=True)
        if not candidate.exists():
            return "unavailable endpoint"
        return None
    except RelationsError as exc:
        if exc.code == "E_PROTECTED":
            return "protected endpoint"
        return "endpoint symlink escapes root"


# YAML's implicit non-string scalars are outside the admitted string subset.
_NONSTRING = re.compile(
    r"^(?:~|null|true|false|yes|no|on|off|"
    r"[-+]?(?:[0-9][0-9_]*(?::[0-9_]+)*(?:\.[0-9_]*)?(?:[eE][-+]?[0-9]+)?|"
    r"\.[0-9_]+(?:[eE][-+]?[0-9]+)?|0[xX][0-9a-fA-F_]+|0[bB][01_]+|\.inf|\.nan)|"
    r"[0-9]{4}-[0-9]{1,2}-[0-9]{1,2}(?:[Tt ].*)?)$",
    re.IGNORECASE,
)


def _row(text):
    """Parse one flat flow row, with JSON double quotes or YAML single quotes."""
    if not text.startswith("["):
        raise RelationsError("E_FORMAT")
    values = []
    index = 1
    while True:
        while index < len(text) and text[index] == " ":
            index += 1
        if index >= len(text) or text[index] in ",]":
            raise RelationsError("E_FORMAT")
        quote = text[index]
        if quote == '"':
            try:
                value, consumed = json.JSONDecoder().raw_decode(text[index:])
            except ValueError:
                raise RelationsError("E_FORMAT") from None
            index += consumed
        elif quote == "'":
            index += 1
            value = ""
            while index < len(text):
                character = text[index]
                index += 1
                if character == "'":
                    if index < len(text) and text[index] == "'":
                        value += "'"
                        index += 1
                    else:
                        break
                else:
                    value += character
            else:
                raise RelationsError("E_FORMAT")
        else:
            start = index
            while index < len(text) and text[index] not in ",]":
                index += 1
            value = text[start:index].strip()
            if (
                not value
                or any(char in value for char in "[]{}!&*#'\"`")
                or value.startswith(("@", "|", ">", "%", "?", ":", "- "))
                or value.endswith(":")
                or ": " in value
                or _NONSTRING.fullmatch(value)
            ):
                raise RelationsError("E_FORMAT")
        if not isinstance(value, str) or not value or _has_control_characters(value):
            raise RelationsError("E_FORMAT")
        try:
            length = len(value.encode("utf-8"))
        except UnicodeEncodeError:
            raise RelationsError("E_FORMAT") from None
        if length > 4096:
            raise RelationsError("E_LIMIT")
        values.append(value)
        while index < len(text) and text[index] == " ":
            index += 1
        if index >= len(text):
            raise RelationsError("E_FORMAT")
        separator = text[index]
        index += 1
        if separator == "]":
            tail = text[index:]
            if tail and not (tail.startswith(" ") and tail.lstrip().startswith("#")):
                if tail.strip():
                    raise RelationsError("E_FORMAT")
            break
        if separator != "," or len(values) >= 3:
            raise RelationsError("E_FORMAT")
    if len(values) != 3:
        raise RelationsError("E_FORMAT")
    return values


def _parse_graph(raw):
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise RelationsError("E_FORMAT") from None
    edges = []
    found = False
    empty = False
    indent = None
    for number, line in enumerate(text.split("\n"), 1):
        if "\t" in line or "\r" in line.rstrip("\r"):
            raise RelationsError("E_FORMAT")
        line = line.rstrip("\r")
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if not found:
            if not re.fullmatch(r"edges: *(\[\])? *(?:#.*)?", line):
                raise RelationsError("E_FORMAT")
            found = True
            empty = "[]" in line.split("#", 1)[0]
            continue
        leading = len(line) - len(line.lstrip(" "))
        if indent is None:
            indent = leading
        if empty or leading != indent or not stripped.startswith("- "):
            raise RelationsError("E_FORMAT")
        values = _row(stripped[2:].lstrip())
        edges.append(Edge(*values, source_line=number))
        if len(edges) > MAX_GRAPH_EDGES:
            raise RelationsError("E_LIMIT")
    if not found or (not edges and not empty):
        raise RelationsError("E_FORMAT")
    return edges


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("anchor")
    parser.add_argument("purpose", choices=tuple(_FORWARD))
    parser.add_argument("--root", required=True)
    parser.add_argument("--graph", default=DEFAULT_GRAPH)
    parser.add_argument("--depth", type=int)
    parser.add_argument("--max-edges", type=int, default=DEFAULT_MAX_EDGES)
    args = parser.parse_args()
    try:
        result = query_relations(
            args.anchor,
            args.purpose,
            root=args.root,
            graph=args.graph,
            depth=args.depth,
            max_edges=args.max_edges,
        )
    except RelationsError as exc:
        print(json.dumps({"ok": False, "error": {"code": exc.code}}))
        return 1
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
