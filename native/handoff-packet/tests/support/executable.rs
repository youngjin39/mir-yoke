//! On Linux, keep executable writable descriptors out of the multithreaded test process.
//! A concurrent fork can retain even CLOEXEC descriptors until it execs. Only
//! the short-lived cp child opens the destination for writing, and we reap it
//! before any caller executes the fixture (including indirect executions).
#[cfg(target_os = "linux")]
use std::process::Command;
use std::{fs, io, path::Path};

// Each integration test includes only the helpers it needs.
#[allow(dead_code)]
pub fn write(path: impl AsRef<Path>, bytes: impl AsRef<[u8]>) -> io::Result<()> {
    #[cfg(target_os = "linux")]
    {
        let staging = tempfile::NamedTempFile::new()?;
        fs::write(staging.path(), bytes)?;
        run_copy(staging.path(), path.as_ref(), false)
    }
    #[cfg(not(target_os = "linux"))]
    fs::write(path, bytes)
}

// Each integration test includes only the helpers it needs.
#[allow(dead_code)]
pub fn copy(source: impl AsRef<Path>, destination: impl AsRef<Path>) -> io::Result<()> {
    #[cfg(target_os = "linux")]
    {
        run_copy(source.as_ref(), destination.as_ref(), true)
    }
    #[cfg(not(target_os = "linux"))]
    fs::copy(source, destination).map(|_| ())
}

#[cfg(target_os = "linux")]
fn run_copy(source: &Path, destination: &Path, preserve_mode: bool) -> io::Result<()> {
    let mut command = Command::new("/bin/cp");
    if preserve_mode {
        command.arg("-p");
    }
    let output = command.arg(source).arg(destination).output()?;
    if !output.status.success() {
        return Err(io::Error::other(format!("fixture cp: {output:?}")));
    }
    Ok(())
}
