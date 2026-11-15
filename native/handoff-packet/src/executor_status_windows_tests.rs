//! Windows-only real filesystem path tests, separate from the child-free runtime.
use super::*;

#[path = "../tests/support/wt_path.rs"]
mod frozen;

#[test]
fn wt_path_status_matches_windows_capture() {
    let (_temp, root, records) = frozen::setup();
    let mut checked = 0;
    for record in records {
        let route = record["route"].as_str().unwrap();
        if let Some(name) = route.strip_prefix("readlink.") {
            let actual = fs::read_link(root.join(if name == "ordinary" { "notes" } else { name }));
            if record.get("error").is_some() {
                assert_eq!(
                    actual.unwrap_err().raw_os_error(),
                    record["winerror"].as_i64().map(|n| n as i32)
                );
            } else {
                assert_eq!(
                    serde_json::json!(actual.unwrap()),
                    record["value"],
                    "{route}"
                );
            }
        } else if route.starts_with("status.") || route == "absent_selector.root" {
            let relative = match route {
                "status.ordinary" => "notes",
                "status.missing" => "missing/leaf",
                "status.missing_parent" => "missing/../notes",
                "status.file_child" => "file/child",
                "status.default_db" => "tasks/jobs.db",
                "absent_selector.root" => "",
                "status.alias" => "alias/leaf",
                "status.escape" => "escape/leaf",
                "status.dangling" => "dangling/leaf",
                "status.drive_root" => record["value"].as_str().unwrap(),
                _ => panic!("uncaptured status route: {route}"),
            };
            let actual = serde_json::json!(resolve(&root.join(relative)).unwrap());
            assert_eq!(actual, record["value"], "{route}");
        } else {
            continue;
        }
        checked += 1;
    }
    assert_eq!(checked, 14);
}

#[test]
fn wt_path_drive_missing_and_junction() {
    let temp = tempfile::tempdir().unwrap();
    let root = handoff_packet::supply::plain(temp.path().canonicalize().unwrap());
    let drive: PathBuf = root.components().take(2).collect();
    assert_eq!(resolve(&drive).unwrap(), drive);
    fs::create_dir(root.join("notes")).unwrap();
    assert_eq!(resolve(&root.join("notes")).unwrap(), root.join("notes"));
    assert_eq!(
        resolve(&root.join("missing/../notes")).unwrap(),
        root.join("notes")
    );
    assert_eq!(
        resolve(&root.join("missing/leaf")).unwrap(),
        root.join("missing/leaf")
    );
    let junction = std::process::Command::new("cmd.exe")
        .args(["/D", "/C", "mklink", "/J"])
        .arg(root.join("alias"))
        .arg(root.join("notes"))
        .current_dir(&root)
        .env("HOME", &root)
        .output()
        .unwrap();
    assert!(junction.status.success(), "{junction:?}");
    assert_eq!(
        resolve(&root.join("alias/leaf")).unwrap(),
        root.join("notes/leaf")
    );
}
