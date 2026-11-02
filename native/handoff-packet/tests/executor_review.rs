use handoff_packet::{
    executor_dispatch::CodexAttempt,
    executor_dispatch_provider::Error,
    executor_review::{diagnostic_token, evidence, review},
};
use serde_json::{Value, json};
use std::{
    path::Path,
    process::Command,
    time::{Duration, Instant},
};

fn python() -> Command {
    Command::new(
        ["python3", "python"]
            .into_iter()
            .find(|name| {
                Command::new(name)
                    .arg("--version")
                    .output()
                    .is_ok_and(|o| o.status.success())
            })
            .unwrap(),
    )
}
fn fake(mode: &str) -> Command {
    let mut command = python();
    command
        .arg(concat!(
            env!("CARGO_MANIFEST_DIR"),
            "/tests/fixtures/executor_review_server.py"
        ))
        .arg(mode);
    command
}
#[test]
fn strict_review_evidence_matches_python() {
    let rows: Value = serde_json::from_str(include_str!("fixtures/executor_review.json")).unwrap();
    for row in rows.as_array().unwrap() {
        let attempt = CodexAttempt {
            stdout: row["content"].as_str().unwrap().into(),
            ..Default::default()
        };
        assert_eq!(evidence(Some(&attempt)).to_value(), row["expected"]);
    }
    assert_eq!(evidence(None).reason, "reviewer-missing");
    for (code, reason) in [(124, "reviewer-timeout"), (1, "reviewer-unavailable")] {
        let attempt = CodexAttempt {
            exit_code: code,
            stderr: "diagnostic".into(),
            blocked_reason: Some(reason.into()),
            ..Default::default()
        };
        let result = evidence(Some(&attempt));
        assert!(!result.passed);
        assert_eq!(result.reason, reason);
        assert_eq!(result.content, "diagnostic");
    }
}
#[test]
fn read_only_reviewer_transport_and_metadata() {
    let protocol: Value =
        serde_json::from_str(include_str!("fixtures/executor_review_protocol.json")).unwrap();
    for (mode, passed, reason) in [
        ("approve", true, "ok"),
        ("reject", false, "unsafe"),
        ("malformed", false, "reviewer-malformed"),
        ("empty", false, "reviewer-malformed"),
        ("unicode", true, "ok"),
    ] {
        let mut calls = 0;
        let output = review(
            fake(mode),
            Path::new("."),
            Path::new("."),
            &if mode == "unicode" {
                vec![
                    "pkg/\u{ac00}\u{1f600}\u{7f}.py".into(),
                    "quote\"\\.py".into(),
                ]
            } else {
                vec!["pkg/mod.py".into()]
            },
            Some(Duration::from_secs(15)),
            &mut |attempt, metadata| {
                calls += 1;
                assert_eq!(
                    metadata["token_usage"],
                    json!({"input_tokens":12,"output_tokens":3,"total_tokens":15})
                );
                assert_eq!(metadata["model"], "fixture-model");
                assert_eq!(metadata["tool_version"], "review-fixture/1");
                assert_eq!(metadata["attempt"], 1);
                assert_eq!(metadata["prompt_sha256"].as_str().unwrap().len(), 64);
                Ok(attempt)
            },
        )
        .unwrap();
        assert_eq!(calls, 1);
        assert_eq!(
            output.evidence.passed, passed,
            "{mode}: {:?}",
            output.evidence
        );
        assert_eq!(output.evidence.reason, reason);
        assert_eq!(output.attempt.tokens_used.len(), 3);
        let oracle = protocol
            .as_array()
            .unwrap()
            .iter()
            .find(|row| row["mode"] == mode)
            .unwrap();
        assert_eq!(output.evidence.to_value(), oracle["expected"]);
        let mut metadata = output.metadata;
        metadata.as_object_mut().unwrap().remove("elapsed_seconds");
        assert_eq!(metadata, oracle["metadata"]);
    }
}
#[test]
fn missing_and_timeout_block_and_return_diagnostics() {
    let pattern = regex::Regex::new(r"after [0-9.e+-]+s").unwrap();
    let protocol: Value =
        serde_json::from_str(include_str!("fixtures/executor_review_protocol.json")).unwrap();
    for mode in ["missing", "timeout"] {
        let start = Instant::now();
        let output = review(
            fake(mode),
            Path::new("."),
            Path::new("."),
            &["pkg/mod.py".into()],
            Some(Duration::from_secs(3)),
            &mut |a, _| Ok(a),
        )
        .unwrap();
        assert!(!output.evidence.passed);
        assert_eq!(
            output.evidence.reason,
            if mode == "timeout" {
                "reviewer-timeout"
            } else {
                "reviewer-unavailable"
            }
        );
        assert!(!output.evidence.content.is_empty());
        let oracle = protocol
            .as_array()
            .unwrap()
            .iter()
            .find(|row| row["mode"] == mode)
            .unwrap();
        let mut observed = output.evidence.to_value();
        if mode == "timeout" {
            observed["content"] = pattern
                .replace_all(output.evidence.content.as_str(), "after <seconds>s")
                .to_string()
                .into();
        }
        assert_eq!(observed, oracle["expected"]);
        let mut metadata = output.metadata;
        metadata.as_object_mut().unwrap().remove("elapsed_seconds");
        assert_eq!(metadata, oracle["metadata"]);
        assert!(start.elapsed() < Duration::from_secs(20));
    }
    let output = review(
        Command::new("missing-fixture-review-executable"),
        Path::new("."),
        Path::new("."),
        &[],
        Some(Duration::from_secs(3)),
        &mut |a, _| Ok(a),
    )
    .unwrap();
    assert_eq!(output.evidence.reason, "reviewer-unavailable");
}
#[test]
fn hook_replacement_and_errors_are_preserved() {
    let output = review(
        fake("approve"),
        Path::new("."),
        Path::new("."),
        &["pkg/mod.py".into()],
        Some(Duration::from_secs(15)),
        &mut |mut a, _| {
            a.exit_code = 1;
            a.blocked_reason = Some("budget-denied".into());
            Ok(a)
        },
    )
    .unwrap();
    assert!(!output.evidence.passed);
    assert_eq!(output.evidence.reason, "budget-denied");
    assert!(
        review(
            fake("approve"),
            Path::new("."),
            Path::new("."),
            &["pkg/mod.py".into()],
            Some(Duration::from_secs(15)),
            &mut |_, _| Err(Error::Output("hook failed".into()))
        )
        .is_err()
    );
}
#[test]
fn diagnostic_tokens_match_python() {
    assert_eq!(
        diagnostic_token(
            Some("noise dispatch_status=blocked other=ok dispatch_status=later"),
            "dispatch_status"
        ),
        Some("blocked")
    );
    assert_eq!(
        diagnostic_token(Some("status= other=x"), "status"),
        Some("")
    );
    assert_eq!(diagnostic_token(None, "status"), None);
}

#[test]
fn invalid_timeout_blocks_before_provider_launch() {
    assert!(
        review(
            Command::new("must-not-launch-review-fixture"),
            Path::new("."),
            Path::new("."),
            &[],
            Some(Duration::ZERO),
            &mut |a, _| Ok(a)
        )
        .is_err()
    );
}
