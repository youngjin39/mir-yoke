//! Windows-only real filesystem path tests, separate from the child-free runtime.
use super::*;

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
