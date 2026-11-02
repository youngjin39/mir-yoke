use handoff_packet::executor_local::LocalConfig;
use serde_json::{Value, json};

#[test]
fn python_local_config_golden_cases() {
    let cases: Value = serde_json::from_str(include_str!("fixtures/executor_local.json")).unwrap();
    for case in cases.as_array().unwrap() {
        let config = if let Some(bytes) = case.get("bytes") {
            LocalConfig::parse_bytes(
                bytes
                    .as_array()
                    .unwrap()
                    .iter()
                    .map(|v| v.as_u64().unwrap() as u8)
                    .collect(),
            )
        } else {
            LocalConfig::parse(case["text"].as_str().unwrap())
        };
        let actual = match config {
            Err(error) => json!({"error": error.kind(), "message": error.to_string()}),
            Ok(config) => match case["operation"].as_str().unwrap() {
                "defaults" => json!({"value": config.defaults()}),
                "timeout" => match config.validate_timeout(
                    case.get("argument_json")
                        .map(|v| config.parse_argument(v.as_str().unwrap()).unwrap())
                        .as_ref(),
                ) {
                    Ok(()) => json!({"value": null}),
                    Err(error) => json!({"error": error.kind(), "message": error.to_string()}),
                },
                "sandbox" => match config.sandbox() {
                    Ok(value) => json!({"value": value}),
                    Err(error) => json!({"error": error.kind(), "message": error.to_string()}),
                },
                "verifier_env" => match config.verifier_env() {
                    Ok(value) => json!({"value": value}),
                    Err(error) => json!({"error": error.kind(), "message": error.to_string()}),
                },
                "retention" => match config.retention_days(case.get("argument")) {
                    Ok(value) => json!({"value": value}),
                    Err(error) => json!({"error": error.kind(), "message": error.to_string()}),
                },
                "verifiers" => match config.verifier_commands(&["check"]) {
                    Ok(value) => json!({"value": value}),
                    Err(error) => json!({"error": error.kind(), "message": error.to_string()}),
                },
                "attempts" => match config.validate_attempts(case["argument"].as_u64().unwrap()) {
                    Ok(()) => json!({"value": null}),
                    Err(error) => json!({"error": error.kind(), "message": error.to_string()}),
                },
                "input_size" => {
                    match config.validate_input_size(2 * case["argument"].as_u64().unwrap()) {
                        Ok(()) => json!({"value": null}),
                        Err(error) => json!({"error": error.kind(), "message": error.to_string()}),
                    }
                }
                "truthy" => json!({"value": [config.require_review(), config.child_env_filter()]}),
                other => panic!("unknown operation {other}"),
            },
        };
        assert_eq!(actual, case["expected"], "{}", case["name"]);
    }
}

#[test]
fn missing_file_defaults_and_read_errors() {
    let scratch =
        std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("target/executor-local-missing");
    let config = LocalConfig::load(&scratch).unwrap();
    assert_eq!(config.defaults()["artifact_retention_days"], 30);
    // An existing directory is an I/O error, not a missing configuration.
    let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR"));
    assert!(LocalConfig::read_path(root).is_err());
    let array_config = root.join("tests/fixtures/executor_local.json");
    assert_eq!(
        LocalConfig::read_path(&array_config)
            .unwrap_err()
            .to_string(),
        format!("{} must contain a JSON object", array_config.display())
    );
    let invalid_utf8 = root.join("tests/fixtures/executor_local_invalid_utf8.bin");
    assert_eq!(
        LocalConfig::read_path(&invalid_utf8).unwrap_err().kind(),
        "UnicodeDecodeError"
    );
}

#[test]
fn deep_json_fails_before_exhausting_the_native_stack() {
    let text = format!("{}0{}", "[".repeat(1024), "]".repeat(1024));
    assert_eq!(
        LocalConfig::parse(&text).unwrap_err().kind(),
        "RecursionError"
    );
}
