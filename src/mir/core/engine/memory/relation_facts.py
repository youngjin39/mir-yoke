"""Validated, deterministic entity-to-entity facts declared in Markdown."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import yaml

from mir.core import relations as relation_core

from .store import audit_append

RELATION_SCHEMA = "mir-memory-relations/v1"
RELATION_PREDICATES = frozenset({"realized_by", "implemented_in", "verified_by", "depends_on"})
MAX_RELATIONS_PER_DOCUMENT = 64
MAX_RELATION_VALUE_CHARS = 1024
MAX_PROVENANCE_QUOTE_CHARS = 4096
MAX_RELATION_SOURCE_CHARS = 1024 * 1024
_INACTIVE_VERIFICATION_STATUSES = frozenset({"candidate", "draft", "proposed"})
_TERMINAL_PREFIXES = ("historical", "superseded")
_TERMINAL_STATUSES = frozenset(
    {
        "archived",
        "rejected",
        "superseded",
        "superseded-design",
        "historical",
        "historical-snapshot",
        "historical-manual-snapshot",
        "historical-ledger",
        "applied-ledger-v1",
        "done",
    }
)


class RelationDeclarationError(ValueError):
    """A ``memory_relations`` declaration is invalid or unsafe."""


@dataclass(frozen=True)
class RelationDeclaration:
    subject: str
    predicate: str
    object: str
    quote: str


@dataclass(frozen=True)
class ParsedRelationDocument:
    declarations: tuple[RelationDeclaration, ...]
    document_status: str
    has_frontmatter: bool


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat(timespec="microseconds")


def _frontmatter(raw: str) -> str | None:
    if not raw.startswith("---\n") and not raw.startswith("---\r\n"):
        return None
    lines = raw.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return None
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return "".join(lines[1:index])
    return None


def _node_string(node: yaml.Node, *, label: str) -> str:
    if not isinstance(node, yaml.ScalarNode) or node.tag != "tag:yaml.org,2002:str":
        raise RelationDeclarationError(f"invalid memory_relations: {label} must be a string")
    value = node.value
    if (
        not value
        or len(value) > MAX_RELATION_VALUE_CHARS
        or relation_core._has_control_characters(value)
    ):
        raise RelationDeclarationError(f"invalid memory_relations: {label} is unsafe or too long")
    return value


def parse_relation_document(raw: str) -> ParsedRelationDocument:
    """Parse only explicit ``memory_relations`` declarations from frontmatter."""
    frontmatter = _frontmatter(raw)
    if frontmatter is None:
        return ParsedRelationDocument((), "", False)
    if not any(
        line.split(":", 1)[0].strip() == "memory_relations"
        for line in frontmatter.splitlines()
        if ":" in line
    ):
        status = ""
        for line in frontmatter.splitlines():
            key, separator, value = line.partition(":")
            if separator and key.strip() == "status":
                status = value.strip().strip('"').strip("'").lower()
                break
        return ParsedRelationDocument((), status, True)
    try:
        root = yaml.compose(frontmatter)
    except (RecursionError, yaml.YAMLError) as exc:
        raise RelationDeclarationError(
            "invalid memory_relations: malformed YAML frontmatter"
        ) from exc
    if not isinstance(root, yaml.MappingNode):
        raise RelationDeclarationError("invalid memory_relations: frontmatter must be a mapping")
    declaration_node: yaml.Node | None = None
    document_status = ""
    status_seen = False
    for key, value in root.value:
        if not isinstance(key, yaml.ScalarNode):
            continue
        if key.value == "memory_relations":
            if declaration_node is not None:
                raise RelationDeclarationError("invalid memory_relations: duplicate declaration")
            declaration_node = value
        elif key.value == "status":
            if status_seen:
                raise RelationDeclarationError("invalid memory_relations: duplicate status")
            status_seen = True
            if not isinstance(value, yaml.ScalarNode) or value.tag != "tag:yaml.org,2002:str":
                raise RelationDeclarationError("invalid memory_relations: status must be a string")
            document_status = value.value.strip().lower()
    if declaration_node is None:
        return ParsedRelationDocument((), document_status, True)
    if not isinstance(declaration_node, yaml.SequenceNode):
        raise RelationDeclarationError("invalid memory_relations: value must be a list")
    if len(declaration_node.value) > MAX_RELATIONS_PER_DOCUMENT:
        raise RelationDeclarationError("invalid memory_relations: more than 64 relations")
    lines = frontmatter.splitlines()
    declarations: list[RelationDeclaration] = []
    seen: set[tuple[str, str, str]] = set()
    for edge in declaration_node.value:
        if not isinstance(edge, yaml.SequenceNode) or len(edge.value) != 3:
            raise RelationDeclarationError(
                "invalid memory_relations: each item must be a three-string list"
            )
        subject = _node_string(edge.value[0], label="subject")
        predicate = _node_string(edge.value[1], label="predicate")
        object_value = _node_string(edge.value[2], label="object")
        if predicate not in RELATION_PREDICATES:
            raise RelationDeclarationError(
                f"invalid memory_relations: unsupported predicate {predicate!r}"
            )
        key = (subject, predicate, object_value)
        if key in seen:
            raise RelationDeclarationError("invalid memory_relations: duplicate relation")
        seen.add(key)
        try:
            relation_core._anchor_spelling_safe(subject)
            relation_core._anchor_spelling_safe(object_value)
        except relation_core.RelationError as exc:
            raise RelationDeclarationError(
                f"invalid memory_relations: unsafe endpoint: {exc}"
            ) from exc
        quote = "\n".join(lines[edge.start_mark.line : edge.end_mark.line + 1])
        if not quote or len(quote) > MAX_PROVENANCE_QUOTE_CHARS:
            raise RelationDeclarationError("invalid memory_relations: supporting quote is too long")
        declarations.append(RelationDeclaration(subject, predicate, object_value, quote))
    return ParsedRelationDocument(tuple(declarations), document_status, True)


def validate_declarations_for_root(
    declarations: tuple[RelationDeclaration, ...], root: Path
) -> None:
    """Check declared file endpoints before an ingest transaction begins."""
    try:
        protections = relation_core._profile_protections(root)
    except relation_core.RelationError as exc:
        raise RelationDeclarationError(f"invalid memory_relations: {exc}") from exc
    for declaration in declarations:
        subject_error = relation_core._validate_endpoint(
            declaration.subject, root, protections=protections
        )
        if subject_error:
            raise RelationDeclarationError(f"invalid memory_relations: {subject_error}")
        error = relation_core._validate_endpoint(
            declaration.object,
            root,
            force_file=declaration.predicate in {"implemented_in", "verified_by"},
            protections=protections,
        )
        if error:
            raise RelationDeclarationError(f"invalid memory_relations: {error}")


def safe_source_relative_path(path: Path, root: Path) -> str:
    """Resolve an ingest source inside an unprotected project path before reading it."""
    try:
        resolved_root = root.resolve()
        resolved = path.resolve(strict=True)
        relative = resolved.relative_to(resolved_root)
        safe = relation_core._safe_relative_path(relative.as_posix(), label="source")
        protections = relation_core._profile_protections(resolved_root)
    except (OSError, ValueError, relation_core.RelationError) as exc:
        raise RelationDeclarationError("invalid memory_relations: unsafe source path") from exc
    if relation_core._protected(safe.parts, protections):
        raise RelationDeclarationError("invalid memory_relations: protected source path")
    return safe.as_posix()


def relation_status_is_active(predicate: str, document_status: str) -> bool:
    """Only settled documents contribute current declared relation edges."""
    normalized = document_status.strip().lower()
    return not (
        normalized in _INACTIVE_VERIFICATION_STATUSES
        or normalized in _TERMINAL_STATUSES
        or normalized.startswith(_TERMINAL_PREFIXES)
    )


def _upsert_entity(conn, slug: str) -> int:
    row = conn.execute("SELECT id FROM entities WHERE slug = ?", (slug,)).fetchone()
    if row:
        return int(row[0])
    conn.execute(
        "INSERT INTO entities(type, canonical_name, slug) VALUES (NULL, ?, ?)",
        (slug, slug),
    )
    return int(conn.execute("SELECT id FROM entities WHERE slug = ?", (slug,)).fetchone()[0])


def _owned_active_rows(conn, *, project_path: str, source_path: str):
    return conn.execute(
        """
        SELECT f.id, subject.slug, f.predicate, object.slug
          FROM facts f
          JOIN entities subject ON subject.id = f.subject_entity_id
          JOIN entities object ON object.id = f.object_entity_id
          JOIN content_items ci ON ci.id = f.created_from
         WHERE f.status = 'active'
           AND f.object_entity_id IS NOT NULL
           AND f.object_literal IS NULL
           AND f.scope = 'project'
           AND f.project_path = ?
           AND ci.source = 'self_ingest_md'
           AND json_extract(ci.metadata_json, '$.relation_schema') = ?
           AND json_extract(ci.metadata_json, '$.relation_project_path') = ?
           AND json_extract(ci.metadata_json, '$.path') = ?
        """,
        (project_path, RELATION_SCHEMA, project_path, source_path),
    ).fetchall()


def has_owned_active_relation_facts(conn, *, project_root: Path, source_path: str) -> bool:
    """Whether an empty-frontmatter revision needs a relation tombstone."""
    return bool(
        _owned_active_rows(
            conn,
            project_path=str(project_root.resolve()),
            source_path=source_path,
        )
    )


def reconcile_relation_facts(
    conn,
    *,
    declarations: tuple[RelationDeclaration, ...],
    content_item_id: int | None,
    project_root: Path,
    source_path: str,
    document_status: str,
) -> tuple[int, int]:
    """Reconcile only active relation facts owned by one source path."""
    project_path = str(project_root.resolve())
    superseded = 0
    for fact_id, _subject, _predicate, _object_value in _owned_active_rows(
        conn, project_path=project_path, source_path=source_path
    ):
        conn.execute(
            "UPDATE facts SET status = 'superseded', valid_to = ? WHERE id = ?",
            (_now_iso(), fact_id),
        )
        audit_append(
            conn,
            event="memory_relation.superseded",
            payload={"fact_id": fact_id, "source_path": source_path},
            commit=False,
        )
        superseded += 1
    if content_item_id is None:
        return 0, superseded

    inserted = 0
    for declaration in declarations:
        active = relation_status_is_active(declaration.predicate, document_status)
        subject_id = _upsert_entity(conn, declaration.subject)
        object_id = _upsert_entity(conn, declaration.object)
        now = _now_iso()
        cur = conn.execute(
            """
                INSERT INTO facts(subject_entity_id, predicate, object_entity_id, object_literal,
                  polarity, valid_from, valid_to, status, confidence,
                  created_from, scope, project_path)
                VALUES (?, ?, ?, NULL, 'asserted', ?, ?, ?, 1.0, ?, 'project', ?)
                """,
            (
                subject_id,
                declaration.predicate,
                object_id,
                now,
                None if active else now,
                "active" if active else "superseded",
                content_item_id,
                project_path,
            ),
        )
        fact_id = int(cur.lastrowid)
        inserted += 1
        audit_append(
            conn,
            event="memory_relation.ingested",
            payload={"fact_id": fact_id, "source_path": source_path},
            commit=False,
        )
        conn.execute(
            "INSERT INTO provenance(fact_id, content_item_id, quote, "
            "attribution_entity_id, strength) "
            "VALUES (?, ?, ?, NULL, 'stated')",
            (fact_id, content_item_id, declaration.quote),
        )
    return inserted, superseded


def relation_metadata(*, path: str, project_root: Path, document_status: str) -> dict[str, str]:
    """Return the self-ingest marker consumed by the read-only relation adapter."""
    return {
        "path": path,
        "relation_schema": RELATION_SCHEMA,
        "relation_project_path": str(project_root.resolve()),
        "relation_document_status": document_status,
    }
