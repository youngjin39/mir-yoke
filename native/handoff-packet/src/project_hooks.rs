//! Generic project-hook entrypoint; shell registrations remain unchanged.
#![forbid(unsafe_code)]
mod checkpoint;
mod compact_snapshot;
mod post_edit_check;
mod pre_commit_verification;
mod pre_tool_use;
mod prompt_submit;
mod python_decimal;
mod stop_audit;
mod tdd_ledger;

use std::{
    env,
    ffi::OsString,
    io::{self, Read, Write},
    process::ExitCode,
};

// The release smoke reads this literal to check the full capabilities output.
const CAPABILITIES: &str = "mir-project-hooks-v1\nmir-project-hooks-compact-v1\nmir-project-hooks-tdd-v1\nmir-project-hooks-post-edit-v1\nmir-project-hooks-prompt-v1\nmir-project-hooks-stop-v1\nmir-project-hooks-session-start-v1\nmir-project-hooks-pre-commit-v1\nmir-project-hooks-pre-tool-use-v1\n";

fn response(args: &[OsString]) -> (u8, &'static str, &'static str) {
    if args.iter().any(|arg| arg == "--mir-warmup") {
        return (0, "", "");
    }
    if args.len() == 1 && args[0] == "capabilities" {
        return (0, CAPABILITIES, "");
    }
    (64, "", "project-hooks: unknown subcommand\n")
}

fn main() -> ExitCode {
    let args: Vec<_> = env::args_os().skip(1).collect();
    if args.len() == 1 && args[0] == "post-edit-memory-sync" {
        let project = std::path::PathBuf::from(
            env::var_os("CLAUDE_PROJECT_DIR")
                .filter(|p| !p.is_empty())
                .unwrap_or_else(|| ".".into()),
        );
        let mut input = Vec::new();
        if io::stdin().read_to_end(&mut input).is_err() {
            return ExitCode::SUCCESS;
        }
        return match handoff_packet::post_edit_memory_sync::run(&project, &input) {
            Ok(()) => ExitCode::SUCCESS,
            Err(error) => {
                let _ = io::stderr().write_all(error.as_bytes());
                ExitCode::FAILURE
            }
        };
    }
    if args.len() == 1 && args[0] == "pre-tool-use" {
        return ExitCode::from(pre_tool_use::run());
    }
    if args.len() == 1 && args[0] == "pre-commit-verification" {
        return ExitCode::from(pre_commit_verification::run());
    }
    if args.len() == 1 && args[0] == "session-start" {
        let project = std::path::PathBuf::from(
            env::var_os("CLAUDE_PROJECT_DIR")
                .filter(|path| !path.is_empty())
                .unwrap_or_else(|| ".".into()),
        );
        return match io::stdout().write_all(handoff_packet::session_start::run(&project).as_bytes())
        {
            Ok(()) => ExitCode::SUCCESS,
            Err(_) => ExitCode::FAILURE,
        };
    }
    if args.len() == 1 && (args[0] == "stop-audit" || args[0] == "stop-failure-audit") {
        stop_audit::run(args[0] == "stop-failure-audit");
        return ExitCode::SUCCESS;
    }
    if args.len() == 1 && args[0] == "prompt-submit" {
        let (stdout, stderr) = prompt_submit::run(io::stdin().lock());
        if io::stdout()
            .write_all(stdout.as_bytes())
            .and_then(|()| io::stderr().write_all(stderr.as_bytes()))
            .is_err()
        {
            return ExitCode::FAILURE;
        }
        return ExitCode::SUCCESS;
    }
    if args.len() == 1 && args[0] == "post-edit-check" {
        let project = std::path::PathBuf::from(
            env::var_os("CLAUDE_PROJECT_DIR")
                .filter(|p| !p.is_empty())
                .unwrap_or_else(|| ".".into()),
        );
        let mut input = Vec::new();
        let _ = io::stdin().read_to_end(&mut input);
        let stdout = post_edit_check::scan(&project, &input);
        let _ = io::stdout().write_all(stdout.as_bytes());
        return ExitCode::SUCCESS;
    }
    if args
        .first()
        .is_some_and(|a| a == "tdd-matrix" || a == "tdd-guard")
    {
        let strings: Option<Vec<String>> = args
            .iter()
            .skip(1)
            .map(|a| a.to_str().map(str::to_owned))
            .collect();
        let Some(strings) = strings else {
            return ExitCode::from(64);
        };
        let (code, stdout, stderr) = if args[0] == "tdd-matrix" {
            tdd_ledger::matrix(&strings)
        } else {
            let project = std::path::PathBuf::from(
                env::var_os("CLAUDE_PROJECT_DIR")
                    .filter(|p| !p.is_empty())
                    .unwrap_or_else(|| ".".into()),
            );
            tdd_ledger::guard(&project, strings.first().map(String::as_str).unwrap_or(""))
        };
        // tdd-matrix: match Python text streams, including the final exception
        // line. tdd-guard replaces a Bash `echo`, which writes LF.
        #[cfg(windows)]
        let (stdout, stderr) = if args[0] == "tdd-matrix" {
            (stdout.replace('\n', "\r\n"), stderr.replace('\n', "\r\n"))
        } else {
            (stdout, stderr)
        };
        if io::stdout()
            .write_all(stdout.as_bytes())
            .and_then(|()| io::stderr().write_all(stderr.as_bytes()))
            .is_err()
        {
            return ExitCode::FAILURE;
        }
        return ExitCode::from(code);
    }
    if (args.len() == 1 && (args[0] == "pre-compact" || args[0] == "session-end"))
        || (args.len() == 3 && args[0] == "invocation-log")
    {
        let project = std::path::PathBuf::from(
            env::var_os("CLAUDE_PROJECT_DIR")
                .filter(|p| !p.is_empty())
                .unwrap_or_else(|| ".".into()),
        );
        if args[0] == "invocation-log" {
            let Some(name) = args[1].to_str() else {
                return ExitCode::from(64);
            };
            let Some(exit) = args[2].to_str().and_then(|value| value.parse::<u8>().ok()) else {
                return ExitCode::from(64);
            };
            checkpoint::telemetry(&project, name, i32::from(exit), std::time::Instant::now());
            return ExitCode::from(exit);
        }
        let (mut stdout, stderr) = checkpoint::pre_compact(&project);
        if args[0] == "session-end" {
            stdout.push_str(&format!(
                "[SessionEnd] Closeout state: {}\n",
                project
                    .join("tasks/handoffs/session-handoff-LATEST.md")
                    .display()
            ));
        }
        let _ = io::stdout().write_all(stdout.as_bytes());
        let _ = io::stderr().write_all(stderr.as_bytes());
        return ExitCode::SUCCESS;
    }
    if args.len() == 1 && (args[0] == "compact-resume" || args[0] == "post-compact") {
        let project = env::var_os("CLAUDE_PROJECT_DIR")
            .filter(|path| !path.is_empty())
            .unwrap_or_else(|| ".".into());
        let project = std::path::PathBuf::from(project);
        let path = project.join("tasks/handoffs/session-handoff-LATEST.md");
        let started = std::time::Instant::now();
        let mut input = Vec::new();
        // PostCompact ignores stdin, as the shell reference does.
        let stdout = if args[0] == "post-compact" {
            compact_snapshot::post_compact(&path)
        } else {
            let _ = io::stdin().read_to_end(&mut input);
            compact_snapshot::compact_resume(&path, &input)
        };
        if args[0] == "post-compact" || !stdout.is_empty() {
            checkpoint::telemetry(&project, args[0].to_str().unwrap(), 0, started);
        }
        return match io::stdout().write_all(stdout.as_bytes()) {
            Ok(()) => ExitCode::SUCCESS,
            Err(error) => {
                eprintln!("project-hooks: {error}");
                ExitCode::FAILURE
            }
        };
    }
    let (code, stdout, stderr) = response(&args);
    if stdout.is_empty() && stderr.is_empty() {
        return ExitCode::from(code);
    }
    if let Err(error) = io::stdout()
        .write_all(stdout.as_bytes())
        .and_then(|()| io::stderr().write_all(stderr.as_bytes()))
    {
        eprintln!("project-hooks: {error}");
        return ExitCode::FAILURE;
    }
    ExitCode::from(code)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn capability_probe() {
        assert_eq!(
            response(&["capabilities".into()]),
            (
                0,
                "mir-project-hooks-v1\nmir-project-hooks-compact-v1\nmir-project-hooks-tdd-v1\nmir-project-hooks-post-edit-v1\nmir-project-hooks-prompt-v1\nmir-project-hooks-stop-v1\nmir-project-hooks-session-start-v1\nmir-project-hooks-pre-commit-v1\nmir-project-hooks-pre-tool-use-v1\n",
                ""
            )
        );
    }

    #[test]
    fn warmup_returns_before_dispatch() {
        for args in [
            vec!["--mir-warmup".into()],
            vec!["unknown".into(), "--mir-warmup".into()],
        ] {
            assert_eq!(response(&args), (0, "", ""));
        }
    }

    #[test]
    fn unknown_subcommand_is_explicit() {
        for args in [
            vec![],
            vec!["unknown".into()],
            vec!["capabilities".into(), "extra".into()],
        ] {
            assert_eq!(
                response(&args),
                (64, "", "project-hooks: unknown subcommand\n")
            );
        }
    }
}
