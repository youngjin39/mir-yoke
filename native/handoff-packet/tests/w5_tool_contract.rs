// This cutover freezes POSIX Python output; Windows retirement is deferred.
#![cfg(unix)]
use serde::Deserialize;
use std::io::Write;
use std::process::{Command, Stdio};

#[derive(Deserialize)]
struct Fixture {
    cases: Vec<Case>,
}

#[derive(Deserialize)]
struct Case {
    id: String,
    stdin: String,
    python: Expected,
    native: Option<Expected>,
}

#[derive(Deserialize)]
struct Expected {
    exit: i32,
    stdout: String,
    stderr: String,
}

#[test]
fn tool_contract_replays_python_reference() {
    let fixture: Fixture =
        serde_json::from_str(include_str!("fixtures/w5/tool-contract.json")).unwrap();
    assert!(!fixture.cases.is_empty());

    for case in fixture.cases {
        let expected = case.native.unwrap_or(case.python);
        let mut child = Command::new(env!("CARGO_BIN_EXE_project-hooks"))
            .arg("tool-contract")
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .unwrap();
        let write_result = child.stdin.take().unwrap().write_all(case.stdin.as_bytes());
        let output = child.wait_with_output().unwrap();

        assert_eq!(
            output.status.code(),
            Some(expected.exit),
            "{}: {}",
            case.id,
            String::from_utf8_lossy(&output.stderr)
        );
        write_result.unwrap();
        assert_eq!(output.stdout, expected.stdout.as_bytes(), "{}", case.id);
        assert_eq!(
            String::from_utf8(output.stderr).unwrap(),
            expected.stderr,
            "{}",
            case.id
        );
    }
}
