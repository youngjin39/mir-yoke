//! Replay all immutable Python bootstrap surface records.
#![forbid(unsafe_code)]
use handoff_packet::mir_cli::bootstrap::{self as m, Error, Host};
use handoff_packet::plugin_scripts::ontology_check::Doc;
use rusqlite::{Connection, types::ValueRef};
use serde_json::{Value, json};
use std::{
    collections::BTreeMap,
    fs,
    path::{Path, PathBuf},
};
#[path = "../src/digest.rs"]
mod digest;

const SURFACES: &[&str] = &[
    "CLAUDE.md",
    "AGENTS.md",
    ".claude/settings.json",
    ".codex/config.toml",
    ".codex/hooks.json",
    ".ai-harness/deny-list.yaml",
    ".claude/agents/main-orchestrator.md",
    ".codex/agents/main-orchestrator.toml",
    "config/sub-agent-policy.json",
    "config/capability-sources.json",
    "config/adopter-boundary.json",
    "config/adopter-payload.json",
    ".claude/hooks/a.sh",
];
fn put(root: &Path, name: &str, body: impl AsRef<[u8]>) -> PathBuf {
    let path = root.join(name);
    fs::create_dir_all(path.parent().unwrap()).unwrap();
    fs::write(&path, body).unwrap();
    path
}
struct Fake<'a> {
    mode: &'a str,
}
impl Host for Fake<'_> {
    fn env(&mut self, _: &str) -> Option<String> {
        panic!("unexpected env")
    }
    fn resolve(&mut self, _: &Path) -> Result<PathBuf, Error> {
        panic!("unexpected resolve")
    }
    fn expanduser(&mut self, _: &Path) -> Result<PathBuf, Error> {
        panic!("unexpected expanduser")
    }
    fn is_dir(&mut self, _: &Path) -> bool {
        panic!("unexpected is_dir")
    }
    fn writable(&mut self, _: &Path) -> bool {
        panic!("unexpected writable")
    }
    fn device(&mut self, _: &Path) -> Result<u64, Error> {
        panic!("unexpected device")
    }
    fn run(&mut self, _: &m::CommandRequest) -> Result<m::CommandOutput, Error> {
        panic!("unexpected subprocess")
    }
    fn which(&mut self, name: &str) -> Option<PathBuf> {
        (self.mode != "runtime").then(|| PathBuf::from(format!("/tools/{name}")))
    }
    fn replace(&mut self, source: &Path, destination: &Path) -> Result<(), Error> {
        if self.mode.ends_with(".True") {
            return Err(Error::new("OSError", "replace denied"));
        }
        tempfile::TempPath::try_from_path(source)
            .and_then(|p| p.persist(destination).map_err(|e| e.error))
            .map_err(|e| Error::new("OSError", e.to_string()))
    }
    fn bootstrap_memory_connect(
        &mut self,
        path: &Path,
    ) -> Result<handoff_packet::mir_core::memory::store::Connection, Error> {
        use handoff_packet::mir_core::memory::store::{self, ConnectOptions, VecLoading};
        store::connect(
            path,
            ConnectOptions {
                timeout: None,
                vec_loading: VecLoading::Unavailable("disabled"),
            },
        )
        .map_err(|e| Error::new(e.python_class(), e.to_string()))
    }
}
fn normalise(value: Value, root: &Path) -> Value {
    match value {
        Value::String(s) => {
            let s = s.replace(root.to_str().unwrap(), "<tmp>");
            #[cfg(windows)]
            let mut s = s
                .replace("\\\\?\\", "")
                .replace(
                    root.to_str().unwrap().trim_start_matches("\\\\?\\"),
                    "<tmp>",
                )
                .replace(
                    &root
                        .to_str()
                        .unwrap()
                        .trim_start_matches("\\\\?\\")
                        .replace('\\', "/"),
                    "<tmp>",
                );
            #[cfg(windows)]
            for path in SURFACES.iter().copied().chain([
                "value",
                ".mir/capability-lock.json",
                "spec/bootstrap-evidence.json",
                "spec/STATE.md",
                "spec/index.yaml",
                "spec/graph.yaml",
                "spec/gaps.yaml",
            ]) {
                s = s.replace(
                    &format!("<tmp>\\{}", path.replace('/', "\\")),
                    &format!("<tmp>/{path}"),
                );
            }
            json!(s.replace("<tmp>\\", "<tmp>/").replace("\r\n", "\n"))
        }
        Value::Array(v) => Value::Array(v.into_iter().map(|v| normalise(v, root)).collect()),
        Value::Object(v) => Value::Object(
            v.into_iter()
                .map(|(k, v)| (k, normalise(v, root)))
                .collect(),
        ),
        v => v,
    }
}
fn observe(result: Result<Value, Error>, root: &Path) -> Value {
    match result {
        Ok(value) => {
            let value = normalise(value, root);
            let text = Doc::from(value.clone()).dump(true, None);
            json!({"value": if text.len() > 512 {
                json!({"len":text.len(), "sha256":digest::sha256(text.as_bytes())})
            } else { value }})
        }
        Err(e) => normalise(json!({"error":[e.class,e.message]}), root),
    }
}
fn surfaces(root: &Path, mode: &str, host: &mut Fake<'_>) -> Result<Value, Error> {
    for name in SURFACES {
        put(
            root,
            name,
            if name.ends_with(".json") {
                "{\"hooks\":{\"Stop\":[]}}"
            } else {
                ""
            },
        );
    }
    if let Some(name) = mode.strip_prefix("missing:") {
        fs::remove_file(root.join(name)).unwrap();
    }
    if let Some(name) = mode.strip_prefix("json:") {
        put(root, name, "{");
    }
    match mode {
        "hooks" => {
            put(root, ".claude/settings.json", "{}");
        }
        "settings_list" => {
            put(root, ".claude/settings.json", "[]");
        }
        "toml" => {
            put(root, ".codex/config.toml", "[");
        }
        "mixed" => {
            put(
                root,
                ".codex/config.toml",
                "sandbox_mode=\"x\"\ndefault_permissions=\"x\"",
            );
        }
        _ => {}
    }
    m::validate_surfaces(root, host).map(|v| json!(v))
}
fn architecture(root: &Path, mode: &str) -> Result<Value, Error> {
    let outputs = [
        "spec/STATE.md",
        "spec/index.yaml",
        "spec/graph.yaml",
        "spec/gaps.yaml",
    ];
    let mut coverage = json!({"ai_ready":{"ready":1,"incomplete":0,"blocked":0}});
    for (key, n) in [("l1", 1), ("l2", 1), ("l3", 9), ("l4", 10)] {
        coverage[key] = json!({"total":n,"filled":n,"derived":0,"na":0,"tbd":0});
    }
    if let Some(key) = mode.strip_prefix("count:") {
        coverage["l3"][key] = json!(if key == "derived" { -1 } else { 1 });
    }
    match mode {
        "zero" => coverage["l2"] = json!({"total":0,"filled":0,"derived":0,"na":0,"tbd":0}),
        "layer" => coverage["l4"] = Value::Null,
        "ai_blocked" => coverage["ai_ready"]["blocked"] = json!(1),
        "ai_invalid" => coverage["ai_ready"] = json!({}),
        _ => {}
    }
    let mut evidence = json!({"schema_version":2,
        "sequence":["mir-core:design","mir-core:spec-architect"],
        "capability_commit":"abc","outputs":outputs,"coverage":coverage,"open_gaps":0,
        "full_review":{"project_structure":"pass","memory":"pass","discoverability":"pass",
            "requirements":"pass","organization":"pass"}});
    if let Some(key) = mode.strip_prefix("field:") {
        evidence[key] = Value::Null;
    }
    if mode == "review_partial" {
        evidence["full_review"]["memory"] = json!("fail");
    }
    for (name, body) in outputs.iter().zip([
        "Complete",
        "requirements: [{status: ready}]",
        "nodes: [a]\nedges: []",
        "gaps: []",
    ]) {
        put(root, name, body);
    }
    if let Some(doc) = mode.strip_prefix("doc:") {
        let (name, body) = doc.split_once(':').unwrap();
        put(root, &format!("spec/{name}"), body);
    }
    let path = put(root, "spec/bootstrap-evidence.json", evidence.to_string());
    let lock = put(
        root,
        ".mir/capability-lock.json",
        "{\"source\":{\"commit\":\"abc\"}}",
    );
    if ["missing", "linked"].contains(&mode) {
        fs::remove_file(&path).unwrap();
        if mode == "linked" {
            symlink(&lock, &path);
        }
    }
    if mode == "list" {
        fs::write(&path, "[]").unwrap();
    }
    if mode.starts_with("lock_") {
        fs::remove_file(&lock).unwrap();
        match mode {
            "lock_bad" => {
                fs::write(&lock, "{").unwrap();
            }
            "lock_list" => {
                fs::write(&lock, "[]").unwrap();
            }
            "lock_source" => {
                fs::write(&lock, "{}").unwrap();
            }
            "lock_missing" => {}
            _ => panic!("unknown lock setup"),
        }
    }
    if ["output_missing", "output_linked"].contains(&mode) {
        let out = root.join("spec/STATE.md");
        fs::remove_file(&out).unwrap();
        if mode == "output_linked" {
            symlink(&lock, &out);
        }
    }
    m::validate_architecture_evidence(root).map(|v| json!(v))
}
fn symlink(source: &Path, destination: &Path) {
    #[cfg(unix)]
    std::os::unix::fs::symlink(source, destination).unwrap();
    #[cfg(windows)]
    std::os::windows::fs::symlink_file(source, destination).unwrap();
}
fn rows(db: &Connection, sql: &str) -> Value {
    let mut statement = db.prepare(sql).unwrap();
    let count = statement.column_count();
    let rows = statement
        .query_map([], |row| {
            Ok(Value::Array(
                (0..count)
                    .map(|i| match row.get_ref(i).unwrap() {
                        ValueRef::Null => Value::Null,
                        ValueRef::Integer(n) => json!(n),
                        ValueRef::Real(n) => json!(n),
                        ValueRef::Text(s) => json!(std::str::from_utf8(s).unwrap()),
                        ValueRef::Blob(_) => panic!("unexpected blob"),
                    })
                    .collect(),
            ))
        })
        .unwrap();
    Value::Array(rows.map(Result::unwrap).collect())
}
fn state(path: &Path) -> Value {
    let db = Connection::open(path).unwrap();
    let pragmas: Vec<_> = ["journal_mode", "user_version", "schema_version"]
        .iter()
        .map(|key| rows(&db, &format!("PRAGMA {key}")))
        .collect();
    let migrations = if db
        .prepare("SELECT 1 FROM sqlite_master WHERE name='schema_migrations'")
        .unwrap()
        .exists([])
        .unwrap()
    {
        rows(&db, "SELECT * FROM schema_migrations ORDER BY version")
    } else {
        json!([])
    };
    json!([
        pragmas,
        migrations,
        rows(
            &db,
            "SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name,tbl_name,sql"
        )
    ])
}
fn stage(root: &Path, mode: &str) -> Result<Value, Error> {
    let path = root.join("db/source.db");
    fs::create_dir(path.parent().unwrap()).unwrap();
    if mode == "pages" {
        Connection::open(&path)
            .unwrap()
            .execute_batch(concat!(
                "CREATE TABLE t(x INTEGER, v TEXT); WITH RECURSIVE c(x) AS ",
                "(SELECT 1 UNION ALL SELECT x + 1 FROM c WHERE x < 400) ",
                "INSERT INTO t SELECT x, printf('%0300d', x) FROM c; ",
                "DELETE FROM t WHERE x % 3 > 0 OR x < 200;"
            ))
            .unwrap();
        let db = Connection::open(m::stage_memory_db(&path)?).unwrap();
        return Ok(json!([
            rows(&db, "PRAGMA page_count"),
            rows(&db, "PRAGMA freelist_count"),
            rows(
                &db,
                "SELECT count(*), min(rowid), max(rowid), sum(rowid) FROM t"
            )
        ]));
    }
    let source = (mode != "missing").then(|| Connection::open(&path).unwrap());
    if let Some(db) = &source {
        db.execute_batch(if mode == "wal" {
            "PRAGMA journal_mode=WAL"
        } else {
            "PRAGMA journal_mode=DELETE"
        })
        .unwrap();
        db.execute_batch(concat!(
            "PRAGMA user_version=7; CREATE TABLE schema_migrations",
            "(version INTEGER, name TEXT);INSERT INTO schema_migrations VALUES(1,'seed');"
        ))
        .unwrap();
    }
    let staged = m::stage_memory_db(&path)?;
    if source.is_some() {
        let before = json!([state(&path), state(&staged)]);
        Connection::open(&staged)
            .unwrap()
            .execute("INSERT INTO schema_migrations VALUES(2,'isolated')", [])
            .unwrap();
        Ok(json!([before, state(&path), state(&staged)]))
    } else {
        Ok(json!([
            staged.parent() == path.parent(),
            staged != path,
            staged.is_file(),
            state(&staged)
        ]))
    }
}
fn memory(root: &Path, mode: &str, host: &mut Fake<'_>) -> Result<Value, Error> {
    let path = root.join("synthetic.db");
    {
        let db = Connection::open(&path).unwrap();
        db.execute_batch(concat!(
            "CREATE TABLE external_archives(id, slug);",
            "CREATE TABLE external_documents(id, archive_id, relative_path);",
            "CREATE TABLE external_chunks(id, document_id);",
            "CREATE VIRTUAL TABLE external_chunks_fts USING fts5(body);",
            "INSERT INTO external_archives VALUES(1,'demo-content');",
            "INSERT INTO external_documents VALUES(1,1,'a.md');",
            "INSERT INTO external_chunks VALUES(1,1);",
            "INSERT INTO external_chunks_fts(rowid,body) VALUES(1,'alpha');"
        ))
        .unwrap();
        match mode {
            "archive" => {
                db.execute("UPDATE external_archives SET slug='other'", [])
                    .unwrap();
            }
            "path" => {
                db.execute("UPDATE external_documents SET relative_path='b.md'", [])
                    .unwrap();
            }
            "no_hit" => {
                db.execute("DELETE FROM external_chunks_fts", []).unwrap();
            }
            _ => {}
        }
    }
    let mut archive = json!({"classification":"notes","path":"notes","acceptance":{
        "query":if mode == "fts_error" { "\"" } else { "alpha" },"expected_path":"a.md"}});
    if mode == "invalid" {
        archive["acceptance"] = json!({});
    }
    if mode == "absent" {
        archive["acceptance"] = Value::Null;
    }
    let archives = match mode {
        "empty" => json!([]),
        "entry" => json!([null]),
        _ => json!([archive]),
    };
    m::validate_content_memory_acceptance(root, &path, "demo", &json!({"archives":archives}), host)
        .map(|v| json!(v))
}
fn projection(root: &Path, mode: &str, host: &mut Fake<'_>) -> Result<Value, Error> {
    let path = root.join("synthetic.db");
    Connection::open(&path)
        .unwrap()
        .execute_batch(concat!(
            "CREATE TABLE entities(id,slug); CREATE TABLE content_items(id,source,metadata_json);",
            "CREATE TABLE facts(id,subject_entity_id,predicate,object_literal,status,created_from);"
        ))
        .unwrap();
    if mode != "missing" {
        for name in ["docs/memory-map.md", "tasks/lessons.md"] {
            put(
                root,
                name,
                format!(
                    "prefix\n{}",
                    if mode == "markers" {
                        "<!-- mir:generated:start -->old<!-- mir:generated:end -->\nsuffix"
                    } else {
                        "kept\n"
                    }
                ),
            );
        }
    }
    let updates = m::build_projection_updates(root, &path, host)?;
    Ok(json!(
        updates
            .into_iter()
            .map(|(path, body)| (
                path.strip_prefix(root)
                    .unwrap()
                    .to_str()
                    .unwrap()
                    .replace('\\', "/"),
                body
            ))
            .collect::<BTreeMap<_, _>>()
    ))
}
fn case(root: &Path, name: &str, host: &mut Fake<'_>) -> Result<Value, Error> {
    let (group, mode) = name.split_once('.').unwrap();
    match group {
        "architecture" => architecture(root, mode),
        "surfaces" => surfaces(root, mode, host),
        "json" => {
            let path = if mode == "None" {
                root.join("value")
            } else {
                put(root, "value", mode)
            };
            m::validate_json_file(&path).map(|v| json!(v))
        }
        "stage" => stage(root, mode),
        "acceptance" => memory(root, mode, host),
        "projection" => projection(root, mode, host),
        "atomic" => {
            let path = put(root, "nested/value", "old");
            let result = if mode.starts_with("json.") {
                m::atomic_write_json(&path, &json!({"z":"\u{e9}","a":1}), host)
            } else {
                m::atomic_write_text(&path, "line\n\u{e9}", host)
            };
            let observed = observe(result.map(|_| Value::Null), root);
            let bytes = fs::read(&path).unwrap();
            #[cfg(windows)]
            let bytes = String::from_utf8(bytes)
                .unwrap()
                .replace("\r\n", "\n")
                .into_bytes();
            let hex: String = bytes.iter().map(|b| format!("{b:02x}")).collect();
            let mut names: Vec<_> = fs::read_dir(path.parent().unwrap())
                .unwrap()
                .map(|e| e.unwrap().file_name().to_str().unwrap().to_owned())
                .collect();
            names.sort();
            Ok(json!([observed, hex, names]))
        }
        "emit" => {
            let (status, as_json) = mode.split_once('.').unwrap();
            m::emit(
                as_json == "True",
                &json!({"status":status,"errors":["blocked"],"z":"\u{e9}"}),
            )
            .map(|v| json!(v))
        }
        _ => panic!("unmapped record {name}"),
    }
}
#[test]
fn replay_all_99_frozen_records() {
    let records: BTreeMap<String, Value> =
        serde_json::from_str(include_str!("fixtures/w2/b30-bootstrap-surfaces.json")).unwrap();
    assert_eq!(records.len(), 99);
    let mut failures = vec![];
    let (mut replayed, mut exempt) = (0, 0);
    for (name, expected) in records {
        if cfg!(windows)
            && ["architecture.linked", "architecture.output_linked"].contains(&name.as_str())
        {
            eprintln!("EXEMPT {name}: symlink creation requires Windows host privilege");
            exempt += 1;
            continue;
        }
        let temp = tempfile::tempdir_in(std::env::temp_dir()).unwrap();
        let root = temp.path().canonicalize().unwrap();
        let mode = name.split_once('.').unwrap().1;
        let mut host = Fake { mode };
        let actual = observe(case(&root, &name, &mut host), &root);
        replayed += 1;
        if actual != expected {
            failures.push(format!("{name}\nactual: {actual}\nexpected: {expected}"));
        }
    }
    assert_eq!(replayed + exempt, 99);
    assert_eq!(exempt, if cfg!(windows) { 2 } else { 0 });
    eprintln!("B30 surfaces: replayed={replayed}, exempt={exempt}, total=99");
    assert!(failures.is_empty(), "{}", failures.join("\n"));
}
