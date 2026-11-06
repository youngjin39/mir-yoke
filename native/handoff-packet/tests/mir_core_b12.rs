//! Frozen Python B12 oracle replay. Only synthetic scratch databases are opened.
#[path = "../src/digest.rs"]
mod digest;
use handoff_packet::{
    mir_cli::memory as cli,
    mir_core::memory::{distill as d, store},
};
use rusqlite::{Connection, types::ValueRef};
use serde_json::{Value, json};
use std::{
    path::Path,
    time::{Duration, SystemTime, UNIX_EPOCH},
};
const CLOCK: &str = "2001-02-03T04:05:06.000000+00:00";
fn clock() -> SystemTime {
    UNIX_EPOCH + Duration::from_secs(981173106)
}
fn rows(conn: &Connection, sql: &str) -> Value {
    let mut stmt = conn.prepare(sql).unwrap();
    let count = stmt.column_count();
    json!(
        stmt.query_map([], |r| Ok((0..count)
            .map(|i| match r.get_ref(i).unwrap() {
                ValueRef::Null => Value::Null,
                ValueRef::Integer(n) => json!(n),
                ValueRef::Real(n) => json!(n),
                ValueRef::Text(s) => json!(std::str::from_utf8(s).unwrap()),
                ValueRef::Blob(_) => panic!("unexpected blob"),
            })
            .collect::<Vec<_>>()))
            .unwrap()
            .collect::<rusqlite::Result<Vec<_>>>()
            .unwrap()
    )
}
fn state(conn: &Connection, ingest: bool) -> Value {
    let mut value = json!({"transaction":!conn.is_autocommit()});
    let tables: &[&str] = if ingest {
        &[
            "content_items",
            "entities",
            "facts",
            "audit_log",
            "fact_links",
            "provenance",
            "fact_documents",
        ]
    } else {
        &["entities", "facts", "audit_log", "fact_links"]
    };
    for table in tables {
        value[table] = rows(conn, &format!("SELECT * FROM {table} ORDER BY rowid"));
    }
    value
}
fn schema(conn: &Connection) -> Value {
    let mut pragmas = json!({});
    for p in ["journal_mode", "foreign_keys", "synchronous"] {
        pragmas[p] = rows(conn, &format!("PRAGMA {p}"))[0][0].clone();
    }
    json!({"pragmas":pragmas,
        "migrations":rows(conn,"SELECT * FROM schema_migrations ORDER BY version"),
        "objects":rows(conn,"SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name")})
}
fn compact(value: Value) -> Value {
    match value {
        Value::String(s) if s.chars().count() > 256 => json!({"length":s.chars().count(),
            "sha256":digest::sha256(s.as_bytes())}),
        Value::Array(a) => json!(a.into_iter().map(compact).collect::<Vec<_>>()),
        Value::Object(m) => Value::Object(m.into_iter().map(|(k, v)| (k, compact(v))).collect()),
        v => v,
    }
}
fn normalize(value: Value, root: &Path) -> Value {
    match value {
        Value::String(s) => json!(s.replace(root.to_str().unwrap(), "<tmp>")),
        Value::Array(a) => json!(
            a.into_iter()
                .map(|v| normalize(v, root))
                .collect::<Vec<_>>()
        ),
        Value::Object(m) => Value::Object(
            m.into_iter()
                .map(|(k, v)| (k, normalize(v, root)))
                .collect(),
        ),
        v => v,
    }
}
fn snapshot(conn: &Connection, root: &Path) -> Value {
    let mut s = state(conn, true);
    let schema = schema(conn);
    let hash = json!({"migrations":schema["migrations"],"objects":schema["objects"]});
    let normalized = normalize(hash, root);
    let body = handoff_packet::mir_core::canonical::canonical_json(&normalized, Some(&[]));
    let mut spaced = String::new();
    let (mut quoted, mut escaped) = (false, false);
    for c in body.chars() {
        if c.is_ascii() {
            spaced.push(c);
        } else {
            use std::fmt::Write;
            for unit in c.encode_utf16(&mut [0; 2]) {
                write!(spaced, "\\u{unit:04x}").unwrap();
            }
        }
        if escaped {
            escaped = false;
            continue;
        }
        if quoted && c == '\\' {
            escaped = true;
        }
        if c == '"' {
            quoted = !quoted;
        }
        if !quoted && matches!(c, ',' | ':') {
            spaced.push(' ');
        }
    }
    s["schema_sha256"] = json!(digest::sha256(spaced.as_bytes()));
    s["pragmas"] = schema["pragmas"].clone();
    compact(normalize(s, root))
}
fn git(root: &Path, args: &[&str]) -> String {
    let output = std::process::Command::new("git")
        .args(["-c", "core.hooksPath=/dev/null"])
        .args(args)
        .current_dir(root)
        .env("GIT_CONFIG_NOSYSTEM", "1")
        .env(
            "GIT_CONFIG_GLOBAL",
            if cfg!(windows) { "NUL" } else { "/dev/null" },
        )
        .env("GIT_AUTHOR_NAME", "Fixture")
        .env("GIT_AUTHOR_EMAIL", "fixture@example.invalid")
        .env("GIT_COMMITTER_NAME", "Fixture")
        .env("GIT_COMMITTER_EMAIL", "fixture@example.invalid")
        .env("GIT_AUTHOR_DATE", "2001-02-03T04:05:06+00:00")
        .env("GIT_COMMITTER_DATE", "2001-02-03T04:05:06+00:00")
        .output()
        .unwrap();
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    String::from_utf8(output.stdout).unwrap()
}
fn replay(name: &str, root: &Path) -> Value {
    let (action, kind) = name.split_once('.').unwrap();
    git(root, &["init", "-b", "fixture"]);
    let db = root.join("synthetic.db");
    let conn = store::connect(&db, None).unwrap().conn;
    store::apply_migrations(&conn).unwrap();
    conn.execute("UPDATE schema_migrations SET applied_at=?", [CLOCK])
        .unwrap();
    let relative = if kind == "nested" {
        "docs/decisions/nested/adr-main.md"
    } else {
        "docs/decisions/adr-main.md"
    };
    let path = root.join(relative);
    let other = root.join("docs/decisions/adr-other.md");
    let mut ingested = Vec::new();
    for (source, target) in [(&path, "CAP-A"), (&other, "CAP-B")] {
        std::fs::create_dir_all(source.parent().unwrap()).unwrap();
        std::fs::write(
            source,
            format!(
                "---\ntitle: source\nstatus: accepted\nmemory_relations:\n  \
             - [REQ-1, realized_by, {target}]\n---\nbody\n"
            ),
        )
        .unwrap();
        ingested.push(d::ingest_markdown_file(source, &conn, root, &["**"], clock).unwrap());
    }
    if kind == "legacy_metadata" {
        // Older content rows carry no relation schema: expiry writes no audit row.
        conn.execute_batch(
            "UPDATE content_items SET metadata_json =
            json_remove(metadata_json, '$.relation_schema') WHERE id = 1",
        )
        .unwrap();
    }
    if kind == "ignored" {
        std::fs::write(root.join(".gitignore"), format!("{relative}\n")).unwrap();
    } else if !matches!(kind, "never_present" | "never_missing") {
        git(root, &["add", "docs"]);
        git(root, &["commit", "-m", "fixture sources"]);
    }
    match kind {
        "deleted_untracked" => {
            git(root, &["rm", relative]);
        }
        "renamed" => {
            git(root, &["mv", relative, "docs/decisions/adr-renamed.md"]);
        }
        "deleted_tracked" | "never_missing" | "nested" | "outer_tx" | "legacy_metadata" => {
            std::fs::remove_file(&path).unwrap();
        }
        _ => {}
    }
    let mut steps = vec![json!({"ingest":ingested,"state":snapshot(&conn,root),
        "tracked":git(root,&["ls-files","--",relative]),"exists":path.exists()})];
    for dry in [true, false, false] {
        let (result, stdout, stderr) = if action == "cli" {
            let mut args = vec!["reconcile-missing", "--db", db.to_str().unwrap()];
            if kind != "nested" {
                args.extend(["--project-root", root.to_str().unwrap()]);
            }
            if dry {
                args.push("--dry-run");
            }
            let (code, out, err) = cli::main_with_clock(&args, &db, root, clock).unwrap();
            (
                json!(code),
                String::from_utf8(out).unwrap(),
                String::from_utf8(err).unwrap(),
            )
        } else {
            if kind == "outer_tx" && !dry {
                conn.execute_batch("BEGIN").unwrap();
            }
            let project = (kind != "nested").then_some(root);
            let n = d::reconcile_missing_source(&conn, project, root, dry, clock).unwrap();
            let value = if kind == "outer_tx" && !dry {
                let value = json!([n, !conn.is_autocommit()]);
                conn.execute_batch("COMMIT").unwrap();
                value
            } else {
                json!(n)
            };
            (value, String::new(), String::new())
        };
        let reader = Connection::open(&db).unwrap();
        // CPython's bare sqlite3 reader uses foreign_keys=OFF and synchronous=FULL.
        reader
            .execute_batch("PRAGMA foreign_keys=OFF; PRAGMA synchronous=FULL")
            .unwrap();
        steps.push(
            json!({"dry_run":dry,"result":result,"stdout":stdout,"stderr":stderr,
            "state":snapshot(&conn,root),"committed":snapshot(&reader,root)}),
        );
    }
    compact(normalize(json!(steps), root))
}
fn compare(actual: &Value, expected: &Value, path: &str) {
    match (actual, expected) {
        (Value::Array(a), Value::Array(b)) if a.len() == b.len() => {
            for (i, (a, b)) in a.iter().zip(b).enumerate() {
                compare(a, b, &format!("{path}/{i}"));
            }
        }
        (Value::Object(a), Value::Object(b)) if a.keys().eq(b.keys()) => {
            for (k, a) in a {
                compare(a, &b[k], &format!("{path}/{k}"));
            }
        }
        _ => assert_eq!(actual, expected, "{path}"),
    }
}
#[test]
fn frozen_records() {
    let oracle: Value =
        serde_json::from_str(include_str!("fixtures/w2/b12-reconcile-missing.json")).unwrap();
    assert_eq!(oracle.as_object().unwrap().len(), 14);
    let mut replayed = 0;
    for (name, expected) in oracle.as_object().unwrap() {
        if name == "git_tracks.availability" {
            assert_eq!(expected, &json!({"value":false}));
            println!("{name}: exempt: Python hasattr on an absent helper has no Rust surface");
            continue;
        }
        let temp = tempfile::Builder::new().prefix("b12-").tempdir().unwrap();
        let root = temp.path().canonicalize().unwrap();
        compare(&json!({"value":replay(name,&root)}), expected, name);
        println!("{name}: replayed");
        replayed += 1;
    }
    assert_eq!(replayed, 13);
    println!("replayed=13 exempt=1 total=14");
}

#[test]
fn cli_options_and_relative_paths() {
    let temp = tempfile::tempdir().unwrap();
    let root = temp.path().canonicalize().unwrap();
    let missing = root.join("fallback.db");
    let (code, out, err) =
        cli::main_with_clock(&["reconcile-missing", "--help"], &missing, &root, clock).unwrap();
    assert_eq!(code, 0);
    assert!(err.is_empty());
    assert_eq!(
        String::from_utf8(out).unwrap(),
        concat!(
            "usage: mir memory reconcile-missing [-h] [--project-root PROJECT_ROOT]\n",
            "                                    [--dry-run] [--db DB]\n\noptions:\n",
            "  -h, --help            show this help message and exit\n",
            "  --project-root PROJECT_ROOT\n",
            "                        project root for relative path resolution (default:\n",
            "                        cwd)\n",
            "  --dry-run             report count without writing any rows\n  --db DB\n"
        )
    );
    for args in [
        vec!["reconcile-missing", "--db"],
        vec!["reconcile-missing", "--dry-run=yes"],
        vec!["reconcile-missing", "--unknown"],
    ] {
        let (code, out, err) = cli::main_with_clock(&args, &missing, &root, clock).unwrap();
        assert_eq!(code, 2);
        assert!(out.is_empty());
        assert!(String::from_utf8(err).unwrap().contains("error:"));
    }
    let (code, out, err) = cli::main_with_clock(
        &["reconcile-missing", "--db", "absent.db"],
        &missing,
        &root,
        clock,
    )
    .unwrap();
    assert_eq!(code, 2);
    assert!(err.is_empty());
    assert_eq!(
        String::from_utf8(out).unwrap(),
        "no memory.db at absent.db \u{2014} run `mir migrate up` first\n"
    );
    assert!(!root.join("absent.db").exists());

    let db = store::connect(&root.join("synthetic.db"), None).unwrap();
    store::apply_migrations(&db.conn).unwrap();
    let project = root.join("project");
    std::fs::create_dir_all(project.join("docs/decisions")).unwrap();
    let source = project.join("docs/decisions/adr-main.md");
    std::fs::write(&source, "---\ntitle: source\n---\nbody\n").unwrap();
    d::ingest_markdown_file(&source, &db.conn, &project, &["**"], clock).unwrap();
    for (dry, expected) in [(true, "dry_run: would_expire=0\n"), (false, "expired=1\n")] {
        if !dry {
            std::fs::remove_file(&source).unwrap();
        }
        let mut args = vec!["reconcile-missing", "--project-root=project"];
        if dry {
            args.push("--dry-r");
        }
        let (code, out, err) =
            cli::main_with_clock(&args, Path::new("synthetic.db"), &root, clock).unwrap();
        assert_eq!(code, 0);
        assert_eq!(String::from_utf8(out).unwrap(), expected);
        assert!(err.is_empty());
    }
}
