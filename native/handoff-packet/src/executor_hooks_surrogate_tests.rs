#[cfg(unix)]
use super::*;

#[cfg(unix)]
#[test]
fn native_hook_surrogate_responses_match_pinned_python() {
    use std::os::unix::fs::PermissionsExt;
    let fixture: Value = serde_json::from_str(include_str!(
        "../tests/fixtures/executor_hook_numeric_responses_reference.json"
    ))
    .unwrap();
    let scratch = std::env::var_os("MIR_NATIVE_TEST_SCRATCH")
        .map(std::path::PathBuf::from)
        .unwrap_or_else(std::env::temp_dir);
    let root = tempfile::tempdir_in(scratch).unwrap();
    let host = root.path().join("hook.sh");
    fs::write(&host, fixture["host"].as_str().unwrap()).unwrap();
    fs::set_permissions(&host, fs::Permissions::from_mode(0o700)).unwrap();
    let config = HooksConfig {
        executable: "hook.sh".into(),
        argv: vec![],
        sha256: crate::digest::sha256(&fs::read(&host).unwrap()),
        hooks: vec!["writer_scope".into(), "on_job_event".into()],
    };
    let mut mismatches = vec![];
    for (index, record) in fixture["surrogates"].as_array().unwrap().iter().enumerate() {
        let environment = BTreeMap::from([
            (OsString::from("HOME"), root.path().as_os_str().to_owned()),
            (
                OsString::from("PATH"),
                std::env::var_os("PATH").unwrap_or_else(|| OsString::from("/usr/bin:/bin")),
            ),
            (
                OsString::from("CODEX_BIN"),
                root.path().join("never-run-codex").into_os_string(),
            ),
            (
                OsString::from("HOOK_REPLY"),
                OsString::from(record["response"].as_str().unwrap()),
            ),
        ]);
        let mut session = HookSession::start_in_environment(
            root.path(),
            root.path(),
            &config,
            &environment,
            Duration::from_secs(2),
        )
        .unwrap();
        let reply = session.call(record["hook"].as_str().unwrap(), json!({}));
        let mut matched = reply.is_ok();
        if let Ok(reply) = reply {
            if index == 0 {
                let effect = root.path().join("execution-effect");
                fs::write(&effect, "executed").unwrap();
                let error = session
                    .call(
                        "writer_exit",
                        json!({"token":{"__native_string":record["points"]},"outcome":"clean"}),
                    )
                    .unwrap_err();
                matched = error.to_string() == record["exit_error"].as_str().unwrap()
                    && fs::read_to_string(effect).unwrap()
                        == record["execution_effect"].as_str().unwrap();
            } else if index == 5 {
                matched = !reply["result"]["token"].is_string();
            }
        }
        session.close();
        if !matched {
            mismatches.push(index);
        }
    }
    assert!(
        mismatches.is_empty(),
        "hook surrogate response mismatches: {mismatches:?}"
    );
}
