//! Replay unmodified Yoke references; no interpreter or live Git repository.
use serde_json::{Value, json};
use std::{fs, path::Path, process::Command};
#[path = "support/fake_git.rs"]
mod fake_git;

fn snapshot(root: &Path) -> Value {
    fn walk(root: &Path, dir: &Path, out: &mut serde_json::Map<String, Value>) {
        for entry in fs::read_dir(dir).unwrap() {
            let path = entry.unwrap().path();
            if path.is_dir() {
                out.insert(
                    format!("{}/", path.strip_prefix(root).unwrap().display()),
                    json!("directory"),
                );
                walk(root, &path, out);
            } else {
                out.insert(
                    path.strip_prefix(root).unwrap().to_str().unwrap().into(),
                    json!(fs::read(&path).unwrap()),
                );
            }
        }
    }
    let mut out = serde_json::Map::new();
    walk(root, root, &mut out);
    Value::Object(out)
}
fn replay_fixture(fixture: &Value, mode: &str) -> (usize, usize) {
    let started = std::time::Instant::now();
    let mut setup_time = std::time::Duration::ZERO;
    let mut hook_time = std::time::Duration::ZERO;
    let tools = tempfile::tempdir().unwrap();
    let mut count = 0;
    let mut skipped_git_mode = 0;
    for record in fixture["records"]
        .as_array()
        .unwrap()
        .iter()
        .filter(|r| r["mode"] == mode)
    {
        let non_executable_git = record["git_mode"].as_u64().unwrap_or(0o755) != 0o755;
        // The permission-refusal record models POSIX executable bits.
        if non_executable_git && !cfg!(unix) {
            skipped_git_mode += 1;
            continue;
        }
        // The permission-refusal record must not alter the shared executable.
        let private_tools = non_executable_git.then(|| tempfile::tempdir().unwrap());
        let tools = private_tools.as_ref().unwrap_or(&tools);
        let record_started = std::time::Instant::now();
        let setup_started = std::time::Instant::now();
        let dir = tempfile::tempdir().unwrap();
        // Records were captured under a non-symlinked root; macOS temp dirs are symlinked.
        let root_buf = fs::canonicalize(dir.path()).unwrap();
        let root = root_buf.as_path();
        let expand = |s: &str| s.replace("@PROJECT@", root.to_str().unwrap());
        for (name, body) in record["setup"].as_object().unwrap() {
            let path = root.join(name);
            fs::create_dir_all(path.parent().unwrap()).unwrap();
            fs::write(path, expand(body.as_str().unwrap())).unwrap();
        }
        let mut cmd = Command::new(env!("CARGO_BIN_EXE_project-hooks"));
        cmd.current_dir(root).env("CLAUDE_PROJECT_DIR", root);
        cmd.env("HOME", root)
            .env("USERPROFILE", root)
            .env("PATH", tools.path());
        if non_executable_git {
            #[cfg(unix)]
            {
                use std::os::unix::fs::PermissionsExt;
                let git = tools.path().join("git");
                fs::write(&git, "#!/bin/sh\n").unwrap();
                fs::set_permissions(&git, fs::Permissions::from_mode(0o644)).unwrap();
            }
        } else {
            let mode = match record["id"].as_str().unwrap() {
                "precommit-merge-git-invalid-stdout" => "invalid-stdout",
                "precommit-merge-git-invalid-stderr" => "invalid-stderr",
                "precommit-merge-git-timeout" => "timeout",
                _ => "changed",
            };
            fake_git::install(
                tools.path(),
                &mut cmd,
                record["changed"].as_str().unwrap(),
                mode,
            );
        }
        // The executable and controlled PATH exist before launching the hook.
        setup_time += setup_started.elapsed();
        let hook_started = std::time::Instant::now();
        run(&mut cmd, record, mode, &expand, root);
        let elapsed = hook_started.elapsed();
        hook_time += elapsed;
        let cleanup_started = std::time::Instant::now();
        drop(dir);
        drop(private_tools);
        eprintln!(
            "timing {}: setup={:?}, hook={elapsed:?}, cleanup={:?}, elapsed={:?}",
            record["id"],
            hook_started.duration_since(setup_started),
            cleanup_started.elapsed(),
            record_started.elapsed()
        );
        count += 1;
    }
    eprintln!(
        "timing fixture replay {mode}: {count} records, {skipped_git_mode} git_mode skips, setup={setup_time:?}, hooks={hook_time:?}, total={:?}",
        started.elapsed()
    );
    (count, skipped_git_mode)
}
fn replay(mode: &str) {
    let fixture: Value = serde_json::from_str(include_str!("fixtures/w1/tdd-ledger.json")).unwrap();
    let expected = match mode {
        "prewrite" => 53,
        "precommit" => 27,
        "precommit-merge" => 13,
        "tdd-guard" => 150,
        _ => panic!("unknown fixture mode"),
    };
    assert_eq!(replay_fixture(&fixture, mode), (expected, 0));
}
fn run(cmd: &mut Command, r: &Value, mode: &str, expand: &impl Fn(&str) -> String, root: &Path) {
    if mode == "tdd-guard" {
        cmd.args(["tdd-guard", &expand(r["target"].as_str().unwrap())]);
    } else {
        cmd.arg("tdd-matrix");
        if let Some(args) = r["args"].as_array() {
            for arg in args {
                let arg = arg.as_str().unwrap();
                if arg == "@PROJECT@/changed" {
                    cmd.arg(root.join("changed"));
                } else {
                    cmd.arg(expand(arg));
                }
            }
        } else {
            cmd.args(
                [
                    mode,
                    root.to_str().unwrap(),
                    if mode == "precommit" {
                        "changed"
                    } else {
                        r["target"].as_str().unwrap()
                    },
                ]
                .map(expand),
            );
        }
    }
    let before = snapshot(root);
    let started = std::time::Instant::now();
    let result = cmd.output().unwrap();
    eprintln!("timing child {}: elapsed={:?}", r["id"], started.elapsed());
    assert_eq!(snapshot(root), before, "filesystem: {}", r["id"]);
    let normalize = |b: Vec<u8>| {
        String::from_utf8(b)
            .unwrap()
            .replace(root.to_str().unwrap(), "@PROJECT@")
    };
    let observed = json!({"exit":result.status.code(),"stdout":normalize(result.stdout),"stderr":normalize(result.stderr),"delta":{},"deleted":[]});
    if r["id"] == "guard-helper-missing" {
        // Retired branch: the Python helper is no longer consulted, so the
        // in-process ledger decides and the guard stays advisory.
        assert_eq!(observed["exit"], 0);
        assert!(
            !observed["stderr"]
                .as_str()
                .unwrap()
                .contains("Missing helper")
        );
        return;
    }
    if r["id"] == "guard-valid" {
        // Captured where the retired interpreter route was unavailable, so the
        // reference warned; the native ledger accepts the valid entry.
        assert_eq!(observed["exit"], 0);
        assert_eq!(observed["stderr"], "");
        return;
    }
    let mut expected = r["expected"].clone();
    if cfg!(windows) {
        if r["id"]
            .as_str()
            .and_then(|id| id.split_once("-metadata-depth-"))
            .and_then(|(_, depth)| depth.parse::<usize>().ok())
            .is_some_and(|depth| depth >= 2997)
        {
            let capture: Value =
                serde_json::from_str(include_str!("fixtures/windows-deep.json")).unwrap();
            let reference = &capture["boundaries"][1]["first_changed"]["reference"];
            expected["exit"] = reference["code"].clone();
            expected["stderr"] = json!(format!(
                "{}\n",
                reference["final_exception"].as_str().unwrap()
            ));
        }
        if mode != "tdd-guard" {
            for field in ["stdout", "stderr"] {
                expected[field] = json!(expected[field].as_str().unwrap().replace('\n', "\r\n"));
            }
        }
    }
    assert_eq!(observed, expected, "{}", r["id"]);
}
#[test]
fn matrix_prewrite() {
    replay("prewrite");
}
#[test]
fn w5_pinned_retirement_replay() {
    let fixture: Value = serde_json::from_str(include_str!("fixtures/w5-tdd.json")).unwrap();
    assert_eq!(
        fixture["oracle"],
        "abb0dd82:.claude/hooks/tdd-matrix-guard.py"
    );
    let mut count = 0;
    let mut skipped_git_mode = 0;
    for mode in ["prewrite", "precommit", "precommit-merge"] {
        let (replayed, skipped) = replay_fixture(&fixture, mode);
        count += replayed;
        skipped_git_mode += skipped;
    }
    assert_eq!(
        (count, skipped_git_mode),
        if cfg!(unix) { (196, 0) } else { (195, 1) }
    );
}
#[test]
fn matrix_precommit_first_match() {
    replay("precommit");
}
#[test]
fn matrix_merge_unused() {
    replay("precommit-merge");
}

#[cfg(unix)]
fn inherited_git_pipe_times_out(redirect: &str) {
    use std::os::unix::fs::PermissionsExt;
    use std::time::{Duration, Instant};

    let project = tempfile::tempdir().unwrap();
    let root = project.path();
    fs::create_dir(root.join("tasks")).unwrap();
    fs::write(
        root.join("tasks/tdd.json"),
        r#"{"changes":[{"id":"fallback","targets":["src/example.py"],"categories":{"unit":{"status":"planned"}}}]}"#,
    )
    .unwrap();

    let git = root.join("git");
    fs::write(
        &git,
        format!(
            r#"#!/bin/sh
case "$3" in
  '@{{upstream}}..HEAD')
    (
      closed() {{ : > pipe-closed; exit 0; }}
      trap closed PIPE
      n=0
      while [ "$n" -lt 160 ]; do
        printf '.' || closed
        /bin/sleep 0.1
        n=$((n + 1))
      done
    ) {redirect} &
    printf '%s\n' "$!" > descendant.pid
    exit 0 ;;
  'origin/main..HEAD')
    n=0
    while [ ! -f pipe-closed ] && [ "$n" -lt 10 ]; do
      /bin/sleep 0.1
      n=$((n + 1))
    done
    [ -f pipe-closed ] || exit 1
    printf '%s\n' src/example.py ;;
  *) exit 1 ;;
esac
"#
        ),
    )
    .unwrap();
    fs::set_permissions(&git, fs::Permissions::from_mode(0o755)).unwrap();

    let started = Instant::now();
    let output = Command::new(env!("CARGO_BIN_EXE_project-hooks"))
        .args(["tdd-matrix", "precommit-merge"])
        .arg(root)
        .current_dir(root)
        .env("PATH", root)
        .output()
        .unwrap();
    let elapsed = started.elapsed();
    let saw_close = root.join("pipe-closed").exists();
    // A detached reader keeps the descendant alive even after Git falls back.
    if !saw_close && elapsed < Duration::from_secs(14) {
        let pid = fs::read_to_string(root.join("descendant.pid")).unwrap();
        assert!(
            Command::new("/bin/kill")
                .args(["-KILL", pid.trim()])
                .status()
                .unwrap()
                .success()
        );
    }
    assert!(
        elapsed < Duration::from_secs(14),
        "capture took {elapsed:?}"
    );
    assert!(saw_close, "Git fallback did not close the inherited pipe");
    assert_eq!(output.status.code(), Some(2));
    assert!(
        String::from_utf8(output.stderr)
            .unwrap()
            .contains("fallback: unit.status='planned'")
    );
}

#[cfg(unix)]
#[test]
fn matrix_merge_git_timeout_includes_inherited_stdout() {
    inherited_git_pipe_times_out("2>/dev/null");
}

#[cfg(unix)]
#[test]
fn matrix_merge_git_timeout_includes_inherited_stderr() {
    inherited_git_pipe_times_out("1>&2");
}

#[test]
fn guard_always_advisory() {
    replay("tdd-guard");
}

#[test]
fn compatibility_y2_evidence_strip() {
    compatibility(|id| id.contains("-reason-") || id.contains("-command-"));
}
#[test]
fn compatibility_y3_exception_paths() {
    compatibility(|id| {
        !id.contains("-reason-")
            && !id.contains("-command-")
            && !id.contains("-strip-")
            && !id.contains("-metadata-")
            && !id.contains("-json-")
            && !id.contains("-splitlines-")
    });
}
#[test]
fn compatibility_y4_target_normalization() {
    compatibility(|id| {
        id.contains("-target-strip-")
            || id.contains("-argument-strip-")
            || id.contains("-splitlines-")
    });
}
#[test]
fn compatibility_y5_json_admission() {
    compatibility(|id| id.contains("-metadata-") || id.contains("-json-"));
}
fn compatibility(select: impl Fn(&str) -> bool) {
    let mut fixture: Value =
        serde_json::from_str(include_str!("fixtures/tdd-compat.json")).unwrap();
    fixture["records"]
        .as_array_mut()
        .unwrap()
        .retain(|r| select(r["id"].as_str().unwrap()));
    assert!(!fixture["records"].as_array().unwrap().is_empty());
    for mode in ["prewrite", "precommit", "precommit-merge"] {
        replay_fixture(&fixture, mode);
    }
}

#[test]
fn native_fake_git_owns_child_path_and_preserves_bytes() {
    let tools = tempfile::tempdir().unwrap();
    let home = tempfile::tempdir().unwrap();
    for (mode, stdout, stderr, code) in [
        (
            "changed",
            b"src/a.rs\nsrc/space name.rs\n".as_slice(),
            b"".as_slice(),
            0,
        ),
        ("invalid-stdout", &[255], &[], 0),
        ("invalid-stderr", &[], &[255], 0),
        ("refusal", &[], b"fixture git refusal\n", 128),
    ] {
        let mut command = Command::new("git");
        command
            .current_dir(home.path())
            .env("HOME", home.path())
            .env("USERPROFILE", home.path());
        command.env("PATH", "must never be inherited");
        fake_git::install(
            tools.path(),
            &mut command,
            "src/a.rs\nsrc/space name.rs\n",
            mode,
        );
        let result = command
            .args(["diff", "--name-only", "HEAD"])
            .output()
            .unwrap();
        assert_eq!(result.stdout, stdout, "{mode}: stdout");
        assert_eq!(result.stderr, stderr, "{mode}: stderr");
        assert_eq!(result.status.code(), Some(code), "{mode}: exit");
    }
}

#[test]
fn native_fake_git_reuses_executable_without_rewriting() {
    let tools = tempfile::tempdir().unwrap();
    let mut command = Command::new("git");
    fake_git::install(tools.path(), &mut command, "first", "changed");
    let executable = tools
        .path()
        .join(format!("git{}", std::env::consts::EXE_SUFFIX));
    let stamp = std::time::SystemTime::UNIX_EPOCH + std::time::Duration::from_secs(86400);
    fs::File::options()
        .write(true)
        .open(&executable)
        .unwrap()
        .set_times(fs::FileTimes::new().set_modified(stamp))
        .unwrap();
    fake_git::install(tools.path(), &mut command, "second", "refusal");
    assert_eq!(fs::metadata(executable).unwrap().modified().unwrap(), stamp);
}
