//! Root classification before subcommand dispatch.
use std::ffi::OsString;

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
    let message = format!(
        "unknown subcommand: {}\n",
        crate::executor_text::repr_points(&crate::executor_text::os_points(command))
    );
    Some((2, vec![], message.into_bytes()))
}
