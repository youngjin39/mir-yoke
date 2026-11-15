//! Replay the 53 frozen Python B15 render records against synthetic databases.
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
const START: &str = "<!-- mir:generated:start -->";
const END: &str = "<!-- mir:generated:end -->";
fn clock() -> SystemTime {
    UNIX_EPOCH + Duration::from_secs(981173106)
}
fn manual() -> String {
    format!("Manual prefix\t \n{START}\nstale\n{END}\nManual suffix  \n")
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
fn normalize(value: Value, root: &Path) -> Value {
    match value {
        Value::String(s) => {
            let root = root.to_str().unwrap();
            let s = s
                .replace(&root.replace('\\', "\\\\"), "<tmp>")
                .replace(root, "<tmp>");
            let chars: Vec<char> = s.chars().collect();
            if chars.len() > 256 {
                json!({"length":chars.len(), "sha256":digest::sha256(s.as_bytes()),
                    "first":chars[..120].iter().collect::<String>(),
                    "last":chars[chars.len()-120..].iter().collect::<String>()})
            } else {
                json!(s)
            }
        }
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
fn write_text(path: &Path, text: &str) {
    let text = if cfg!(windows) {
        text.replace('\n', "\r\n")
    } else {
        text.into()
    };
    std::fs::write(path, text).unwrap();
}
fn populate(conn: &Connection, root: &Path) -> Vec<Value> {
    let mut ingests = Vec::new();
    for (rel, fields) in [
        (
            "docs/decisions/adr-z.md",
            "title: Z | title\nkeywords: [z, a, z]\nlesson: last",
        ),
        (
            "docs/decisions/adr-a.md",
            "title: \u{e9}\nkeywords: [b, a]\nlesson: first",
        ),
        ("docs/decisions/adr-bare.md", "use: fallback"),
        (
            "docs/_archive/adr-hidden.md",
            "title: hidden\nlesson: excluded",
        ),
        (
            "docs/_archive/nested/adr-hidden.md",
            "title: nested\nlesson: excluded",
        ),
        ("docs/_archive-neighbor/adr-visible.md", "title: neighbor"),
    ] {
        let path = root.join(rel);
        std::fs::create_dir_all(path.parent().unwrap()).unwrap();
        write_text(&path, &format!("---\n{fields}\n---\nbody\n"));
        ingests.push(json!(
            d::ingest_markdown_file(&path, conn, root, &["**"], clock).unwrap()
        ));
    }
    let path = root.join("docs/decisions/adr-z.md");
    write_text(
        &path,
        "---\ntitle: updated\nkeywords: [z, c]\nlesson: replaced\n---\nbody2\n",
    );
    ingests.push(json!(
        d::ingest_markdown_file(&path, conn, root, d::DEFAULT_WHITELIST, clock).unwrap()
    ));
    ingests
}
fn invoke(
    conn: &Connection,
    root: &Path,
    args: &[String],
    direct: bool,
    options: (&str, bool, Option<&Path>),
    stdout: &mut String,
    stderr: &mut String,
) -> Value {
    let result = if direct {
        cli::render(conn, options.0, options.1, options.2)
    } else {
        let argv: Vec<&str> = args.iter().map(String::as_str).collect();
        cli::main_with_clock(&argv, &root.join("synthetic.db"), root, clock)
    };
    match result {
        Ok((code, out, err)) => {
            stdout.push_str(std::str::from_utf8(&out).unwrap());
            stderr.push_str(std::str::from_utf8(&err).unwrap());
            if code == 2 {
                json!({"error":["SystemExit","2"]})
            } else {
                json!({"value":code})
            }
        }
        Err(e) => json!({"error":[e.python_class(),e.to_string()]}),
    }
}
fn replay(name: &str, conn: &Connection, root: &Path) -> Value {
    if name == "cli.relative_missing_db" {
        // The message keeps the --db spelling; the file is looked up from the working directory.
        let argv = ["render", "--db", "absent.db"];
        let (code, out, _) =
            cli::main_with_clock(&argv, &root.join("synthetic.db"), root, clock).unwrap();
        return json!({"exit":code,"stdout":String::from_utf8(out).unwrap()});
    }
    let empty = name.starts_with("empty") || name == "helpers.empty";
    let ingests = if empty { vec![] } else { populate(conn, root) };
    if name == "helpers.direct_facts" {
        // Direct inserts bypass ingest dedup: recall dedups keywords and render trims lessons.
        for (predicate, value) in [("keywords", "b"), ("lesson", "\t padded \n")] {
            let triple = d::Triple::new("adr-a", predicate, value);
            d::insert_triple(conn, &triple, "ephemeral", clock).unwrap();
        }
        return json!({"index":d::recall_ingested_index(conn).unwrap(),
            "lessons":d::recall_lessons(conn).unwrap(),
            "lessons_markdown":cli::render_lessons_section(conn).unwrap()});
    }
    if name.starts_with("helpers.") {
        let mut pragmas = json!({});
        for p in ["journal_mode", "foreign_keys", "synchronous"] {
            pragmas[p] = rows(conn, &format!("PRAGMA {p}"))[0][0].clone();
        }
        return json!({"ingests":ingests,
            "index":d::recall_ingested_index(conn).unwrap(),
            "lessons":d::recall_lessons(conn).unwrap(),
            "map_markdown":cli::render_memory_map_section(conn).unwrap(),
            "lessons_markdown":cli::render_lessons_section(conn).unwrap(),
            "pragmas":pragmas,
            "migrations":rows(conn,"SELECT * FROM schema_migrations ORDER BY version"),
            "objects":rows(conn,
                "SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name")});
    }
    #[cfg(unix)]
    if name == "cli.in_place" {
        // Python write_text keeps the existing file: mode bits and a symlinked path survive.
        use std::os::unix::fs::PermissionsExt;
        let real = root.join("out/real.md");
        std::fs::create_dir_all(real.parent().unwrap()).unwrap();
        std::fs::write(&real, manual()).unwrap();
        std::fs::set_permissions(&real, std::fs::Permissions::from_mode(0o640)).unwrap();
        let link = root.join("out/link.md");
        std::os::unix::fs::symlink("real.md", &link).unwrap();
        let args: Vec<String> = [
            "render",
            "--apply",
            "--target",
            "lessons",
            "--db",
            root.join("synthetic.db").to_str().unwrap(),
            "--output-path",
            link.to_str().unwrap(),
        ]
        .map(String::from)
        .into();
        let (mut stdout, mut stderr) = (String::new(), String::new());
        let result = invoke(
            conn,
            root,
            &args,
            false,
            ("lessons", true, Some(&link)),
            &mut stdout,
            &mut stderr,
        );
        let mode = std::fs::metadata(&real).unwrap().permissions().mode() & 0o777;
        return json!({"result":result,"stdout":stdout,"mode":format!("0o{mode:o}"),
            "link_is_symlink":link.symlink_metadata().unwrap().file_type().is_symlink(),
            "real":std::fs::read_to_string(&real).unwrap()});
    }
    let output = root.join("out/nested/projection.md");
    let body = if let Some(mode) = name.strip_prefix("markers.") {
        match mode.parse::<usize>().unwrap() {
            0 => None,
            1 => Some(String::new()),
            2 => Some("manual".into()),
            3 => Some("manual\n".into()),
            4 => Some("manual\n\n".into()),
            5 => Some(manual()),
            6 => Some(format!("{START}\norphan\n")),
            7 => Some(format!("orphan\n{END}")),
            8 => Some(format!("{}{START}\nsecond\n{END}\ntail", manual())),
            9 => Some(format!("{END}\nreverse\n{START}")),
            10 => Some(format!("crlf\r\n{START}\r\nold\r\n{END}\r\ntail\r")),
            _ => unreachable!(),
        }
    } else {
        Some(manual())
    };
    if let Some(body) = body {
        std::fs::create_dir_all(output.parent().unwrap()).unwrap();
        write_text(&output, &body);
    }
    let parts: Vec<&str> = name.split('.').collect();
    let direct = parts[0] == "direct";
    let normal = (parts[0] == "cli" || direct) && parts.len() == 4;
    let (target, apply, explicit) = if normal {
        (parts[1], parts[2] == "True", parts[3] == "True")
    } else if parts[0] == "empty" {
        ("all", parts[2] == "True", true)
    } else {
        ("all", true, true)
    };
    let mut args = vec!["render".to_owned()];
    if name == "cli.invalid_target" {
        args.extend(["--target".into(), "unknown".into()]);
    } else if name == "cli.unsupported_exclusion" {
        args.extend(["--exclude".into(), "docs/_archive/".into()]);
    } else {
        if (normal || parts[0] == "empty") && target != "None" {
            args.extend(["--target".into(), target.into()]);
        }
        if apply {
            args.push("--apply".into());
        }
        if explicit {
            args.extend(["--output-path".into(), output.to_str().unwrap().into()]);
        }
    }
    if parts[0] != "cli" || target != "None" || !normal {
        args.extend([
            "--db".into(),
            root.join("synthetic.db").to_str().unwrap().into(),
        ]);
    }
    let mut stdout = String::new();
    let mut stderr = String::new();
    let mut results = vec![invoke(
        conn,
        root,
        &args,
        direct,
        (
            if target == "None" { "all" } else { target },
            apply,
            explicit.then_some(output.as_path()),
        ),
        &mut stdout,
        &mut stderr,
    )];
    if name == "cli.second_failure" {
        let first = std::fs::read_to_string(&output).unwrap();
        let blocked = root.join("second.md");
        std::fs::create_dir(&blocked).unwrap();
        let args = vec![
            "render".into(),
            "--apply".into(),
            "--target".into(),
            "lessons".into(),
            "--db".into(),
            root.join("synthetic.db").to_str().unwrap().into(),
            "--output-path".into(),
            blocked.to_str().unwrap().into(),
        ];
        results.push(invoke(
            conn,
            root,
            &args,
            false,
            ("lessons", true, Some(&blocked)),
            &mut stdout,
            &mut stderr,
        ));
        results.push(
            json!({"first_after_failure":std::fs::read_to_string(&output).unwrap(),
            "first_before_failure":first,"second_is_file":blocked.is_file()}),
        );
    }
    json!({"results":results,"stdout":stdout,"stderr":stderr,
        "file":std::fs::read_to_string(&output).ok()})
}
fn capture() -> Value {
    serde_json::from_str(include_str!("fixtures/w2/wt-core-c-windows.json")).unwrap()
}
fn records(windows: bool) -> Value {
    let unix: Value = serde_json::from_str(include_str!("fixtures/w2/b15-render.json")).unwrap();
    if !windows {
        return unix;
    }
    let capture = capture();
    let captured = capture["b15"].as_object().unwrap();
    assert_eq!(captured.len(), unix.as_object().unwrap().len());
    unix.as_object()
        .unwrap()
        .keys()
        .map(|name| {
            let record = captured
                .get(name)
                .unwrap_or_else(|| panic!("missing Windows record: {name}"));
            (
                name.clone(),
                normalize(record["observation"].clone(), Path::new("{ROOT}")),
            )
        })
        .collect::<serde_json::Map<_, _>>()
        .into()
}

#[test]
fn windows_capture_selector() {
    let windows = capture();
    let record = &windows["b15"]["cli.None.True.True"];
    assert_eq!(record["byte_length"], 558);
    assert_eq!(record["character_length"], 549);
    assert_eq!(
        record["sha256"],
        "276f78da771ee415532e3851631079337365d61dc9edb2781954b37fc65e7942"
    );
    assert_eq!(
        record["observation"]["value"]["stdout"],
        "render applied \u{2192} {ROOT}\\out\\nested\\projection.md\n"
    );
    assert_eq!(records(false).as_object().unwrap().len(), 53);
}

#[test]
fn every_windows_record_maps_without_fallback() {
    let capture: Value =
        serde_json::from_str(include_str!("fixtures/w2/wt-core-c-windows.json")).unwrap();
    let windows = records(true);
    let unix = records(false);
    assert_eq!(capture["b15"].as_object().unwrap().len(), 53);
    assert_eq!(
        windows.as_object().unwrap().keys().collect::<Vec<_>>(),
        unix.as_object().unwrap().keys().collect::<Vec<_>>()
    );
    for (name, record) in capture["b15"].as_object().unwrap() {
        assert_eq!(
            windows[name],
            normalize(record["observation"].clone(), Path::new("{ROOT}")),
            "{name}"
        );
    }
}

#[test]
fn frozen_records() {
    // Every scenario uses its own captured Windows expectation; Unix is unchanged.
    let oracle = records(false);
    let windows = capture();
    let selected = records(cfg!(windows));
    let mut failures = Vec::new();
    let total = 53;
    assert_eq!(oracle.as_object().unwrap().len(), total);
    let (mut replayed, mut exempt) = (0, 0);
    for (name, _) in oracle.as_object().unwrap() {
        let expected = &selected[name];
        if cfg!(windows) && name == "cli.in_place" {
            // Unix mode bits and an unprivileged symlink have no Windows equivalent.
            println!("{name}: exempt (Windows symlink/mode privilege)");
            exempt += 1;
            continue;
        }
        let result =
            std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
                let temp = tempfile::Builder::new()
                    .prefix("b15-")
                    .tempdir_in(std::env::temp_dir())
                    .unwrap();
                let root = temp.path().canonicalize().unwrap();
                let db = store::connect(&root.join("synthetic.db"), None).unwrap();
                store::apply_migrations(&db.conn).unwrap();
                db.conn
                    .execute("UPDATE schema_migrations SET applied_at=?", [CLOCK])
                    .unwrap();
                let actual = normalize(json!({"value":replay(name, &db.conn, &root)}), &root);
                if cfg!(windows) {
                    let captured = &windows["b15"][name];
                    let bytes = std::fs::read(root.join("out/nested/projection.md")).ok();
                    let actual_file = bytes.as_ref().map(|bytes| json!({
                "file_hex": bytes.iter().map(|b| format!("{b:02x}")).collect::<String>(),
                "byte_length": bytes.len(), "sha256": digest::sha256(bytes),
                "character_length": std::str::from_utf8(bytes).unwrap().chars().count()
            }));
                    let expected_file = (!captured["file_hex"].is_null()).then(|| json!({
                "file_hex": captured["file_hex"], "byte_length": captured["byte_length"],
                "sha256": captured["sha256"], "character_length": captured["character_length"]
            }));
                    if actual_file != expected_file {
                        failures.push(format!(
                            "{name}: file actual={actual_file:?} expected={expected_file:?}"
                        ));
                    }
                }
                if actual != *expected {
                    failures.push(format!(
                        "{name}: observation actual={actual} expected={expected}"
                    ));
                }
            }));
        if result.is_err() {
            failures.push(format!("{name}: replay panicked"));
        }
        replayed += 1;
        println!("render:{name}: replayed");
    }
    assert!(
        failures.is_empty(),
        "{} mismatches:\n{}",
        failures.len(),
        failures.join("\n")
    );
    assert_eq!(replayed + exempt, total);
    println!("replayed={replayed} exempt={exempt} total={total}");
}

#[test]
fn render_directory_failure() {
    let tmp = tempfile::tempdir().unwrap();
    let db = store::connect(&tmp.path().join("synthetic.db"), None).unwrap();
    store::apply_migrations(&db.conn).unwrap();
    let blocked = tmp.path().join("blocked.md");
    std::fs::create_dir(&blocked).unwrap();
    // This seam reaches the real OS failure, rather than injecting an Error.
    assert!(std::fs::write(&blocked, "probe").is_err());
    let error = cli::render(&db.conn, "all", true, Some(&blocked)).unwrap_err();
    let (class, message) = if cfg!(windows) {
        ("PermissionError", "[Errno 13] Permission denied:")
    } else {
        ("IsADirectoryError", "[Errno 21] Is a directory:")
    };
    assert_eq!(error.python_class(), class);
    assert!(error.to_string().starts_with(message));
    assert!(blocked.is_dir());
}
