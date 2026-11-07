"""B18-F01: archive helper oracle captured from unmodified Python, never a port.

Real trees freeze membership; controlled traversal freezes order independently of FS order.
Unreadability is simulated at the filesystem boundary, including on privileged runners.
No register, scan, indexing, context sync, or database operations belong to this slice.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from unittest import mock

import pytest

from mir.core.engine.memory import external_store as es

FIXTURE = (Path(__file__).parent
           / "../native/handoff-packet/tests/fixtures/w2/b18-archive-helpers.json")


def observe(case, tmp):
    try:
        return {"value": json.loads(json.dumps(case(tmp)), parse_constant=str)}
    except Exception as exc:  # noqa: BLE001 - freeze exception class and message
        return {"error": [type(exc).__name__, str(exc).replace(str(tmp), "<tmp>")]}


def _chunk(raw, size, overlap):
    return lambda tmp: [asdict(c) for c in es._chunk_text(raw, size=size, overlap=overlap)]


RELS = ("a.md", ".hidden.md", "docs/a.md", "docs/deep/b.md", "a.txt", "docs/", "b.md")


def _glob(spec):
    def run(tmp):
        patterns = es._compile_globs(spec)
        compiled = es._compile_pattern_set(patterns)
        return {"patterns": patterns, "regex": [r.pattern for r in compiled],
                "fnmatch": [es._matches_any(p, patterns) for p in RELS],
                "regex_match": [es._matches_regex_any(p, compiled) for p in RELS]}
    return run


def _paths(tmp):
    paths = ("docs/decisions/a.md", "docs/_archive/decisions/a.md", "x/_archive/a.md",
             "_archive/a.md", "docs/_archive", "docs/a.md", ".ai-harness/rules/a.md",
             "tasks/a.md", "tasks/handoffs/a.md", "tasks/sessions/a.md", "tasks/dispatch/a.md",
             "tasks/runner/a.md", "tasks/archive/a.md", "tasks/plan-archive.md",
             "tasks/plan_archive/a.md", "tasks/plan-archived.md", "tasks/handoffs",
             "tasks/handoffs-extra/a.md", "other/a.md", "", "Docs/a.md")
    return [[p, es._is_history_path(p), es._derive_doc_category(p), es._derive_layer(p)]
            for p in paths]


def _logical(tmp):
    return [[root, rel, es._logical_metadata_path(root, rel)]
            for root in ("repo", "repo/docs", "repo/tasks", "repo/.ai-harness", "repo/docs/")
            for rel in ("", "a.md", "docs/a.md", "tasks", ".ai-harness/r.md")]


def _scope(tmp):
    return [[scope, [es._is_within_path_scope(p, scope) for p in RELS]] for scope in
            ("", "  ", ".", "././docs/", " docs\\deep ", "docs", "docs/a.md", "doc",
             "/docs", "../docs", "docs/../a.md", "**/*.md", "*.md", "docs/?.md", "[ab].md")]


def _walk(mode):
    def run(tmp):
        root = tmp / "archive"
        if mode == "missing":
            return list(es._walk_archive(root, (), ()))
        root.mkdir()
        for name in ("z.md", "a.md", ".hidden.md", "deep/b.md", "deep/.secret.md", "note.txt",
                     "blocked.md", ".hidden-dir/c.md"):
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("synthetic", encoding="ascii")
        (root / "link.md").symlink_to(root / "a.md")
        (root / "link-dir").symlink_to(root / "deep", target_is_directory=True)
        (root / "broken.md").symlink_to(root / "absent.md")
        if mode == "not_dir":
            return list(es._walk_archive(root / "a.md", (), ()))
        if mode == "order":
            with mock.patch.object(Path, "rglob", return_value=iter(
                    [root / p for p in ("z.md", "deep", "a.md", "deep/b.md")])):
                return list(es._walk_archive(root, (), ()))
        include = ("**/*.md",) if mode in ("include", "exclude") else ()
        exclude = ("deep/**", ".*", "link*") if mode == "exclude" else ()
        if mode == "unreadable":
            original = Path.open
            def denied(path, *args, **kwargs):
                if path == root / "blocked.md":
                    raise PermissionError(f"unreadable {path}")
                return original(path, *args, **kwargs)
            with mock.patch.object(Path, "open", denied):
                return {"walk": sorted(es._walk_archive(root, (), ())), "read": observe(
                    lambda _: (root / "blocked.md").read_text(), tmp)}
        return sorted(es._walk_archive(root, include, exclude))
    return run


CASES = {f"chunk.{name}": _chunk(raw, size, overlap) for name, raw, size, overlap in (
    ("empty", "", 4, 0), ("zero", "abc", 0, 0), ("negative", "abc", -1, 0),
    ("negative_overlap", "abc", 4, -1), ("equal_overlap", "abc", 4, 4),
    ("larger_overlap", "abc", 4, 5), ("empty_invalid", "", 0, 0),
    ("equal", "abcd", 4, 0), ("larger", "abc", 9, 0), ("unit", "abc", 1, 0),
    ("overlap", "abcdefghij", 4, 2), ("max_overlap", "abcdef", 4, 3),
    ("paragraph", "abc\n\ndefghij", 8, 1), ("tiny_paragraph", "a\n\nbcdefghi", 6, 2),
    ("sentence", "Ab. Cd! Ef? Gh.", 9, 1),
    ("paragraph_at_overlap", "ab\n\ncdefgh", 6, 2), ("sentence_at_overlap", "A. bcdefghij", 6, 3),
    ("unicode", "\u00e9\u0301\uba85\U0001f680. \u4e2d\u6587\u3002 abc", 5, 1),
    ("surrogate", "\ud800", 4, 0))}
CASES.update({f"glob.{name}": _glob(spec) for name, spec in (
    ("none", None), ("empty", ""), ("space", " , , "), ("comma", " *.md, docs/**, ,a.txt "),
    ("whitespace", "*.md *.txt"), ("star", "*"), ("recursive", "**/*.md"),
    ("question", "?.md"), ("classes", "[ab].md,[!a].txt"), ("trailing", "docs/"),
    ("escaped", r"a.+^$(){}|\x"), ("malformed", "["))})
CASES.update({"paths.lookalikes": lambda tmp: [
    [p, es._is_history_path(p), es._derive_doc_category(p), es._derive_layer(p)]
    for p in (".ai-harness-x/a.md", ".ai-harnessa.md", "docsx/a.md", "tasksx/a.md",
              "docs/decisionsx/a.md")],
    "paths.scope_dotdot": lambda tmp: [es._is_within_path_scope(rel, scope) for rel, scope in (
        ("a/../b", "*/../*"), ("../docs/a.md", "../docs"), ("docs/../a.md", "docs/../a.md"))]})
CASES.update({"paths.classification": _paths, "paths.logical": _logical, "paths.scope": _scope})
CASES.update({f"walk.{mode}": _walk(mode) for mode in
              ("all", "include", "exclude", "order", "missing", "not_dir", "unreadable")})
CASES["version.shapes"] = lambda tmp: [es._int_ver(v) for v in
                                      ("5", " 05 ", "+3", "-2", "1.2", "", "v5", None,
                                       True, 3.9, "\u0665")]
CASES.update({f"title.{name}": lambda tmp, text=text: es._extract_title_and_frontmatter(text)
              for name, text in (
                  ("none", "plain"), ("empty", ""), ("heading", "## no\n# First  \n# Second"),
                  ("frontmatter", "---\ntitle: ' Title '\ncreated: 2026-06-06\n---\n# Other"),
                  ("blank_title", "---\ntitle: ''\n---\n# Fallback"),
                  ("empty_block", "---\n---\n# Heading"),
                  ("malformed", "---\ntitle: Missing end\n# Fallback"),
                  ("ignored_line", "---\nbroken\ntitle: Kept\n---\n"),
                  ("lists", "---\ntitle: [a, b]\ntags:\n  - x\n  - y\n---\n# Fallback"),
                  ("crlf", "---\r\ntitle: CRLF\r\n---\r\n# Heading\r\n"),
                  ("bom", "\ufeff---\ntitle: BOM\n---\n# Heading"),
                  ("unicode", "---\ntitle: \uba85\n---\n# \u00e9"))})
CASES["created.shapes"] = lambda tmp: [es._doc_created_ordinal(v) for v in (
    None, "", "{", "[]", "null", "{}", *[json.dumps({"created": v}) for v in (
        None, "", 0, 20260606, False, [], {}, "2026-06-06", "2026-06-06T12:00:00",
        "2026-06-06 12:00:00+09:00", "2026-06-06Z", "20260606", "2026-W23-6",
        "2026-6-6", "2024-02-29", "2025-02-29", "0001-01-01", "9999-12-31", "invalid")])]


# Added parity witnesses carry their input cells so Rust replays the Python oracle.
def _parity(cell):
    def run(tmp):
        op = cell["op"]
        if op == "title":
            result = es._extract_title_and_frontmatter(cell["text"])
        elif op == "chunk":
            result = [asdict(c) for c in es._chunk_text(
                cell["text"], size=cell["size"], overlap=cell["overlap"])]
        elif op == "created":
            result = es._doc_created_ordinal(json.dumps({"created": cell["text"]}))
        elif op == "paths":
            result = [es._is_history_path(cell["text"]),
                      es._derive_doc_category(cell["text"]), es._derive_layer(cell["text"])]
        elif op == "strip":
            result = [es._compile_globs(cell["text"]),
                      es._is_within_path_scope("docs/a.md", cell["scope"])]
        elif op == "status":
            from types import SimpleNamespace
            archive = SimpleNamespace(root_path="repo", historical_glob=())
            result = es.ExternalStore._document_metadata(
                None, archive, "docs/a.md", cell["text"])[3]
        elif op == "fnmatch":
            result = [es._matches_any(p, (cell["pattern"],)) for p in cell["paths"]]
        elif op == "regex":
            compiled = es._glob_to_regex(cell["pattern"])
            result = [compiled.pattern,
                      [es._matches_regex_any(p, (compiled,)) for p in cell["paths"]]]
        else:
            raise AssertionError(op)
        return {"input": cell, "output": result}
    return run


_PARITY_CELLS = {}
for _i, _text in enumerate(("#\u001ftitle", "#\u001c\u001dname\n", "#\u0085x",
                           "# title\u001f", "---\ntitle: '  '\n---\n# Fallback")):
    _PARITY_CELLS[f"heading_{_i}"] = {"op": "title", "text": _text}
for _i, _text in enumerate(("ab.\u001fcdefghij", "ab\u3002 cdefghij")):
    _PARITY_CELLS[f"sentence_{_i}"] = {"op": "chunk", "text": _text,
                                      "size": 8, "overlap": 2}
for _i, _text in enumerate(("tasks/handoffs\n", "tasks/plan-archive\n",
                           "tasks/handoffs\n\n", "tasks/handoffs-extra\n")):
    _PARITY_CELLS[f"dollar_{_i}"] = {"op": "paths", "text": _text}
_PARITY_CELLS["strip"] = {"op": "strip", "text": "\u001c*.md\u001f,\u001e,\u001ddocs/**\u001f",
                           "scope": "\u001cdocs\u001f"}
for _i, _field in enumerate(("status: '\u001farchived\u001c'",
                            "source: '\u001dmirrored-summary\u001e'",
                            "status: '\u001factive\u001c'")):
    _PARITY_CELLS[f"status_{_i}"] = {"op": "status", "text": f"---\n{_field}\n---\n# Title"}
for _i, _text in enumerate(("2024W09", "2024-W09", "2024W094", "2024-W094", "2024W09-4",
                           "2024-W53", "2020-W53", "2024-+1-01", "+024-01-01",
                           "2024-01-+1", "2024W+94", "2024-W0-1", "20240229",
                           "2024-W09-4", "\u0662024-01-01")):
    _PARITY_CELLS[f"date_{_i}"] = {"op": "created", "text": _text}
_CLASS_PATHS = ("a.md", "b.md", "x.md", "d.md", "&.md", "~.md", "^.md", "].md", "[.md",
                "-.md", "|.md", "\\.md", "/.md", ":.md", ".md", "a", "x", "-", "\n")
for _i, _pattern in enumerate(("[a&&b].md", "[a~~a].md", "[^x].md", "[]x].md", "[!]x].md",
                              "[!z-a].md", "[xz-a].md", "[z-a].md", "[a-].md", "[-a].md",
                              "[a--b].md", "[--/].md", "[a-c-e].md", "[[x].md", "[a|b].md",
                              r"[\].md", r"[\-a].md", "[[:alpha:]].md", "[!a-].md", "[!x]",
                              "[!-a].md", "[a-c--e].md", "[!--a].md")):
    _PARITY_CELLS[f"fnmatch_{_i}"] = {"op": "fnmatch", "pattern": _pattern,
                                     "paths": _CLASS_PATHS}
for _i, _pattern in enumerate(("[a&&b].md", "[a~~a].md", "[[x].md", "[a*].md", "[]x].md",
                              "[^x].md", "[!x].md", "**/*.md")):
    _PARITY_CELLS[f"regex_{_i}"] = {"op": "regex", "pattern": _pattern,
                                   "paths": (*_CLASS_PATHS, "a.md\n", "a.md\n\n")}
CASES.update({f"parity.{name}": _parity(cell) for name, cell in _PARITY_CELLS.items()})

RECORDS = json.loads(FIXTURE.read_text(encoding="ascii")) if FIXTURE.exists() else {}


def test_every_case_has_a_frozen_record():
    assert sorted(RECORDS) == sorted(CASES)


@pytest.mark.parametrize("name", sorted(CASES))
def test_reference_matches_frozen_record(name, tmp_path):
    assert observe(CASES[name], tmp_path) == RECORDS[name]
