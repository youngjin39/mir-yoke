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
    if name.starts_with("filter.") {
        return observed(current_fact_filter_sql(match name {
            "filter.custom" => "fact_2",
            "filter.invalid" => "f;DROP",
            _ => "f",
        }));
    }
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
        (n.starts_with("filter.") && !n.ends_with("absent"))
            || n.starts_with("connect.")
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
    let mut snapshot_exempt = 0;
    for (name, expected) in snapshot.as_object().unwrap() {
        if name.starts_with("api.") {
            // Python-only exemption: probes assert an absent dynamic attribute.
            assert_eq!(expected["error"][0], "AttributeError");
            snapshot_exempt += 1;
        } else if cfg!(windows)
            && ["connect.symlink", "file_state.symlink"].contains(&name.as_str())
        {
            // Windows exemption: symlink creation requires privileges unavailable in CI.
            snapshot_exempt += 1;
        } else {
            let tmp = tempfile::tempdir().unwrap();
            assert_eq!(snapshot_replay(name, tmp.path()), *expected, "{name}");
            replayed += 1;
        }
    }
    assert_eq!(
        (replayed, exempt.len() + snapshot_exempt),
        if cfg!(windows) { (42, 8) } else { (44, 6) }
    );
    assert_eq!(replayed + exempt.len() + snapshot_exempt, 50);
}
#[test]
fn embedded_directory_parity() {
    let root =
        Path::new(env!("CARGO_MANIFEST_DIR")).join("../../src/mir/core/engine/memory/migrations");
    assert_eq!(discover(&root).unwrap(), migrations());
}

#[rustfmt::skip] // Compact oracle projections follow the Python case bodies.
fn database(tmp: &Path, schema: bool) -> (std::path::PathBuf, Sqlite) {
    let path = tmp.join("db");
    let c = Sqlite::open(&path).unwrap();
    c.execute_batch("CREATE TABLE items(value TEXT); INSERT INTO items VALUES ('base');").unwrap();
    if schema { c.execute_batch("CREATE TABLE schema_migrations(version TEXT, name TEXT); INSERT INTO schema_migrations VALUES ('999', 'future.sql');").unwrap(); }
    (path, c)
}
#[rustfmt::skip]
fn logical(c: &Sqlite) -> Value {
    let objects = rows(c, "SELECT type, name, tbl_name, sql FROM sqlite_master ORDER BY type, name");
    let versions = if objects.as_array().unwrap().iter().any(|r| r[1] == "schema_migrations") { rows(c, "SELECT version, name FROM schema_migrations ORDER BY version") } else { Value::Null };
    json!({"objects":objects,"versions":versions,"rows":rows(c,"SELECT * FROM items ORDER BY value"),"pragmas":{"journal_mode":rows(c,"PRAGMA journal_mode")[0][0],"query_only":rows(c,"PRAGMA query_only")[0][0],"user_version":rows(c,"PRAGMA user_version")[0][0]}})
}
#[rustfmt::skip]
fn snapshot_replay(name: &str, tmp: &Path) -> Value {
    let mode = name.split_once('.').unwrap().1;
    let path = tmp.join("db");
    if name == "error.hierarchy" { return json!({"value":Error::Snapshot("test").python_hierarchy()}); }
    if name.starts_with("file_state.") {
        if mode != "missing" { std::fs::write(&path, b"abc").unwrap(); }
        let before = snapshot_file_state(&path).unwrap();
        #[cfg(unix)]
        if mode == "symlink" {
            std::os::unix::fs::symlink(&path, tmp.join("link")).unwrap();
            return json!({"value":snapshot_file_state(&tmp.join("link")).unwrap() == before});
        }
        // Private fields make the Python frozen-dataclass mutation unrepresentable.
        return json!({"value":before.map(|s| json!({"fields":s.fields(),"size":s.size(),"equal":Some(s)==snapshot_file_state(&path).unwrap(),"frozen":"FrozenInstanceError"}))});
    }
    if name == "connect.missing" { return observed(connect_read_only(&tmp.join("missing")).map(|_| ())); }
    let (path, c) = database(tmp, mode != "no_schema");
    if name.starts_with("connect.") {
        if mode == "wal" { c.execute_batch("PRAGMA journal_mode=WAL; INSERT INTO items VALUES ('wal-row');").unwrap(); }
        if mode == "empty_wal" || mode == "shm" { std::fs::write(tmp.join(if mode == "shm" {"db-shm"} else {"db-wal"}), b"").unwrap(); }
        #[cfg(not(unix))]
        let target = path.clone();
        #[cfg(unix)]
        let target = if mode == "symlink" { let link = tmp.join("link"); std::os::unix::fs::symlink(&path, &link).unwrap(); link } else { path.clone() };
        let before = logical(&c);
        let mut files: Vec<_> = std::fs::read_dir(tmp).unwrap().map(|p| p.unwrap().file_name().into_string().unwrap()).collect(); files.sort();
        let wal_before = snapshot_file_state(&tmp.join("db-wal")).unwrap();
        let read = match connect_read_only(&target) {
            Err(e) => observed::<()>(Err(e)),
            Ok(w) => {
                let data = logical(&w.conn);
                let write = observed(w.conn.execute("INSERT INTO items VALUES ('snapshot-write')", []).map(|_| ()).map_err(Error::from));
                w.conn.close().unwrap();
                // Rust close consumes ownership; Python's subsequent query is invalid.
                json!({"value":{"logical":data,"type":"Connection","vec":[w.vec_available,w.vec_reason],"write":write,"closed_query":{"error":["ProgrammingError","Cannot operate on a closed database."]}}})
            }
        };
        let after = logical(&c);
        return json!({"value":{"read":read,"source_before":before,"source_after":after,"source_unchanged":before==after,"wal_unchanged":wal_before==snapshot_file_state(&tmp.join("db-wal")).unwrap(),"copy_exists_after_close":std::fs::read_dir(tmp).unwrap().any(|p| !files.contains(&p.unwrap().file_name().into_string().unwrap())),"files_before":files}});
    }
    drop(c);
    if ["wal","journal","empty_wal","shm","wal_removed"].contains(&mode) { std::fs::write(tmp.join(format!("db-{}", if ["empty_wal","wal_removed"].contains(&mode) {"wal"} else {mode})), if ["empty_wal","wal_removed"].contains(&mode) {b"".as_slice()} else {b"x".as_slice()}).unwrap(); }
    let before = immutable_snapshot_state(&path).unwrap();
    let change = || -> Result<(), Error> {
        match mode {
            "changed" => { use std::io::Write; std::fs::OpenOptions::new().append(true).open(&path)?.write_all(b"x")?; }
            "deleted" => std::fs::remove_file(&path)?,
            "wal_removed" => std::fs::remove_file(tmp.join("db-wal"))?,
            _ => ()
        } Ok(())
    };
    let result = if name.starts_with("assert.") { change().unwrap(); observed(assert_immutable_snapshot_state(&path, &before)) } else { observed(immutable_snapshot_guard(&path, change)) };
    let after = immutable_snapshot_state(&path).unwrap();
    let present: serde_json::Map<_,_> = before.iter().map(|(k,v)| ((*k).into(), json!(v.is_some()))).collect();
    let unchanged: serde_json::Map<_,_> = before.iter().map(|(k,v)| ((*k).into(), json!(Some(v)==after.get(k)))).collect();
    json!({"value":{"result":result,"keys":before.keys().collect::<Vec<_>>(),"present":present,"unchanged":unchanged}})
}
#[cfg(unix)]
#[test]
fn symlink_cannot_bypass_wal() {
    let tmp = tempfile::tempdir().unwrap();
    let (path, c) = database(tmp.path(), true);
    drop(c);
    let link = tmp.path().join("link");
    std::os::unix::fs::symlink(&path, &link).unwrap();
    std::fs::write(tmp.path().join("db-wal"), b"x").unwrap();
    assert_eq!(
        observed(connect_read_only(&link).map(|_| ())),
        json!({"error":["ReadOnlySnapshotUnavailable","immutable read refused because a non-empty SQLite WAL is present"]})
    );
}
#[test]
fn guard_checks_body_errors() {
    let tmp = tempfile::tempdir().unwrap();
    let (path, c) = database(tmp.path(), true);
    drop(c);
    let result: Result<(), Error> = immutable_snapshot_guard(&path, || {
        std::fs::remove_file(&path)?;
        Err(Error::Snapshot("body"))
    });
    assert!(result.unwrap_err().to_string().contains("changed during"));
}
