#![cfg(unix)]
#[path = "../src/digest.rs"]
mod digest;
#[path = "support/executable.rs"]
mod executable;
use handoff_packet::mir_cli::project_hooks;
use serde_json::{Value, json};
use std::{
    fs,
    io::Write,
    os::unix::fs::PermissionsExt,
    path::{Path, PathBuf},
    process::{Command, Stdio},
    time::{Duration, Instant},
};

const TARGET: &str = "aarch64-apple-darwin";
const GOOD: &[u8] = b"#!/bin/sh\nprintf 'mir-project-hooks-v1\\nmir-project-hooks-compact-v1\\n'\n";
#[test]
fn early_eof_uses_python_remaining_timeout_and_stays_bounded() {
    let temp = scratch();
    let script = temp.path().join("early-eof");
    executable::write(
        &script,
        b"#!/bin/sh\nexec >/dev/null 2>/dev/null\nexec /bin/sleep 3\n",
    )
    .unwrap();
    fs::set_permissions(&script, fs::Permissions::from_mode(0o755)).unwrap();
    let started = Instant::now();
    let error = project_hooks::run_probe(project_hooks::ProbeRequest {
        argv: [script.to_str().unwrap().into(), "capabilities".into()],
        stdin: -3,
        capture_output: true,
        timeout: 2,
        check: false,
        cwd: temp.path(),
    })
    .err()
    .unwrap();
    assert!(started.elapsed() >= Duration::from_millis(1900));
    assert!(started.elapsed() < Duration::from_secs(3));
    let remaining = error
        .split("timed out after ")
        .nth(1)
        .unwrap()
        .strip_suffix(" seconds")
        .unwrap();
    assert!(remaining.contains('.'), "{error}");
    assert!(remaining.parse::<f64>().unwrap() > 0.0);
    assert!(remaining.parse::<f64>().unwrap() < 2.0);
}
fn scratch() -> tempfile::TempDir {
    tempfile::tempdir_in(std::env::temp_dir().canonicalize().unwrap()).unwrap()
}
fn setup(base: &Path, bytes: &[u8]) -> (PathBuf, Value) {
    let root = base.join("project with spaces");
    fs::create_dir(&root).unwrap();
    let source = base.join("artifact");
    fs::write(&source, bytes).unwrap();
    let digest = digest::sha256(bytes);
    let metadata = json!({"schema_version":1,"provider_revision":"a".repeat(40),
        "plugins":{"mir-lifecycle-hooks":{}},"native_artifacts":{"project-hooks":{
        "plugin":"mir-lifecycle-hooks","install_path":"bin/project-hooks","targets":{TARGET:{
        "url":source,"size":bytes.len(),"sha256":digest}}}}});
    (root, metadata)
}
fn invoke(request: &Value, home: &Path) -> std::process::Output {
    invoke_with_home(request, Some(home))
}
fn invoke_with_home(request: &Value, home: Option<&Path>) -> std::process::Output {
    let mut command = Command::new(env!("CARGO_BIN_EXE_adoption-install"));
    command.env_remove("HOME");
    if let Some(home) = home {
        command.env("HOME", home);
    }
    let mut child = command
        .env_remove("MIR_CAPABILITY_NATIVE_ARTIFACTS")
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .unwrap();
    child
        .stdin
        .take()
        .unwrap()
        .write_all(serde_json::to_string(request).unwrap().as_bytes())
        .unwrap();
    child.wait_with_output().unwrap()
}
fn hooks(root: &Path, metadata: &Value, action: &str) -> Value {
    json!({"operation":"project-hooks","root":root,"metadata":metadata,"target":TARGET,"action":action,"disabled":false})
}
#[test]
fn real_host_installs_checks_and_preserves_receipt_bytes_modes_and_mtime() {
    let temp = scratch();
    let (root, metadata) = setup(temp.path(), GOOD);
    let request = hooks(&root, &metadata, "install");
    let installed = invoke(&request, temp.path());
    assert_eq!(installed.status.code(), Some(0), "{:?}", installed);
    assert_eq!(
        installed.stdout,
        b"project-hooks: ready (verified binary, receipt and capability probe)\n"
    );
    assert!(installed.stderr.is_empty());
    let binary = root.join(".mir/bin/project-hooks");
    let receipt = root.join(".mir/bin/project-hooks.json");
    let hash = metadata["native_artifacts"]["project-hooks"]["targets"][TARGET]["sha256"]
        .as_str()
        .unwrap();
    let expected =
        format!("{{\n  \"path\": \".mir/bin/project-hooks\",\n  \"sha256\": \"{hash}\"\n}}\n");
    assert_eq!(fs::read(&binary).unwrap(), GOOD);
    assert_eq!(fs::read(&receipt).unwrap(), expected.as_bytes());
    assert_eq!(
        fs::metadata(&binary).unwrap().permissions().mode() & 0o777,
        0o755
    );
    assert_eq!(
        fs::metadata(&receipt).unwrap().permissions().mode() & 0o777,
        0o600
    );
    let times = [
        fs::metadata(&binary).unwrap().modified().unwrap(),
        fs::metadata(&receipt).unwrap().modified().unwrap(),
    ];
    assert!(
        invoke(&hooks(&root, &metadata, "check"), temp.path())
            .status
            .success()
    );
    assert!(invoke(&request, temp.path()).status.success());
    assert_eq!(
        times,
        [
            fs::metadata(&binary).unwrap().modified().unwrap(),
            fs::metadata(&receipt).unwrap().modified().unwrap()
        ]
    );
}
#[test]
fn real_host_declines_unknown_requests_before_effects_and_warms_up() {
    let temp = scratch();
    let (root, _) = setup(temp.path(), GOOD);
    for request in [
        json!({"operation":"unknown","root":root}),
        json!({"operation":"project-hooks","root":root,"action":"unknown"}),
        json!({"operation":"install-artifact","root":root,"name":"../escape","target":TARGET}),
        json!({"operation":"install-artifact","root":root,"name":"project-hooks","target":TARGET,"local_source":"~unknown/artifact"}),
        json!({"operation":"install-artifact","root":root,"name":"project-hooks","target":TARGET,"local_source":"./~unknown/artifact"}),
    ] {
        let output = invoke(&request, temp.path());
        assert_eq!(output.status.code(), Some(64));
        assert!(output.stdout.is_empty());
        assert!(output.stderr.is_empty());
        assert_eq!(fs::read_dir(&root).unwrap().count(), 0);
    }
    for source in ["~/artifact", "./~/artifact", "./~unknown/artifact"] {
        let request = json!({"operation":"install-artifact","root":root,"name":"project-hooks","target":TARGET,"local_source":source});
        let output = invoke_with_home(&request, None);
        assert_eq!(output.status.code(), Some(64), "{source}: {output:?}");
        assert!(output.stdout.is_empty());
        assert!(output.stderr.is_empty());
        assert_eq!(fs::read_dir(&root).unwrap().count(), 0);
    }
    let output = Command::new(env!("CARGO_BIN_EXE_adoption-install"))
        .arg("--mir-warmup")
        .output()
        .unwrap();
    assert!(output.status.success());
    assert!(output.stdout.is_empty());
    assert!(output.stderr.is_empty());
}
#[test]
fn real_host_metadata_failures_have_no_project_effects() {
    let temp = scratch();
    let (root, metadata) = setup(temp.path(), GOOD);
    for (field, value, message) in [
        ("schema_version", json!(true), "invalid provider metadata"),
        (
            "schema_version",
            json!(2),
            "unsupported provider metadata schema",
        ),
        (
            "provider_revision",
            json!("main"),
            "invalid project-hooks provider identity",
        ),
    ] {
        let mut changed = metadata.clone();
        changed[field] = value;
        let output = invoke(&hooks(&root, &changed, "install"), temp.path());
        assert_eq!(output.status.code(), Some(1));
        assert_eq!(
            output.stdout,
            format!("project-hooks: degraded: {message}\n").as_bytes()
        );
        assert!(output.stderr.is_empty());
        assert_eq!(fs::read_dir(&root).unwrap().count(), 0);
    }
    let mut disabled = hooks(&root, &metadata, "install");
    disabled["disabled"] = json!(true);
    let output = invoke(&disabled, temp.path());
    assert_eq!(
        output.stdout,
        b"project-hooks: degraded: native artifacts disabled\n"
    );
    assert_eq!(fs::read_dir(&root).unwrap().count(), 0);
}
#[test]
fn real_host_capability_failure_never_publishes_receipt_and_timeout_is_bounded() {
    for data in [
        b"#!/bin/sh\nprintf 'mir-project-hooks-v1\\n'\n".as_slice(),
        b"#!/bin/sh\nprintf 'other-capability\\n'\n".as_slice(),
        b"#!/bin/sh\nexec /bin/sleep 20\n".as_slice(),
    ] {
        let temp = scratch();
        let (root, metadata) = setup(temp.path(), data);
        let start = Instant::now();
        let output = invoke(&hooks(&root, &metadata, "install"), temp.path());
        assert_eq!(output.status.code(), Some(1));
        assert!(output.stderr.is_empty());
        assert!(String::from_utf8_lossy(&output.stdout).starts_with("project-hooks: degraded: "));
        assert!(!root.join(".mir/bin/project-hooks.json").exists());
        assert!(start.elapsed() < Duration::from_secs(5));
        if data.contains(&b'2') {
            assert!(String::from_utf8_lossy(&output.stdout).contains("timed out after 2 seconds"));
        }
    }
}
#[test]
fn receipt_publication_stays_inside_pinned_directory_after_layout_mutation() {
    let temp = scratch();
    let root = temp.path().canonicalize().unwrap();
    let bin = root.join("bin");
    let outside = root.join("outside");
    fs::create_dir(&bin).unwrap();
    fs::create_dir(&outside).unwrap();
    let receipt = bin.join("project-hooks.json");
    fs::write(&receipt, b"old").unwrap();
    fs::write(outside.join("project-hooks.json"), b"outside").unwrap();
    let result = project_hooks::write_receipt_with(
        &receipt,
        &json!({"path":"x","sha256":"y"}),
        |source, dest| {
            let _ = (source, dest);
            fs::rename(&bin, root.join("saved-bin"))?;
            std::os::unix::fs::symlink(&outside, &bin)?;
            Ok(())
        },
    );
    assert!(result.is_err());
    assert_eq!(
        fs::read(outside.join("project-hooks.json")).unwrap(),
        b"outside"
    );
    assert_eq!(
        fs::read_dir(root.join("saved-bin")).unwrap().count(),
        1,
        "temporary receipt leaked into original pinned parent"
    );
}

#[test]
fn substituted_receipt_bytes_never_replace_the_previous_receipt() {
    for link in [false, true] {
        let temp = scratch();
        let root = temp.path().canonicalize().unwrap();
        let receipt = root.join("receipt");
        let outside = root.join("outside");
        fs::write(&receipt, b"old").unwrap();
        fs::write(&outside, b"outside sentinel").unwrap();
        let mut replacement = None;
        let result =
            project_hooks::write_receipt_with(&receipt, &json!({"path":"x"}), |source, _| {
                replacement = Some(source.to_path_buf());
                fs::rename(source, root.join("saved"))?;
                if link {
                    std::os::unix::fs::symlink(&outside, source)?;
                } else {
                    fs::write(source, b"unverified attacker bytes")?;
                }
                Ok(())
            });
        assert!(result.is_err());
        assert_eq!(fs::read(&receipt).unwrap(), b"old");
        assert_eq!(fs::read(&outside).unwrap(), b"outside sentinel");
        let replacement = replacement.unwrap();
        if link {
            assert_eq!(fs::read_link(&replacement).unwrap(), outside);
        } else {
            assert_eq!(
                fs::read(&replacement).unwrap(),
                b"unverified attacker bytes"
            );
        }
        assert_eq!(fs::read_dir(root).unwrap().count(), 4);
    }
}

#[test]
fn receipt_failure_cleanup_stays_in_original_parent_and_preserves_previous_receipt() {
    let temp = scratch();
    let root = temp.path().canonicalize().unwrap();
    let bin = root.join("bin");
    let outside = root.join("outside");
    fs::create_dir(&bin).unwrap();
    fs::create_dir(&outside).unwrap();
    let receipt = bin.join("project-hooks.json");
    fs::write(&receipt, b"old").unwrap();
    fs::write(outside.join("project-hooks.json"), b"outside").unwrap();
    let result =
        project_hooks::write_receipt_with(&receipt, &json!({"path":"x","sha256":"y"}), |_, _| {
            fs::rename(&bin, root.join("saved-bin"))?;
            std::os::unix::fs::symlink(&outside, &bin)?;
            Err(std::io::Error::other("injected placement failure"))
        });
    assert_eq!(result.unwrap_err(), "injected placement failure");
    assert_eq!(
        fs::read(outside.join("project-hooks.json")).unwrap(),
        b"outside"
    );
    assert_eq!(
        fs::read(root.join("saved-bin/project-hooks.json")).unwrap(),
        b"old"
    );
    assert_eq!(fs::read_dir(root.join("saved-bin")).unwrap().count(), 1);
}
#[test]
fn real_host_declines_network_pins_before_project_effects() {
    let temp = scratch();
    let (root, mut metadata) = setup(temp.path(), GOOD);
    metadata["native_artifacts"]["project-hooks"]["targets"][TARGET]["url"] =
        json!("https://invalid.example/artifact");
    let pin = &metadata["native_artifacts"]["project-hooks"]["targets"][TARGET];
    for request in [
        hooks(&root, &metadata, "install"),
        json!({"operation":"install-artifact","root":root,"name":"project-hooks","target":TARGET,"pin":pin}),
    ] {
        let output = invoke(&request, temp.path());
        assert_eq!(output.status.code(), Some(64));
        assert!(output.stdout.is_empty());
        assert!(output.stderr.is_empty());
        assert_eq!(fs::read_dir(&root).unwrap().count(), 0);
    }
}
#[test]
fn metadata_key_and_receipt_decode_errors_match_reference_messages() {
    let temp = scratch();
    let (root, metadata) = setup(temp.path(), GOOD);
    for (changed, message) in [
        (json!([]), "invalid provider metadata"),
        (
            json!({"schema_version":1,"native_artifacts":{}}),
            "'plugins'",
        ),
        (json!({"schema_version":1}), "'native_artifacts'"),
    ] {
        let output = invoke(&hooks(&root, &changed, "install"), temp.path());
        assert_eq!(output.status.code(), Some(1));
        assert_eq!(
            output.stdout,
            format!("project-hooks: degraded: {message}\n").as_bytes()
        );
    }
    assert!(
        invoke(&hooks(&root, &metadata, "install"), temp.path())
            .status
            .success()
    );
    let receipt = root.join(".mir/bin/project-hooks.json");
    fs::write(&receipt, b"{").unwrap();
    let output = invoke(&hooks(&root, &metadata, "check"), temp.path());
    assert_eq!(output.stdout,b"project-hooks: degraded: Expecting property name enclosed in double quotes: line 1 column 2 (char 1)\n");
    assert_eq!(output.status.code(), Some(1));
    fs::write(&receipt, br#"{"path":"\ud800"}"#).unwrap();
    let output = invoke(&hooks(&root, &metadata, "check"), temp.path());
    assert_eq!(
        output.stdout,
        b"project-hooks: degraded: project-hooks receipt mismatch\n"
    );
    assert_eq!(output.status.code(), Some(1));
    fs::remove_file(&receipt).unwrap();
    let output = invoke(&hooks(&root, &metadata, "check"), temp.path());
    assert_eq!(
        output.stdout,
        format!(
            "project-hooks: degraded: [Errno 2] No such file or directory: '{}'\n",
            receipt.display()
        )
        .as_bytes()
    );
    assert_eq!(output.status.code(), Some(1));
}

#[test]
fn real_host_accepts_parent_components_in_explicit_root_spelling() {
    let temp = scratch();
    let (root, metadata) = setup(temp.path(), GOOD);
    fs::create_dir(root.join("nested")).unwrap();
    let spelled = root.join("nested/..");
    let output = invoke(&hooks(&spelled, &metadata, "install"), temp.path());
    assert_eq!(output.status.code(), Some(0), "{output:?}");
    assert!(root.join(".mir/bin/project-hooks.json").is_file());
    assert!(
        invoke(&hooks(&spelled, &metadata, "check"), temp.path())
            .status
            .success()
    );
}

#[test]
fn real_host_accepts_receipt_json_byte_encodings() {
    let temp = scratch();
    let (root, metadata) = setup(temp.path(), GOOD);
    assert!(
        invoke(&hooks(&root, &metadata, "install"), temp.path())
            .status
            .success()
    );
    let receipt = root.join(".mir/bin/project-hooks.json");
    let text = fs::read_to_string(&receipt).unwrap();
    let mut utf16 = vec![0xff, 0xfe];
    for unit in text.encode_utf16() {
        utf16.extend(unit.to_le_bytes());
    }
    let mut utf32 = vec![0, 0, 0xfe, 0xff];
    for unit in text.chars() {
        utf32.extend(u32::from(unit).to_be_bytes());
    }
    for bytes in [utf16, utf32] {
        fs::write(&receipt, &bytes).unwrap();
        let output = invoke(&hooks(&root, &metadata, "check"), temp.path());
        assert_eq!(output.status.code(), Some(0), "{output:?}");
        assert_eq!(fs::read(&receipt).unwrap(), bytes);
    }
}

#[test]
fn artifact_host_expands_tilde_from_synthetic_environment_home() {
    let temp = scratch();
    let (root, metadata) = setup(temp.path(), GOOD);
    let output = invoke(
        &json!({"operation":"install-artifact","root":root,"name":"project-hooks","target":TARGET,"local_source":"~//artifact"}),
        temp.path(),
    );
    assert_eq!(output.status.code(), Some(0), "{output:?}");
    assert_eq!(
        serde_json::from_slice::<Value>(&output.stdout).unwrap(),
        json!({"path":".mir/bin/project-hooks","sha256":metadata["native_artifacts"]["project-hooks"]["targets"][TARGET]["sha256"]})
    );
    assert_eq!(fs::read(root.join(".mir/bin/project-hooks")).unwrap(), GOOD);
}

#[test]
fn private_host_declines_unrepresentable_reader_sizes_before_effects() {
    let temp = scratch();
    let (root, metadata) = setup(temp.path(), GOOD);
    for size in [
        json!(isize::MAX as u64),
        serde_json::from_str::<Value>("18446744073709551616").unwrap(),
    ] {
        let mut metadata = metadata.clone();
        metadata["native_artifacts"]["project-hooks"]["targets"][TARGET]["size"] = size;
        let pin = &metadata["native_artifacts"]["project-hooks"]["targets"][TARGET];
        let provider = temp.path().join("provider");
        fs::create_dir_all(provider.join(".mir")).unwrap();
        fs::write(
            provider.join(".mir/capability-lock.json"),
            serde_json::to_vec(&metadata).unwrap(),
        )
        .unwrap();
        for request in [
            hooks(&root, &metadata, "install"),
            json!({"operation":"install-artifact","root":root,"name":"project-hooks","target":TARGET,"pin":pin}),
            json!({"operation":"install-artifact","root":root,"name":"project-hooks","target":TARGET,"source_root":provider}),
        ] {
            let output = invoke(&request, temp.path());
            assert_eq!(output.status.code(), Some(64), "{output:?}");
            assert!(output.stdout.is_empty());
            assert!(output.stderr.is_empty());
            assert_eq!(fs::read_dir(&root).unwrap().count(), 0);
        }
    }
    // Preserve the raw unbounded integer spelling: serde Value would round-trip
    // this as an exponent float and miss the shared reader's numeric-tag route.
    let provider = temp.path().join("raw-provider");
    fs::create_dir_all(provider.join(".mir")).unwrap();
    let raw = serde_json::to_string(&metadata).unwrap().replacen(
        &format!("\"size\":{}", GOOD.len()),
        "\"size\":18446744073709551616",
        1,
    );
    assert!(raw.contains("\"size\":18446744073709551616"));
    fs::write(provider.join(".mir/capability-lock.json"), raw).unwrap();
    let request = json!({"operation":"install-artifact","root":root,"name":"project-hooks","target":TARGET,"source_root":provider});
    let output = invoke(&request, temp.path());
    assert_eq!(output.status.code(), Some(64), "{output:?}");
    assert!(output.stdout.is_empty());
    assert!(output.stderr.is_empty());
    assert_eq!(fs::read_dir(&root).unwrap().count(), 0);
}
