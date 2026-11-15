//! Shared placement scenarios; the PC driver runs the same bodies on Windows.
#[path = "../src/digest.rs"]
mod digest;
use handoff_packet::{
    mir_cli::{adoption_native, project_hooks},
    mir_core::capabilities::native::{self, ArtifactHost, PlacementMutation, PlacementOptions},
    python_json,
};
use serde_json::json;
use std::{fs, io, path::Path};

const TARGET: &str = "x86_64-pc-windows-msvc";
const DATA: &[u8] = b"synthetic artifact; never executed";
fn scratch() -> tempfile::TempDir {
    tempfile::tempdir().unwrap()
}
fn root(temp: &tempfile::TempDir) -> std::path::PathBuf {
    temp.path().canonicalize().unwrap()
}
struct Install(bool);
impl adoption_native::InstallHost for Install {
    fn before_replace(&mut self, source: &Path, _: &Path) -> io::Result<()> {
        if self.0 {
            fs::rename(source, source.with_extension("saved"))?;
            fs::write(source, b"foreign")?;
        }
        Ok(())
    }
}
#[test]
fn private_install_uses_owned_stage_and_preserves_foreign_replacement() {
    let t = scratch();
    let r = root(&t);
    let source = r.join("source");
    fs::write(&source, DATA).unwrap();
    let options = adoption_native::InstallOptions {
        target: Some(TARGET),
        local_source: Some(&source),
        ..Default::default()
    };
    let result = adoption_native::install(&r, "runtime-verify", &options, &mut Install(true));
    assert!(result.is_none(), "foreign stage published: {result:?}");
    let bin = r.join(".mir/bin");
    assert!(!bin.join("runtime-verify.exe").exists(), "{result:?}");
    let files: Vec<_> = fs::read_dir(&bin)
        .unwrap()
        .map(|e| e.unwrap().path())
        .collect();
    assert_eq!(
        files.len(),
        2,
        "foreign and saved entries must survive: {files:?}"
    );
    assert!(
        files.iter().any(|p| fs::read(p).unwrap() == b"foreign"),
        "{files:?}"
    );
    let result = adoption_native::install(&r, "runtime-verify", &options, &mut Install(false));
    assert!(result.is_some(), "{result:?}");
    assert_eq!(
        fs::read(bin.join("runtime-verify.exe")).unwrap(),
        DATA,
        "{result:?}"
    );
}
#[test]
fn receipt_rejects_modified_bytes_and_preserves_old_receipt() {
    let t = scratch();
    let r = root(&t);
    let path = r.join("receipt.json");
    fs::write(&path, b"old").unwrap();
    let result = project_hooks::write_receipt_with(&path, &json!({"pin":1}), |source, _| {
        fs::write(source, b"tampered")
    });
    assert!(result.is_err(), "modified receipt accepted: {result:?}");
    assert_eq!(fs::read(&path).unwrap(), b"old", "{result:?}");
    assert_eq!(fs::read_dir(&r).unwrap().count(), 1, "{result:?}");
    let result = project_hooks::write_receipt_with(&path, &json!({"pin":1}), |_, _| Ok(()));
    assert!(result.is_ok(), "{result:?}");
    let value: serde_json::Value = serde_json::from_slice(&fs::read(path).unwrap()).unwrap();
    assert_eq!(value, json!({"pin":1}), "{result:?}");
}
#[test]
fn receipt_never_publishes_or_cleans_a_foreign_stage() {
    let t = scratch();
    let r = root(&t);
    let path = r.join("receipt.json");
    let saved = r.join("saved");
    let mut foreign = None;
    let result = project_hooks::write_receipt_with(&path, &json!({"pin":1}), |source, _| {
        fs::rename(source, &saved)?;
        fs::write(source, b"foreign")?;
        foreign = Some(source.to_owned());
        Ok(())
    });
    assert!(
        result.is_err(),
        "foreign receipt stage accepted: {result:?}"
    );
    assert!(!path.exists(), "{result:?}");
    assert_eq!(
        fs::read(foreign.unwrap()).unwrap(),
        b"foreign",
        "{result:?}"
    );
    assert!(saved.exists(), "{result:?}");
}
struct Artifact {
    fail_metadata: bool,
    mode: bool,
}
impl ArtifactHost for Artifact {
    fn read(&mut self, _: &str, _: u64) -> Result<Vec<u8>, String> {
        Ok(DATA.to_vec())
    }
    fn before_mutation(&mut self, site: PlacementMutation, path: &Path) -> io::Result<()> {
        if site == PlacementMutation::SetExecutable && self.mode {
            let mut permissions = fs::metadata(path)?.permissions();
            permissions.set_readonly(true);
            fs::set_permissions(path, permissions)?;
        }
        if site == PlacementMutation::PublishMetadata && self.fail_metadata {
            // Real OS rename failure: a nonempty directory occupies the target.
            fs::create_dir(path)?;
            fs::write(path.join("foreign"), b"outside")?;
        }
        Ok(())
    }
}
fn records() -> python_json::Value {
    python_json::parse(
        &json!({"mir-mcp": {
            "plugin":"mir-mcp", "install_path":"bin/mir-mcp", "targets":{
                TARGET:{"url":"synthetic", "size":DATA.len(), "sha256":digest::sha256(DATA)}
            }
        }})
        .to_string(),
    )
    .unwrap()
}
#[test]
fn artifact_mode_metadata_and_failure_rollback_use_shared_primitives() {
    for failure in [false, true] {
        let t = scratch();
        let r = root(&t);
        let result = native::place_artifacts(
            &r,
            "mir-mcp",
            &records(),
            PlacementOptions {
                target: Some(TARGET),
                disabled: false,
            },
            &mut Artifact {
                fail_metadata: failure,
                mode: !failure,
            },
        );
        assert!(result.is_ok(), "{result:?}");
        let warnings = result.unwrap();
        let executable = r.join("bin/mir-mcp.exe");
        if failure {
            assert_eq!(warnings.len(), 1, "{warnings:?}");
            assert!(!executable.exists(), "{warnings:?}");
            assert_eq!(
                fs::read(r.join("bin/native-artifacts.json/foreign")).unwrap(),
                b"outside",
                "{warnings:?}"
            );
        } else {
            assert!(warnings.is_empty(), "{warnings:?}");
            assert_eq!(fs::read(&executable).unwrap(), DATA, "{warnings:?}");
            assert!(
                !fs::metadata(&executable).unwrap().permissions().readonly(),
                "{warnings:?}"
            );
            let value: serde_json::Value =
                serde_json::from_slice(&fs::read(r.join("bin/native-artifacts.json")).unwrap())
                    .unwrap();
            assert_eq!(value["mir-mcp"]["target"], TARGET, "{value:?}");
        }
    }
}
#[cfg(windows)]
#[test]
fn receipt_real_deny_delete_error_preserves_target_and_cleans_stage() {
    use std::os::windows::fs::OpenOptionsExt;
    let t = scratch();
    let r = root(&t);
    let path = r.join("receipt.json");
    fs::write(&path, b"old").unwrap();
    let locked = fs::OpenOptions::new()
        .read(true)
        .share_mode(3)
        .open(&path)
        .unwrap();
    let mut reached = false;
    let result = project_hooks::write_receipt_with(&path, &json!({"pin":1}), |_, _| {
        reached = true;
        Ok(())
    });
    assert!(reached, "publication boundary not reached: {result:?}");
    assert!(result.is_err(), "deny-delete failure swallowed: {result:?}");
    assert_eq!(fs::read(&path).unwrap(), b"old", "{result:?}");
    assert_eq!(fs::read_dir(&r).unwrap().count(), 1, "{result:?}");
    drop(locked);
}
#[test]
fn receipt_parent_swap_or_platform_refusal_preserves_outside_tree() {
    let t = scratch();
    let r = root(&t);
    let inside = r.join("inside");
    let saved = r.join("saved");
    let outside = r.join("outside");
    fs::create_dir(&inside).unwrap();
    fs::create_dir(&outside).unwrap();
    fs::write(outside.join("receipt.json"), b"outside").unwrap();
    let mut reached = false;
    let mut refused = false;
    let result = project_hooks::write_receipt_with(
        &inside.join("receipt.json"),
        &json!({"pin":1}),
        |_, _| {
            reached = true;
            match fs::rename(&inside, &saved) {
                Ok(()) => {
                    #[cfg(unix)]
                    std::os::unix::fs::symlink(&outside, &inside)?;
                    #[cfg(windows)]
                    {
                        let status = std::process::Command::new("cmd")
                            .args(["/d", "/c", "mklink", "/J"])
                            .arg(&inside)
                            .arg(&outside)
                            .status()?;
                        assert!(status.success(), "junction setup: {status:?}");
                    }
                }
                Err(error) => {
                    // Observed on S1/S2 PC: an open subtree can prevent directory rename.
                    assert!(
                        cfg!(windows) && matches!(error.raw_os_error(), Some(5 | 32)),
                        "{error:?}"
                    );
                    refused = true;
                }
            }
            Ok(())
        },
    );
    assert!(reached, "callback not reached: {result:?}");
    assert_eq!(
        fs::read(outside.join("receipt.json")).unwrap(),
        b"outside",
        "{result:?}"
    );
    assert_eq!(fs::read_dir(&outside).unwrap().count(), 1, "{result:?}");
    if refused {
        assert!(result.is_ok(), "{result:?}");
        let value: serde_json::Value =
            serde_json::from_slice(&fs::read(inside.join("receipt.json")).unwrap()).unwrap();
        assert_eq!(value, json!({"pin":1}), "{result:?}");
    } else {
        assert!(result.is_err(), "{result:?}");
        assert_eq!(fs::read_dir(&saved).unwrap().count(), 0, "{result:?}");
    }
}
