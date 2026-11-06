#[path = "../src/digest.rs"]
mod digest;
use handoff_packet::mir_core::memory::store::*;
use rusqlite::{Connection as Sqlite, types::ValueRef};
use serde_json::{Value, json};
use std::path::Path;
fn rows(c: &Sqlite, sql: &str) -> Value {
    let mut s = c.prepare(sql).unwrap();
    let width = s.column_count();
    let mut data = Vec::new();
    let mut cursor = s.query([]).unwrap();
    while let Some(r) = cursor.next().unwrap() {
        let row = (0..width)
            .map(|i| match r.get_ref(i).unwrap() {
                ValueRef::Null => Value::Null,
                ValueRef::Integer(v) => json!(v),
                ValueRef::Text(v) => json!(std::str::from_utf8(v).unwrap()),
                other => panic!("unexpected value: {other:?}"),
            })
            .collect();
        data.push(Value::Array(row));
    }
    json!(data)
}
fn state(c: &Sqlite) -> Value {
    json!({"objects": rows(c, "SELECT type, name, tbl_name, sql FROM sqlite_master ORDER BY type, name"),
        "versions": rows(c, "SELECT version, name FROM schema_migrations ORDER BY version"),
        "version": schema_version(c).unwrap(), "transaction": !c.is_autocommit()})
}
fn observed<T: serde::Serialize>(r: Result<T, Error>) -> Value {
    match r {
        Ok(v) => json!({"value":v}),
        Err(e) => json!({"error":[e.python_class(), e.to_string()]}),
    }
}
fn replay(name: &str, tmp: &Path) -> Value {
    if name.starts_with("connect.") {
        let timeout = match name {
            "connect.custom_timeout" => Some(0.125),
            "connect.zero_timeout" => Some(0.0),
            _ => None,
        };
        let w = connect(&tmp.join("nested/db"), timeout).unwrap();
        let mut pragmas = serde_json::Map::new();
        for p in [
            "journal_mode",
            "synchronous",
            "foreign_keys",
            "busy_timeout",
        ] {
            pragmas.insert(
                p.into(),
                rows(&w.conn, &format!("PRAGMA {p}"))[0][0].clone(),
            );
        }
        // Python tuple/default row_factory map to unconfigured rusqlite rows.
        return json!({"value":{"pragmas":pragmas,"row_factory":null,"row_type":"tuple",
            "objects":rows(&w.conn,"SELECT type, name FROM sqlite_master ORDER BY type, name"),
            "vec":[w.vec_available,w.vec_reason]}});
    }
    if name == "migrations.resources" {
        return json!({"value":migrations().iter().map(|m| json!([m.version,m.name,
            digest::sha256(m.body.as_bytes())])).collect::<Vec<_>>()});
    }
    let c = Sqlite::open(tmp.join("db")).unwrap();
    if name == "migrations.rollback" {
        let root = tmp.join("migrations");
        std::fs::create_dir(&root).unwrap();
        for (name, body) in [
            (
                "020_fail.sql",
                "CREATE TABLE lost(x);\nINSERT INTO absent VALUES (1);\n",
            ),
            (
                "003_keep.sql",
                "CREATE TABLE kept(x);\nINSERT INTO kept VALUES (7);\n",
            ),
            ("README.md", "ignored"),
            ("1_bad.sql", "ignored"),
            ("004_UPPER.sql", "ignored"),
        ] {
            std::fs::write(root.join(name), body).unwrap();
        }
        let entries = discover(&root).unwrap();
        let failure = observed(apply_entries(&c, &entries));
        return json!({"value":{"entries":entries.iter().map(|m|json!([m.version,m.name])).collect::<Vec<_>>(),
            "failure":failure,"state":state(&c),"kept":rows(&c,"SELECT * FROM kept")}});
    }
    if name.starts_with("migrations.") {
        let before = if name == "migrations.earlier" {
            let applied = apply_entries(&c, &migrations()[..2]).unwrap();
            json!({"applied":applied,"state":state(&c)})
        } else {
            Value::Null
        };
        let applied = apply_migrations(&c).unwrap();
        let mut value = json!({"before":before,"applied":applied,"state":state(&c)});
        if name == "migrations.rerun" {
            value["rerun"] = json!(apply_migrations(&c).unwrap());
            value["after_rerun"] = state(&c);
        }
        return json!({"value":value});
    }
    match name {
        "schema.empty_table" => {
            c.execute_batch(SCHEMA_MIGRATIONS_DDL).unwrap();
            observed(schema_version(&c))
        }
        "schema.missing_table" => observed(schema_version(&c)),
        "schema.latest" => json!({"value":latest_schema_version()}),
        _ => panic!("unimplemented replay: {name}"),
    }
}
#[test]
fn frozen_records() {
    let store: Value = serde_json::from_str(include_str!("fixtures/w2/b03-store.json")).unwrap();
    let snapshot: Value =
        serde_json::from_str(include_str!("fixtures/w2/b03-snapshot.json")).unwrap();
    let splits: Vec<(String, String)> = serde_json::from_str(r#"[
["split.multi","CREATE TABLE a(x);\nINSERT INTO a VALUES (1);\n"],
["split.same_line","SELECT 1; SELECT 2;\n"],
["split.trigger","CREATE TRIGGER t AFTER INSERT ON a BEGIN\nINSERT INTO b VALUES ('a;b');\nUPDATE b SET x=2;\nEND;\n"],
["split.comments_tail","-- head;\nSELECT ';';\n/* block; */\nSELECT 2"],
["split.empty",""],["split.comment_only","-- comment only"]]"#).unwrap();
    let mut replayed = 0;
    for (name, body) in splits {
        assert_eq!(observed(complete_statements(&body)), store[&name], "{name}");
        replayed += 1;
    }
    for name in store.as_object().unwrap().keys().filter(|n| {
        n.starts_with("connect.")
            || n.starts_with("migrations.")
            || [
                "schema.latest",
                "schema.empty_table",
                "schema.missing_table",
            ]
            .contains(&n.as_str())
    }) {
        let tmp = tempfile::tempdir().unwrap();
        assert_eq!(replay(name, tmp.path()), store[name], "{name}");
        replayed += 1;
    }
    // Python-only exemption: Rust has no dynamic missing-attribute lookup.
    let exempt = [
        "checkpoint.absent",
        "filter.ids_absent",
        "schema.guard_absent",
    ];
    for name in exempt {
        assert_eq!(store[name]["error"][0], "AttributeError");
    }
    // Authorized fallback: all snapshot and filter cases remain OPEN.
    let deferred = ["filter.default", "filter.custom", "filter.invalid"];
    assert_eq!(
        (
            replayed,
            exempt.len(),
            deferred.len() + snapshot.as_object().unwrap().len()
        ),
        (17, 3, 30)
    );
}
#[test]
fn embedded_directory_parity() {
    let root =
        Path::new(env!("CARGO_MANIFEST_DIR")).join("../../src/mir/core/engine/memory/migrations");
    assert_eq!(discover(&root).unwrap(), migrations());
}
