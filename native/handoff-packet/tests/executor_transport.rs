use handoff_packet::executor_transport::{CallOptions, Client};
use serde_json::{Value, json};
use std::{process::Command, time::Duration};

fn python() -> String {
    ["python3", "python"]
        .into_iter()
        .find(|p| {
            Command::new(p)
                .arg("--version")
                .output()
                .is_ok_and(|o| o.status.success())
        })
        .expect("Python required")
        .to_owned()
}

#[test]
fn shared_python_scenarios() {
    let cases: Value =
        serde_json::from_str(include_str!("fixtures/executor_transport.json")).unwrap();
    let seconds = regex::Regex::new(r"after [0-9.e+-]+s").unwrap();
    for case in cases.as_array().unwrap() {
        let mode = case["mode"].as_str().unwrap();
        let mut command = Command::new(python());
        command
            .arg(concat!(
                env!("CARGO_MANIFEST_DIR"),
                "/tests/fixtures/executor_transport_server.py"
            ))
            .arg(mode);
        let mut client =
            Client::spawn(command, Duration::from_secs(3), Duration::from_millis(100)).unwrap();
        let cancel = client.cancellation();
        let mut options = CallOptions::new("hello", ".");
        if mode == "blocked_send" {
            options.prompt = "x".repeat(2 * 1024 * 1024);
        }
        options.sandbox = "workspace-write".into();
        options.model = Some("fixture".into());
        options.base_instructions = Some("base".into());
        options.config = Some(json!({"effort":"medium"}));
        options.timeout = Some(Duration::from_millis(
            if matches!(
                mode,
                "deadline" | "thread_timeout" | "blocked_send" | "deadline_activity"
            ) {
                300
            } else {
                3000
            },
        ));
        options.stall_timeout = match mode {
            "stall" => Some(Duration::from_millis(150)),
            "heartbeat" => Some(Duration::from_millis(500)),
            _ => None,
        };
        let mut progress = |method: &str, _: &Value| {
            if mode == "cancel" && method == "test/cancel" {
                cancel.cancel();
            }
            if mode == "callback_error" && method == "test/callback" {
                return Err("fixture callback".into());
            }
            Ok(())
        };
        if matches!(
            mode,
            "normal" | "nested_limits" | "exit_before_response" | "reader_eof" | "cancel"
        ) {
            options.timeout = None;
        }
        let clock = std::time::Instant::now();
        let result = client.call(options, &mut progress);
        assert!(
            clock.elapsed() < Duration::from_secs(5),
            "{mode}: unbounded cleanup"
        );
        let observed = match result {
            Ok(r) => {
                json!({"text":r.content_text,"thread_id":r.thread_id,"model_id":r.model_id,"usage":r.token_usage,"tool_version":r.tool_version,"raw_result":r.raw_result})
            }
            Err(e) => {
                if let Some(found) = seconds.find(&e.to_string()) {
                    let raw = e.to_string();
                    let elapsed: f64 = raw[found.start() + 6..found.end() - 1].parse().unwrap();
                    assert!(
                        (0.0..4.0).contains(&elapsed),
                        "{mode}: invalid timer {elapsed}"
                    );
                }
                let message = seconds
                    .replace_all(&e.to_string(), "after <seconds>s")
                    .into_owned();
                json!({"error":e.python_class(),"message":message})
            }
        };
        client.close();
        assert_eq!(observed, case["expected"], "{mode}");
        assert_eq!(
            client.malformed_messages().len(),
            case["malformed"].as_u64().unwrap() as usize,
            "{mode}"
        );
        assert_eq!(
            client.stderr_lines().len(),
            case["stderr"].as_u64().unwrap() as usize,
            "{mode}"
        );
        assert_eq!(client.pending_count(), 0, "{mode}");
        assert!(!client.is_running(), "{mode}");
    }
}
