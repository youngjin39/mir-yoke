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

fn cross_root_resume(
    policy: Option<serde_json::Value>,
    family: Option<&str>,
    cwd_home: bool,
) -> (std::process::Output, Vec<u8>, Vec<u8>, bool) {
    let home = scratch();
    let target = scratch();
    for root in [&home.0, &target.0] {
        assert!(
            Command::new("git")
                .args(["init", "-q"])
                .arg(root)
                .status()
                .unwrap()
                .success()
        );
        fs::create_dir_all(root.join("config")).unwrap();
    }
    if let Some(policy) = policy {
        fs::write(
            home.0.join("config/mir-executor.local.json"),
            json!({"native_policy":policy}).to_string(),
        )
        .unwrap();
    }
    fs::write(
        target.0.join("config/mir-executor.local.json"),
        json!({"timeout_seconds_range":[1,2]}).to_string(),
    )
    .unwrap();
    let brief = target.0.join("brief.md");
    fs::write(&brief, "fixture").unwrap();
    let db = target.0.join("tasks/jobs.db");
    let registry = JobRegistry::open(&db).unwrap();
    registry.insert(&json!({"job_id":"saved","repo_root":target.0,"family":family,"change_id":"fixture","category":"unit","codex_args":["exec","fixture"],"dispatch_brief_path":brief,"dispatch_options_json":json!({"dispatch_brief":brief,"brief_sha256":"f16d05ec6b29248d2c61adb1e9263f78e4f7bace1b955014a2d17872cfe4064d"}).to_string(),"execution_backend":"codex","timeout_seconds":600,"status":"failed","started_at":"fixture","allow_harness_self_modify":false,"resume_count":0,"cancel_requested":false})).unwrap();
    drop(registry);
    let before = fs::read(&db).unwrap();
    let output = Command::new(env!("CARGO_BIN_EXE_executor-query"))
        .arg("--home-root")
        .arg(&home.0)
        .args(["resume", "--job-id", "saved", "--repo-root"])
        .arg(&target.0)
        .current_dir(if cwd_home { &home.0 } else { &target.0 })
        .env("MIR_EXECUTOR_OWNED_RECEIPT", home.0.join("receipt"))
        .output()
        .unwrap();
    let after = fs::read(&db).unwrap();
    let owned = home.0.join("receipt").exists();
    (output, before, after, owned)
}
fn family_authority() -> serde_json::Value {
    json!({"version":1,"target_admission":{"authorize_target":true,"family":{"mode":"reject","failure":{"kind":"ValueError","message":"family denied {family}"}}}})
}
#[test]
fn cross_root_resume_admitted_by_home_checks_target_configuration() {
    let (output, before, after, owned) = cross_root_resume(Some(family_authority()), None, false);
    assert_eq!(output.status.code(), Some(1));
    assert!(owned);
    let error = String::from_utf8(output.stderr).unwrap();
    assert!(error.contains("timeout"), "{error}");
    assert_eq!(before, after);
}
#[test]
fn cross_root_resume_home_repository_policy_refuses_before_registry_write() {
    let policy = json!({"version":1,"target_admission":{"authorize_target":true,"repository_local":{"kind":"ValueError","message":"local denied"}}});
    let (output, before, after, owned) = cross_root_resume(Some(policy), None, true);
    assert_eq!(output.status.code(), Some(1));
    assert!(owned);
    assert!(
        String::from_utf8(output.stderr)
            .unwrap()
            .contains("local denied")
    );
    assert_eq!(before, after);
}
#[test]
fn cross_root_resume_home_family_policy_refuses_before_registry_write() {
    let (output, before, after, owned) =
        cross_root_resume(Some(family_authority()), Some("saved-family"), false);
    assert_eq!(output.status.code(), Some(1));
    assert!(owned);
    assert!(
        String::from_utf8(output.stderr)
            .unwrap()
            .contains("family denied saved-family")
    );
    assert_eq!(before, after);
}
#[test]
fn cross_root_resume_without_home_policy_declines_without_ownership() {
    let (output, before, after, owned) = cross_root_resume(None, None, false);
    assert_eq!(output.status.code(), Some(64));
    assert!(!owned);
    assert!(output.stdout.is_empty());
    assert!(output.stderr.is_empty());
    assert_eq!(before, after);
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
