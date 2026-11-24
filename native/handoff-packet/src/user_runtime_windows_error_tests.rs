//! Scratch OS failures; localize only Win32 message text in the pinned PC corpus.
// Windows only: set_readonly(false) clears FILE_ATTRIBUTE_READONLY set by the test itself; no Unix mode bits exist here.
#![allow(clippy::permissions_set_readonly_false)]
use super::*;
use crate::executor_text::IoOperation;
use serde_json::Value;
use std::{fs, io, os::windows::io::AsRawHandle};
use windows_sys::Win32::Storage::FileSystem::*;
#[rustfmt::skip]
fn corpus() -> Value { serde_json::from_str(include_str!("../../../tests/fixtures/user_runtime_install/installer-windows.json")).unwrap() }
// Other tests must not allocate a handle between the two real OS calls below.
fn isolated_handle_probe(name: &str) -> bool {
    if std::env::var("MIR_S7_HANDLE_PROBE").ok().as_deref() == Some(name) {
        return false;
    }
    let test = format!("{}::{name}", module_path!().split_once("::").unwrap().1);
    let output = std::process::Command::new(std::env::current_exe().unwrap())
        .args(["--exact", &test, "--test-threads=1", "--nocapture"])
        .env("MIR_S7_HANDLE_PROBE", name)
        .output()
        .unwrap();
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(
        output.status.success() && stdout.contains("1 passed"),
        "{output:?}"
    );
    true
}
fn check(name: &str, error: Error, root: &Path) {
    let c = corpus();
    let expected = &c["records"][name]["error"];
    let mut rendered = expected["rendered"].as_str().unwrap().to_owned();
    if name == "rollback" {
        // S7 FIX 2: the handle-relative NT replace reports sharing violation,
        // while MoveFileExW reports access denied for the same deny-delete handle.
        // Keep the reference record intact; borrow only the independently frozen
        // OS message for code 32. The syscall comparison lives in the rename probe.
        let sharing = &c["records"]["win32-sharing"]["error"];
        assert_eq!(sharing["class"], expected["cause"]["class"]);
        assert_eq!(sharing["errno"], expected["cause"]["errno"]);
        assert_eq!(expected["cause"]["winerror"], 5);
        assert_eq!(sharing["winerror"], 32);
        rendered = rendered.replacen(
            &format!(
                "[WinError 5] {}",
                expected["cause"]["strerror"].as_str().unwrap()
            ),
            &format!("[WinError 32] {}", sharing["strerror"].as_str().unwrap()),
            1,
        );
    }
    let rendered = crate::windows_oracle::localize(&rendered);
    let mut message = error
        .message
        .replace(&root.to_str().unwrap().replace('\\', "\\\\"), "{ROOT}")
        .replace(root.to_str().unwrap(), "{ROOT}");
    if let Some(start) = message.find(".mir-install-") {
        let end = start + message[start..].find('\'').unwrap();
        message.replace_range(
            start..end,
            if name == "rollback" {
                "{TEMP-13}"
            } else {
                "{TEMP-16}"
            },
        );
    }
    assert_eq!(
        error.class,
        expected["class"].as_str().unwrap(),
        "{name}: {error:?}"
    );
    assert_eq!(message, rendered, "{name}: {error:?}");
}
#[test]
#[rustfmt::skip]
fn frozen_os_errors() {
    let temp = tempfile::tempdir().unwrap(); let root = temp.path().canonicalize().unwrap();
    for case in ["os-errors", "extended-os-errors", "refusals"] { fs::create_dir_all(root.join("cases").join(case)).unwrap(); }
    let base = root.join("cases\\os-errors"); let file = base.join("file"); let dir = base.join("directory");
    fs::write(&file,b"x").unwrap(); fs::create_dir(&dir).unwrap(); fs::write(dir.join("child"),b"x").unwrap();
    for (name, path, destination, operation, result) in [
        ("read-missing",base.join("missing"),None,IoOperation::Read,fs::read(base.join("missing")).map(|_|())),
        ("replace-missing",base.join("missing"),Some(file.clone()),IoOperation::Win32,fs::rename(base.join("missing"),&file)),
        ("mkdir-collision",file.clone(),None,IoOperation::Win32,fs::create_dir(&file)),
        ("rmdir-nonempty",dir.clone(),None,IoOperation::Win32,fs::remove_dir(&dir)),
        ("unlink-directory",dir,None,IoOperation::Win32,fs::remove_file(base.join("directory"))),
    ] { let e = result.unwrap_err(); check(name,operation_error(Some(&path),destination.as_deref(),e,operation),&root); }
    let ext = root.join("cases\\extended-os-errors"); fs::write(ext.join("file"),b"x").unwrap();
    for (name,path) in [("win32-path-missing",ext.join("absent\\child")),("win32-invalid-name",ext.join("bad<name")),("win32-long-name",ext.join("x".repeat(256)))] {
        check(name,io(&path,fs::create_dir(&path).unwrap_err()),&root);
    }
    check("win32-not-directory",io(&ext.join("file"),fs::read_dir(ext.join("file")).unwrap_err()),&root);
    let path = root.join("cases\\refusals\\file"); fs::write(&path,b"foreign").unwrap();
    let mut permissions = fs::metadata(&path).unwrap().permissions(); permissions.set_readonly(true); fs::set_permissions(&path,permissions).unwrap();
    let identity = capture_home_identity(path.parent().unwrap()).unwrap();
    let error = write(&identity,Path::new("file"),b"new").unwrap_err();
    let mut permissions = fs::metadata(&path).unwrap().permissions(); permissions.set_readonly(false); fs::set_permissions(&path,permissions).unwrap();
    check("atomic-readonly",error,&root);
}
#[test]
// SAFETY: only the documented OS failure probes below use raw handles.
#[allow(unsafe_code)]
#[rustfmt::skip]
fn frozen_handle_errors() {
    if isolated_handle_probe("frozen_handle_errors") { return; }
    assert_eq!(std::env::var("MIR_S7_HANDLE_PROBE").ok().as_deref(), Some("frozen_handle_errors"));
    use std::os::windows::fs::OpenOptionsExt;
    let temp = tempfile::tempdir().unwrap(); let root = temp.path().canonicalize().unwrap();
    let path = root.join("file"); fs::write(&path,b"locked byte").unwrap();
    let file = fs::File::open(&path).unwrap(); let handle = file.as_raw_handle(); drop(file);
    // SAFETY: only this test runs in the child; no allocation between close and flush.
    assert_eq!(unsafe { FlushFileBuffers(handle) },0);
    let error = io::Error::last_os_error();
    check("win32-invalid-handle",operation_error(None,None,io::Error::from_raw_os_error(error.raw_os_error().unwrap()),IoOperation::Win32),&root);
    check("crt-bad-fd",operation_error(None,None,error,IoOperation::Handle),&root);
    let locked = fs::OpenOptions::new().read(true).write(true).open(&path).unwrap();
    let reader = fs::File::open(&path).unwrap();
    // SAFETY: live handles and buffers remain valid throughout these synchronous calls.
    unsafe {
        assert_ne!(LockFile(locked.as_raw_handle(),0,0,1,0),0);
        let mut byte=0u8; let mut count=0;
        assert_eq!(ReadFile(reader.as_raw_handle(),&mut byte,1,&mut count,std::ptr::null_mut()),0);
        let error=io::Error::last_os_error();
        check("win32-lock",operation_error(None,None,io::Error::from_raw_os_error(error.raw_os_error().unwrap()),IoOperation::Win32),&root);
        check("crt-lock-read",operation_error(None,None,error,IoOperation::Handle),&root);
        assert_ne!(UnlockFile(locked.as_raw_handle(),0,0,1,0),0);
    }
    drop(reader); drop(locked);
    let exclusive = fs::OpenOptions::new().read(true).share_mode(0).open(&path).unwrap();
    let src = root.join("cases\\extended-os-errors\\file"); fs::create_dir_all(src.parent().unwrap()).unwrap();
    let dst = src.with_file_name("renamed");
    check("win32-sharing",operation_error(Some(&src),Some(&dst),fs::rename(&path,root.join("renamed")).unwrap_err(),IoOperation::Win32),&root);
    drop(exclusive);
    let file = fs::File::open(&path).unwrap();
    let wide: Vec<u16> = { use std::os::windows::ffi::OsStrExt; path.as_os_str().encode_wide().chain(Some(0)).collect() };
    // SAFETY: the name is NUL terminated; File remains owned until after the probe.
    unsafe {
        assert_ne!(DeleteFileW(wide.as_ptr()),0);
        check("win32-delete-pending",operation_error(None,None,fs::File::open(&path).unwrap_err(),IoOperation::Win32),&root);
    }
    drop(file);
    fs::write(&src,b"x").unwrap();
    check("win32-exists",operation_error(None,None,fs::OpenOptions::new().write(true).create_new(true).open(&src).unwrap_err(),IoOperation::Win32),&root);
}
#[test]
#[rustfmt::skip]
fn frozen_logical_refusals_and_rollback() {
    use super::user_runtime_windows_oracle_tests::{plans, seed, tree};
    use std::os::windows::fs::OpenOptionsExt;
    let temp=tempfile::tempdir().unwrap(); let root=temp.path().canonicalize().unwrap();
    let provider=root.join("provider"); fs::create_dir_all(&provider).unwrap();
    check("sources-missing",load_sources(&provider).unwrap_err(),&root);
    check("source-missing",regular_source(&provider,&provider.join("missing.md")).unwrap_err(),&root);
    for (name,path) in [("home-relative",PathBuf::from("relative")),("home-root",root.ancestors().last().unwrap().to_owned())] {
        check(name,require_safe_home(&path).unwrap_err(),&root);
    }
    let admission=root.join("cases\\admission"); fs::create_dir_all(&admission).unwrap();
    fs::write(admission.join(RECEIPT_NAME),b"{").unwrap();
    match load_receipt(&admission,"claude") {
        Err(error) => check("receipt-malformed",error,&root),
        Ok(_) => panic!("malformed receipt must fail"),
    }
    let refusals=root.join("cases\\refusals"); fs::create_dir_all(&refusals).unwrap(); fs::write(refusals.join("file"),b"foreign").unwrap();
    check("target-nonregular",safe_target(&refusals,Path::new("file/child")).unwrap_err(),&root);
    let plan=RuntimePlan { identity:capture_home_identity(&refusals).unwrap(), files:vec![], stale:vec![], receipt:vec![], created_home:false };
    check("restore-foreign",restore(&plan,&Snapshot { relative:"file".into(),before:Some(b"old".to_vec()),after:Some(b"new".to_vec()) }).unwrap_err(),&root);
    // Run the real stale branch, then remove only the transaction wrapper when
    // comparing the reference's direct remove_stale_file boundary.
    let plan=RuntimePlan { stale:vec![StaleFile { source_relative:crate::python_json::Text::new(vec![]), target_relative:"file".into(),sha256:sha256_bytes(b"old") }], ..plan };
    let error=apply_transaction(&[plan]).unwrap_err();
    let message=error.message.strip_prefix("apply failed; rollback complete: ").unwrap();
    check("stale-divergent",sync(message.into()),&root);
    let c=corpus(); let case=root.join("cases\\rollback"); fs::create_dir_all(&case).unwrap(); seed(&case,&c["records"]["rollback"]);
    let plans=plans(&case,&c);
    let lock=fs::OpenOptions::new().read(true).share_mode(FILE_SHARE_READ | FILE_SHARE_WRITE).open(case.join("codex\\agents\\old.md")).unwrap();
    let codex=plans.iter().find(|p| p.identity.path == case.join("codex")).unwrap();
    let denied=write(&codex.identity,Path::new("agents/old.md"),b"new").unwrap_err();
    assert_eq!(denied.class,c["records"]["rollback"]["error"]["cause"]["class"].as_str().unwrap());
    assert!(denied.message.starts_with("[WinError 32] "),"{denied:?}");
    let result=apply_transaction(&plans); drop(lock);
    check("rollback",result.unwrap_err(),&root);
    assert_eq!(tree(&case),c["records"]["rollback"]["tree"]);
    // Python rejects negative numeric fds before the OS. Native APIs accept File,
    // so this ValueError is an unreachable argument-validation boundary.
    assert_eq!(c["records"]["fsync-invalid"]["error"]["class"],"ValueError");
    assert_eq!(c["records"].as_object().unwrap().values().filter(|r| !r["error"].is_null()).count(),27);
}
#[test]
fn cleanup_failure_supersedes_replace_failure() {
    let temp = tempfile::tempdir().unwrap();
    let root = temp.path().canonicalize().unwrap();
    let target = root.join("target");
    fs::write(&target, b"before").unwrap();
    let identity = capture_home_identity(&root).unwrap();
    let mut temporary = PathBuf::new();
    let result = write_with(&identity, Path::new("target"), b"after", |stage| {
        temporary = stage.to_owned();
        for path in [stage, &target] {
            let mut permissions = fs::metadata(path)?.permissions();
            permissions.set_readonly(true);
            fs::set_permissions(path, permissions)?;
        }
        Ok(())
    });
    let error = result.unwrap_err();
    assert_eq!(error.class, "PermissionError", "{error:?}");
    assert!(!error.message.contains(" -> "), "{error:?}");
    assert!(temporary.exists(), "{error:?}");
    assert_eq!(fs::read(&target).unwrap(), b"before", "{error:?}");
    for path in [&temporary, &target] {
        let mut permissions = fs::metadata(path).unwrap().permissions();
        permissions.set_readonly(false);
        fs::set_permissions(path, permissions).unwrap();
    }
}
#[test]
// SAFETY: this probe invalidates its own handle immediately before checked close.
#[allow(unsafe_code)]
fn checked_close_exposes_a_real_invalid_handle_failure() {
    if isolated_handle_probe("checked_close_exposes_a_real_invalid_handle_failure") {
        return;
    }
    assert_eq!(
        std::env::var("MIR_S7_HANDLE_PROBE").ok().as_deref(),
        Some("checked_close_exposes_a_real_invalid_handle_failure")
    );
    let temp = tempfile::tempdir().unwrap();
    let file = fs::File::create(temp.path().join("file")).unwrap();
    // SAFETY: only this test runs in the child; no allocation between the closes.
    assert_ne!(
        unsafe { windows_sys::Win32::Foundation::CloseHandle(file.as_raw_handle()) },
        0
    );
    let error = crate::adoption_fs::close_file(file).unwrap_err();
    assert_eq!(error.raw_os_error(), Some(6), "{error:?}");
    check("crt-bad-fd", io_context(None, error), temp.path());
}
