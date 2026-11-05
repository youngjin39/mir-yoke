//! Yoke's staged verification policy; callers remain on the shell reference.
use crate::tdd_ledger;
use serde_json::Value;
use std::{
    env, fs,
    io::Write,
    path::Path,
    process::{Command, Stdio},
    time::{SystemTime, UNIX_EPOCH},
};

fn git(project: &Path, args: &[&str]) -> Option<Vec<u8>> {
    Command::new("git")
        .args(args)
        .current_dir(project)
        .stderr(Stdio::null())
        .output()
        .ok()
        .filter(|output| output.status.success())
        .map(|output| output.stdout)
}

fn code(path: &str, deferred_tools: bool) -> bool {
    tdd_ledger::implementation(path)
        || ["tests/", "tools/"]
            .iter()
            .any(|root| path.starts_with(root) && (*root != "tools/" || !deferred_tools))
            && tdd_ledger::implementation(&format!("src/{path}"))
}

fn step(project: &Path, label: &str, command: &str) -> bool {
    if command.is_empty() {
        return true;
    }
    eprintln!("[PreCommitVerification] {label}: {command}");
    if Command::new("/bin/bash")
        .args(["-lc", command])
        .current_dir(project)
        .status()
        .is_ok_and(|status| status.success())
    {
        true
    } else {
        eprintln!("[PreCommitVerification BLOCK] {label} failed");
        false
    }
}

fn override_command(name: &str, default: String) -> String {
    env::var(name)
        .ok()
        .filter(|s| !s.is_empty())
        .unwrap_or(default)
}

// Match the reference's UTC ISO timestamp without an interpreter or shell helper.
fn record_bypass(project: &Path) -> Result<(), Box<dyn std::error::Error>> {
    let now = SystemTime::now().duration_since(UNIX_EPOCH)?;
    let db = rusqlite::Connection::open_in_memory()?;
    let iso: String = db.query_row(
        "SELECT strftime('%Y-%m-%dT%H:%M:%S', ?1, 'unixepoch')",
        [i64::try_from(now.as_secs())?],
        |row| row.get(0),
    )?;
    let audit = project.join("tasks/audit");
    fs::create_dir_all(&audit)?;
    let mut file = fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(audit.join("suggest_bypass.jsonl"))?;
    writeln!(
        file,
        "{{\"ts\":\"{iso}.{:06}+00:00\",\"hook_id\":\"pre-commit/test\",\"reason\":\"test step failed; bypassed by MIR_SUGGEST_TIER_CONFIRM=1\"}}",
        now.subsec_micros()
    )?;
    Ok(())
}

pub fn run() -> u8 {
    let project = env::var_os("CLAUDE_PROJECT_DIR")
        .filter(|p| !p.is_empty())
        .unwrap_or_else(|| ".".into());
    let project = Path::new(&project);
    if git(project, &["rev-parse", "--is-inside-work-tree"]).is_none() {
        return 0;
    }
    // Unknown, missing and malformed manifest values keep tools gated. Only the
    // repository's exact deferred value changes the classifier.
    let deferred_tools = fs::read(project.join("config/harness-consistency.json"))
        .ok()
        .and_then(|bytes| serde_json::from_slice::<Value>(&bytes).ok())
        .is_some_and(|v| v["repo"]["enforcement"]["tools_commit_gate"] == "deferred");
    let staged = git(
        project,
        &["diff", "--cached", "--name-only", "--diff-filter=ACMR"],
    )
    .unwrap_or_default();
    let Ok(staged) = String::from_utf8(staged) else {
        eprintln!("[PreCommitVerification BLOCK] Staged paths are not UTF-8");
        return 2;
    };
    let mut paths: Vec<_> = staged
        .lines()
        .filter(|p| !p.trim().is_empty() && code(p, deferred_tools))
        .collect();
    paths.sort_unstable();
    paths.dedup();
    if paths.is_empty() {
        eprintln!("[PreCommitVerification] Skipped: no code changes detected");
        return 0;
    }
    let implementation: Vec<_> = paths
        .iter()
        .filter(|p| tdd_ledger::implementation(p))
        .map(|p| (*p).to_owned())
        .collect();
    if !implementation.is_empty() {
        let (code, commands, stderr) = tdd_ledger::precommit(project, implementation);
        eprint!("{stderr}");
        if code != 0 {
            return 2;
        }
        for (index, command) in commands.lines().filter(|c| !c.is_empty()).enumerate() {
            if !step(project, &format!("tdd[{}]", index + 1), command) {
                return 2;
            }
        }
    }
    let (lint, typecheck, test, build) = if project.join("package.json").is_file() {
        (
            "npm run lint --if-present".into(),
            "npm run typecheck --if-present".into(),
            "npm run test --if-present".into(),
            "npm run build --if-present".into(),
        )
    } else if project.join("pyproject.toml").is_file() {
        // The shell reference splits the joined paths for these two selections.
        let joined = paths.join(" ");
        let python: Vec<_> = joined
            .split_whitespace()
            .filter(|p| p.ends_with(".py"))
            .collect();
        let tests: Vec<_> = joined
            .split_whitespace()
            .filter(|p| p.starts_with("tests/"))
            .collect();
        (
            format!("uv run ruff check {joined}"),
            if python.is_empty() {
                "echo skip-typecheck-no-python-changes".into()
            } else {
                format!("uv run mypy --follow-imports=silent {}", python.join(" "))
            },
            if python.is_empty() && tests.is_empty() {
                "echo skip-test-no-python-changes".into()
            } else {
                format!("uv run pytest -q {}", tests.join(" "))
            },
            String::new(),
        )
    } else {
        (
            "echo skip-lint-no-product-command".into(),
            "echo skip-typecheck-no-product-command".into(),
            "echo skip-test-no-product-command".into(),
            String::new(),
        )
    };
    let lint = override_command("MIR_PRE_COMMIT_LINT", lint);
    let typecheck = override_command("MIR_PRE_COMMIT_TYPECHECK", typecheck);
    let test = override_command("MIR_PRE_COMMIT_TEST", test);
    let build = override_command("MIR_PRE_COMMIT_BUILD", build);
    if !step(project, "lint", &lint) || !step(project, "typecheck", &typecheck) {
        return 2;
    }
    if !step(project, "test", &test) {
        if env::var("MIR_SUGGEST_TIER_CONFIRM").as_deref() != Ok("1") {
            eprintln!(
                "[hook SUGGEST block] pre-commit/test: test failed (set MIR_SUGGEST_TIER_CONFIRM=1 to bypass)"
            );
            return 2;
        }
        if let Err(error) = record_bypass(project) {
            eprintln!("project-hooks: cannot record suggest bypass: {error}");
        }
        eprintln!(
            "[hook SUGGEST bypass] pre-commit/test: test failed but MIR_SUGGEST_TIER_CONFIRM=1 set"
        );
    }
    if !step(project, "build", &build) {
        return 2;
    }
    0
}
