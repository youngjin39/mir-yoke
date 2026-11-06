//! Frozen Python B11 oracle replay. Only synthetic scratch databases are opened.
#[path = "../src/digest.rs"]
mod digest;
use handoff_packet::{
    mir_cli::memory as cli,
    mir_core::memory::{distill as d, store},
};
use rusqlite::{Connection, params, types::ValueRef};
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
        Value::String(s) if s.chars().count() > 256 => json!({"len":s.chars().count(),
            "sha256":digest::sha256(s.as_bytes())}),
        Value::Array(a) => json!(a.into_iter().map(compact).collect::<Vec<_>>()),
        Value::Object(m) => Value::Object(m.into_iter().map(|(k, v)| (k, compact(v))).collect()),
        v => v,
    }
}
fn observe<T: serde::Serialize>(r: Result<T, d::WriteError>) -> Value {
    match r {
        Ok(v) => json!({"value":v}),
        Err(e) => json!({"error":[e.python_class(),e.to_string()]}),
    }
}
fn triple(conn: &Connection, slug: &str, body: &str, content: bool) -> i64 {
    let mut t = d::Triple::new(slug, "use", body);
    t.source_content_id = content.then_some(1);
    d::insert_triple(conn, &t, "ephemeral", clock).unwrap()
}
fn commit(conn: &Connection) {
    if !conn.is_autocommit() {
        conn.execute_batch("COMMIT").unwrap();
    }
}
fn seed(conn: &Connection) {
    conn.execute_batch(
        "BEGIN; INSERT INTO content_items(id,source,text_hash)
        VALUES (1,'test','h')",
    )
    .unwrap();
}
fn reader(root: &Path, ingest: bool) -> Value {
    let conn = Connection::open(root.join("synthetic.db")).unwrap();
    json!({"committed":state(&conn,ingest)})
}
fn replay_insert(name: &str, conn: &Connection, root: &Path) -> Value {
    let mut steps = Vec::new();
    if name == "schema" {
        return schema(conn);
    }
    if name == "upsert.sequence" {
        for (slug, typ) in [
            ("A", None),
            ("A", None),
            ("A", Some("first")),
            ("A", None),
            ("A", Some("changed")),
            ("B", Some("typed")),
            ("", None),
        ] {
            steps.push(json!([
                d::upsert_entity(conn, slug, typ).unwrap(),
                state(conn, false)
            ]));
        }
    } else if name.starts_with("insert.") {
        seed(conn);
        d::upsert_entity(conn, "target", Some("node")).unwrap();
        let (body, consent) = match name {
            "insert.0" => ("plain target", "ephemeral"),
            "insert.1" => ("target", "persistent"),
            "insert.2" => (
                "<PRIVATE>a\nb</PRIVATE><secret>s</secret><noindex>n</noindex>",
                "ephemeral",
            ),
            "insert.3" => (
                "<private>a\nb</private><SECRET>s</SECRET><noindex>n</noindex>",
                "persistent",
            ),
            "insert.4" => ("<private>x</private>", "unknown"),
            _ => panic!("unhandled {name}"),
        };
        for _ in 0..2 {
            let mut t = d::Triple::new("A", " Uses ", body);
            t.source_content_id = Some(1);
            t.scope = "project".into();
            t.project_path = Some("project".into());
            t.polarity = "negated".into();
            t.confidence = 0.25;
            steps.push(json!([
                d::insert_triple(conn, &t, consent, clock).unwrap(),
                state(conn, false)
            ]));
        }
    } else if let Some(mode) = name.strip_prefix("supersede.") {
        seed(conn);
        let (old_time, new_time, old_conf, new_conf) = match mode {
            "newer" => (Some("a"), "b", Some(1.0), 0.0),
            "older" => (Some("b"), "a", Some(0.0), 1.0),
            "higher" => (Some("a"), "a", Some(0.2), 0.8),
            "lower" => (Some("a"), "a", Some(0.8), 0.2),
            "tie" => (Some("a"), "a", Some(0.5), 0.5),
            "null" => (None, "", None, 0.5),
            "second" => (Some("c"), "b", Some(0.5), 0.5),
            _ => (Some("a"), "b", Some(0.5), 0.5),
        };
        let old = triple(conn, "A", "old", true);
        conn.execute(
            "UPDATE facts SET valid_from=?,confidence=? WHERE id=?",
            params![old_time, old_conf, old],
        )
        .unwrap();
        if mode == "entity" {
            conn.execute(
                "UPDATE facts SET object_entity_id=subject_entity_id WHERE id=?",
                [old],
            )
            .unwrap();
        }
        if mode == "inactive" {
            conn.execute("UPDATE facts SET status='rejected' WHERE id=?", [old])
                .unwrap();
        }
        if mode == "second" {
            // The new fact loses to the first row; the scan must stop before the second.
            let extra = triple(conn, "A", "older", true);
            conn.execute("UPDATE facts SET valid_from='a' WHERE id=?", [extra])
                .unwrap();
        }
        let body = if mode == "equal" { "old" } else { "new" };
        let mut t = d::Triple::new("A", "use", body);
        t.source_content_id = Some(1);
        t.is_list_member = mode == "list";
        let new = d::insert_triple(conn, &t, "ephemeral", clock).unwrap();
        conn.execute(
            "UPDATE facts SET valid_from=?,confidence=? WHERE id=?",
            params![new_time, new_conf, new],
        )
        .unwrap();
        steps.push(state(conn, false));
        for _ in 0..2 {
            let result = d::supersede_existing(
                conn,
                &d::Supersede {
                    subject_id: 1,
                    predicate: " Uses ",
                    new_object: body,
                    new_confidence: new_conf,
                    new_valid_from: new_time,
                    new_fact_id: new,
                    current_content_id: (mode == "batch").then_some(1),
                },
                clock,
            )
            .unwrap();
            steps.push(json!([result, state(conn, false)]));
        }
    } else if name.starts_with("audit.") {
        let id = triple(conn, "A", "old", false);
        commit(conn);
        steps.push(state(conn, false));
        for attempt in 0..2 {
            let new = triple(conn, "A", "new", false);
            conn.execute("UPDATE facts SET status='superseded' WHERE id=?", [id])
                .unwrap();
            if name == "audit.failure_replay" && attempt == 0 {
                conn.execute_batch(
                    "CREATE TEMP TRIGGER fail_audit BEFORE INSERT ON audit_log
                    BEGIN SELECT RAISE(FAIL,'injected audit failure'); END",
                )
                .unwrap();
            }
            d::audit_supersede(conn, id, "A", "use", clock);
            conn.execute_batch("DROP TRIGGER IF EXISTS fail_audit")
                .unwrap();
            steps.push(json!([new, null, state(conn, false)]));
            commit(conn);
            steps.push(reader(root, false));
        }
    } else if name == "links.sequence" {
        let subject = d::upsert_entity(conn, "adr-self", None).unwrap();
        d::upsert_entity(conn, "adr-empty", None).unwrap();
        for slug in ["adr-self", "adr-target"] {
            triple(conn, slug, "first", false);
            triple(conn, slug, "latest", false);
        }
        for raw in [
            "docs/x/adr-missing.md",
            "docs/x/adr-empty.md",
            "docs/x/adr-self.md",
            "docs/x/adr-target.md docs/x/adr-target.md",
            "docs/x/adr-target.md",
        ] {
            steps.push(json!([
                d::link_cross_refs(conn, raw, subject).unwrap(),
                state(conn, false)
            ]));
        }
    } else if name.starts_with("cli.") {
        let cwd = root.join("cwd");
        std::fs::create_dir_all(&cwd).unwrap();
        let db = root.join(if name == "cli.local" {
            "cwd/synthetic.db"
        } else {
            "other/synthetic.db"
        });
        assert_eq!(db.starts_with(&cwd), name == "cli.local");
        let mut stdout = String::new();
        let mut stderr = String::new();
        for _ in 0..2 {
            let (code, out, err) = cli::main_with_clock(
                &[
                    "insert",
                    "--db",
                    db.to_str().unwrap(),
                    "--subject",
                    "A",
                    "--predicate",
                    "uses",
                    "--object",
                    "<private>x</private><secret>s</secret>",
                    "--consent",
                    "persistent",
                ],
                &db,
                &cwd,
                clock,
            )
            .unwrap();
            stdout.push_str(std::str::from_utf8(&out).unwrap());
            stderr.push_str(std::str::from_utf8(&err).unwrap());
            steps.push(json!([{"value":code},state(conn,false)]));
        }
        return json!({"steps":steps,"stdout":stdout,"stderr":stderr,"schema":schema(conn)});
    } else {
        panic!("unhandled {name}");
    }
    json!(steps)
}
fn fm(text: &str) -> String {
    format!("---\n{text}\n---\nbody\n")
}
struct Ingest<'a> {
    conn: &'a Connection,
    root: &'a Path,
    path: std::path::PathBuf,
    steps: Vec<Value>,
}
impl Ingest<'_> {
    fn run(&mut self, body: Option<&str>, globs: &[&str], fail: &str, outer: bool) {
        if let Some(body) = body {
            std::fs::write(&self.path, body).unwrap();
        }
        if outer {
            self.conn.execute_batch("BEGIN").unwrap();
        }
        let result =
            d::ingest_with_observer(&self.path, self.conn, self.root, globs, clock, |phase| {
                if phase == fail {
                    Err(d::WriteError::Injected(if phase == "content" {
                        "after content"
                    } else {
                        "after fact"
                    }))
                } else {
                    Ok(())
                }
            });
        self.steps.push(json!([
            observe(result),
            state(self.conn, true),
            reader(self.root, true)
        ]));
        if outer {
            commit(self.conn);
        }
    }
    fn ingest(&mut self, body: Option<&str>) {
        self.run(body, d::DEFAULT_WHITELIST, "", false);
    }
}
fn replay_ingest(name: &str, conn: &Connection, root: &Path) -> Value {
    if name == "schema" {
        return schema(conn);
    }
    if name == "paths.missing_via_link" {
        let real = root.join("real");
        std::fs::create_dir_all(real.join("docs/decisions")).unwrap();
        #[cfg(unix)]
        std::os::unix::fs::symlink(&real, root.join("link")).unwrap();
        #[cfg(windows)]
        std::os::windows::fs::symlink_dir(&real, root.join("link")).unwrap();
        let path = root.join("link/docs/decisions/adr-gone.md");
        let result = d::ingest_markdown_file(&path, conn, &real, d::DEFAULT_WHITELIST, clock);
        return serde_json::to_value(result.unwrap()).unwrap();
    }
    if name == "roots.dedup" {
        let declared = "memory_relations: [[REQ-1, depends_on, CAP-A]]";
        let mut out = Vec::new();
        for (dir, body) in [
            ("a", declared),
            ("a", declared),
            ("b", declared),
            ("c", "title: same"),
            ("d", "title: same"),
        ] {
            let project = root.join(dir);
            let path = project.join("docs/decisions/adr-main.md");
            std::fs::create_dir_all(path.parent().unwrap()).unwrap();
            std::fs::write(&path, format!("---\n{body}\n---\n")).unwrap();
            let result =
                d::ingest_markdown_file(&path, conn, &project, d::DEFAULT_WHITELIST, clock);
            out.push(json!([dir, result.unwrap()]));
        }
        return json!(out);
    }
    let path = root.join("docs/decisions/adr-main.md");
    std::fs::create_dir_all(path.parent().unwrap()).unwrap();
    let mut s = Ingest {
        conn,
        root,
        path,
        steps: vec![],
    };
    if let Some(mode) = name.strip_prefix("paths.") {
        s.path = root.join(match mode {
            "0" => "notes.md",
            "1" => "docs/_archive/adr-main.md",
            "2" => "docs/_archive/nested/adr-main.md",
            _ => panic!("{mode}"),
        });
        std::fs::create_dir_all(s.path.parent().unwrap()).unwrap();
        let globs = if mode == "0" {
            d::DEFAULT_WHITELIST
        } else {
            &["**"]
        };
        s.run(Some(&fm("title: first")), globs, "", false);
        s.run(Some(&fm("title: changed")), globs, "", false);
    } else if let Some(mode) = name.strip_prefix("frontmatter.") {
        let bodies = [
            "",
            "no frontmatter",
            "---\n---\n",
            "---\nbroken\n",
            "---\n: bad\nignore\nblank:\n---\n",
            "---\nprivate: <PRIVATE>p</PRIVATE><SECRET>s</SECRET><noindex>n</noindex>\n---\n",
            "\u{feff}---\ntitle: bom\n---\n",
            "---\nmemory_relations: [[REQ-1, illegal, CAP-A]]\n---\n",
            "---\ntitle: caf\u{e9} \u{2603}\n---\n",
        ];
        s.ingest(Some(bodies[mode.parse::<usize>().unwrap()]));
        s.ingest(None);
    } else if name == "sequence" {
        s.ingest(Some(&fm(
            "type: decision\nkeywords: [a, b]\nuse: old\nstatus: accepted",
        )));
        s.ingest(None);
        s.ingest(Some(&fm(
            "type: changed\nkeywords:\n  - b\n  - c\nuse: new\nstatus: superseded",
        )));
        s.ingest(None);
    } else if let Some(mode) = name.strip_prefix("winners.") {
        s.ingest(Some(&fm("use: old")));
        let (time, confidence) = match mode {
            "r1_new" => ("2000", 1.0),
            "r1_old" => ("2002", 0.0),
            "r2_new" => (CLOCK, 0.2),
            "r2_old" => (CLOCK, 2.0),
            "tie" => (CLOCK, 1.0),
            _ => panic!("{mode}"),
        };
        conn.execute_batch("BEGIN").unwrap();
        conn.execute(
            "UPDATE facts SET valid_from=?,confidence=?",
            params![time, confidence],
        )
        .unwrap();
        commit(conn);
        s.ingest(Some(&fm("uses: new")));
        s.ingest(None);
    } else if name == "relations" {
        std::fs::create_dir(root.join("tests")).unwrap();
        std::fs::write(root.join("tests/check.py"), "# fixture\n").unwrap();
        for (status, edge) in [
            ("accepted", "CAP-A"),
            ("accepted", "CAP-B"),
            ("proposed", "CAP-B"),
            ("archived", "CAP-B"),
            ("accepted", "CAP-B"),
        ] {
            s.ingest(Some(&fm(&format!(
                "status: {status}\nmemory_relations:\n\
                \x20 - [REQ-1, realized_by, {edge}]\n\
                \x20 - [REQ-1, verified_by, tests/check.py]"
            ))));
            s.ingest(None);
        }
        s.ingest(Some(&fm("title: removed")));
        s.ingest(Some(&fm("memory_relations: [[REQ-1, depends_on, CAP-A]]")));
        s.ingest(Some("plain body\n"));
        s.ingest(None);
    } else if name == "links" {
        let target = s.path.with_file_name("adr-target.md");
        std::fs::write(&target, fm("title: target")).unwrap();
        s.steps.push(json!(
            d::ingest_markdown_file(&target, conn, root, d::DEFAULT_WHITELIST, clock).unwrap()
        ));
        s.ingest(Some(
            &(fm("title: source")
                + "docs/decisions/adr-target.md docs/decisions/adr-target.md\n\
             docs/decisions/adr-main.md docs/decisions/adr-missing.md\n"),
        ));
        s.ingest(None);
    } else if let Some(mode) = name.strip_prefix("failure.") {
        s.ingest(Some(&fm("use: old")));
        s.run(Some(&fm("use: new")), d::DEFAULT_WHITELIST, mode, false);
        s.run(None, d::DEFAULT_WHITELIST, mode, true);
        s.ingest(None);
        s.ingest(None);
    } else if let Some(mode) = name.strip_prefix("cli.") {
        if mode == "override" {
            s.path = root.join("notes.md");
        }
        std::fs::write(
            &s.path,
            if mode == "invalid" {
                fm("memory_relations: broken")
            } else {
                fm("title: <private>p</private><secret>s</secret><noindex>n</noindex>")
            },
        )
        .unwrap();
        let db = root.join("synthetic.db");
        let mut stdout = String::new();
        let mut stderr = String::new();
        for _ in 0..2 {
            let mut args = vec![
                "ingest-md",
                s.path.to_str().unwrap(),
                "--db",
                db.to_str().unwrap(),
            ];
            if mode == "override" {
                args.extend(["--whitelist", "*.md"]);
            }
            let (code, out, err) = cli::main_with_clock(&args, &db, root, clock).unwrap();
            stdout.push_str(std::str::from_utf8(&out).unwrap());
            stderr.push_str(std::str::from_utf8(&err).unwrap());
            s.steps.push(json!([{"value":code},state(conn,true)]));
        }
        s.steps.push(json!({"stdout":stdout,"stderr":stderr}));
    } else {
        panic!("unhandled {name}");
    }
    json!(s.steps)
}
fn normalize(value: Value, root: &Path) -> Value {
    // Match the oracle's in-case path substitution, including JSON string fields.
    fn walk(v: Value, root: &str) -> Value {
        match v {
            Value::String(s) => json!(s.replace(root, "<tmp>")),
            Value::Array(a) => json!(a.into_iter().map(|v| walk(v, root)).collect::<Vec<_>>()),
            Value::Object(m) => {
                Value::Object(m.into_iter().map(|(k, v)| (k, walk(v, root))).collect())
            }
            v => v,
        }
    }
    walk(value, root.to_str().unwrap())
}
#[test]
fn frozen_records() {
    for (ingest, fixture, total) in [
        (true, include_str!("fixtures/w2/b11-ingest.json"), 28),
        (false, include_str!("fixtures/w2/b11-insert.json"), 24),
    ] {
        let oracle: Value = serde_json::from_str(fixture).unwrap();
        assert_eq!(oracle.as_object().unwrap().len(), total);
        let mut replayed = 0;
        for (name, expected) in oracle.as_object().unwrap() {
            let temp = tempfile::Builder::new().prefix("b11-").tempdir().unwrap();
            let root = temp.path().canonicalize().unwrap();
            let relative = match (ingest, name.as_str()) {
                (false, "cli.local") => "cwd/synthetic.db",
                (false, "cli.foreign") => "other/synthetic.db",
                _ => "synthetic.db",
            };
            let db = store::connect(&root.join(relative), None).unwrap();
            store::apply_migrations(&db.conn).unwrap();
            // Migration clock was frozen in Python; seed only the migration timestamps.
            db.conn
                .execute("UPDATE schema_migrations SET applied_at=?", [CLOCK])
                .unwrap();
            let value = if ingest {
                replay_ingest(name, &db.conn, &root)
            } else {
                compact(replay_insert(name, &db.conn, &root))
            };
            let actual = normalize(json!({"value":value}), &root);
            assert_eq!(
                &actual,
                expected,
                "{}:{name}",
                if ingest { "ingest" } else { "insert" }
            );
            replayed += 1;
            println!(
                "{}:{name}: replayed",
                if ingest { "ingest" } else { "insert" }
            );
        }
        assert_eq!(replayed, total);
        println!("replayed={replayed} exempt=0 total={total}");
    }
}
