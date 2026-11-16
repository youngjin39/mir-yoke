#[path = "../src/digest.rs"]
mod digest;
#[path = "../src/entry_supply.rs"]
mod entry_supply;
use serde_json::Value;
use std::{fs, process::Command};

fn records(windows: bool) -> Vec<Value> {
    // Regenerate the Windows counterpart with generate_y_e13.py on Windows.
    // Initial CRLF projection requires the PC capture recorded in the S11 report.
    let fixture = if windows {
        include_str!("fixtures/y-e13-windows.json")
    } else {
        include_str!("fixtures/y-e13.json")
    };
    serde_json::from_str(fixture).unwrap()
}

#[test]
fn platform_records_preserve_console_bytes() {
    let unix = records(false);
    let windows = records(true);
    assert_eq!(unix.len(), 124);
    assert_eq!(windows.len(), 121);
    let exercised: Vec<_> = unix
        .iter()
        .filter(|r| {
            !["local", "probe", "receipt"]
                .iter()
                .any(|m| r["mode"] == *m)
        })
        .collect();
    for (reference, captured) in exercised.into_iter().zip(windows) {
        for field in ["mode", "argv", "exit"] {
            assert_eq!(reference[field], captured[field]);
        }
        for field in ["stdout", "stderr"] {
            assert_eq!(
                reference[field].as_str().unwrap().replace("\n", "\r\n"),
                captured[field]
            );
        }
    }
}

#[test]
fn frozen_relations_and_project_hooks() {
    let records = records(cfg!(windows));
    let malformed = entry_supply::hooks_resource(&["check", "--project-root", "."], "{", None);
    assert_eq!(malformed.0, 1);
    assert!(
        String::from_utf8(malformed.1)
            .unwrap()
            .contains("project-hooks: degraded: EOF")
    );
    let mut failures = Vec::new();
    for r in records {
        let temp = tempfile::tempdir().unwrap();
        let root = temp.path().canonicalize().unwrap();
        fs::create_dir(root.join("spec")).unwrap();
        fs::write(
            root.join("spec/graph.yaml"),
            "edges: [[x, implemented_in, src/a.rs]]\n",
        )
        .unwrap();
        if ["local", "probe", "receipt"]
            .iter()
            .any(|m| r["mode"] == *m)
        {
            #[cfg(unix)]
            {
                let data = if r["mode"] == "probe" {
                    b"#!/bin/sh\nexit 1\n".as_slice()
                } else {
                    b"#!/bin/sh\nprintf 'mir-project-hooks-v1\\nmir-project-hooks-compact-v1\\n'\n"
                };
                let artifact = root.join("artifact");
                fs::write(&artifact, data).unwrap();
                let target = "aarch64-apple-darwin";
                let metadata = serde_json::json!({"schema_version":1,"provider_revision":"a".repeat(40),
                    "plugins":{"mir-lifecycle-hooks":{}},"native_artifacts":{"project-hooks":{
                        "plugin":"mir-lifecycle-hooks","install_path":"bin/project-hooks","targets":{target:{
                            "url":artifact.to_str().unwrap(),"size":data.len(),
                            "sha256":digest::sha256(data)}}}}});
                let action = r["argv"][1].as_str().unwrap();
                let args = [action, "--project-root", root.to_str().unwrap()];
                let (code, out, err) = entry_supply::hooks(&args, &metadata, Some(target));
                assert_eq!(code, r["exit"].as_i64().unwrap() as i32, "{r}");
                assert_eq!(
                    String::from_utf8(out)
                        .unwrap()
                        .replace(root.to_str().unwrap(), "{ROOT}"),
                    r["stdout"]
                );
                assert_eq!(String::from_utf8(err).unwrap(), r["stderr"]);
                if r["mode"] == "local" {
                    assert_eq!(fs::read(root.join(".mir/bin/project-hooks")).unwrap(), data);
                    assert_eq!(
                        entry_supply::hooks(
                            &["check", "--project-root", root.to_str().unwrap()],
                            &metadata,
                            Some(target)
                        )
                        .0,
                        0
                    );
                    for url in ["https://invalid.example/artifact", "~named/artifact"] {
                        let mut declined = metadata.clone();
                        declined["native_artifacts"]["project-hooks"]["targets"][target]["url"] =
                            url.into();
                        let result = entry_supply::hooks(&args, &declined, Some(target));
                        assert_eq!(result.0, 1);
                        assert_eq!(result.1, b"project-hooks: degraded: verified project-hooks placement unavailable\n");
                    }
                    // Switch the validated parent at the reused installer's pre-replace seam.
                    use handoff_packet::mir_cli::adoption_native::{self as a, InstallHost};
                    struct Race;
                    impl InstallHost for Race {
                        fn before_replace(
                            &mut self,
                            _: &std::path::Path,
                            dest: &std::path::Path,
                        ) -> std::io::Result<()> {
                            let parent = dest.parent().unwrap();
                            fs::rename(parent, parent.with_extension("saved"))?;
                            std::os::unix::fs::symlink("../../outside", parent)
                        }
                    }
                    let raced = root.join("race");
                    fs::create_dir(&raced).unwrap();
                    fs::create_dir(root.join("outside")).unwrap();
                    let pin = &metadata["native_artifacts"]["project-hooks"]["targets"][target];
                    assert!(
                        a::install_project_hooks(
                            &raced,
                            &a::InstallOptions {
                                target: Some(target),
                                artifact_pin: Some(pin),
                                ..Default::default()
                            },
                            &mut Race
                        )
                        .is_none()
                    );
                    assert_eq!(fs::read_dir(root.join("outside")).unwrap().count(), 0);
                }
            }
            continue;
        }
        // Exercise the same dispatcher used by the public root, including the resource path.
        if r["argv"][0] == "project-hooks" && r["argv"][1] == "--help" {
            assert_eq!(entry_supply::console("project-hooks", &["--help"]).0, 0);
        }
        if r["mode"] == "bad" {
            fs::create_dir(root.join(".mir")).unwrap();
            fs::write(root.join(".mir/memory.db"), b"not a database").unwrap();
        } else if r["mode"] == "valid" {
            use handoff_packet::mir_core::memory::store;
            let c = store::connect(
                &root.join(".mir/memory.db"),
                store::ConnectOptions {
                    timeout: None,
                    vec_loading: store::VecLoading::Bundled,
                },
            )
            .unwrap();
            store::apply_migrations(&c.conn).unwrap();
        }
        let out = Command::new(env!("CARGO_BIN_EXE_mir"))
            .args(r["argv"].as_array().unwrap().iter().map(|v| {
                v.as_str()
                    .unwrap()
                    .replace("{ROOT}", root.to_str().unwrap())
            }))
            .env_clear()
            .env("HOME", &root)
            .current_dir(&root)
            .output()
            .unwrap();
        let actual = serde_json::json!({"exit":out.status.code(),
            "stdout":String::from_utf8(out.stdout).unwrap(),
            "stderr":String::from_utf8(out.stderr).unwrap()});
        if actual["exit"] != r["exit"]
            || actual["stdout"] != r["stdout"]
            || actual["stderr"] != r["stderr"]
        {
            failures.push(format!("{}: {actual} != {r}", r["argv"]));
        }
    }
    assert!(failures.is_empty(), "{}", failures.join("\n"));
}
