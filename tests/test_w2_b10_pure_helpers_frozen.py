"""Pure memory helper oracle captured from the unmodified Python reference.

Never regenerate from a port. This reference has tag redaction, no PII masking
or marker editing helpers, and no native frontmatter/hash helpers in distill.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import pytest

from mir.core.engine.memory import distill, predicates
from mir.core.engine.memory.sanitize import sanitize

FIXTURE = Path(__file__).parent / "../native/handoff-packet/tests/fixtures/w2/b10-pure-helpers.json"


def _calls(fn, values):
    return lambda tmp: [fn(value) for value in values]


def _triples(fm):
    return lambda tmp: [asdict(t) for t in distill._frontmatter_to_triples("adr-01", fm)]


# Explicit inputs, independent of the production alias table (mutation-sensitive).
ALIASES = ("use uses used using call calls called calling import imports imported "
           "extend extends extended implement implements implemented "
           "reference references referenced").split()
ALIASES += ["depend on", "depends on", "depended on", "depending on", "depend_on"]
CASES = {
    f"canonicalize.{alias}": _calls(predicates.canonicalize,
                                    [alias, alias.upper(), " \t" + alias.title() + "\n"])
    for alias in ALIASES
}
CASES.update({
    "canonicalize.unknown": _calls(predicates.canonicalize,
                                  ["", " \n", "Owns", "depend  on", "depend\ton",
                                   "\u0130", "USES!"]),
    "canonicalize.invalid": lambda tmp: predicates.canonicalize(None),
    "sanitize.default": lambda tmp: sanitize(
        "a<private>x\ny</private>b<secret>s</secret><noindex>n</noindex>"),
    "sanitize.scopes": lambda tmp: [sanitize(
        "<PRIVATE>x\ny</PRIVATE><SeCrEt>s\nt</sEcReT><NOINDEX>n\nm</NOINDEX>", consent_scope=s)
        for s in ("ephemeral", "persistent", "Persistent", "", "unknown", None)],
    "sanitize.empty": lambda tmp: sanitize(
        "<private></private><secret></secret><noindex></noindex>"),
    "sanitize.boundaries": lambda tmp: sanitize(
        "<private> </private><secret>\n</secret><noindex>\t</noindex>"
        "<private>a</private><private>b</private><private>x<private>y</private>z</private>"),
    "sanitize.near_miss": lambda tmp: sanitize(
        "<private >x</private><secret attr='x'>y</secret><noindex/>"
        "<private>open</secret></privateX> &lt;secret&gt; <SECRET>open"),
    "sanitize.synthetic_pii": lambda tmp: sanitize(
        "test@example.invalid sk-" + "x" * 32 + " api_key=synthetic-token "
        "AKIA0000000000000000 +1-202-555-0100 /home/example/file C:\\example\\file"),
    "quote.tokens": _calls(distill._quote_fts_phrase,
                          ["", "---", 'a"b', "adr-99", "a_b 12", "\u00bf\u00c0\uffff\U00010000",
                           "\uba85\u0301 \U0001f680", "a\nb\tc"]),
    "fts.empty": _calls(distill.sanitize_fts_query,
                        [None, "", " \t", '""', '"---"', "-:*()"]),
    "fts.operators": _calls(distill.sanitize_fts_query,
                            ["a OR b NOT c AND d", "NEAR(a b, 2)",
                             "title:adr-99* +x ^y", 'a"b c"d']),
    "fts.quotes": _calls(distill.sanitize_fts_query,
                         ['before "two-words" after', '"a" "b"', '"unclosed',
                          'a""b', '"---" tail']),
    "fts.unicode": _calls(distill.sanitize_fts_query,
                          ["\u00bf\u00c0\uffff\U00010000", '"\uba85\u0301 \U0001f680"',
                           "\x00a\x7fb"]),
    "frontmatter.absent": _calls(distill._parse_frontmatter,
                                ["", "body", "---\nx: y\n---", "\ufeff---\nx: y\n---\n",
                                 " \n---\nx: y\n---\n", "---\rX\r---\r"]),
    "frontmatter.empty": _calls(distill._parse_frontmatter,
                               ["---\n---\n", "---\n\n---\n", "---\n# comment\n \n---\n"]),
    "frontmatter.crlf": lambda tmp: distill._parse_frontmatter("---\r\nx: y\r\n---\r\nbody"),
    "frontmatter.scalars": lambda tmp: distill._parse_frontmatter(
        "---\ndate: 2026-01-02\nflag: true\nnull: null\nnumber: 3\n"
        "quoted: 'a:b'\ndouble: \"x\"\ncomment: a # kept\n---\n"),
    "frontmatter.lists": lambda tmp: distill._parse_frontmatter(
        "---\na: [one, 'two', \"three\", ,]\nb:\n  - x\n  -\ty\n"
        "c:\n# done\nd: []\ne:\n  - \"\"\n  - z\n---\n"),
    "frontmatter.malformed": lambda tmp: distill._parse_frontmatter(
        "---\nbroken\n: empty-key\nx: [unclosed\nx: replacement\n"
        "q: [\"a,b\", c]\nnot-list: [a] trailing\n---\n---\ny: ignored\n---\n"),
    "frontmatter.nested": lambda tmp: distill._parse_frontmatter(
        "---\nouter:\n  inner: value\nseq:\n - wrong-indent\nblock: |\n  text\nlast:\n---\n"),
    "adr_slug.paths": _calls(lambda p: distill._adr_slug(Path(p)),
                             ["docs/decisions/adr-05-foo.md", "a.tar.md", ".hidden",
                              "README", "", "a/"]),
    "never.paths": _calls(distill._is_never_ingested,
                         ["docs/_archive/", "docs/_archive/README.md", "docs/_archive/a/b.md",
                          "docs/_archive", "docs/_archived/a.md", "Docs/_archive/a.md",
                          "./docs/_archive/a.md", "docs/_archive/../live.md", ""]),
    "whitelist.boundaries": lambda tmp: [distill._matches_whitelist(p, globs)
        for globs in ((), ("*",), ("docs/decisions/adr-*.md",), ("docs/**/*.md",),
                      ("*.txt", "?.md"), distill.DEFAULT_WHITELIST)
        for p in ("", "docs/_archive/a.md", "docs/_archive/", "docs/_archive",
                  "docs/decisions/adr-.md", "docs/decisions/adr-a/b.md",
                  "docs/a.md", "x.md", "x.txt")],
    "constants": lambda tmp: [dict(predicates.PREDICATE_MAP), list(distill.DEFAULT_WHITELIST),
                              list(distill.NEVER_INGEST_PREFIXES)],
    "links.boundaries": _calls(distill._LINK_RE.findall,
                               ["docs/a.md docs/a_b-1/../x.md", "Docs/a.md docs/a.MD",
                                "docs/.md docs/a.mdX docs/a+b.md docs/\u00e9.md"]),
    "triples.empty": _triples({}),
    "triples.scalars": _triples({"uses": " x ", "blank": " \n", "none": None, "bool": False,
                                "number": 0, "date": "2026-01-02", "nested": {"a": "b"}}),
    "triples.members": _triples({"depends on": ["a", "b", "", None, False, 0, " ", ["c"], {"x": 1}],
                                "empty": [], "tail": "z"}),
    "triples.reserved": _triples({"memory_relations": ["skip"], "'memory_relations'": "skip",
                                 '"memory_relations"': "skip", "Memory_relations": "keep",
                                 " memory_relations ": "skip", "ordinary": "keep"}),
    "triples.parsed": lambda tmp: [asdict(t) for t in distill._frontmatter_to_triples(
        "adr-list", distill._parse_frontmatter(
            "---\nuses: [a, b]\nimports:\n  - c\n  - d\n---\n"))],
})


def observe(case, tmp: Path) -> dict:
    try:
        return {"value": case(tmp)}
    except Exception as exc:  # noqa: BLE001 - freeze error class and text
        return {"error": [type(exc).__name__, str(exc)]}


RECORDS = json.loads(FIXTURE.read_text(encoding="utf-8")) if FIXTURE.exists() else {}


def test_every_case_has_a_frozen_record():
    assert sorted(RECORDS) == sorted(CASES)


@pytest.mark.parametrize("name", sorted(CASES))
def test_reference_matches_frozen_record(name, tmp_path):
    assert observe(CASES[name], tmp_path) == RECORDS[name]
