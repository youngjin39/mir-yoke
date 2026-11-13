use handoff_packet::executor_worktree::*;
use serde_json::{Value, json};
use std::{
    collections::BTreeMap,
    fs,
    path::{Path, PathBuf},
    process::Command,
};

struct Fixture(PathBuf);
impl Fixture {
    fn new() -> Self {
        static NEXT: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);
        let root = std::env::var_os("MIR_NATIVE_TEST_SCRATCH")
            .map(PathBuf::from)
            .unwrap_or_else(std::env::temp_dir)
            .join(format!(
                "e6-{}-{}",
                std::process::id(),
                NEXT.fetch_add(1, std::sync::atomic::Ordering::Relaxed)
            ));
        fs::create_dir_all(&root).unwrap();
        Self(root)
    }
    fn repo(&self, name: &str, files: &Value) -> PathBuf {
        let repo = self.0.join(name);
        fs::create_dir_all(&repo).unwrap();
        git(&repo, &["init", "-q"]);
        git(&repo, &["config", "core.autocrlf", "false"]);
        git(&repo, &["config", "user.name", "Fixture"]);
        git(&repo, &["config", "user.email", "fixture@example.invalid"]);
        for (path, text) in files.as_object().unwrap() {
            let path = repo.join(path);
            fs::create_dir_all(path.parent().unwrap()).unwrap();
            fs::write(path, text.as_str().unwrap()).unwrap();
        }
        git(&repo, &["add", "-A"]);
        git(&repo, &["commit", "-qm", "fixture"]);
        repo
    }
}
impl Drop for Fixture {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}
fn git(repo: &Path, args: &[&str]) -> String {
    let out = Command::new("git")
        .arg("-C")
        .arg(repo)
        .args(args)
        .output()
        .unwrap();
    assert!(
        out.status.success(),
        "{}",
        String::from_utf8_lossy(&out.stderr)
    );
    String::from_utf8(out.stdout).unwrap().trim().to_owned()
}
fn golden() -> Value {
    serde_json::from_str(include_str!("fixtures/executor_worktree.json")).unwrap()
}
#[test]
fn python_golden_real_git_lifecycle_and_artifacts() {
    for case in golden()["cases"].as_array().unwrap() {
        let fixture = Fixture::new();
        let repo = fixture.repo(case["name"].as_str().unwrap(), &case["files"]);
        fs::create_dir(repo.join(".mir")).unwrap();
        fs::write(
            repo.join(".mir/repo-profile.toml"),
            case["profile"].as_str().unwrap(),
        )
        .unwrap();
        let trees = fixture.0.join("work trees");
        let wt = create_dispatch_worktree(
            &repo,
            "fixture",
            "HEAD",
            case["brief"].as_str().unwrap(),
            Some(&trees),
        )
        .unwrap();
        let inspected = inspect_worktree(&wt).unwrap();
        assert_eq!(inspected["head"], git(&repo, &["rev-parse", "HEAD"]));
        assert_eq!(inspected["branch"], "mir-dispatch/fixture");
        let expected = &case["expected"];
        assert_eq!(git(&wt.path, &["ls-files", "-z"]), expected["tracked"]);
        assert_eq!(
            git(&wt.path, &["status", "--porcelain", "-z"]),
            expected["git_status"]
        );
        assert_eq!(
            fs::read_to_string(&wt.brief_path).unwrap(),
            expected["brief"]
        );
        let mut status: Value =
            serde_json::from_slice(&fs::read(&wt.status_path).unwrap()).unwrap();
        assert_eq!(status["base_commit"], git(&repo, &["rev-parse", "HEAD"]));
        status["base_commit"] = json!("<BASE>");
        assert_eq!(status, expected["status"]);
        assert_eq!(
            git(&wt.path, &["branch", "--show-current"]),
            expected["branch"]
        );
        assert_eq!(
            fs::read_to_string(wt.path.join(".mir/repo-profile.toml")).unwrap(),
            expected["profile"]
        );
        assert_eq!(
            fs::read_to_string(wt.path.join("code [literal].txt")).unwrap(),
            "initial\n"
        );
        fs::write(wt.path.join("code [literal].txt"), "isolated\n").unwrap();
        assert_eq!(
            fs::read_to_string(repo.join("code [literal].txt")).unwrap(),
            "initial\n"
        );
        for (name, text) in case["artifacts"].as_object().unwrap() {
            fs::write(
                wt.path.join(".mir-dispatch").join(name),
                text.as_str().unwrap(),
            )
            .unwrap();
        }
        let output =
            persist_dispatch_artifacts(&wt, &repo, Some(&fixture.0.join("artifacts"))).unwrap();
        for (name, text) in expected["artifacts"].as_object().unwrap() {
            assert_eq!(
                fs::read_to_string(output.join(name)).unwrap(),
                text.as_str().unwrap(),
                "{name}"
            );
        }
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            assert_eq!(
                format!(
                    "{:#o}",
                    fs::metadata(&wt.brief_path).unwrap().permissions().mode() & 0o777
                ),
                expected["private_mode"]
            );
        }
        write_status(&wt, "complete", &json!({"token":"hidden"})).unwrap();
        let status: Value = serde_json::from_slice(&fs::read(&wt.status_path).unwrap()).unwrap();
        assert_eq!(status["token"], "[REDACTED]");
        cleanup_worktree(&wt, true).unwrap();
        cleanup_worktree(&wt, true).unwrap();
        assert!(!wt.path.exists());
        assert!(git(&repo, &["branch", "--list", &wt.branch]).is_empty());
        assert_eq!(
            git(&repo, &["worktree", "list", "--porcelain"])
                .matches("worktree ")
                .count(),
            1
        );
    }
}
#[test]
fn python_golden_child_env() {
    let fixture = Fixture::new();
    fs::create_dir(fixture.0.join("config")).unwrap();
    for case in golden()["env"].as_array().unwrap() {
        fs::write(
            fixture.0.join("config/mir-executor.local.json"),
            case["config"].to_string(),
        )
        .unwrap();
        let source: BTreeMap<String, String> =
            serde_json::from_value(case["source"].clone()).unwrap();
        assert_eq!(
            serde_json::to_value(
                child_env(&fixture.0, &source, case["force"].as_bool().unwrap()).unwrap()
            )
            .unwrap(),
            case["expected"]
        );
    }
}
#[test]
fn seed_failure_retains_git_registration_branch_and_tree_like_reference() {
    let fixture = Fixture::new();
    let repo = fixture.repo("repo", &json!({".mir-dispatch":"blocked\n"}));
    let trees = fixture.0.join("trees");
    let error =
        create_dispatch_worktree(&repo, "failure", "HEAD", "brief", Some(&trees)).unwrap_err();
    assert_eq!(error.kind(), "FileExistsError");
    assert_eq!(
        error.to_string(),
        format!(
            "[Errno 17] File exists: '{}'",
            trees.join("failure/.mir-dispatch").display()
        )
    );
    assert!(trees.join("failure").exists());
    assert!(!git(&repo, &["branch", "--list", "mir-dispatch/failure"]).is_empty());
    assert_eq!(
        git(&repo, &["worktree", "list", "--porcelain"])
            .matches("worktree ")
            .count(),
        2
    );
}

#[test]
fn private_replacement_and_invalid_json() {
    let fixture = Fixture::new();
    let file = fixture.0.join("brief.md");
    fs::write(&file, "old").unwrap();
    write_private_text(&file, "token=hidden", true).unwrap();
    assert_eq!(fs::read_to_string(&file).unwrap(), "token=[REDACTED]");
    assert!(secure_write(&fixture.0.join("bad.json"), "not json", false).is_err());
}
#[cfg(unix)]
#[test]
fn artifact_and_private_symlinks_are_refused() {
    use std::os::unix::fs::symlink;
    let fixture = Fixture::new();
    let repo = fixture.repo("repo", &json!({"code":"initial"}));
    let wt = create_dispatch_worktree(
        &repo,
        "symlink",
        "HEAD",
        "brief",
        Some(&fixture.0.join("trees")),
    )
    .unwrap();
    let outside = fixture.0.join("outside");
    fs::write(&outside, "{}").unwrap();
    symlink(&outside, wt.path.join(".mir-dispatch/result.json")).unwrap();
    assert!(persist_dispatch_artifacts(&wt, &repo, Some(&fixture.0.join("artifacts"))).is_err());
    let dest = fixture.0.join("private");
    symlink(&outside, &dest).unwrap();
    let refusal = write_private_text(&dest, "overwrite", true).unwrap_err();
    assert_eq!(refusal.kind(), "OSError");
    assert!(
        refusal
            .to_string()
            .starts_with(&format!("[Errno {}]", libc::ELOOP))
    );
    assert_eq!(fs::read_to_string(outside).unwrap(), "{}");
    cleanup_worktree(&wt, true).unwrap();
}
#[test]
fn literal_merge_paths_and_harness_exclusions() {
    let fixture = Fixture::new();
    let repo = fixture.repo(
        "repo",
        &json!({"code [literal].txt":"old", "tasks/plan.md":"main", "gone.txt":"old"}),
    );
    let wt = create_dispatch_worktree(&repo, "merge", "HEAD", "", Some(&fixture.0.join("trees")))
        .unwrap();
    fs::write(wt.path.join("code [literal].txt"), "new").unwrap();
    fs::write(wt.path.join("tasks/plan.md"), "changed").unwrap();
    fs::remove_file(wt.path.join("gone.txt")).unwrap();
    let unicode = "space \u{3bb}.txt";
    fs::write(wt.path.join(unicode), "unicode").unwrap();
    git(&wt.path, &["add", "-A"]);
    git(&wt.path, &["commit", "-qm", "change"]);
    let outcome = merge_result(&wt, None, None, false).unwrap();
    assert!(outcome.skipped.contains(&"tasks/plan.md".to_owned()));
    assert!(outcome.merged_files.contains(&unicode.to_owned()));
    assert_eq!(
        fs::read_to_string(repo.join("code [literal].txt")).unwrap(),
        "new"
    );
    assert_eq!(
        fs::read_to_string(repo.join("tasks/plan.md")).unwrap(),
        "main"
    );
    assert!(!repo.join("gone.txt").exists());
    cleanup_worktree(&wt, true).unwrap();
}
#[test]
fn automatic_root_is_removed_and_branch_can_be_kept() {
    let fixture = Fixture::new();
    let repo = fixture.repo("repo", &json!({"code":"initial"}));
    let wt = create_dispatch_worktree(&repo, "auto", "HEAD", "", None).unwrap();
    let root = wt.path.parent().unwrap().to_owned();
    cleanup_worktree(&wt, false).unwrap();
    let golden: Value =
        serde_json::from_str(include_str!("fixtures/executor_tmpdir.json")).unwrap();
    for case in golden["cases"].as_object().unwrap().values() {
        assert_eq!(!root.exists(), case["automatic_removed"]);
        assert_eq!(
            !git(&repo, &["branch", "--list", &wt.branch]).is_empty(),
            case["branch_kept"]
        );
    }
}
#[test]
fn malformed_local_config_fails_and_missing_config_preserves_environment() {
    let fixture = Fixture::new();
    let source = BTreeMap::from([("API_TOKEN".to_owned(), "hidden".to_owned())]);
    assert_eq!(child_env(&fixture.0, &source, false).unwrap(), source);
    fs::create_dir(fixture.0.join("config")).unwrap();
    fs::write(fixture.0.join("config/mir-executor.local.json"), "[]").unwrap();
    assert!(child_env(&fixture.0, &source, false).is_err());
}
#[test]
fn redaction_preserves_long_evidence_and_structured_secrets() {
    let fixture = Fixture::new();
    let file = fixture.0.join("brief.md");
    let text = "x".repeat(20000) + "\npassword=private\n";
    write_private_text(&file, &text, true).unwrap();
    let actual = fs::read_to_string(&file).unwrap();
    assert_eq!(actual, "x".repeat(20000) + "\npassword=[REDACTED]\n");
    let file = fixture.0.join("result.json");
    secure_write(
        &file,
        r#"{"nested":{"API_KEY":"private"},"items":["token=private"]}"#,
        false,
    )
    .unwrap();
    let actual: Value = serde_json::from_slice(&fs::read(file).unwrap()).unwrap();
    assert_eq!(
        actual,
        json!({"nested":{"API_KEY":"[REDACTED]"},"items":["token=[REDACTED]"]})
    );
}
#[cfg(unix)]
#[test]
fn artifact_directory_symlink_is_refused() {
    use std::os::unix::fs::symlink;
    let fixture = Fixture::new();
    let repo = fixture.repo("repo", &json!({"code":"initial"}));
    let wt = create_dispatch_worktree(
        &repo,
        "dirlink",
        "HEAD",
        "brief",
        Some(&fixture.0.join("trees")),
    )
    .unwrap();
    fs::remove_dir_all(wt.path.join(".mir-dispatch")).unwrap();
    let outside = fixture.0.join("outside");
    fs::create_dir(&outside).unwrap();
    fs::write(outside.join("brief.md"), "keep").unwrap();
    symlink(&outside, wt.path.join(".mir-dispatch")).unwrap();
    assert!(persist_dispatch_artifacts(&wt, &repo, Some(&fixture.0.join("artifacts"))).is_err());
    assert_eq!(
        fs::read_to_string(outside.join("brief.md")).unwrap(),
        "keep"
    );
    cleanup_worktree(&wt, true).unwrap();
}
#[test]
fn git_refusal_preserves_existing_branch_and_checkout() {
    let fixture = Fixture::new();
    let repo = fixture.repo("repo", &json!({"code":"initial"}));
    git(&repo, &["branch", "mir-dispatch/existing"]);
    let trees = fixture.0.join("trees");
    let refusal =
        create_dispatch_worktree(&repo, "existing", "HEAD", "", Some(&trees)).unwrap_err();
    assert_eq!(refusal.kind(), "CalledProcessError");
    assert!(
        refusal
            .to_string()
            .contains("returned non-zero exit status 255.")
    );
    match refusal {
        Error::Git { stderr, .. } => {
            assert_eq!(stderr, golden()["cases"][0]["expected"]["refusal_stderr"])
        }
        other => panic!("unexpected refusal: {other}"),
    }
    assert!(!trees.join("existing").exists());
    assert!(!git(&repo, &["branch", "--list", "mir-dispatch/existing"]).is_empty());
    assert_eq!(fs::read_to_string(repo.join("code")).unwrap(), "initial");
}

// Windows runners without Developer Mode may not grant symlink privileges.
fn directory_link(target: &Path, link: &Path) -> bool {
    #[cfg(unix)]
    std::os::unix::fs::symlink(target, link).unwrap();
    #[cfg(windows)]
    if let Err(error) = std::os::windows::fs::symlink_dir(target, link) {
        if error.raw_os_error() == Some(1314) {
            eprintln!("skipping: directory symlink privilege unavailable");
            return false;
        }
        panic!("directory symlink failed: {error}");
    }
    true
}

#[test]
fn selected_roots_under_symlinked_ancestor_complete_lifecycle() {
    let fixture = Fixture::new();
    fixture.repo("real/repo", &json!({"code":"initial"}));
    let alias = fixture.0.join("alias");
    if !directory_link(&fs::canonicalize(fixture.0.join("real")).unwrap(), &alias) {
        return;
    }
    let repo = alias.join("repo");
    // Both roots are absent, exercising nearest-existing-ancestor resolution.
    let trees = alias.join("new/trees");
    let wt = create_dispatch_worktree(&repo, "alias", "HEAD", "brief", Some(&trees)).unwrap();
    assert_eq!(
        inspect_worktree(&wt).unwrap()["branch"],
        "mir-dispatch/alias"
    );
    let artifacts = alias.join("new/artifacts");
    let output = persist_dispatch_artifacts(&wt, &repo, Some(&artifacts)).unwrap();
    assert_eq!(
        fs::read_to_string(output.join("brief.md")).unwrap(),
        "brief"
    );
    let default_output = persist_dispatch_artifacts(&wt, &repo, None).unwrap();
    assert_eq!(
        fs::read_to_string(default_output.join("brief.md")).unwrap(),
        "brief"
    );
    let file = repo.join("private.md");
    write_private_text(&file, "private", false).unwrap();
    secure_write(&alias.join("missing/evidence.json"), "{}", false).unwrap();
    write_status(&wt, "complete", &json!({})).unwrap();
    cleanup_worktree(&wt, true).unwrap();
    assert!(!wt.path.exists());
    assert!(git(&repo, &["branch", "--list", &wt.branch]).is_empty());
    assert_eq!(
        git(&repo, &["worktree", "list", "--porcelain"])
            .matches("worktree ")
            .count(),
        1
    );
}

#[test]
fn links_below_selected_roots_are_refused() {
    let fixture = Fixture::new();
    let repo = fixture.repo("repo", &json!({"code":"initial"}));
    let outside = fixture.0.join("outside");
    fs::create_dir(&outside).unwrap();
    fs::write(outside.join("brief.md"), "keep").unwrap();
    let trees = fixture.0.join("trees");
    fs::create_dir(&trees).unwrap();
    if !directory_link(&fs::canonicalize(&outside).unwrap(), &trees.join("linked")) {
        return;
    }
    let refusal = create_dispatch_worktree(&repo, "linked", "HEAD", "", Some(&trees)).unwrap_err();
    assert!(
        refusal
            .to_string()
            .contains("symlink/reparse point rejected:")
    );
    let wt = create_dispatch_worktree(&repo, "safe", "HEAD", "brief", Some(&trees)).unwrap();
    let artifacts = fixture.0.join("artifacts");
    fs::create_dir(&artifacts).unwrap();
    directory_link(
        &fs::canonicalize(&outside).unwrap(),
        &artifacts.join("safe"),
    );
    assert!(persist_dispatch_artifacts(&wt, &repo, Some(&artifacts)).is_err());
    fs::remove_dir_all(wt.path.join(".mir-dispatch")).unwrap();
    directory_link(
        &fs::canonicalize(&outside).unwrap(),
        &wt.path.join(".mir-dispatch"),
    );
    assert!(persist_dispatch_artifacts(&wt, &repo, Some(&fixture.0.join("evidence"))).is_err());
    assert!(write_status(&wt, "complete", &json!({})).is_err());
    assert_eq!(
        fs::read_to_string(outside.join("brief.md")).unwrap(),
        "keep"
    );
    cleanup_worktree(&wt, true).unwrap();
}

#[test]
fn selected_terminal_root_matches_pinned_python() {
    let fixture = Fixture::new();
    let repo = fixture.repo("repo", &json!({"code":"initial"}));
    let real = fixture.0.join("real");
    fs::create_dir(&real).unwrap();
    let alias = fixture.0.join("alias");
    if !directory_link(&fs::canonicalize(&real).unwrap(), &alias) {
        return;
    }
    let expected: Value =
        serde_json::from_str(include_str!("fixtures/executor_tmpdir.json")).unwrap();
    let wt = create_dispatch_worktree(&repo, "selected", "HEAD", "", Some(&alias));
    assert_eq!(
        wt.is_ok(),
        expected["cases"]["terminal"]["selected_terminal_accepted"]
    );
    cleanup_worktree(&wt.unwrap(), true).unwrap();
}

#[test]
fn descendant_refusal_matches_pinned_python_control() {
    let fixture = Fixture::new();
    let repo = fixture.repo("repo", &json!({"code":"initial"}));
    let root = fixture.0.join("trees");
    let outside = fixture.0.join("outside");
    fs::create_dir(&root).unwrap();
    fs::create_dir(&outside).unwrap();
    fs::write(outside.join("keep"), "keep").unwrap();
    if !directory_link(
        &fs::canonicalize(&outside).unwrap(),
        &root.join("descendant"),
    ) {
        return;
    }
    let golden: Value =
        serde_json::from_str(include_str!("fixtures/executor_tmpdir.json")).unwrap();
    let err = create_dispatch_worktree(&repo, "descendant", "HEAD", "", Some(&root)).unwrap_err();
    assert!(err.to_string().contains("symlink/reparse point rejected:"));
    for case in golden["cases"].as_object().unwrap().values() {
        assert_eq!(case["descendant"]["exception"], "CalledProcessError");
        assert_eq!(case["descendant"]["code"], 128);
        assert_eq!(
            fs::read_to_string(outside.join("keep")).unwrap() == "keep",
            case["descendant"]["target_preserved"]
        );
    }
}

#[test]
fn dangling_selected_root_remains_refused() {
    let fixture = Fixture::new();
    let repo = fixture.repo("repo", &json!({"code":"initial"}));
    let alias = fixture.0.join("dangling");
    if !directory_link(&fixture.0.join("missing"), &alias) {
        return;
    }
    assert!(create_dispatch_worktree(&repo, "dangling", "HEAD", "", Some(&alias)).is_err());
    assert!(!fixture.0.join("missing").exists());
}

#[cfg(unix)]
#[test]
fn invalid_terminal_roots_keep_existing_guard_refusal() {
    use std::os::unix::fs::symlink;
    let fixture = Fixture::new();
    let repo = fixture.repo("repo", &json!({"code":"initial"}));
    let file = fixture.0.join("file");
    fs::write(&file, "keep").unwrap();
    let pair = fixture.0.join("pair");
    symlink(fixture.0.join("loop-pair"), &pair).unwrap();
    let wt = create_dispatch_worktree(
        &repo,
        "safe",
        "HEAD",
        "brief",
        Some(&fixture.0.join("trees")),
    )
    .unwrap();
    for (name, target) in [
        ("dangling-absolute", fixture.0.join("missing")),
        ("dangling-relative", PathBuf::from("missing")),
        ("loop-self", fixture.0.join("loop-self")),
        ("loop-pair", pair),
        ("file-alias", file.clone()),
    ] {
        let alias = fixture.0.join(name);
        symlink(target, &alias).unwrap();
        let expected = format!("symlink/reparse point rejected: {}", alias.display());
        for refusal in [
            create_dispatch_worktree(&repo, "attack", "HEAD", "", Some(&alias)).unwrap_err(),
            write_private_text(&alias.join("private.md"), "probe", false).unwrap_err(),
            secure_write(&alias.join("secure.md"), "probe", false).unwrap_err(),
            persist_dispatch_artifacts(&wt, &repo, Some(&alias)).unwrap_err(),
        ] {
            assert_eq!(refusal.kind(), "ValueError", "{name}");
            assert_eq!(refusal.to_string(), expected, "{name}");
        }
    }
    assert_eq!(fs::read_to_string(file).unwrap(), "keep");
    assert!(!fixture.0.join("missing").exists());
    cleanup_worktree(&wt, true).unwrap();
}

#[cfg(unix)]
#[test]
fn artifact_existing_file_preserves_write_permission_contract() {
    use std::os::unix::fs::PermissionsExt;
    let fixture = Fixture::new();
    let path = fixture.0.join("artifact.md");
    fs::write(&path, "original").unwrap();
    fs::set_permissions(&path, fs::Permissions::from_mode(0o400)).unwrap();
    let refusal = secure_write(&path, "replacement", false).unwrap_err();
    assert_eq!(refusal.kind(), "PermissionError");
    assert_eq!(fs::read_to_string(&path).unwrap(), "original");
    fs::set_permissions(&path, fs::Permissions::from_mode(0o200)).unwrap();
    secure_write(&path, "replacement", false).unwrap();
    secure_write(&path, "+append", true).unwrap();
    assert_eq!(fs::read_to_string(&path).unwrap(), "replacement+append");
    assert_eq!(
        fs::metadata(&path).unwrap().permissions().mode() & 0o777,
        0o600
    );
}

#[test]
fn selected_alias_errors_preserve_caller_spelling() {
    for nested in [false, true] {
        selected_alias_errors_preserve_caller_spelling_case(nested);
    }
}

fn selected_alias_errors_preserve_caller_spelling_case(nested: bool) {
    let fixture = Fixture::new();
    let real = fixture.0.join("real");
    fs::create_dir(&real).unwrap();
    let alias = if nested {
        fixture.0.join("real/alias")
    } else {
        fixture.0.join("alias")
    };
    if !directory_link(&fs::canonicalize(&real).unwrap(), &alias) {
        return;
    }
    fs::write(real.join("blocked"), "keep").unwrap();
    let file = alias.join("blocked/child/evidence.md");
    let error = secure_write(&file, "probe", false).unwrap_err();
    assert_eq!(error.kind(), "NotADirectoryError");
    assert_eq!(
        error.to_string(),
        format!(
            "[Errno 20] Not a directory: '{}'",
            file.parent().unwrap().display()
        )
    );
    let file = alias.join("blocked");
    let error = secure_write(&file.join("evidence.md"), "probe", false).unwrap_err();
    assert_eq!(error.kind(), "FileExistsError");
    assert_eq!(
        error.to_string(),
        format!("[Errno 17] File exists: '{}'", file.display())
    );
    let error = write_private_text(&alias.join("missing/evidence.md"), "probe", false).unwrap_err();
    assert_eq!(error.kind(), "FileNotFoundError");
    assert_eq!(
        error.to_string(),
        format!(
            "[Errno 2] No such file or directory: '{}'",
            alias.join("missing/evidence.md").display()
        )
    );
}

#[test]
fn git_refusal_uses_caller_alias_in_command() {
    for nested in [false, true] {
        git_refusal_uses_caller_alias_in_command_case(nested);
    }
}

fn git_refusal_uses_caller_alias_in_command_case(nested: bool) {
    let fixture = Fixture::new();
    let real = fixture.0.join("real");
    let repo = fixture.repo("real/repo", &json!({"code":"keep"}));
    let alias = if nested {
        fixture.0.join("real/alias")
    } else {
        fixture.0.join("alias")
    };
    if !directory_link(&fs::canonicalize(&real).unwrap(), &alias) {
        return;
    }
    git(&repo, &["branch", "mir-dispatch/existing"]);
    let error = create_dispatch_worktree(
        &alias.join("repo"),
        "existing",
        "HEAD",
        "",
        Some(&alias.join("trees")),
    )
    .unwrap_err();
    assert_eq!(error.kind(), "CalledProcessError");
    assert!(matches!(
        &error,
        Error::Git {
            code: Some(255),
            ..
        }
    ));
    assert_eq!(
        error.to_string(),
        format!(
            "Command '['git', '-C', '{}', 'worktree', 'add', '-b', 'mir-dispatch/existing', '{}', '{}']' returned non-zero exit status 255.",
            alias.join("repo").display(),
            alias.join("trees/existing").display(),
            git(&repo, &["rev-parse", "HEAD"])
        )
    );
    // An explicit physical worktree root must not inherit the repo alias.
    let physical_trees = fs::canonicalize(&repo).unwrap().join("trees");
    let error = create_dispatch_worktree(
        &alias.join("repo"),
        "existing",
        "HEAD",
        "",
        Some(&physical_trees),
    )
    .unwrap_err();
    let Error::Git {
        command: Some(command),
        ..
    } = error
    else {
        panic!("expected Git refusal");
    };
    assert_eq!(Path::new(&command[2]), alias.join("repo"));
    assert_eq!(Path::new(&command[7]), physical_trees.join("existing"));
}

#[test]
fn alias_status_inspection_and_event_errors_keep_spelling() {
    for nested in [false, true] {
        alias_status_inspection_and_event_errors_keep_spelling_case(nested);
    }
}

fn alias_status_inspection_and_event_errors_keep_spelling_case(nested: bool) {
    use handoff_packet::executor_dispatch::{
        CodexAttempt, DispatchContext, DispatchOptions, run_dispatch,
    };
    let fixture = Fixture::new();
    let repo = fixture.repo("real/repo", &json!({"code":"keep"}));
    let alias = if nested {
        fixture.0.join("real/alias")
    } else {
        fixture.0.join("alias")
    };
    if !directory_link(&fs::canonicalize(fixture.0.join("real")).unwrap(), &alias) {
        return;
    }
    let trees = alias.join("trees");
    let wt =
        create_dispatch_worktree(&alias.join("repo"), "inspect", "HEAD", "", Some(&trees)).unwrap();
    fs::remove_dir_all(wt.path.join(".mir-dispatch")).unwrap();
    let error = write_status(&wt, "complete", &json!({})).unwrap_err();
    assert_eq!(
        error.to_string(),
        format!(
            "[Errno 2] No such file or directory: '{}'",
            trees.join("inspect/.mir-dispatch/status.json").display()
        )
    );
    fs::remove_file(wt.path.join(".git")).unwrap();
    let error = inspect_worktree(&wt).unwrap_err();
    assert_eq!(error.kind(), "CalledProcessError");
    assert!(matches!(
        &error,
        Error::Git {
            code: Some(128),
            ..
        }
    ));
    assert_eq!(
        error.to_string(),
        format!(
            "Command '['git', '-C', '{}', 'rev-parse', 'HEAD']' returned non-zero exit status 128.",
            trees.join("inspect").display()
        )
    );
    for mode in ["default", "explicit", "artifacts"] {
        let mut options = DispatchOptions::new(&repo, mode);
        options.worktrees_root = Some(trees.clone());
        let expected = match mode {
            "explicit" => {
                let path = alias.join("events/explicit.jsonl");
                options.dispatch_events_path = Some(path.clone());
                path
            }
            "artifacts" => {
                options.artifacts_root = Some(alias.join("artifacts"));
                alias.join("artifacts/artifacts/dispatch-events.jsonl")
            }
            _ => trees.join("default/.mir-dispatch/dispatch-events.jsonl"),
        };
        let error = run_dispatch(
            &options,
            &mut DispatchContext::default(),
            &mut |_: &DispatchWorktree, _: usize| {
                fs::create_dir_all(&expected).unwrap();
                Ok(CodexAttempt::default())
            },
        )
        .unwrap_err();
        assert_eq!(error.kind(), "IsADirectoryError", "{mode}");
        assert_eq!(
            error.to_string(),
            format!("[Errno 21] Is a directory: '{}'", expected.display()),
            "{mode}"
        );
    }
}

#[test]
fn nested_alias_cleanup_and_merge_errors_keep_spelling() {
    let fixture = Fixture::new();
    let repo = fixture.repo("repo", &json!({"code":"keep"}));
    let alias = repo.join("alias");
    if !directory_link(&fs::canonicalize(&repo).unwrap(), &alias) {
        return;
    }
    let trees = alias.join("trees");
    let wt = create_dispatch_worktree(&alias, "locked", "HEAD", "", Some(&trees)).unwrap();
    git(&repo, &["worktree", "lock", wt.path.to_str().unwrap()]);
    let error = cleanup_worktree(&wt, false).unwrap_err();
    assert_eq!(error.kind(), "CalledProcessError");
    assert_eq!(
        error.to_string(),
        format!(
            "Command '['git', '-C', '{}', 'worktree', 'remove', '--force', '{}']' returned non-zero exit status 128.",
            alias.display(),
            trees.join("locked").display()
        )
    );
    let error = merge_result(&wt, Some("missing-ref"), None, false).unwrap_err();
    assert_eq!(error.kind(), "CalledProcessError");
    assert_eq!(
        error.to_string(),
        format!(
            "Command '['git', '-C', '{}', 'diff', '--no-renames', '--name-only', '-z', '{}', 'missing-ref']' returned non-zero exit status 128.",
            alias.display(),
            wt.base_commit
        )
    );
}
