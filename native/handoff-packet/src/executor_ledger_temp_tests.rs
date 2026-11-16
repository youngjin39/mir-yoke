use super::*;

#[cfg(windows)]
#[test]
fn windows_executor_input_errors() {
    use crate::executor_text::windows_frozen_error;
    let temp = tempfile::tempdir().unwrap();
    let missing = temp.path().join("missing");
    let args = json!({"codex_args_file":{"value":missing}});
    let local = LocalConfig::default();
    assert_eq!(
        resolve_args(&args, temp.path(), &local).unwrap_err(),
        windows_frozen_error("replace-missing", &missing)
    );
    let args = json!({"codex_args_file":{"value":temp.path()}});
    assert_eq!(
        resolve_args(&args, temp.path(), &local).unwrap_err(),
        windows_frozen_error("crt-lock-read", temp.path())
    );
}

#[cfg(windows)]
#[test]
fn windows_executor_temp_open_error() {
    use crate::executor_text::windows_frozen_error;
    let temp = tempfile::tempdir().unwrap();
    names(&["candidate.tmp"]);
    let parent = temp.path().join("absent");
    let error = create_ledger_temp(&parent, |name| {
        let result = fs::File::create_new(parent.join(name));
        assert_eq!(result.as_ref().unwrap_err().raw_os_error(), Some(3));
        result
    })
    .unwrap_err();
    assert_eq!(
        error,
        windows_frozen_error("read-missing", &parent.join("candidate.tmp"))
    );
}

#[cfg(windows)]
#[test]
fn windows_executor_registry_open_error() {
    let temp = tempfile::tempdir().unwrap();
    let path = temp.path().join("bad<name");
    let error = JobRegistry::open(&path).err().unwrap();
    match &error {
        crate::executor_registry::Error::Io(cause, _) => {
            assert_eq!(cause.raw_os_error(), Some(123));
            assert_eq!(format!("{error:?}"), format!("Io({cause:?})"));
        }
        _ => panic!("expected the real open failure: {error:?}"),
    }
    let rendered = crate::executor_text::registry_error(error, &path);
    // Frozen win32-invalid-name: real code 123 maps to CRT errno 22.
    assert!(rendered.starts_with("OSError: [Errno 22] "), "{rendered}");
}

fn names(values: &[&str]) {
    LEDGER_TEMP_NAMES.with(|names| {
        *names.borrow_mut() = values.iter().rev().map(OsString::from).collect();
    });
}

fn reference() -> Value {
    serde_json::from_str(include_str!(
        "../tests/fixtures/executor_ledger_temp_reference.json"
    ))
    .unwrap()
}

#[test]
fn ledger_temp_collision_retries_without_removing_existing_file() {
    let root = tempfile::tempdir().unwrap();
    let ledger = root.path().join("tdd.json");
    fs::write(&ledger, "original").unwrap();
    let collision = root.path().join(".mir-executor-reviewcollision.tmp");
    fs::write(&collision, "collision-owner").unwrap();
    names(&[
        ".mir-executor-reviewcollision.tmp",
        ".mir-executor-aftercollision.tmp",
    ]);
    let result = write_ledger(&ledger, "updated");
    assert_eq!(fs::read_to_string(&collision).unwrap(), "collision-owner");
    result.unwrap();
    assert_eq!(fs::read_to_string(&ledger).unwrap(), "updated");
    assert_eq!(fs::read_dir(root.path()).unwrap().count(), 2);
    assert!(reference()["records"]["collision"]["error"].is_null());
}

#[test]
fn ledger_temp_exhaustion_preserves_every_candidate() {
    let root = tempfile::tempdir().unwrap();
    let ledger = root.path().join("tdd.json");
    fs::write(&ledger, "original").unwrap();
    let candidates = ["one.tmp", "two.tmp", "three.tmp"];
    for name in candidates {
        fs::write(root.path().join(name), name).unwrap();
    }
    names(&candidates);
    let reference = reference();
    assert_eq!(reference["test_retry_bound"], candidates.len());
    LEDGER_TEMP_LIMIT.with(|limit| limit.set(Some(candidates.len())));
    let result = write_ledger(&ledger, "updated");
    LEDGER_TEMP_LIMIT.with(|limit| limit.set(None));
    for name in candidates {
        assert_eq!(fs::read_to_string(root.path().join(name)).unwrap(), name);
    }
    assert_eq!(
        result.unwrap_err(),
        reference["records"]["exhaustion"]["error"]
            .as_str()
            .unwrap()
    );
    assert!(LEDGER_TEMP_NAMES.with(|names| names.borrow().is_empty()));
    assert_eq!(fs::read_to_string(&ledger).unwrap(), "original");
}

#[test]
fn ledger_temp_cleanup_preserves_substituted_file() {
    let root = tempfile::tempdir().unwrap();
    let ledger = root.path().join("tdd.json");
    fs::write(&ledger, "original").unwrap();
    names(&["candidate.tmp"]);
    let parent = root.path().to_owned();
    BEFORE_LEDGER_REPLACE.with(|hook| {
        *hook.borrow_mut() = Some(Box::new(move || {
            fs::rename(parent.join("candidate.tmp"), parent.join("retained.tmp")).unwrap();
            fs::write(parent.join("candidate.tmp"), "other-owner").unwrap();
            fs::remove_file(parent.join("tdd.json")).unwrap();
            fs::create_dir(parent.join("tdd.json")).unwrap();
        }))
    });
    assert!(write_ledger(&ledger, "updated").is_err());
    assert_eq!(
        fs::read_to_string(root.path().join("candidate.tmp")).unwrap(),
        "other-owner"
    );
    assert_eq!(
        fs::read_to_string(root.path().join("retained.tmp")).unwrap(),
        "updated"
    );
}

#[test]
fn ledger_temp_failure_cleans_its_own_file() {
    let root = tempfile::tempdir().unwrap();
    let ledger = root.path().join("tdd.json");
    fs::create_dir(&ledger).unwrap();
    names(&["candidate.tmp"]);
    assert!(write_ledger(&ledger, "updated").is_err());
    assert!(!root.path().join("candidate.tmp").exists());
    assert!(ledger.is_dir());
}

#[cfg(unix)]
#[test]
fn ledger_replace_directory_error_has_both_filenames() {
    let root = tempfile::tempdir().unwrap();
    let ledger = root.path().join("tdd.json");
    fs::create_dir(&ledger).unwrap();
    names(&["candidate.tmp"]);
    // A real renameat failure beyond the permission-denied regression.
    assert_eq!(
        write_ledger(&ledger, "updated").unwrap_err(),
        format!(
            "IsADirectoryError: [Errno {}] Is a directory: {} -> {}",
            libc::EISDIR,
            repr(&root.path().join("candidate.tmp").to_string_lossy()),
            repr(&ledger.to_string_lossy())
        )
    );
    assert!(ledger.is_dir());
    assert!(!root.path().join("candidate.tmp").exists());
}

fn directory_alias(link: &Path, target: &Path) {
    #[cfg(unix)]
    std::os::unix::fs::symlink(target, link).unwrap();
    #[cfg(windows)]
    {
        // canonicalize() supplies extended drive paths; cmd's mklink needs plain paths.
        use std::os::windows::ffi::{OsStrExt, OsStringExt};
        let plain = |p: &Path| {
            let units: Vec<_> = p.as_os_str().encode_wide().collect();
            assert!(units.starts_with(&[92, 92, 63, 92]));
            OsString::from_wide(&units[4..])
        };
        let result = Command::new("cmd.exe")
            .args(["/D", "/C", "mklink", "/J"])
            .arg(plain(link))
            .arg(plain(target))
            .output()
            .unwrap();
        assert!(result.status.success(), "junction precondition: {result:?}");
    }
}

fn ledger_alias_swap(fail_replace: bool) {
    let t = tempfile::tempdir().unwrap();
    let root = t.path().canonicalize().unwrap();
    let inside = root.join("inside");
    let outside = root.join("outside");
    let alias = root.join("alias");
    fs::create_dir(&inside).unwrap();
    fs::create_dir(&outside).unwrap();
    if fail_replace {
        fs::create_dir(inside.join("tdd.json")).unwrap();
        fs::create_dir(outside.join("tdd.json")).unwrap();
    } else {
        fs::write(inside.join("tdd.json"), "original").unwrap();
        fs::write(outside.join("tdd.json"), "outside-ledger").unwrap();
    }
    fs::write(outside.join("candidate.tmp"), "outside-temp").unwrap();
    directory_alias(&alias, &inside);
    names(&["candidate.tmp"]);
    let swapped_alias = alias.clone();
    let swapped_target = outside.clone();
    BEFORE_LEDGER_REPLACE.with(|hook| {
        *hook.borrow_mut() = Some(Box::new(move || {
            // Swap only the alias, not the pinned real directory: Windows subtree
            // handle rename restrictions must not mask pathname redirection.
            #[cfg(unix)]
            fs::remove_file(&swapped_alias).unwrap();
            #[cfg(windows)]
            fs::remove_dir(&swapped_alias).unwrap();
            directory_alias(&swapped_alias, &swapped_target);
        }));
    });
    let result = write_ledger(&alias.join("tdd.json"), "updated");
    assert_eq!(result.is_err(), fail_replace, "{result:?}");
    assert_eq!(
        fs::read(outside.join("candidate.tmp")).unwrap(),
        b"outside-temp"
    );
    if fail_replace {
        assert!(inside.join("tdd.json").is_dir());
        assert!(outside.join("tdd.json").is_dir());
    } else {
        assert_eq!(fs::read(inside.join("tdd.json")).unwrap(), b"updated");
        assert_eq!(
            fs::read(outside.join("tdd.json")).unwrap(),
            b"outside-ledger"
        );
    }
    assert!(!inside.join("candidate.tmp").exists());
    assert_eq!(fs::read_dir(&outside).unwrap().count(), 2);
    #[cfg(unix)]
    fs::remove_file(alias).unwrap();
    #[cfg(windows)]
    fs::remove_dir(alias).unwrap();
}

#[test]
fn ledger_parent_alias_swap_keeps_rename_inside() {
    ledger_alias_swap(false);
}

#[test]
fn ledger_parent_alias_swap_keeps_failure_cleanup_inside() {
    ledger_alias_swap(true);
}
