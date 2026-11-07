#![forbid(unsafe_code)]
use handoff_packet::mir_cli::adoption_native::{self as adoption, InstallHost, InstallOptions};
use serde_json::{Value, json};
use std::{fs, io, path::Path};

const TARGET: &str = "x86_64-unknown-linux-gnu";
const DATA: &[u8] = b"fixture artifact\n";
const DIGEST: &str = "0fc7c8c357dfa2cc6116cdf1172b5734908a31644d6a807152023dd63d7f151a";

struct Observer(Vec<Value>);
impl InstallHost for Observer {
    fn before_replace(&mut self, source: &Path, destination: &Path) -> io::Result<()> {
        self.0
            .push(json!([fs::read_to_string(source)?, destination.exists()]));
        Ok(())
    }
}

fn tree(
    root: &Path,
    here: &Path,
    files: &mut serde_json::Map<String, Value>,
    dirs: &mut Vec<String>,
) {
    for entry in fs::read_dir(here).unwrap() {
        let path = entry.unwrap().path();
        let relative = path
            .strip_prefix(root)
            .unwrap()
            .to_str()
            .unwrap()
            .replace('\\', "/");
        if path.is_dir() {
            dirs.push(relative);
            if !path.is_symlink() {
                tree(root, &path, files, dirs);
            }
        } else if path.is_file() && !path.is_symlink() {
            files.insert(relative, json!(fs::read_to_string(path).unwrap()));
        }
    }
}

pub fn replay(name: &str, tmp: &Path) -> Value {
    let parts: Vec<_> = name.split('.').collect();
    let (operation, mode) = (parts[1], parts[2]);
    let artifact = tmp.join("artifact");
    fs::write(&artifact, DATA).unwrap();
    let mut pin = json!({"url":artifact,"size":DATA.len(),"sha256":DIGEST});
    let artifact_name = match operation {
        "evaluator" => "bootstrap-gate",
        "runtime_verifier" => "runtime-verify",
        "executor_query" => "executor-query",
        "delegation_gate" => "delegation-gate",
        "project_hooks" => "project-hooks",
        _ => panic!("unknown frozen native operation"),
    };
    let target = if mode == "windows" {
        "x86_64-pc-windows-msvc"
    } else {
        TARGET
    };
    let provider = tmp.join("provider");
    fs::create_dir_all(provider.join(".mir")).unwrap();
    fs::create_dir(provider.join("resources")).unwrap();
    let metadata = json!({
        "schema_version": 1,
        "provider_revision": "a".repeat(40),
        "plugins": {"mir-lifecycle-hooks": {}},
        "native_artifacts": {artifact_name: {
            "plugin": "mir-lifecycle-hooks",
            "install_path": format!("bin/{artifact_name}"),
            "targets": {target: pin}
        }}
    });
    let lock = provider.join(".mir/capability-lock.json");
    fs::write(&lock, serde_json::to_vec(&metadata).unwrap()).unwrap();
    fs::write(
        provider.join("resources/project-hooks-provider.json"),
        serde_json::to_vec(&metadata).unwrap(),
    )
    .unwrap();
    let root = tmp.join("project");
    fs::create_dir(&root).unwrap();
    let destination = root.join(".mir/bin").join(artifact_name);
    if matches!(mode, "replace" | "failure" | "existing" | "linked") {
        fs::create_dir_all(destination.parent().unwrap()).unwrap();
        fs::write(&destination, if mode == "existing" { DATA } else { b"old" }).unwrap();
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            fs::set_permissions(&destination, fs::Permissions::from_mode(0o755)).unwrap();
        }
    }
    #[cfg(unix)]
    if mode == "linked" {
        fs::remove_file(&destination).unwrap();
        std::os::unix::fs::symlink(&artifact, &destination).unwrap();
    }
    #[cfg(unix)]
    if mode == "linked-parent" {
        fs::create_dir(tmp.join("elsewhere")).unwrap();
        fs::create_dir(root.join(".mir")).unwrap();
        std::os::unix::fs::symlink(tmp.join("elsewhere"), root.join(".mir/bin")).unwrap();
    }
    if mode == "empty-local" {
        fs::write(&artifact, b"").unwrap();
    }
    if mode == "missing-local" {
        fs::remove_file(&artifact).unwrap();
    }
    if matches!(mode, "bad-lock" | "missing-lock") {
        fs::write(&lock, b"{").unwrap();
        if mode == "missing-lock" {
            fs::remove_file(lock).unwrap();
        }
    }
    if mode == "failure" {
        pin["sha256"] = json!("0".repeat(64));
    }
    let options = InstallOptions {
        target: (mode != "unsupported").then_some(target),
        native_artifacts: match mode {
            "disabled" => Some("0"),
            "enabled" => Some("1"),
            _ => None,
        },
        source_root: (!matches!(mode, "failure" | "replace" | "existing" | "linked"))
            .then_some(provider.as_path()),
        artifact_pin: matches!(mode, "failure" | "replace" | "existing" | "linked").then_some(&pin),
        local_source: matches!(mode, "local" | "empty-local" | "missing-local")
            .then_some(artifact.as_path()),
        home: None,
    };
    let mut host = Observer(Vec::new());
    let result = adoption::install(&root, artifact_name, &options, &mut host);
    let mut files = serde_json::Map::new();
    let mut dirs = Vec::new();
    tree(&root, &root, &mut files, &mut dirs);
    dirs.sort();
    json!({"value":{"result":result,"files":files,"atomic":host.0,"dirs":dirs}})
}
