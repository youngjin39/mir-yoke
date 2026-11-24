use crate::adoption_fs::windows_crt_error;
use std::{io, path::Path};

#[test]
fn w_errno2b_filename_spelling() {
    use crate::executor_text::{FilenameArgument, repr_points};
    // CPython PureWindowsPath rule; Str is passed directly to open().
    for (raw, expected) in [
        (
            "config/bootstrap-adoption.json",
            r"config\bootstrap-adoption.json",
        ),
        (r"C:/root/config/file", r"C:\root\config\file"),
        (r"//server/share/file", r"\\server\share\file"),
        (r"\\?\C:\root/file", r"\\?\C:\root\file"),
        (r"\\?\UNC\server\share/file", r"\\?\UNC\server\share\file"),
    ] {
        assert_eq!(
            FilenameArgument::Path.windows_points(Path::new(raw)),
            expected.chars().map(u32::from).collect::<Vec<_>>()
        );
        assert_eq!(
            FilenameArgument::Str.windows_points(Path::new(raw)),
            raw.chars().map(u32::from).collect::<Vec<_>>()
        );
    }
    assert_eq!(
        repr_points(
            &FilenameArgument::Path.windows_points(Path::new("config/bootstrap-adoption.json"))
        ),
        r"'config\\bootstrap-adoption.json'"
    );
}

fn operation_classes() -> Vec<crate::executor_text::IoOperation> {
    use crate::executor_text::IoOperation::*;
    vec![
        Read, Write, Stat, Lstat, Scandir, Listdir, Mkdir, Rmdir, Unlink, Rename, Replace, Chmod,
        Readlink, Symlink,
    ]
}

#[test]
fn w_errno2_operation_codes() {
    use crate::executor_text::IoOperation;
    for op in operation_classes() {
        for (code, mapped) in [(2, 2), (3, 2), (5, 13), (32, 13), (112, 28), (183, 17)] {
            let (_, form, number) =
                crate::executor_text::windows_error_code(&io::Error::from_raw_os_error(code), op);
            let crt = matches!(op, IoOperation::Read | IoOperation::Write);
            assert_eq!(
                (form, number),
                if crt {
                    ("Errno", mapped)
                } else {
                    ("WinError", code)
                },
                "{op:?}: {code}"
            );
        }
    }
}

#[cfg(windows)]
#[test]
fn w_errno2_captured_operations() {
    let corpus: serde_json::Value = serde_json::from_slice(
        &std::fs::read(
            Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/w-errno-windows.json"),
        )
        .expect("run generate_w_errno.py on Windows CPython 3.12 first"),
    )
    .unwrap();
    let records = corpus["operations"]
        .as_array()
        .expect("W-ERRNO-2 operation capture missing");
    for op in operation_classes() {
        let name = format!("{op:?}").to_lowercase();
        let mut count = 0;
        for record in records.iter().filter(|r| {
            (r["operation"] == name
                || (name == "read" && r["operation"] == "open")
                || (name == "write" && r["operation"] == "create"))
                && r["exception"].is_string()
        }) {
            let error = io::Error::from_raw_os_error(record["raw_code"].as_i64().unwrap() as i32);
            let path = record["filename"].as_str().map(Path::new);
            let dest = record["filename2"].as_str().map(Path::new);
            let rendered = crate::adoption_fs::windows_error(
                &error,
                path,
                dest,
                op,
                crate::executor_text::FilenameArgument::Str,
            );
            assert_eq!(
                rendered,
                format!(
                    "{}: {}",
                    record["exception"].as_str().unwrap(),
                    crate::windows_oracle::localize(record["message"].as_str().unwrap())
                ),
                "{}",
                record["case"]
            );
            let (_, form, number) = crate::executor_text::windows_error_code(&error, op);
            assert_eq!(windows_crt_error(&error).1, record["errno"]);
            if form == "Errno" {
                assert_eq!(number, record["errno"]);
            } else {
                assert_eq!(number, record["winerror"]);
            }
            count += 1;
        }
        assert!(count > 0, "missing {name} errors");
    }
}

#[cfg(windows)]
#[test]
fn w_errno2b_read_carrier_spelling() {
    use crate::executor_text::{FilenameArgument, IoOperation};
    let path = Path::new("config/bootstrap-adoption.json");
    let error = io::Error::from_raw_os_error(3);
    for (argument, expected) in [
        (
            FilenameArgument::Path,
            r"[Errno 2] No such file or directory: 'config\\bootstrap-adoption.json'",
        ),
        (
            FilenameArgument::Str,
            "[Errno 2] No such file or directory: 'config/bootstrap-adoption.json'",
        ),
    ] {
        assert_eq!(
            crate::executor_brief_profile::python_file_error_message(
                &error,
                path,
                IoOperation::Read,
                argument
            ),
            expected
        );
    }
    let temp = tempfile::tempdir().unwrap();
    let path = temp.path().join("absent/leaf");
    let error = std::fs::read(&path).unwrap_err();
    assert_eq!(error.raw_os_error(), Some(3));
    let expected = format!(
        "[Errno 2] No such file or directory: {}",
        crate::executor_text::repr(&format!(r"{}\absent\leaf", temp.path().display()))
    );
    assert_eq!(
        crate::mir_cli::bootstrap_adoption::read_error(&path, error).to_string(),
        expected
    );
}

#[cfg(windows)]
#[test]
fn w_errno2_real_read_routes() {
    let temp = tempfile::tempdir().unwrap();
    let path = temp.path().join("absent").join("leaf");
    let profile =
        crate::executor_brief_profile::BriefProfile::parse(&serde_json::json!({"name":"base_v1"}))
            .unwrap();
    let expected = format!(
        "[Errno 2] No such file or directory: {}",
        crate::executor_execute::repr(&path.display().to_string())
    );
    let error = profile.load(&path).unwrap_err();
    assert_eq!(error.kind, "FileNotFoundError");
    assert_eq!(error.message, expected);
    let error = crate::plugin_scripts::ontology_check::read(&path).unwrap_err();
    assert_eq!(error.message, expected);
    let error =
        crate::mir_cli::bootstrap_adoption::read_error(&path, std::fs::read(&path).unwrap_err());
    assert_eq!(error.to_string(), expected);
}

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
            crate::executor_execute::repr(&path.display().to_string().replace('/', "\\"))
        );
        assert_eq!(
            crate::executor_brief_profile::python_read_error_message(
                &error,
                &path,
                crate::executor_text::FilenameArgument::Path
            ),
            expected
        );
    }
    let error = fs::write(&file, "other").unwrap_err();
    assert_eq!(error.raw_os_error(), Some(32));
    assert_eq!(
        crate::executor_text::windows_error_code(&error, crate::executor_text::IoOperation::Write),
        ("PermissionError", "Errno", 13)
    );
    assert_eq!(
        crate::executor_brief_profile::python_file_error_message(
            &error,
            &file,
            crate::executor_text::IoOperation::Write,
            crate::executor_text::FilenameArgument::Path
        ),
        crate::executor_brief_profile::python_read_error_message(
            &error,
            &file,
            crate::executor_text::FilenameArgument::Path
        )
    );
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
            path,
            crate::executor_text::FilenameArgument::Path
        ),
        "[Errno 2] No such file or directory: 'synthetic/missing'"
    );
}
