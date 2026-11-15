//! Isolate aborting stack probes in a subprocess; never overflow the test runner.
use handoff_packet::python_json;
use std::process::Command;

#[test]
fn deep_json_small_stack_probe() {
    let Ok(phase) = std::env::var("WT_DEEP_PHASE") else {
        return;
    };
    let result = std::thread::Builder::new()
        .stack_size(1024 * 1024)
        .spawn(move || {
            let raw = format!("{{\"ignored\":{}0{}}}", "[".repeat(9995), "]".repeat(9995));
            let parsed = python_json::parse(&raw);
            assert!(parsed.is_ok(), "parse Err: {:?}", parsed.as_ref().err());
            let value = parsed.unwrap();
            eprintln!("depth=9995 stack=1048576 parsed");
            if phase == "parsed" {
                std::mem::forget(value);
                return;
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
