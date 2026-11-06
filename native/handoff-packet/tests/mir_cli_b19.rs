#![forbid(unsafe_code)]
use handoff_packet::mir_cli::policy;
use serde_json::{Value, json};

/// Each record's input mirrors its Python case: argv plus the scripted native result.
fn case(name: &str) -> (Vec<&'static str>, Option<i32>) {
    match name {
        "main.help_long" => (vec!["--help"], None),
        "main.help_short" => (vec!["-h"], None),
        "main.empty" => (vec![], None),
        "main.unknown" => (vec!["unknown"], None),
        "main.help_extra" => (vec!["--help", "extra"], None),
        "main.short_help_extra" => (vec!["-h", "extra"], None),
        "main.resolve_not_first" => (vec!["--help", "resolve"], None),
        "main.resolve_zero" => (vec!["resolve", "--category", "unit"], Some(0)),
        "main.resolve_seven" => (
            vec![
                "resolve",
                "--category",
                "unit",
                "--repo-root",
                "relative-repo",
                "--format",
                "json",
            ],
            Some(7),
        ),
        "main.resolve_bare" => (vec!["resolve"], Some(0)),
        "main.resolve_help_forwarded" => (vec!["resolve", "--help"], Some(7)),
        "main.resolve_unavailable" => (vec!["resolve", "--category", "unit"], None),
        other => panic!("no Rust input for record {other}"),
    }
}

#[test]
fn frozen_policy_records() {
    let records: Value = serde_json::from_str(include_str!("fixtures/w2/b19-policy.json")).unwrap();
    let mut replayed = 0;
    for (name, expected) in records.as_object().unwrap() {
        let (argv, result) = case(name);
        let mut calls: Vec<Vec<String>> = Vec::new();
        let (code, stdout, stderr) = policy::main(&argv, |forwarded| {
            calls.push(forwarded.iter().map(|s| (*s).to_owned()).collect());
            result
        });
        let actual = json!({"value": {
            "exit": code,
            "stdout": String::from_utf8(stdout).unwrap(),
            "stderr": String::from_utf8(stderr).unwrap(),
            "native_argv": calls,
        }});
        assert_eq!(actual, *expected, "{name}");
        replayed += 1;
    }
    assert_eq!(replayed, 12);
}
