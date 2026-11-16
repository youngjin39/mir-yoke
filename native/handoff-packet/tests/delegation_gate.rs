use serde_json::{Value, json};
use std::{
    fs,
    io::Write,
    path::Path,
    process::{Command, Stdio},
    time::{Instant, SystemTime, UNIX_EPOCH},
};

fn remaining(path: &Path) {
    eprintln!("[gate-diag] inspect path={path:?}");
    match fs::read_dir(path) {
        Ok(entries) => {
            for entry in entries {
                match entry {
                    Ok(entry) => {
                        let kind = entry.file_type();
                        eprintln!(
                            "[gate-diag] remaining path={:?} type={kind:?}",
                            entry.path()
                        );
                        if kind.is_ok_and(|kind| kind.is_dir()) {
                            remaining(&entry.path());
                        }
                    }
                    Err(error) => eprintln!("[gate-diag] entry parent={path:?}: {error:?}"),
                }
            }
        }
        Err(error) => eprintln!("[gate-diag] read_dir path={path:?}: {error:?}"),
    }
}

#[cfg(windows)]
fn directory_users(path: &Path, capacity: usize) -> std::io::Result<Vec<usize>> {
    use std::os::windows::{fs::OpenOptionsExt, io::AsRawHandle};
    use windows_sys::{
        Wdk::Storage::FileSystem::{FileProcessIdsUsingFileInformation, NtQueryInformationFile},
        Win32::{Storage::FileSystem::*, System::IO::IO_STATUS_BLOCK},
    };
    let directory = fs::OpenOptions::new()
        .access_mode(FILE_READ_ATTRIBUTES)
        .share_mode(FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE)
        .custom_flags(FILE_FLAG_BACKUP_SEMANTICS)
        .open(path)?;
    // ULONG count followed by pointer-aligned ULONG_PTR process IDs. The
    // diagnostic's own runner PID is expected because of this scoped handle.
    let mut buffer = vec![0usize; capacity];
    let mut iosb = IO_STATUS_BLOCK::default();
    // SAFETY: valid synchronous handle, aligned initialized buffer, exact byte
    // capacity, live IO_STATUS_BLOCK; no pointers escape this call.
    let status = unsafe {
        NtQueryInformationFile(
            directory.as_raw_handle(),
            &mut iosb,
            buffer.as_mut_ptr().cast(),
            std::mem::size_of_val(buffer.as_slice()) as u32,
            FileProcessIdsUsingFileInformation,
        )
    };
    if status < 0 {
        return Err(std::io::Error::other(format!(
            "NtQueryInformationFile status={status:#x}"
        )));
    }
    let count = buffer.first().copied().unwrap_or_default() as u32 as usize;
    if count >= buffer.len() || iosb.Information < (count + 1) * size_of::<usize>() {
        return Err(std::io::Error::other("incomplete directory user list"));
    }
    Ok(buffer[1..count + 1].to_vec())
}

#[cfg(windows)]
#[test]
fn windows_directory_users() {
    use std::io::Read;
    if std::env::var("MIR_GATE_HOLDER").as_deref() == Ok("1") {
        std::io::stderr().write_all(b"R").unwrap();
        std::io::stdin().read_to_end(&mut Vec::new()).unwrap();
        return;
    }
    let base = std::env::var_os("MIR_NATIVE_TEST_SCRATCH")
        .map(std::path::PathBuf::from)
        .unwrap_or_else(std::env::temp_dir);
    let directory = tempfile::tempdir_in(base).unwrap();
    let mut child = Command::new(std::env::current_exe().unwrap())
        .args(["--exact", "windows_directory_users", "--nocapture"])
        .current_dir(directory.path())
        .env("HOME", directory.path())
        .env("MIR_GATE_HOLDER", "1")
        .stdin(Stdio::piped())
        .stdout(Stdio::null())
        .stderr(Stdio::piped())
        .spawn()
        .unwrap();
    let pid = child.id() as usize;
    let ready = child.stderr.take().unwrap().read_exact(&mut [0u8]);
    let close = fs::remove_dir(directory.path());
    let users = directory_users(directory.path(), 1024);
    let short = directory_users(directory.path(), 0);
    let missing = directory_users(&directory.path().join("absent"), 1024);
    drop(child.stdin.take());
    let status = child.wait().unwrap();
    drop(child);
    directory.close().unwrap();
    assert!(ready.is_ok() && status.success());
    assert_eq!(close.unwrap_err().raw_os_error(), Some(32));
    assert!(
        users.as_ref().is_ok_and(|users| users.contains(&pid)),
        "{users:?}"
    );
    assert!(
        short
            .unwrap_err()
            .to_string()
            .starts_with("NtQueryInformationFile status=")
    );
    assert_eq!(missing.unwrap_err().kind(), std::io::ErrorKind::NotFound);
}

#[test]
fn spawn_boundary_probe() {
    if std::env::var("MIR_GATE_DIAG").as_deref() != Ok("1") {
        return;
    }
    let start = Instant::now();
    for stream in ["stdin", "stdout", "stderr"] {
        eprintln!(
            "[gate-diag] probe=pipe stream={stream} stage=begin elapsed_us={}",
            start.elapsed().as_micros()
        );
        let pipe = std::io::pipe().unwrap();
        eprintln!(
            "[gate-diag] probe=pipe stream={stream} stage=done elapsed_us={}",
            start.elapsed().as_micros()
        );
        drop(pipe);
    }
    let base = std::env::var_os("MIR_NATIVE_TEST_SCRATCH")
        .map(std::path::PathBuf::from)
        .unwrap_or_else(std::env::temp_dir);
    let directory = tempfile::tempdir_in(base).unwrap();
    for piped in [false, true] {
        let stdio = || if piped { Stdio::piped() } else { Stdio::null() };
        let mut command = Command::new(env!("CARGO_BIN_EXE_delegation-gate"));
        command
            .arg("--mir-warmup")
            .current_dir(directory.path())
            .env("HOME", directory.path())
            .stdin(stdio())
            .stdout(stdio())
            .stderr(stdio());
        eprintln!(
            "[gate-diag] probe=warmup piped={piped} stage=spawn_call elapsed_us={} command={command:?}",
            start.elapsed().as_micros()
        );
        let child = command.spawn().unwrap();
        eprintln!(
            "[gate-diag] probe=warmup piped={piped} stage=spawn_done elapsed_us={} gate_pid={}",
            start.elapsed().as_micros(),
            child.id()
        );
        assert!(child.wait_with_output().unwrap().status.success());
    }
    directory.close().unwrap();
}

#[test]
fn diagnostic_opt_in() {
    let cases: Vec<Value> =
        serde_json::from_str(include_str!("fixtures/delegation-gate.json")).unwrap();
    for enabled in [false, true] {
        let mut command = Command::new(std::env::current_exe().unwrap());
        command
            .args(["--exact", "decision_fixtures", "--nocapture"])
            .env_remove("MIR_GATE_DIAG");
        if enabled {
            command.env("MIR_GATE_DIAG", "1");
        }
        let output = command.output().unwrap();
        assert!(output.status.success(), "{output:?}");
        let log = String::from_utf8(output.stderr).unwrap();
        for stage in [
            "spawn_begin",
            "command_ready",
            "spawn_call",
            "spawn_done",
            "stdin_closed",
            "wait_done",
            "close_begin",
            "close_done",
        ] {
            assert_eq!(
                log.matches(&format!("stage={stage} ")).count(),
                if enabled { cases.len() } else { 0 },
                "stage={stage}, enabled={enabled}: {log}"
            );
        }
    }
}

#[test]
fn decision_fixtures() {
    let cases: Vec<Value> =
        serde_json::from_str(include_str!("fixtures/delegation-gate.json")).unwrap();
    for case in &cases {
        let base = std::env::var_os("MIR_NATIVE_TEST_SCRATCH")
            .map(std::path::PathBuf::from)
            .unwrap_or_else(std::env::temp_dir);
        let directory = tempfile::Builder::new()
            .prefix("delegation-gate-")
            .tempdir_in(base)
            .unwrap();
        let root = directory.path();
        let diagnostic_root = root.to_owned();
        let start = Instant::now();
        let diag = |stage: &str, detail: &str| {
            if std::env::var("MIR_GATE_DIAG").as_deref() == Ok("1") {
                eprintln!(
                    "[gate-diag] case={} stage={stage} unix_ms={:?} elapsed_us={} root={diagnostic_root:?} runner_pid={} cwd={:?} {detail}",
                    case["name"],
                    SystemTime::now()
                        .duration_since(UNIX_EPOCH)
                        .map(|d| d.as_millis()),
                    start.elapsed().as_micros(),
                    std::process::id(),
                    std::env::current_dir()
                );
            }
        };
        fs::create_dir_all(root.join("config")).unwrap();
        let mode = &case["mode"];
        let source = case["source"].as_str().unwrap_or("lock");
        if !mode.is_null() && case["no_policy"] != true {
            let (file, data) = match source {
                "local" => ("sub-agent-policy.json", json!({"delegation":{"mode":mode}})),
                "flat" => ("sub-agent-policy.json", json!({"mode":mode})),
                _ => (
                    "model-routing.lock.json",
                    json!({"policy":{"delegation":{"mode":mode}}}),
                ),
            };
            fs::write(root.join("config").join(file), data.to_string()).unwrap();
        }
        if let Some(local) = case.get("local_mode") {
            fs::write(
                root.join("config/sub-agent-policy.json"),
                json!({"mode":local}).to_string(),
            )
            .unwrap();
        }
        if let Some(raw) = case["raw_policy"].as_str() {
            fs::write(root.join("config/model-routing.lock.json"), raw).unwrap();
        }
        let lock = root.join("config/model-routing.lock.json");
        if case["broken_policy"] == true {
            fs::remove_file(&lock).unwrap();
        }
        if case["directory_lock"] == true {
            fs::remove_file(&lock).unwrap();
            fs::create_dir(&lock).unwrap();
        }
        let overlay = root.join("overlay.json");
        if let Some(data) = case.get("overlay") {
            fs::write(&overlay, data.to_string()).unwrap();
        }
        if let Some(raw) = case["raw_overlay"].as_str() {
            fs::write(&overlay, raw).unwrap();
        }
        diag("spawn_begin", "grandchildren=none_by_source_audit");
        let mut command = Command::new(env!("CARGO_BIN_EXE_delegation-gate"));
        command
            .current_dir(root)
            .env("HOME", root)
            .env_remove("CLAUDE_PROJECT_DIR")
            .env("MIR_SUB_AGENT_POLICY", &overlay)
            .env("MIR_R3_FALLBACK", case["r3"].as_str().unwrap_or("0"))
            .env(
                "MIR_CODEX_MAIN",
                if case["main"] == true { "1" } else { "0" },
            )
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped());
        diag(
            "command_ready",
            &format!(
                "program={:?} argv={:?} child_cwd={:?}",
                command.get_program(),
                command.get_args().collect::<Vec<_>>(),
                command.get_current_dir()
            ),
        );
        diag("spawn_call", "stdio=piped,piped,piped");
        let mut child = command.spawn().unwrap();
        let gate_pid = child.id();
        diag("spawn_done", &format!("gate_pid={gate_pid}"));
        let input = case["raw"]
            .as_str()
            .map(str::to_owned)
            .unwrap_or_else(|| case["payload"].to_string());
        child
            .stdin
            .take()
            .unwrap()
            .write_all(input.as_bytes())
            .unwrap();
        diag("stdin_closed", &format!("gate_pid={gate_pid}"));
        let output = child.wait_with_output().unwrap();
        diag(
            "wait_done",
            &format!("gate_pid={gate_pid} status={:?}", output.status),
        );
        assert_eq!(
            output.status.code(),
            Some(case["code"].as_i64().unwrap() as i32),
            "{}: {:?}",
            case["name"],
            output
        );
        assert!(output.stdout.is_empty());
        let error = String::from_utf8(output.stderr).unwrap();
        if let Some(hint) = case["expected_hint"].as_str() {
            assert!(error.contains(hint), "{error}");
        }
        if case["advisory"] == true {
            assert_eq!(
                error,
                "[mir ADVISORY] force_codex Agent/Task escape via MIR_R3_FALLBACK=1\n"
            );
        } else if case["code"] == 0 {
            assert!(error.is_empty(), "{error}");
        } else if case["malformed"] == true {
            assert!(error.contains("Malformed PreToolUse payload"), "{error}");
        } else {
            assert!(error.starts_with("[mir BLOCKED]"), "{error}");
        }
        // wait_with_output consumes Child and closes its handles before cleanup.
        // Preserve the exact OS error and remaining entries; do not retry away
        // a sharing violation or attribute it to an unobserved external holder.
        let path = root.to_owned();
        diag(
            "close_begin",
            &format!("gate_pid={gate_pid} operation=TempDir.close/remove_dir_all"),
        );
        directory.close().unwrap_or_else(|error| {
            diag(
                "close_error",
                &format!("gate_pid={gate_pid} error={error:?} ({error})"),
            );
            if std::env::var("MIR_GATE_DIAG").as_deref() == Ok("1") {
                #[cfg(windows)]
                eprintln!("[gate-diag] directory_users root={path:?} runner_pid={} gate_pid={gate_pid} result={:?}", std::process::id(), directory_users(&path, 1024));
                remaining(&path);
            }
            panic!(
                "cleanup case={} root={} runner_pid={} gate_pid={} cwd={:?}: {error:?} ({error})",
                case["name"],
                path.display(),
                std::process::id(),
                gate_pid,
                std::env::current_dir()
            );
        });
        diag("close_done", &format!("gate_pid={gate_pid}"));
    }
}
