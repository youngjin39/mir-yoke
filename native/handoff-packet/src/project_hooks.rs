//! Generic project-hook entrypoint; hook families are added in later slices.
#![forbid(unsafe_code)]
use std::{
    env,
    ffi::OsString,
    io::{self, Write},
    process::ExitCode,
};

fn response(args: &[OsString]) -> (u8, &'static str, &'static str) {
    if args.iter().any(|arg| arg == "--mir-warmup") {
        return (0, "", "");
    }
    if args.len() == 1 && args[0] == "capabilities" {
        return (0, "mir-project-hooks-v1\n", "");
    }
    (64, "", "project-hooks: unknown subcommand\n")
}

fn main() -> ExitCode {
    let args: Vec<_> = env::args_os().skip(1).collect();
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
            (0, "mir-project-hooks-v1\n", "")
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
