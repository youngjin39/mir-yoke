use crate::{OUTPUT, wire};
use std::ffi::OsString;
use std::io::{Read, Write};
use std::process::{Command, Stdio};
use std::sync::mpsc;
use std::thread;
use std::time::{Duration, Instant};
pub struct Forward {
    pub python: OsString,
    pub script: OsString,
}
impl Forward {
    // One child, one deadline including spawn/write/read/wait, never retry.
    pub fn call(&self, raw: &[u8]) -> Result<Vec<u8>, &'static str> {
        let deadline = Instant::now() + Duration::from_secs(10);
        let mut child = Command::new(&self.python)
            .args(["-I", "-B", "-u"])
            .arg(&self.script)
            .arg("--internal-reference")
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
            // A non-reading child must not block the protocol thread's deadline.
            let mut payload = raw.to_vec();
            if !payload.ends_with(b"\n") {
                payload.push(b'\n');
            }
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
        }
        let _ = child.wait();
        result
    }
}
