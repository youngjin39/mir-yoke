use handoff_packet::executor_policy_query::query;
use std::{collections::BTreeMap, ffi::OsString, fs, path::PathBuf};

#[test]
fn query_bytes_precedence_nulls_and_silent_decline() {
    let root = std::env::var_os("MIR_NATIVE_TEST_SCRATCH")
        .map(PathBuf::from)
        .unwrap_or_else(std::env::temp_dir)
        .join(format!("policy-query-{}", std::process::id()));
    fs::create_dir_all(root.join("config")).unwrap();
    let overlay = root.join("overlay.json");
    fs::write(&overlay, "{}").unwrap();
    let environment = BTreeMap::from([(
        "MIR_SUB_AGENT_POLICY".into(),
        overlay.to_str().unwrap().into(),
    )]);
    let invoke = |args: &[&str]| {
        query(
            &args.iter().map(OsString::from).collect::<Vec<_>>(),
            &root,
            &root,
            &environment,
        )
    };
    assert_eq!(
        invoke(&["policy-resolve", "--category", "unit"]),
        Some((
            "{\"model\": null, \"reasoning_effort\": null}\n".into(),
            String::new(),
            0
        ))
    );
    fs::write(root.join("config/model-routing.lock.json"),
              r#"{"policy":{"routing":{"by_category":{"unit":{"prefer":[{}, {"model":" m ","reasoning_effort":" high "}]}}}}}"#).unwrap();
    fs::write(&overlay, "malformed ignored overlay").unwrap();
    assert_eq!(
        invoke(&["policy-resolve", "--category=unit", "--format=text"]),
        Some(("model=m\nreasoning_effort=high\n".into(), String::new(), 0))
    );
    fs::write(root.join("config/model-routing.lock.json"), "{").unwrap();
    assert_eq!(invoke(&["policy-resolve", "--category", "unit"]), None);
    for args in [
        vec!["policy-resolve"],
        vec!["policy-resolve", "--category", "unit", "--format", "yaml"],
        vec!["policy-resolve", "--category", "unit", "--category", "edge"],
    ] {
        assert_eq!(invoke(&args), None);
    }
    fs::remove_file(root.join("config").join("model-routing.lock.json")).unwrap();
    let account = root.join("account");
    let rendered = account.join(".mir").join("model-routing");
    fs::create_dir_all(&rendered).unwrap();
    fs::write(
        rendered.join("sub-agent-policy.json"),
        r#"{"routing":{"default":{"model":"account-model"}}}"#,
    )
    .unwrap();
    let args = ["policy-resolve", "--category", "unit", "--format", "text"].map(OsString::from);
    assert_eq!(
        query(&args, &root, &account, &BTreeMap::new()),
        Some((
            "model=account-model\nreasoning_effort=\n".into(),
            String::new(),
            0
        ))
    );
    let missing = root.join("absent.json");
    let env = BTreeMap::from([(
        "MIR_SUB_AGENT_POLICY".into(),
        missing.to_str().unwrap().into(),
    )]);
    assert_eq!(
        query(&args, &root, &account, &env),
        Some((
            "model=account-model\nreasoning_effort=\n".into(),
            format!(
                "[mir policy] MIR_SUB_AGENT_POLICY names a missing file: {}; falling back to the rendered policy\n",
                missing.display()
            ),
            0
        ))
    );
    fs::remove_dir_all(root).unwrap();
}
