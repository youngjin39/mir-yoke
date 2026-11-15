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

fn observe_root(name: &str, mut value: Value, root: &str) -> Value {
    // 6b8796fa memory.py:434,233: Path in errors[0], then JSON stdout.
    // Replace only that error's JSON-escaped synthetic root; keep suffix bytes.
    if name == "doctor.missing.True"
        && let Some(text) = value["value"]["command"]["stdout"].as_str()
    {
        let plain = root.strip_prefix(r"\\?\").unwrap_or(root);
        let mut text = text.to_owned();
        for spelling in [root.to_owned(), plain.to_owned(), plain.replace('\\', "/")] {
            for separator in ["/", r"\"] {
                let encoded = serde_json::to_string(&format!("{spelling}{separator}")).unwrap();
                let suffix = serde_json::to_string(separator).unwrap();
                text = text.replace(
                    &format!(
                        "\"errors\":[\"memory database is missing: {}",
                        &encoded[1..encoded.len() - 1]
                    ),
                    &format!(
                        "\"errors\":[\"memory database is missing: <tmp>{}",
                        &suffix[1..suffix.len() - 1]
                    ),
                );
            }
        }
        value["value"]["command"]["stdout"] = json!(text);
    }
    // Python 6b8796fa memory.py:511,571: observe only the two displayed error paths.
    if name == "doctor.stale.True"
        && let Some(text) = value["value"]["command"]["stdout"].as_str()
    {
        let mut report: Value = serde_json::from_str(text).unwrap();
        for error in report["errors"].as_array_mut().unwrap() {
            let text = error.as_str().unwrap();
            let plain = root.strip_prefix(r"\\?\").unwrap_or(root);
            let (prefix, path, separator) = if text.starts_with("archive root drift for 'docs': ") {
                (
                    "archive root drift for 'docs': ",
                    format!("{plain}\\"),
                    r"\",
                )
            } else if text.starts_with("archive FTS5 probe failed: [Errno 2] ") {
                (
                    "archive FTS5 probe failed: [Errno 2] ",
                    format!("{}\\\\", plain.replace('\\', r"\\")),
                    r"\\",
                )
            } else {
                continue;
            };
            *error = json!(format!(
                "{prefix}{}",
                text[prefix.len()..].replace(&path, &format!("<tmp>{separator}"))
            ));
        }
        value["value"]["command"]["stdout"] = json!(report.to_string() + "\n");
    }
    value
}

#[test]
fn wt_core_a_d_roots() {
    let root = r"\\?\C:\synthetic\case";
    for spelling in [root, r"C:\synthetic\case", "C:/synthetic/case"] {
        for suffix in ["/.mir/db", r"\.mir\db"] {
            let text =
                json!({"errors":[format!("memory database is missing: {spelling}{suffix}")]})
                    .to_string();
            let input = json!({"value":{"command":{"stdout":text,"stderr":text}}});
            let mut expected = input.clone();
            expected["value"]["command"]["stdout"] = json!(
                json!({"errors":[format!("memory database is missing: <tmp>{suffix}")]})
                    .to_string()
            );
            assert_eq!(
                observe_root("doctor.missing.True", input.clone(), root),
                expected
            );
            assert_eq!(observe_root("other", input.clone(), root), input);
            let other = text.replace("case", "case-other");
            let input = json!({"value":{"command":{"stdout":other}}});
            assert_eq!(
                observe_root("doctor.missing.True", input.clone(), root),
                input
            );
        }
    }
}
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
    let mut failures = Vec::new();
    for (name, expected) in records.as_object().unwrap() {
        let tmp = tempfile::Builder::new()
            .prefix("b14-")
            .tempdir_in(std::env::temp_dir())
            .unwrap();
        let root = tmp.path().canonicalize().unwrap();
        let actual = std::panic::catch_unwind(|| replay(name, &root));
        let Ok(actual) = actual else {
            failures.push(format!("record {name}: replay panicked"));
            replayed += 1;
            continue;
        };
        let actual = observe_root(name, actual, root.to_str().unwrap());
        let actual = observe_paths(name, normalize(actual, &root));
        // Apply the same existing field observation to the selected platform oracle.
        let expected = observe_paths(name, platform_expected(name, expected, cfg!(windows)));
        if actual != expected {
            failures.push(format!(
                "record {name}: actual={actual}, expected={expected}"
            ));
        }
        replayed += 1;
        println!("{name}: replayed");
    }
    assert!(failures.is_empty(), "{}", failures.join("\n"));
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

fn platform_expected(name: &str, expected: &Value, windows: bool) -> Value {
    // Only these explicitly uncaptured records retain the Unix expectation.
    if !windows || matches!(name, "doctor.relative_link.True") {
        return expected.clone();
    }
    let capture: Value = serde_json::from_str(
        &include_str!("fixtures/w2/b14-gc-doctor-windows-all.json").replace("{ROOT}", "<tmp>"),
    )
    .unwrap();
    capture["records"]
        .get(name)
        .expect("record missing from Windows capture")
        .clone()
}

#[test]
fn wt_core_a_f_expectations() {
    let unix: Value = serde_json::from_str(include_str!("fixtures/w2/b14-gc-doctor.json")).unwrap();
    let capture: Value = serde_json::from_str(
        &include_str!("fixtures/w2/b14-gc-doctor-windows-all.json").replace("{ROOT}", "<tmp>"),
    )
    .unwrap();
    let captured = capture["records"].as_object().unwrap();
    // These records are absent from the PC capture; retain their existing handling.
    let absent = ["doctor.relative_link.True"];
    assert_eq!(captured.len(), 39);
    assert_eq!(capture["exempt"], json!(absent));
    assert_eq!(
        captured.len() + absent.len(),
        unix.as_object().unwrap().len()
    );
    let single: Value = serde_json::from_str(
        &include_str!("fixtures/w2/b14-gc-doctor-windows.json").replace("{ROOT}", "<tmp>"),
    )
    .unwrap();
    assert_eq!(captured["doctor.missing.True"], single);
    for name in captured.keys() {
        assert!(unix.get(name).is_some(), "unknown captured record {name}");
    }
    for (name, expected) in unix.as_object().unwrap() {
        assert_eq!(platform_expected(name, expected, false), *expected);
        let wanted = if absent.contains(&name.as_str()) {
            assert!(!captured.contains_key(name));
            expected
        } else {
            captured
                .get(name)
                .expect("record missing from Windows capture")
        };
        assert_eq!(platform_expected(name, expected, true), *wanted, "{name}");
        // Distinguish selection even where the two platform values happen to match.
        let sentinel = json!({"wrong_unix_expectation":name});
        let wanted = if absent.contains(&name.as_str()) {
            &sentinel
        } else {
            wanted
        };
        assert_eq!(platform_expected(name, &sentinel, true), *wanted, "{name}");
    }
}

// Exercise the display route with real canonicalisation and a real missing-file error.
#[test]
fn wt_core_a_g_display_observation() {
    let root = r"\\?\C:\synthetic\case";
    let plain = r"C:\synthetic\case";
    let errors = json!([
        format!("archive root drift for 'docs': {plain}\\elsewhere != {plain}\\docs"),
        format!(
            "archive FTS5 probe failed: [Errno 2] No such file or directory: '{}\\\\elsewhere\\\\note.md'",
            plain.replace('\\', r"\\")
        ),
        format!("unrelated: {plain}\\docs"),
    ]);
    let input = json!({"value":{"command":{"stdout":json!({"errors":errors}).to_string()+"\n"}}});
    let observed = observe_root("doctor.stale.True", input.clone(), root);
    let report: Value =
        serde_json::from_str(observed["value"]["command"]["stdout"].as_str().unwrap()).unwrap();
    assert_eq!(
        report["errors"][0],
        r"archive root drift for 'docs': <tmp>\elsewhere != <tmp>\docs"
    );
    assert_eq!(
        report["errors"][1],
        r"archive FTS5 probe failed: [Errno 2] No such file or directory: '<tmp>\\elsewhere\\note.md'"
    );
    assert_eq!(report["errors"][2], errors[2]);
    assert_eq!(observe_root("other", input.clone(), root), input);
}

#[cfg(windows)]
#[test]
fn wt_core_a_g_doctor_display_paths() {
    let tmp = tempfile::tempdir().unwrap();
    let root = tmp.path().canonicalize().unwrap();
    assert!(root.to_str().unwrap().starts_with(r"\\?\"));
    let plain = handoff_packet::supply::plain(root.clone());
    let actual = replay("doctor.stale.True", &root);
    let report: Value =
        serde_json::from_str(actual["value"]["command"]["stdout"].as_str().unwrap()).unwrap();
    assert_eq!(
        report["errors"],
        json!([
            format!(
                "archive root drift for 'docs': {} != {}",
                plain.join("elsewhere").display(),
                plain.join("docs").display()
            ),
            "archive has no successful current sync evidence: 'docs'",
            format!(
                "archive FTS5 probe failed: [Errno 2] No such file or directory: '{}'",
                plain
                    .join("elsewhere/note.md")
                    .display()
                    .to_string()
                    .replace('\\', r"\\")
            ),
        ])
    );
    // The display conversion must not change the stored or accessed path.
    assert_eq!(
        actual["value"]["after"]["rows"]["external_archives"][0][2],
        root.join("elsewhere").to_str().unwrap()
    );
}
