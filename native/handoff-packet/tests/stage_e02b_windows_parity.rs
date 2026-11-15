//! S9 frozen PC observations and independent native containment assertions.
#![forbid(unsafe_code)]
#[path = "../src/digest.rs"]
mod digest;
use handoff_packet::{
    mir_core::capabilities::native::{
        self, ArtifactHost, PlacementMutation as Site, PlacementOptions,
    },
    python_json,
};
use serde_json::json;
use std::ffi::OsString;
use std::path::{Path, PathBuf};
use std::{fs, io};
const TARGET: &str = "x86_64-pc-windows-msvc";
fn payload() -> Vec<u8> {
    include_bytes!("../../../tests/fixtures/stage_e02b/probe.exe").to_vec()
}
fn place(root: &Path, hash: &str, host: &mut Host) -> Result<Vec<String>, native::PlacementError> {
    let entries = python_json::parse(
        &json!({"mir-mcp":{"plugin":"mir-mcp","install_path":"bin/mir-mcp",
        "targets":{TARGET:{"url":"synthetic","size":payload().len(),"sha256":hash}}}})
        .to_string(),
    )
    .unwrap();
    let options = PlacementOptions {
        target: Some(TARGET),
        disabled: false,
    };
    native::place_artifacts(root, "mir-mcp", &entries, options, host)
}
#[derive(Default)]
struct Host {
    site: Option<Site>,
    target: PathBuf,
    outside: PathBuf,
    leaf: bool,
    refused: bool,
    count: usize,
    #[cfg(windows)]
    foreign_attributes: Option<u32>,
}
impl ArtifactHost for Host {
    fn read(&mut self, _: &str, _: u64) -> Result<Vec<u8>, String> {
        Ok(payload())
    }
    fn temporary_name(&mut self) -> OsString {
        self.count += 1;
        format!("temp{}", self.count).into()
    }
    fn before_mutation(&mut self, site: Site, _path: &Path) -> io::Result<()> {
        if self.site != Some(site) {
            return Ok(());
        }
        self.site = None;
        match fs::rename(&self.target, self.target.with_extension("saved")) {
            Ok(()) => {
                if self.leaf {
                    if site == Site::RemoveDirectory {
                        fs::create_dir(&self.target)?;
                    } else {
                        fs::write(&self.target, b"foreign")?;
                        if site == Site::SetExecutable {
                            let mut permissions = fs::metadata(&self.target)?.permissions();
                            permissions.set_readonly(true);
                            fs::set_permissions(&self.target, permissions)?;
                            #[cfg(windows)]
                            {
                                use std::os::windows::fs::MetadataExt;
                                self.foreign_attributes =
                                    Some(fs::metadata(&self.target)?.file_attributes());
                            }
                        }
                    }
                } else {
                    directory_link(&self.outside, &self.target)?;
                }
            }
            Err(e) => {
                assert!(
                    cfg!(windows) && matches!(e.raw_os_error(), Some(5 | 32)),
                    "{site:?}: {e:?}"
                );
                self.refused = true;
            }
        }
        Ok(())
    }
}
#[cfg(unix)]
fn directory_link(target: &Path, path: &Path) -> io::Result<()> {
    std::os::unix::fs::symlink(target, path)
}
#[cfg(windows)]
fn directory_link(target: &Path, path: &Path) -> io::Result<()> {
    let output = std::process::Command::new("cmd.exe")
        .args(["/D", "/C", "mklink", "/J"])
        .arg(path.to_str().unwrap().replacen(r"\\?\", "", 1))
        .arg(target.to_str().unwrap().replacen(r"\\?\", "", 1))
        .output()?;
    assert!(output.status.success(), "junction capability: {output:?}");
    Ok(())
}
#[test]
fn native_only_junction_and_owned_leaf_swaps_at_all_eight_sites() {
    use Site::*;
    for leaf in [false, true] {
        for site in [
            CreateDirectory,
            CreateTemporary,
            SetExecutable,
            PublishArtifact,
            PublishMetadata,
            RemoveInstalled,
            RemoveTemporary,
            RemoveDirectory,
        ] {
            if leaf && matches!(site, CreateDirectory | CreateTemporary) {
                continue;
            }
            let temp = tempfile::tempdir().unwrap();
            let base = temp.path().canonicalize().unwrap();
            let root = base.join("root");
            let outside = base.join("outside");
            fs::create_dir(&root).unwrap();
            fs::create_dir(&outside).unwrap();
            for name in ["mir-mcp.exe", "native-artifacts.json", "temp1", "temp2"] {
                fs::write(outside.join(name), b"outside").unwrap();
            }
            if !matches!(site, CreateDirectory | RemoveDirectory) {
                fs::create_dir(root.join("bin")).unwrap();
            }
            if site == RemoveInstalled {
                fs::write(root.join("bin/native-artifacts.json"), b"old").unwrap();
            }
            let mut host = Host {
                site: Some(site),
                target: root
                    .join(match (leaf, site) {
                        (false, CreateDirectory) => "",
                        (true, SetExecutable | PublishArtifact | RemoveTemporary) => "bin/temp1",
                        (true, PublishMetadata) => "bin/temp2",
                        (true, RemoveInstalled) => "bin/mir-mcp.exe",
                        _ => "bin",
                    })
                    .components()
                    .collect(),
                outside: outside.clone(),
                leaf,
                ..Default::default()
            };
            let hash = if matches!(site, RemoveDirectory | RemoveTemporary) {
                "0".repeat(64)
            } else {
                digest::sha256(&payload())
            };
            let result = place(&root, &hash, &mut host);
            assert!(host.site.is_none(), "{site:?}/{leaf}: {result:?}");
            for name in ["mir-mcp.exe", "native-artifacts.json", "temp1", "temp2"] {
                assert_eq!(
                    fs::read(outside.join(name)).ok().as_deref(),
                    Some(b"outside".as_slice()),
                    "{site:?}/{leaf}: {result:?}"
                );
            }
            assert_eq!(
                fs::read_dir(&outside).unwrap().count(),
                4,
                "{site:?}/{leaf}: {result:?}"
            );
            if leaf && !host.refused {
                let path = &host.target;
                assert!(path.exists(), "foreign removed at {site:?}: {result:?}");
                if site != RemoveDirectory {
                    assert_eq!(fs::read(path).unwrap(), b"foreign", "{site:?}: {result:?}");
                }
                if site == SetExecutable {
                    let metadata = fs::metadata(path).unwrap();
                    assert!(
                        metadata.permissions().readonly(),
                        "foreign readonly changed at {site:?}: {result:?}"
                    );
                    #[cfg(windows)]
                    {
                        use std::os::windows::fs::MetadataExt;
                        assert_eq!(
                            Some(metadata.file_attributes()),
                            host.foreign_attributes,
                            "foreign attributes changed at {site:?}: {result:?}"
                        );
                    }
                    // Restore original writable permissions only after checking the foreign leaf.
                    fs::set_permissions(
                        path,
                        fs::metadata(path.with_extension("saved"))
                            .unwrap()
                            .permissions(),
                    )
                    .unwrap();
                }
                assert!(result.is_err(), "foreign accepted at {site:?}: {result:?}");
            }
            if !leaf && !host.refused {
                let path = &host.target;
                #[cfg(windows)]
                fs::remove_dir(path).unwrap();
                #[cfg(unix)]
                fs::remove_file(path)
                    .unwrap_or_else(|e| panic!("unlink junction {site:?}: {e:?}; {result:?}"));
            }
        }
    }
}
#[cfg(windows)]
mod oracle {
    use super::*;
    const PIN: &str = "ba6aa95673deefcb5f418b3fe9f3007f9b22e62a";
    use handoff_packet::mir_cli::{adoption_native as adoption, project_hooks as hooks};
    use serde_json::Value;
    use std::os::windows::fs::MetadataExt;
    fn tree(root: &Path, expected: &Value) {
        fn count(root: &Path) -> usize {
            fs::read_dir(root)
                .unwrap()
                .map(|e| {
                    let p = e.unwrap().path();
                    1 + if p.is_dir() { count(&p) } else { 0 }
                })
                .sum()
        }
        assert_eq!(
            count(root),
            expected.as_object().unwrap().len(),
            "{root:?}: {expected:#}"
        );
        for (name, entry) in expected.as_object().unwrap() {
            let path = root.join(name);
            let m = fs::metadata(&path).unwrap();
            let actual = json!({"directory":m.is_dir(),"attributes":m.file_attributes(),
                "readonly":m.permissions().readonly(),
                "hex":if m.is_dir(){Value::Null}else{json!(hex(&fs::read(path).unwrap()))}});
            let mut wanted = entry.clone();
            wanted["readonly"] = json!(entry["mode"].as_u64().unwrap() & 0o222 == 0);
            wanted.as_object_mut().unwrap().remove("mode");
            assert_eq!(actual, wanted, "{name}: {entry}");
        }
    }

    fn hex(bytes: &[u8]) -> String {
        bytes.iter().map(|b| format!("{b:02x}")).collect()
    }
    fn readonly(path: &Path) {
        let mut p = fs::metadata(path).unwrap().permissions();
        p.set_readonly(true);
        fs::set_permissions(path, p).unwrap();
    }
    #[test]
    fn frozen_e02_install_receipt_placement_and_pe() {
        let path =
            Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/stage-e02b-windows.json");
        let fixture: Value = serde_json::from_slice(
            &fs::read(path).expect("Main must capture the PC fixture first"),
        )
        .unwrap();
        assert_eq!(fixture["manifest"]["reference_pin"], PIN);
        assert_eq!(fixture["manifest"]["pe_sha256"], digest::sha256(&payload()));
        assert_eq!(fixture["records"].as_object().unwrap().len(), 7);
        for (key, record) in fixture["records"].as_object().unwrap() {
            let temp = tempfile::tempdir().unwrap();
            let base = temp.path().canonicalize().unwrap();
            let root = base.join("project");
            fs::create_dir(&root).unwrap();
            let source = base.join("probe.exe");
            fs::write(&source, payload()).unwrap();
            let parts: Vec<_> = key.split(':').collect();
            let mode = parts[parts.len() - 1];
            if parts[0] == "install" {
                let pin = json!({"url":source,"size":payload().len(),"sha256":digest::sha256(&payload())});
                let options = adoption::InstallOptions {
                    target: Some(TARGET),
                    artifact_pin: Some(&pin),
                    ..Default::default()
                };
                let result = adoption::install(&root, parts[1], &options, &mut adoption::LocalHost);
                assert_eq!(json!(result), record["value"], "{key}: {result:?}");
            } else if parts[0] == "receipt" {
                let path = root.join("receipt.json");
                let pin = json!({"path":".mir/bin/project-hooks.exe","sha256":digest::sha256(&payload())});
                if mode == "readonly" {
                    fs::write(&path, b"old").unwrap();
                    readonly(&path);
                }
                let result = hooks::write_receipt(&path, &pin);
                assert_eq!(
                    result.is_err(),
                    !record["error"].is_null(),
                    "{key}: {result:?}"
                );
            } else if parts[0] == "placement" {
                if mode != "valid" {
                    fs::create_dir(root.join("bin")).unwrap();
                    fs::write(root.join("bin/native-artifacts.json"), b"old").unwrap();
                }
                let result = place(&root, &digest::sha256(&payload()), &mut Host::default());
                assert!(result.is_ok(), "{key}: {result:?}");
                assert_eq!(
                    result
                        .unwrap()
                        .into_iter()
                        .map(|s| s + "\n")
                        .collect::<String>(),
                    record["stderr"],
                    "{key}"
                );
            } else if mode == "bytes" {
                let result = hooks::run_probe(hooks::ProbeRequest {
                    argv: [source.to_str().unwrap().into(), "capabilities".into()],
                    stdin: -3,
                    capture_output: true,
                    timeout: 2,
                    check: false,
                    cwd: &root,
                });
                assert!(result.is_ok(), "{key}: {:?}", result.as_ref().err());
                let output = result.unwrap();
                assert_eq!(json!(output.returncode), record["code"], "{key}");
                assert_eq!(hex(&output.stdout), record["stdout_hex"], "{key}");
                continue;
            }
            tree(&root, &record["tree"]);
        }
    }
}
