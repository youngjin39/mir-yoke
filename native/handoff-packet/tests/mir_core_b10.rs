//! Frozen Python oracle replay; library only.
use handoff_packet::mir_core::memory::{distill, predicates, sanitize};
use serde_json::{Value, json};
use std::collections::BTreeSet;
const ORACLE: &str = include_str!("fixtures/w2/b10-pure-helpers.json");
const ALIASES: &str = "use uses used using call calls called calling import imports imported extend extends extended implement implements implemented reference references referenced";
const DEPENDS: &[&str] = &[
    "depend on",
    "depends on",
    "depended on",
    "depending on",
    "depend_on",
];
const DEFERRED: &[&str] = &[];
#[rustfmt::skip]
const DISTILL_CASES: &[(&str, &str)] = &[
    ("quote.tokens", r#"["","---","a\"b","adr-99","a_b 12","\u00bf\u00c0\uffff\ud800\udc00","\uba85\u0301 \ud83d\ude80","a\nb\tc"]"#),
    ("fts.empty", r#"[null,""," \t","\"\"","\"---\"","-:*()"]"#),
    ("fts.operators", r#"["a OR b NOT c AND d","NEAR(a b, 2)","title:adr-99* +x ^y","a\"b c\"d"]"#),
    ("fts.quotes", r#"["before \"two-words\" after","\"a\" \"b\"","\"unclosed","a\"\"b","\"---\" tail"]"#),
    ("fts.unicode", r#"["\u00bf\u00c0\uffff\ud800\udc00","\"\uba85\u0301 \ud83d\ude80\"","\u0000a\u007fb"]"#),
    ("frontmatter.absent", r#"["","body","---\nx: y\n---","\ufeff---\nx: y\n---\n"," \n---\nx: y\n---\n","---\rX\r---\r"]"#),
    ("frontmatter.empty", r#"["---\n---\n","---\n\n---\n","---\n# comment\n \n---\n"]"#),
    ("frontmatter.crlf", r#""---\r\nx: y\r\n---\r\nbody""#),
    ("frontmatter.line_breaks", r#""---\r\na:\r\n  - x\r\n  - y\r\nb: 1\u0085c: 2\u000bd: 3\u2028e: [p, q]\r\n---\r\n""#),
    ("frontmatter.scalars", r#""---\ndate: 2026-01-02\nflag: true\nnull: null\nnumber: 3\nquoted: 'a:b'\ndouble: \"x\"\ncomment: a # kept\n---\n""#),
    ("frontmatter.lists", r#""---\na: [one, 'two', \"three\", ,]\nb:\n  - x\n  -\ty\nc:\n# done\nd: []\ne:\n  - \"\"\n  - z\n---\n""#),
    ("frontmatter.malformed", r#""---\nbroken\n: empty-key\nx: [unclosed\nx: replacement\nq: [\"a,b\", c]\nnot-list: [a] trailing\n---\n---\ny: ignored\n---\n""#),
    ("frontmatter.nested", r#""---\nouter:\n  inner: value\nseq:\n - wrong-indent\nblock: |\n  text\nlast:\n---\n""#),
    ("adr_slug.paths", r#"["docs/decisions/adr-05-foo.md","a.tar.md",".hidden","README","","a/"]"#),
    ("never.paths", r#"["docs/_archive/","docs/_archive/README.md","docs/_archive/a/b.md","docs/_archive","docs/_archived/a.md","Docs/_archive/a.md","./docs/_archive/a.md","docs/_archive/../live.md",""]"#),
    ("whitelist.boundaries", r#"null"#),
    ("constants", r#"null"#),
    ("links.boundaries", r#"["docs/a.md docs/a_b-1/../x.md","Docs/a.md docs/a.MD","docs/.md docs/a.mdX docs/a+b.md docs/\u00e9.md"]"#),
    ("triples.empty", r#"[]"#),
    ("triples.scalars", r#"[["uses"," x "],["blank"," \n"],["none",null],["bool",false],["number",0],["date","2026-01-02"],["nested",{"a":"b"}]]"#),
    ("triples.members", r#"[["depends on",["a","b","",null,false,0," ",["c"],{"x":1}]],["empty",[]],["tail","z"]]"#),
    ("triples.reserved", r#"[["memory_relations",["skip"]],["'memory_relations'","skip"],["\"memory_relations\"","skip"],["Memory_relations","keep"],[" memory_relations ","skip"],["ordinary","keep"]]"#),
    ("triples.parsed", r#""---\nuses: [a, b]\nimports:\n  - c\n  - d\n---\n""#),
];
fn aliases() -> impl Iterator<Item = &'static str> {
    ALIASES.split_whitespace().chain(DEPENDS.iter().copied())
}
fn check(name: &str, actual: Value) {
    let oracle: Value = serde_json::from_str(ORACLE).unwrap();
    assert_eq!(json!({"value": actual}), oracle[name], "{name}");
}
#[test]
#[rustfmt::skip]
fn distill_replay() {
    for (name, input) in DISTILL_CASES {
        let input: Value = serde_json::from_str(input).unwrap();
        let strings = || input.as_array().unwrap().iter().map(|v| v.as_str().unwrap_or_default());
        let actual = match *name {
            "constants" => json!([predicates::PREDICATE_MAP.iter().map(|(k,v)| ((*k).to_owned(), json!(v))).collect::<serde_json::Map<_,_>>(), distill::DEFAULT_WHITELIST, distill::NEVER_INGEST_PREFIXES]),
            "adr_slug.paths" => json!(strings().map(distill::_adr_slug).collect::<Vec<_>>()),
            "never.paths" => json!(strings().map(distill::_is_never_ingested).collect::<Vec<_>>()),
            "whitelist.boundaries" => {
                let paths = ["", "docs/_archive/a.md", "docs/_archive/", "docs/_archive", "docs/decisions/adr-.md", "docs/decisions/adr-a/b.md", "docs/a.md", "x.md", "x.txt"];
                let globs: &[&[&str]] = &[&[], &["*"], &["docs/decisions/adr-*.md"], &["docs/**/*.md"], &["*.txt", "?.md"], distill::DEFAULT_WHITELIST];
                json!(globs.iter().flat_map(|g| paths.map(|p| distill::_matches_whitelist(p,g).unwrap())).collect::<Vec<_>>())
            }
            "links.boundaries" => json!(strings().map(|s| distill::links(s).unwrap()).collect::<Vec<_>>()),
            "quote.tokens" => json!(strings().map(|s| distill::_quote_fts_phrase(s).unwrap()).collect::<Vec<_>>()),
            n if n.starts_with("fts.") => json!(strings().map(|s| distill::sanitize_fts_query(s).unwrap()).collect::<Vec<_>>()),
            n if n.starts_with("frontmatter.") => {
                let parse = |s| json!(distill::_parse_frontmatter(s).unwrap().into_iter().collect::<serde_json::Map<_,_>>());
                if input.is_array() { json!(strings().map(parse).collect::<Vec<_>>()) } else { parse(input.as_str().unwrap()) }
            }
            n if n.starts_with("triples.") => {
                let fm = if input.is_string() { distill::_parse_frontmatter(input.as_str().unwrap()).unwrap() } else {
                    input.as_array().unwrap().iter().map(|p| (p[0].as_str().unwrap().to_owned(),p[1].clone())).collect()
                };
                json!(distill::_frontmatter_to_triples(if *name == "triples.parsed" { "adr-list" } else { "adr-01" }, &fm))
            }
            _ => panic!("unhandled {name}"),
        };
        check(name, actual);
    }
}
#[test]
fn predicates_replay() {
    for alias in aliases() {
        let title = alias
            .split_inclusive([' ', '_'])
            .map(|word| {
                let mut chars = word.chars();
                format!("{}{}", chars.next().unwrap().to_uppercase(), chars.as_str())
            })
            .collect::<String>();
        let inputs = [
            alias.to_owned(),
            alias.to_uppercase(),
            format!(" \t{title}\n"),
        ];
        check(
            &format!("canonicalize.{alias}"),
            json!(inputs.map(|s| predicates::canonicalize(&s))),
        );
    }
    check(
        "canonicalize.unknown",
        json!(
            [
                "",
                " \n",
                "Owns",
                "depend  on",
                "depend\ton",
                "\u{130}",
                "USES!"
            ]
            .map(predicates::canonicalize)
        ),
    );
    check(
        "canonicalize.python_space",
        json!(
            [
                "\u{1c}uses\u{1f}",
                "\u{1d}\u{1e}USE",
                "\u{a0}calls\u{2003}",
                "\u{85}imports"
            ]
            .map(predicates::canonicalize)
        ),
    );
    // Also check the predicate portion of the mixed constants record.
    let oracle: Value = serde_json::from_str(ORACLE).unwrap();
    let map: serde_json::Map<String, Value> = predicates::PREDICATE_MAP
        .iter()
        .map(|(k, v)| ((*k).into(), json!(v)))
        .collect();
    assert_eq!(json!(map), oracle["constants"]["value"][0]);
}
#[test]
fn sanitize_replay() {
    let run = |src| sanitize::sanitize(src, None).unwrap();
    check(
        "sanitize.default",
        json!(run(
            "a<private>x\ny</private>b<secret>s</secret><noindex>n</noindex>"
        )),
    );
    check(
        "sanitize.scopes",
        json!(
            [
                Some("ephemeral"),
                Some("persistent"),
                Some("Persistent"),
                Some(""),
                Some("unknown"),
                None
            ]
            .map(|scope| sanitize::sanitize(
                "<PRIVATE>x\ny</PRIVATE><SeCrEt>s\nt</sEcReT><NOINDEX>n\nm</NOINDEX>",
                scope
            )
            .unwrap())
        ),
    );
    check(
        "sanitize.empty",
        json!(run(
            "<private></private><secret></secret><noindex></noindex>"
        )),
    );
    check(
        "sanitize.boundaries",
        json!(run(
            "<private> </private><secret>\n</secret><noindex>\t</noindex><private>a</private><private>b</private><private>x<private>y</private>z</private>"
        )),
    );
    check(
        "sanitize.near_miss",
        json!(run(
            "<private >x</private><secret attr='x'>y</secret><noindex/><private>open</secret></privateX> &lt;secret&gt; <SECRET>open"
        )),
    );
    check(
        "sanitize.synthetic_pii",
        json!(run(&format!(
            "test@example.invalid sk-{} api_key=synthetic-token AKIA0000000000000000 +1-202-555-0100 /home/example/file C:\\example\\file",
            "x".repeat(32)
        ))),
    );
}
#[test]
fn exact_record_accounting() {
    assert_eq!(DISTILL_CASES.len(), 23);
    let oracle: Value = serde_json::from_str(ORACLE).unwrap();
    let replayed: BTreeSet<String> = aliases()
        .map(|s| format!("canonicalize.{s}"))
        .chain(
            [
                "canonicalize.unknown",
                "canonicalize.python_space",
                "sanitize.default",
                "sanitize.scopes",
                "sanitize.empty",
                "sanitize.boundaries",
                "sanitize.near_miss",
                "sanitize.synthetic_pii",
            ]
            .map(String::from),
        )
        .chain(DISTILL_CASES.iter().map(|(name, _)| (*name).to_owned()))
        .collect();
    // Python-only exemption: Rust's &str excludes None and its AttributeError.
    let exempt = ["canonicalize.invalid"];
    assert_eq!((replayed.len(), exempt.len(), DEFERRED.len()), (56, 1, 0));
    let mut accounted = replayed.clone();
    for name in exempt.iter().chain(DEFERRED) {
        assert!(accounted.insert((*name).into()), "duplicate {name}");
    }
    assert_eq!(accounted.len(), 57);
    assert_eq!(
        accounted,
        oracle.as_object().unwrap().keys().cloned().collect()
    );
    for name in accounted {
        let reason = if replayed.contains(&name) {
            "replayed"
        } else if name == exempt[0] {
            "exempt: Python None AttributeError is excluded by Rust &str"
        } else {
            "deferred"
        };
        println!("{name}: {reason}");
    }
}
