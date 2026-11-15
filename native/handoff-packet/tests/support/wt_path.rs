use serde_json::Value;
use std::{fs, path::PathBuf, process::Command};

pub fn setup() -> (tempfile::TempDir, PathBuf, Vec<Value>) {
    let temp = tempfile::tempdir().unwrap();
    let scratch = handoff_packet::supply::plain(temp.path().canonicalize().unwrap());
    let root = scratch.join("project");
    fs::create_dir_all(root.join("notes")).unwrap();
    fs::write(root.join("file"), "synthetic").unwrap();
    fs::create_dir(scratch.join("outside")).unwrap();
    for (name, target) in [
        ("alias", root.join("notes")),
        ("escape", scratch.join("outside")),
        ("dangling", root.join("missing")),
    ] {
        let output = Command::new("cmd.exe")
            .args(["/D", "/C", "mklink", "/J"])
            .arg(root.join(name))
            .arg(target)
            .current_dir(&scratch)
            .env("HOME", &scratch)
            .output()
            .unwrap();
        assert!(output.status.success(), "{output:?}");
    }
    let escaped = serde_json::to_string(scratch.to_str().unwrap()).unwrap();
    let drive: PathBuf = scratch.components().take(2).collect();
    let drive = serde_json::to_string(drive.to_str().unwrap()).unwrap();
    let frozen: Value = serde_json::from_str(
        &include_str!("../fixtures/wt-path-windows.json")
            .replace("{ROOT}", &escaped[1..escaped.len() - 1])
            .replace("{DRIVE}", &drive[1..drive.len() - 1]),
    )
    .unwrap();
    (temp, root, frozen["records"].as_array().unwrap().clone())
}
