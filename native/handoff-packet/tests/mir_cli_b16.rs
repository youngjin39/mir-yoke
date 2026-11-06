#![forbid(unsafe_code)]
#[path = "../src/digest.rs"]
mod digest;
use handoff_packet::{mir_cli::migrate, mir_core::memory::store};
use rusqlite::{Connection, OpenFlags, types::ValueRef};
use serde_json::{Value, json};
use std::path::{Path, PathBuf};

const SUFFIXES: [&str; 4] = ["", "-wal", "-shm", "-journal"];
fn file(db: &Path, suffix: &str) -> PathBuf {
    let mut s = db.as_os_str().to_os_string();
    s.push(suffix);
    s.into()
}
fn rows(c: &Connection, sql: &str) -> rusqlite::Result<Value> {
    let mut s = c.prepare(sql)?;
    let width = s.column_count();
    let result = s
        .query_map([], |r| {
            (0..width)
                .map(|i| {
                    Ok(match r.get_ref(i)? {
                        ValueRef::Null => Value::Null,
                        ValueRef::Integer(v) => json!(v),
                        ValueRef::Text(v) => json!(std::str::from_utf8(v).unwrap()),
                        v => panic!("unexpected {v:?}"),
                    })
                })
                .collect::<rusqlite::Result<Vec<_>>>()
        })?
        .collect::<rusqlite::Result<Vec<_>>>()?;
    Ok(json!(result))
}
fn files(db: &Path) -> Value {
    json!(
        SUFFIXES
            .into_iter()
            .map(|s| {
                let p = file(db, s);
                (
                    s.to_owned(),
                    json!({"exists":p.exists(),
            "nonempty":p.metadata().is_ok_and(|m| m.len() > 0)}),
                )
            })
            .collect::<serde_json::Map<_, _>>()
    )
}
fn fingerprints(db: &Path) -> Vec<Option<String>> {
    SUFFIXES
        .iter()
        .map(|s| std::fs::read(file(db, s)).ok().map(|b| digest::sha256(&b)))
        .collect()
}
fn error(e: &store::Error) -> Value {
    let class = if matches!(e, store::Error::Sql(rusqlite::Error::SqliteFailure(e, _))
        if e.code == rusqlite::ErrorCode::NotADatabase)
    {
        "DatabaseError"
    } else {
        e.python_class()
    };
    json!([class, e.to_string()])
}
fn state(db: &Path, held: Option<&Connection>) -> Value {
    let before = fingerprints(db);
    let before_files = files(db);
    let value = inspect(db, held);
    let after = fingerprints(db);
    for i in [0, 1, 3] {
        assert_eq!(
            after[i], before[i],
            "observer must not create or checkpoint files"
        );
    }
    // A held WAL reader may update SHM read marks, but must not create sidecars.
    assert_eq!(files(db), before_files);
    value
}
fn inspect(db: &Path, held: Option<&Connection>) -> Value {
    let mut out = json!({"files":files(db)});
    if !db.exists() {
        return out;
    }
    // This observer must never create sidecars, checkpoint WAL, or mutate the DB.
    let owned;
    let c = match held {
        Some(c) => c,
        None => {
            let uri = format!(
                "file:{}?immutable=1&mode=ro",
                db.to_str().unwrap().replace('\\', "/")
            );
            owned = Connection::open_with_flags(
                uri,
                OpenFlags::SQLITE_OPEN_READ_ONLY | OpenFlags::SQLITE_OPEN_URI,
            )
            .unwrap();
            &owned
        }
    };
    match rows(
        c,
        "SELECT type, name, tbl_name, sql FROM sqlite_master ORDER BY type, name",
    ) {
        Ok(objects) => {
            out["schema_sha256"] = json!(digest::sha256(
                serde_json::to_string(&objects)
                    .unwrap()
                    .encode_utf16()
                    .map(|c| {
                        if c < 128 {
                            char::from(c as u8).to_string()
                        } else {
                            format!("\\u{c:04x}")
                        }
                    })
                    .collect::<String>()
                    .as_bytes()
            ));
            out["pragmas"] = json!(
                ["journal_mode", "user_version", "application_id"]
                    .into_iter()
                    .map(|p| (
                        p.to_owned(),
                        rows(c, &format!("PRAGMA {p}")).unwrap()[0][0].clone()
                    ))
                    .collect::<serde_json::Map<_, _>>()
            );
            out["migrations"] = if objects
                .as_array()
                .unwrap()
                .iter()
                .any(|r| r[1] == "schema_migrations")
            {
                let mut migrations =
                    rows(c, "SELECT * FROM schema_migrations ORDER BY version").unwrap();
                // Only the clock is injected in Python; Rust uses the real clock.
                for row in migrations.as_array_mut().unwrap() {
                    row[2] = json!("<time>");
                }
                migrations
            } else {
                Value::Null
            };
        }
        Err(e) => out["error"] = error(&e.into()),
    }
    out
}
fn readonly(db: &Path, enabled: bool) {
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        std::fs::set_permissions(
            db,
            std::fs::Permissions::from_mode(if enabled { 0o444 } else { 0o644 }),
        )
        .unwrap();
    }
    #[cfg(windows)]
    {
        let mut permissions = db.metadata().unwrap().permissions();
        permissions.set_readonly(enabled);
        std::fs::set_permissions(db, permissions).unwrap();
    }
}
fn replay(name: &str, tmp: &Path) -> Value {
    let (action, mode) = name.split_once('.').unwrap();
    let db = if action == "args" {
        tmp.join("db")
    } else {
        tmp.join("nested/db")
    };
    std::fs::create_dir_all(db.parent().unwrap()).unwrap();
    let mut held = None;
    if action != "args" {
        match mode {
            "missing" | "vec_available" => {}
            "empty" => std::fs::write(&db, "").unwrap(),
            "invalid" => std::fs::write(&db, "not sqlite").unwrap(),
            _ => {
                let c = Connection::open(&db).unwrap();
                if mode != "fresh" {
                    let entries = store::migrations()
                        .into_iter()
                        .filter(|m| {
                            if mode == "wal" {
                                m.version.as_str() <= "002"
                            } else if let Some(v) = mode.strip_prefix("earlier_") {
                                m.version.as_str() <= v
                            } else {
                                true
                            }
                        })
                        .collect::<Vec<_>>();
                    store::apply_entries(&c, &entries).unwrap();
                    c.execute("UPDATE schema_migrations SET applied_at='<time>'", [])
                        .unwrap();
                }
                match mode {
                    "future" => {
                        c.execute(
                            "INSERT INTO schema_migrations VALUES ('999','future','<time>')",
                            [],
                        )
                        .unwrap();
                    }
                    "versionless" => {
                        c.execute("DELETE FROM schema_migrations", []).unwrap();
                    }
                    "wal" => c
                        .execute_batch(
                            "PRAGMA journal_mode=WAL;
                        PRAGMA wal_autocheckpoint=0; CREATE TABLE wal_marker(value);
                        INSERT INTO wal_marker VALUES (7);",
                        )
                        .unwrap(),
                    _ => {}
                }
                if mode == "wal" {
                    held = Some(c);
                } else {
                    drop(c);
                }
                if mode == "readonly" {
                    readonly(&db, true);
                }
            }
        }
    }
    let db_str = db.to_str().unwrap();
    let args = if action == "args" {
        match mode {
            "help" => vec!["--help"],
            "missing" => vec![],
            "unknown" => vec!["rollback"],
            "option" => vec!["up", "--bad"],
            "db_value" => vec!["status", "--db"],
            "up_help" => vec!["up", "--help"],
            "status_help" => vec!["status", "--help"],
            _ => panic!("unmapped {name}"),
        }
    } else {
        vec![action, "--db", db_str]
    };
    let before = state(&db, held.as_ref());
    let hashes = fingerprints(&db);
    let (mut connections, mut failure) = (vec![], None);
    let (code, stdout, stderr) = migrate::main(
        &args,
        tmp,
        |path| {
            let mut c = store::connect(path, None)?;
            c.vec_available = mode == "vec_available";
            c.vec_reason = "fixture";
            connections.push(json!(
                [
                    "journal_mode",
                    "synchronous",
                    "foreign_keys",
                    "query_only",
                    "busy_timeout"
                ]
                .into_iter()
                .map(|p| (
                    p.to_owned(),
                    rows(&c.conn, &format!("PRAGMA {p}")).unwrap()[0][0].clone()
                ))
                .collect::<serde_json::Map<_, _>>()
            ));
            Ok(c)
        },
        |e| failure = Some(error(&e)),
    );
    let changed = json!(
        SUFFIXES
            .into_iter()
            .zip(fingerprints(&db).into_iter().zip(hashes))
            .map(|(s, (after, before))| (s.to_owned(), json!(after != before)))
            .collect::<serde_json::Map<_, _>>()
    );
    if failure.is_some() {
        assert_eq!(code, 1, "failed migrations must not exit zero");
    }
    let mut value = json!({"before":before,"after":state(&db, held.as_ref()),
        "connections":connections,"files_changed":changed,"error":failure,
        "exit":if failure.is_some() { Value::Null } else { json!(code) },
        "stdout":String::from_utf8(stdout).unwrap(),
        "stderr":String::from_utf8(stderr).unwrap().replace(tmp.to_str().unwrap(), "<tmp>")});
    if let Some(c) = &held {
        value["wal_rows"] = rows(c, "SELECT * FROM wal_marker").unwrap();
    }
    drop(held);
    if mode == "readonly" {
        readonly(&db, false);
    }
    json!({"value":value})
}
#[test]
fn frozen_records() {
    let records: Value =
        serde_json::from_str(include_str!("fixtures/w2/b16-migrate.json")).unwrap();
    let records = records.as_object().unwrap();
    assert_eq!(records.len(), 42);
    let root = std::env::var_os("TMPDIR").expect("TMPDIR must select task scratch");
    let mut replayed = 0;
    for (name, expected) in records {
        let tmp = tempfile::tempdir_in(&root).unwrap();
        assert_eq!(&replay(name, tmp.path()), expected, "{name}");
        replayed += 1;
    }
    assert_eq!((replayed, 0), (42, 0), "replayed / exempt");
}
#[test]
fn default_database_path() {
    let tmp = tempfile::tempdir_in(std::env::var_os("TMPDIR").unwrap()).unwrap();
    for args in [
        vec!["status"],
        vec!["status", "--db", ""],
        vec!["status", "--db=other"],
        vec!["status", "--d", "other"],
    ] {
        let mut seen = None;
        let (code, _, _) = migrate::main(
            &args,
            tmp.path(),
            |path| {
                seen = Some(path.to_owned());
                Err(store::Error::Snapshot("synthetic failure"))
            },
            |_| {},
        );
        assert_eq!(code, 1);
        let explicit = args.last().is_some_and(|v| v.contains("other"));
        assert_eq!(
            seen.unwrap(),
            if explicit {
                PathBuf::from("other")
            } else if args.len() > 1 {
                PathBuf::from(".")
            } else {
                tmp.path().join(".mir/memory.db")
            }
        );
    }
}
