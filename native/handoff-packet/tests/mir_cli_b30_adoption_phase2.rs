//! Replay all frozen Python content, memory, and phase-2 acceptance records.
#![forbid(unsafe_code)]
use handoff_packet::mir_cli::bootstrap_adoption::{self as m, Error, Host};
use rusqlite::Connection;
use serde_json::{Value, json};
use std::{
    cell::RefCell,
    fs, io,
    path::{Path, PathBuf},
    rc::Rc,
};

#[path = "../src/digest.rs"]
mod digest;

const QUERY_SQL: &str = "SELECT a.slug, a.root_path, d.relative_path \
    FROM external_chunks_fts f \
    JOIN external_chunks c ON c.id = f.rowid \
    JOIN external_documents d ON d.id = c.document_id \
    JOIN external_archives a ON a.id = d.archive_id \
    WHERE external_chunks_fts MATCH ? \
    AND a.slug = ? AND d.relative_path = ? LIMIT 1";
const OBJECT_SQL: &str = "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')";
const DDL: &str = "CREATE TABLE external_archives(id INTEGER PRIMARY KEY, slug, root_path);\
    CREATE TABLE external_documents(id INTEGER PRIMARY KEY, archive_id, relative_path);\
    CREATE TABLE external_chunks(id INTEGER PRIMARY KEY, document_id);\
    CREATE VIRTUAL TABLE external_chunks_fts USING fts5(body);";
const REVIEWS: [&str; 5] = [
    "project_structure",
    "memory",
    "discoverability",
    "requirements",
    "organization",
];
type SqlCalls = Rc<RefCell<Vec<(String, Vec<Value>)>>>;
#[derive(Default)]
struct Observer {
    root: PathBuf,
    scan_error: bool,
    denied: bool,
    opens: Vec<(String, bool, bool)>,
    sql: SqlCalls,
}
struct RecordingConnection {
    inner: Box<dyn m::MemoryConnection>,
    calls: SqlCalls,
}
impl m::MemoryConnection for RecordingConnection {
    fn execute(&mut self, sql: &str, params: &[Value]) -> Result<Vec<Vec<Value>>, String> {
        self.calls.borrow_mut().push((sql.into(), params.to_vec()));
        self.inner.execute(sql, params)
    }
}
impl Host for Observer {
    fn read(&mut self, path: &Path) -> io::Result<Vec<u8>> {
        assert!(path.starts_with(&self.root));
        assert!(
            self.root
                .starts_with(std::env::temp_dir().canonicalize().unwrap())
        );
        fs::read(path)
    }
    fn git(&mut self, _: &m::GitRequest) -> io::Result<bool> {
        panic!("phase-2 validators must not invoke git")
    }
    fn scan_content_candidates(&mut self, root: &Path) -> Result<Vec<Value>, String> {
        assert_eq!(root, self.root);
        if self.scan_error {
            Err("scan denied".into())
        } else {
            m::LocalHost.scan_content_candidates(root)
        }
    }
    fn sqlite_open(
        &mut self,
        request: &m::SqliteRequest,
    ) -> Result<Box<dyn m::MemoryConnection>, String> {
        assert_eq!(request.uri, expected_uri(&self.root));
        self.opens
            .push((request.uri.clone(), request.uri_mode, request.read_only));
        if self.denied {
            return Err("denied".into());
        }
        let inner = m::LocalHost.sqlite_open(request)?;
        Ok(Box::new(RecordingConnection {
            inner,
            calls: self.sql.clone(),
        }))
    }
}
fn put(root: &Path, name: &str, bytes: impl AsRef<[u8]>) {
    let path = root.join(name);
    fs::create_dir_all(path.parent().unwrap()).unwrap();
    fs::write(path, bytes).unwrap();
}
fn success(v: impl serde::Serialize) -> Value {
    json!({"value": v})
}
fn outcome<T: serde::Serialize>(result: Result<T, Error>) -> Value {
    match result {
        Ok(v) => success(v),
        Err(e) => json!({"error": [e.class(), e.to_string()]}),
    }
}
fn py_json(v: &Value) -> String {
    match v {
        Value::Array(a) => format!("[{}]", a.iter().map(py_json).collect::<Vec<_>>().join(", ")),
        Value::Object(o) => format!(
            "{{{}}}",
            o.iter()
                .map(|(k, v)| format!("{}: {}", py_json(&json!(k)), py_json(v)))
                .collect::<Vec<_>>()
                .join(", ")
        ),
        _ => serde_json::to_string(v)
            .unwrap()
            .chars()
            .map(|c| {
                if c.is_ascii() {
                    c.to_string()
                } else {
                    let mut units = [0; 2];
                    c.encode_utf16(&mut units)
                        .iter()
                        .map(|u| format!("\\u{u:04x}"))
                        .collect::<String>()
                }
            })
            .collect(),
    }
}
fn observe(mut v: Value, tmp: &Path) -> Value {
    let serialized = serde_json::to_string(&v).unwrap();
    let escaped = serde_json::to_string(tmp.to_str().unwrap()).unwrap();
    v = serde_json::from_str(&serialized.replace(&escaped[1..escaped.len() - 1], "<tmp>")).unwrap();
    #[cfg(windows)]
    {
        let posix = tmp
            .to_str()
            .unwrap()
            .trim_start_matches("\\\\?\\")
            .replace('\\', "/");
        let serialized = serde_json::to_string(&v).unwrap();
        v = serde_json::from_str(&serialized.replace(&posix, "<tmp>")).unwrap();
    }
    if v.get("value").is_some() {
        let text = py_json(&v["value"]);
        if text.len() > 512 {
            v["value"] = json!({"len": text.len(), "sha256": digest::sha256(text.as_bytes())});
        }
    }
    v
}
fn content(root: &Path, mode: &str) -> Value {
    let archive = json!({"classification":"notes", "path":"notes"});
    let mut raw = json!({"schema_version":1, "profile":"content_workspace",
        "archives":[archive.clone()], "scan":{"unclassified":[]}});
    fs::create_dir(root.join("notes")).unwrap();
    if mode != "absent" {
        put(root, "notes/a.md", "searchable");
    }
    if mode == "uncovered" {
        put(root, "other/a.md", "searchable");
    }
    match mode {
        "schema" => raw["schema_version"] = json!(2),
        "profile_field" => raw["profile"] = json!("code_app"),
        "archives_empty" => raw["archives"] = json!([]),
        "archives_type" => raw["archives"] = json!({}),
        "archive_object" => raw["archives"] = json!([1]),
        "classification" => raw["archives"][0]["classification"] = json!("TODO"),
        "path" => raw["archives"][0]["path"] = json!("../escape"),
        "archive_missing" => raw["archives"][0]["path"] = json!("gone"),
        "duplicate" => raw["archives"] = json!([archive.clone(), archive]),
        "overlap" | "overlap_reversed" => {
            let child = json!({"classification":"child", "path":"notes/a.md"});
            raw["archives"] = if mode == "overlap" {
                json!([archive, child])
            } else {
                json!([child, archive])
            };
        }
        "scan_type" => raw["scan"] = json!([]),
        "unclassified" => raw["scan"]["unclassified"] = json!(["x"]),
        "valid" | "absent" | "uncovered" | "scan_error" | "missing" | "invalid" | "profile" => (),
        _ => panic!("unknown content case {mode}"),
    }
    if mode != "missing" {
        let body = if mode == "invalid" {
            "{".into()
        } else {
            raw.to_string()
        };
        put(root, "config/content-onboarding.json", body);
    }
    let mut host = Observer {
        root: root.into(),
        scan_error: mode == "scan_error",
        ..Default::default()
    };
    let profile = if mode == "profile" {
        "code_app"
    } else {
        "content_workspace"
    };
    let result = outcome(m::validate_content_onboarding(
        root,
        &json!(profile),
        &mut host,
    ));
    assert!(host.opens.is_empty());
    assert!(host.sql.borrow().is_empty());
    result
}
fn query() -> Value {
    json!({"archive_slug":"notes", "query":"adr-99", "expected_path":"a.md"})
}
fn memory_inputs(name: &str) -> (String, Value) {
    let mut spec = query();
    let queries = match name {
        "none" => Value::Null,
        "empty" => json!([]),
        "type" => json!("query"),
        "object" => json!([1]),
        "fields" => json!([{}]),
        "mixed" => json!([spec, 1]),
        "query" | "path" | "wrong_archive" | "wrong_path" => {
            let (field, value) = match name {
                "query" => ("query", "TODO"),
                "path" => ("expected_path", ""),
                "wrong_archive" => ("archive_slug", "other"),
                _ => ("expected_path", "other.md"),
            };
            spec[field] = json!(value);
            json!([spec])
        }
        name if name.starts_with("sanitize_") => {
            let index: usize = name[9..].parse().unwrap();
            spec["query"] = json!(
                [
                    "\"alpha beta\"",
                    "alpha OR beta",
                    "---",
                    "\u{3b1}",
                    "alpha\"beta",
                    "alpha:beta",
                ][index]
            );
            json!([spec])
        }
        _ => {
            return (
                if name == "mode_empty" { "empty" } else { name }.into(),
                json!([spec]),
            );
        }
    };
    ("valid".into(), queries)
}
fn database_state(db: &Connection) -> Value {
    let mut state = Vec::new();
    for sql in [
        "PRAGMA journal_mode",
        "PRAGMA user_version",
        "PRAGMA schema_version",
        "SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name,tbl_name,sql",
    ] {
        let mut statement = db.prepare(sql).unwrap();
        let columns = statement.column_count();
        let rows = statement
            .query_map([], |row| {
                (0..columns)
                    .map(|i| {
                        Ok(match row.get_ref(i)? {
                            rusqlite::types::ValueRef::Null => Value::Null,
                            rusqlite::types::ValueRef::Integer(v) => json!(v),
                            rusqlite::types::ValueRef::Text(v) => {
                                json!(std::str::from_utf8(v).unwrap())
                            }
                            other => panic!("unexpected database state {other:?}"),
                        })
                    })
                    .collect::<rusqlite::Result<Vec<_>>>()
            })
            .unwrap()
            .collect::<rusqlite::Result<Vec<_>>>()
            .unwrap();
        state.push(json!(rows));
    }
    json!(state)
}
fn expected_uri(root: &Path) -> String {
    let path = root.join(".mir/memory.db").canonicalize().unwrap();
    let path = path.to_str().unwrap();
    #[cfg(windows)]
    let path = path.trim_start_matches("\\\\?\\").replace('\\', "/");
    let prefix = if cfg!(windows) && path.starts_with("//") {
        "file:"
    } else if cfg!(windows) {
        "file:///"
    } else {
        "file://"
    };
    let encoded: String = path
        .bytes()
        .enumerate()
        .map(|(i, b)| {
            if b.is_ascii_alphanumeric()
                || b"/-._~".contains(&b)
                || (cfg!(windows) && i == 1 && b == b':')
            {
                (b as char).to_string()
            } else {
                format!("%{b:02X}")
            }
        })
        .collect();
    format!("{prefix}{encoded}?mode=ro&immutable=1")
}
fn assert_sql_contract(root: &Path, host: &Observer, mode: &str, queries: &Value) {
    let should_open = mode != "missing" && queries.as_array().is_some_and(|q| !q.is_empty());
    if !should_open {
        assert!(host.opens.is_empty());
        assert!(host.sql.borrow().is_empty());
        return;
    }
    assert_eq!(host.opens, vec![(expected_uri(root), true, true)]);
    let calls = host.sql.borrow();
    if mode == "unreadable" {
        assert!(calls.is_empty());
        return;
    }
    assert_eq!(calls[0], ("PRAGMA query_only = ON".into(), vec![]));
    if calls.len() > 1 {
        assert_eq!(calls[1], (OBJECT_SQL.into(), vec![]));
    }
    let mut expected_params = Vec::new();
    if !["corrupt", "schema", "wrong_columns"].contains(&mode) && !mode.starts_with("drop_") {
        for spec in queries.as_array().unwrap() {
            let fields = ["archive_slug", "query", "expected_path"];
            if !fields
                .iter()
                .all(|k| spec[*k].as_str().is_some_and(|v| !v.is_empty()))
                || spec["query"] == "TODO"
            {
                continue;
            }
            let sanitized = match spec["query"].as_str().unwrap() {
                "adr-99" => "\"adr\" \"99\"",
                "\"alpha beta\"" => "\"alpha beta\"",
                "alpha OR beta" => "\"alpha\" \"OR\" \"beta\"",
                "---" => "\"__noop__\"",
                "\u{3b1}" => "\"\u{3b1}\"",
                "alpha\"beta" | "alpha:beta" => "\"alpha\" \"beta\"",
                other => panic!("unhandled FTS query {other}"),
            };
            expected_params.push(vec![
                json!(sanitized),
                spec["archive_slug"].clone(),
                spec["expected_path"].clone(),
            ]);
        }
    }
    if mode == "wrong_columns" {
        expected_params.push(vec![json!("\"adr\" \"99\""), json!("notes"), json!("a.md")]);
    }
    assert_eq!(calls.len().saturating_sub(2), expected_params.len());
    for ((sql, params), expected) in calls.iter().skip(2).zip(expected_params) {
        assert_eq!(sql, QUERY_SQL);
        assert_eq!(params, &expected);
    }
}
fn memory(root: &Path, name: &str) -> Value {
    let (mode, queries) = memory_inputs(name);
    let path = root.join(".mir/memory.db");
    fs::create_dir(root.join(".mir")).unwrap();
    if mode == "corrupt" {
        fs::write(&path, b"not a database").unwrap();
    } else if mode != "missing" {
        let db = Connection::open(&path).unwrap();
        if !["schema", "unreadable"].contains(&mode.as_str()) {
            db.execute_batch(DDL).unwrap();
            if let Some(table) = mode.strip_prefix("drop_") {
                db.execute_batch(&format!("DROP TABLE {table}")).unwrap();
            } else if mode == "wrong_columns" {
                db.execute_batch(
                    "ALTER TABLE external_documents RENAME COLUMN archive_id TO wrong",
                )
                .unwrap();
            } else if mode != "empty" {
                db.execute_batch(
                    "INSERT INTO external_archives VALUES(1,'notes','archive');\
                    INSERT INTO external_documents VALUES(1,1,'a.md');\
                    INSERT INTO external_chunks VALUES(1,1);\
                    INSERT INTO external_chunks_fts(rowid,body) VALUES(1,'adr 99 alpha beta');",
                )
                .unwrap();
            }
        }
    }
    let before = if ["missing", "corrupt", "unreadable"].contains(&mode.as_str()) {
        None
    } else {
        Some(database_state(&Connection::open(&path).unwrap()))
    };
    let mut host = Observer {
        root: root.into(),
        denied: mode == "unreadable",
        ..Default::default()
    };
    let result = m::validate_memory(root, &json!({"queries":queries}), &mut host);
    assert_sql_contract(root, &host, &mode, &queries);
    match (result, before) {
        (Ok(result), Some(before)) => {
            let after = database_state(&Connection::open(&path).unwrap());
            assert_eq!(after, before, "acceptance must not change database state");
            success(json!([result, after]))
        }
        (result, _) => outcome(result),
    }
}
fn phase_cases() -> Vec<(&'static str, Value)> {
    let mut cases = vec![
        ("surface.open_gaps", json!(0)),
        ("surface.coverage", Value::Null),
        ("surface.coverage", json!({})),
        ("surface.coverage.l1", json!([])),
        ("surface.coverage.l1.total", json!(0)),
        ("surface.coverage.l1.total", json!(2)),
        ("surface.coverage.l1.tbd", json!(1)),
        ("surface.ai_ready", Value::Null),
        ("surface.ai_ready.ready", json!(0)),
        ("surface.ai_ready.blocked", json!(1)),
        ("surface.open_gaps", json!(1)),
        ("surface.full_review", json!({})),
        ("surface.full_review.memory", json!("fail")),
        ("surface.native_evidence", Value::Null),
        ("surface.native_evidence.extra", json!(1)),
        ("surface.native_evidence.format", json!("other")),
        ("surface.native_evidence.coverage_key", json!("bad")),
        ("surface.native_evidence.meta_path", json!("../escape")),
        ("surface.evidence_paths", json!([])),
        ("meta.coverage", json!([])),
        ("meta.coverage.l1", Value::Null),
        ("meta.coverage.l1.filled", json!(2)),
        ("meta.ai_ready.ready", json!(2)),
        ("gaps.gaps", json!({})),
        ("gaps.gaps", json!([1])),
        ("review.reviews", json!({})),
        ("review.reviews.memory", json!({})),
        ("review.reviews.memory.status", json!("fail")),
        ("review.reviews.memory.evidence_paths", json!([])),
        (
            "review.reviews.memory.evidence_paths",
            json!(["proof", "proof"]),
        ),
        ("review.reviews.memory.evidence_paths", json!(["../escape"])),
        (
            "review.reviews.memory.evidence_paths",
            json!(["undeclared"]),
        ),
        ("review.reviews.memory.verification", json!("TODO")),
        ("file.proof", json!("")),
        ("file.proof", json!("TODO")),
        ("file.proof", Value::Null),
        ("file.proof", json!([255])),
        ("file.meta", Value::Null),
        ("file.meta", json!([255])),
        ("file.meta", json!("[")),
        ("file.meta", json!("[]")),
    ];
    for target in [
        "surface.coverage.l1.total",
        "surface.coverage.l1.filled",
        "surface.coverage.l1.derived",
        "surface.coverage.l1.na",
        "surface.coverage.l1.tbd",
    ] {
        cases.push((target, json!(true)));
    }
    for value in [json!(-1), json!("1"), Value::Null] {
        cases.push(("surface.coverage.l1.total", value));
    }
    cases.push(("shape", json!("completeness")));
    cases.push(("shape", json!("derived")));
    for target in [
        "surface.ai_ready.ready",
        "surface.ai_ready.incomplete",
        "surface.ai_ready.blocked",
    ] {
        for value in [json!(true), json!(-1)] {
            cases.push((target, value));
        }
    }
    for value in [Value::Null, json!("proof"), json!([1])] {
        cases.push(("review.reviews.memory.evidence_paths", value));
    }
    cases
}
fn phase(root: &Path, target: &str, value: Value) -> Value {
    let mut coverage = json!({});
    for layer in ["l1", "l2", "l3", "l4"] {
        coverage[layer] = json!({"total":1, "filled":1, "derived":0, "na":0, "tbd":0});
    }
    let ready = json!({"ready":1, "incomplete":0, "blocked":0});
    let mut reviews = json!({});
    let mut full_review = json!({});
    for key in REVIEWS {
        reviews[key] = json!({"status":"pass", "evidence_paths":["proof"],
            "verification":"Checked"});
        full_review[key] = json!("pass");
    }
    let surface = json!({"coverage":coverage.clone(), "ai_ready":ready.clone(), "open_gaps":0,
        "full_review":full_review, "native_evidence":{"format":"mir_spec_yaml_v1",
        "meta_path":"meta", "gaps_path":"gaps", "review_path":"review",
        "coverage_key":"coverage"}, "evidence_paths":["meta", "gaps", "review", "proof"]});
    let mut objects = json!({"surface":surface, "meta":{"coverage":coverage, "ai_ready":ready},
        "gaps":{"gaps":[]}, "review":{"reviews":reviews}});
    if target == "shape" {
        if value == "completeness" {
            let coverage = objects["meta"]
                .as_object_mut()
                .unwrap()
                .remove("coverage")
                .unwrap();
            objects["meta"]["completeness"] = coverage;
            objects["surface"]["native_evidence"]["coverage_key"] = value.clone();
        } else {
            for doc in ["meta", "surface"] {
                for row in objects[doc]["coverage"]
                    .as_object_mut()
                    .unwrap()
                    .values_mut()
                {
                    row["filled"] = json!(0);
                    row["derived"] = json!(1);
                }
            }
        }
    } else if let Some(path) = target.strip_prefix("drop.") {
        let mut object = &mut objects;
        let keys: Vec<_> = path.split('.').collect();
        for key in &keys[..keys.len() - 1] {
            object = &mut object[*key];
        }
        object
            .as_object_mut()
            .unwrap()
            .remove(keys[keys.len() - 1])
            .unwrap();
    } else if !target.starts_with("file.") {
        let mut object = &mut objects;
        let keys: Vec<_> = target.split('.').collect();
        for key in &keys[..keys.len() - 1] {
            object = &mut object[*key];
        }
        object[keys[keys.len() - 1]] = value.clone();
    }
    for doc in ["meta", "gaps", "review"] {
        put(root, doc, objects[doc].to_string());
    }
    put(root, "proof", "Verified");
    if let Some(name) = target.strip_prefix("file.") {
        if value.is_null() {
            fs::remove_file(root.join(name)).unwrap();
        } else if value.is_array() {
            put(root, name, [255]);
        } else {
            put(root, name, value.as_str().unwrap());
        }
    }
    let mut host = Observer {
        root: root.into(),
        ..Default::default()
    };
    let result = outcome(m::validate_phase2(root, &objects["surface"], &mut host));
    assert!(host.opens.is_empty());
    assert!(host.sql.borrow().is_empty());
    result
}
#[test]
fn every_frozen_record_replays_exactly() {
    let records: Value =
        serde_json::from_str(include_str!("fixtures/w2/b30-adoption-phase2.json")).unwrap();
    assert_eq!(records.as_object().unwrap().len(), 113);
    let phases = phase_cases();
    let mut replayed = 0;
    for (name, expected) in records.as_object().unwrap() {
        let root = tempfile::Builder::new()
            .prefix("b30-phase2-")
            .tempdir_in(std::env::temp_dir().canonicalize().unwrap())
            .unwrap();
        assert!(
            root.path()
                .starts_with(std::env::temp_dir().canonicalize().unwrap())
        );
        let (group, mode) = name.split_once('.').unwrap();
        let result = match group {
            "content" => content(root.path(), mode),
            "memory" => memory(root.path(), mode),
            "phase2" => {
                let (index, target) = mode.split_once('.').unwrap();
                let (expected_target, value) = &phases[index.parse::<usize>().unwrap()];
                assert_eq!(&target, expected_target);
                phase(root.path(), target, value.clone())
            }
            // Witness: a removed key; the Python case deletes it from the built documents.
            "phase2_drop" => phase(root.path(), &format!("drop.{mode}"), Value::Null),
            _ => panic!("unhandled frozen record {name}"),
        };
        let actual = observe(result, root.path());
        assert_eq!(&actual, expected, "record {name}");
        replayed += 1;
        eprintln!("REPLAY {name}");
    }
    assert_eq!(replayed, 113);
    eprintln!("B30 phase2: replayed={replayed}, exempt=0, total=113");
}
