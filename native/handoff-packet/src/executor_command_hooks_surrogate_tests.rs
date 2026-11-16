#[cfg(unix)]
use super::*;

#[cfg(unix)]
#[test]
fn native_command_hook_surrogate_token_and_error_provenance() {
    use std::os::unix::fs::PermissionsExt;
    use std::{collections::BTreeMap, ffi::OsString, fs, time::Duration};
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
    let config = crate::executor_hooks::HooksConfig {
        executable: "hook.sh".into(),
        argv: vec![],
        sha256: crate::digest::sha256(&fs::read(&host).unwrap()),
        hooks: vec!["writer_scope".into(), "on_job_event".into()],
    };
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
        let native = HookSession::start_in_environment(
            root.path(),
            root.path(),
            &config,
            &environment,
            Duration::from_secs(2),
        )
        .unwrap();
        let mut hooks = CommandHooks {
            python: None,
            native: Some(native),
            hello: json!({}),
            context: json!({}),
            token: None,
            token_points: None,
            error_points: None,
            outcome: TeardownOutcome::Clean,
            provider_uncertain: false,
            brief_profile: None,
            job_identity: None,
            instruction: None,
        };
        let result = if record["hook"] == "writer_enter" {
            hooks.call("writer_scope.enter", vec![], json!({}))
        } else {
            hooks.call(
                "on_job_event",
                vec![json!("job_inserted"), json!({})],
                json!({}),
            )
        };
        if index == 5 {
            assert!(
                result.is_err_and(|error| error
                    .to_string()
                    .ends_with("writer_enter requires opaque token")),
                "forged token object accepted"
            );
            assert!(hooks.token.is_none());
            assert!(hooks.token_points.is_none());
            continue;
        }
        let reply = result.unwrap();
        if index == 0 {
            assert_eq!(reply["ok"], true);
            let effect = root.path().join("execution-effect");
            fs::write(&effect, "executed").unwrap();
            let error = hooks
                .call("writer_scope.exit", vec![], json!({}))
                .unwrap_err();
            assert_eq!(error.to_string(), record["exit_error"].as_str().unwrap());
            assert_eq!(
                fs::read_to_string(effect).unwrap(),
                record["execution_effect"].as_str().unwrap()
            );
        } else if index == 3 || index == 4 || index == 7 {
            assert_eq!(reply["ok"], false);
            if index == 7 {
                assert!(
                    hooks.take_error_points().is_none(),
                    "literal escape became trusted response points"
                );
            } else {
                assert_eq!(hooks.take_error_points().unwrap(), vec![0xd800]);
            }
            assert!(hooks.take_error_points().is_none());
            let _ = hooks.call("unused", vec![], json!({}));
            assert!(hooks.take_error_points().is_none());
        } else {
            assert_eq!(reply["ok"], true, "ignored surrogate string rejected");
            if index == 6 {
                assert!(
                    hooks.token_points.is_none(),
                    "literal token escape became surrogate token"
                );
            }
            if index == 8 {
                assert_eq!(reply["result"], json!({"__native_string":[55296]}));
            }
        }
    }
}
