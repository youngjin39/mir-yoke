//! Isolate aborting stack probes in a subprocess; never overflow the test runner.
use handoff_packet::python_json;
use std::process::Command;
use std::{fs, io::Write, process::Stdio};

#[test]
fn deep_json_platform_admission() {
    let capture: serde_json::Value =
        serde_json::from_str(include_str!("fixtures/windows-deep.json")).unwrap();
    for boundary in capture["boundaries"].as_array().unwrap() {
        let consumer = boundary["consumer"].as_str().unwrap();
        for depth in [2996, 2997, 9990, 10000] {
            let limit = if cfg!(windows) { 2997 } else { 9997 };
            let expected = &boundary[if depth < limit {
                "last_baseline"
            } else {
                "first_changed"
            }]["reference"];
            let root = tempfile::tempdir().unwrap();
            let nested = format!("{}0{}", "[".repeat(depth), "]".repeat(depth));
            let mut cmd = Command::new(if consumer == "handoff" {
                env!("CARGO_BIN_EXE_handoff-packet")
            } else {
                env!("CARGO_BIN_EXE_project-hooks")
            });
            cmd.current_dir(root.path())
                .env("HOME", root.path())
                .env("USERPROFILE", root.path())
                .env("PATH", "")
                .stdout(Stdio::piped())
                .stderr(Stdio::piped());
            let ledger = root.path().join("tasks/tdd.json");
            let input = if consumer == "handoff" {
                cmd.stdin(Stdio::piped());
                format!(
                    "{{\"hook_event_name\":\"PreToolUse\",\"tool_name\":\"Bash\",\"prompt\":\"Write a handoff for agent receiver. Do not run any commands. Owner instruction: no commands.\",\"ignored\":{nested}}}"
                )
            } else {
                fs::create_dir(root.path().join("tasks")).unwrap();
                fs::write(&ledger, format!("{{\"changes\":[],\"metadata\":{nested}}}")).unwrap();
                cmd.args(["tdd-matrix", "prewrite"])
                    .arg(root.path())
                    .arg("src/a.py");
                String::new()
            };
            let before = fs::read(&ledger).ok();
            let mut child = cmd.spawn().unwrap();
            if let Some(mut stdin) = child.stdin.take() {
                stdin.write_all(input.as_bytes()).unwrap();
            }
            let result = child.wait_with_output().unwrap();
            let eol = if cfg!(windows) { "\r\n" } else { "\n" };
            let stderr = expected["final_exception"].as_str().map_or_else(
                || expected["stderr"].as_str().unwrap().to_owned(),
                |error| format!("{error}\r\n"),
            );
            let text = |value: &str| value.replace("\r\n", eol).into_bytes();
            assert_eq!(
                (result.status.code(), result.stdout, result.stderr),
                (
                    expected["code"].as_i64().map(|code| code as i32),
                    text(expected["stdout"].as_str().unwrap()),
                    text(&stderr)
                ),
                "{consumer} depth={depth}"
            );
            assert_eq!(fs::read(ledger).ok(), before, "{consumer} depth={depth}");
        }
    }
}

#[test]
fn deep_json_small_stack_probe() {
    let Ok(phase) = std::env::var("WT_DEEP_PHASE") else {
        return;
    };
    let result = std::thread::Builder::new()
        .stack_size(1024 * 1024)
        .spawn(move || {
            let depth = if cfg!(windows) { 2995 } else { 9995 };
            let raw = format!(
                "{{\"ignored\":{}0{}}}",
                "[".repeat(depth),
                "]".repeat(depth)
            );
            let parsed = python_json::parse(&raw);
            assert!(parsed.is_ok(), "parse Err: {:?}", parsed.as_ref().err());
            let mut value = parsed.unwrap();
            eprintln!("depth={depth} stack=1048576 parsed");
            if phase == "parsed" {
                std::mem::forget(value);
                return;
            }
            // Disposal stays exercised at depth 9995 even past Windows admission.
            for _ in depth..9995 {
                value = python_json::Value::Array(vec![value]);
            }
            if phase == "drop-python" {
                python_json::discard(value);
                eprintln!("dropped python Value");
                return;
            }
            let converted = value.to_serde();
            eprintln!("converted");
            std::mem::forget(value);
            if phase == "converted" {
                std::mem::forget(converted);
            } else {
                python_json::discard_serde(converted);
                eprintln!("dropped serde Value");
            }
        });
    assert!(result.is_ok(), "spawn Err: {:?}", result.as_ref().err());
    let joined = result.unwrap().join();
    assert!(joined.is_ok(), "join Err: {:?}", joined.err());
}

#[test]
fn deep_json_small_stack() {
    let mut failures = Vec::new();
    for phase in ["parsed", "converted", "drop-python", "drop-serde"] {
        let output = Command::new(std::env::current_exe().unwrap())
            .args(["--exact", "deep_json_small_stack_probe", "--nocapture"])
            .env("WT_DEEP_PHASE", phase)
            .output()
            .unwrap();
        if !output.status.success() {
            failures.push(format!(
                "{phase}: {:?}; Err: {}",
                output.status,
                String::from_utf8_lossy(&output.stderr)
            ));
        }
    }
    assert!(failures.is_empty(), "{}", failures.join("\n"));
}
