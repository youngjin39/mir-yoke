//! Replay the unmodified Python B30 oracle through library-only Rust modules.
#![forbid(unsafe_code)]
use handoff_packet::mir_cli::changes;
use serde_json::{Value, json};
use std::{fs, path::Path};

#[path = "b30_capability_support/mod.rs"]
mod capability;
#[path = "b30_hooks_support/mod.rs"]
mod hooks;
#[path = "b30_native_support/mod.rs"]
mod native;

fn windows_exemption(name: &str) -> Option<&'static str> {
    if cfg!(windows) {
        match name {
            "changes.snapshot_and_diff"
            | "native.project_hooks.linked"
            | "native.project_hooks.linked-parent"
            | "hooks.path.normal" => {
                return Some("symlink creation requires Windows host privilege");
            }
            "hooks.check.not-executable" => {
                return Some("Unix executable permission has no Windows equivalent");
            }
            _ => {}
        }
    }
    None
}

fn snapshot_case(tmp: &Path) -> Value {
    fs::write(tmp.join("a"), "before").unwrap();
    fs::create_dir(tmp.join(".git")).unwrap();
    fs::write(tmp.join(".git/ignored"), "ignored").unwrap();
    #[cfg(unix)]
    std::os::unix::fs::symlink("a", tmp.join("link")).unwrap();
    let before = changes::snapshot_project(tmp).unwrap();
    fs::remove_file(tmp.join("a")).unwrap();
    fs::write(tmp.join("z"), "after").unwrap();
    let after = changes::snapshot_project(tmp).unwrap();
    let paths = changes::changed_paths(&before, &after);
    json!({"value": [before, after, paths]})
}

fn excluded_case(tmp: &Path) -> Value {
    for name in [
        ".git/a",
        ".pytest_cache/b",
        ".venv/c",
        "__pycache__/d.pyc",
        "pkg/__pycache__/m.pyc",
        "pkg/.venv/e",
        "docs/.git",
        ".venvx/keep",
        "pkg/__pycache__x/n",
        "pkg/keep.py",
    ] {
        let path = tmp.join(name);
        fs::create_dir_all(path.parent().unwrap()).unwrap();
        fs::write(path, name).unwrap();
    }
    let keys: Vec<_> = changes::snapshot_project(tmp)
        .unwrap()
        .into_keys()
        .collect();
    json!({"value": keys})
}

#[test]
fn every_frozen_record_replays_exactly() {
    let records: Value =
        serde_json::from_str(include_str!("fixtures/w2/b30-capability.json")).unwrap();
    let records = records.as_object().unwrap();
    assert_eq!(records.len(), 60);
    let (mut replayed, mut exempt) = (0, 0);
    for (name, expected) in records {
        if let Some(reason) = windows_exemption(name) {
            eprintln!("EXEMPT {name}: {reason}");
            exempt += 1;
            continue;
        }
        let root = tempfile::Builder::new().prefix("b30-").tempdir().unwrap();
        assert!(root.path().starts_with(std::env::temp_dir()));
        let observed = if name.starts_with("native.") {
            native::replay(name, root.path())
        } else if name.starts_with("hooks.") {
            hooks::replay(name, root.path())
        } else if name.starts_with("capability.") {
            capability::replay(name, root.path())
        } else if name == "changes.excluded" {
            excluded_case(root.path())
        } else {
            assert_eq!(name, "changes.snapshot_and_diff");
            snapshot_case(root.path())
        };
        // Match observe(): serialize first, then replace only the case's temporary root.
        let actual = serde_json::to_string(&observed).unwrap();
        let prefix = serde_json::to_string(root.path().to_str().unwrap()).unwrap();
        let actual = actual.replace(&prefix[1..prefix.len() - 1], "<tmp>");
        let actual: Value = serde_json::from_str(&actual).unwrap();
        assert_eq!(&actual, expected, "record {name}");
        replayed += 1;
    }
    assert_eq!(replayed + exempt, 60);
    assert_eq!(exempt, if cfg!(windows) { 5 } else { 0 });
    eprintln!("B30: replayed={replayed}, deferred=0, exempt={exempt}, total=60");
}
