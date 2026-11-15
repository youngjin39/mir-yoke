//! Exact B14 oracle replay; all databases and projects are synthetic.
#[path = "../src/digest.rs"]
mod digest;
use handoff_packet::{mir_cli::memory as cli, mir_core::memory::store};
use rusqlite::{Connection, types::ValueRef};
use serde_json::{Value, json};
use std::{
    path::Path,
    time::{Duration, SystemTime, UNIX_EPOCH},
};
const NOW: &str = "2030-01-02T00:00:00.123456+00:00";
fn clock() -> SystemTime {
    UNIX_EPOCH + Duration::new(1893542400, 123456000)
}
fn rows(conn: &Connection, sql: &str) -> rusqlite::Result<Value> {
    let mut stmt = conn.prepare(sql)?;
    let count = stmt.column_count();
    let values = stmt
        .query_map([], |r| {
            (0..count)
                .map(|i| {
                    Ok(match r.get_ref(i)? {
                        ValueRef::Null => Value::Null,
                        ValueRef::Integer(n) => json!(n),
                        ValueRef::Real(n) => json!(n),
                        ValueRef::Text(s) => json!(std::str::from_utf8(s).unwrap()),
                        ValueRef::Blob(_) => panic!("unexpected blob"),
                    })
                })
                .collect::<rusqlite::Result<Vec<_>>>()
        })?
        .collect::<rusqlite::Result<Vec<_>>>()?;
    Ok(json!(values))
}
// json.dumps default separators, preserving SQL string bytes (including commas).
fn python_json(v: &Value) -> String {
    match v {
        Value::Array(a) => format!(
            "[{}]",
            a.iter().map(python_json).collect::<Vec<_>>().join(", ")
        ),
        _ => serde_json::to_string(v)
            .unwrap()
            .chars()
            .map(|c| {
                if c.is_ascii() {
                    c.to_string()
                } else {
                    c.encode_utf16(&mut [0; 2])
                        .iter()
                        .map(|u| format!("\\u{u:04x}"))
                        .collect::<String>()
                }
            })
            .collect(),
    }
}
fn state(db: &Path) -> Value {
    if !db.exists() {
        return json!({"exists":false});
    }
    let conn = Connection::open_with_flags(db, rusqlite::OpenFlags::SQLITE_OPEN_READ_ONLY).unwrap();
    let objects = match rows(
        &conn,
        "SELECT type, name, tbl_name, sql FROM sqlite_master ORDER BY type, name",
    ) {
        Ok(v) => v,
        Err(e) => return json!({"error":["DatabaseError",e.to_string()]}),
    };
    let mut tables = json!({});
    for table in [
        "schema_migrations",
        "entities",
        "facts",
        "audit_log",
        "sqlite_sequence",
        "external_archives",
        "external_store_meta",
        "external_documents",
        "external_chunks",
    ] {
        if objects
            .as_array()
            .unwrap()
            .iter()
            .any(|o| o[0] == "table" && o[1] == table)
        {
            tables[table] = rows(&conn, &format!("SELECT * FROM \"{table}\" ORDER BY 1")).unwrap();
        }
    }
    let mut pragmas = json!({});
    for p in ["journal_mode", "user_version", "application_id"] {
        pragmas[p] = rows(&conn, &format!("PRAGMA {p}")).unwrap()[0][0].clone();
    }
    json!({"objects_sha256":digest::sha256(python_json(&objects).as_bytes()),
        "rows":tables,"pragmas":pragmas})
}
fn normalize(v: Value, root: &Path) -> Value {
    match v {
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
fn replay(name: &str, root: &Path) -> Value {
    let parts: Vec<_> = name.split('.').collect();
    let gc = parts[0] == "gc";
    let mode = if matches!(parts[1], "False" | "True") {
        "migrated"
    } else {
        parts[1]
    };
    let as_json = parts.last() != Some(&"False");
    let apply = gc && parts[1] == "True";
    std::fs::create_dir(root.join(".mir")).unwrap();
    std::fs::create_dir(root.join("docs")).unwrap();
    let db = root.join(".mir/db");
    let vector = if mode == "vector" { "optional" } else { "off" };
    // A TOML escape keeps the file ASCII; the missing archive root is non-ASCII.
    let archive = if mode == "unicode_root" {
        "d\\u00f6cs"
    } else {
        "docs"
    };
    std::fs::write(
        root.join("harness_a.toml"),
        format!(
            "[memory]\nenabled=true\nrequired=true\nbackend=\"sqlite_fts5\"\n\
        db_path=\".mir/db\"\nvector_mode=\"{vector}\"\n[memory.embedding]\n\
        enabled=false\nrequired=false\n[[memory.external_archives]]\n\
        slug=\"docs\"\nroot=\"{archive}\"\n"
        ),
    )
    .unwrap();
    let mut keeper = None;
    match mode {
        "missing" | "db_option" => (),
        "empty" => std::fs::write(&db, "").unwrap(),
        "non_sqlite" => std::fs::write(&db, "not sqlite\n").unwrap(),
        _ => {
            let conn = Connection::open(&db).unwrap();
            store::apply_migrations(&conn).unwrap();
            conn.execute("UPDATE schema_migrations SET applied_at=?", [NOW])
                .unwrap();
            if gc {
                for date in [
                    None,
                    Some("2030-01-01"),
                    Some("2030-01-01T23:59:59+00:00"),
                    Some("2030-01-02"),
                    Some("2030-01-02T00:00:00+00:00"),
                    Some("2030-01-03"),
                ] {
                    conn.execute(
                        "INSERT INTO facts(status,valid_to) VALUES ('active',?)",
                        [date],
                    )
                    .unwrap();
                }
                for status in ["expired", "superseded"] {
                    conn.execute(
                        "INSERT INTO facts(status,valid_to) VALUES (?, '2030-01-01')",
                        [status],
                    )
                    .unwrap();
                }
            }
            match mode {
                "missing_migration" => conn
                    .execute_batch(
                        "DELETE FROM schema_migrations WHERE version=(SELECT MIN(version)
                    FROM schema_migrations)",
                    )
                    .unwrap(),
                "future" => {
                    conn.execute(
                        "INSERT INTO schema_migrations VALUES
                    ('999','future',?)",
                        [NOW],
                    )
                    .unwrap();
                }
                "fts_missing" => conn.execute_batch("DROP TABLE facts_fts").unwrap(),
                "fts_broken" => conn.execute_batch("DROP TRIGGER facts_fts_ai").unwrap(),
                "ready" | "ready_short" | "relative_link" | "stale" => {
                    // A synced archive seeded directly; ready_short has no 6-character token,
                    // stale drifted and was never scanned, and an unconfigured archive is ignored.
                    let text = if mode == "ready_short" {
                        "a bc def\n"
                    } else {
                        "alpha betagamma\n"
                    };
                    std::fs::write(root.join("docs/note.md"), text).unwrap();
                    let stale = mode == "stale";
                    let archive = root.join(if stale { "elsewhere" } else { "docs" });
                    conn.execute(
                        "INSERT INTO external_archives(id,slug,root_path,mode,owner,created_at,
                        last_scanned_at) VALUES (1,'docs',?,'indexed','family:docs',?,?)",
                        rusqlite::params![archive.to_str().unwrap(), NOW, (!stale).then_some(NOW)],
                    )
                    .unwrap();
                    conn.execute(
                        "INSERT INTO external_archives(id,slug,root_path,mode,owner,created_at)
                        VALUES (2,'other',?,'indexed','family:other',?)",
                        [root.join("other").to_str().unwrap(), NOW],
                    )
                    .unwrap();
                    conn.execute_batch(
                        "INSERT INTO external_store_meta VALUES
                        ('schema_metadata_version:archive:1','5');
                        INSERT INTO external_documents(id,archive_id,relative_path,file_hash)
                        VALUES (1,1,'note.md','h');",
                    )
                    .unwrap();
                    conn.execute(
                        "INSERT INTO external_chunks VALUES (1,1,0,0,?,'h')",
                        [text.len() as i64],
                    )
                    .unwrap();
                    conn.execute(
                        "INSERT INTO external_chunks_fts(rowid,content) VALUES (1,?)",
                        [text],
                    )
                    .unwrap();
                }
                "wal" => {
                    conn.execute_batch(
                        "PRAGMA journal_mode=WAL; PRAGMA wal_autocheckpoint=0;
                        INSERT INTO facts(status) VALUES ('active');",
                    )
                    .unwrap();
                    keeper = Some(conn);
                }
                _ => (),
            }
        }
    }
    let original_permissions = std::fs::metadata(&db).ok().map(|m| m.permissions());
    if mode == "readonly" {
        let mut permissions = std::fs::metadata(&db).unwrap().permissions();
        permissions.set_readonly(true);
        std::fs::set_permissions(&db, permissions).unwrap();
    }
    let before = state(&db);
    // Relative --db and --project-root resolve against the injected working directory.
    let mut args = match mode {
        "relative_db" => vec![parts[0], "--db", ".mir/db"],
        "relative_root" => vec![parts[0], "--project-root", "nowhere"],
        "relative_missing" => vec![parts[0], "--db", "absent.db"],
        "relative_link" => {
            #[cfg(unix)]
            std::os::unix::fs::symlink(root, root.join("alias")).unwrap();
            #[cfg(windows)]
            std::os::windows::fs::symlink_dir(root, root.join("alias")).unwrap();
            vec![parts[0], "--project-root", "alias"]
        }
        _ => vec![
            parts[0],
            if gc || mode == "db_option" {
                "--db"
            } else {
                "--project-root"
            },
            if gc || mode == "db_option" {
                db.to_str().unwrap()
            } else {
                root.to_str().unwrap()
            },
        ],
    };
    if as_json {
        args.push("--json");
    }
    if apply {
        args.push("--apply");
    }
    let command = match cli::main_with_clock(&args, &db, root, clock) {
        Ok((code, out, err)) => json!({"exit":code,"stdout":String::from_utf8(out).unwrap(),
            "stderr":String::from_utf8(err).unwrap()}),
        Err(e) => json!({"exit":[e.python_class(),e.to_string()],"stdout":"",
            "stderr":e.stderr()}),
    };
    let mut result = json!({"before":before,"command":command,"after":state(&db)});
    if keeper.is_some() {
        result["nonempty_wal"] = json!(
            std::fs::metadata(db.with_file_name("db-wal"))
                .unwrap()
                .len()
                > 0
        );
    }
    if mode == "readonly" {
        std::fs::set_permissions(&db, original_permissions.unwrap()).unwrap();
    }
    drop(keeper);
    json!({"value":result})
}
#[test]
fn frozen_records() {
    let records: Value =
        serde_json::from_str(include_str!("fixtures/w2/b14-gc-doctor.json")).unwrap();
    assert_eq!(records.as_object().unwrap().len(), 40);
    let mut replayed = 0;
    for (name, expected) in records.as_object().unwrap() {
        let tmp = tempfile::Builder::new()
            .prefix("b14-")
            .tempdir_in(std::env::temp_dir())
            .unwrap();
        let root = tmp.path().canonicalize().unwrap();
        let actual = observe_paths(name, normalize(replay(name, &root), &root));
        assert_eq!(&actual, expected, "{name}");
        replayed += 1;
        println!("{name}: replayed");
    }
    assert_eq!(replayed, 40);
    println!("replayed={replayed} exempt=0 total=40");
}

#[test]
fn options_before_database_access() {
    let tmp = tempfile::Builder::new()
        .prefix("b14-options-")
        .tempdir_in(std::env::temp_dir())
        .unwrap();
    let root = tmp.path();
    let db = root.join("absent.db");
    let expected = [
        (
            "gc",
            concat!(
                "usage: mir memory gc [-h] [--apply] [--json] [--db DB]\n\noptions:\n",
                "  -h, --help  show this help message and exit\n",
                "  --apply     apply expiry updates (default: dry-run)\n",
                "  --json      emit machine-readable counts\n  --db DB\n"
            ),
        ),
        (
            "doctor",
            concat!(
                "usage: mir memory doctor [-h] [--project-root PROJECT_ROOT] [--json]\n",
                "\noptions:\n  -h, --help            show this help message and exit\n",
                "  --project-root PROJECT_ROOT\n",
                "                        repository root containing harness_a.toml (default:\n",
                "                        cwd)\n",
                "  --json                emit machine-readable evidence\n"
            ),
        ),
    ];
    for (action, text) in expected {
        for help in ["--help", "-h", "--he"] {
            let output = cli::main_with_clock(&[action, help], &db, root, clock).unwrap();
            assert_eq!(output, (0, text.as_bytes().to_vec(), vec![]));
        }
    }
    let output = cli::main_with_clock(&["gc", "--apply=yes"], &db, root, clock).unwrap();
    assert_eq!(output.0, 2);
    assert!(
        String::from_utf8(output.2)
            .unwrap()
            .contains("ignored explicit argument 'yes'")
    );
    let output = cli::main_with_clock(&["doctor", "--project-root"], &db, root, clock).unwrap();
    assert_eq!(output.0, 2);
    assert!(!db.exists());
}

fn observe_paths(name: &str, mut value: Value) -> Value {
    // Python 6b8796fa:src/mir/cli/memory.py:188-220 rejects --db via argparse.
    // Only its synthetic argv path is platform-dependent; keep the refusal intact.
    if matches!(name, "doctor.db_option.False" | "doctor.db_option.True")
        && let Some(text) = value["value"]["command"]["stderr"].as_str()
    {
        value["value"]["command"]["stderr"] =
            json!(text.replace("--db <tmp>\\.mir\\db\n", "--db <tmp>/.mir/db\n"));
    }
    // Python 6b8796fa:src/mir/cli/memory.py:434 interpolates db_path;
    // :237 prints that error. Match only the missing text record's synthetic path.
    if name == "doctor.missing.False"
        && value["value"]["command"]["stdout"]
            == "memory doctor: not_ready\n  [not-ready] memory database is missing: <tmp>\\.mir\\db\n"
    {
        value["value"]["command"]["stdout"] = json!(
            "memory doctor: not_ready\n  [not-ready] memory database is missing: <tmp>/.mir/db\n"
        );
    }
    value
}

#[test]
fn wt_core_a_paths() {
    let records: Value =
        serde_json::from_str(include_str!("fixtures/w2/b14-gc-doctor.json")).unwrap();
    for name in ["doctor.db_option.False", "doctor.db_option.True"] {
        let expected = &records[name];
        let mut input = expected.clone();
        input["value"]["command"]["stderr"] = json!(
            expected["value"]["command"]["stderr"]
                .as_str()
                .unwrap()
                .replace("<tmp>/.mir/db", r"<tmp>\.mir\db")
        );
        input["value"]["command"]["stdout"] = json!("keep --db <tmp>\\.mir\\db\n");
        let mut wanted = expected.clone();
        wanted["value"]["command"]["stdout"] = input["value"]["command"]["stdout"].clone();
        assert_eq!(observe_paths(name, input.clone()), wanted);
        assert_eq!(observe_paths("gc.False.True", input.clone()), input);
        assert_eq!(observe_paths(name, expected.clone()), *expected);
    }
}

#[test]
fn wt_core_a_c_paths() {
    let records: Value =
        serde_json::from_str(include_str!("fixtures/w2/b14-gc-doctor.json")).unwrap();
    let expected = &records["doctor.missing.False"];
    assert_eq!(
        observe_paths("doctor.missing.False", expected.clone()),
        *expected
    );
    let mut input = expected.clone();
    input["value"]["command"]["stdout"] = json!(
        "memory doctor: not_ready\n  [not-ready] memory database is missing: <tmp>\\.mir\\db\n"
    );
    input["value"]["command"]["stderr"] = json!(r"keep <tmp>\.mir\db");
    let mut wanted = expected.clone();
    wanted["value"]["command"]["stderr"] = input["value"]["command"]["stderr"].clone();
    assert_eq!(observe_paths("doctor.missing.False", input.clone()), wanted);
    assert_eq!(observe_paths("doctor.missing.True", input.clone()), input);
    input["value"]["command"]["stdout"] = json!(r"keep <tmp>\.mir\db");
    assert_eq!(observe_paths("doctor.missing.False", input.clone()), input);
}
