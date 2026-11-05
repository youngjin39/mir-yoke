use handoff_packet::codex_binary::windows_codex_binary;

#[test]
fn shared_windows_resolution_fixtures() {
    let cases: serde_json::Value =
        serde_json::from_str(include_str!("fixtures/codex-resolution.json")).unwrap();
    for case in cases.as_array().unwrap() {
        let files = case["files"].as_array().unwrap();
        let actual = windows_codex_binary(
            case["path"].as_str().unwrap(),
            case["pathext"].as_str().unwrap(),
            |name| {
                files
                    .iter()
                    .any(|file| file.as_str().unwrap().eq_ignore_ascii_case(name))
            },
        );
        assert_eq!(
            actual,
            case["expected"].as_str().unwrap(),
            "{}",
            case["name"]
        );
    }
}

#[test]
fn explicit_override_is_preserved() {
    let mut environment = std::collections::BTreeMap::new();
    environment.insert("CODEX_BIN".into(), "custom codex.cmd".into());
    let before = environment.clone();
    assert_eq!(
        handoff_packet::codex_binary::resolve(&environment),
        "custom codex.cmd"
    );
    assert_eq!(environment, before);
}

#[cfg(not(windows))]
#[test]
fn posix_default_stays_literal() {
    let mut environment = std::collections::BTreeMap::new();
    environment.insert("PATH".into(), "/somewhere".into());
    environment.insert("CODEX_BIN".into(), "".into());
    assert_eq!(handoff_packet::codex_binary::resolve(&environment), "codex");
}

#[cfg(windows)]
#[test]
fn batch_shims_accept_app_server_and_config_arguments() {
    // The executor sends configuration in JSON-RPC; also exercise CLI -c escaping.
    let root = std::env::temp_dir().join(format!("codex-shims-{}", std::process::id()));
    std::fs::create_dir_all(&root).unwrap();
    for extension in ["cmd", "bat"] {
        let shim = root.join(format!("codex.{extension}"));
        std::fs::write(&shim, b"@echo off\r\necho %1\r\necho %2\r\necho %3\r\n").unwrap();
        let output = std::process::Command::new(&shim)
            .args(["app-server", "-c", "model_reasoning_effort=high"])
            .output()
            .unwrap();
        assert!(output.status.success(), "{output:?}");
        assert_eq!(
            output.stdout,
            b"app-server\r\n-c\r\nmodel_reasoning_effort=high\r\n"
        );
        assert!(output.stderr.is_empty());
    }
    std::fs::remove_dir_all(root).unwrap();
}
