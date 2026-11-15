use handoff_packet::{
    executor_command_hooks::{CommandHooks, TeardownOutcome},
    executor_hooks::{HookSession, HooksConfig},
    local_bridge::{BridgeConfig, BridgeError},
};
use serde_json::{Value, json};
use std::{
    fs,
    path::PathBuf,
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};
#[path = "../src/digest.rs"]
mod digest;

// Windows phase marks distinguish hashing/build/startup from operation time.
struct Timing(&'static str, Instant);
impl Timing {
    fn new(label: &'static str) -> Self {
        Self(label, Instant::now())
    }
}
impl Drop for Timing {
    fn drop(&mut self) {
        if cfg!(windows) || std::env::var_os("MIR_HOOK_TEST_TIMING").is_some() {
            eprintln!("timing {}: {:?}", self.0, self.1.elapsed());
        }
    }
}

struct Fixture {
    root: PathBuf,
    config: HooksConfig,
}
impl Fixture {
    fn new(mode: &str) -> Self {
        let _timing = Timing::new("fixture/setup");
        static NEXT: std::sync::atomic::AtomicUsize = std::sync::atomic::AtomicUsize::new(0);
        let base = std::env::var_os("MIR_NATIVE_TEST_SCRATCH")
            .map(PathBuf::from)
            .unwrap_or_else(std::env::temp_dir);
        let root = base.join(format!(
            "hooks-{}-{}",
            std::process::id(),
            NEXT.fetch_add(1, std::sync::atomic::Ordering::Relaxed)
        ));
        fs::create_dir_all(root.join("cwd")).unwrap();
        let name = format!("fixture{}", std::env::consts::EXE_SUFFIX);
        let example = fixture_binary();
        let copy_timing = Timing::new("fixture/copy");
        fs::copy(&example, root.join(&name))
            .expect("build fixture first: cargo build --offline --locked --example hook_fixture");
        drop(copy_timing);
        let hash_timing = Timing::new("fixture/hash");
        // This target builds the immutable fixture once; production still
        // verifies each copied executable independently.
        static SHA256: std::sync::OnceLock<String> = std::sync::OnceLock::new();
        let sha256 = SHA256
            .get_or_init(|| digest::sha256(&fs::read(&example).unwrap()))
            .clone();
        drop(hash_timing);
        let config = HooksConfig {
            executable: name,
            argv: vec![
                mode.into(),
                root.join("parent.pid").to_str().unwrap().into(),
                root.join("child.pid").to_str().unwrap().into(),
            ],
            sha256,
            hooks: vec!["writer_scope".into(), "on_job_event".into()],
        };
        Self { root, config }
    }
    fn start(&self) -> Result<HookSession, BridgeError> {
        let _timing = Timing::new("fixture/verify+spawn+hello");
        HookSession::start_with_timeout(
            &self.root,
            &self.root.join("cwd"),
            &self.config,
            Duration::from_secs(2),
        )
    }
}
impl Drop for Fixture {
    fn drop(&mut self) {
        let _timing = Timing::new("fixture/cleanup");
        let _ = fs::remove_dir_all(&self.root);
    }
}

#[test]
fn persistent_child_uses_exact_argv_cwd_and_request_ids() {
    let _timing = Timing::new("test/persistent_child_uses_exact_argv_cwd_and_request_ids");
    let f = Fixture::new("echo");
    let mut session = f.start().unwrap();
    assert!(session.serves("writer_scope"));
    assert!(!session.serves("other"));
    let a = session
        .call("on_job_event", json!({"text":"a; $(ignored)"}))
        .unwrap();
    let b = session
        .call("writer_scope", json!({"phase":"enter"}))
        .unwrap();
    assert_eq!(a["id"], 1);
    assert_eq!(b["id"], 2);
    assert_eq!(a["result"]["pid"], b["result"]["pid"]);
    assert_eq!(a["result"]["params"]["text"], "a; $(ignored)");
    assert_eq!(b["result"]["count"], 2);
    assert_eq!(
        fs::canonicalize(PathBuf::from(a["result"]["cwd"].as_str().unwrap())).unwrap(),
        fs::canonicalize(f.root.join("cwd")).unwrap()
    );
}
#[test]
fn pin_and_repository_path_are_checked_before_spawn() {
    let _timing = Timing::new("test/pin_and_repository_path_are_checked_before_spawn");
    for path in ["../fixture", "/absolute/fixture"] {
        let mut f = Fixture::new("echo");
        f.config.executable = path.into();
        assert!(f.start().is_err());
        assert!(!f.root.join("parent.pid").exists());
    }
    let mut f = Fixture::new("echo");
    f.config.sha256 = "0".repeat(64);
    assert!(f.start().is_err());
    assert!(!f.root.join("parent.pid").exists());
}
#[test]
fn hello_requires_version_and_exact_hook_set() {
    let _timing = Timing::new("test/hello_requires_version_and_exact_hook_set");
    for mode in ["bad-hello", "missing-hook", "extra-hook"] {
        let f = Fixture::new(mode);
        assert!(matches!(f.start(), Err(BridgeError::Protocol(_))), "{mode}");
    }
}
#[test]
fn faults_close_session_without_retry() {
    let _timing = Timing::new("test/faults_close_session_without_retry");
    for mode in [
        "wrong-id",
        "bad-version",
        "crash",
        "eof",
        "oversized",
        "depth",
        "nonfinite",
        "partial",
        "bad-error",
        "missing-result",
    ] {
        let f = Fixture::new(mode);
        let mut s = f.start().unwrap();
        assert!(s.call("on_job_event", json!({})).is_err(), "{mode}");
        assert!(
            matches!(s.call("on_job_event", json!({})), Err(BridgeError::Closed)),
            "{mode}"
        );
    }
}
#[test]
fn timeout_covers_hello_response_and_blocked_stdin() {
    let _timing = Timing::new("test/timeout_covers_hello_response_and_blocked_stdin");
    let f = Fixture::new("hello-hang");
    let t = Instant::now();
    assert!(matches!(f.start(), Err(BridgeError::Timeout)));
    let total = t.elapsed();
    // Executable verification and OS startup precede this fixture marker.
    let ready: u128 = fs::read_to_string(f.root.join("parent.ready"))
        .expect("hello-hang must mark transport readiness")
        .parse()
        .unwrap();
    let operation = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos()
        - ready;
    eprintln!(
        "hello-hang: startup+operation={total:?}, ready-to-return={}ms",
        operation / 1_000_000
    );
    assert!(operation < Duration::from_secs(4).as_nanos());
    // Total startup is diagnostic: slow verification/OS startup must not skip
    // the response and blocked-stdin deadline/error assertions below.
    for mode in ["hang", "blocked-stdin"] {
        let f = Fixture::new(mode);
        let mut s = f.start().unwrap();
        let t = Instant::now();
        assert!(
            matches!(
                s.call("writer_scope", json!({"data":"x".repeat(800_000)})),
                Err(BridgeError::Timeout)
            ),
            "{mode}"
        );
        assert!(t.elapsed() < Duration::from_secs(4));
        assert!(matches!(
            s.call("writer_scope", json!({})),
            Err(BridgeError::Closed)
        ));
    }
}
#[test]
fn request_size_depth_and_unserved_hook_are_rejected() {
    let _timing = Timing::new("test/request_size_depth_and_unserved_hook_are_rejected");
    let f = Fixture::new("echo");
    let mut s = f.start().unwrap();
    assert!(matches!(
        s.call("other", json!({})),
        Err(BridgeError::Protocol(_))
    ));
    let mut s = f.start().unwrap();
    assert!(matches!(
        s.call("writer_scope", json!({"data":"x".repeat(1_048_576)})),
        Err(BridgeError::FrameTooLarge)
    ));
    let mut s = f.start().unwrap();
    let mut value = Value::Null;
    for _ in 0..65 {
        value = json!([value]);
    }
    assert!(s.call("writer_scope", value).is_err());
}
#[test]
fn timeout_and_crash_reap_descendants_on_every_supported_platform() {
    let _timing =
        Timing::new("test/timeout_and_crash_reap_descendants_on_every_supported_platform");
    for mode in ["tree-hang", "tree-crash"] {
        let mut f = Fixture::new(mode);
        // Startup may exceed the transport timeout; it must precede the request.
        f.config.argv.push("2200".into());
        let mut s = f.start().unwrap();
        let ready = f.root.join("child.ready");
        let startup = Instant::now();
        loop {
            match fs::read(&ready) {
                Ok(bytes) if bytes == b"R" => break,
                Ok(bytes) => assert!(bytes.is_empty(), "invalid readiness: {bytes:?}"),
                Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
                Err(error) => panic!("{mode}: {}: {error:?}", ready.display()),
            }
            assert!(
                startup.elapsed() < Duration::from_secs(30),
                "{mode}: descendant readiness"
            );
            std::thread::sleep(Duration::from_millis(10));
        }
        let heartbeat = f.root.join("child.heartbeat");
        assert!(
            !fs::read(&heartbeat).unwrap_or_default().is_empty(),
            "{mode}: request must follow the descendant's first flushed heartbeat"
        );
        let t = Instant::now();
        assert!(s.call("on_job_event", json!({})).is_err());
        eprintln!("{mode}: operation+cleanup={:?}", t.elapsed());
        assert!(t.elapsed() < Duration::from_secs(4), "{mode}");
        std::thread::sleep(Duration::from_millis(100));
        let bytes = fs::read(&heartbeat).unwrap();
        assert!(!bytes.is_empty());
        std::thread::sleep(Duration::from_millis(200));
        assert_eq!(
            fs::read(&heartbeat).unwrap(),
            bytes,
            "{mode} left running descendant"
        );
    }
}

fn fixture_binary() -> PathBuf {
    static FIXTURE: std::sync::OnceLock<PathBuf> = std::sync::OnceLock::new();
    FIXTURE
        .get_or_init(|| {
            if let Some(path) = std::env::var_os("MIR_HOOK_FIXTURE") {
                return path.into();
            }
            let path = std::env::current_exe()
                .unwrap()
                .parent()
                .unwrap()
                .parent()
                .unwrap()
                .join("examples")
                .join(format!("hook_fixture{}", std::env::consts::EXE_SUFFIX));
            let _timing = Timing::new("fixture/build");
            let output = std::process::Command::new(env!("CARGO"))
                .args([
                    "build",
                    "--offline",
                    "--locked",
                    "--example",
                    "hook_fixture",
                ])
                .current_dir(env!("CARGO_MANIFEST_DIR"))
                .output()
                .unwrap();
            assert!(
                output.status.success(),
                "fixture build: {}",
                String::from_utf8_lossy(&output.stderr)
            );
            assert!(path.is_file(), "fixture path missing: {}", path.display());
            path
        })
        .clone()
}

#[test]
fn exact_one_mib_frames_include_the_newline() {
    let _timing = Timing::new("test/exact_one_mib_frames_include_the_newline");
    let f = Fixture::new("ack");
    let mut s = f.start().unwrap();
    let overhead = serde_json::to_vec(
        &json!({"version":"mir-executor.hooks@1","id":1,"hook":"on_job_event","params":""}),
    )
    .unwrap()
    .len();
    assert!(
        s.call("on_job_event", json!("x".repeat(1_048_576 - 1 - overhead)))
            .is_ok()
    );
    let f = Fixture::new("ack");
    let mut s = f.start().unwrap();
    assert!(matches!(
        s.call("on_job_event", json!("x".repeat(1_048_576 - overhead))),
        Err(BridgeError::FrameTooLarge)
    ));
    let f = Fixture::new("boundary");
    let mut s = f.start().unwrap();
    assert!(
        s.call("on_job_event", json!({})).unwrap()["result"]
            .as_str()
            .unwrap()
            .len()
            > 1_000_000
    );
}

#[test]
fn explicit_environment_and_writer_scope_pair_are_supported() {
    let _timing = Timing::new("test/explicit_environment_and_writer_scope_pair_are_supported");
    let f = Fixture::new("echo");
    let env =
        std::collections::BTreeMap::from([("MIR_HOOK_FIXTURE_ENV".into(), "forwarded".into())]);
    let mut s = HookSession::start_in_environment(
        &f.root,
        &f.root.join("cwd"),
        &f.config,
        &env,
        Duration::from_secs(2),
    )
    .unwrap();
    assert_eq!(
        s.call("writer_enter", json!({})).unwrap()["result"]["env"],
        "forwarded"
    );
    assert_eq!(
        s.call("writer_exit", json!({"token":"opaque","outcome":"clean"}))
            .unwrap()["result"]["count"],
        2
    );
}

fn command(f: &Fixture) -> CommandHooks {
    fs::create_dir_all(f.root.join("config")).unwrap();
    fs::write(f.root.join("config/mir-executor.local.json"),serde_json::to_vec(&json!({"native_policy":{"version":1,"hooks":{"executable":f.config.executable,"argv":f.config.argv,"sha256":f.config.sha256,"hooks":f.config.hooks}}})).unwrap()).unwrap();
    let environment = std::collections::BTreeMap::from([
        (
            "MIR_HOOK_FIXTURE_LOG".into(),
            f.root.join("requests.jsonl").into_os_string(),
        ),
        (
            "MIR_HOOK_FIXTURE_LEASE".into(),
            f.root.join("lease").into_os_string(),
        ),
    ]);
    CommandHooks::start_in(
        BridgeConfig {
            interpreter: f.root.join("unused-python"),
            target_root: f.root.clone(),
            bridge_script: f.root.join("unused-bridge.py"),
            environment,
            timeout: Duration::from_secs(2),
        },
        &f.root.join("cwd"),
    )
    .unwrap()
    .unwrap()
}

#[test]
fn writer_token_is_paired_with_clean_unclean_and_abandoned_teardown() {
    let _timing =
        Timing::new("test/writer_token_is_paired_with_clean_unclean_and_abandoned_teardown");
    for outcome in ["clean", "unclean", "uncertain"] {
        let mut f = Fixture::new("command");
        // The command fixture receives log and lease locations through its
        // explicit environment, so only the mode is needed in argv.
        f.config.argv.truncate(1);
        let mut hooks = command(&f);
        assert_eq!(
            hooks.call("writer_scope", vec![], json!({})).unwrap()["handle"],
            "native-writer"
        );
        hooks.call("writer_scope.enter", vec![], json!({})).unwrap();
        assert!(f.root.join("lease").is_file());
        hooks
            .call(
                "on_job_event",
                vec![
                    json!("job_inserted"),
                    json!({"job_id":"j","dispatch_id":"a"}),
                ],
                json!({}),
            )
            .unwrap();
        if outcome == "uncertain" {
            // Dropping an active token must override a previously set outcome.
            hooks.teardown_outcome(TeardownOutcome::Clean);
        } else {
            hooks.teardown_outcome(if outcome == "clean" {
                TeardownOutcome::Clean
            } else {
                TeardownOutcome::Unclean
            });
            hooks.call("writer_scope.exit", vec![], json!({})).unwrap();
        }
        drop(hooks);
        assert!(!f.root.join("lease").exists());
        let rows: Vec<Value> = fs::read_to_string(f.root.join("requests.jsonl"))
            .unwrap()
            .lines()
            .map(|line| serde_json::from_str(line).unwrap())
            .collect();
        assert_eq!(
            rows.iter()
                .map(|v| v["hook"].as_str().unwrap())
                .collect::<Vec<_>>(),
            vec!["writer_enter", "on_job_event", "writer_exit"]
        );
        assert_eq!(rows[2]["params"]["token"], "opaque");
        assert_eq!(rows[2]["params"]["outcome"], outcome);
        assert_eq!(
            rows[0]["params"]["invocation_id"],
            rows[2]["params"]["invocation_id"]
        );
        assert_eq!(rows[1]["params"]["job_id"], "j");
        assert_eq!(rows[1]["params"]["attempt_id"], "a");
    }
}

#[test]
fn writer_enter_requires_a_nonempty_opaque_token() {
    let _timing = Timing::new("test/writer_enter_requires_a_nonempty_opaque_token");
    let mut f = Fixture::new("command-missing-token");
    f.config.argv.truncate(1);
    let mut hooks = command(&f);
    assert!(matches!(
        hooks.call("writer_scope.enter", vec![], json!({})),
        Err(BridgeError::Protocol("writer_enter requires opaque token"))
    ));
}
