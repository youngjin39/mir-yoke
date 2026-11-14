use super::*;
use crate::{
    adoption_fs, user_runtime_mutation::PendingWrite, user_runtime_transaction as transaction,
};
use std::ffi::OsStr;

#[test]
fn homes_alias_overlap_and_replacement_are_checked() {
    let t = tempfile::tempdir().unwrap();
    let root = t.path().canonicalize().unwrap();
    let home = root.join("Home");
    fs::create_dir_all(home.join("nested")).unwrap();
    let id = capture_home_identity(&home).unwrap();
    let alias = capture_home_identity(&root.join("hOME")).unwrap();
    let nested = capture_home_identity(&home.join("nested")).unwrap();
    assert!(runtime_homes_overlap(&id, &alias));
    assert!(runtime_homes_overlap(&id, &nested));
    assert!(runtime_homes_overlap(&nested, &id));
    let safe = require_safe_home(&home);
    assert!(safe.is_ok(), "home {home:?}: {safe:?}");
    fs::rename(&home, root.join("saved")).unwrap();
    fs::create_dir(&home).unwrap();
    let replaced = verified_target(&id, Path::new("new.md"));
    assert!(replaced.is_err(), "replaced home: {replaced:?}");
    assert!(!home.join("new.md").exists());
    let missing = capture_home_identity(&root.join("missing"));
    assert!(missing.is_err(), "missing home: {missing:?}");
}
#[test]
fn case_and_hardlink_temporary_aliases_have_no_effect() {
    let t = tempfile::tempdir().unwrap();
    let root = t.path().canonicalize().unwrap();
    let target = root.join("payload.md");
    fs::write(&target, b"original").unwrap();
    for alias in ["PAYLOAD.MD", "alias.md"] {
        if alias == "alias.md" {
            fs::hard_link(&target, root.join(alias)).unwrap();
        }
        let error = PendingWrite::prepare(&root, &target, OsStr::new(alias), b"new")
            .err()
            .unwrap();
        assert_eq!(error.kind(), io::ErrorKind::InvalidInput, "{error:?}");
        assert_eq!(fs::read(&target).unwrap(), b"original");
    }
}
#[test]
fn transaction_reaches_shared_windows_write_and_receipt_path() {
    let t = tempfile::tempdir().unwrap();
    let home = t.path().canonicalize().unwrap();
    let plan = transaction::RuntimePlan {
        identity: capture_home_identity(&home).unwrap(),
        files: vec![],
        stale: vec![],
        receipt: b"receipt".to_vec(),
        created_home: false,
    };
    transaction::apply_transaction(&[plan]).unwrap();
    assert_eq!(fs::read(home.join(RECEIPT_NAME)).unwrap(), b"receipt");
    assert!(
        !fs::metadata(home.join(RECEIPT_NAME))
            .unwrap()
            .permissions()
            .readonly()
    );
}
#[test]
fn windows_component_order_and_equal_keys_match_pathlib() {
    transaction::windows_core_order_test();
    assert_ne!(
        adoption_fs::path_key(Path::new("agents/ΟΣ\u{1c89}.md")),
        adoption_fs::path_key(Path::new("agents/Οσ\u{1c89}.md"))
    );
    assert_ne!(
        adoption_fs::path_key(Path::new("agents/\u{1c89}.md")),
        adoption_fs::path_key(Path::new("agents/\u{1c8a}.md"))
    );
    let root = Path::new("C:\\synthetic");
    let surrogate = python_json::Text::new(vec![0x41, 0xd800, 0x42]);
    assert_eq!(
        crate::executor_text::os_points(source_path(root, &surrogate).unwrap().as_os_str()),
        surrogate.codepoints
    );
}

#[test]
fn junction_home_swap_fails_before_transaction_effects() {
    let t = tempfile::tempdir().unwrap();
    let root = t.path().canonicalize().unwrap();
    let home = root.join("home");
    let outside = root.join("outside");
    fs::create_dir(&home).unwrap();
    fs::create_dir(&outside).unwrap();
    fs::write(outside.join(RECEIPT_NAME), b"outside").unwrap();
    let plan = transaction::RuntimePlan {
        identity: capture_home_identity(&home).unwrap(),
        files: vec![],
        stale: vec![],
        receipt: b"new".to_vec(),
        created_home: false,
    };
    let mut reached = false;
    let result = transaction::transaction_with(&[plan], |phase, _, _| {
        if phase == "snapshot" {
            reached = true;
            fs::rename(&home, root.join("saved")).unwrap();
            let junction = std::process::Command::new("cmd")
                .args(["/C", "mklink", "/J"])
                .arg(&home)
                .arg(&outside)
                .output()
                .unwrap();
            assert!(junction.status.success(), "{junction:?}");
        }
        Ok(())
    });
    assert!(reached && result.is_err(), "reached={reached}, {result:?}");
    let safe = require_safe_home(&home);
    assert!(safe.is_err(), "junction home: {safe:?}");
    let target = safe_target(&root, Path::new("home"));
    assert!(target.is_err(), "junction target: {target:?}");
    assert_eq!(fs::read(outside.join(RECEIPT_NAME)).unwrap(), b"outside");
    fs::remove_dir(home).unwrap();
}

#[test]
fn short_home_alias_uses_full_object_identity() {
    let t = tempfile::tempdir().unwrap();
    let home = t
        .path()
        .canonicalize()
        .unwrap()
        .join("long-runtime-home-name");
    fs::create_dir(&home).unwrap();
    let short = adoption_fs::short_path(&home);
    assert!(
        short.file_name().unwrap().to_string_lossy().contains('~'),
        "8.3 capability precondition: short names must be enabled on the PC test volume"
    );
    assert!(runtime_homes_overlap(
        &capture_home_identity(&home).unwrap(),
        &capture_home_identity(&short).unwrap()
    ));
}

#[test]
fn mode_updates_live_handle_and_propagates_real_access_denial() {
    crate::user_runtime_transaction::windows_core_order_test();
    let t = tempfile::tempdir().unwrap();
    let root = t.path().canonicalize().unwrap();
    let stage = adoption_fs::StagedFile::create(&root, &root.join("stage")).unwrap();
    adoption_fs::set_mode(&stage.file, 0o444).unwrap();
    assert!(stage.file.metadata().unwrap().permissions().readonly());
    adoption_fs::set_mode(&stage.file, 0o644).unwrap();
    assert!(!stage.file.metadata().unwrap().permissions().readonly());
    let readonly_handle = fs::File::open(&stage.path).unwrap();
    let error = adoption_fs::set_mode(&readonly_handle, 0o444).unwrap_err();
    assert_eq!(error.raw_os_error(), Some(5), "{error:?}");
    assert!(!stage.file.metadata().unwrap().permissions().readonly());
    drop(readonly_handle);
    stage.remove().unwrap();
}
