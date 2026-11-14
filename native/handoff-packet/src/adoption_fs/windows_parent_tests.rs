use super::*;
use std::{
    fs,
    os::windows::{
        ffi::{OsStrExt, OsStringExt},
        io::AsRawHandle,
    },
    path::PathBuf,
    process::Command,
};

fn rejected(root: &Path, path: &Path) {
    assert_eq!(
        parent(root, path).err().unwrap().kind(),
        io::ErrorKind::InvalidInput
    );
}

#[test]
fn walks_drive_and_verbatim_roots_and_preserves_counted_utf16() {
    let t = tempfile::tempdir().unwrap();
    let root = t.path().canonicalize().unwrap();
    fs::create_dir(root.join("nested")).unwrap();
    let units: Vec<_> = root.as_os_str().encode_wide().collect();
    assert!(units.starts_with(&[92, 92, 63, 92]));
    let plain = PathBuf::from(OsString::from_wide(&units[4..]));
    let leaf = OsString::from_wide(&[0x41, 0xd800, 0x42]);
    fs::create_dir(root.join("nested").join(&leaf)).unwrap();
    for root in [&root, &plain] {
        assert!(parent(root, &root.join("nested").join(&leaf).join("payload")).is_ok());
        let p = parent(root, &root.join("nested").join(&leaf)).unwrap();
        assert!(p.directory.metadata().unwrap().is_dir());
        assert_eq!(p.name, leaf);
        let mut flags = 0;
        // SAFETY: live borrowed handle and writable flags; ownership unchanged.
        assert_ne!(
            unsafe {
                windows_sys::Win32::Foundation::GetHandleInformation(
                    p.directory.as_raw_handle(),
                    &mut flags,
                )
            },
            0
        );
        assert_eq!(
            flags & windows_sys::Win32::Foundation::HANDLE_FLAG_INHERIT,
            0
        );
    }
}

#[test]
fn refuses_aliases_streams_devices_and_counted_length_overflow() {
    let t = tempfile::tempdir().unwrap();
    let root = t.path().canonicalize().unwrap();
    for name in [
        "",
        ".",
        "..",
        "x:y",
        "nul.txt",
        "con .txt",
        "CON",
        "conin$",
        "conout$",
        "COM1",
        "LPT².log",
        "x.",
        "x ",
        "a*",
        "a?",
        "a|",
        "a\0b",
        "a\u{1f}",
    ] {
        rejected(&root, &root.join(name));
    }
    rejected(&root, &root.join("x".repeat(32768)));
    assert!(parent(&root, &root.join("x".repeat(32767))).is_ok());
    rejected(&root, &root.join("..\\outside"));
    rejected(&root, &root.with_file_name("outside").join("leaf"));
    let plain = Path::new(r"C:\synthetic");
    rejected(plain, &plain.join(r"nested\.\leaf"));
}

#[test]
fn refuses_untrusted_root_prefixes_before_opening() {
    for root in [
        r"C:relative",
        r"\relative",
        r"\\.\C:\",
        r"\\?\GLOBALROOT\Device\HarddiskVolume1",
        r"\\?\arbitrary\root",
        r"C:\nul\root",
        r"C:\root\..\other",
        r"\\?\Volume{not-a-guid}\root",
    ] {
        let root = Path::new(root);
        rejected(root, &root.join("leaf"));
    }
}

#[test]
fn preserves_missing_and_wrong_type_os_errors() {
    let t = tempfile::tempdir().unwrap();
    let root = t.path().canonicalize().unwrap();
    let missing = parent(&root, &root.join("missing\\leaf")).err().unwrap();
    assert!(matches!(missing.raw_os_error(), Some(2 | 3)));
    fs::write(root.join("file"), b"unchanged").unwrap();
    assert!(
        parent(&root, &root.join("file\\leaf"))
            .err()
            .unwrap()
            .raw_os_error()
            .is_some()
    );
    assert_eq!(fs::read(root.join("file")).unwrap(), b"unchanged");
}

fn junction(link: &Path, target: &Path) {
    let plain = |path: &Path| {
        let units: Vec<_> = path.as_os_str().encode_wide().collect();
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

#[test]
fn refuses_junctions_above_and_inside_root_and_keeps_pinned_parent() {
    let t = tempfile::tempdir().unwrap();
    let base = t.path().canonicalize().unwrap();
    let root = base.join("root");
    let outside = base.join("outside");
    fs::create_dir(&root).unwrap();
    fs::create_dir(&outside).unwrap();
    fs::write(outside.join("sentinel"), b"outside").unwrap();
    let inside = root.join("inside");
    fs::create_dir(&inside).unwrap();
    let pinned = parent(&root, &inside.join("leaf")).unwrap();
    let identity = file_id(&pinned.directory);
    let moved = root.join("moved");
    fs::rename(&inside, &moved).unwrap();
    junction(&inside, &outside);
    assert!(parent(&root, &inside.join("leaf")).is_err());
    assert!(pinned.directory.metadata().unwrap().is_dir());
    assert_eq!(file_id(&pinned.directory), identity);
    fs::remove_dir(&inside).unwrap();
    let saved = base.join("saved");
    // Observed on the PC (Windows 10.0.26200): an open subtree handle can
    // prevent ancestor rename with ERROR_ACCESS_DENIED despite DELETE sharing.
    let swapped = match fs::rename(&root, &saved) {
        Ok(()) => true,
        Err(error) => {
            assert!(matches!(error.raw_os_error(), Some(5 | 32)), "{error}");
            assert!(!saved.exists());
            false
        }
    };
    assert_eq!(file_id(&pinned.directory), identity);
    assert_eq!(fs::read(outside.join("sentinel")).unwrap(), b"outside");
    assert_eq!(fs::read_dir(&outside).unwrap().count(), 1);
    drop(pinned);
    if !swapped {
        fs::rename(&root, &saved).unwrap();
    }
    junction(&root, &outside);
    assert!(parent(&root, &root.join("leaf")).is_err());
    fs::remove_dir(&root).unwrap();
    assert_eq!(fs::read(outside.join("sentinel")).unwrap(), b"outside");
    assert_eq!(fs::read_dir(&outside).unwrap().count(), 1);
    assert_eq!(fs::read_dir(saved.join("moved")).unwrap().count(), 0);
}

fn file_id(file: &File) -> (u64, [u8; 16]) {
    use windows_sys::Win32::Storage::FileSystem::{
        FILE_ID_INFO, FileIdInfo, GetFileInformationByHandleEx,
    };
    let mut id = FILE_ID_INFO::default();
    // SAFETY: exact repr(C) record for FileIdInfo; live borrowed directory handle.
    assert_ne!(
        unsafe {
            GetFileInformationByHandleEx(
                file.as_raw_handle(),
                FileIdInfo,
                (&mut id as *mut FILE_ID_INFO).cast(),
                std::mem::size_of::<FILE_ID_INFO>() as u32,
            )
        },
        0
    );
    (id.VolumeSerialNumber, id.FileId.Identifier)
}
