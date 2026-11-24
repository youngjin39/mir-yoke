use crate::{OUTPUT, wire};
use std::ffi::OsString;
use std::io::{Read, Write};
use std::process::{Child, Command, Stdio};
use std::sync::mpsc;
use std::thread;
use std::time::{Duration, Instant};

const REAP_GRACE: Duration = Duration::from_millis(25);

pub struct Forward {
    pub python: OsString,
    pub script: OsString,
}

impl Forward {
    // Native dispatch and semantic fallback share the caller's execution
    // deadline, including child spawn, pipe I/O, and exit.
    pub fn call(&self, raw: &[u8], deadline: Instant) -> Result<Vec<u8>, &'static str> {
        let mut command = Command::new(&self.python);
        command
            .args(["-I", "-B", "-u"])
            .arg(&self.script)
            .arg("--internal-reference");
        Self::capture(command, raw, deadline)
    }
    pub fn native(raw: &[u8], deadline: Instant) -> Result<Vec<u8>, &'static str> {
        let mut command = Command::new(std::env::current_exe().map_err(|_| "E_IO")?);
        command.arg("--internal-native");
        Self::capture(command, raw, deadline)
    }
    fn capture(
        mut command: Command,
        raw: &[u8],
        deadline: Instant,
    ) -> Result<Vec<u8>, &'static str> {
        if Instant::now() >= deadline {
            return Err("E_TIMEOUT");
        }
        let mut child = command
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .map_err(|_| "E_IO")?;
        let result = (|| {
            let stdin = child.stdin.take().ok_or("E_IO")?;
            let stdout = child.stdout.take().ok_or("E_IO")?;
            let stderr = child.stderr.take().ok_or("E_IO")?;
            let (tx, rx) = mpsc::channel();
            for (is_stdout, pipe) in [
                (true, Box::new(stdout) as Box<dyn Read + Send>),
                (false, Box::new(stderr) as Box<dyn Read + Send>),
            ] {
                let tx = tx.clone();
                thread::spawn(move || {
                    let mut bytes = Vec::new();
                    let result = pipe.take((OUTPUT + 1) as u64).read_to_end(&mut bytes);
                    let _ = tx.send((is_stdout, result, bytes));
                });
            }
            // Close stdin after writing the frame unchanged so an unterminated
            // final frame is delimited by EOF. Write off the protocol thread.
            let payload = raw.to_vec();
            thread::spawn(move || {
                let mut stdin = stdin;
                let _ = stdin.write_all(&payload);
            });
            let mut output = Vec::new();
            for _ in 0..2 {
                let wait = deadline.saturating_duration_since(Instant::now());
                let (out, read, bytes) = rx.recv_timeout(wait).map_err(|_| "E_TIMEOUT")?;
                read.map_err(|_| "E_IO")?;
                if bytes.len() > OUTPUT {
                    return Err("E_LIMIT");
                }
                if out {
                    output = bytes;
                } else if !bytes.is_empty() {
                    return Err("E_IO");
                }
            }
            loop {
                if let Some(status) = child.try_wait().map_err(|_| "E_IO")? {
                    if !status.success() {
                        return Err("E_IO");
                    }
                    break;
                }
                if Instant::now() >= deadline {
                    return Err("E_TIMEOUT");
                }
                thread::sleep(Duration::from_millis(1));
            }
            let value = wire::parse(&output)?;
            if !value.is_object() || !output.ends_with(b"\n") {
                return Err("E_FORMAT");
            }
            Ok(output)
        })();
        if result.is_err() {
            let _ = child.kill();
            reap_after_kill(child);
        }
        result
    }
}

fn reap_after_kill(mut child: Child) {
    let deadline = Instant::now() + REAP_GRACE;
    loop {
        match child.try_wait() {
            Ok(Some(_)) => return,
            Ok(None) => {
                let remaining = deadline.saturating_duration_since(Instant::now());
                if remaining.is_zero() {
                    break;
                }
                thread::sleep(remaining.min(Duration::from_millis(1)));
            }
            Err(_) => break,
        }
    }
    // A child blocked in kernel I/O can outlive the grace period.
    let _ = thread::Builder::new().spawn(move || {
        let _ = child.wait();
    });
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn expired_call_deadline_never_spawns_another_child() {
        let command = Command::new("nonexistent-reference-must-not-run");
        assert_eq!(
            Forward::capture(command, b"{}\n", Instant::now()),
            Err("E_TIMEOUT")
        );
    }

    #[cfg(unix)]
    #[test]
    fn capture_times_out_when_child_ignores_input() {
        let mut command = Command::new("sleep");
        command.arg("60");
        let deadline = Instant::now() + Duration::from_millis(50);
        assert_eq!(
            Forward::capture(command, &[b' '; crate::FRAME], deadline),
            Err("E_TIMEOUT")
        );
        let scheduler_slack = Duration::from_millis(500);
        assert!(Instant::now() <= deadline + REAP_GRACE + scheduler_slack);
    }

    #[cfg(unix)]
    #[test]
    fn reap_returns_when_a_child_is_still_running() -> std::io::Result<()> {
        let start = Instant::now();
        // Model a killed worker that has not exited by keeping this child alive.
        let child = Command::new("sleep").arg("2").spawn()?;
        let pid = child.id().to_string();
        assert!(process_exists(&pid)?);
        reap_after_kill(child);
        assert!(start.elapsed() < Duration::from_secs(1));
        assert_reaped(&pid, Duration::from_secs(3))
    }

    #[cfg(unix)]
    #[test]
    fn reap_collects_a_killed_child() -> std::io::Result<()> {
        let mut child = Command::new("sleep").arg("60").spawn()?;
        let pid = child.id().to_string();
        assert!(process_exists(&pid)?);
        child.kill()?;
        reap_after_kill(child);
        assert_reaped(&pid, Duration::from_secs(1))
    }

    #[cfg(unix)]
    fn assert_reaped(pid: &str, timeout: Duration) -> std::io::Result<()> {
        let deadline = Instant::now() + timeout;
        while process_exists(pid)? {
            assert!(Instant::now() < deadline, "child {pid} was not reaped");
            thread::sleep(Duration::from_millis(50));
        }
        Ok(())
    }

    #[cfg(unix)]
    fn process_exists(pid: &str) -> std::io::Result<bool> {
        // Signal zero probes the process table without affecting the child.
        Ok(Command::new("sh")
            .args(["-c", "kill -0 \"$1\"", "probe-child", pid])
            .stderr(Stdio::null())
            .status()?
            .success())
    }
}
