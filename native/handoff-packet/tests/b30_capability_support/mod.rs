use handoff_packet::mir_cli::capability::{self, Manager};
use serde_json::{Map, Value, json};
use std::{fs, path::Path};

pub fn expected_command_list(name: &str, mut expected: Value) -> Value {
    let field = match name {
        "capability.help" => 1,
        "capability.invalid" | "capability.empty" => 2,
        _ => return expected,
    };
    // Keep the pinned capture and account for the new subcommand in top-level usage.
    expected["value"][field] = json!(
        expected["value"][field]
            .as_str()
            .unwrap()
            .replace(
                "[-h] {status,check,sync,update,finalize,attest} ...",
                "[-h]\n                      {status,check,sync,update,finalize,attest}\n                      ...",
            )
            .replace(
                "{status,check,sync,update,finalize,attest}",
                "{status,check,sync,update,finalize,attest,deregister}",
            )
            .replace(
                "(choose from status, check, sync, update, finalize, attest)",
                "(choose from status, check, sync, update, finalize, attest, deregister)",
            )
    );
    expected
}

pub fn replay(name: &str, tmp: &Path) -> Value {
    struct Mock<'a> {
        root: &'a Path,
        calls: Vec<Value>,
        error: bool,
    }
    impl Manager for Mock<'_> {
        fn initialize(
            &mut self,
            root: &Path,
            config: Option<&Path>,
            home: Option<&Path>,
        ) -> Result<(), capability::Error> {
            self.calls
                .push(json!(["init",root,{"config_path":config,"capability_home":home}]));
            Ok(())
        }
        fn call(
            &mut self,
            method: &str,
            args: Vec<Value>,
            kwargs: Map<String, Value>,
        ) -> Result<handoff_packet::python_json::Value, capability::Error> {
            self.calls.push(json!([method, args, kwargs]));
            if self.error {
                return Err(capability::Error::new(
                    "CapabilityError",
                    "synthetic failure",
                ));
            }
            fs::write(self.root.join("written"), method).unwrap();
            Ok(handoff_packet::python_json::Value::from(
                &json!({"query":method}),
            ))
        }
    }
    let command = name.strip_prefix("capability.").unwrap_or(name);
    let (command, apply_deregister) = if command == "deregister-apply" {
        ("deregister", true)
    } else {
        (command, false)
    };
    let mut args: Vec<String> = vec![
        command.into(),
        "--project-root".into(),
        tmp.display().to_string(),
        "--capability-home".into(),
        tmp.join("home").display().to_string(),
        "--config".into(),
        tmp.join("config").display().to_string(),
        "--json".into(),
    ];
    if apply_deregister || ["sync", "update", "finalize", "attest"].contains(&command) {
        args.push("--apply".into());
    }
    if ["check", "sync", "update"].contains(&command) {
        args.extend(["--profile", "fixture", "--no-mcp"].map(str::to_string));
    }
    if command == "finalize" {
        args.push("--after-restart".into());
    }
    if ["attest", "bad-evidence"].contains(&command) {
        let evidence = tmp.join("evidence.json");
        fs::write(
            &evidence,
            if command == "bad-evidence" {
                "{"
            } else {
                "{\"pkg\":true}"
            },
        )
        .unwrap();
        args[0] = "attest".into();
        args.extend(
            [
                "--runtime",
                "codex-cli-desktop",
                "--observed-skill",
                "p:s",
                "--observed-hook",
                "p:h",
                "--mcp-evidence",
            ]
            .map(str::to_string),
        );
        args.push(evidence.display().to_string());
    }
    if command == "error" {
        args[0] = "status".into();
    }
    match command {
        "help" => args = vec!["--help".into()],
        "invalid" => args = vec!["bad".into()],
        "empty" => args.clear(),
        "deregister-unscoped" => args = vec!["deregister".into(), "--apply".into()],
        "pretty" => {
            args = vec![
                "status".into(),
                "--project-root".into(),
                tmp.display().to_string(),
            ]
        }
        _ => {}
    }
    let mut mock = Mock {
        root: tmp,
        calls: vec![],
        error: command == "error",
    };
    let (code, out, err) = capability::main(
        &args.iter().map(String::as_str).collect::<Vec<_>>(),
        &mut mock,
    )
    .unwrap();
    let mut files = Map::new();
    for entry in fs::read_dir(tmp).unwrap() {
        let path = entry.unwrap().path();
        if path.is_file() {
            files.insert(
                path.file_name().unwrap().to_string_lossy().into(),
                json!(fs::read_to_string(path).unwrap()),
            );
        }
    }
    json!({"value":[
        code, String::from_utf8(out).unwrap(), String::from_utf8(err).unwrap(), files, mock.calls
    ]})
}

#[test]
fn deregister_dispatches_preview_and_apply() {
    for (command, apply) in [("deregister", false), ("deregister-apply", true)] {
        let temp = tempfile::tempdir().unwrap();
        let root = temp.path().canonicalize().unwrap();
        let observation = replay(command, &root);
        let result = &observation["value"];
        assert_eq!(result[0], 0, "{result}");
        assert_eq!(result[2], "");
        assert_eq!(result[4][1], json!(["deregister", [], {"apply": apply}]),);
        assert_eq!(
            serde_json::from_str::<Value>(result[1].as_str().unwrap()).unwrap(),
            json!({
                "change_evidence": {
                    "status": "not-applicable",
                    "reason": "registry-only-operation",
                },
                "query": "deregister",
            }),
        );
    }
}

#[test]
fn deregister_requires_explicit_scope() {
    let temp = tempfile::tempdir().unwrap();
    let observation = replay("deregister-unscoped", temp.path());
    let result = &observation["value"];
    assert_eq!(result[0], 2, "{result}");
    assert!(
        result[2]
            .as_str()
            .unwrap()
            .contains("the following arguments are required: --project-root, --capability-home")
    );
    assert_eq!(result[4], json!([]));
}
