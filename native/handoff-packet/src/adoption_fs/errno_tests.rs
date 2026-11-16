use crate::adoption_fs::windows_crt_error;
use std::{io, path::Path};

#[test]
fn w_errno_raw_codes() {
    for (code, expected) in [
        (2, "FileNotFoundError: [Errno 2] No such file or directory"),
        (3, "FileNotFoundError: [Errno 2] No such file or directory"),
        (5, "PermissionError: [Errno 13] Permission denied"),
        (32, "PermissionError: [Errno 13] Permission denied"),
        (183, "FileExistsError: [Errno 17] File exists"),
    ] {
        let (class, errno, text) = windows_crt_error(&io::Error::from_raw_os_error(code));
        assert_eq!(
            format!("{class}: [Errno {errno}] {text}"),
            expected,
            "Win32 {code}"
        );
    }
}

#[cfg(windows)]
#[test]
fn w_errno_captured_codes() {
    let corpus: serde_json::Value = serde_json::from_slice(
        &std::fs::read(
            Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/w-errno-windows.json"),
        )
        .expect("capture w-errno-windows.json on Windows with generate_w_errno.py first"),
    )
    .unwrap();
    assert_eq!(
        corpus["reference_pin"],
        "a61c3013dc382989c321577bb93dd937d11884fd"
    );
    assert_eq!(corpus["platform"], "win32");
    assert_eq!(corpus["records"].as_object().unwrap().len(), 5);
    for (code, expected) in corpus["records"].as_object().unwrap() {
        let (class, errno, text) =
            windows_crt_error(&io::Error::from_raw_os_error(code.parse().unwrap()));
        assert_eq!(class, expected["exception"]);
        assert_eq!(errno, expected["errno"]);
        assert_eq!(format!("[Errno {errno}] {text}"), expected["message"]);
    }
}

#[cfg(windows)]
#[test]
fn w_errno_real_failures() {
    use std::{fs, os::windows::fs::OpenOptionsExt};
    let temp = tempfile::tempdir().unwrap();
    let root = temp.path();
    let file = root.join("file");
    fs::write(&file, "synthetic").unwrap();
    let lock = fs::OpenOptions::new()
        .read(true)
        .share_mode(0)
        .open(&file)
        .unwrap();
    for (path, result, code) in [
        (root.join("absent"), fs::read(root.join("absent")), 2),
        (
            root.join("absent/leaf"),
            fs::read(root.join("absent/leaf")),
            3,
        ),
        (root.to_owned(), fs::read(root), 5),
        (file.clone(), fs::read(&file), 32),
    ] {
        let error = result.unwrap_err();
        assert_eq!(error.raw_os_error(), Some(code));
        let (_, errno, text) = windows_crt_error(&error);
        let expected = format!(
            "[Errno {errno}] {text}: {}",
            crate::executor_execute::repr(&path.display().to_string())
        );
        assert_eq!(
            crate::executor_brief_profile::python_read_error_message(&error, &path),
            expected
        );
    }
    drop(lock);
    let error = fs::create_dir(root).unwrap_err();
    assert_eq!(error.raw_os_error(), Some(183));
    assert_eq!(
        windows_crt_error(&error),
        ("FileExistsError", 17, "File exists".into())
    );
    let error = fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&file)
        .unwrap_err();
    assert!(matches!(error.raw_os_error(), Some(80 | 183)));
    assert_eq!(
        windows_crt_error(&error),
        ("FileExistsError", 17, "File exists".into())
    );
}

#[test]
fn w_errno_unix_text_unchanged() {
    if cfg!(windows) {
        return;
    }
    let path = Path::new("synthetic/missing");
    assert_eq!(
        crate::executor_brief_profile::python_read_error_message(
            &io::Error::from_raw_os_error(2),
            path
        ),
        "[Errno 2] No such file or directory: 'synthetic/missing'"
    );
}
