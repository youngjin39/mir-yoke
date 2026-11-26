//! Replay the TDD shell routes with synthetic projects and no Python helper.
#![cfg(unix)]

#[path = "support/executable.rs"]
mod executable;

use serde_json::{Value, json};
use std::{
    fs,
    os::unix::fs::{PermissionsExt, symlink},
    path::{Path, PathBuf},
    process::{Command, Output},
};

const HOOKS: &str = ".claude/hooks";
const GUARD: &str = ".claude/hooks/tdd-guard.sh";
const PRECOMMIT: &str = ".claude/hooks/pre-commit-verification.sh";
const TARGET: &str = "apps/web/main.ts";
const INCOMPLETE: &str =
    "[TddGuard WARN] composite TDD evidence is incomplete for apps/web/main.ts (advisory only)\n";
const UNAVAILABLE: &str = "Native TDD validation unavailable";

struct Fixture {
    scratch: tempfile::TempDir,
    project: PathBuf,
    repository: PathBuf,
    native: PathBuf,
}

impl Fixture {
    fn new() -> Self {
        let scratch = tempfile::tempdir().unwrap();
        let root = scratch.path();
        let repository = Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
        let project = root.join("test project");
        for path in ["home", "tmp", "test project/.mir/bin", "test project/tasks"] {
            fs::create_dir_all(root.join(path)).unwrap();
        }
        let native = project.join(".mir/bin/project-hooks");
        let fixture = Self {
            scratch,
            project,
            repository,
            native,
        };
        fixture.git(&["init", "--quiet", "--template="]);
        fixture.stage(TARGET);
        fixture
    }

    fn command(&self, program: &str) -> Command {
        let mut command = Command::new(program);
        command
            .env_clear()
            .env("PATH", "/usr/bin:/bin")
            .env("HOME", self.scratch.path().join("home"))
            .env("TMPDIR", self.scratch.path().join("tmp"))
            .env("LC_ALL", "C")
            .env("GIT_CONFIG_NOSYSTEM", "1")
            .env("GIT_CONFIG_GLOBAL", "/dev/null")
            .env("CLAUDE_PROJECT_DIR", &self.project)
            .env("MIR_PRE_COMMIT_LINT", "true")
            .env("MIR_PRE_COMMIT_TYPECHECK", "true")
            .env("MIR_PRE_COMMIT_TEST", "true")
            .current_dir(&self.project);
        command
    }

    fn git(&self, args: &[&str]) {
        let output = self.command("git").args(args).output().unwrap();
        assert!(output.status.success(), "{output:?}");
    }

    fn stage(&self, path: &str) {
        let destination = self.project.join(path);
        fs::create_dir_all(destination.parent().unwrap()).unwrap();
        fs::write(destination, "// fixture\n").unwrap();
        self.git(&["add", "--", path]);
    }

    fn install_native(&self) {
        executable::copy(env!("CARGO_BIN_EXE_project-hooks"), &self.native).unwrap();
    }

    fn write_ledger(&self, category: Value) {
        let ledger = json!({"changes": [{
            "id": "change",
            "targets": [TARGET],
            "categories": {"unit": category}
        }]});
        fs::write(self.project.join("tasks/tdd.json"), ledger.to_string()).unwrap();
    }

    fn replay(&self, disabled: bool, check: impl Fn(&str, Output, Output)) {
        let manifest: Value =
            serde_json::from_str(include_str!("../../../config/adopter-payload.json")).unwrap();
        let staged_hooks = self.project.join(HOOKS);
        fs::create_dir_all(&staged_hooks).unwrap();
        // Replay staged reference assets before adoption removes them. Copy the
        // candidate source bytes, since the checked-in inventory can predate them.
        for hook in [GUARD, PRECOMMIT] {
            let entry = manifest["files"]
                .as_array()
                .unwrap()
                .iter()
                .find(|entry| entry["path"] == hook)
                .unwrap();
            assert_eq!(entry["disposition"], "remove");
            fs::copy(self.repository.join(hook), self.project.join(hook)).unwrap();
        }
        for (label, source) in [
            ("repository source", &self.repository),
            ("staged adopter source", &self.project),
        ] {
            let invoke = |hook, arguments: &[&str]| {
                let mut command = self.command("/bin/bash");
                if disabled {
                    command.env("MIR_NATIVE_HOOKS", "0");
                }
                command
                    .arg(source.join(hook))
                    .args(arguments)
                    .output()
                    .unwrap()
            };
            check(label, invoke(GUARD, &[TARGET]), invoke(PRECOMMIT, &[]));
        }
    }
}

fn stderr(output: &Output) -> &str {
    std::str::from_utf8(&output.stderr).unwrap()
}

fn assert_guard(label: &str, output: &Output, expected: &str) {
    assert_eq!(output.status.code(), Some(0), "{label}: {output:?}");
    assert!(output.stdout.is_empty(), "{label}: {output:?}");
    assert_eq!(stderr(output), expected, "{label}");
}

fn assert_blocked(label: &str, output: &Output, expected: &str) {
    assert_eq!(output.status.code(), Some(2), "{label}: {output:?}");
    assert!(output.stdout.is_empty(), "{label}: {output:?}");
    assert!(stderr(output).contains(expected), "{label}: {output:?}");
}

#[test]
fn valid_evidence_advises_silently_and_runs_the_ledger_command() {
    let fixture = Fixture::new();
    fixture.install_native();
    fixture.write_ledger(json!({"status":"pass","command":"echo tdd-ran"}));
    fixture.replay(false, |label, guard, commit| {
        assert_eq!(commit.status.code(), Some(0), "{label}: {commit:?}");
        assert_eq!(commit.stdout, b"tdd-ran\n", "{label}");
        assert_guard(label, &guard, "");
    });
}

#[test]
fn planned_evidence_allows_edits_and_blocks_commits() {
    let fixture = Fixture::new();
    fixture.install_native();
    fixture.write_ledger(json!({"status":"planned"}));
    fixture.replay(false, |label, guard, commit| {
        assert_blocked(label, &commit, "Category 'unit' is still planned");
        assert_guard(label, &guard, "");
    });
}

#[test]
fn incomplete_evidence_warns_on_edit_and_blocks_commit() {
    let fixture = Fixture::new();
    fixture.install_native();
    fixture.write_ledger(json!({"status":"pass"}));
    fixture.replay(false, |label, guard, commit| {
        assert_guard(label, &guard, INCOMPLETE);
        assert_blocked(
            label,
            &commit,
            "Category 'unit' requires a runnable command",
        );
    });
}

#[test]
fn missing_and_malformed_ledgers_warn_on_edit_and_block_commit() {
    let fixture = Fixture::new();
    fixture.install_native();
    for (ledger, expected) in [
        (None, "Missing tasks/tdd.json"),
        (Some("{"), "Malformed tasks/tdd.json"),
    ] {
        if let Some(contents) = ledger {
            fs::write(fixture.project.join("tasks/tdd.json"), contents).unwrap();
        }
        fixture.replay(false, |label, guard, commit| {
            assert_guard(label, &guard, INCOMPLETE);
            assert_blocked(label, &commit, expected);
        });
    }
}

#[test]
fn unavailable_native_advises_on_edit_and_blocks_implementation_commits() {
    for case in [
        "missing",
        "disabled",
        "symlink",
        "symlink-bin",
        "symlink-mir",
        "capability",
        "warmup",
    ] {
        let fixture = Fixture::new();
        fixture.write_ledger(json!({"status":"pass","command":"echo tdd-ran"}));
        if case != "missing" {
            let (warmup, capability) = match case {
                "warmup" => (1, "mir-project-hooks-tdd-v1"),
                "capability" => (0, "mir-project-hooks-tdd-v10"),
                _ => (0, "mir-project-hooks-tdd-v1"),
            };
            executable::write(
                &fixture.native,
                format!(
                    "#!/bin/sh\nprintf '%s\n' \"$1\" >> native-attempts\ncase \"$1\" in\n  --mir-warmup) exit {warmup} ;;\n  capabilities) echo {capability} ;;\n  *) exit 0 ;;\nesac\n"
                ),
            )
            .unwrap();
            fs::set_permissions(&fixture.native, fs::Permissions::from_mode(0o755)).unwrap();
            let linked = match case {
                "symlink" => Some(fixture.native.as_path()),
                "symlink-bin" => fixture.native.parent(),
                "symlink-mir" => fixture.native.parent().and_then(Path::parent),
                _ => None,
            };
            if let Some(path) = linked {
                let original = path.with_extension("original");
                fs::rename(path, &original).unwrap();
                symlink(original, path).unwrap();
            }
        }
        fixture.replay(case == "disabled", |source, guard, commit| {
            let label = format!("{case}, {source}");
            let expected = format!("[TddGuard WARN] {UNAVAILABLE} (advisory only)\n");
            assert_blocked(
                &label,
                &commit,
                &format!("[PreCommitVerification BLOCK] {UNAVAILABLE}"),
            );
            assert_guard(&label, &guard, &expected);
        });
        let attempts = fixture.project.join("native-attempts");
        match case {
            "warmup" => assert_eq!(
                fs::read_to_string(attempts).unwrap(),
                "--mir-warmup\n".repeat(4)
            ),
            "capability" => assert_eq!(
                fs::read_to_string(attempts).unwrap(),
                "--mir-warmup\ncapabilities\n".repeat(4)
            ),
            _ => assert!(!attempts.exists(), "{case} executed the native hook"),
        }
    }
}
