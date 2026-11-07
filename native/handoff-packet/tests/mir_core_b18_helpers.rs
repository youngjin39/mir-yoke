use handoff_packet::mir_core::memory::external_store as es;
use serde_json::{Value, json};

const RELS: [&str; 7] = [
    "a.md",
    ".hidden.md",
    "docs/a.md",
    "docs/deep/b.md",
    "a.txt",
    "docs/",
    "b.md",
];
fn observed<T: serde::Serialize>(result: Result<T, es::HelperError>) -> Value {
    match result {
        Ok(value) => json!({"value": value}),
        Err(error) => json!({"error": [error.kind, error.message]}),
    }
}
fn classify(paths: &[&str]) -> Value {
    json!(
        paths
            .iter()
            .map(|p| json!([
                p,
                es::is_history_path(p),
                es::derive_doc_category(p),
                es::derive_layer(p)
            ]))
            .collect::<Vec<_>>()
    )
}
fn replay(name: &str) -> Value {
    let (group, case) = name.split_once('.').unwrap();
    if group == "chunk" {
        let (raw, size, overlap) = match case {
            "empty" => ("", 4, 0),
            "zero" => ("abc", 0, 0),
            "negative" => ("abc", -1, 0),
            "negative_overlap" => ("abc", 4, -1),
            "equal_overlap" => ("abc", 4, 4),
            "larger_overlap" => ("abc", 4, 5),
            "empty_invalid" => ("", 0, 0),
            "equal" => ("abcd", 4, 0),
            "larger" => ("abc", 9, 0),
            "unit" => ("abc", 1, 0),
            "overlap" => ("abcdefghij", 4, 2),
            "max_overlap" => ("abcdef", 4, 3),
            "paragraph" => ("abc\n\ndefghij", 8, 1),
            "tiny_paragraph" => ("a\n\nbcdefghi", 6, 2),
            "sentence" => ("Ab. Cd! Ef? Gh.", 9, 1),
            "paragraph_at_overlap" => ("ab\n\ncdefgh", 6, 2),
            "sentence_at_overlap" => ("A. bcdefghij", 6, 3),
            "unicode" => (
                "\u{e9}\u{301}\u{ba85}\u{1f680}. \u{4e2d}\u{6587}\u{3002} abc",
                5,
                1,
            ),
            _ => panic!("unknown chunk {case}"),
        };
        return observed(es::chunk_text(raw, size, overlap));
    }
    let value = match group {
        "glob" => {
            let spec = match case {
                "none" => None,
                "empty" => Some(""),
                "space" => Some(" , , "),
                "comma" => Some(" *.md, docs/**, ,a.txt "),
                "whitespace" => Some("*.md *.txt"),
                "star" => Some("*"),
                "recursive" => Some("**/*.md"),
                "question" => Some("?.md"),
                "classes" => Some("[ab].md,[!a].txt"),
                "trailing" => Some("docs/"),
                "escaped" => Some(r"a.+^$(){}|\x"),
                "malformed" => Some("["),
                _ => panic!("unknown glob {case}"),
            };
            let patterns = es::compile_globs(spec);
            let compiled = match es::compile_pattern_set(&patterns) {
                Ok(compiled) => compiled,
                Err(e) => return observed::<Value>(Err(e)),
            };
            json!({"patterns": patterns, "regex": compiled,
                "fnmatch": RELS.map(|p| es::matches_any(p, &patterns).unwrap()),
                "regex_match": RELS.map(|p| es::matches_regex_any(p, &compiled).unwrap())})
        }
        "paths" => match case {
            "classification" => classify(&[
                "docs/decisions/a.md",
                "docs/_archive/decisions/a.md",
                "x/_archive/a.md",
                "_archive/a.md",
                "docs/_archive",
                "docs/a.md",
                ".ai-harness/rules/a.md",
                "tasks/a.md",
                "tasks/handoffs/a.md",
                "tasks/sessions/a.md",
                "tasks/dispatch/a.md",
                "tasks/runner/a.md",
                "tasks/archive/a.md",
                "tasks/plan-archive.md",
                "tasks/plan_archive/a.md",
                "tasks/plan-archived.md",
                "tasks/handoffs",
                "tasks/handoffs-extra/a.md",
                "other/a.md",
                "",
                "Docs/a.md",
            ]),
            "lookalikes" => classify(&[
                ".ai-harness-x/a.md",
                ".ai-harnessa.md",
                "docsx/a.md",
                "tasksx/a.md",
                "docs/decisionsx/a.md",
            ]),
            "logical" => json!(
                [
                    "repo",
                    "repo/docs",
                    "repo/tasks",
                    "repo/.ai-harness",
                    "repo/docs/"
                ]
                .iter()
                .flat_map(|root| {
                    ["", "a.md", "docs/a.md", "tasks", ".ai-harness/r.md"]
                        .map(|rel| json!([root, rel, es::logical_metadata_path(root, rel)]))
                })
                .collect::<Vec<_>>()
            ),
            "scope" => json!(
                [
                    "",
                    "  ",
                    ".",
                    "././docs/",
                    " docs\\deep ",
                    "docs",
                    "docs/a.md",
                    "doc",
                    "/docs",
                    "../docs",
                    "docs/../a.md",
                    "**/*.md",
                    "*.md",
                    "docs/?.md",
                    "[ab].md"
                ]
                .map(|s| json!([s, RELS.map(|p| es::is_within_path_scope(p, s).unwrap())]))
            ),
            "scope_dotdot" => json!(
                [
                    ("a/../b", "*/../*"),
                    ("../docs/a.md", "../docs"),
                    ("docs/../a.md", "docs/../a.md")
                ]
                .map(|(p, s)| es::is_within_path_scope(p, s).unwrap())
            ),
            _ => panic!("unknown paths {case}"),
        },
        "version" => json!(
            [
                json!("5"),
                json!(" 05 "),
                json!("+3"),
                json!("-2"),
                json!("1.2"),
                json!(""),
                json!("v5"),
                Value::Null,
                json!(true),
                json!(3.9),
                json!("\u{665}")
            ]
            .map(|v| es::int_ver(&v))
        ),
        "title" => {
            let text = match case {
                "none" => "plain",
                "empty" => "",
                "heading" => "## no\n# First  \n# Second",
                "frontmatter" => "---\ntitle: ' Title '\ncreated: 2026-06-06\n---\n# Other",
                "blank_title" => "---\ntitle: ''\n---\n# Fallback",
                "empty_block" => "---\n---\n# Heading",
                "malformed" => "---\ntitle: Missing end\n# Fallback",
                "ignored_line" => "---\nbroken\ntitle: Kept\n---\n",
                "lists" => "---\ntitle: [a, b]\ntags:\n  - x\n  - y\n---\n# Fallback",
                "crlf" => "---\r\ntitle: CRLF\r\n---\r\n# Heading\r\n",
                "bom" => "\u{feff}---\ntitle: BOM\n---\n# Heading",
                "unicode" => "---\ntitle: \u{ba85}\n---\n# \u{e9}",
                _ => panic!("unknown title {case}"),
            };
            json!(es::extract_title_and_frontmatter(text))
        }
        "created" => {
            let mut inputs = vec![
                None,
                Some(String::new()),
                Some("{".into()),
                Some("[]".into()),
                Some("null".into()),
                Some("{}".into()),
            ];
            for v in [
                Value::Null,
                json!(""),
                json!(0),
                json!(20260606),
                json!(false),
                json!([]),
                json!({}),
                json!("2026-06-06"),
                json!("2026-06-06T12:00:00"),
                json!("2026-06-06 12:00:00+09:00"),
                json!("2026-06-06Z"),
                json!("20260606"),
                json!("2026-W23-6"),
                json!("2026-6-6"),
                json!("2024-02-29"),
                json!("2025-02-29"),
                json!("0001-01-01"),
                json!("9999-12-31"),
                json!("invalid"),
            ] {
                inputs.push(Some(json!({"created": v}).to_string()));
            }
            json!(
                inputs
                    .iter()
                    .map(|s| es::doc_created_ordinal(s.as_deref()))
                    .collect::<Vec<_>>()
            )
        }
        "walk" => return walk(case),
        _ => panic!("unknown record {name}"),
    };
    json!({"value": value})
}
fn walk(mode: &str) -> Value {
    let tmp = tempfile::tempdir().unwrap();
    let root = tmp.path().join("archive");
    if mode == "missing" {
        return observed(es::walk_archive(&root, &[], &[]));
    }
    std::fs::create_dir(&root).unwrap();
    for name in [
        "z.md",
        "a.md",
        ".hidden.md",
        "deep/b.md",
        "deep/.secret.md",
        "note.txt",
        "blocked.md",
        ".hidden-dir/c.md",
    ] {
        let path = root.join(name);
        std::fs::create_dir_all(path.parent().unwrap()).unwrap();
        std::fs::write(path, "synthetic").unwrap();
    }
    #[cfg(unix)]
    {
        use std::os::unix::fs::symlink;
        symlink(root.join("a.md"), root.join("link.md")).unwrap();
        symlink(root.join("deep"), root.join("link-dir")).unwrap();
        symlink(root.join("absent.md"), root.join("broken.md")).unwrap();
    }
    if mode == "not_dir" {
        return observed(es::walk_archive(&root.join("a.md"), &[], &[]));
    }
    if mode == "order" {
        return observed(es::walk_archive_with(&root, &[], &[], |r| {
            Ok(["z.md", "deep", "a.md", "deep/b.md"]
                .map(|p| r.join(p))
                .to_vec())
        }));
    }
    let include = if ["include", "exclude"].contains(&mode) {
        vec!["**/*.md".into()]
    } else {
        vec![]
    };
    let exclude = if mode == "exclude" {
        vec!["deep/**".into(), ".*".into(), "link*".into()]
    } else {
        vec![]
    };
    let mut files = es::walk_archive(&root, &include, &exclude).unwrap();
    files.sort();
    if mode == "unreadable" {
        // The reference patches Path.open, not traversal: inject the same denied read.
        let read = |path: &std::path::Path| -> std::io::Result<String> {
            if path == root.join("blocked.md") {
                Err(std::io::Error::new(
                    std::io::ErrorKind::PermissionDenied,
                    format!("unreadable {}", path.display()),
                ))
            } else {
                std::fs::read_to_string(path)
            }
        };
        let error = read(&root.join("blocked.md")).unwrap_err();
        assert_eq!(error.kind(), std::io::ErrorKind::PermissionDenied);
        let message = error
            .to_string()
            .replace(tmp.path().to_str().unwrap(), "<tmp>");
        json!({"value": {"walk": files, "read": {"error": ["PermissionError", message]}}})
    } else {
        json!({"value": files})
    }
}

fn parity(cell: &Value) -> Value {
    let text = cell["text"].as_str().unwrap_or("");
    let output = match cell["op"].as_str().unwrap() {
        "title" => json!(es::extract_title_and_frontmatter(text)),
        "chunk" => json!(
            es::chunk_text(
                text,
                cell["size"].as_i64().unwrap(),
                cell["overlap"].as_i64().unwrap()
            )
            .unwrap()
        ),
        "created" => json!(es::doc_created_ordinal(Some(
            &json!({"created": text}).to_string()
        ))),
        "paths" => json!([
            es::is_history_path(text),
            es::derive_doc_category(text),
            es::derive_layer(text)
        ]),
        "strip" => json!([
            es::compile_globs(Some(text)),
            es::is_within_path_scope("docs/a.md", cell["scope"].as_str().unwrap()).unwrap()
        ]),
        "status" => {
            use handoff_packet::mir_core::memory::store;
            let tmp = tempfile::tempdir().unwrap();
            let connection = store::connect(
                &tmp.path().join("synthetic.db"),
                store::ConnectOptions {
                    timeout: None,
                    vec_loading: store::VecLoading::Disabled,
                },
            )
            .unwrap();
            store::apply_migrations(&connection.conn).unwrap();
            let clock = || "2026-01-02T00:00:00+00:00".into();
            let external = es::ExternalStore::new(&connection, &clock).unwrap();
            let registration = es::Registration {
                slug: "sample".into(),
                root_path: tmp.path().to_str().unwrap().into(),
                mode: "indexed".into(),
                owner: "synthetic".into(),
                glob_include: vec![],
                glob_exclude: vec![],
                historical_glob: vec![],
                chunk_size: 800,
                chunk_overlap: 100,
            };
            std::fs::create_dir(tmp.path().join("docs")).unwrap();
            std::fs::write(tmp.path().join("docs/a.md"), text).unwrap();
            let id = external.register(&registration).unwrap();
            let archive = external.fetch_archive(id).unwrap();
            external.index_file(&archive, "docs/a.md").unwrap();
            json!(
                connection
                    .conn
                    .query_row("SELECT status FROM external_documents", [], |r| r
                        .get::<_, String>(0))
                    .unwrap()
            )
        }
        "fnmatch" | "regex" => {
            let pattern = cell["pattern"].as_str().unwrap().to_owned();
            let patterns = vec![pattern];
            let compiled = if cell["op"] == "regex" {
                es::compile_pattern_set(&patterns).unwrap()
            } else {
                vec![]
            };
            let matches: Vec<_> = cell["paths"]
                .as_array()
                .unwrap()
                .iter()
                .map(|p| {
                    if cell["op"] == "regex" {
                        es::matches_regex_any(p.as_str().unwrap(), &compiled).unwrap()
                    } else {
                        es::matches_any(p.as_str().unwrap(), &patterns).unwrap()
                    }
                })
                .collect();
            if cell["op"] == "regex" {
                json!([compiled[0], matches])
            } else {
                json!(matches)
            }
        }
        op => panic!("unknown parity operation {op}"),
    };
    json!({"value": {"input": cell, "output": output}})
}

#[test]
fn frozen_archive_helpers() {
    let records: Value =
        serde_json::from_str(include_str!("fixtures/w2/b18-archive-helpers.json")).unwrap();
    let mut replayed = 0;
    let mut exempt = 0;
    for (name, expected) in records.as_object().unwrap() {
        let reason = match name.as_str() {
            "chunk.surrogate" => Some("Python-only: Rust str excludes lone surrogates"),
            #[cfg(windows)]
            "walk.all" | "walk.include" | "walk.exclude" | "walk.unreadable" => {
                Some("Windows: symlink creation requires host privilege")
            }
            _ => None,
        };
        if let Some(reason) = reason {
            println!("{name}: exempt ({reason})");
            exempt += 1;
        } else {
            let actual = if name.starts_with("parity.") {
                parity(&expected["value"]["input"])
            } else {
                replay(name)
            };
            assert_eq!(actual, *expected, "{name}");
            println!("{name}: replayed");
            replayed += 1;
        }
    }
    assert_eq!(replayed + exempt, 118);
    assert_eq!(
        (replayed, exempt),
        if cfg!(windows) { (113, 5) } else { (117, 1) }
    );
}

#[test]
fn parity_witnesses() {
    let records: Value =
        serde_json::from_str(include_str!("fixtures/w2/b18-archive-helpers.json")).unwrap();
    let mut failures = Vec::new();
    for (name, expected) in records.as_object().unwrap() {
        if !name.starts_with("parity.") {
            continue;
        }
        let result = std::panic::catch_unwind(|| parity(&expected["value"]["input"]));
        let actual = match result {
            Ok(value) => value,
            Err(_) => json!({"panic": true}),
        };
        println!(
            "PROBE {}",
            json!({"name": name, "actual": actual, "matches": actual == *expected})
        );
        if actual != *expected {
            failures.push(name);
        }
    }
    assert!(failures.is_empty(), "divergent witnesses: {failures:?}");
}
