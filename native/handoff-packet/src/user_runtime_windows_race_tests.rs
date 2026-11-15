//! Shared native containment assertions; no Python parity is claimed for races.
use crate::adoption_fs::*;
use crate::user_runtime_mutation::{PendingWrite, remove_with};
use std::{
    cell::{Cell, RefCell},
    fs,
    path::PathBuf,
};
use std::{ffi::OsStr, io, path::Path};

#[cfg(unix)]
fn attributes(m: &fs::Metadata) -> u32 {
    use std::os::unix::fs::PermissionsExt;
    m.permissions().mode()
}
#[cfg(windows)]
fn attributes(m: &fs::Metadata) -> u32 {
    use std::os::windows::fs::MetadataExt;
    m.file_attributes()
}
#[cfg(unix)]
fn file_link(target: &Path, link: &Path) -> io::Result<()> {
    std::os::unix::fs::symlink(target, link)
}
#[cfg(windows)]
fn file_link(target: &Path, link: &Path) -> io::Result<()> {
    std::os::windows::fs::symlink_file(target, link)
}
#[cfg(unix)]
fn directory_link(target: &Path, link: &Path) -> io::Result<()> {
    file_link(target, link)
}
#[cfg(windows)]
fn plain_path(p: &Path) -> std::ffi::OsString {
    use std::{
        ffi::OsString,
        os::windows::ffi::{OsStrExt, OsStringExt},
    };
    let w: Vec<_> = p.as_os_str().encode_wide().collect();
    if w.starts_with(&[92, 92, 63, 92, 85, 78, 67, 92]) {
        let mut unc = vec![92, 92];
        unc.extend_from_slice(&w[8..]);
        OsString::from_wide(&unc)
    } else {
        OsString::from_wide(&w[4..])
    }
}
#[cfg(windows)]
fn directory_link(target: &Path, link: &Path) -> io::Result<()> {
    let output = std::process::Command::new("cmd.exe")
        .args(["/D", "/C", "mklink", "/J"])
        .arg(plain_path(link))
        .arg(plain_path(target))
        .output()?;
    assert!(
        output.status.success(),
        "junction capability precondition: {output:?}"
    );
    Ok(())
}
fn remove_directory_link(path: &Path) {
    #[cfg(windows)]
    fs::remove_dir(path).unwrap();
    #[cfg(unix)]
    fs::remove_file(path).unwrap();
}
fn rename_directory(path: &Path, dest: &Path, refused: &Cell<bool>) -> io::Result<()> {
    let result = fs::rename(path, dest);
    // S1-S3 PC observation: an open subtree can prevent directory rename.
    // This branch proves OS refusal plus unchanged identity; it never skips a test.
    #[cfg(windows)]
    if let Err(e) = &result {
        assert!(
            matches!(e.raw_os_error(), Some(5 | 32)),
            "rename {path:?}: {e:?}"
        );
        refused.set(true);
    }
    #[cfg(unix)]
    let _ = refused;
    result
}
fn swap_directory(path: &Path, outside: &Path, refused: &Cell<bool>) -> io::Result<()> {
    rename_directory(path, &path.with_extension("saved"), refused)?;
    directory_link(outside, path)
}
#[rustfmt::skip]
pub(crate) fn snapshot(path: &Path) -> Vec<(PathBuf, u32, Vec<u8>)> {
    fn visit(root: &Path, path: &Path, rows: &mut Vec<(PathBuf, u32, Vec<u8>)>) {
        let metadata = fs::symlink_metadata(path).unwrap();
        let bytes = if reparse(&metadata) {
            fs::read_link(path).unwrap().as_os_str().as_encoded_bytes().to_vec()
        } else if metadata.is_file() { fs::read(path).unwrap() } else { vec![] };
        rows.push((path.strip_prefix(root).unwrap().to_owned(), attributes(&metadata), bytes));
        if metadata.is_dir() && !reparse(&metadata) {
            let mut entries: Vec<_> = fs::read_dir(path).unwrap().map(|p| p.unwrap().path()).collect();
            entries.sort();
            for entry in entries { visit(root, &entry, rows); }
        }
    }
    let mut rows = vec![];
    visit(path, path, &mut rows);
    rows
}

#[test]
#[rustfmt::skip]
fn create_replace_restore_unlink_cleanup_swap_matrix() {
    for operation in ["create", "replace", "restore", "unlink", "cleanup"] {
        for site in ["root", "leaf", "ancestor", "temporary", "moved-outside", "replaced-parent"] {
            let temp = tempfile::tempdir().unwrap();
            let base = temp.path().canonicalize().unwrap();
            let root = base.join("root"); let dir = root.join("agents");
            let target = dir.join("agent.md"); let outside = base.join("outside");
            fs::create_dir_all(&dir).unwrap(); fs::create_dir(&outside).unwrap();
            for name in ["agent.md", "temporary", "keep"] {
                fs::write(outside.join(name), b"OUTSIDE").unwrap();
                #[cfg(unix)] {
                    use std::os::unix::fs::PermissionsExt;
                    fs::set_permissions(outside.join(name), fs::Permissions::from_mode(0o640)).unwrap();
                }
            }
            file_link(Path::new("keep"), &outside.join("link")).unwrap();
            if operation != "create" { fs::write(&target, b"before").unwrap(); }
            let reached = Cell::new(false); let refused = Cell::new(false);
            let original_parent = directory_identity(&dir).unwrap();
            let expected = RefCell::new(snapshot(&outside));
            let changed = || -> io::Result<()> {
                reached.set(true);
                match site {
                    "root" | "ancestor" => swap_directory(if site == "root" { &root } else { &dir }, &outside, &refused),
                    "moved-outside" | "replaced-parent" => {
                        rename_directory(&dir, &outside.join("moved"), &refused)?;
                        if site == "replaced-parent" { fs::create_dir(&dir)?; }
                        else { directory_link(&outside.join("moved"), &dir)?; }
                        *expected.borrow_mut() = snapshot(&outside);
                        Ok(())
                    }
                    "leaf" => {
                        if target.exists() { fs::rename(&target, dir.join("leaf.saved"))?; }
                        file_link(&outside.join("agent.md"), &target)
                    }
                    "temporary" => {
                        let temporary = dir.join("temporary");
                        if temporary.exists() { fs::rename(&temporary, dir.join("temp.saved"))?; }
                        file_link(&outside.join("temporary"), &temporary)
                    }
                    _ => unreachable!(),
                }
            };
            let result = if operation == "unlink" { remove_with(&root, &target, false, changed) }
            else {
                let pending = PendingWrite::prepare(&root, &target, OsStr::new("temporary"), b"after").unwrap();
                if operation == "cleanup" { pending.cleanup_with(|_| changed()) }
                else { pending.publish_with(|_| changed()) }
                // pending drops here: compare outside only after implicit cleanup too.
            };
            assert!(reached.get(), "callback {operation}/{site}: {result:?}");
            if refused.get() { assert_eq!(directory_identity(&dir).unwrap(), original_parent, "{operation}/{site}: {result:?}"); }
            assert_eq!(snapshot(&outside), *expected.borrow(), "{operation}/{site}: {result:?}");
            if matches!(site, "root" | "ancestor" | "moved-outside" | "replaced-parent") {
                assert!(result.is_err(), "{operation}/{site}: {result:?}");
            } else if operation != "unlink" && site == "temporary" {
                assert!(result.is_err(), "{operation}/{site}: {result:?}");
                assert!(dir.join("temporary").is_symlink());
            } else if matches!(operation, "create" | "replace" | "restore") {
                result.unwrap(); assert_eq!(fs::read(&target).unwrap(), b"after");
            } else if operation == "unlink" {
                result.unwrap(); assert!(!target.exists());
            } else { result.unwrap(); assert!(!dir.join("temporary").exists()); }
            if !refused.get() {
                let link = match site { "root" => Some(&root), "ancestor" | "moved-outside" => Some(&dir), _ => None };
                if let Some(link) = link { remove_directory_link(link); }
            }
        }
    }
}

#[test]
#[rustfmt::skip]
fn creation_visibility_and_pinned_policy_share_the_same_swap() {
    for visible in [true, false] {
        let t = tempfile::tempdir().unwrap(); let base = t.path().canonicalize().unwrap();
        let root = base.join("root"); let dir = root.join("agents"); let outside = base.join("outside");
        fs::create_dir_all(&dir).unwrap(); fs::create_dir(&outside).unwrap();
        fs::write(outside.join("keep"), b"outside").unwrap();
        let reached = Cell::new(false); let refused = Cell::new(false);
        let mut expected = snapshot(&outside);
        let result = StagedFile::create_with_parent_check(&root, &dir.join("temp"), visible, |_| {
            reached.set(true); rename_directory(&dir, &outside.join("moved"), &refused)?;
            fs::create_dir(&dir)?; expected = snapshot(&outside); Ok(())
        });
        let error = result.as_ref().err();
        assert!(reached.get(), "visible={visible}: {error:?}");
        if visible || refused.get() { assert!(result.is_err(), "visible={visible}: {error:?}"); }
        else {
            let stage = result.as_ref().unwrap();
            assert!(outside.join("moved/temp").is_file(), "{error:?}");
            assert!(!dir.join("temp").exists(), "{error:?}");
            stage.remove().unwrap();
        }
        drop(result); assert_eq!(snapshot(&outside), expected, "visible={visible}");
        assert_eq!(fs::read_dir(&dir).unwrap().count(), 0);
    }
}

#[test]
#[rustfmt::skip]
fn file_to_directory_and_directory_to_junction_cleanup_swaps_refuse() {
    for directory in [false, true] {
        let t = tempfile::tempdir().unwrap(); let root = t.path().canonicalize().unwrap();
        let target = root.join("entry"); let outside = root.join("outside");
        fs::create_dir(&outside).unwrap(); fs::write(outside.join("keep"), b"outside").unwrap();
        if directory { fs::create_dir(&target).unwrap(); } else { fs::write(&target,b"old").unwrap(); }
        let expected = snapshot(&outside); let reached = Cell::new(false);
        let result = remove_with(&root, &target, directory, || {
            reached.set(true); fs::rename(&target, root.join("saved"))?;
            if directory { directory_link(&outside,&target) } else { fs::create_dir(&target) }
        });
        assert!(reached.get() && result.is_err(), "directory={directory}: {result:?}");
        assert!(target.is_dir(), "directory={directory}: {result:?}");
        assert_eq!(snapshot(&outside), expected, "directory={directory}: {result:?}");
        if directory { remove_directory_link(&target); }
    }
}

#[cfg(windows)]
#[test]
#[rustfmt::skip]
fn case_short_and_hardlink_aliases_preserve_target_and_home_identity() {
    use crate::user_runtime_install::{capture_home_identity, runtime_homes_overlap};
    let t = tempfile::tempdir().unwrap(); let base = t.path().canonicalize().unwrap();
    let root = base.join("Long-runtime-home-name"); fs::create_dir_all(root.join("Nested")).unwrap();
    let target = root.join("Long-payload-name.md"); fs::write(&target,b"original").unwrap();
    fs::hard_link(&target,root.join("hardlink")).unwrap();
    let short = short_path(&target);
    assert!(short.file_name().unwrap().to_string_lossy().contains('~'), "8.3 capability precondition: {short:?}");
    let expected = snapshot(&root);
    for alias in [OsStr::new("LONG-PAYLOAD-NAME.MD"), OsStr::new("hardlink"), short.file_name().unwrap()] {
        let error = PendingWrite::prepare(&root,&target,alias,b"new").err();
        assert!(error.as_ref().is_some_and(|e| e.kind()==io::ErrorKind::InvalidInput), "{alias:?}: {error:?}");
        assert_eq!(snapshot(&root),expected, "{alias:?}: {error:?}");
    }
    let id = capture_home_identity(&root).unwrap();
    for alias in [base.join("lONG-RUNTIME-HOME-NAME"), short_path(&root), root.join("nESTED")] {
        let other = capture_home_identity(&alias).unwrap();
        assert!(runtime_homes_overlap(&id,&other) && runtime_homes_overlap(&other,&id), "{alias:?}");
    }
}

#[cfg(windows)]
#[test]
#[rustfmt::skip]
fn delete_sharing_and_byte_locks_reach_real_os_operations() {
    use std::{io::Read, os::windows::{fs::OpenOptionsExt, io::AsRawHandle}};
    use windows_sys::Win32::Storage::FileSystem::{FILE_SHARE_DELETE, FILE_SHARE_READ, FILE_SHARE_WRITE, LockFile, UnlockFile};
    let t = tempfile::tempdir().unwrap(); let root = t.path().canonicalize().unwrap();
    let target = root.join("target");
    for allow_delete in [false,true] {
        fs::write(&target,b"old").unwrap();
        let lock = fs::OpenOptions::new().read(true).share_mode(FILE_SHARE_READ | FILE_SHARE_WRITE | if allow_delete { FILE_SHARE_DELETE } else { 0 }).open(&target).unwrap();
        let pending = PendingWrite::prepare(&root,&target,OsStr::new("temp"),b"new").unwrap();
        let result = pending.publish_with(|_| Ok(()));
        if allow_delete { assert!(result.is_ok(), "{result:?}"); }
        else { assert!(result.as_ref().is_err_and(|e| matches!(e.raw_os_error(),Some(5|32))), "{result:?}"); }
        drop(pending); assert!(!root.join("temp").exists(), "{result:?}");
        assert_eq!(fs::read(&target).unwrap(), if allow_delete { b"new" } else { b"old" }, "{result:?}");
        let result = remove_with(&root,&target,false,|| Ok(()));
        assert_eq!(result.is_ok(), allow_delete, "{result:?}"); drop(lock);
        if !allow_delete { remove_with(&root,&target,false,|| Ok(())).unwrap(); }
    }
    fs::write(&target,b"bytes").unwrap();
    let lock = fs::OpenOptions::new().read(true).write(true).open(&target).unwrap();
    let mut reader = parent(&root,&target).unwrap().open_file().unwrap();
    // windows-sys 0.61.2 FileSystem/mod.rs:257,435: HANDLE + four u32 -> BOOL.
    // SAFETY: both handles remain owned and open throughout lock/read/unlock.
    assert_ne!(unsafe { LockFile(lock.as_raw_handle(),0,0,1,0) },0, "{:?}",io::Error::last_os_error());
    let result = reader.read_exact(&mut [0]);
    assert_ne!(unsafe { UnlockFile(lock.as_raw_handle(),0,0,1,0) },0, "{:?}",io::Error::last_os_error());
    assert!(result.as_ref().is_err_and(|e| e.raw_os_error()==Some(33)), "{result:?}");
    reader.read_exact(&mut [0]).unwrap(); drop((reader,lock));
    assert_eq!(fs::read(&target).unwrap(),b"bytes");
}

#[cfg(windows)]
#[test]
#[rustfmt::skip]
fn long_paths_preserve_drive_verbatim_or_unc_anchor() {
    let t = tempfile::tempdir().unwrap(); let root = t.path().canonicalize().unwrap();
    for root in [root.clone(), PathBuf::from(plain_path(&root))] {
    let relative = ["directory-with-a-long-name";12].join("/");
    let target = root.join(relative).join("payload.md");
    assert!(target.as_os_str().len()>260, "{target:?}");
    let pending = PendingWrite::prepare(&root,&target,OsStr::new("temp"),b"long").unwrap();
    let result = pending.publish_with(|_| Ok(())); assert!(result.is_ok(), "{result:?}");
    drop(pending); assert_eq!(fs::read(&target).unwrap(),b"long");
    remove_with(&root,&target,false,|| Ok(())).unwrap();
    }
}
