#![forbid(unsafe_code)]
use handoff_packet::{mir_cli::memory, mir_core::memory::store};
use rusqlite::{Connection, types::ValueRef};
use serde_json::{Value, json};
use std::path::Path;

fn rows(c: &Connection, sql: &str) -> Value {
    let mut s = c.prepare(sql).unwrap();
    let width = s.column_count();
    let data = s
        .query_map([], |r| {
            Ok((0..width)
                .map(|i| match r.get_ref(i).unwrap() {
                    ValueRef::Null => Value::Null,
                    ValueRef::Integer(n) => json!(n),
                    ValueRef::Text(s) => json!(std::str::from_utf8(s).unwrap()),
                    other => panic!("unexpected value {other:?}"),
                })
                .collect::<Vec<_>>())
        })
        .unwrap()
        .collect::<Result<Vec<_>, _>>()
        .unwrap();
    json!(data)
}
fn seed(db: &Path) -> Connection {
    let c = Connection::open(db).unwrap();
    store::apply_migrations(&c).unwrap();
    c.execute_batch("INSERT INTO entities(id, slug) VALUES (1,'alpha'),(2,'beta'),(3,'retired');")
        .unwrap();
    for (subject, predicate, body, status) in [
        (1, "topic", "needle", "active"),
        (2, "topic", "needle", "active"),
        (1, "detail", "needle long extra padding words", "active"),
        (1, "topic", "needle expired", "expired"),
        (2, "detail", "needle superseded", "superseded"),
        (3, "status", "historical-snapshot", "active"),
        (3, "topic", "needle terminal", "active"),
        (
            2,
            "special",
            "quote \"alpha beta\" star* adr-99 key:value NEAR (group)",
            "active",
        ),
        (1, "unicode", "\u{ba54}\u{baa8} caf\u{e9}", "active"),
    ] {
        c.execute("INSERT INTO facts(subject_entity_id,predicate,object_literal,status,polarity) VALUES (?,?,?,?,'asserted')",
            rusqlite::params![subject,predicate,body,status]).unwrap();
    }
    c
}
fn replay(name: &str, tmp: &Path) -> Value {
    let mode = name.strip_prefix("query.").unwrap();
    let db = tmp.join("db");
    let conn = match mode {
        "missing" => None,
        "invalid" => {
            std::fs::write(&db, "not sqlite").unwrap();
            None
        }
        _ => Some(seed(&db)),
    };
    if let Some(c) = &conn {
        if matches!(mode, "unknown" | "future") {
            c.execute_batch("DELETE FROM schema_migrations").unwrap();
            c.execute(
                "INSERT INTO schema_migrations VALUES (?, 'synthetic.sql','fixed')",
                [if mode == "unknown" { "unknown" } else { "999" }],
            )
            .unwrap();
        }
        if mode.starts_with("wal_") {
            c.execute_batch("PRAGMA journal_mode=WAL; PRAGMA wal_autocheckpoint=0;
                INSERT INTO facts(predicate,object_literal,status) VALUES ('wal','needle committed','active');").unwrap();
            if mode == "wal_uncommitted" {
                c.execute_batch("BEGIN; INSERT INTO facts(predicate,object_literal,status) VALUES ('wal','needle uncommitted','active');").unwrap();
            }
            assert!(std::fs::metadata(tmp.join("db-wal")).unwrap().len() > 0);
        }
    }
    #[cfg(unix)]
    if mode == "unreadable" {
        use std::os::unix::fs::PermissionsExt;
        std::fs::set_permissions(&db, std::fs::Permissions::from_mode(0o0)).unwrap();
    }
    let keyword = match mode {
        "no_match" => "absenttoken",
        "keyword_quotes" => "\"alpha beta\"",
        "keyword_unmatched_quote" => "\"alpha",
        "keyword_star" => "star*",
        "keyword_hyphen" => "adr-99",
        "keyword_colon" => "key:value",
        "keyword_near" => "NEAR",
        "keyword_parentheses" => "(group)",
        "keyword_empty" => "",
        "keyword_unicode" => "\u{ba54}\u{baa8}",
        _ => "needle",
    };
    let mut args = vec!["query", keyword];
    match mode {
        "limit_zero" => args.extend(["--limit", "0"]),
        "limit_one" => args.extend(["--limit", "1"]),
        "limit_negative" => args.extend(["--limit", "-1"]),
        "history" => args.push("--history"),
        "semantic_unavailable" => args.push("--semantic"),
        "args_abbrev_history" => args.push("--hist"),
        "args_abbrev_limit" => args.extend(["--lim", "1"]),
        "args_equals_limit" => args.push("--limit=1"),
        "args_help" => args = vec!["query", "-h"],
        "args_no_keyword" => args = vec!["query"],
        "args_extra_positional" => args.push("other"),
        "args_option_first" => args = vec!["query", "--limit", "1", keyword],
        "args_double_dash" => args = vec!["query", "--", "--needle"],
        "args_limit_missing_value" => args.push("--limit"),
        _ => (),
    }
    let db_arg = format!("{}/db", tmp.to_str().unwrap());
    args.extend(["--db", &db_arg]);
    let mut value = match memory::main(&args, &db) {
        Ok((code, out, err)) => {
            json!({"exit":code,"stdout":String::from_utf8(out).unwrap().replace(tmp.to_str().unwrap(),"<tmp>"),"stderr":String::from_utf8(err).unwrap().replace(tmp.to_str().unwrap(),"<tmp>")})
        }
        Err(e) => {
            json!({"exit":null,"stdout":"","stderr":"","error":[e.python_class(),e.to_string()]})
        }
    };
    #[cfg(unix)]
    if mode == "unreadable" {
        use std::os::unix::fs::PermissionsExt;
        std::fs::set_permissions(&db, std::fs::Permissions::from_mode(0o600)).unwrap();
    }
    if mode == "default" {
        let c = conn.as_ref().unwrap();
        value["state"] = json!({"pragmas":{"journal_mode":rows(c,"PRAGMA journal_mode")[0][0],"user_version":rows(c,"PRAGMA user_version")[0][0]},
            "versions":rows(c,"SELECT version, name FROM schema_migrations ORDER BY version"),
            "objects":rows(c,"SELECT type, name, tbl_name, sql FROM sqlite_master ORDER BY type, name")});
    }
    json!({"value":value})
}
#[test]
fn frozen_query_records() {
    let records: Value =
        serde_json::from_str(include_str!("fixtures/w2/b05-memory-query.json")).unwrap();
    let (mut replayed, mut exempt) = (0, 0);
    for (name, expected) in records.as_object().unwrap() {
        if cfg!(windows) && name == "query.unreadable" {
            // Python chmod(0) POSIX access denial has no Windows equivalent.
            exempt += 1;
            continue;
        }
        let tmp = tempfile::tempdir().unwrap();
        assert_eq!(replay(name, tmp.path()), *expected, "{name}");
        replayed += 1;
    }
    assert_eq!(
        (replayed, exempt),
        if cfg!(windows) { (31, 1) } else { (32, 0) }
    );
    assert_eq!(replayed + exempt, 32);
}
