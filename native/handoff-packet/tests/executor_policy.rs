use handoff_packet::executor_policy::Policy;
use serde_json::{Value, json};
#[test]
fn python_policy_goldens() {
    let cases: Value = serde_json::from_str(include_str!("fixtures/executor_policy.json")).unwrap();
    for case in cases.as_array().unwrap() {
        let policy = Policy::resolve(&case["data"]);
        let mut actual = policy.snapshot();
        actual["route"] = policy.category("unit");
        actual["fallback"] = policy.category("missing");
        actual["backend"] = json!(policy.backend(Some("codex"), Some("demo"), None, None));
        assert_eq!(actual, case["expected"], "{}", case["data"]);
    }
}
#[test]
fn backend_guard_aliases_unknown_and_explicit_models() {
    use handoff_packet::executor_policy::model_backend;
    let policy = Policy::resolve(&json!({"mode":"force_codex"}));
    for model in ["sonnet", "opus", "fable", "haiku", " CLAUDE-test "] {
        assert_eq!(model_backend(model), Some("claude"));
        assert!(policy.guard(model, "codex", false).is_err());
        assert!(policy.guard(model, "codex", true).is_ok());
    }
    for model in ["unknown", "codex", "", "gpt"] {
        assert_eq!(model_backend(model), None);
        assert!(policy.guard(model, "codex", false).is_ok());
    }
    assert_eq!(model_backend(" GPT-fixture "), Some("codex"));
}
#[test]
fn merged_lock_and_explicit_account_home_ignore_home_environment() {
    use handoff_packet::executor_policy::{load, merge};
    use std::{collections::BTreeMap, fs, path::PathBuf};
    let root = std::env::var_os("MIR_NATIVE_TEST_SCRATCH")
        .map(PathBuf::from)
        .unwrap_or_else(std::env::temp_dir)
        .join(format!("policy-{}", std::process::id()));
    fs::create_dir_all(root.join("config")).unwrap();
    fs::create_dir_all(root.join("account/.mir/model-routing")).unwrap();
    fs::write(
        root.join("account/.mir/model-routing/sub-agent-policy.json"),
        r#"{"mode":"force_claude"}"#,
    )
    .unwrap();
    let env = BTreeMap::from([(
        "HOME".into(),
        root.join("fake-home").to_str().unwrap().into(),
    )]);
    assert_eq!(
        load(&root, &root.join("account"), &env).mode(),
        "force_claude"
    );
    fs::write(
        root.join("config/sub-agent-policy.json"),
        r#"{"mode":"force_claude","delegation":{"default_backend":"claude"},"monitoring":{"a":1}}"#,
    )
    .unwrap();
    fs::write(
        root.join("config/model-routing.lock.json"),
        r#"{"policy":{"mode":"force_codex","monitoring":{"b":2}}}"#,
    )
    .unwrap();
    let policy = load(&root, &root.join("account"), &env);
    assert_eq!(policy.mode(), "force_codex");
    assert_eq!(policy.snapshot()["monitoring"], json!({"a":1,"b":2}));
    assert_eq!(
        merge(&json!({"routing":{"a":1}}), &json!({"routing":{"b":2}}))["routing"],
        json!({"b":2})
    );
    fs::write(
        root.join("config/model-routing.lock.json"),
        r#"{"policy":[]}"#,
    )
    .unwrap();
    assert_eq!(
        load(&root, &root.join("account"), &env).warning,
        "[mir policy] unreadable sub-agent policy (model-routing lock `policy` must be a JSON object); using select defaults\n"
    );
    fs::remove_dir_all(root).unwrap();
}
#[test]
fn python_agent_route_goldens() {
    use handoff_packet::executor_policy::agent_route;
    use std::{fs, path::PathBuf};
    let root = std::env::var_os("MIR_NATIVE_TEST_SCRATCH")
        .map(PathBuf::from)
        .unwrap_or_else(std::env::temp_dir)
        .join(format!("agents-{}", std::process::id()));
    fs::create_dir_all(root.join(".claude/agents")).unwrap();
    fs::create_dir_all(root.join(".codex/agents")).unwrap();
    let cases: Value = serde_json::from_str(include_str!("fixtures/executor_agents.json")).unwrap();
    for case in cases.as_array().unwrap() {
        fs::write(
            root.join(".claude/agents/reviewer.md"),
            case["source"].as_str().unwrap(),
        )
        .unwrap();
        let path = root.join(".codex/agents/reviewer.toml");
        if let Some(text) = case["codex"].as_str() {
            fs::write(&path, text).unwrap()
        } else {
            let _ = fs::remove_file(&path);
        }
        let actual = match agent_route(&root, "reviewer", &Policy::resolve(&case["policy"])) {
            Ok((route, warning)) => json!({"route":route,"warning":warning}),
            Err(error) => json!({"error":error}),
        };
        assert_eq!(actual, case["expected"]);
    }
    fs::remove_dir_all(root).unwrap();
}
#[test]
fn hook_routes_preserve_identity_and_repository_read_only_constraints() {
    use handoff_packet::executor_policy::narrow_agent_route;
    use std::{fs, path::PathBuf};
    let root = std::env::var_os("MIR_NATIVE_TEST_SCRATCH")
        .map(PathBuf::from)
        .unwrap_or_else(std::env::temp_dir)
        .join(format!("agent-hook-{}", std::process::id()));
    let agents = root.join(".claude").join("agents");
    fs::create_dir_all(&agents).unwrap();
    let route = json!({"target_agent":"custom","execution_backend":"codex","model":"hook-model","sandbox":"danger-full-access","base_instructions":"hook instructions"});
    assert_eq!(
        narrow_agent_route(&root, "custom", route.clone()).unwrap(),
        route
    );
    // Hook overrides need no executable backend in repository frontmatter.
    fs::write(
        agents.join("custom.md"),
        "---\r\ndisallowedTools: \"Write,\r\n  Edit\"\r\n---\r\nRepository instructions.\r\n",
    )
    .unwrap();
    let mut narrowed = route.clone();
    narrowed["sandbox"] = json!("read-only");
    assert_eq!(
        narrow_agent_route(&root, "custom", route.clone()).unwrap(),
        narrowed
    );
    assert_eq!(
        narrow_agent_route(&root, "codex-final-reviewer", route.clone()).unwrap(),
        narrowed
    );
    fs::write(agents.join("custom.md"), "invalid frontmatter").unwrap();
    assert_eq!(
        narrow_agent_route(&root, "custom", route.clone()).unwrap_err(),
        "agent definition requires leading frontmatter"
    );
    assert!(narrow_agent_route(&root, "../custom", route).is_err());
    fs::remove_dir_all(root).unwrap();
}
#[test]
fn windows_account_profile_rule_never_uses_home() {
    use handoff_packet::executor_policy::windows_account_home;
    use std::collections::BTreeMap;
    let mut env = BTreeMap::from([("HOME".into(), "Z:\\session".into())]);
    assert!(windows_account_home(&env).is_err());
    for profile in [
        "C:\\Users\\account",
        "D:/Profiles/account",
        "\\\\server\\profiles\\account",
    ] {
        env.insert("USERPROFILE".into(), profile.into());
        assert_eq!(windows_account_home(&env).unwrap().to_str(), Some(profile));
    }
    env.insert("USERPROFILE".into(), "relative".into());
    assert!(windows_account_home(&env).is_err());
}
#[test]
fn python_policy_loading_goldens() {
    use handoff_packet::executor_policy::load;
    use std::{collections::BTreeMap, fs, path::PathBuf};
    let root = std::env::var_os("MIR_NATIVE_TEST_SCRATCH")
        .map(PathBuf::from)
        .unwrap_or_else(std::env::temp_dir)
        .join(format!("load-{}", std::process::id()));
    fs::create_dir_all(root.join("config")).unwrap();
    fs::create_dir_all(root.join("account/.mir/model-routing")).unwrap();
    let cases: Value =
        serde_json::from_str(include_str!("fixtures/executor_policy_load.json")).unwrap();
    for case in cases.as_array().unwrap() {
        for (key, path) in [
            ("local", "config/sub-agent-policy.json"),
            ("lock", "config/model-routing.lock.json"),
            (
                "overlay",
                "account/.mir/model-routing/sub-agent-policy.json",
            ),
        ] {
            let path = root.join(path);
            if let Some(text) = case[key].as_str() {
                fs::write(path, text).unwrap()
            } else {
                let _ = fs::remove_file(path);
            }
        }
        assert_eq!(
            load(&root, &root.join("account"), &BTreeMap::new()).snapshot(),
            case["expected"],
            "{case}"
        );
    }
    fs::remove_dir_all(root).unwrap();
}
