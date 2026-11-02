//! Resume CLI admission must stay read-only until it owns a supported route.
use handoff_packet::executor_registry::JobRegistry;
use serde_json::json;
use std::{
    ffi::OsString,
    fs,
    path::PathBuf,
    process::Command,
    time::{SystemTime, UNIX_EPOCH},
};
struct Scratch(PathBuf);
static NEXT: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);
impl Drop for Scratch {
    fn drop(&mut self) {
        if std::thread::panicking() {
            eprintln!(
                "native decline trace ({}):\n{}",
                self.0.join("decline-trace.log").display(),
                fs::read_to_string(self.0.join("decline-trace.log"))
                    .unwrap_or_else(|_| "<no declines>".into())
            );
        }
        let _ = fs::remove_dir_all(&self.0);
    }
}
fn scratch() -> Scratch {
    let base = std::env::var_os("MIR_NATIVE_TEST_SCRATCH")
        .map(PathBuf::from)
        .unwrap_or_else(std::env::temp_dir);
    let root = base.join(format!(
        "resume-cli-{}-{}-{}",
        std::process::id(),
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos(),
        NEXT.fetch_add(1, std::sync::atomic::Ordering::Relaxed)
    ));
    fs::create_dir_all(&root).unwrap();
    Scratch(root)
}
fn args(values: &[&str]) -> Vec<OsString> {
    values.iter().map(OsString::from).collect()
}
fn run(arguments: &[OsString], root: &Scratch) -> i32 {
    let mut command = Command::new(env!("CARGO_BIN_EXE_executor-query"));
    windows_path_only(&mut command);
    command
        .arg("--home-root")
        .arg(&root.0)
        .args(arguments)
        .current_dir(&root.0)
        .env(
            "MIR_EXECUTOR_DECLINE_TRACE",
            root.0.join("decline-trace.log"),
        )
        .output()
        .unwrap()
        .status
        .code()
        .unwrap()
}
#[test]
fn unsupported_options_decline_without_database_creation() {
    let root = scratch();
    for command in [
        args(&["resume", "--job-id", "saved", "--unknown"]),
        args(&["resume"]),
        args(&["resume", "--job-id", "saved", "--timeout", "invalid"]),
    ] {
        assert_eq!(run(&command, &root), 64);
        assert!(!root.0.join("tasks").join("jobs.db").exists());
    }
}
#[test]
fn saved_cross_target_and_backend_decline_without_registry_changes() {
    let root = scratch();
    let other = scratch();
    let db = root.0.join("tasks").join("jobs.db");
    let registry = JobRegistry::open(&db).unwrap();
    for (id, target, backend) in [
        ("cross", &other.0, "codex"),
        ("backend", &root.0, "unsupported"),
    ] {
        registry.insert(&json!({"job_id":id,"repo_root":target,"change_id":"fixture","category":"unit","codex_args":["exec","fixture"],"dispatch_brief_path":root.0.join("brief.md"),"execution_backend":backend,"timeout_seconds":600,"status":"failed","started_at":"fixture","allow_harness_self_modify":false,"resume_count":0,"cancel_requested":false})).unwrap();
    }
    drop(registry);
    let before = fs::read(&db).unwrap();
    for id in ["cross", "backend"] {
        assert_eq!(run(&args(&["resume", "--job-id", id]), &root), 64);
        assert_eq!(fs::read(&db).unwrap(), before);
    }
}
#[test]
fn integrity_failure_leaves_resume_state_unchanged() {
    let root = scratch();
    fs::write(root.0.join("brief.md"), "changed").unwrap();
    let db = root.0.join("tasks").join("jobs.db");
    let registry = JobRegistry::open(&db).unwrap();
    registry.insert(&json!({"job_id":"saved","repo_root":root.0,"change_id":"fixture","category":"unit","codex_args":["exec","fixture"],"dispatch_brief_path":root.0.join("brief.md"),"dispatch_options_json":json!({"dispatch_brief":root.0.join("brief.md"),"brief_sha256":"old"}).to_string(),"execution_backend":"codex","timeout_seconds":600,"status":"failed","started_at":"fixture","allow_harness_self_modify":false,"resume_count":0,"cancel_requested":false})).unwrap();
    drop(registry);
    assert_eq!(run(&args(&["resume", "--job-id", "saved"]), &root), 1);
    let registry = JobRegistry::open(&db).unwrap();
    let count: i64 = registry
        .connection()
        .query_row(
            "SELECT resume_count FROM jobs WHERE job_id='saved'",
            [],
            |r| r.get(0),
        )
        .unwrap();
    assert_eq!(count, 0);
}

fn windows_path_only(command: &mut Command) {
    #[cfg(windows)]
    {
        let path = std::env::var_os("PATH").or_else(|| std::env::var_os("Path"));
        command.env_remove("MIR_EXECUTOR_PYTHON").env_remove("PATH");
        if let Some(path) = path {
            command.env("Path", path);
        }
    }
    #[cfg(not(windows))]
    let _ = command;
}
