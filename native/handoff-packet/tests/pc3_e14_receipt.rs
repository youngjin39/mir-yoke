use handoff_packet::mir_cli::bootstrap_adoption::write_receipt_with;
use serde_json::Value;
use std::{fs, path::Path};

#[test]
fn directory_destination_preserves_both_names_and_cleanup() {
    let temp = tempfile::tempdir().unwrap();
    let root = temp.path().canonicalize().unwrap();
    let destination = root.join("receipt.json");
    fs::create_dir(&destination).unwrap();
    let mut staged = None;
    let error = write_receipt_with(
        &destination,
        &serde_json::json!({"ready":true}),
        |from, to| {
            assert_eq!(to, destination);
            assert!(from.is_file());
            staged = Some(from.to_owned());
            Ok(())
        },
    )
    .unwrap_err();
    let staged = staged.unwrap();
    let record: Vec<Value> =
        serde_json::from_slice(include_bytes!("fixtures/y-e14-windows.json")).unwrap();
    let record = record.iter().find(|r| r["mode"] == "receipt-dir").unwrap();
    assert_eq!(record["exit"], 1);
    assert_eq!(record["stdout"], "");
    let rendered = format!("{}: {}\r\n", error.class(), error);
    if cfg!(windows) {
        // Match only the varying names; every other byte, including CRLF, is frozen.
        let repr = |path: &Path| {
            format!(
                "'{}'",
                path.display()
                    .to_string()
                    .replace('/', r"\")
                    .replace('\\', r"\\")
            )
        };
        let expected = record["stderr"].as_str().unwrap();
        let source_start = expected.find(": '").unwrap() + 2;
        let actual = format!(
            "{}{} -> {}\r\n",
            &expected[..source_start],
            repr(&staged),
            repr(&destination)
        );
        assert_eq!(rendered.as_bytes(), actual.as_bytes());
    } else {
        assert_eq!(error.class(), "IsADirectoryError");
        assert!(rendered.contains(&staged.display().to_string()));
        assert!(rendered.contains(&format!(" -> '{}'", destination.display())));
    }
    assert!(destination.is_dir());
    assert!(!staged.exists());
    assert_eq!(fs::read_dir(root).unwrap().count(), 1);
}

#[test]
fn receipt_physical_bytes_remain_frozen() {
    let fixture = if cfg!(windows) {
        include_bytes!("fixtures/y-e14-receipt-bytes-windows.json").as_slice()
    } else {
        include_bytes!("fixtures/y-e14-receipt-bytes.json").as_slice()
    };
    let record: Value = serde_json::from_slice(fixture).unwrap();
    let temp = tempfile::tempdir().unwrap();
    let path = temp.path().canonicalize().unwrap().join("receipt.json");
    write_receipt_with(&path, &record["payload"], |_, _| Ok(())).unwrap();
    let bytes = fs::read(path).unwrap();
    let hex: String = bytes.iter().map(|b| format!("{b:02x}")).collect();
    assert_eq!(hex, record["physical_hex"]);
}

#[test]
fn substituted_parent_preserves_outside_bytes() {
    let temp = tempfile::tempdir().unwrap();
    let root = temp.path().canonicalize().unwrap();
    let parent = root.join("project");
    let outside = root.join("outside");
    fs::create_dir(&parent).unwrap();
    fs::create_dir(&outside).unwrap();
    let path = parent.join("receipt.json");
    fs::write(outside.join("receipt.json"), b"preserve").unwrap();
    let result = write_receipt_with(&path, &serde_json::json!({"ready":true}), |source, _| {
        // A matching staged name outside makes accidental pathname publication observable.
        fs::copy(source, outside.join(source.file_name().unwrap()))?;
        fs::rename(&parent, root.join("saved"))?;
        #[cfg(unix)]
        std::os::unix::fs::symlink(&outside, &parent)?;
        #[cfg(windows)]
        {
            let output = std::process::Command::new("cmd.exe")
                .args(["/D", "/C", "mklink", "/J"])
                .arg(&parent)
                .arg(&outside)
                .current_dir(&root)
                .output()?;
            assert!(output.status.success(), "{output:?}");
        }
        Ok(())
    });
    assert!(result.is_err());
    assert_eq!(fs::read(outside.join("receipt.json")).unwrap(), b"preserve");
    assert_eq!(fs::read_dir(&outside).unwrap().count(), 2);
    // Remove the junction itself before TempDir cleanup; never traverse it.
    #[cfg(windows)]
    fs::remove_dir(parent).unwrap();
}
