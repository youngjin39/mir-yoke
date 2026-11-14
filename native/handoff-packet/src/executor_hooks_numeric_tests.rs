#[cfg(unix)]
use super::*;

#[cfg(unix)]
#[test]
fn native_hook_numeric_frames_match_pinned_python() {
    use std::os::unix::fs::PermissionsExt;
    let fixture: Value = serde_json::from_str(include_str!(
        "../tests/fixtures/executor_hook_numeric_reference.json"
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
        hooks: vec!["on_job_event".into()],
    };
    let mut mismatches = vec![];
    for (index, record) in fixture["records"].as_array().unwrap().iter().enumerate() {
        let log = root.path().join(format!("frame-{index}"));
        let environment = BTreeMap::from([
            (OsString::from("HOME"), root.path().as_os_str().to_owned()),
            (OsString::from("FRAME_LOG"), log.as_os_str().to_owned()),
        ]);
        let mut session = HookSession::start_in_environment(
            root.path(),
            root.path(),
            &config,
            &environment,
            Duration::from_secs(2),
        )
        .unwrap();
        let field = record["field"].as_str().unwrap();
        let token = record["token"].as_str();
        let marker = if record["kind"] == "int" {
            json!({"__native_integer":token.unwrap()})
        } else {
            json!({"__native_float":token.unwrap_or("")})
        };
        let args = json!({"codex_args":"{\"__native_integer\":\"99999999999999999999999\"}","model":{"__native_integer":"99999999999999999999999"}});
        let mut params = json!({"event":"pre_execute", "payload":{"args":args}});
        if record["kind"] == "string" {
            params[field] = json!({"__native_string":record["points"]});
        } else {
            params["payload"]["args"][field] = marker;
        }
        let result = session.call("on_job_event", params);
        let actual = fs::read_to_string(&log).unwrap_or_default();
        let matched = if let Some(expected) = record["error"].as_str() {
            result.is_err_and(|error| error.to_string() == expected) && actual.is_empty()
        } else {
            result.is_ok() && actual == record["frame"].as_str().unwrap()
        };
        session.close();
        if !matched {
            mismatches.push(index);
        }
    }
    assert!(
        mismatches.is_empty(),
        "hook numeric wire mismatches: {mismatches:?}"
    );
}

#[cfg(unix)]
#[test]
fn native_hook_numeric_responses_match_pinned_python() {
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
    for (index, record) in fixture["records"].as_array().unwrap().iter().enumerate() {
        let environment = BTreeMap::from([
            (OsString::from("HOME"), root.path().as_os_str().to_owned()),
            (
                OsString::from("HOOK_REPLY"),
                OsString::from(record["response"].as_str().unwrap()),
            ),
            (
                OsString::from("PATH"),
                std::env::var_os("PATH").unwrap_or_else(|| OsString::from("/usr/bin:/bin")),
            ),
            (
                OsString::from("CODEX_BIN"),
                root.path().join("never-run-codex").into_os_string(),
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
        let result = session.call(record["hook"].as_str().unwrap(), json!({}));
        let matched = if record["accepted"] == true {
            match result {
                Ok(reply) if record["result_type"] == "int" => {
                    reply["result"]["__native_hook_integer"]
                        .as_str()
                        .is_some_and(|raw| raw.len() >= 400)
                }
                Ok(reply) if index == 0 => {
                    reply["result"]["token"] == "opaque"
                        && reply["result"]["extra"]["__native_hook_integer"]
                            .as_str()
                            .is_some_and(|raw| raw.len() == 401)
                }
                Ok(reply) if record["token_is_string"] == false => {
                    !reply["result"]["token"].is_string()
                        && reply["result"]["token"]["__native_hook_integer"]
                            .as_str()
                            .is_some_and(|raw| raw.len() == 401)
                }
                Ok(reply) => {
                    reply["result"]["__native_hook_integer"] == "1"
                        && reply["result"]["extra"]["__native_hook_integer"]
                            .as_str()
                            .is_some_and(|raw| raw.len() == 401)
                }
                Err(_) => false,
            }
        } else {
            result.is_err_and(|error| {
                let actual = error.to_string();
                actual == record["error"].as_str().unwrap()
                    || (record["error"]
                        .as_str()
                        .unwrap()
                        .ends_with("invalid native hook response")
                        && actual.ends_with("invalid native hook response"))
            })
        };
        session.close();
        if !matched {
            mismatches.push(index);
        }
    }
    assert!(
        mismatches.is_empty(),
        "hook response mismatches: {mismatches:?}"
    );
}
