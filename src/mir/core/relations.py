"""Read-only, bounded traversal of declared YAML specification relations."""

from __future__ import annotations

import fnmatch
import json
import tomllib
from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

import yaml

DEFAULT_GRAPH = "spec/graph.yaml"
DEFAULT_DEPTH = 3
DEFAULT_MAX_EDGES = 16
DEFAULT_MAX_BYTES = 6000
MAX_DEPTH = 4
MAX_EDGES = 64
MIN_BYTES = 1024
MAX_BYTES = 16000
MAX_GRAPH_BYTES = 1024 * 1024
MAX_GRAPH_EDGES = 10_000
MAX_ANCHOR_CHARS = 4096
MAX_PROFILE_BYTES = 64 * 1024
MAX_PROFILE_PATTERNS = 256
MAX_PROFILE_PATTERN_CHARS = 4096


class RelationError(ValueError):
    """An input that cannot safely produce a bounded relation result."""


@dataclass(frozen=True)
class Edge:
    source: str
    relation: str
    target: str
    source_line: int

    def as_dict(self) -> dict[str, Any]:
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


def _protected(parts: tuple[str, ...], patterns: tuple[str, ...] = ()) -> bool:
    lowered = "/".join(parts).lower()
    baseline = (
        any(part.lower().startswith(".env") for part in parts)
        or lowered == "secrets"
        or lowered.startswith("secrets/")
        or lowered.startswith(".mir/memory.db")
    )
    return baseline or any(_matches_protection(lowered, pattern) for pattern in patterns)


def _matches_protection(path: str, pattern: str) -> bool:
    folded = pattern.lower().rstrip("/")
    return fnmatch.fnmatchcase(path, folded) or (
        not any(character in folded for character in "*?[") and path.startswith(folded + "/")
    )


def _profile_pattern(value: object) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > MAX_PROFILE_PATTERN_CHARS
        or _has_control_characters(value)
    ):
        raise RelationError("repo profile protection paths must be non-empty strings")
    windows = PureWindowsPath(value)
    pure = PurePosixPath(value.replace("\\", "/"))
    if windows.drive or windows.root or pure.is_absolute() or ".." in pure.parts:
        raise RelationError("repo profile protection path is unsafe")
    parts = tuple(part for part in pure.parts if part != ".")
    if not parts:
        raise RelationError("repo profile protection path is unsafe")
    return "/".join(parts)


def _profile_protections(root: Path) -> tuple[str, ...]:
    profile = root / ".mir" / "repo-profile.toml"
    try:
        profile.lstat()
    except FileNotFoundError:
        return ()
    except OSError as exc:
        raise RelationError("repo profile cannot safely define protections") from exc
    try:
        resolved = profile.resolve(strict=True)
        relative = resolved.relative_to(root)
        if _protected(relative.parts):
            raise RelationError("repo profile cannot safely define protections")
        with resolved.open("rb") as handle:
            raw = handle.read(MAX_PROFILE_BYTES + 1)
        if len(raw) > MAX_PROFILE_BYTES:
            raise RelationError("repo profile exceeds 64 KiB limit")
        document = tomllib.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError, ValueError) as exc:
        raise RelationError("repo profile cannot safely define protections") from exc
    if not isinstance(document, dict):
        raise RelationError("repo profile cannot safely define protections")
    sections = tuple(document.get(name, {}) for name in ("paths", "boundaries", "preserve"))
    if any(not isinstance(section, dict) for section in sections):
        raise RelationError("repo profile cannot safely define protections")
    paths, boundaries, preserve = sections
    collections = (
        paths.get("protected_paths", []),
        boundaries.get("secrets", []),
        preserve.get("agent_memory_paths", []),
    )
    values: list[str] = []
    for collection in collections:
        if not isinstance(collection, list):
            raise RelationError("repo profile protections must be lists")
        if len(values) + len(collection) > MAX_PROFILE_PATTERNS:
            raise RelationError("repo profile has too many protection paths")
        values.extend(_profile_pattern(value) for value in collection)
    return tuple(dict.fromkeys(values))


def _safe_relative_path(value: str, *, label: str) -> PurePosixPath:
    if not isinstance(value, str) or not value or _has_control_characters(value):
        raise RelationError(f"{label} must be a non-empty repository-relative path")
    windows = PureWindowsPath(value)
    pure = PurePosixPath(value.replace("\\", "/"))
    if windows.drive or windows.root or pure.is_absolute() or ".." in pure.parts:
        raise RelationError(f"{label} must be a safe repository-relative path")
    parts = tuple(part for part in pure.parts if part != ".")
    if not parts:
        raise RelationError(f"{label} must be a safe repository-relative path")
    if _protected(parts):
        raise RelationError(f"{label} is protected")
    return PurePosixPath(*parts)


def _resolve_root(root: str | Path) -> Path:
    if not isinstance(root, (str, Path)):
        raise RelationError("root must be a path")
    try:
        base = Path(root).resolve()
    except OSError as exc:
        raise RelationError("root is unavailable") from exc
    if not base.is_dir():
        raise RelationError("root must be a directory")
    return base


def _graph_path(root: Path, graph: str, *, protections: tuple[str, ...]) -> tuple[Path, str]:
    relative = _safe_relative_path(graph, label="graph")
    display = relative.as_posix()
    if _protected(relative.parts, protections):
        raise RelationError("graph is protected")
    candidate = root.joinpath(*relative.parts)
    try:
        parent = candidate.parent.resolve()
        parent_relative = parent.relative_to(root)
    except (OSError, ValueError) as exc:
        raise RelationError("graph parent escapes root") from exc
    if _protected(parent_relative.parts, protections):
        raise RelationError("graph parent is protected")
    if not candidate.is_file():
        raise RelationError(f"{display} is unavailable")
    try:
        resolved = candidate.resolve(strict=True)
        resolved_relative = resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise RelationError("graph symlink escapes root") from exc
    if _protected(resolved_relative.parts, protections):
        raise RelationError("graph resolved target is protected")
    if not resolved.is_file():
        raise RelationError(f"{display} is unavailable")
    return resolved, display


def _load_graph(
    root: Path, graph: str = DEFAULT_GRAPH, *, protections: tuple[str, ...] = ()
) -> tuple[list[Edge], str, str]:
    source, display = _graph_path(root, graph, protections=protections)
    try:
        with source.open("rb") as handle:
            raw = handle.read(MAX_GRAPH_BYTES + 1)
    except OSError as exc:
        raise RelationError(f"{display} cannot be read") from exc
    if len(raw) > MAX_GRAPH_BYTES:
        raise RelationError("graph exceeds 1 MiB limit")
    try:
        document = yaml.compose(raw)
    except (RecursionError, yaml.YAMLError) as exc:
        raise RelationError("malformed graph") from exc
    if not isinstance(document, yaml.MappingNode):
        raise RelationError("graph must be a mapping with edges")
    edge_nodes = []
    for key, value in document.value:
        if not isinstance(key, yaml.ScalarNode) or key.tag != "tag:yaml.org,2002:str":
            raise RelationError("graph keys must be strings")
        if key.value == "edges":
            edge_nodes.append(value)
    if len(edge_nodes) != 1:
        raise RelationError("graph must contain exactly one edges mapping")
    edges_node = edge_nodes[0]
    if not isinstance(edges_node, yaml.SequenceNode):
        raise RelationError("graph edges must be a list")
    if len(edges_node.value) > MAX_GRAPH_EDGES:
        raise RelationError("graph exceeds 10000 edge rows")
    edges: list[Edge] = []
    for row in edges_node.value:
        if (
            not isinstance(row, yaml.SequenceNode)
            or len(row.value) != 3
            or any(
                not isinstance(item, yaml.ScalarNode) or item.tag != "tag:yaml.org,2002:str"
                for item in row.value
            )
        ):
            raise RelationError("each graph edge must be a three-item scalar list")
        values = [str(item.value) for item in row.value]
        if any(not value or _has_control_characters(value) for value in values):
            raise RelationError(
                "graph edge values must be non-empty and contain no control characters"
            )
        edges.append(Edge(*values, source_line=row.start_mark.line + 1))
    return edges, sha256(raw).hexdigest(), display


def _endpoint_path(value: str, *, force_file: bool = False) -> str | None:
    path = value.split("::", 1)[0]
    return path if force_file or "/" in path or path.startswith(".") else None


def _validate_endpoint(
    value: str, root: Path, *, force_file: bool = False, protections: tuple[str, ...] = ()
) -> str | None:
    path = _endpoint_path(value, force_file=force_file)
    if path is None:
        return None
    try:
        relative = _safe_relative_path(path, label="endpoint")
    except RelationError as exc:
        if "protected" in str(exc):
            return "protected endpoint"
        return "unsafe path endpoint"
    candidate = root.joinpath(*relative.parts)
    if not candidate.exists():
        return "unavailable endpoint"
    try:
        resolved_relative = candidate.resolve().relative_to(root)
    except (OSError, ValueError):
        return "endpoint symlink escapes root"
    if _protected(relative.parts, protections) or _protected(resolved_relative.parts, protections):
        return "protected endpoint"
    if not candidate.is_file():
        return "unavailable file endpoint"
    return None


def _anchor_spelling_safe(anchor: str) -> None:
    if (
        not isinstance(anchor, str)
        or not anchor
        or len(anchor) > MAX_ANCHOR_CHARS
        or _has_control_characters(anchor)
    ):
        raise RelationError("anchor must be non-empty")
    path = _endpoint_path(anchor)
    if path is not None:
        try:
            _safe_relative_path(path, label="anchor")
        except RelationError as exc:
            raise RelationError(f"anchor unsafe path endpoint: {exc}") from exc


def _normalized_locator(value: str) -> str:
    path, separator, suffix = value.partition("::")
    normalized = "/".join(part for part in PurePosixPath(path).parts if part != ".")
    return normalized + (separator + suffix if separator else "")


def _has_control_characters(value: str) -> bool:
    return any(
        ord(character) < 32
        or 127 <= ord(character) <= 159
        or character in {"\u2028", "\u2029"}
        for character in value
    )


def _validate_limits(depth: int, max_edges: int, max_bytes: int) -> None:
    if isinstance(depth, bool) or not isinstance(depth, int) or not 1 <= depth <= MAX_DEPTH:
        raise RelationError("depth must be between 1 and 4")
    if (
        isinstance(max_edges, bool)
        or not isinstance(max_edges, int)
        or not 1 <= max_edges <= MAX_EDGES
    ):
        raise RelationError("max-edges must be between 1 and 64")
    if (
        isinstance(max_bytes, bool)
        or not isinstance(max_bytes, int)
        or not MIN_BYTES <= max_bytes <= MAX_BYTES
    ):
        raise RelationError("max-bytes must be between 1024 and 16000")


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
) -> dict[str, Any]:
    return {
        "anchor": anchor,
        "purpose": purpose,
        "scope": "declared_spec_relations_only",
        "source": {"graph": source, "sha256": digest},
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
    anchor: str,
    purpose: str,
    *,
    root: str | Path = ".",
    graph: str = DEFAULT_GRAPH,
    depth: int = DEFAULT_DEPTH,
    max_edges: int = DEFAULT_MAX_EDGES,
    max_bytes: int = DEFAULT_MAX_BYTES,
    _graph: list[Edge] | None = None,
    _digest: str | None = None,
    _source: str | None = None,
    _protections: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """Return explicitly declared, safety-checked graph edges for one purpose."""
    if not isinstance(purpose, str) or purpose not in _FORWARD:
        raise RelationError("purpose must be implementation, impact, verification, or dependencies")
    _validate_limits(depth, max_edges, max_bytes)
    base = _resolve_root(root)
    protections = _profile_protections(base) if _protections is None else _protections
    _anchor_spelling_safe(anchor)
    if _graph is None or _digest is None or _source is None:
        loaded_graph, digest, source = _load_graph(base, graph, protections=protections)
    else:
        loaded_graph, digest, source = _graph, _digest, _source
    nodes = list(
        dict.fromkeys(item for edge in loaded_graph for item in (edge.source, edge.target))
    )
    file_nodes = {edge.target for edge in loaded_graph if edge.relation in _FILE_ENDPOINT_RELATIONS}
    if anchor not in nodes:
        issue = _validate_endpoint(anchor, base, protections=protections)
        if issue:
            raise RelationError(f"anchor {issue}")
    elif anchor in file_nodes:
        issue = _validate_endpoint(anchor, base, force_file=True, protections=protections)
        if issue:
            raise RelationError(f"anchor {issue}")
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
        raise RelationError("unknown anchor")
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
    for level in range(depth):
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
        if level + 1 == depth and _has_eligible_edge(frontier, loaded_graph, purpose):
            notices.append("truncated: depth reached; frontier remains unexplored")
            break
    return _result(anchor, purpose, digest, source, result, _notices(skipped, notices), resolved)


def _source_line(source: str, line: int) -> str:
    return f"graph.yaml:{line}" if source == DEFAULT_GRAPH else f"{source}:{line}"


def _render_edge(edge: dict[str, Any], source: str) -> str:
    return (
        f"{edge['source']} {edge['relation']} {edge['target']} "
        f"({_source_line(source, edge['source_line'])})"
    )


def render_json(result: dict[str, Any], max_bytes: int) -> str:
    """Serialize a bounded copy without changing the caller's result."""
    candidate = deepcopy(result)
    while True:
        output = (
            json.dumps(candidate, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        )
        if len(output.encode("utf-8")) <= max_bytes:
            return output
        if not candidate["edges"]:
            raise RelationError("max-bytes cannot contain required result metadata")
        candidate["edges"].pop()
        _refresh_bundle_facets(candidate)
        if "truncated: output byte limit reached; edges omitted" not in candidate["notices"]:
            candidate["notices"].append("truncated: output byte limit reached; edges omitted")
        candidate["truncated"] = True


def render_human(result: dict[str, Any], max_bytes: int) -> str:
    source = result["source"]["graph"]
    lines = [
        f"anchor={result['anchor']} purpose={result['purpose']} scope={result['scope']}",
        f"source={source} sha256={result['source']['sha256']}",
    ]
    if result.get("resolved_anchors", []) != [result["anchor"]]:
        lines.append("resolved_anchors=" + ",".join(result["resolved_anchors"]))
    edges, notices = list(result["edges"]), list(result["notices"])
    while True:
        output = (
            "\n".join(
                [
                    *lines,
                    *(_render_edge(edge, source) for edge in edges),
                    *(f"notice: {notice}" for notice in notices),
                ]
            )
            + "\n"
        )
        if len(output.encode("utf-8")) <= max_bytes:
            return output
        if not edges:
            raise RelationError("max-bytes cannot contain required result metadata")
        edges.pop()
        if "truncated: output byte limit reached; edges omitted" not in notices:
            notices.append("truncated: output byte limit reached; edges omitted")


def _search_bundle(anchors: list[str], purposes: list[str], reason: str) -> dict[str, Any]:
    return {
        "route": "search",
        "anchors": anchors,
        "requested_purposes": purposes,
        "reason": reason,
        "scope": "declared_spec_relations_only",
        "edges": [],
        "notices": [],
        "truncated": False,
    }


def bundle_relations(
    anchors: list[str],
    purposes: list[str],
    *,
    root: str | Path = ".",
    graph: str = DEFAULT_GRAPH,
    depth: int = DEFAULT_DEPTH,
    max_edges: int = DEFAULT_MAX_EDGES,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> dict[str, Any]:
    """Combine eligible same-anchor facets from one graph read, or select ordinary search."""
    if (
        not isinstance(anchors, list)
        or not isinstance(purposes, list)
        or any(not isinstance(value, str) for value in [*anchors, *purposes])
    ):
        raise RelationError("anchors and purposes must be lists")
    _validate_limits(depth, max_edges, max_bytes)
    for anchor in anchors:
        _anchor_spelling_safe(anchor)
    unique_anchors, unique_purposes = list(dict.fromkeys(anchors)), list(dict.fromkeys(purposes))
    if len(unique_anchors) != 1:
        return _search_bundle(
            unique_anchors, unique_purposes, "requires exactly one distinct anchor"
        )
    if len(unique_purposes) < 2:
        return _search_bundle(
            unique_anchors, unique_purposes, "requires at least two distinct purposes"
        )
    if any(purpose not in _FORWARD for purpose in unique_purposes):
        return _search_bundle(unique_anchors, unique_purposes, "unknown purpose")
    base = _resolve_root(root)
    protections = _profile_protections(base)
    try:
        loaded_graph, digest, source = _load_graph(base, graph, protections=protections)
    except RelationError as exc:
        if "unavailable" in str(exc):
            return _search_bundle(unique_anchors, unique_purposes, "graph unavailable")
        raise
    anchor = unique_anchors[0]
    nodes = {item for edge in loaded_graph for item in (edge.source, edge.target)}
    resolved_anchor, resolution = anchor, None
    file_targets = {edge.target for edge in loaded_graph if edge.relation == "implemented_in"}
    if anchor in file_targets or (anchor not in nodes and _endpoint_path(anchor) is not None):
        issue = _validate_endpoint(anchor, base, force_file=True, protections=protections)
        if issue:
            if issue == "unavailable endpoint":
                return _search_bundle(unique_anchors, unique_purposes, "unknown anchor")
            raise RelationError(f"anchor {issue}")
        normalized = _normalized_locator(anchor)
        owners = [
            edge
            for edge in loaded_graph
            if edge.relation == "implemented_in"
            and _normalized_locator(edge.target).split("::", 1)[0] == normalized
        ]
        owner_ids = list(dict.fromkeys(edge.source for edge in owners))
        if len(owner_ids) != 1:
            return _search_bundle(
                unique_anchors,
                unique_purposes,
                "ambiguous implementation owner" if owners else "unknown anchor",
            )
        resolved_anchor = owner_ids[0]
        owner = owners[0]
        resolution = {
            "relation": owner.relation,
            "source": owner.source,
            "target": owner.target,
            "source_line": owner.source_line,
        }
    elif anchor not in nodes:
        return _search_bundle(unique_anchors, unique_purposes, "unknown anchor")
    merged: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    facets, notices, omitted = [], [], False
    for purpose in unique_purposes:
        item = query_relations(
            resolved_anchor,
            purpose,
            root=base,
            graph=graph,
            depth=depth,
            max_edges=max_edges,
            max_bytes=max_bytes,
            _graph=loaded_graph,
            _digest=digest,
            _source=source,
            _protections=protections,
        )
        available, contributed = len(item["edges"]), 0
        for edge in item["edges"]:
            key = (edge["source"], edge["relation"], edge["target"])
            if key in seen:
                next(
                    item
                    for item in merged
                    if (item["source"], item["relation"], item["target"]) == key
                )["purposes"].append(purpose)
            elif len(merged) < max_edges:
                merged.append({**edge, "purposes": [purpose]})
                seen.add(key)
                contributed += 1
            else:
                omitted = True
        facets.append(
            {
                "purpose": purpose,
                "available_count": available,
                "edge_count": contributed,
                "coverage": "truncated"
                if item["truncated"] or omitted
                else "empty"
                if not available
                else "bounded",
                "notices": list(item["notices"]),
            }
        )
        notices.extend(item["notices"])
    if any(facet["available_count"] == 0 for facet in facets):
        return _search_bundle(
            unique_anchors,
            unique_purposes,
            "one or more requested facets have no declared evidence",
        )
    notices = list(dict.fromkeys(notices))
    if omitted:
        notices.append("truncated: global max-edges reached; facet coverage incomplete")
    result = {
        "route": "graph",
        "anchor": anchor,
        "resolved_anchor": resolved_anchor,
        "resolution": resolution,
        "requested_purposes": unique_purposes,
        "facets": facets,
        "scope": "declared_spec_relations_only",
        "source": {"graph": source, "sha256": digest},
        "edges": merged,
        "notices": notices,
        "truncated": any(notice.startswith("truncated:") for notice in notices),
    }
    _refresh_bundle_facets(result)
    return result


def _refresh_bundle_facets(result: dict[str, Any]) -> None:
    if "facets" not in result:
        return
    emitted = {facet["purpose"]: 0 for facet in result["facets"]}
    for edge in result["edges"]:
        for purpose in edge.get("purposes", []):
            if purpose in emitted:
                emitted[purpose] += 1
    for facet in result["facets"]:
        facet["edge_count"] = emitted[facet["purpose"]]
        if facet["edge_count"] < facet.get("available_count", 0):
            facet["coverage"] = "truncated"


def render_bundle_human(result: dict[str, Any], max_bytes: int) -> str:
    candidate = deepcopy(result)
    lines = [f"route={candidate['route']}"]
    if candidate["route"] == "search":
        lines.append(f"reason={candidate['reason']}")
    else:
        lines.extend(
            [
                f"anchor={candidate['anchor']} resolved_anchor={candidate['resolved_anchor']}",
                f"purposes={','.join(candidate['requested_purposes'])}",
            ]
        )
        if candidate.get("resolution"):
            resolution = candidate["resolution"]
            lines.append(
                "resolution=implemented_in "
                f"{_source_line(candidate['source']['graph'], resolution['source_line'])}"
            )
        lines.append(
            f"source={candidate['source']['graph']} sha256={candidate['source']['sha256']}"
        )
    edges, notices = list(candidate["edges"]), list(candidate["notices"])
    while True:
        facets = [
            f"facet={facet['purpose']} edges={facet['edge_count']} coverage={facet['coverage']}"
            for facet in candidate.get("facets", [])
        ]
        source = candidate.get("source", {}).get("graph", DEFAULT_GRAPH)
        output = (
            "\n".join(
                [
                    *lines,
                    *facets,
                    *(_render_edge(edge, source) for edge in edges),
                    *(f"notice: {notice}" for notice in notices),
                ]
            )
            + "\n"
        )
        if len(output.encode("utf-8")) <= max_bytes:
            return output
        if not edges:
            raise RelationError("max-bytes cannot contain required result metadata")
        edges.pop()
        _refresh_bundle_facets({"edges": edges, "facets": candidate["facets"]})
        if "truncated: output byte limit reached; edges omitted" not in notices:
            notices.append("truncated: output byte limit reached; edges omitted")
