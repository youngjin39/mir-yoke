//! Frozen Python oracle replay. Whole distill module deferred by the 360-line cap.
use handoff_packet::mir_core::memory::{predicates, sanitize};
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
const DEFERRED: &[&str] = &[
    "adr_slug.paths",
    "constants",
    "frontmatter.absent",
    "frontmatter.crlf",
    "frontmatter.empty",
    "frontmatter.lists",
    "frontmatter.malformed",
    "frontmatter.nested",
    "frontmatter.scalars",
    "fts.empty",
    "fts.operators",
    "fts.quotes",
    "fts.unicode",
    "links.boundaries",
    "never.paths",
    "quote.tokens",
    "triples.empty",
    "triples.members",
    "triples.parsed",
    "triples.reserved",
    "triples.scalars",
    "whitelist.boundaries",
];
fn aliases() -> impl Iterator<Item = &'static str> {
    ALIASES.split_whitespace().chain(DEPENDS.iter().copied())
}
fn check(name: &str, actual: Value) {
    let oracle: Value = serde_json::from_str(ORACLE).unwrap();
    assert_eq!(json!({"value": actual}), oracle[name], "{name}");
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
    // Also check the predicate portion of the otherwise deferred mixed constants record.
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
        .collect();
    // Python-only exemption: Rust's &str excludes None and its AttributeError.
    let exempt = ["canonicalize.invalid"];
    assert_eq!((replayed.len(), exempt.len(), DEFERRED.len()), (33, 1, 22));
    let mut accounted = replayed.clone();
    for name in exempt.iter().chain(DEFERRED) {
        assert!(accounted.insert((*name).into()), "duplicate {name}");
    }
    assert_eq!(accounted.len(), 56);
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
            "deferred: whole distill module exceeds this slice's line budget"
        };
        println!("{name}: {reason}");
    }
}
