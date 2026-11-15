//! Disposable Git process fixture; compiled by the integration test, never installed.
use std::io::{self, Write};

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    assert_eq!(args.first().map(String::as_str), Some("diff"));
    assert_eq!(args.get(1).map(String::as_str), Some("--name-only"));
    match std::env::var("MIR_TEST_GIT_MODE").unwrap().as_str() {
        "invalid-stdout" => io::stdout().write_all(&[255]).unwrap(),
        "invalid-stderr" => io::stderr().write_all(&[255]).unwrap(),
        "refusal" => {
            io::stderr().write_all(b"fixture git refusal\n").unwrap();
            std::process::exit(128);
        }
        mode @ ("changed" | "timeout") => {
            if mode == "timeout" && args.get(2).map(String::as_str) == Some("@{upstream}..HEAD") {
                std::thread::sleep(std::time::Duration::from_secs(11));
            }
            io::stdout()
                .write_all(std::env::var("MIR_TEST_GIT_CHANGED").unwrap().as_bytes())
                .unwrap();
        }
        other => panic!("unknown fixture Git mode: {other}"),
    }
}
