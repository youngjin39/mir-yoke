use handoff_packet::{executor_dispatch::CodexAttempt, executor_result_policy::ResultPolicy};
use serde_json::json;
use std::{fs, path::PathBuf};

fn policy() -> ResultPolicy {
    ResultPolicy::parse(&json!({
        "provider_output": "sanitize_persisted_text",
        "attempt_artifact": "result_json"
    }))
    .unwrap()
}

#[test]
fn provider_replaces_only_changed_output_and_preserves_metadata() {
    let clean = CodexAttempt {
        stdout: "\u{d55c}\u{ae00} clean".into(),
        ..Default::default()
    };
    assert!(policy().after_provider_call(&clean).unwrap().is_none());
    let raw = CodexAttempt {
        stdout: "token=hidden".into(),
        stderr: "é".repeat(17000),
        error_sig: "token=signature".into(),
        blocked_reason: Some("token=reason".into()),
        model_id: Some("model".into()),
        ..Default::default()
    };
    let output = policy().after_provider_call(&raw).unwrap().unwrap();
    assert_eq!(output.stdout, "token=[REDACTED]");
    assert_eq!(output.stderr.chars().count(), 16384);
    assert!(output.stderr.ends_with("\n...[truncated]...\n"));
    assert_eq!(output.error_sig, raw.error_sig);
    assert_eq!(output.blocked_reason, raw.blocked_reason);
    assert_eq!(output.model_id, raw.model_id);
}

#[test]
fn artifact_matches_python_order_unicode_newline_null_and_private_mode() {
    let root = std::env::var_os("MIR_NATIVE_TEST_SCRATCH")
        .map(PathBuf::from)
        .unwrap_or_else(std::env::temp_dir);
    fs::create_dir_all(&root).unwrap();
    let path = root.join(format!("result-policy-{}.json", std::process::id()));
    let result = CodexAttempt {
        exit_code: 1,
        error_sig: "token=signature".into(),
        stdout: "\u{d55c}\u{ae00}".into(),
        stderr: "password=hidden".into(),
        retryable: true,
        ..Default::default()
    };
    policy().after_run(&path, &result).unwrap();
    assert_eq!(
        fs::read_to_string(&path).unwrap(),
        concat!(
            "{\n  \"exit_code\": 1,\n  \"error_sig\": \"token=[REDACTED]\",\n",
            "  \"stdout\": \"\u{d55c}\u{ae00}\",\n  \"stderr\": \"password=[REDACTED]\",\n",
            "  \"lane_unavailable\": false,\n  \"retryable\": true,\n  \"blocked_reason\": null\n}\n"
        )
    );
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        assert_eq!(
            fs::metadata(&path).unwrap().permissions().mode() & 0o777,
            0o600
        );
    }
    fs::remove_file(path).unwrap();
}

#[test]
fn strict_schema_and_disabled_fields() {
    for value in [
        json!(null),
        json!({"extra":true}),
        json!({"provider_output":false}),
        json!({"provider_output":"custom"}),
        json!({"attempt_artifact":"custom"}),
    ] {
        assert!(ResultPolicy::parse(&value).is_err(), "{value}");
    }
    let empty = ResultPolicy::parse(&json!({})).unwrap();
    assert!(
        empty
            .after_provider_call(&CodexAttempt {
                stdout: "token=hidden".into(),
                ..Default::default()
            })
            .unwrap()
            .is_none()
    );
    empty
        .after_run(
            std::path::Path::new("missing-parent/result.json"),
            &CodexAttempt::default(),
        )
        .unwrap();
}

#[test]
fn dispatch_route_applies_policy_before_outcome_and_artifact() {
    use handoff_packet::executor_dispatch::{DispatchContext, DispatchOptions, run_dispatch};
    use std::process::Command;
    let root = std::env::var_os("MIR_NATIVE_TEST_SCRATCH")
        .map(PathBuf::from)
        .unwrap_or_else(std::env::temp_dir)
        .join(format!("result-policy-dispatch-{}", std::process::id()));
    fs::create_dir_all(root.join("config")).unwrap();
    for args in [
        vec!["init", "-q"],
        vec!["config", "user.name", "Fixture"],
        vec!["config", "user.email", "fixture@example.invalid"],
    ] {
        assert!(
            Command::new("git")
                .arg("-C")
                .arg(&root)
                .args(args)
                .status()
                .unwrap()
                .success()
        );
    }
    fs::write(root.join("code.txt"), "initial\n").unwrap();
    fs::write(
        root.join("config/mir-executor.local.json"),
        json!({
            "native_policy": {"version":1, "result_policy": {
                "provider_output":"sanitize_persisted_text", "attempt_artifact":"result_json"
            }}
        })
        .to_string(),
    )
    .unwrap();
    for args in [vec!["add", "-A"], vec!["commit", "-qm", "fixture"]] {
        assert!(
            Command::new("git")
                .arg("-C")
                .arg(&root)
                .args(args)
                .status()
                .unwrap()
                .success()
        );
    }
    let mut options = DispatchOptions::new(&root, "result-policy");
    options.worktrees_root = Some(root.join("worktrees"));
    let out = run_dispatch(&options, &mut DispatchContext::default(), |_, _| {
        Ok(CodexAttempt {
            stdout: "token=hidden".into(),
            blocked_reason: Some("password=hidden".into()),
            ..Default::default()
        })
    })
    .unwrap();
    assert_eq!(out.stdout, "token=[REDACTED]");
    let artifact = fs::read_to_string(&out.worktree.unwrap().result_path).unwrap();
    assert!(!artifact.contains("hidden"));
    assert_eq!(
        serde_json::from_str::<serde_json::Value>(&artifact).unwrap()["blocked_reason"],
        "password=[REDACTED]"
    );
    fs::remove_dir_all(root).unwrap();
}
