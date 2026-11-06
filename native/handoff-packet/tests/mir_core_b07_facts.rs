#[path = "../src/digest.rs"]
mod digest;
use handoff_packet::mir_core::{
    audit_log::AuditLog,
    memory::{relation_facts as f, store},
    yaml,
};
use rusqlite::{Connection, params, types::ValueRef};
use serde_json::{Value, json};
use std::{
    path::Path,
    time::{Duration, SystemTime, UNIX_EPOCH},
};
fn raw() -> Vec<String> {
    vec![
        "".into(),
        "---".into(),
        " ---\n---\n".into(),
        "---\nx: y".into(),
        "---\n---\n".into(),
        "---\r\nstatus: Active\r\n---\r\n".into(),
        "---\nstatus: \" Draft \"\n---\nbody\n".into(),
        "---\nstatus: ACTIVE\nstatus: draft\n---\nbody\n".into(),
        "---\nx: memory_relations\n---\nbody\n".into(),
        "---\n- memory_relations\n---\nbody\n".into(),
        "---\nmemory_relations: []\n---\nbody\n".into(),
        "---\nmemory_relations: null\n---\nbody\n".into(),
        "---\nmemory_relations: []\nmemory_relations: []\n---\nbody\n".into(),
        "---\nmemory_relations: []\nstatus: A\nstatus: B\n---\nbody\n".into(),
        "---\nmemory_relations: []\nstatus: 1\n---\nbody\n".into(),
        "---\nmemory_relations: [\n---\nbody\n".into(),
        "---\n\"memory_relations\": []\n? [complex, key]\n: ignored\n---\nbody\n".into(),
        "---\nmemory_relations: []\nstatus: \" ACTIVE \"\n---\nbody\n".into(),
    ]
}
const STATUSES: &[&str] = &[
    "",
    "active",
    " ACTIVE ",
    "inactive",
    "candidate",
    "draft",
    "proposed",
    "archived",
    "rejected",
    "superseded",
    "superseded-design",
    "historical",
    "historical-snapshot",
    "historical-manual-snapshot",
    "historical-ledger",
    "applied-ledger-v1",
    "done",
    "historical-new",
    "superseded-new",
    "done-new",
];
const EDGES: &[&str] = &[
    "[A, depends_on, B]",
    "[A, realized_by, B]",
    "[A, implemented_in, src/a.py::f]",
    "[A, verified_by, tests/a.py]",
    "[ns:A, depends_on, ns:B]",
    "[A, alias, B]",
    "[A, same_as, B]",
    "[A, inverse_depends_on, B]",
    "[A, ns:depends_on, B]",
    "[A, DEPENDS_ON, B]",
    "[A, depends_on, A]",
    "[A, depends_on, \".env\"]",
    "[A, depends_on, \"/absolute\"]",
    "[A, depends_on, \"src/../a.py\"]",
    "[A, depends_on, \"a\\tb\"]",
    "[A, depends_on]",
    "[A, depends_on, B, C]",
    "scalar",
    "null",
    "[1, depends_on, B]",
    "[A, true, B]",
    "[A, depends_on, null]",
    "[\"\", depends_on, B]",
    "[A, depends_on, \"../escape\"]",
    "[\"./src/a.py::f\", depends_on, \"src//a.py::g\"]",
    "{subject: A, predicate: depends_on, object: B, summary: why, reason: because}",
    "{subject: A, predicate: depends_on, object: B}",
    "{subject: A}",
    "{subject: A, subject: B, predicate: depends_on, object: C}",
    "{subject: A, predicate: depends_on, object: B, unknown: x}",
    "{1: A}",
    "{? [x, y]: z}",
    "{subject: A, predicate: depends_on, object: B, summary: null}",
    "{subject: A, predicate: depends_on, object: B, reason: \"\"}",
];
fn doc(s: &str) -> String {
    format!("---\n{s}\n---\nbody\n")
}
fn observed<T: serde::Serialize>(v: f::Result<T>) -> Value {
    match v {
        Ok(v) => json!({"value":v}),
        Err(e) => json!({"error":["RelationDeclarationError",e.0]}),
    }
}
fn batch<T>(values: impl IntoIterator<Item = T>, mut call: impl FnMut(T) -> Value) -> Value {
    json!({"value":values.into_iter().map(&mut call).collect::<Vec<_>>()})
}
fn parse(s: &str) -> Value {
    observed(f::parse_relation_document(s))
}
fn declaration(a: &str, p: &str, b: &str, quote: &str) -> f::RelationDeclaration {
    f::RelationDeclaration {
        subject: a.into(),
        predicate: p.into(),
        object: b.into(),
        quote: quote.into(),
        summary: None,
        reason: None,
        source_line: None,
    }
}
fn pure(name: &str, root: &Path) -> Value {
    match name {
        "frontmatter" => batch(
            raw().into_iter().chain(["---\nstatus: A\n --- \n".into()]),
            |s| json!({"value":f::frontmatter(&s)}),
        ),
        "key" => batch(
            [
                "memory_relations",
                "\"memory_relations\"",
                "'memory_relations'",
                "!!str memory_relations",
                "memory_relation",
                "MEMORY_RELATIONS",
                "\"memory_\\u0072elations\"",
                "[memory_relations]",
                "*missing",
                "x: y\nmemory_relations",
                "",
            ],
            |s| json!({"value":f::is_relation_declaration_key(s)}),
        ),
        "declares" => batch(
            [
                "memory_relations: []",
                "\"memory_relations\": [",
                "x: [",
                "[memory_relations]",
                "",
                "  memory_relations: [",
                "# memory_relations: [",
                "x: memory_relations",
            ],
            |s| json!({"value":f::frontmatter_declares_relations(s,None)}),
        ),
        "declares_cap" => batch(
            [None, Some(0), Some(3), Some(4), Some(5)],
            |n| json!({"value":f::frontmatter_declares_relations("x: y",n)}),
        ),
        "has" => batch(
            raw(),
            |s| json!({"value":f::has_relation_declaration(&s,None)}),
        ),
        "has_cap" => batch(
            [0, 4, 5],
            |n| json!({"value":f::has_relation_declaration(&doc("x: y"),Some(n))}),
        ),
        "node" | "note" => {
            let mut inputs: Vec<String> = if name == "node" {
                [
                    "null",
                    "1",
                    "[]",
                    "{}",
                    "\"\"",
                    "\" \"",
                    "A",
                    "\"\\t\"",
                    "\"\\u007f\"",
                    "\"\\u009f\"",
                    "\"\\u00a0\"",
                    "\"\\u2028\"",
                ]
            } else {
                [
                    "null",
                    "[]",
                    "\"\"",
                    "\" \"",
                    "ok",
                    "\"a\\nb\"",
                    "\"a\\rb\"",
                    "\"\\t\"",
                    "\"\\u0080\"",
                    "\"\\u2029\"",
                    "",
                    "",
                ]
            }
            .into_iter()
            .filter(|s| !s.is_empty())
            .map(str::to_owned)
            .collect();
            for n in if name == "node" {
                [1024, 1025]
            } else {
                [240, 241]
            } {
                inputs.push(format!("\"{}\"", "a".repeat(n)));
            }
            batch(inputs, |s| {
                let node = yaml::compose(yaml::Input::Text(&s)).unwrap().unwrap();
                observed(if name == "node" {
                    f::node_string
                } else {
                    f::note_string
                }(&node.arena[node.root], "field"))
            })
        }
        "parse_frontmatter" => batch(raw(), |s| parse(&s)),
        "parse_edges" => batch(EDGES, |s| {
            parse(&doc(&format!("memory_relations:\n  - {s}")))
        }),
        "parse_nested" => batch(
            [
                "memory_relations: &loop [*loop]",
                "memory_relations:\n - [A, depends_on, B]\nstatus: []",
                "memory_relations:\n - [A, depends_on, B]\n - [B, depends_on, C]",
            ],
            |s| parse(&doc(s)),
        ),
        "parse_order_duplicate" => batch(
            [
                " - [B, depends_on, A]\n - [A, depends_on, B]",
                " - [A, depends_on, B]\n - [A, depends_on, B]",
                " - [A, depends_on, B]\n - {subject: A, predicate: depends_on, object: B}",
            ],
            |s| parse(&doc(&format!("memory_relations:\n{s}"))),
        ),
        "parse_count" => batch([0, 64, 65], |n| {
            parse(&doc(&format!(
                "memory_relations:\n{}",
                (0..n)
                    .map(|i| format!(" - [A{i}, depends_on, B]"))
                    .collect::<Vec<_>>()
                    .join("\n")
            )))
        }),
        "parse_quote" => batch([4072, 4073, 4074, 4096], |n| {
            parse(&doc(&format!(
                "memory_relations:\n - [A, depends_on, B] #{}",
                "x".repeat(n)
            )))
        }),
        "parse_multiline_quote" => batch(
            [
                concat!(
                    "memory_relations:\n - subject: A\n   predicate: depends_on\n   object: B\n",
                    " # trailing comment\n\nstatus: active"
                ),
                "memory_relations:\n - [A,\n    depends_on,\n    B]  # tail\n - [B, depends_on, C]",
                "memory_relations:\n -\n   - A\n   - depends_on\n   - B\n# c\n",
                concat!(
                    "memory_relations:\n - {subject: A,\n    predicate: depends_on, object: B}\n",
                    "\n # gap\nstatus: active"
                ),
            ],
            |s| parse(&doc(s)),
        ),
        "parse_size" => batch([1048575, 1048576, 1048577], |n| {
            parse(&doc(&format!("#{}", "x".repeat(n - 2))))
        }),
        "status" => batch(
            ["verified_by", "depends_on", "unknown"]
                .into_iter()
                .flat_map(|p| STATUSES.iter().map(move |s| (p, *s))),
            |(p, s)| json!({"value":f::relation_status_is_active(p,s)}),
        ),
        "metadata" => json!({"value":([("docs/note.md"," ACTIVE "),("../raw","historical"),("","")]
            .map(|(p,s)| f::relation_metadata(p,root,s).unwrap()))}),
        "sources" => {
            std::fs::write(root.join("note.md"), "synthetic").unwrap();
            batch(
                ["note.md", "./note.md", "missing", "../missing", ".env", "."],
                |p| observed(f::safe_source_relative_path(&root.join(p), root)),
            )
        }
        "root_validation" => {
            std::fs::create_dir(root.join("src")).unwrap();
            std::fs::write(root.join("src/unit.py"), "pass\n").unwrap();
            std::fs::create_dir(root.join("directory")).unwrap();
            let mut v = vec![];
            for (a, p, b) in [
                ("A", "depends_on", "B"),
                ("A", "implemented_in", "src/unit.py::run"),
                ("src/unit.py", "verified_by", "src/unit.py"),
                ("A", "implemented_in", "missing"),
                ("A", "depends_on", "../escape"),
                (".env", "depends_on", "B"),
                ("A", "verified_by", ".env"),
                ("A", "implemented_in", "directory"),
            ] {
                v.push(observed(f::validate_declarations_for_root(
                    &[declaration(a, p, b, "proof")],
                    root,
                )));
            }
            std::fs::create_dir(root.join(".mir")).unwrap();
            std::fs::write(root.join(".mir/repo-profile.toml"), "invalid = [").unwrap();
            v.push(observed(f::validate_declarations_for_root(&[], root)));
            json!({"value":v})
        }
        "now_format" => {
            let now = handoff_packet::mir_core::audit_log::now_iso(clock()).unwrap();
            json!({"value":{"utc":0.0,"microseconds":
                now.split('.').nth(1).unwrap().split('+').next().unwrap().len()}})
        }
        _ => panic!("unclassified pure record {name}"),
    }
}
fn clock() -> SystemTime {
    UNIX_EPOCH + Duration::from_secs(981173106)
}
fn rows(conn: &Connection, sql: &str) -> Value {
    let mut stmt = conn.prepare(sql).unwrap();
    let count = stmt.column_count();
    json!(
        stmt.query_map([], |row| Ok((0..count)
            .map(|i| match row.get_ref(i).unwrap() {
                ValueRef::Null => Value::Null,
                ValueRef::Integer(n) => json!(n),
                ValueRef::Real(n) => json!(n),
                ValueRef::Text(s) => json!(std::str::from_utf8(s).unwrap()),
                ValueRef::Blob(_) => panic!("unexpected blob"),
            })
            .collect::<Vec<_>>()))
            .unwrap()
            .map(Result::unwrap)
            .collect::<Vec<_>>()
    )
}
fn state(conn: &Connection) -> Value {
    let mut v = json!({});
    for table in ["facts", "entities", "provenance", "audit_log"] {
        v[table] = rows(conn, &format!("SELECT * FROM {table} ORDER BY rowid"));
    }
    v
}
fn decls() -> Vec<f::RelationDeclaration> {
    [
        ("A", "depends_on", "B"),
        ("A", "depends_on", "C"),
        ("B", "implemented_in", "src/a.py::z"),
        ("C", "implemented_in", "src/a.py::a"),
    ]
    .map(|(a, p, b)| declaration(a, p, b, "proof"))
    .to_vec()
}
fn reconcile(
    conn: &Connection,
    root: &Path,
    source: &str,
    cid: Option<i64>,
    status: &str,
    declarations: &[f::RelationDeclaration],
) -> Value {
    json!(
        f::reconcile_relation_facts(
            conn,
            &f::Reconcile {
                declarations,
                content_item_id: cid,
                project_root: root,
                source_path: source,
                document_status: status
            },
            clock
        )
        .unwrap()
    )
}
const OWNED: &[Option<&str>] = &[
    None,
    Some("UPDATE facts SET status='superseded' WHERE created_from=1"),
    Some("UPDATE facts SET object_literal='literal' WHERE created_from=1"),
    Some("UPDATE facts SET object_entity_id=NULL WHERE created_from=1"),
    Some("UPDATE facts SET scope='global' WHERE created_from=1"),
    Some("UPDATE facts SET project_path='other' WHERE created_from=1"),
    Some("UPDATE content_items SET source='other' WHERE id=1"),
    Some("UPDATE content_items SET metadata_json='{}' WHERE id=1"),
    Some(
        "UPDATE content_items SET metadata_json=json_set(metadata_json, \
            '$.relation_schema', 'other') WHERE id=1",
    ),
    Some(
        "UPDATE content_items SET metadata_json=json_set(metadata_json, \
            '$.relation_project_path', 'other') WHERE id=1",
    ),
    Some(
        "UPDATE content_items SET metadata_json=json_set(metadata_json, \
            '$.path', 'other') WHERE id=1",
    ),
];
fn db(name: &str, root: &Path) -> Value {
    let conn = Connection::open(root.join("synthetic.db")).unwrap();
    conn.execute_batch("PRAGMA foreign_keys=OFF").unwrap();
    store::apply_migrations(&conn).unwrap();
    for (cid, path) in [(1, "a.md"), (2, "b.md")] {
        // Python json.dumps preserves insertion order and spaces here.
        let m = f::relation_metadata(path, root, "active").unwrap();
        let metadata = format!(
            "{{\"path\": {}, \"relation_schema\": {}, \"relation_project_path\": {}, \
            \"relation_document_status\": {}}}",
            m["path"],
            m["relation_schema"],
            m["relation_project_path"],
            m["relation_document_status"]
        );
        conn.execute(
            "INSERT INTO content_items(id,source,text_hash,metadata_json)
            VALUES (?,'self_ingest_md','hash',?)",
            params![cid, metadata],
        )
        .unwrap();
    }
    if name == "schema" {
        let mut pragmas = json!({});
        for p in ["journal_mode", "foreign_keys", "synchronous"] {
            pragmas[p] = rows(&conn, &format!("PRAGMA {p}"))[0][0].clone();
        }
        return json!({"value":{"pragmas":pragmas,
            "migrations":rows(&conn,"SELECT version,name FROM schema_migrations ORDER BY version"),
            "schema":rows(&conn,
                "SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name")}});
    }
    if name == "upsert" {
        let ids: Vec<_> = ["A", "A", "", "a", "ns:A"]
            .map(|s| f::upsert_entity(&conn, s).unwrap())
            .into();
        return json!({"value":[ids,state(&conn)]});
    }
    let declarations = decls();
    let first = reconcile(&conn, root, "a.md", Some(1), "active", &declarations);
    let other = reconcile(&conn, root, "b.md", Some(2), "active", &declarations[..1]);
    conn.execute_batch("COMMIT").unwrap();
    if let Some(mode) = name.strip_prefix("lifecycle.") {
        let before = state(&conn);
        let changed = match mode {
            "change" => reconcile(
                &conn,
                root,
                "a.md",
                Some(1),
                "active",
                &[declaration("A", "depends_on", "D", "changed")],
            ),
            "remove" => reconcile(&conn, root, "a.md", None, "active", &declarations),
            _ => reconcile(
                &conn,
                root,
                "a.md",
                Some(1),
                if mode == "replay" { "active" } else { mode },
                &declarations,
            ),
        };
        let owned = f::owned_active_rows(&conn, root.to_str().unwrap(), "a.md").unwrap();
        return json!({"value":[first,other,before,changed,owned,state(&conn)]});
    }
    if let Some(mode) = name.strip_prefix("owned.") {
        if let Some(sql) = OWNED[mode.parse::<usize>().unwrap()] {
            conn.execute(sql, []).unwrap();
        }
        let owned = f::owned_active_rows(&conn, root.to_str().unwrap(), "a.md").unwrap();
        let checks: Vec<_> = [
            (root.to_path_buf(), "a.md"),
            (root.to_path_buf(), "b.md"),
            (root.to_path_buf(), "missing"),
            (root.join("other"), "a.md"),
        ]
        .map(|(r, s)| f::has_owned_active_relation_facts(&conn, &r, s).unwrap())
        .into();
        return json!({"value":[owned,checks]});
    }
    if let Some(mode) = name.strip_prefix("rollback.") {
        let fail_at = mode.parse::<usize>().unwrap();
        let before = state(&conn);
        let audit = AuditLog::with_clock(&conn, clock);
        let mut calls = vec![];
        let mut new = vec![declaration("D", "depends_on", "E", "new")];
        new.extend(declarations);
        let failure = f::reconcile_with_audit(
            &conn,
            &f::Reconcile {
                declarations: &new,
                content_item_id: Some(1),
                project_root: root,
                source_path: "a.md",
                document_status: "active",
            },
            clock,
            |event, payload| {
                calls.push(event.to_owned());
                if calls.len() == fail_at {
                    return Err(store::Error::Snapshot("injected audit failure"));
                }
                audit.audit_append(event, payload, false).map(|_| ())
            },
        );
        assert!(failure.is_err());
        let failure = json!({"error":["RuntimeError","injected audit failure"]});
        let partial = state(&conn);
        conn.execute_batch("ROLLBACK").unwrap();
        return json!({"value":[before,failure,calls,partial,state(&conn),!conn.is_autocommit()]});
    }
    panic!("unclassified db record {name}")
}
fn compact(v: Value) -> Value {
    match v {
        Value::String(s) if s.chars().count() > 256 => json!({"len":s.chars().count(),
            "sha256":digest::sha256(s.as_bytes())}),
        Value::Array(a) => Value::Array(a.into_iter().map(compact).collect()),
        Value::Object(m) => Value::Object(m.into_iter().map(|(k, v)| (k, compact(v))).collect()),
        _ => v,
    }
}
const PURE_DEFERRED: &[&str] = &[
    "metadata_gate",
    "entity",
    "coalesce",
    "proof_notices",
    "inactive_sql",
    "locator_sql",
    "source_marker",
    "search_hint",
    "stamp",
    "directions",
];
const DB_DEFERRED: &[&str] = &[
    "empty",
    "provenance",
    "locator.0",
    "locator.1",
    "locator.2",
    "locator.3",
    "query.0",
    "query.1",
    "query.2",
    "query.3",
    "query.4",
    "query.5",
    "query.6",
    "query.7",
    "query.8",
    "query.9",
    "query.10",
    "query.11",
    "query.12",
    "query.13",
    "query.14",
    "query.15",
    "query.16",
    "query.17",
    "query.18",
    "query.19",
    "query.20",
    "query.21",
    "query.22",
    "query.23",
    "query.24",
];
#[test]
fn frozen_records() {
    for (fixture, deferred, expected, is_db) in [
        (
            include_str!("fixtures/w2/b07-relations-pure.json"),
            PURE_DEFERRED,
            [21, 10, 0],
            false,
        ),
        (
            include_str!("fixtures/w2/b07-relations-db.json"),
            DB_DEFERRED,
            [23, 31, 0],
            true,
        ),
    ] {
        let oracle: Value = serde_json::from_str(fixture).unwrap();
        assert_eq!(deferred.len(), expected[1]);
        assert!(deferred.iter().all(|name| oracle.get(*name).is_some()));
        let mut counts = [0, 0, 0];
        for (name, expected) in oracle.as_object().unwrap() {
            if deferred.contains(&name.as_str()) {
                // Every named record above is deferred whole: memory_relations: B07-P02.
                eprintln!("DEFERRED {name}: memory_relations: B07-P02");
                counts[1] += 1;
                continue;
            }
            let temp = tempfile::tempdir().unwrap();
            let root = temp.path().canonicalize().unwrap();
            let actual = if is_db {
                db(name, &root)
            } else {
                pure(name, &root)
            };
            let actual: Value =
                serde_json::from_str(&serde_json::to_string(&actual).unwrap().replace(
                    &serde_json::to_string(root.to_str().unwrap()).unwrap()
                        [1..serde_json::to_string(root.to_str().unwrap()).unwrap().len() - 1],
                    "<tmp>",
                ))
                .unwrap();
            assert_eq!(
                if is_db { compact(actual) } else { actual },
                *expected,
                "{name}"
            );
            counts[0] += 1;
        }
        assert_eq!(counts, expected);
    }
}
#[test]
fn non_string_key_and_external_source_witnesses() {
    let raw = doc("memory_relations:\n - {!!int subject: A, predicate: depends_on, object: B}");
    assert_eq!(
        parse(&raw),
        json!({"error":["RelationDeclarationError",
        "invalid memory_relations: relation mapping key must be a string"]})
    );
    let temp = tempfile::tempdir().unwrap();
    let root = temp.path().join("root");
    std::fs::create_dir(&root).unwrap();
    let outside = temp.path().join("outside.md");
    std::fs::write(&outside, "synthetic").unwrap();
    assert_eq!(
        observed(f::safe_source_relative_path(&outside, &root)),
        json!({
        "error":["RelationDeclarationError","invalid memory_relations: unsafe source path"]})
    );
}

#[test]
fn metadata_resolves_relative_and_missing_parent_paths() {
    let cwd = std::env::current_dir().unwrap().canonicalize().unwrap();
    assert_eq!(
        f::relation_metadata("", Path::new("."), "").unwrap()["relation_project_path"],
        cwd.to_str().unwrap()
    );
    let temp = tempfile::tempdir().unwrap();
    let root = temp.path().canonicalize().unwrap();
    let metadata = f::relation_metadata("", &root.join("missing/../other"), "").unwrap();
    assert_eq!(
        metadata["relation_project_path"],
        root.join("other").to_str().unwrap()
    );
}
