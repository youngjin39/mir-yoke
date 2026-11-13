//! Signal only an unreaped subprocess represented by an owned std Child.
use std::{io, process::Child};

pub(crate) fn terminate_owned_child(child: &mut Child) -> io::Result<()> {
    if child.try_wait()?.is_some() {
        return Ok(());
    }
    let pid = libc::pid_t::try_from(child.id())
        .map_err(|_| io::Error::new(io::ErrorKind::InvalidInput, "invalid child process ID"))?;
    // SAFETY: Child owns this subprocess and has not reaped it. Its PID cannot
    // be reused while it is live or an unreaped zombie. The exclusive borrow
    // prevents another Child operation from reaping it during this call.
    if unsafe { libc::kill(pid, libc::SIGTERM) } == 0 {
        return Ok(());
    }
    let error = io::Error::last_os_error();
    // Popen.terminate ignores a child exiting between poll and signal delivery.
    if error.raw_os_error() == Some(libc::ESRCH) {
        Ok(())
    } else {
        Err(error)
    }
}

// The execute binary owns signal policy; the handler only records a request.
// All process operations happen in the transport owner, outside signal context.
use std::sync::atomic::{AtomicI32, Ordering};
static INTERRUPTED: AtomicI32 = AtomicI32::new(0);
extern "C" fn interrupted(number: libc::c_int) {
    INTERRUPTED.store(number, Ordering::SeqCst);
}
pub fn install_interrupts() {
    // SAFETY: the handler only writes a lock-free atomic and has C ABI.
    unsafe {
        libc::signal(
            libc::SIGTERM,
            interrupted as *const () as libc::sighandler_t,
        );
        libc::signal(libc::SIGINT, interrupted as *const () as libc::sighandler_t);
    }
}
pub fn interruption() -> i32 {
    INTERRUPTED.load(Ordering::SeqCst)
}
pub(crate) fn signal_group(child: &Child, number: i32) {
    // A prior EOF path may already have reaped the provider. Never signal a
    // numeric group ID whose ownership can no longer be established.
    let mut info = std::mem::MaybeUninit::<libc::siginfo_t>::zeroed();
    // SAFETY: info is writable; WNOWAIT explicitly preserves the owned child.
    if unsafe {
        libc::waitid(
            libc::P_PID,
            child.id(),
            info.as_mut_ptr(),
            libc::WEXITED | libc::WNOHANG | libc::WNOWAIT,
        )
    } != 0
    {
        return;
    }
    // SAFETY: spawn created this child's own process group. Called before its
    // owner finishes cleanup; never signals the caller's or an ambient group.
    unsafe {
        libc::kill(-(child.id() as libc::pid_t), number);
    }
}

pub(crate) fn nonblocking(fd: std::os::fd::RawFd) -> io::Result<()> {
    // SAFETY: caller borrows the descriptor from its live owned pipe.
    unsafe {
        let flags = libc::fcntl(fd, libc::F_GETFL);
        if flags < 0 || libc::fcntl(fd, libc::F_SETFL, flags | libc::O_NONBLOCK) < 0 {
            return Err(io::Error::last_os_error());
        }
    }
    Ok(())
}
pub(crate) fn poll(fds: &mut [libc::pollfd], millis: i32) -> io::Result<()> {
    // SAFETY: the slice is writable for its length; callers retain descriptor ownership.
    if unsafe { libc::poll(fds.as_mut_ptr(), fds.len() as _, millis) } < 0 {
        let error = io::Error::last_os_error();
        if error.kind() != io::ErrorKind::Interrupted {
            return Err(error);
        }
    }
    Ok(())
}

pub(crate) fn available(fd: std::os::fd::RawFd) -> io::Result<usize> {
    let mut bytes: libc::c_int = 0;
    // SAFETY: fd is borrowed from a live owned pipe, bytes is writable.
    if unsafe { libc::ioctl(fd, libc::FIONREAD, &mut bytes) } < 0 {
        return Err(io::Error::last_os_error());
    }
    Ok(bytes.max(0) as usize)
}
#[cfg(test)]
mod tests {
    use super::*;
    use std::{
        io::Read,
        path::PathBuf,
        process::{Command, Stdio},
        time::{Duration, Instant},
    };

    struct OwnedChild(Child);
    impl Drop for OwnedChild {
        fn drop(&mut self) {
            let _ = self.0.kill();
            let _ = self.0.wait();
        }
    }

    #[test]
    fn termination_delivers_sigterm_to_the_started_child() {
        let scratch = std::env::var_os("MIR_NATIVE_TEST_SCRATCH")
            .map(PathBuf::from)
            .unwrap_or_else(|| {
                PathBuf::from(env!("CARGO_MANIFEST_DIR"))
                    .join("target/mig-scratch/sd-yoke-execute-direct")
            });
        std::fs::create_dir_all(&scratch).unwrap();
        let root = tempfile::tempdir_in(scratch).unwrap();
        let mut child = OwnedChild(
            Command::new("/bin/sh")
                .args(["-c", "trap 'exit 23' TERM; printf 'ready\\n'; read unused"])
                .current_dir(root.path())
                .stdin(Stdio::piped())
                .stdout(Stdio::piped())
                .spawn()
                .unwrap(),
        );
        let mut ready = [0; 6];
        child
            .0
            .stdout
            .take()
            .unwrap()
            .read_exact(&mut ready)
            .unwrap();
        assert_eq!(&ready, b"ready\n");
        terminate_owned_child(&mut child.0).unwrap();
        let deadline = Instant::now() + Duration::from_secs(2);
        let status = loop {
            if let Some(status) = child.0.try_wait().unwrap() {
                break status;
            }
            assert!(
                Instant::now() < deadline,
                "synthetic child did not terminate"
            );
            std::thread::sleep(Duration::from_millis(5));
        };
        assert_eq!(status.code(), Some(23));
    }
}
