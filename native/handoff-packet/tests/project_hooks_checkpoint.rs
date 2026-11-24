//! Exact immutable full-effect replay, implemented entirely in Rust.
#![cfg(unix)]
use frozen::executable;
#[path = "support/replay.rs"]
mod frozen;

#[test]
fn checkpoint_frozen_records() {
    for prefix in ["", "templates/common-harness/"] {
        frozen::replay(&format!("{prefix}.claude/hooks/pre-compact.sh"), 9);
        frozen::replay(&format!("{prefix}.claude/hooks/_lib/invocation_log.sh"), 3);
    }
    frozen::replay(".claude/hooks/session-end.sh", 2);
}

#[test]
fn git_status_and_checkpoint_permissions() {
    use std::{fs, os::unix::fs::PermissionsExt};
    let dir = tempfile::tempdir().unwrap();
    let root = dir.path();
    let mut command = frozen::prepare(root);
    executable::write(root.join("tools/git"), "#!/bin/sh\nprintf '%s\\n' \"$*\" >> \"$HOME/git-calls\"\ncase \"$3\" in rev-parse) exit 0 ;; status) printf ' M a\\n?? b\\n' ;; esac\n").unwrap();
    let target = root.join("project/tasks/handoffs/session-handoff-LATEST.md");
    fs::create_dir_all(target.parent().unwrap()).unwrap();
    fs::write(&target, "curated\n").unwrap();
    fs::set_permissions(&target, fs::Permissions::from_mode(0o640)).unwrap();
    let result = command.arg("pre-compact").output().unwrap();
    assert!(result.status.success());
    assert_eq!(
        fs::metadata(&target).unwrap().permissions().mode() & 0o777,
        0o600
    );
    assert!(
        fs::read_to_string(&target)
            .unwrap()
            .contains("Working tree dirty (2 paths;")
    );
    let project = root.join("project");
    assert_eq!(
        fs::read_to_string(root.join("home/git-calls")).unwrap(),
        format!(
            "-C {} rev-parse --is-inside-work-tree\n-C {} status --short --untracked-files=all\n",
            project.display(),
            project.display()
        )
    );
    fs::set_permissions(target.parent().unwrap(), fs::Permissions::from_mode(0o555)).unwrap();
    let result = command.output().unwrap();
    fs::set_permissions(target.parent().unwrap(), fs::Permissions::from_mode(0o755)).unwrap();
    assert!(result.status.success());
    assert!(String::from_utf8_lossy(&result.stdout).contains("ERROR: Failed to refresh"));
    assert!(fs::read_to_string(target).unwrap().starts_with("curated\n"));
}

#[test]
fn slow_git_is_killed_and_reaped_within_collection_budget() {
    use std::{
        fs,
        process::Command,
        time::{Duration, Instant},
    };
    // Exercise expiry in either Git command. exec keeps the recorded PID as the
    // sleeping Git child itself; a surviving process would fail kill -0.
    for phase in ["rev-parse", "status"] {
        let dir = tempfile::tempdir().unwrap();
        let root = dir.path();
        let mut command = frozen::prepare(root);
        executable::write(root.join("tools/git"), format!("#!/bin/sh\nif [ \"$3\" = {phase} ]; then\n echo $$ > \"$HOME/git-pid\"\n exec /bin/sleep 10\nfi\nexit 0\n")).unwrap();
        let start = Instant::now();
        let result = command.arg("session-end").output().unwrap();
        let elapsed = start.elapsed();
        println!("slow Git {phase}: {elapsed:?}");
        let pid = fs::read_to_string(root.join("home/git-pid")).unwrap();
        let alive = Command::new("/bin/kill")
            .args(["-0", pid.trim()])
            .output()
            .unwrap()
            .status
            .success();
        // Clean up even when a deadline mutation breaks the timing assertion.
        if alive {
            let _ = Command::new("/bin/kill")
                .args(["-KILL", pid.trim()])
                .status();
        }
        assert!(!alive, "Git child survived: {pid}");
        assert!(
            elapsed < Duration::from_secs(3),
            "collection exceeded budget + 1 s: {elapsed:?}"
        );
        assert!(result.status.success());
        assert!(
            fs::read_to_string(root.join("project/tasks/handoffs/session-handoff-LATEST.md"))
                .unwrap()
                .contains("- Git status unavailable.\n")
        );
        let log =
            fs::read_to_string(root.join("project/.mir/runtime/hook-invocations.jsonl")).unwrap();
        assert_eq!(log.lines().count(), 1);
        assert_eq!(
            serde_json::from_str::<serde_json::Value>(&log).unwrap()["name"],
            "pre-compact"
        );
    }
}
