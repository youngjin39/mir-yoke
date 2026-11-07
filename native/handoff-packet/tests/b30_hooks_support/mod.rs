use handoff_packet::mir_cli::{adoption_native, project_hooks};
use serde_json::{Value, json};
use std::{fs, path::Path};

const DATA: &[u8] = b"fixture artifact\n";
const SHA: &str = "0fc7c8c357dfa2cc6116cdf1172b5734908a31644d6a807152023dd63d7f151a";
struct Host;
impl adoption_native::InstallHost for Host {}

fn files(root: &Path) -> Value {
    fn visit(root: &Path, path: &Path, result: &mut serde_json::Map<String, Value>) {
        let mut entries: Vec<_> = fs::read_dir(path).unwrap().map(Result::unwrap).collect();
        entries.sort_by_key(|entry| entry.path());
        for entry in entries {
            let path = entry.path();
            let meta = fs::symlink_metadata(&path).unwrap();
            if meta.file_type().is_symlink() {
                continue;
            }
            if meta.is_dir() {
                visit(root, &path, result);
            } else {
                result.insert(
                    path.strip_prefix(root)
                        .unwrap()
                        .to_string_lossy()
                        .replace('\\', "/"),
                    json!(fs::read_to_string(path).unwrap()),
                );
            }
        }
    }
    let mut result = serde_json::Map::new();
    visit(root, root, &mut result);
    Value::Object(result)
}

pub fn replay(name: &str, tmp: &Path) -> Value {
    if name == "hooks.receipt_failure" {
        let path = tmp.join("project-hooks.json");
        let result = project_hooks::write_receipt_with(
            &path,
            &json!({"path":"x","sha256":"0".repeat(64)}),
            |_, _| Err(std::io::Error::other("synthetic replace failure")),
        );
        let remaining: Vec<_> = fs::read_dir(tmp)
            .unwrap()
            .map(|entry| entry.unwrap().file_name().to_string_lossy().into_owned())
            .collect();
        return json!({"value": [["OSError", result.unwrap_err()], remaining]});
    }
    let parts: Vec<_> = name.split('.').collect();
    let operation = parts[1];
    let mode = parts[2];
    let artifact = tmp.join("artifact");
    fs::write(&artifact, DATA).unwrap();
    let pin = json!({"url":artifact.to_string_lossy(),"size":DATA.len(),"sha256":SHA});
    let mut metadata = json!({
        "schema_version": 1,
        "provider_revision": "a".repeat(40),
        "plugins": {"mir-lifecycle-hooks": {}},
        "native_artifacts": {
            "project-hooks": {
                "plugin": "mir-lifecycle-hooks",
                "install_path": "bin/project-hooks",
                "targets": {"x86_64-unknown-linux-gnu": pin.clone()}
            }
        }
    });
    if mode == "bad-schema" {
        metadata["schema_version"] = json!(true);
    }
    if mode == "bad-identity" {
        metadata["provider_revision"] = json!("main");
    }
    if mode == "no-pin" {
        metadata["native_artifacts"]["project-hooks"]["targets"] = json!({});
    }
    let provider = tmp.join("provider");
    fs::create_dir_all(provider.join(".mir")).unwrap();
    fs::create_dir(provider.join("resources")).unwrap();
    for relative in [
        ".mir/capability-lock.json",
        "resources/project-hooks-provider.json",
    ] {
        fs::write(provider.join(relative), metadata.to_string()).unwrap();
    }
    let root = tmp.join("project");
    fs::create_dir(&root).unwrap();
    let target = if mode == "unsupported" {
        None
    } else {
        Some("x86_64-unknown-linux-gnu")
    };
    if operation == "provider" {
        return match project_hooks::provider_pin(&metadata, target, mode == "disabled") {
            Ok((target, pin)) => json!({"value":[target,pin]}),
            Err(error) => json!({"error":["ValueError",error]}),
        };
    }
    if operation == "path" {
        #[cfg(unix)]
        std::os::unix::fs::symlink(&provider, root.join("link")).unwrap();
        #[cfg(windows)]
        std::os::windows::fs::symlink_dir(&provider, root.join("link")).unwrap();
        return match project_hooks::project_path(&root, "link/x") {
            Ok(path) => json!({"value":path.to_string_lossy()}),
            Err(error) => json!({"error":["ValueError",error]}),
        };
    }
    if operation == "check" && mode != "uninstalled" {
        let options = adoption_native::InstallOptions {
            target,
            artifact_pin: Some(&pin),
            ..Default::default()
        };
        let installed = adoption_native::install_project_hooks(&root, &options, &mut Host).unwrap();
        let receipt = root.join(".mir/bin/project-hooks.json");
        project_hooks::write_receipt(&receipt, &installed).unwrap();
        project_hooks::write_receipt(&receipt, &installed).unwrap();
        let binary = root.join(".mir/bin/project-hooks");
        if mode == "missing-binary" {
            fs::remove_file(&binary).unwrap();
        }
        if mode == "not-executable" {
            #[cfg(unix)]
            {
                use std::os::unix::fs::PermissionsExt;
                fs::set_permissions(&binary, fs::Permissions::from_mode(0o644)).unwrap();
            }
        }
        if mode == "bad-receipt" {
            fs::write(receipt, "{}").unwrap();
        }
    }
    let root_arg = root.to_string_lossy();
    let args = match operation {
        "help" => vec!["--help"],
        "invalid" => vec!["bad"],
        "empty" => vec![],
        _ => vec![operation, "--project-root", &root_arg],
    };
    let mut calls = Vec::new();
    let output = project_hooks::main(
        &args,
        &metadata,
        target,
        mode == "disabled",
        |root, pin| {
            let options = adoption_native::InstallOptions {
                target,
                artifact_pin: Some(pin),
                ..Default::default()
            };
            adoption_native::install_project_hooks(root, &options, &mut Host)
        },
        |request| {
            calls.push(json!({
                "argv": request.argv,
                "stdin": request.stdin,
                "capture_output": request.capture_output,
                "timeout": request.timeout,
                "check": request.check,
                "cwd": request.cwd.to_string_lossy()
            }));
            if mode == "missing" {
                return Err("synthetic missing binary".to_owned());
            }
            Ok(project_hooks::ProbeOutput {
                returncode: i32::from(mode == "nonzero"),
                stdout: match mode {
                    "json" => b"{}".to_vec(),
                    "malformed" => b"{".to_vec(),
                    "one-token" => b"mir-project-hooks-v1\n".to_vec(),
                    _ => b"mir-project-hooks-v1\nmir-project-hooks-compact-v1\n".to_vec(),
                },
            })
        },
    );
    json!({"value": [
        output.0,
        String::from_utf8(output.1).unwrap(),
        String::from_utf8(output.2).unwrap(),
        files(&root),
        calls
    ]})
}
