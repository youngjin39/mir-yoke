#[path = "../src/digest.rs"]
mod digest;
use handoff_packet::mir_core::{
    audit_log::AuditLog,
    memory::{relation_facts as f, store},
    memory_relations as m, relations as r, yaml,
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
        _ => memory_pure(name),
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
    if name == "empty" {
        let first = reconcile(&conn, root, "a.md", None, "active", &decls());
        return json!({"value":[first,
            f::has_owned_active_relation_facts(&conn,root,"a.md").unwrap(),
            m::relation_rows(&conn,root,&Default::default(),"dependencies",None,None,1).unwrap(),
            state(&conn)]});
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
    memory_db(name, &conn, root)
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
#[test]
fn frozen_records() {
    for (fixture, expected, is_db) in [
        (
            include_str!("fixtures/w2/b07-relations-pure.json"),
            [29, 0, 2],
            false,
        ),
        (
            include_str!("fixtures/w2/b07-relations-db.json"),
            [54, 0, 0],
            true,
        ),
    ] {
        let oracle: Value = serde_json::from_str(fixture).unwrap();
        let mut counts = [0, 0, 0];
        for (name, expected) in oracle.as_object().unwrap() {
            if ["stamp", "coalesce"].contains(&name.as_str()) {
                // Python-only mock stat and invalid Edge constructor argument binding.
                counts[2] += 1;
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
fn memory_pure(name: &str) -> Value {
    match name {
        "entity" => batch(
            [
                Value::Null,
                json!(0),
                json!([]),
                json!(""),
                json!(" "),
                json!("ns:A"),
                json!("a".repeat(4096)),
                json!("a".repeat(4097)),
                json!("\n"),
                json!("\u{1f}"),
                json!("\u{7f}"),
                json!("\u{9f}"),
                json!("\u{a0}"),
                json!("\u{2028}"),
            ],
            |v| json!({"value":m::entity_value(&v)}),
        ),
        "metadata_gate" => {
            let meta = json!({"relation_schema":f::RELATION_SCHEMA,
                "relation_project_path":"project",
                "relation_document_status":"active"});
            let mut inputs = vec![Value::Null, json!([]), json!({})];
            for (k, v) in [
                ("relation_schema", json!("v2")),
                ("relation_project_path", json!("other")),
                ("relation_document_status", Value::Null),
            ] {
                let mut m = meta.clone();
                m[k] = v;
                inputs.push(m);
            }
            for status in STATUSES.iter().copied().chain(["\n", "\u{7f}"]) {
                let mut m = meta.clone();
                m["relation_document_status"] = json!(status);
                inputs.push(m);
            }
            batch(
                inputs,
                |v| json!({"value":m::metadata_gate(Path::new("project"),&v)}),
            )
        }
        "proof_notices" => batch([0, 1, 8], |n| {
            let mut state = m::SelectionState::default();
            state.proofs_omitted = n;
            json!({"value":m::proof_notices(&state)})
        }),
        "inactive_sql" => batch(
            ["f.subject_entity_id", "f.object_entity_id"],
            |s| json!({"value":m::inactive_endpoint_sql(s)}),
        ),
        "locator_sql" => batch(
            ["subject.slug", "object.slug", ""],
            |s| json!({"value":m::locator_path_sql(s)}),
        ),
        "source_marker" => json!({"value":m::memory_source()}),
        "search_hint" => json!({"value":m::search_hint(&["B","A","B"].map(str::to_owned),
            &["impact","dependencies","impact"].map(str::to_owned),"missing")}),
        "directions" => {
            let mut value = json!({});
            for (label, reverse) in [("forward", false), ("reverse", true)] {
                for p in r::PURPOSES {
                    let mut predicates: Vec<_> =
                        "has_req refines realized_by constrains implemented_in \
                        exposes decided_by governed_by verified_by affects blocks depends_on"
                            .split_whitespace()
                            .filter(|v| r::allowed(p, v, reverse))
                            .collect();
                    predicates.sort();
                    value[label][p] = json!(predicates);
                }
            }
            json!({"value":value})
        }
        _ => panic!("unclassified pure record {name}"),
    }
}
fn memory_db(name: &str, conn: &Connection, root: &Path) -> Value {
    if name == "provenance" {
        conn.execute(
            "INSERT INTO provenance VALUES (1,1,'other',NULL,'inferred')",
            [],
        )
        .unwrap();
        return json!({"value":([(1,1,"proof"),(1,2,"proof"),(99,1,"proof"),(1,1,"other"),
            (1,1,""),(1,1,"Proof")].map(|(f,c,q)|m::provenance_is_current(conn,f,c,q).unwrap()))});
    }
    if let Some(n) = name.strip_prefix("locator.") {
        let n = n.parse().unwrap();
        let result: Vec<_> = [
            "src/a.py",
            "./src//a.py",
            "src/a.py::a",
            "src/a.py::z",
            "src/A.py",
            "missing",
            "A",
        ]
        .map(|a| m::locator_nodes(conn, root, a, n).unwrap())
        .into();
        return json!({"value":[result,rows(conn,"SELECT mir_locator_path('src//a.py::a'), \
            mir_normalized_locator('./src/a.py::z')")]});
    }
    let n = name
        .strip_prefix("query.")
        .unwrap()
        .parse::<usize>()
        .unwrap();
    let extra = [
        "UPDATE content_items SET text_hash=printf('%0128d',1) WHERE id=1",
        "UPDATE content_items SET metadata_json=printf('%065536d',1) WHERE id=1",
        "UPDATE entities SET slug=printf('%04096d',1) WHERE slug='B'",
        "UPDATE facts SET polarity='negated' WHERE created_from=1",
        "UPDATE facts SET valid_to='ended' WHERE created_from=1",
        "UPDATE content_items SET text_hash=printf('%0129d',1) WHERE id=1",
        "UPDATE content_items SET metadata_json=printf('%065537d',1) WHERE id=1",
        "UPDATE entities SET slug=printf('%04097d',1) WHERE slug='A'",
    ];
    if n < OWNED.len() {
        if let Some(sql) = OWNED[n] {
            conn.execute(sql, []).unwrap();
        }
    } else if n < 19 {
        conn.execute(extra[n - 11], []).unwrap();
    } else {
        let endpoint = if n < 22 { 1 } else { 2 };
        let status = ["historical-new", "draft", "active"][(n - 19) % 3];
        conn.execute(
            "INSERT INTO facts(subject_entity_id,predicate,object_literal,status,polarity)
            VALUES (?,'status',?,'active','asserted')",
            params![endpoint, status],
        )
        .unwrap();
    }
    let set = |v: &[&str]| v.iter().map(|s| s.to_string()).collect();
    let ids = [1, 5].into_iter().collect();
    let empty = Default::default();
    let excluded = [1].into_iter().collect();
    let mut queries = vec![];
    for purpose in ["dependencies", "impact", "implementation", "verification"] {
        for limit in [-1, 0, 1, 2, 5, 6] {
            for (frontier, ids, exc) in [
                (set(&["A", "B"]), None, None),
                (set(&["A"]), Some(&ids), Some(&excluded)),
                (set(&["A"]), Some(&empty), Some(&excluded)),
                (set(&[]), None, None),
            ] {
                queries.push(json!([
                    purpose,
                    limit,
                    ids,
                    exc,
                    m::relation_rows(conn, root, &frontier, purpose, ids, exc, limit).unwrap()
                ]));
            }
        }
    }
    json!({"value":{"queries":queries,"eligible":(["A","B","missing"].map(|a|
        m::eligible_nodes(conn,root,a).unwrap())),"probe":(["A","B","missing"].map(|a|
        !m::relation_rows(conn,root,&set(&[a]),"dependencies",None,None,1).unwrap().is_empty()))}})
}
