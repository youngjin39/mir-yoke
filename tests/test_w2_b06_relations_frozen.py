"""Declared graph oracle captured from the unmodified Python reference, never a port."""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
from pathlib import Path

import pytest

from mir.cli.relations import main
from mir.core import relations as r

FIXTURE = Path(__file__).parent / "../native/handoff-packet/tests/fixtures/w2/b06-relations.json"
ROWS = [["A", "has_req", "R"], ["R", "realized_by", "M"],
        ["M", "implemented_in", "src/m.py"], ["R", "verified_by", "tests/t.py::one"],
        ["A", "depends_on", "Z"], ["Z", "depends_on", "A"], ["A", "has_req", "B"],
        ["A", "has_req", "R"], ["B", "governed_by", "D"], ["B", "affects", "A"]]
PURPOSES = list(r._FORWARD)


def setup(tmp, rows=ROWS, raw=None, profile=""):
    for path in ("src/m.py", "tests/t.py", ".mir/repo-profile.toml", "spec/graph.yaml"):
        target = tmp / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("", encoding="ascii")
    (tmp / ".mir/repo-profile.toml").write_text(profile, encoding="ascii")
    (tmp / "spec/graph.yaml").write_text(
        raw if raw is not None else json.dumps({"edges": rows}), encoding="ascii")


def compact(value):
    if isinstance(value, str) and len(value) > 900:
        return {"bytes": len(value.encode()), "sha256": hashlib.sha256(value.encode()).hexdigest(),
                "first": value[:120], "last": value[-120:]}
    return value


def observe(case, tmp):
    try:
        return {"value": case(tmp)}
    except Exception as exc:  # noqa: BLE001 - freeze reference exception class and message
        return {"error": [type(exc).__name__, str(exc).replace(str(tmp), "<tmp>")]}


def grid(cases):
    def run(tmp):
        result = []
        for index, case in enumerate(cases):
            child = tmp / str(index)
            child.mkdir()
            result.append(observe(case, child))
        return result
    return run


def query(tmp, anchor="A", purpose="implementation", rows=ROWS, raw=None, profile="", **kw):
    setup(tmp, rows, raw, profile)
    return r.query_relations(anchor, purpose, root=tmp, **kw)


def bundle(tmp, anchors=None, purposes=None, rows=ROWS, **kw):
    setup(tmp, rows)
    return r.bundle_relations(anchors if anchors is not None else ["A"],
                              purposes if purposes is not None else PURPOSES, root=tmp, **kw)


def render(tmp, kind, budget, bundled=False):
    rows = ROWS + [["A", "has_req", f"N{i}" + "\u00e9" * 150] for i in range(8)]
    value = bundle(tmp, rows=rows) if bundled else query(tmp, rows=rows)
    before = json.dumps(value, sort_keys=True)
    output = getattr(r, kind)(value, budget)
    return [compact(output), before == json.dumps(value, sort_keys=True)]


def cli(tmp, argv):
    setup(tmp)
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = main([*argv, *(["--root", str(tmp)] if argv and argv[0] in
                                 ("query", "bundle") and "--help" not in argv else [])])
        except SystemExit as exc:
            code = exc.code
    return [code, compact(out.getvalue().replace(str(tmp), "<tmp>")),
            compact(err.getvalue().replace(str(tmp), "<tmp>"))]


def paths(tmp, mode):
    setup(tmp, profile='[paths]\nprotected_paths=["private"]\n')
    (tmp / "private").mkdir()
    (tmp / "private/g.yaml").write_text("edges: []")
    (tmp / "outside").mkdir()
    (tmp / "outside/g.yaml").write_text("edges: []")
    root = tmp / "root"
    root.mkdir()
    (root / "link").symlink_to(tmp / "outside", target_is_directory=True)
    (root / "file.yaml").symlink_to(tmp / "outside/g.yaml")
    (tmp / "alias.yaml").symlink_to(tmp / "private/g.yaml")
    if mode == "endpoint":
        return [r._validate_endpoint(v, root, force_file=True) for v in
                ["link/g.yaml", "link", "missing", "../outside/g.yaml", ".env", "ID"]]
    if mode == "profile":
        (root / ".mir").mkdir()
        (root / ".mir/repo-profile.toml").symlink_to(tmp / ".mir/repo-profile.toml")
        return r._profile_protections(root)
    return r.query_relations("A", "implementation", root=root if mode in
                             ("link/g.yaml", "file.yaml") else tmp, graph=mode)


def helper_values(tmp):
    setup(tmp)
    edge = r.Edge("A", "has_req", "B", None, {"database": "synthetic", "sources": [
        {"source_path": "docs/a.md", "summary": "\u00e9", "reason": "declared"}]})
    value = r._result("A", "implementation", "hash", "custom.yaml", [edge], [], ["A"])
    return [edge.as_dict(), r._render_edge(edge.as_dict(), "custom.yaml"),
            r.render_human(value, 6000), r._render_source({"memory_db": "synthetic"}),
            r._source_line(r.DEFAULT_GRAPH, 2), r._source_line("custom.yaml", 2),
            r._notices({"z": 2, "a": 1}, ["extra"])]


CASES = {
    "query.purposes_depths": grid([
        lambda tmp, p=p, d=d: query(tmp, purpose=p, depth=d)
        for p in PURPOSES for d in [None, 1, 2, 3, 4]]),
    "query.anchors": grid([lambda tmp, a=a: query(tmp, anchor=a) for a in
                           ["", None, "x" * 4097, "A\n", "A\u0085", "/abs", "../x",
                            "C:\\x", ".env", "secrets/x", "unknown", "src/m.py"]]),
    "query.limits": grid([lambda tmp, k=k, v=v: query(tmp, **{k: v}) for k, vals in
                          [("depth", [0, 5, True, "1"]), ("max_edges", [0, 65, True, 1, 64]),
                           ("max_bytes", [1023, 16001, False, 1024, 16000])]
                          for v in vals]),
    "query.bad_purpose": lambda tmp: query(tmp, purpose="other"),
    "graph.invalid": grid([lambda tmp, raw=raw: query(tmp, raw=raw) for raw in
                           ["", "[", "[]", "{1: x}", "{}", "edges: []\nedges: []",
                            "edges: {}", "edges: [[A, has_req]]", "edges: [[A, 1, B]]",
                            'edges: [[A, has_req, "B\\n"]]', "#" * (r.MAX_GRAPH_BYTES + 1),
                            "edges: " + json.dumps([["A", "has_req", "B"]] * 10001)]]),
    "graph.paths": grid([lambda tmp, m=m: paths(tmp, m) for m in
                         ["missing", "../outside", ".env", "private/g.yaml", "alias.yaml",
                          "link/g.yaml", "file.yaml", "endpoint", "profile"]]),
    "profile.invalid": grid([lambda tmp, p=p: query(tmp, profile=p) for p in
                             ["[", "paths=1", '[paths]\nprotected_paths="x"',
                              '[paths]\nprotected_paths=["../x"]',
                              '[paths]\nprotected_paths=[""]', "#" * 65537,
                              "[paths]\nprotected_paths=" + json.dumps(["x"] * 257)]]),
    "profile.collections": lambda tmp: query(tmp, profile=(
        '[paths]\nprotected_paths=["src", "src"]\n[boundaries]\nsecrets=["tests/*"]\n'
        '[preserve]\nagent_memory_paths=["private"]\n')),
    "query.skipped": lambda tmp: query(tmp, rows=ROWS + [["A", "implemented_in", v] for v in
        [".env", "secrets/key", "../bad", "absent", "src", "private/key"]],
        profile='[paths]\nprotected_paths=["private"]'),
    "query.locators": grid([lambda tmp, a=a: query(tmp, anchor=a, purpose="verification",
        max_edges=1, rows=ROWS + [["R", "verified_by", "tests/t.py::two"]]) for a in
        ["tests/t.py", "./tests/t.py::one", "tests/t.py::absent"]]),
    "bundle.routes": grid([lambda tmp, a=a, p=p: bundle(tmp, anchors=a, purposes=p)
        for a, p in [([], PURPOSES), (["A", "B"], PURPOSES), (["A"], []), (["A"], ["impact"]),
                     (["A"], ["other", "impact"]), (["unknown"], PURPOSES),
                     (["A", "A"], ["implementation", "verification", "implementation"]),
                     (["src/m.py"], ["implementation", "verification"]),
                     (["src/m.py::x"], PURPOSES), (["missing/file"], PURPOSES),
                     ("A", PURPOSES), (["../bad"], PURPOSES)]]),
    "bundle.unavailable": lambda tmp: r.bundle_relations(
        ["A"], PURPOSES, root=tmp),
    "bundle.protected": lambda tmp: bundle(tmp, anchors=[".env"]),
    "profile.values": lambda tmp: (setup(tmp, profile=(
        '[paths]\nprotected_paths=["private", "private"]\n[boundaries]\nsecrets=["keys/*"]\n'
        '[preserve]\nagent_memory_paths=["local"]')), list(r._profile_protections(tmp)))[1],
    "bundle.empty_facet": lambda tmp: bundle(tmp, rows=[["A", "has_req", "B"]]),
    "bundle.ambiguous": lambda tmp: bundle(tmp, anchors=["src/m.py"], rows=ROWS +
                                          [["OTHER", "implemented_in", "src/m.py"]]),
    "bundle.limits": grid([lambda tmp, n=n: bundle(tmp, max_edges=n) for n in [1, 2, 16]]),
    "render.bytes": grid([lambda tmp, k=k, n=n, b=b: render(tmp, k, n, b)
        for b, kinds in [(False, ["render_json", "render_human"]),
                         (True, ["render_json", "render_bundle_human"])]
        for k in kinds for n in [100, 1024, 6000, 16000]]),
    "helpers.values": helper_values,
    "helpers.protection": lambda tmp: [[v, r._protected(tuple(v.split("/")), ("private",)),
        r._matches_protection(v, "private"), r._endpoint_path(v), r._normalized_locator(v),
        r._has_control_characters(v)] for v in
        [".ENV/x", "secrets/x", ".mir/memory.db-wal", "private/a", "src/./m.py::x", "A\u2029"]],
    "helpers.paths": grid([lambda tmp, v=v: str(r._safe_relative_path(v, label="test"))
                           for v in [None, "", ".", "C:\\x", "a\\b", "./src/m.py"]]),
    "helpers.patterns": grid([lambda tmp, v=v: r._profile_pattern(v)
                              for v in [3, "/abs", ".", "x" * 4097, "a\t", "a\\b"]]),
    "helpers.roots": grid([lambda tmp, v=v: r._resolve_root(tmp / v if isinstance(v, str) else v)
                           for v in [3, "missing-root-that-does-not-exist"]]),
    "helpers.source_invalid": lambda tmp: r._render_source({}),
    "cli.arguments": grid([lambda tmp, a=a: cli(tmp, a) for a in
        [[], ["--help"], ["query", "--help"], ["bundle", "--help"], ["other"],
         ["query", "A"], ["query", "A", "--purpose", "other"],
         ["query", "A", "--purpose", "impact", "--depth", "bad"],
         ["query", "A", "--purpose", "impact", "--graph", "../escape"],
         ["query", "A", "--purpose", "impact", "--graph", "x", "--memory"]]]),
    "cli.commands": grid([lambda tmp, a=a: cli(tmp, a) for a in
        [[cmd, anchor, "--purpose", p, *extra] for cmd, anchor, p in
         [("query", "A", p) for p in PURPOSES] + [("query", "unknown", "impact"),
          ("bundle", "A", "implementation")] for extra in [[], ["--json"]]]]),
    "cli.bundle_graph": grid([lambda tmp, x=x: cli(tmp, ["bundle", "A", "--purpose",
        "implementation", "--purpose", "verification", *x]) for x in [[], ["--json"]]]),
}
RECORDS = json.loads(FIXTURE.read_text(encoding="ascii")) if FIXTURE.exists() else {}


def test_every_case_has_a_frozen_record():
    assert sorted(RECORDS) == sorted(CASES)


@pytest.mark.parametrize("name", sorted(CASES))
def test_reference_matches_frozen_record(name, tmp_path):
    assert observe(CASES[name], tmp_path) == RECORDS[name]
