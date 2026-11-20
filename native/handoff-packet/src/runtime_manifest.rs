//! Full, opt-in runtime manifest provider. Consumer entry points remain unchanged.
#![deny(unsafe_code)]
#![cfg_attr(
    not(test),
    deny(clippy::unwrap_used, clippy::expect_used, clippy::panic)
)]
// Reuse the reviewed descriptor-relative adoption boundary. Loaded as a normal (non-#[path]) module so its
// platform submodules resolve under src/adoption_fs/ exactly as in the library.
#[cfg(unix)]
#[allow(unsafe_code, dead_code)]
#[path = "."]
mod fs_root {
    pub(crate) mod adoption_fs;
}
#[cfg(unix)]
use fs_root::adoption_fs;
#[path = "runtime_manifest_args.rs"]
mod runtime_manifest_args;
#[path = "runtime_verify.rs"]
mod runtime_verify;

use runtime_verify::Failure;
#[cfg(any(test, not(unix)))]
use std::fs;
use std::{
    collections::BTreeMap,
    ffi::OsString,
    io::{self, Write},
    path::Path,
};

type Result<T> = std::result::Result<T, Failure>;

use runtime_verify::io_failure;

#[cfg(unix)]
fn publish(
    root: &Path,
    target: &Path,
    body: &[u8],
    before_move: impl FnOnce(&Path, &Path),
) -> Result<()> {
    let parent = adoption_fs::parent(root, target).map_err(|e| io_failure(target, e))?;
    let mut prefix = OsString::from(".");
    prefix.push(target.file_name().unwrap_or_default());
    prefix.push(".");
    // Generation needs no scratch I/O. Disable pathname cleanup so every
    // mutation, including cleanup, uses the pinned directory descriptor.
    let mut attempted = target.to_path_buf();
    let temporary_file = tempfile::Builder::new()
        .prefix(&prefix)
        .rand_bytes(8)
        .make_in(root, |candidate| {
            attempted = candidate.to_path_buf();
            parent.create(candidate.file_name().unwrap_or_default(), 0o600)
        })
        .map_err(|e| io_failure(&attempted, e))?;
    let (mut handle, mut inert_path) = temporary_file.into_parts();
    inert_path.disable_cleanup(true);
    let temporary_name = inert_path.file_name().unwrap_or_default().to_owned();
    let temporary = root.join(&temporary_name);
    let result = (|| {
        handle
            .write_all(body)
            .and_then(|()| handle.flush())
            .and_then(|()| handle.sync_all())
            .map_err(|e| io_failure(&temporary, e))?;
        drop(handle);
        before_move(&temporary, target);
        let movement = adoption_fs::Move::prepare(root, &temporary, target).map_err(|_| {
            Failure::Error(format!(
                "unsafe slim move: {} -> {}",
                temporary_name.to_string_lossy(),
                target.file_name().unwrap_or_default().to_string_lossy()
            ))
        })?;
        movement
            .rename()
            .map_err(|e| match io_failure(&temporary, e) {
                Failure::Error(message) => Failure::Error(format!(
                    "{}: {} -> {}",
                    message.split(": ").next().unwrap_or(&message),
                    runtime_verify::path_repr(Path::new(&temporary_name)),
                    runtime_verify::path_repr(Path::new(target.file_name().unwrap_or_default()))
                )),
                other => other,
            })
    })();
    let cleanup = parent.unlink(&temporary_name, false);
    if let Err(e) = cleanup
        && e.kind() != io::ErrorKind::NotFound
    {
        return Err(io_failure(&temporary, e));
    }
    result
}

#[cfg(not(unix))]
fn publish(
    root: &Path,
    target: &Path,
    body: &[u8],
    before_move: impl FnOnce(&Path, &Path),
) -> Result<()> {
    fs::create_dir_all(root).map_err(|e| io_failure(root, e))?;
    let mut temporary = tempfile::Builder::new()
        .prefix(&format!(
            ".{}.",
            target.file_name().unwrap_or_default().to_string_lossy()
        ))
        .rand_bytes(8)
        .tempfile_in(root)
        .map_err(|e| io_failure(target, e))?;
    let body = String::from_utf8_lossy(body).replace('\n', "\r\n");
    temporary
        .write_all(body.as_bytes())
        .and_then(|()| temporary.flush())
        .and_then(|()| temporary.as_file().sync_all())
        .map_err(|e| io_failure(temporary.path(), e))?;
    before_move(temporary.path(), target);
    temporary
        .persist(target)
        .map_err(|e| io_failure(target, e.error))?;
    Ok(())
}

fn create(options: &BTreeMap<String, OsString>) -> Result<usize> {
    let input_root = runtime_verify::expand_path(Path::new(&options["--runtime-root"]))?;
    let root = runtime_verify::strict_root(&input_root)?;
    let target = runtime_verify::resolve_path(
        &runtime_verify::expand_path(Path::new(&options["--manifest"]))?,
        false,
    )?;
    if target.parent() != Some(root.as_path()) {
        return Err(Failure::Error(
            "runtime manifest must be a direct child of the runtime root".into(),
        ));
    }
    let entries = runtime_verify::runtime_entries(&root, &target)?;
    let entry_text = runtime_verify::pretty_entries(&entries);
    let entry_text = entry_text.replace('\n', "\n  ");
    let body = format!(
        "{{\n  \"constraints_sha256\": {},\n  \"entries\": {},\n  \"schema_version\": 1,\n  \"source_commit\": {},\n  \"source_url\": {}\n}}\n",
        runtime_verify::quote_path(Path::new(&options["--constraints-sha256"])),
        entry_text,
        runtime_verify::quote_path(Path::new(&options["--source-commit"])),
        runtime_verify::quote_path(Path::new(&options["--source-url"]))
    );
    publish(&root, &target, body.as_bytes(), |_, _| {})?;
    Ok(entries.len())
}

pub fn console(args: Vec<OsString>) -> (i32, String, String) {
    let (command, options) = match runtime_manifest_args::parse(args) {
        runtime_manifest_args::Parsed::Run { command, options } => (command, options),
        runtime_manifest_args::Parsed::Exit {
            code,
            stdout,
            stderr,
        } => return (code, stdout, stderr),
    };
    let result = match command.as_str() {
        "create" => create(&options)
            .map(|entries| format!("{{\"status\": \"created\", \"entries\": {entries}}}\n")),
        "verify" => runtime_verify::verify_os(
            Path::new(&options["--runtime-root"]),
            Path::new(&options["--manifest"]),
            Some(&options["--source-url"]),
            Some(&options["--source-commit"]),
            Some(&options["--constraints-sha256"]),
        )
        .map(|()| String::new()),
        _ => Err(Failure::Error(format!("invalid command: {command}"))),
    };
    match result {
        Ok(out) => (0, out, String::new()),
        Err(Failure::Finding(message)) => (
            2,
            String::new(),
            format!("runtime manifest error: {message}\n"),
        ),
        Err(Failure::Error(message)) => (
            2,
            String::new(),
            format!("runtime manifest error: {message}\n"),
        ),
        Err(Failure::Exception(message)) => (1, String::new(), format!("{message}\n")),
        Err(Failure::Unsupported) => (
            1,
            String::new(),
            "ValueError: unsupported runtime manifest input\n".into(),
        ),
    }
}
#[allow(dead_code)]
fn main() {
    let (code, out, err) = console(std::env::args_os().skip(1).collect());
    let _ = io::stdout().write_all(out.as_bytes());
    let _ = io::stderr().write_all(err.as_bytes());
    std::process::exit(code);
}

#[cfg(all(test, unix))]
mod tests {
    use super::*;

    #[test]
    fn verify_through_forty_symlinks() -> std::result::Result<(), Box<dyn std::error::Error>> {
        use std::os::unix::fs::symlink;

        let base = tempfile::tempdir()?;
        let root = base.path().join("runtime");
        fs::create_dir(&root)?;
        let manifest = root.join("manifest.json");
        fs::write(
            &manifest,
            r#"{"schema_version":1,"entries":[],"source_url":"fixture","source_commit":"fixture","constraints_sha256":"fixture"}"#,
        )?;
        symlink("runtime/manifest.json", base.path().join("link39"))?;
        for i in (0..39).rev() {
            symlink(
                format!("link{}", i + 1),
                base.path().join(format!("link{i}")),
            )?;
        }
        let verify = || {
            console(vec![
                "verify".into(),
                "--runtime-root".into(),
                root.as_os_str().into(),
                "--manifest".into(),
                base.path().join("link0").into_os_string(),
                "--source-url".into(),
                "fixture".into(),
                "--source-commit".into(),
                "fixture".into(),
                "--constraints-sha256".into(),
                "fixture".into(),
            ])
        };
        assert_eq!(verify(), (0, String::new(), String::new()));
        fs::remove_file(manifest)?;
        assert_eq!(
            verify(),
            (
                2,
                String::new(),
                "runtime manifest error: runtime manifest is unreadable\n".into()
            )
        );
        Ok(())
    }

    #[test]
    fn manifest_layout_change_before_replace() -> std::result::Result<(), Box<dyn std::error::Error>>
    {
        let base = tempfile::tempdir()?;
        let base = fs::canonicalize(base.path())?;
        let root = base.join("root");
        let outside = base.join("outside");
        fs::create_dir(&root)?;
        fs::create_dir(&outside)?;
        fs::write(outside.join("manifest"), b"SENTINEL")?;
        let result = publish(&root, &root.join("manifest"), b"BODY", |source, _| {
            let moved = base.join("moved");
            assert!(fs::rename(&root, moved).is_ok());
            assert!(std::os::unix::fs::symlink(&outside, &root).is_ok());
            assert!(
                fs::write(
                    outside.join(source.file_name().unwrap_or_default()),
                    b"TRAP"
                )
                .is_ok()
            );
        });
        assert!(result.is_err());
        assert_eq!(fs::read(outside.join("manifest"))?, b"SENTINEL");
        assert_eq!(fs::read_dir(base.join("moved"))?.count(), 0);
        Ok(())
    }
}
