#![forbid(unsafe_code)]
#![deny(clippy::unwrap_used, clippy::expect_used, clippy::panic)]

mod adoption;
mod digest;

use std::io::{self, Write};

fn main() {
    if std::env::args_os().nth(1).as_deref() == Some(std::ffi::OsStr::new("--mir-warmup")) {
        return;
    }
    let args: Vec<_> = std::env::args_os().skip(1).collect();
    let (output, code) = if args.len() == 1 && args[0] == "--version" {
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
