#![forbid(unsafe_code)]
#![deny(clippy::unwrap_used, clippy::expect_used, clippy::panic)]

mod adoption;
mod bootstrap_enforce;
mod bootstrap_json;
mod bootstrap_state;
mod digest;

use std::io::{self, Read, Write};

fn main() {
    if std::env::args_os().nth(1).as_deref() == Some(std::ffi::OsStr::new("--mir-warmup")) {
        return;
    }
    let args: Vec<_> = std::env::args_os().skip(1).collect();
    if args
        .first()
        .is_some_and(|a| a == "enforce" || a == "instructions")
    {
        let enforce = args[0] == "enforce";
        let count = if enforce { 4 } else { 5 };
        if args.len() != count || args[1] != "--protocol" || args[2] != "1" {
            std::process::exit(64);
        }
        let root = std::path::Path::new(&args[count - 1]);
        let (out, err, code) = if enforce {
            let mut payload = Vec::new();
            if io::stdin().read_to_end(&mut payload).is_err() {
                std::process::exit(64);
            }
            let (err, code) = bootstrap_enforce::enforce(&payload, root);
            (String::new(), err, code)
        } else {
            let Some(state) = args[3].to_str() else {
                std::process::exit(64);
            };
            (
                bootstrap_enforce::instructions(state, root),
                String::new(),
                0,
            )
        };
        if io::stdout().write_all(out.as_bytes()).is_err()
            || io::stderr().write_all(err.as_bytes()).is_err()
        {
            std::process::exit(64);
        }
        std::process::exit(code);
    }
    if args.len() > 1 && args.first().is_some_and(|a| a == "state") {
        if args.len() != 4 || args[1] != "--protocol" || args[2] != "1" {
            std::process::exit(64);
        }
        let (result, code) = bootstrap_state::evaluate(std::path::Path::new(&args[3]));
        let output = format!("{result}\n");
        if io::stdout().write_all(output.as_bytes()).is_err() {
            std::process::exit(64);
        }
        std::process::exit(code);
    }
    let (output, code) = if args.len() == 1 && args[0] == "--capabilities" {
        (
            "{\"protocols\":[\"mir.bootstrap-state@1\",\"mir.bootstrap-enforce@1\",\"mir.bootstrap-instructions@1\"]}\n",
            0,
        )
    } else if args.len() == 1 && args[0] == "--version" {
        ("bootstrap-gate 0.1.0\n", 0)
    } else if args.len() == 1 {
        match adoption::evaluate(std::path::Path::new(&args[0])) {
            Some(true) => ("ready\n", 0),
            Some(false) => ("invalid\n", 1),
            None => ("", 64),
        }
    } else {
        ("", 64)
    };
    if io::stdout().write_all(output.as_bytes()).is_err() {
        std::process::exit(64);
    }
    std::process::exit(code);
}
