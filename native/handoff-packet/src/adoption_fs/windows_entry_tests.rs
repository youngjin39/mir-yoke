use super::{windows_parent_tests::file_id as raw_id, *};
use std::fs;
use std::io::{Read, Seek, Write};

#[test]
fn full_identity_types_and_creation_collision() {
    let t = tempfile::tempdir().unwrap();
    let r = t.path().canonicalize().unwrap();
    let p = parent(&r, &r.join("file")).unwrap();
    let mut file = p.create(&p.name, 0o600).unwrap();
    assert!(p.create(OsStr::new("..\\escape"), 0o600).is_err());
    assert!(p.create(OsStr::new("file:stream"), 0o600).is_err());
    file.write_all(b"original").unwrap();
    let id = p.identity().unwrap().unwrap();
    let (volume, bytes) = raw_id(&file);
    assert_eq!(
        format!("{id:?}"),
        format!("Identity {{ volume: {volume}, id: {bytes:?} }}")
    );
    assert_eq!(p.object_identity(true).unwrap(), None);
    assert!(owns_file(&p, &p.name, &file));
    assert_eq!(
        p.create(&p.name, 0o600).err().unwrap().kind(),
        io::ErrorKind::AlreadyExists
    );
    fs::hard_link(r.join("file"), r.join("alias")).unwrap();
    assert_eq!(
        parent(&r, &r.join("alias")).unwrap().identity().unwrap(),
        Some(id)
    );
    fs::rename(r.join("file"), r.join("saved")).unwrap();
    fs::write(r.join("file"), b"foreign").unwrap();
    assert!(!owns_file(&p, &p.name, &file));
    assert_ne!(p.identity().unwrap(), Some(id));
    file.rewind().unwrap();
    let mut bytes = Vec::new();
    file.read_to_end(&mut bytes).unwrap();
    assert_eq!(bytes, b"original");
    assert_eq!(fs::read(r.join("file")).unwrap(), b"foreign");
    let staged = StagedFile::create(&r, &r.join("stage")).unwrap();
    let entry = parent(&r, &staged.path)
        .unwrap()
        .identity()
        .unwrap()
        .unwrap();
    assert_eq!(staged.identity().unwrap(), entry);
    staged.keep(); // Windows staged cleanup/publication is S3.
}

#[test]
fn private_open_never_truncates_and_append_cannot_overwrite() {
    let t = tempfile::tempdir().unwrap();
    let r = t.path().canonicalize().unwrap();
    let p = parent(&r, &r.join("file")).unwrap();
    let mut private = p.open_private(false).unwrap();
    private.write_all(b"original").unwrap();
    drop(private);
    drop(p.open_private(false).unwrap());
    let mut append = p.open_private(true).unwrap();
    append.rewind().unwrap();
    append.write_all(b"+").unwrap();
    let mut bytes = Vec::new();
    p.open_file().unwrap().read_to_end(&mut bytes).unwrap();
    assert_eq!(bytes, b"original+");
    let missing = parent(&r, &r.join("missing")).unwrap();
    assert!(matches!(
        missing.open_file().err().unwrap().raw_os_error(),
        Some(2 | 3)
    ));
    assert!(matches!(
        missing.identity().err().unwrap().raw_os_error(),
        Some(2 | 3)
    ));
}

#[test]
fn directory_types_listing_and_sync_stay_on_the_handle() {
    let t = tempfile::tempdir().unwrap();
    let r = t.path().canonicalize().unwrap();
    mkdir(&r, &r.join("dir"), 0o777).unwrap();
    assert_eq!(
        mkdir(&r, &r.join("dir"), 0o777).err().unwrap().kind(),
        io::ErrorKind::AlreadyExists
    );
    let p = parent(&r, &r.join("dir")).unwrap();
    assert!(p.object_identity(true).unwrap().is_some());
    assert_eq!(p.identity().unwrap(), None);
    assert!(p.open_file().is_err());
    assert!(p.directory_empty().unwrap());
    fs::write(r.join("dir/entry"), b"x").unwrap();
    assert!(!p.directory_empty().unwrap());
    let leaf = parent(&r, &r.join("dir/entry")).unwrap();
    let error = leaf.directory_empty().err().unwrap();
    assert!(error.raw_os_error().is_some());
    let sync = leaf.sync_file().unwrap();
    assert_eq!(raw_id(&sync), raw_id(&leaf.directory));
    // Directory durability is filesystem-dependent; expose the real flush error.
    if let Err(error) = sync.sync_all() {
        assert!(error.raw_os_error().is_some(), "{error}");
    }
}

#[test]
fn refuses_reparse_leaves_without_touching_the_target() {
    let t = tempfile::tempdir().unwrap();
    let r = t.path().canonicalize().unwrap();
    let outside = r.join("outside");
    fs::create_dir(&outside).unwrap();
    fs::write(outside.join("sentinel"), b"outside").unwrap();
    super::windows_parent_tests::junction(&r.join("link"), &outside);
    let p = parent(&r, &r.join("link")).unwrap();
    assert_eq!(p.object_identity(true).unwrap(), None);
    assert_eq!(p.identity().unwrap(), None);
    assert!(p.open_file().is_err());
    assert!(p.open_private(false).is_err());
    assert!(p.directory_empty().is_err());
    assert!(p.create(&p.name, 0o600).is_err());
    fs::remove_dir(r.join("link")).unwrap();
    assert_eq!(fs::read(outside.join("sentinel")).unwrap(), b"outside");
    assert_eq!(fs::read_dir(outside).unwrap().count(), 1);
}

#[test]
fn pinned_entry_operations_do_not_follow_a_replaced_parent() {
    let t = tempfile::tempdir().unwrap();
    let r = t.path().canonicalize().unwrap();
    fs::create_dir(r.join("inside")).unwrap();
    fs::create_dir(r.join("outside")).unwrap();
    fs::write(r.join("outside/sentinel"), b"outside").unwrap();
    let path = r.join("inside/file");
    let p = parent(&r, &path).unwrap();
    p.verify_parent(&r, &path).unwrap();
    fs::rename(r.join("inside"), r.join("saved")).unwrap();
    super::windows_parent_tests::junction(&r.join("inside"), &r.join("outside"));
    assert!(p.verify_parent(&r, &path).is_err());
    assert_eq!(raw_id(&p.sync_file().unwrap()), raw_id(&p.directory));
    p.create(&p.name, 0o600)
        .unwrap()
        .write_all(b"pinned")
        .unwrap();
    p.open_private(true).unwrap().write_all(b"+").unwrap();
    assert_eq!(fs::read(r.join("saved/file")).unwrap(), b"pinned+");
    assert_eq!(fs::read(r.join("outside/sentinel")).unwrap(), b"outside");
    assert_eq!(fs::read_dir(r.join("outside")).unwrap().count(), 1);
    fs::remove_dir(r.join("inside")).unwrap();
}

#[test]
fn sync_reopen_does_not_require_directory_listing() {
    use std::os::windows::ffi::OsStrExt;
    use windows_sys::Win32::{
        Foundation::LocalFree,
        Security::{
            Authorization::{
                ConvertStringSecurityDescriptorToSecurityDescriptorW, SDDL_REVISION_1,
            },
            DACL_SECURITY_INFORMATION, GetFileSecurityW, PROTECTED_DACL_SECURITY_INFORMATION,
            SetFileSecurityW,
        },
    };
    struct RestoreDacl(Vec<u16>, Vec<u32>);
    impl Drop for RestoreDacl {
        fn drop(&mut self) {
            // SAFETY: original self-relative descriptor and terminated scratch path.
            assert_ne!(
                unsafe {
                    SetFileSecurityW(
                        self.0.as_ptr(),
                        DACL_SECURITY_INFORMATION,
                        self.1.as_mut_ptr().cast(),
                    )
                },
                0,
                "DACL restore: {}",
                io::Error::last_os_error()
            );
        }
    }
    let t = tempfile::tempdir().unwrap();
    let r = t.path().canonicalize().unwrap();
    let dir = r.join("restricted");
    fs::create_dir(&dir).unwrap();
    let path: Vec<_> = dir.as_os_str().encode_wide().chain(Some(0)).collect();
    let mut needed = 0;
    // SAFETY: size query followed by aligned storage of the advertised byte length.
    unsafe {
        GetFileSecurityW(
            path.as_ptr(),
            DACL_SECURITY_INFORMATION,
            std::ptr::null_mut(),
            0,
            &mut needed,
        )
    };
    assert!(needed > 0);
    let mut original = vec![0u32; (needed as usize).div_ceil(4)];
    assert_ne!(
        unsafe {
            GetFileSecurityW(
                path.as_ptr(),
                DACL_SECURITY_INFORMATION,
                original.as_mut_ptr().cast(),
                needed,
                &mut needed,
            )
        },
        0
    );
    let restore = RestoreDacl(path, original);
    // Deny only FILE_LIST_DIRECTORY (bit 1); allow write/attribute/traverse and
    // cleanup rights. No inheritance: the synthetic directory alone is affected.
    let sddl: Vec<_> = "D:P(D;;0x1;;;WD)(A;;FA;;;WD)"
        .encode_utf16()
        .chain(Some(0))
        .collect();
    let mut descriptor = std::ptr::null_mut();
    // SAFETY: terminated SDDL; API allocates descriptor, freed after SetFileSecurityW.
    assert_ne!(
        unsafe {
            ConvertStringSecurityDescriptorToSecurityDescriptorW(
                sddl.as_ptr(),
                SDDL_REVISION_1,
                &mut descriptor,
                std::ptr::null_mut(),
            )
        },
        0
    );
    let changed = unsafe {
        SetFileSecurityW(
            restore.0.as_ptr(),
            DACL_SECURITY_INFORMATION | PROTECTED_DACL_SECURITY_INFORMATION,
            descriptor,
        )
    };
    unsafe { LocalFree(descriptor) };
    assert_ne!(changed, 0);
    let p = parent(&r, &dir.join("file")).unwrap();
    let entry = parent(&r, &dir).unwrap();
    assert_eq!(entry.directory_empty().unwrap_err().raw_os_error(), Some(5));
    let mut file = p.create(&p.name, 0o600).unwrap();
    file.write_all(b"allowed").unwrap();
    assert!(p.identity().unwrap().is_some());
    let sync = p.sync_file().unwrap(); // baseline incorrectly asks for LIST_DIRECTORY
    assert_eq!(raw_id(&sync), raw_id(&p.directory));
    // Flush support is filesystem-dependent; reopening must not require listing.
    if let Err(error) = sync.sync_all() {
        assert!(error.raw_os_error().is_some(), "{error}");
    }
    drop(restore);
}
