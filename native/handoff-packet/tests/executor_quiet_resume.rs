use handoff_packet::executor_target_policy::NativePolicy;
use serde_json::{Value, json};
use std::{collections::BTreeMap, fs, path::PathBuf};

#[test]
fn resume_fill_schema_and_ownership() {
    let declaration = json!({"version":1,
        "brief_profile":{"name":"base_v1"},
        "brief_controls":{"mode":"resume_fill"},
        "verifier_aliases":{"configuration_root":"initial"}});
    let policy = NativePolicy::parse(&declaration).unwrap();
    assert_eq!(policy.covered_hooks(), ["pre_execute", "validate_brief"]);
    for (key, value) in [
        ("brief_profile", json!({"name":"closed_verifier_v2"})),
        ("brief_controls", json!({"mode":"unknown"})),
        (
            "brief_controls",
            json!({"mode":"resume_fill","unknown":true}),
        ),
        ("verifier_aliases", json!({"configuration_root":"target"})),
    ] {
        let mut invalid = declaration.clone();
        invalid[key] = value;
        assert!(NativePolicy::parse(&invalid).is_err());
    }
    for key in ["brief_profile", "verifier_aliases"] {
        let mut invalid = declaration.clone();
        invalid.as_object_mut().unwrap().remove(key);
        assert!(NativePolicy::parse(&invalid).is_err());
    }
    let absent = NativePolicy::parse(&json!({"version":1,"target_admission":{}})).unwrap();
    assert!(!absent.covered_hooks().contains(&"validate_brief"));
}

#[test]
fn captured_resume_patches_and_failures_match() {
    let fixture: Value = serde_json::from_str(include_str!(
        "../../../tests/fixtures/executor_quiet_resume.json"
    ))
    .unwrap();
    let root = std::env::var_os("MIR_NATIVE_TEST_SCRATCH")
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("target/test-scratch"))
        .join(format!("resume-oracle-{}", std::process::id()));
    fs::create_dir_all(root.join("config")).unwrap();
    fs::write(
        root.join("config/mir-executor.local.json"),
        r#"{"verifiers":{"offline":["check"],"last":["check"],"literal":["other"]}}"#,
    )
    .unwrap();
    let policy = NativePolicy::parse(&json!({"version":1,
        "brief_profile":{"name":"base_v1"},
        "brief_controls":{"mode":"resume_fill"},
        "verifier_aliases":{"configuration_root":"initial"}}))
    .unwrap();
    for case in fixture["cases"].as_array().unwrap() {
        let path = root.join("brief.json");
        fs::write(&path, case["raw"].as_str().unwrap()).unwrap();
        if case["missing"] == true {
            fs::remove_file(&path).unwrap();
        }
        // Substitute the root as JSON string content: Windows paths carry backslashes.
        let escaped_root = json!(root.to_string_lossy()).to_string();
        let escaped_root = &escaped_root[1..escaped_root.len() - 1];
        let mut args: Value =
            serde_json::from_str(&case["args"].to_string().replace("<root>", escaped_root))
                .unwrap();
        let result = policy.pre_execute(&root, &root, &root, &mut args, &BTreeMap::new());
        let normalize = |value: &str| value.replace(root.to_str().unwrap(), "<root>");
        match result {
            Ok(()) => assert!(case["kind"].is_null(), "{}", case["name"]),
            Err(error) => {
                assert_eq!(error.kind, case["kind"], "{}", case["name"]);
                assert_eq!(
                    normalize(&error.message),
                    case["message"],
                    "{}",
                    case["name"]
                );
                assert_eq!(
                    normalize(error.stderr.as_deref().unwrap_or("")),
                    case["stderr"],
                    "{}",
                    case["name"]
                );
            }
        }
        let patch: Value =
            serde_json::from_str(&args.to_string().replace(escaped_root, "<root>")).unwrap();
        assert_eq!(patch, case["patch"], "{}", case["name"]);
    }
    fs::remove_dir_all(root).unwrap();
}
