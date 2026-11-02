use handoff_packet::executor_registry::JobRegistry;
use rusqlite::Connection;
use serde_json::{Value, json};
use std::{fs, path::PathBuf};

fn scratch() -> PathBuf {
    static SEQUENCE: std::sync::atomic::AtomicUsize = std::sync::atomic::AtomicUsize::new(0);
    let root = std::env::var_os("MIR_NATIVE_TEST_SCRATCH")
        .map(PathBuf::from)
        .unwrap_or_else(std::env::temp_dir)
        .join(format!(
            "registry-{}-{}",
            std::process::id(),
            SEQUENCE.fetch_add(1, std::sync::atomic::Ordering::Relaxed)
        ));
    fs::create_dir_all(&root).unwrap();
    root
}
fn snapshot(db: &Connection) -> Value {
    let columns: Vec<Value> = db
        .prepare("PRAGMA table_info(jobs)")
        .unwrap()
        .query_map([], |row| {
            Ok(json!([
                row.get::<_, i64>(0)?,
                row.get::<_, String>(1)?,
                row.get::<_, String>(2)?,
                row.get::<_, i64>(3)?,
                row.get::<_, Option<String>>(4)?,
                row.get::<_, i64>(5)?
            ]))
        })
        .unwrap()
        .map(Result::unwrap)
        .collect();
    let mut stmt = db.prepare("SELECT * FROM jobs ORDER BY job_id").unwrap();
    let names: Vec<String> = stmt.column_names().iter().map(|s| s.to_string()).collect();
    let rows: Vec<Value> = stmt
        .query_map([], |row| {
            let mut out = serde_json::Map::new();
            for (i, name) in names.iter().enumerate() {
                use rusqlite::types::ValueRef;
                let value = match row.get_ref(i)? {
                    ValueRef::Null => Value::Null,
                    ValueRef::Integer(n) => json!(n),
                    ValueRef::Real(n) => json!(n),
                    ValueRef::Text(s) => json!(std::str::from_utf8(s).unwrap()),
                    ValueRef::Blob(_) => panic!("unexpected blob"),
                };
                out.insert(name.clone(), value);
            }
            Ok(Value::Object(out))
        })
        .unwrap()
        .map(Result::unwrap)
        .collect();
    let sweeps: Vec<Value> = db
        .prepare("SELECT * FROM artifact_sweeps")
        .unwrap()
        .query_map([], |r| {
            Ok(json!([
                r.get::<_, String>(0)?,
                r.get::<_, String>(1)?,
                r.get::<_, i64>(2)?,
                r.get::<_, i64>(3)?,
                r.get::<_, String>(4)?
            ]))
        })
        .unwrap()
        .map(Result::unwrap)
        .collect();
    json!({"columns":columns,"rows":rows,"sweeps":sweeps})
}
#[test]
fn python_registry_migrations_and_writes() {
    let fixture: Value =
        serde_json::from_str(include_str!("fixtures/executor_registry.json")).unwrap();
    let root = scratch();
    let path = root.join("jobs.db");
    for case in fixture["migrations"].as_array().unwrap() {
        let db = Connection::open(&path).unwrap();
        db.execute_batch(case["initial"].as_str().unwrap()).unwrap();
        drop(db);
        let registry = JobRegistry::open(&path).unwrap();
        assert_eq!(
            snapshot(registry.connection()),
            case["expected"],
            "{:?}",
            case["removed"]
        );
        drop(registry);
        fs::remove_file(&path).unwrap();
    }
    let registry = JobRegistry::open(&path).unwrap();
    for op in fixture["operations"].as_array().unwrap() {
        let id = op["job_id"].as_str().unwrap_or("job");
        let result = match op["op"].as_str().unwrap() {
            "insert" => registry.insert(&op["record"]),
            "update_route_metadata" => registry.update_route_metadata(
                id,
                &op["execution_backend"],
                &op["resolved_model"],
                &op["resolved_reasoning_effort"],
            ),
            "update_ai_run_metadata" => registry.update_ai_run_metadata(id, &op["metadata"]),
            "update_status" => registry.update_status(id, op["status"].as_str().unwrap(), op),
            "cancel" => registry.cancel(id).map(|found| {
                assert_eq!(json!(found), op["result"]);
            }),
            "mark_resumed" => registry.mark_resumed(id, op["resumed_at"].as_str().unwrap()),
            "record_artifact_sweep" => {
                registry.record_artifact_sweep(id, "artifacts", 2, 10, "now")
            }
            other => panic!("{other}"),
        };
        if op.get("error").is_some() {
            assert!(result.is_err());
        } else {
            result.unwrap();
        }
        assert_eq!(
            snapshot(registry.connection()),
            op["expected"],
            "{}",
            op["op"]
        );
    }
    drop(registry);
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn python_redaction_and_truncation() {
    let fixture: Value =
        serde_json::from_str(include_str!("fixtures/executor_registry.json")).unwrap();
    for case in fixture["sanitize"].as_array().unwrap() {
        assert_eq!(
            handoff_packet::executor_registry::sanitize(case["input"].as_str().unwrap()).unwrap(),
            case["expected"].as_str().unwrap()
        );
    }
}

#[cfg(unix)]
#[test]
fn private_sidecars_and_no_follow() {
    use std::os::unix::{fs::PermissionsExt, fs::symlink};
    let root = scratch().join("permissions");
    fs::create_dir_all(&root).unwrap();
    let path = root.join("jobs.db");
    let registry = JobRegistry::open(&path).unwrap();
    registry
        .connection()
        .execute_batch("PRAGMA journal_mode=WAL; CREATE TABLE extra(x);")
        .unwrap();
    for suffix in ["", "-wal", "-shm"] {
        let candidate = PathBuf::from(format!("{}{suffix}", path.display()));
        fs::set_permissions(&candidate, fs::Permissions::from_mode(0o644)).unwrap();
    }
    registry.cancel("absent").unwrap();
    for suffix in ["", "-wal", "-shm"] {
        assert_eq!(
            fs::metadata(format!("{}{suffix}", path.display()))
                .unwrap()
                .permissions()
                .mode()
                & 0o777,
            0o600
        );
    }
    drop(registry);
    let link = root.join("link.db");
    symlink(&path, &link).unwrap();
    assert!(JobRegistry::open(&link).is_err());
    assert!(JobRegistry::open(&root).is_err());
    fs::remove_dir_all(root).unwrap();
}
