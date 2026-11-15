//! Status owns every argument shape before touching its synthetic registry.
use std::{fs, path::PathBuf, process::Command};

#[cfg(windows)]
#[path = "support/executor_text.rs"]
mod executor_text;

fn root() -> PathBuf {
    static NEXT: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);
    let base = std::env::var_os("MIR_NATIVE_TEST_SCRATCH")
        .map(PathBuf::from)
        .unwrap_or_else(|| {
            PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("target/mig-scratch/D04a-status")
        });
    let root = base.join(format!(
        "owned-status-{}-{}",
        std::process::id(),
        NEXT.fetch_add(1, std::sync::atomic::Ordering::Relaxed)
    ));
    fs::create_dir_all(&root).unwrap();
    fs::canonicalize(root).unwrap()
}

#[test]
fn status_source_has_no_decline_or_python_command_forwarding() {
    let source = include_str!("../src/executor_status.rs");
    assert!(!source.contains("executor_protocol::decline"));
    assert!(!source.contains("tools.mir_executor.cli"));
    assert!(!source.contains("cli_jobs"));
    assert!(!source.contains("Command::new"));
    assert!(!source.contains("LocalBridge"));
    let entry = include_str!("../src/executor_query.rs");
    assert!(
        entry.find("executor_status::owns").unwrap()
            < entry.find("parse(std::env::args_os()").unwrap()
    );
}

#[test]
fn status_shared_json_codepoints_preserve_surrogates() {
    let ordinary = "[1, {\"text\": \"hello\"}]";
    assert_eq!(
        handoff_packet::python_json::parse(ordinary).unwrap(),
        handoff_packet::python_json::parse_codepoints(ordinary.chars().map(u32::from).collect())
            .unwrap()
    );
    let value = handoff_packet::python_json::parse_codepoints(vec![34, 0xd800, 34]).unwrap();
    assert_eq!(value.repr(), "'\\ud800'");
}

#[test]
fn status_extended_parser_shapes_never_decline() {
    let root = root();
    let cases = vec![
        (
            vec![
                "--repo-root".to_owned(),
                root.to_string_lossy().into_owned(),
                "status".into(),
                "--job-id=fixture".into(),
            ],
            2,
            b"usage: python -m tools.mir_executor [--jobs-db PATH]".as_slice(),
        ),
        (
            vec!["--".into(), "status".into(), "--job-id=absent".into()],
            1,
            b"".as_slice(),
        ),
        (
            vec![
                "status".into(),
                "--job-id=fixture".into(),
                "--help=ignored".into(),
            ],
            2,
            b"usage: python -m tools.mir_executor status [-h]".as_slice(),
        ),
        (
            vec!["status".into(), "--job-id=fixture".into(), "-hfoo".into()],
            0,
            b"".as_slice(),
        ),
    ];
    for (args, code, prefix) in cases {
        let output = Command::new(env!("CARGO_BIN_EXE_executor-query"))
            .arg("--home-root")
            .arg(&root)
            .args(&args)
            .current_dir(&root)
            .env("HOME", &root)
            .output()
            .unwrap();
        assert_eq!(
            output.status.code(),
            Some(code),
            "{args:?}: {}",
            String::from_utf8_lossy(&output.stderr)
        );
        assert!(
            output.stderr.starts_with(prefix),
            "{}",
            String::from_utf8_lossy(&output.stderr)
        );
    }
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn status_blob_json_decode_errors_count_the_bom() {
    let root = root();
    let registry =
        handoff_packet::executor_registry::JobRegistry::open(&root.join("jobs.db")).unwrap();
    registry.connection().execute("INSERT INTO jobs (job_id,change_id,category,repo_root,codex_args,timeout_seconds,status,started_at) VALUES ('fixture','c','unit','r',?,1,'running','')",[vec![0xffu8,0xfe,0,0,0,0,0x11,0]]).unwrap();
    drop(registry);
    let output = Command::new(env!("CARGO_BIN_EXE_executor-query"))
        .arg("--home-root")
        .arg(&root)
        .args(["--jobs-db=jobs.db", "status", "--job-id=fixture"])
        .current_dir(&root)
        .env("HOME", &root)
        .output()
        .unwrap();
    assert_eq!(output.status.code(), Some(1));
    assert_eq!(output.stderr,b"UnicodeDecodeError: 'utf-32-le' codec can't decode bytes in position 4-7: code point not in range(0x110000)\n");
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn status_legacy_hooks_require_the_facade_without_launching_children() {
    let root = root();
    let home = root.join("home");
    let package = home.join("tools/mir_executor");
    fs::create_dir_all(&package).unwrap();
    fs::write(
        package.join("local.py"),
        "raise AssertionError('must not import')\n",
    )
    .unwrap();
    for option in [None, Some("--help"), Some("--unknown")] {
        let output = Command::new(env!("CARGO_BIN_EXE_executor-query"))
            .arg("--home-root")
            .arg(&home)
            .args(["status", "--job-id=missing"])
            .args(option)
            .current_dir(&home)
            .env("HOME", &root)
            .env("PATH", "")
            .output()
            .unwrap();
        assert_eq!(output.status.code(), Some(2));
        assert!(output.stdout.is_empty());
        assert_eq!(
            output.stderr,
            // WT-TEXT pass 2 authorizes the native-only text-stream contract.
            "[mir_executor] legacy status hooks require the Python facade\n"
                .replace('\n', if cfg!(windows) { "\r\n" } else { "\n" })
                .as_bytes(),
            "legacy stderr bytes, option={option:?}"
        );
    }
    assert!(!home.join("tasks/jobs.db").exists());
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn status_abbreviated_repeated_options_and_missing_parent_are_owned() {
    let root = root();
    let output = Command::new(env!("CARGO_BIN_EXE_executor-query"))
        .args(["--home-root"])
        .arg(&root)
        .args([
            "--jobs-d",
            "missing/../jobs.db",
            "status",
            "--job-i=first",
            "--job-id=last",
        ])
        .current_dir(&root)
        .env("HOME", &root)
        .output()
        .unwrap();
    assert_eq!(output.status.code(), Some(1));
    assert!(output.stdout.is_empty());
    assert_eq!(output.stderr, b"[mir_executor] job_id not found: 'last'\n");
    assert!(root.join("jobs.db").is_file());
    assert!(!root.join("missing").exists());
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn status_parser_errors_are_owned_without_registry_effects() {
    let root = root().join("parser");
    fs::create_dir_all(&root).unwrap();
    let output = Command::new(env!("CARGO_BIN_EXE_executor-query"))
        .arg("--home-root")
        .arg(&root)
        .args(["status", "--job-id"])
        .current_dir(&root)
        .env("HOME", &root)
        .output()
        .unwrap();
    assert_eq!(output.status.code(), Some(2));
    assert!(output.stdout.is_empty());
    #[cfg(windows)]
    {
        let record = executor_text::record("parser", "");
        assert_eq!(
            output.status.code(),
            record["exit"].as_i64().map(|v| v as i32)
        );
        assert_eq!(
            output.stdout,
            executor_text::bytes(&record, "stdout"),
            "parser stdout bytes"
        );
        assert_eq!(
            output.stderr,
            executor_text::bytes(&record, "stderr"),
            "parser stderr bytes"
        );
    }
    #[cfg(not(windows))]
    assert_eq!(output.stderr, b"usage: python -m tools.mir_executor status --job-id JOB_ID [--repo-root PATH]\npython -m tools.mir_executor status: error: argument --job-id: expected one argument\n", "parser stderr bytes");
    assert!(!root.join("tasks/jobs.db").exists());
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn status_does_not_create_mutation_receipts() {
    let root = root();
    fs::create_dir(root.join("tasks")).unwrap();
    let receipt = root.join("tasks/status-receipt");
    let output = Command::new(env!("CARGO_BIN_EXE_executor-query"))
        .arg("--home-root")
        .arg(&root)
        .args(["status", "--job-id=missing"])
        .current_dir(&root)
        .env("HOME", &root)
        .env("MIR_EXECUTOR_OWNED_RECEIPT", &receipt)
        .output()
        .unwrap();
    assert_eq!(output.status.code(), Some(1));
    assert!(!receipt.exists());
    fs::remove_dir_all(root).unwrap();
}
