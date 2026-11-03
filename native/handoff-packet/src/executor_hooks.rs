//! Pinned target-owned persistent executable hooks. Unknown envelope fields are
//! tolerated for forward-compatible diagnostics; required fields remain strict.
use crate::local_bridge::BridgeError;
use serde_json::{Value, json};
use std::{
    collections::{BTreeMap, BTreeSet},
    ffi::OsString,
    fs,
    io::{BufRead, BufReader, Write},
    path::{Component, Path},
    process::{Child, Command, Stdio},
    sync::mpsc::{self, Receiver, Sender},
    thread::{self, JoinHandle},
    time::Duration,
};

pub const PROTOCOL: &str = "mir-executor.hooks@1";
pub const MAX_FRAME_BYTES: usize = 1024 * 1024;
pub const MAX_JSON_DEPTH: usize = 64;
pub const DEFAULT_TIMEOUT: Duration = Duration::from_secs(10);
type Result<T> = std::result::Result<T, BridgeError>;

#[derive(Clone, Debug)]
pub struct HooksConfig {
    pub executable: String,
    pub argv: Vec<String>,
    pub sha256: String,
    pub hooks: Vec<String>,
}

#[derive(Debug)]
pub struct HookSession {
    child: Child,
    requests: Option<Sender<Vec<u8>>>,
    responses: Receiver<Result<Value>>,
    worker: Option<JoinHandle<()>>,
    hooks: Vec<String>,
    next_id: u64,
    timeout: Duration,
    closed: bool,
    #[cfg(windows)]
    job: Option<crate::executor_hooks_windows::ProcessJob>,
}

impl HookSession {
    pub fn start(root: &Path, cwd: &Path, config: &HooksConfig) -> Result<Self> {
        Self::start_with_timeout(root, cwd, config, DEFAULT_TIMEOUT)
    }
    pub fn start_with_timeout(
        root: &Path,
        cwd: &Path,
        config: &HooksConfig,
        timeout: Duration,
    ) -> Result<Self> {
        Self::spawn(root, cwd, config, None, timeout)
    }
    /// An explicitly supplied environment is the complete child environment.
    pub fn start_in_environment(
        root: &Path,
        cwd: &Path,
        config: &HooksConfig,
        environment: &BTreeMap<OsString, OsString>,
        timeout: Duration,
    ) -> Result<Self> {
        Self::spawn(root, cwd, config, Some(environment), timeout)
    }
    fn spawn(
        root: &Path,
        cwd: &Path,
        config: &HooksConfig,
        environment: Option<&BTreeMap<OsString, OsString>>,
        timeout: Duration,
    ) -> Result<Self> {
        let executable = Path::new(&config.executable);
        let expected: BTreeSet<&str> = config.hooks.iter().map(String::as_str).collect();
        if !root.is_absolute()
            || !cwd.is_absolute()
            || executable.as_os_str().is_empty()
            || executable
                .components()
                .any(|c| !matches!(c, Component::Normal(_)))
            || config.sha256.len() != 64
            || !config.sha256.bytes().all(|b| b.is_ascii_hexdigit())
            || expected.len() != config.hooks.len()
            || expected.is_empty()
            || expected
                .iter()
                .any(|h| !matches!(*h, "writer_scope" | "on_job_event"))
        {
            return Err(BridgeError::Configuration(
                "invalid native hook configuration".into(),
            ));
        }
        let root = fs::canonicalize(root)?;
        let mut path = root.clone();
        for component in executable.components() {
            path.push(component);
            if fs::symlink_metadata(&path)?.file_type().is_symlink() {
                return Err(BridgeError::Configuration(
                    "native hook path contains a symlink".into(),
                ));
            }
        }
        if !path.is_file()
            || !crate::digest::sha256(&fs::read(&path)?).eq_ignore_ascii_case(&config.sha256)
        {
            return Err(BridgeError::Configuration(
                "native hook executable SHA-256 mismatch".into(),
            ));
        }
        let mut command = Command::new(path);
        command
            .args(&config.argv)
            .current_dir(cwd)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::inherit());
        if let Some(environment) = environment {
            command.env_clear().envs(environment);
        }
        #[cfg(unix)]
        {
            use std::os::unix::process::CommandExt;
            command.process_group(0);
        }
        #[cfg(windows)]
        let job = {
            use std::os::windows::process::CommandExt;
            // Assign the suspended process before any target code can spawn.
            command.creation_flags(0x00000004 | 0x00000200);
            crate::executor_hooks_windows::ProcessJob::new()?
        };
        let mut child = command.spawn()?;
        #[cfg(windows)]
        if let Err(error) = job.assign_and_resume(&child) {
            drop(job);
            let _ = child.kill();
            let _ = child.wait();
            return Err(error.into());
        }
        let Some(mut stdin) = child.stdin.take() else {
            stop_tree(&mut child);
            return Err(BridgeError::Protocol("missing hook stdin"));
        };
        let Some(stdout) = child.stdout.take() else {
            stop_tree(&mut child);
            return Err(BridgeError::Protocol("missing hook stdout"));
        };
        let (requests, incoming) = mpsc::channel::<Vec<u8>>();
        let (outgoing, responses) = mpsc::channel();
        let worker = thread::spawn(move || {
            let mut reader = BufReader::new(stdout);
            if !send_frame(&mut reader, &outgoing) {
                return;
            }
            for frame in incoming {
                if let Err(error) = stdin.write_all(&frame).and_then(|()| stdin.flush()) {
                    let _ = outgoing.send(Err(error.into()));
                    return;
                }
                if !send_frame(&mut reader, &outgoing) {
                    return;
                }
            }
        });
        let mut session = Self {
            child,
            requests: Some(requests),
            responses,
            worker: Some(worker),
            hooks: config.hooks.clone(),
            next_id: 1,
            timeout,
            closed: false,
            #[cfg(windows)]
            job: Some(job),
        };
        let hello = session.receive()?;
        let actual = hello
            .get("hooks")
            .and_then(Value::as_array)
            .and_then(|hooks| hooks.iter().map(Value::as_str).collect::<Option<Vec<_>>>());
        if hello.get("version").and_then(Value::as_str) != Some(PROTOCOL)
            || actual.as_ref().is_none_or(|hooks| {
                hooks.len() != expected.len()
                    || hooks.iter().copied().collect::<BTreeSet<_>>() != expected
            })
        {
            session.close();
            return Err(BridgeError::Protocol("invalid native hook hello"));
        }
        Ok(session)
    }
    pub fn serves(&self, name: &str) -> bool {
        self.hooks.iter().any(|hook| hook == name)
    }
    /// Preserves the complete reply, including target-owned errors and tokens.
    pub fn call(&mut self, hook: &str, params: Value) -> Result<Value> {
        if self.closed {
            return Err(BridgeError::Closed);
        }
        let result = self.exchange(hook, params);
        if result.is_err() {
            self.close();
        }
        result
    }
    fn exchange(&mut self, hook: &str, params: Value) -> Result<Value> {
        if !self.serves(hook)
            && !(matches!(hook, "writer_enter" | "writer_exit") && self.serves("writer_scope"))
        {
            return Err(BridgeError::Protocol("unserved native hook"));
        }
        validate_value(&params)?;
        let id = self.next_id;
        self.next_id = id
            .checked_add(1)
            .ok_or(BridgeError::Protocol("request id exhausted"))?;
        let request = json!({"version":PROTOCOL,"id":id,"hook":hook,"params":params});
        validate_value(&request)?;
        let mut frame = serde_json::to_vec(&request)?;
        if frame.len() >= MAX_FRAME_BYTES {
            return Err(BridgeError::FrameTooLarge);
        }
        frame.push(b'\n');
        self.requests
            .as_ref()
            .ok_or(BridgeError::Closed)?
            .send(frame)
            .map_err(|_| BridgeError::Closed)?;
        let response = self.receive()?;
        if response.get("version").and_then(Value::as_str) != Some(PROTOCOL)
            || response.get("id").and_then(Value::as_u64) != Some(id)
            || !response.get("ok").is_some_and(Value::is_boolean)
            || (response["ok"] == true && response.get("result").is_none())
            || (response["ok"] == false
                && (!response["error"]["type"].is_string()
                    || !response["error"]["message"].is_string()))
        {
            return Err(BridgeError::Protocol("invalid native hook response"));
        }
        Ok(response)
    }
    fn receive(&mut self) -> Result<Value> {
        let result = match self.responses.recv_timeout(self.timeout) {
            Ok(result) => result,
            Err(mpsc::RecvTimeoutError::Timeout) => Err(BridgeError::Timeout),
            Err(mpsc::RecvTimeoutError::Disconnected) => Err(BridgeError::Closed),
        };
        if result.is_err() {
            self.close();
        }
        result
    }
    pub fn close(&mut self) {
        if self.closed {
            return;
        }
        self.closed = true;
        self.requests.take();
        #[cfg(windows)]
        self.job.take();
        stop_tree(&mut self.child);
        // Pipes held outside the owned tree must never make cleanup unbounded.
        if self
            .worker
            .as_ref()
            .is_some_and(|worker| worker.is_finished())
            && let Some(worker) = self.worker.take()
        {
            let _ = worker.join();
        }
    }
}
impl Drop for HookSession {
    fn drop(&mut self) {
        self.close();
    }
}

fn stop_tree(child: &mut Child) {
    #[cfg(unix)]
    {
        let _ = Command::new("/bin/kill")
            .args(["-KILL", "--", &format!("-{}", child.id())])
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status();
    }
    let _ = child.kill();
    let _ = child.wait();
}
fn validate_value(value: &Value) -> Result<()> {
    let mut pending = vec![(value, 0)];
    while let Some((value, depth)) = pending.pop() {
        if depth > MAX_JSON_DEPTH {
            return Err(BridgeError::Protocol(
                "native hook JSON depth exceeds limit",
            ));
        }
        match value {
            Value::Array(values) => {
                if depth >= MAX_JSON_DEPTH {
                    return Err(BridgeError::Protocol(
                        "native hook JSON depth exceeds limit",
                    ));
                }
                pending.extend(values.iter().map(|v| (v, depth + 1)));
            }
            Value::Object(values) => {
                if depth >= MAX_JSON_DEPTH {
                    return Err(BridgeError::Protocol(
                        "native hook JSON depth exceeds limit",
                    ));
                }
                pending.extend(values.values().map(|v| (v, depth + 1)));
            }
            Value::Number(number) if number.as_f64().is_some_and(|v| !v.is_finite()) => {
                return Err(BridgeError::Protocol("nonfinite native hook number"));
            }
            _ => {}
        }
    }
    Ok(())
}
fn send_frame(reader: &mut impl BufRead, outgoing: &Sender<Result<Value>>) -> bool {
    let result = read_frame(reader);
    let keep_reading = result.is_ok();
    outgoing.send(result).is_ok() && keep_reading
}
fn read_frame(reader: &mut impl BufRead) -> Result<Value> {
    let mut frame = Vec::new();
    loop {
        let available = reader.fill_buf()?;
        if available.is_empty() {
            return Err(BridgeError::Protocol("unexpected end of native hook frame"));
        }
        let newline = available.iter().position(|b| *b == b'\n');
        let size = newline.unwrap_or(available.len());
        if frame.len() + size >= MAX_FRAME_BYTES {
            return Err(BridgeError::FrameTooLarge);
        }
        frame.extend_from_slice(&available[..size]);
        reader.consume(size + usize::from(newline.is_some()));
        if newline.is_some() {
            break;
        }
    }
    // Bound nesting before serde allocates or recursively parses untrusted JSON.
    let (mut depth, mut quoted, mut escape) = (0_usize, false, false);
    for byte in &frame {
        if quoted {
            if escape {
                escape = false;
            } else if *byte == b'\\' {
                escape = true;
            } else if *byte == b'"' {
                quoted = false;
            }
        } else {
            match byte {
                b'"' => quoted = true,
                b'[' | b'{' => {
                    depth += 1;
                    if depth > MAX_JSON_DEPTH {
                        return Err(BridgeError::Protocol(
                            "native hook JSON depth exceeds limit",
                        ));
                    }
                }
                b']' | b'}' => depth = depth.saturating_sub(1),
                _ => {}
            }
        }
    }
    let value = serde_json::from_slice(&frame)?;
    validate_value(&value)?;
    Ok(value)
}
