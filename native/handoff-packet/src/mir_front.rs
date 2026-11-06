//! Library-only root classification for POSIX argv, before subcommand dispatch.
#![cfg(unix)]
use std::{ffi::OsString, os::unix::ffi::OsStrExt};

pub const SUBCOMMANDS: [&str; 13] = [
    "bootstrap",
    "bootstrap-adoption",
    "capability",
    "context",
    "executor",
    "loop",
    "memory",
    "migrate",
    "policy",
    "project-hooks",
    "relations",
    "run-python",
    "runtime-manifest",
];

/// Return root-owned output, or defer a known command without executing it.
pub fn root(argv: &[OsString]) -> Option<(i32, Vec<u8>, Vec<u8>)> {
    if argv.is_empty() || matches!(argv[0].to_str(), Some("-h" | "--help")) {
        let mut names = SUBCOMMANDS;
        names.sort_unstable();
        let help = format!(
            "usage: mir <subcommand> [args]\nsubcommands: {}\n",
            names.join(", ")
        );
        return Some((
            if argv.is_empty() { 2 } else { 0 },
            help.into_bytes(),
            vec![],
        ));
    }
    let command = &argv[0];
    if command.to_str().is_some_and(|s| SUBCOMMANDS.contains(&s)) {
        return None;
    }
    let message = format!("unknown subcommand: {}\n", argv_repr(command.as_bytes()));
    Some((2, vec![], message.into_bytes()))
}

fn argv_repr(mut bytes: &[u8]) -> String {
    let mut points = Vec::new();
    while !bytes.is_empty() {
        match std::str::from_utf8(bytes) {
            Ok(s) => {
                points.extend(s.chars().map(u32::from));
                break;
            }
            Err(error) => {
                let (valid, rest) = bytes.split_at(error.valid_up_to());
                // valid_up_to is guaranteed to delimit valid UTF-8.
                points.extend(
                    std::str::from_utf8(valid)
                        .unwrap_or("")
                        .chars()
                        .map(u32::from),
                );
                let length = error.error_len().unwrap_or(rest.len());
                points.extend(rest[..length].iter().map(|b| 0xdc00 + u32::from(*b)));
                bytes = &rest[length..];
            }
        }
    }
    crate::executor_execute::repr_codepoints(&points)
}
