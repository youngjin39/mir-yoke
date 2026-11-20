use super::{windows_parent_tests::junction, *};
use std::{
    fs,
    io::{Read, Write},
    os::windows::fs::{MetadataExt, OpenOptionsExt},
};

#[test]
// SAFETY: only scratch files, live owned handles and sized NT records are used.
#[allow(unsafe_code)]
fn deny_delete_replace_syscall_probe() {
    use std::{mem::size_of, os::windows::ffi::OsStrExt, os::windows::io::AsRawHandle};
    use windows_sys::{
        Wdk::Storage::FileSystem::{
            FILE_RENAME_INFORMATION, FILE_RENAME_REPLACE_IF_EXISTS, FileRenameInformation,
            FileRenameInformationEx, NtSetInformationFile,
        },
        Win32::{
            Foundation::RtlNtStatusToDosError,
            Storage::FileSystem::{
                FILE_SHARE_DELETE, FILE_SHARE_READ, FILE_SHARE_WRITE, MOVEFILE_REPLACE_EXISTING,
                MoveFileExW,
            },
            System::IO::IO_STATUS_BLOCK,
        },
    };
    let temp = tempfile::tempdir().unwrap();
    let root = temp.path().canonicalize().unwrap();
    let mut outcomes = Vec::new();
    for allow_delete in [false, true] {
        for route in [
            "movefile-closed",
            "movefile-live",
            "native",
            "nt-ex",
            "nt-legacy",
        ] {
            let case = root.join(format!("{allow_delete}-{route}"));
            fs::create_dir(&case).unwrap();
            let source = case.join("stage");
            let target = case.join("target");
            fs::write(&target, b"old").unwrap();
            // Same GENERIC_READ and READ|WRITE sharing as capture_windows.py:377.
            let lock = fs::OpenOptions::new()
                .read(true)
                .share_mode(
                    FILE_SHARE_READ
                        | FILE_SHARE_WRITE
                        | if allow_delete { FILE_SHARE_DELETE } else { 0 },
                )
                .open(&target)
                .unwrap();
            let mut stage = StagedFile::create(&case, &source).unwrap();
            stage.file.write_all(b"new").unwrap();
            let destination = parent(&case, &target).unwrap();
            assert_eq!(
                stage.source.identity().unwrap(),
                Some(stage.identity().unwrap())
            );
            let result = if route.starts_with("movefile") {
                // Reference closes its temporary before os.replace. Probe both
                // lifetimes to isolate that from NT-vs-Win32 replacement behavior.
                if route == "movefile-closed" {
                    stage.keep();
                    drop(stage);
                }
                let src: Vec<u16> = source.as_os_str().encode_wide().chain(Some(0)).collect();
                let dst: Vec<u16> = target.as_os_str().encode_wide().chain(Some(0)).collect();
                // SAFETY: both NUL-terminated names refer only to this scratch case.
                if unsafe { MoveFileExW(src.as_ptr(), dst.as_ptr(), MOVEFILE_REPLACE_EXISTING) }
                    == 0
                {
                    Err(io::Error::last_os_error())
                } else {
                    Ok(())
                }
            } else if route == "native" {
                // Exact production call after all staging/parent/identity opens
                // succeeded. A failure here is NtSetInformationFile, not an open.
                windows::rename_file(&stage.file, &destination)
            } else {
                // Diagnostic alternatives, never runtime fallbacks. Installed
                // windows-sys 0.61.2 Wdk/Storage/FileSystem/mod.rs:688,2496,3216-18.
                let units: Vec<u16> = destination.name.encode_wide().collect();
                let start = std::mem::offset_of!(FILE_RENAME_INFORMATION, FileName);
                let bytes = size_of::<FILE_RENAME_INFORMATION>().max(start + units.len() * 2);
                let mut buffer = vec![0usize; bytes.div_ceil(size_of::<usize>())];
                let info = buffer.as_mut_ptr().cast::<FILE_RENAME_INFORMATION>();
                let mut iosb = IO_STATUS_BLOCK::default();
                // SAFETY: aligned allocation fits the header/tail, all handles
                // remain live; one validated basename uses the pinned directory.
                let status = unsafe {
                    if route == "nt-legacy" {
                        (*info).Anonymous.ReplaceIfExists = true;
                    } else {
                        (*info).Anonymous.Flags = FILE_RENAME_REPLACE_IF_EXISTS;
                    }
                    (*info).RootDirectory = destination.directory.as_raw_handle();
                    (*info).FileNameLength = (units.len() * 2) as u32;
                    std::ptr::copy_nonoverlapping(
                        units.as_ptr(),
                        buffer.as_mut_ptr().cast::<u8>().add(start).cast::<u16>(),
                        units.len(),
                    );
                    NtSetInformationFile(
                        stage.file.as_raw_handle(),
                        &mut iosb,
                        info.cast(),
                        bytes as u32,
                        if route == "nt-legacy" {
                            FileRenameInformation
                        } else {
                            FileRenameInformationEx
                        },
                    )
                };
                println!("allow_delete={allow_delete} route={route} NTSTATUS={status:#x}");
                if status < 0 {
                    // SAFETY: pure conversion of the immediately captured status.
                    Err(io::Error::from_raw_os_error(
                        unsafe { RtlNtStatusToDosError(status) } as i32,
                    ))
                } else {
                    Ok(())
                }
            };
            let code = result.as_ref().err().and_then(io::Error::raw_os_error);
            assert!(result.is_ok() || code.is_some(), "{result:?}");
            outcomes.push((allow_delete, route, code));
            println!(
                "allow_delete={allow_delete} route={route} winerror={code:?} result={result:?}"
            );
            assert_eq!(
                fs::read(&target).unwrap(),
                if result.is_ok() { b"new" } else { b"old" }
            );
            assert_eq!(source.exists(), result.is_err());
            if source.exists() {
                assert_eq!(fs::read(&source).unwrap(), b"new");
            }
            drop(lock);
        }
    }
    // Collect every diagnostic before rejecting an unexpected result.
    for route in ["movefile-closed", "movefile-live", "native"] {
        assert!(outcomes.contains(&(false, route, Some(if route == "native" { 32 } else { 5 }))));
    }
    assert!(outcomes.contains(&(true, "native", None)));
    for route in ["nt-ex", "nt-legacy"] {
        // Do not accept the deviation if a simple handle-relative alternative
        // matches reference code 5 AND preserves replacement of a shared-open
        // target. Main must then evaluate that candidate as a production fix.
        assert!(
            !(outcomes.contains(&(false, route, Some(5)))
                && outcomes.contains(&(true, route, None))),
            "{route} may preserve both contracts; evaluate it before accepting the deviation"
        );
    }
}

#[test]
fn dispose_reopen_sharing_denial_preserves_original_handle_and_file() {
    use std::io::{Seek, SeekFrom};
    use windows_sys::Win32::{
        Foundation::ERROR_SHARING_VIOLATION,
        Storage::FileSystem::{FILE_SHARE_READ, FILE_SHARE_WRITE},
    };

    let t = tempfile::tempdir().unwrap();
    let r = t.path().canonicalize().unwrap();
    let path = r.join("blocked-delete");
    fs::write(&path, b"original").unwrap();
    // ReOpenFile's desired access must be compatible with every existing
    // handle's sharing mode. This live handle omits FILE_SHARE_DELETE, so the
    // DELETE reopen fails in the OS before any disposition can be requested.
    // https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-reopenfile
    let mut original = fs::OpenOptions::new()
        .read(true)
        .write(true)
        .share_mode(FILE_SHARE_READ | FILE_SHARE_WRITE)
        .open(&path)
        .unwrap();
    let id = file_identity(&original).unwrap();
    let error = windows::dispose_file(&original).unwrap_err();
    assert_eq!(error.raw_os_error(), Some(ERROR_SHARING_VIOLATION as i32));
    assert_eq!(file_identity(&original).unwrap(), id);
    assert_eq!(parent(&r, &path).unwrap().identity().unwrap(), Some(id));
    assert_eq!(fs::read(&path).unwrap(), b"original");
    // The failure must neither close nor poison the caller's borrowed handle.
    let mut bytes = Vec::new();
    original.read_to_end(&mut bytes).unwrap();
    assert_eq!(bytes, b"original");
    original.seek(SeekFrom::Start(0)).unwrap();
    original.write_all(b"retained").unwrap();
    assert_eq!(fs::read(&path).unwrap(), b"retained");
    drop(original);
    assert_eq!(fs::read(&path).unwrap(), b"retained");
    fs::remove_file(&path).unwrap();
    assert!(!path.exists());
}

#[test]
fn rename_counted_utf16_tails_preserve_identity_for_moves_and_stages() {
    use std::os::windows::ffi::OsStringExt;
    let t = tempfile::tempdir().unwrap();
    let r = t.path().canonicalize().unwrap();
    fs::create_dir(r.join("to")).unwrap();
    // Exercise lengths below/at/above the struct's trailing alignment padding,
    // including non-scalar UTF-16: the NT length counts bytes, without a NUL.
    for units in [
        vec![b'x' as u16],
        vec![b'x' as u16, b'y' as u16],
        "\u{d55c}\u{ae00}-🦀".encode_utf16().collect(),
        vec![b'x' as u16, 0xd800, b'y' as u16],
    ] {
        let dest = r.join("to").join(OsString::from_wide(&units));
        for staged in [false, true] {
            fs::write(&dest, b"old").unwrap();
            let mut old = File::open(&dest).unwrap();
            let id = if staged {
                let mut s = StagedFile::create(&r, &r.join("source")).unwrap();
                s.file.write_all(b"new").unwrap();
                let id = s.identity().unwrap();
                s.publish(&r, &dest).unwrap();
                id
            } else {
                fs::write(r.join("source"), b"new").unwrap();
                let id = parent(&r, &r.join("source"))
                    .unwrap()
                    .identity()
                    .unwrap()
                    .unwrap();
                Move::prepare(&r, &r.join("source"), &dest)
                    .unwrap()
                    .rename()
                    .unwrap();
                id
            };
            assert_eq!(parent(&r, &dest).unwrap().identity().unwrap(), Some(id));
            assert_eq!(fs::read(&dest).unwrap(), b"new");
            assert!(!r.join("source").exists());
            let mut bytes = Vec::new();
            old.read_to_end(&mut bytes).unwrap();
            assert_eq!(bytes, b"old");
        }
    }
}

#[test]
fn generic_rename_replaces_and_moves_the_current_reparse_entry() {
    let t = tempfile::tempdir().unwrap();
    let r = t.path().canonicalize().unwrap();
    fs::create_dir(r.join("to")).unwrap();
    fs::write(r.join("source"), b"new").unwrap();
    fs::write(r.join("to/dest"), b"old").unwrap();
    let mut old = File::open(r.join("to/dest")).unwrap();
    let movement = Move::prepare(&r, &r.join("source"), &r.join("to/dest")).unwrap();
    movement.rename().unwrap();
    assert_eq!(fs::read(r.join("to/dest")).unwrap(), b"new");
    let mut bytes = Vec::new();
    old.read_to_end(&mut bytes).unwrap();
    assert_eq!(bytes, b"old");
    assert!(!r.join("source").exists());
    fs::write(r.join("source"), b"blocked").unwrap();
    let locked = fs::OpenOptions::new()
        .read(true)
        .share_mode(windows_sys::Win32::Storage::FileSystem::FILE_SHARE_READ)
        .open(r.join("to/dest"))
        .unwrap();
    assert!(
        Move::prepare(&r, &r.join("source"), &r.join("to/dest"))
            .unwrap()
            .rename()
            .is_err()
    );
    assert_eq!(fs::read(r.join("source")).unwrap(), b"blocked");
    assert_eq!(fs::read(r.join("to/dest")).unwrap(), b"new");
    drop(locked);
    let movement = Move::prepare(&r, &r.join("to/dest"), &r.join("link")).unwrap();
    fs::rename(r.join("to/dest"), r.join("saved")).unwrap();
    fs::create_dir(r.join("outside")).unwrap();
    fs::write(r.join("outside/sentinel"), b"outside").unwrap();
    junction(&r.join("to/dest"), &r.join("outside"));
    movement.rename().unwrap();
    assert_ne!(
        fs::symlink_metadata(r.join("link"))
            .unwrap()
            .file_attributes()
            & windows_sys::Win32::Storage::FileSystem::FILE_ATTRIBUTE_REPARSE_POINT,
        0
    );
    fs::remove_dir(r.join("link")).unwrap();
    assert_eq!(fs::read(r.join("saved")).unwrap(), b"new");
    assert_eq!(fs::read(r.join("outside/sentinel")).unwrap(), b"outside");
    assert_eq!(fs::read_dir(r.join("outside")).unwrap().count(), 1);
    let movement = Move::prepare(&r, &r.join("saved"), &r.join("outside")).unwrap();
    assert!(movement.rename().is_err());
    assert_eq!(fs::read(r.join("saved")).unwrap(), b"new");
    fs::remove_file(r.join("saved")).unwrap();
    assert_eq!(
        movement.rename().unwrap_err().kind(),
        io::ErrorKind::NotFound
    );
}

#[test]
fn disposition_enforces_type_nonempty_missing_and_reparse_rules() {
    let t = tempfile::tempdir().unwrap();
    let r = t.path().canonicalize().unwrap();
    let p = parent(&r, &r.join("entry")).unwrap();
    fs::write(r.join("entry"), b"file").unwrap();
    let held = File::open(r.join("entry")).unwrap();
    p.unlink(&p.name, false).unwrap();
    assert!(!r.join("entry").exists());
    drop(held);
    fs::write(r.join("entry"), b"readonly").unwrap();
    let original = fs::metadata(r.join("entry")).unwrap().permissions();
    let mut readonly = original.clone();
    readonly.set_readonly(true);
    fs::set_permissions(r.join("entry"), readonly).unwrap();
    assert!(p.unlink(&p.name, false).is_err());
    assert_eq!(fs::read(r.join("entry")).unwrap(), b"readonly");
    fs::set_permissions(r.join("entry"), original).unwrap();
    p.unlink(&p.name, false).unwrap();
    assert_eq!(
        p.unlink(&p.name, false).unwrap_err().kind(),
        io::ErrorKind::NotFound
    );
    fs::create_dir(r.join("entry")).unwrap();
    assert!(p.unlink(&p.name, false).is_err()); // file -> empty real directory swap
    fs::write(r.join("entry/sentinel"), b"outside").unwrap();
    assert!(p.unlink(&p.name, true).is_err());
    assert_eq!(fs::read(r.join("entry/sentinel")).unwrap(), b"outside");
    fs::remove_file(r.join("entry/sentinel")).unwrap();
    p.unlink(&p.name, true).unwrap();
    fs::write(r.join("entry"), b"file").unwrap();
    assert!(p.unlink(&p.name, true).is_err());
    p.unlink(&p.name, false).unwrap();
    fs::create_dir(r.join("outside")).unwrap();
    fs::write(r.join("outside/sentinel"), b"outside").unwrap();
    junction(&r.join("entry"), &r.join("outside"));
    assert!(p.unlink(&p.name, true).is_err()); // directory cleanup refuses junctions
    p.unlink(&p.name, false).unwrap(); // file unlink removes the entry, never its target
    assert!(!r.join("entry").exists());
    assert_eq!(fs::read(r.join("outside/sentinel")).unwrap(), b"outside");
    assert_eq!(fs::read_dir(r.join("outside")).unwrap().count(), 1);
}

#[test]
fn staged_publish_collision_keep_and_drop_follow_ownership() {
    let t = tempfile::tempdir().unwrap();
    let r = t.path().canonicalize().unwrap();
    fs::write(r.join("dest"), b"old").unwrap();
    let mut s = StagedFile::create(&r, &r.join("temp")).unwrap();
    s.file.write_all(b"verified").unwrap();
    assert_eq!(s.contents(8).unwrap(), b"verified");
    s.publish(&r, &r.join("dest")).unwrap();
    fs::write(&s.path, b"foreign").unwrap();
    drop(s);
    assert_eq!(fs::read(r.join("dest")).unwrap(), b"verified");
    assert_eq!(fs::read(r.join("temp")).unwrap(), b"foreign");
    assert!(StagedFile::create(&r, &r.join("temp")).is_err());
    assert_eq!(fs::read(r.join("temp")).unwrap(), b"foreign");
    let s = StagedFile::create(&r, &r.join("drop")).unwrap();
    fs::create_dir(r.join("drop.stage")).unwrap();
    drop(s);
    assert!(!r.join("drop").exists());
    assert!(r.join("drop.stage").is_dir());
    let s = StagedFile::create(&r, &r.join("keep")).unwrap();
    s.keep();
    drop(s);
    assert!(r.join("keep").is_file());
    let s = StagedFile::create(&r, &r.join("failed")).unwrap();
    assert!(s.publish(&r, &r.join("drop.stage")).is_err());
    assert!(r.join("failed").is_file());
    drop(s);
    assert!(!r.join("failed").exists());
    let s = StagedFile::create(&r, &r.join("missing")).unwrap();
    fs::remove_file(&s.path).unwrap();
    s.remove().unwrap();
    drop(s);
}

#[test]
fn removed_temporary_name_can_be_reused_before_drop() {
    let t = tempfile::tempdir().unwrap();
    let r = t.path().canonicalize().unwrap();
    let mut s = StagedFile::create(&r, &r.join("temp")).unwrap();
    s.file.write_all(b"verified").unwrap();
    s.remove().unwrap();
    assert!(!s.path.exists());
    let mut replacement = StagedFile::create(&r, &s.path).unwrap();
    replacement.file.write_all(b"foreign").unwrap();
    assert_eq!(s.contents(8).unwrap(), b"verified");
    s.remove().unwrap();
    drop(s);
    assert_eq!(fs::read(&replacement.path).unwrap(), b"foreign");
    replacement.remove().unwrap();
    assert!(!replacement.path.exists());
}

#[test]
fn staged_cleanup_does_not_resolve_leaf_after_validation() {
    let t = tempfile::tempdir().unwrap();
    let base = t.path().canonicalize().unwrap();
    let r = base.join("root");
    let outside = base.join("outside");
    fs::create_dir(&r).unwrap();
    let s = StagedFile::create(&r, &r.join("temp")).unwrap();
    let expected = s.identity().unwrap();
    assert_eq!(s.source.identity().unwrap(), Some(expected));
    // Change the leaf after remove's ownership check but before its mutation.
    fs::rename(&s.path, r.join("saved")).unwrap();
    fs::create_dir(&outside).unwrap();
    fs::write(outside.join("sentinel"), b"outside").unwrap();
    junction(&s.path, &outside);
    windows::dispose_file(&s.file).unwrap();
    assert!(!r.join("saved").exists());
    assert_eq!(fs::read(outside.join("sentinel")).unwrap(), b"outside");
    assert_eq!(fs::read_dir(&outside).unwrap().count(), 1);
    assert_ne!(
        fs::symlink_metadata(&s.path).unwrap().file_attributes()
            & windows_sys::Win32::Storage::FileSystem::FILE_ATTRIBUTE_REPARSE_POINT,
        0
    );
    drop(s);
    fs::remove_dir(r.join("temp")).unwrap();
}

#[test]
fn staged_swapped_leaf_survives_publish_remove_and_drop() {
    let t = tempfile::tempdir().unwrap();
    let r = t.path().canonicalize().unwrap();
    for reparse in [false, true] {
        let mut s = StagedFile::create(&r, &r.join("temp")).unwrap();
        s.file.write_all(b"verified").unwrap();
        fs::rename(&s.path, r.join("saved")).unwrap();
        if reparse {
            fs::create_dir(r.join("outside")).unwrap();
            fs::write(r.join("outside/sentinel"), b"outside").unwrap();
            junction(&s.path, &r.join("outside"));
        } else {
            fs::write(&s.path, b"foreign").unwrap();
        }
        assert!(s.publish(&r, &r.join("dest")).is_err());
        assert!(s.remove().is_err());
        assert_eq!(s.contents(8).unwrap(), b"verified");
        drop(s);
        assert!(!r.join("dest").exists());
        assert_eq!(fs::read(r.join("saved")).unwrap(), b"verified");
        fs::remove_file(r.join("saved")).unwrap();
        if reparse {
            assert_eq!(fs::read(r.join("outside/sentinel")).unwrap(), b"outside");
            assert_eq!(fs::read_dir(r.join("outside")).unwrap().count(), 1);
            fs::remove_dir(r.join("temp")).unwrap();
        } else {
            assert_eq!(fs::read(r.join("temp")).unwrap(), b"foreign");
            fs::remove_file(r.join("temp")).unwrap();
        }
    }
}

#[test]
fn pinned_mutations_survive_parent_swap_or_platform_refusal() {
    let t = tempfile::tempdir().unwrap();
    let r = t.path().canonicalize().unwrap();
    fs::create_dir(r.join("inside")).unwrap();
    fs::create_dir(r.join("outside")).unwrap();
    fs::write(r.join("outside/sentinel"), b"outside").unwrap();
    fs::write(r.join("inside/source"), b"verified").unwrap();
    let source = r.join("inside/source");
    let dest = r.join("inside/dest");
    let movement = Move::prepare(&r, &source, &dest).unwrap();
    let pinned = parent(&r, &source).unwrap();
    pinned.verify_parent(&r, &source).unwrap();
    let id = file_identity(&pinned.directory).unwrap();
    fs::rename(r.join("inside"), r.join("saved")).unwrap();
    junction(&r.join("inside"), &r.join("outside"));
    assert!(pinned.verify_parent(&r, &source).is_err());
    movement.rename().unwrap();
    assert_eq!(fs::read(r.join("saved/dest")).unwrap(), b"verified");
    pinned.unlink(OsStr::new("dest"), false).unwrap();
    assert_eq!(file_identity(&pinned.directory).unwrap(), id);
    fs::remove_dir(r.join("inside")).unwrap();
    drop((pinned, movement));
    fs::rename(r.join("saved"), r.join("inside")).unwrap();
    let mut s = StagedFile::create(&r, &r.join("inside/temp")).unwrap();
    s.file.write_all(b"verified").unwrap();
    let mut swapped = false;
    // S1/S2 PC observation: an open file in a subtree may block directory rename.
    match fs::rename(r.join("inside"), r.join("saved")) {
        Ok(()) => {
            swapped = true;
            junction(&r.join("inside"), &r.join("outside"));
            assert!(s.publish(&r, &r.join("dest")).is_err());
        }
        Err(e) => {
            assert!(matches!(e.raw_os_error(), Some(5 | 32)), "{e}");
            s.source.verify_parent(&r, &s.path).unwrap();
        }
    }
    drop(s);
    let actual = if swapped { "saved" } else { "inside" };
    assert!(!r.join(actual).join("temp").exists());
    if swapped {
        fs::remove_dir(r.join("inside")).unwrap();
    }
    assert_eq!(fs::read(r.join("outside/sentinel")).unwrap(), b"outside");
    assert_eq!(fs::read_dir(r.join("outside")).unwrap().count(), 1);
}

#[test]
fn staged_creation_callback_preserves_visible_and_pinned_parent_policies() {
    for visible in [false, true] {
        let t = tempfile::tempdir().unwrap();
        let r = t.path().canonicalize().unwrap();
        fs::create_dir(r.join("inside")).unwrap();
        fs::create_dir(r.join("outside")).unwrap();
        fs::write(r.join("outside/sentinel"), b"outside").unwrap();
        let mut reached = false;
        let result =
            StagedFile::create_with_parent_check(&r, &r.join("inside/temp"), visible, |_| {
                reached = true;
                fs::rename(r.join("inside"), r.join("saved"))?;
                junction(&r.join("inside"), &r.join("outside"));
                Ok(())
            });
        assert!(reached);
        if visible {
            assert!(result.is_err());
        } else {
            let s = result.unwrap();
            assert!(r.join("saved/temp").is_file());
            assert!(s.publish(&r, &r.join("dest")).is_err());
            s.remove().unwrap();
            drop(s);
        }
        assert!(!r.join("saved/temp").exists());
        assert_eq!(fs::read(r.join("outside/sentinel")).unwrap(), b"outside");
        assert_eq!(fs::read_dir(r.join("outside")).unwrap().count(), 1);
        fs::remove_dir(r.join("inside")).unwrap();
    }
}
