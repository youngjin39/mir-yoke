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
    time::{Duration, Instant},
};

pub const PROTOCOL: &str = "mir-executor.hooks@1";
pub const MAX_FRAME_BYTES: usize = 1024 * 1024;
pub const MAX_JSON_DEPTH: usize = 64;
pub const DEFAULT_TIMEOUT: Duration = Duration::from_secs(10);
type Result<T> = std::result::Result<T, BridgeError>;

// Temporary startup/transport diagnostics; never part of the hook wire protocol.
struct PhaseProbe(Option<(&'static str, Instant)>);
impl PhaseProbe {
    fn new(phase: &'static str) -> Self {
        Self(
            (std::env::var_os("MIR_HOOK_PHASE_PROBE").as_deref() == Some("1".as_ref()))
                .then(|| (phase, Instant::now())),
        )
    }
}
impl Drop for PhaseProbe {
    fn drop(&mut self) {
        if let Some((phase, start)) = self.0 {
            // A diagnostic write failure must not change transport behavior.
            let _ = writeln!(
                std::io::stderr().lock(),
                "mir-hook phase={phase} elapsed_ns={}",
                start.elapsed().as_nanos()
            );
        }
    }
}

#[derive(Debug)]
struct HookResponse {
    value: Value,
    strings: BTreeMap<Vec<String>, Vec<u32>>,
}

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
    responses: Receiver<Result<HookResponse>>,
    response_strings: BTreeMap<Vec<String>, Vec<u32>>,
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
        let validation = PhaseProbe::new("validation/canonicalisation");
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
        let is_file = path.is_file();
        drop(validation);
        let valid_pin = is_file && {
            let read = PhaseProbe::new("executable-read");
            let bytes = fs::read(&path)?;
            drop(read);
            let _sha = PhaseProbe::new("sha256");
            crate::digest::sha256(&bytes).eq_ignore_ascii_case(&config.sha256)
        };
        if !valid_pin {
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
            let _phase = PhaseProbe::new("process-job");
            use std::os::windows::process::CommandExt;
            // Assign the suspended process before any target code can spawn.
            command.creation_flags(0x00000004 | 0x00000200);
            crate::executor_hooks_windows::ProcessJob::new()?
        };
        let mut child = {
            let _phase = PhaseProbe::new("spawn");
            command.spawn()?
        };
        #[cfg(windows)]
        {
            let _phase = PhaseProbe::new("assignment/resume");
            if let Err(error) = job.assign_and_resume(&child) {
                drop(job);
                let _ = child.kill();
                let _ = child.wait();
                return Err(error.into());
            }
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
            response_strings: BTreeMap::new(),
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
    pub(crate) fn response_string(&self, path: &[&str]) -> Option<&[u32]> {
        self.response_strings
            .get(
                &path
                    .iter()
                    .map(|part| (*part).to_owned())
                    .collect::<Vec<_>>(),
            )
            .map(Vec::as_slice)
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
        let mut frame = request_frame(&request)?;
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
        let result = {
            let _phase = PhaseProbe::new("receive");
            match self.responses.recv_timeout(self.timeout) {
                Ok(result) => result,
                Err(mpsc::RecvTimeoutError::Timeout) => Err(BridgeError::Timeout),
                Err(mpsc::RecvTimeoutError::Disconnected) => Err(BridgeError::Closed),
            }
        };
        if result.is_err() {
            self.close();
        }
        result.map(|response| {
            self.response_strings = response.strings;
            response.value
        })
    }
    pub fn close(&mut self) {
        if self.closed {
            return;
        }
        let _phase = PhaseProbe::new("close");
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

// Only parser-owned numeric slots and path slots can contain typed scalars.
// Target-owned dictionaries and strings elsewhere remain ordinary JSON.
fn request_frame(request: &Value) -> Result<Vec<u8>> {
    fn append(value: &Value, path: &mut Vec<String>, out: &mut Vec<u32>) -> Result<()> {
        let numeric = path.len() == 4
            && path[..3] == ["params", "payload", "args"]
            && matches!(
                path[3].as_str(),
                "timeout" | "stall_timeout" | "max_codex_attempts" | "finalize_lock_timeout"
            );
        let path_slot = (path.len() == 2
            && path[0] == "params"
            && matches!(path[1].as_str(), "cwd" | "repo_root" | "token"))
            || (path.len() == 3
                && path[..2] == ["params", "payload"]
                && matches!(path[2].as_str(), "repo_root" | "jobs_db"))
            || (path.len() == 4
                && path[..3] == ["params", "payload", "args"]
                && matches!(
                    path[3].as_str(),
                    "repo_root"
                        | "jobs_db"
                        | "codex_args_file"
                        | "artifacts_dir"
                        | "dispatch_brief"
                ));
        if let Some(fields) = value.as_object().filter(|fields| fields.len() == 1) {
            if numeric && fields.contains_key("__native_float") {
                return Err(BridgeError::Configuration(
                    "NativeHookError: nonfinite native hook number".into(),
                ));
            }
            if numeric && let Some(raw) = fields.get("__native_integer").and_then(Value::as_str) {
                let valid = crate::python_json::parse(raw).is_ok_and(|value| matches!(value, crate::python_json::Value::Number(number) if number.is_integer()));
                if !valid {
                    return Err(BridgeError::Protocol("invalid native hook integer"));
                }
                out.extend(raw.chars().map(u32::from));
                return Ok(());
            }
            if path_slot && let Some(raw) = fields.get("__native_string").and_then(Value::as_array)
            {
                let points = raw
                    .iter()
                    .map(|point| {
                        point
                            .as_u64()
                            .and_then(|point| u32::try_from(point).ok())
                            .filter(|point| *point <= 0x10ffff)
                    })
                    .collect::<Option<Vec<_>>>()
                    .ok_or(BridgeError::Protocol("invalid native hook string"))?;
                out.extend(crate::executor_text::json_quote_points(&points));
                return Ok(());
            }
        }
        match value {
            Value::Object(fields) => {
                out.push(123);
                let mut fields = fields.iter().collect::<Vec<_>>();
                fields.sort_by_key(|(key, _)| *key);
                for (index, (key, value)) in fields.into_iter().enumerate() {
                    if index > 0 {
                        out.push(44);
                    }
                    out.extend(crate::executor_text::json_quote_points(
                        &key.chars().map(u32::from).collect::<Vec<_>>(),
                    ));
                    out.push(58);
                    path.push(key.clone());
                    append(value, path, out)?;
                    path.pop();
                }
                out.push(125);
            }
            Value::Array(items) => {
                out.push(91);
                for (index, value) in items.iter().enumerate() {
                    if index > 0 {
                        out.push(44);
                    }
                    path.push(index.to_string());
                    append(value, path, out)?;
                    path.pop();
                }
                out.push(93);
            }
            Value::String(text) => out.extend(crate::executor_text::json_quote_points(
                &text.chars().map(u32::from).collect::<Vec<_>>(),
            )),
            _ => out.extend(value.to_string().chars().map(u32::from)),
        }
        Ok(())
    }
    let mut points = vec![];
    append(request, &mut vec![], &mut points)?;
    if let Some(start) = points
        .iter()
        .position(|point| (0xd800..=0xdfff).contains(point))
    {
        let end = start
            + points[start..]
                .iter()
                .take_while(|point| (0xd800..=0xdfff).contains(*point))
                .count();
        return Err(BridgeError::Configuration(
            crate::executor_text::encode_error(
                "utf-8",
                &points,
                start,
                end,
                "surrogates not allowed",
            ),
        ));
    }
    Ok(points
        .into_iter()
        .filter_map(char::from_u32)
        .collect::<String>()
        .into_bytes())
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
fn send_frame(reader: &mut impl BufRead, outgoing: &Sender<Result<HookResponse>>) -> bool {
    let result = read_frame(reader);
    let keep_reading = result.is_ok();
    outgoing.send(result).is_ok() && keep_reading
}
fn read_frame(reader: &mut impl BufRead) -> Result<HookResponse> {
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
    match serde_json::from_slice(&frame) {
        Ok(value) => {
            validate_value(&value)?;
            Ok(HookResponse {
                value,
                strings: BTreeMap::new(),
            })
        }
        Err(error)
            if [
                "number out of range",
                "lone leading surrogate in hex escape",
                "unexpected end of hex escape",
                "invalid unicode code point",
            ]
            .iter()
            .any(|message| error.to_string().starts_with(message)) =>
        {
            numeric_response(&frame, error)
        }
        Err(error) => Err(error.into()),
    }
}

// A direct hook consumes envelope fields and writer tokens, while numeric result
// extras stay opaque. Preserve oversized integers without coercing them into an
// envelope id or interpreting a target-owned dictionary as an internal scalar.
fn numeric_response(frame: &[u8], original: serde_json::Error) -> Result<HookResponse> {
    use crate::python_json::Value as Python;
    let Ok(text) = std::str::from_utf8(frame) else {
        return Err(original.into());
    };
    let value = crate::python_json::parse(text)
        .map_err(|error| BridgeError::Configuration(format!("NativeHookError: {error}")))?;
    let mut pending = vec![(&value, 0)];
    while let Some((item, depth)) = pending.pop() {
        if depth > MAX_JSON_DEPTH
            || (depth >= MAX_JSON_DEPTH && matches!(item, Python::Object(_) | Python::Array(_)))
        {
            return Err(BridgeError::Protocol(
                "native hook JSON depth exceeds limit",
            ));
        }
        match item {
            Python::Object(fields) => {
                for (_, value) in fields.iter() {
                    pending.push((value, depth + 1));
                }
            }
            Python::Array(items) => pending.extend(items.iter().map(|item| (item, depth + 1))),
            Python::Number(number)
                if !number.is_integer()
                    && number
                        .token
                        .parse::<f64>()
                        .is_ok_and(|number| !number.is_finite()) =>
            {
                return Err(BridgeError::Configuration(
                    "NativeHookError: nonfinite native hook number".into(),
                ));
            }
            _ => (),
        }
    }
    fn convert(
        value: Python,
        path: &mut Vec<String>,
        strings: &mut BTreeMap<Vec<String>, Vec<u32>>,
    ) -> Result<Value> {
        Ok(match value {
            Python::Null => Value::Null,
            Python::Bool(value) => Value::Bool(value),
            Python::String(text) => {
                if text.has_surrogates() {
                    strings.insert(path.clone(), text.codepoints.clone());
                }
                Value::String(text.py_str())
            }
            Python::Number(number)
                if number.is_integer()
                    && number.token.parse::<i64>().is_err()
                    && number.token.parse::<u64>().is_err() =>
            {
                json!({"__native_hook_integer":number.token})
            }
            Python::Number(number) => Value::Number(number.token.parse()?),
            Python::Array(items) => Value::Array(
                items
                    .into_iter()
                    .enumerate()
                    .map(|(index, value)| {
                        path.push(index.to_string());
                        let value = convert(value, path, strings);
                        path.pop();
                        value
                    })
                    .collect::<Result<_>>()?,
            ),
            Python::Object(fields) => Value::Object(
                fields
                    .into_entries()
                    .into_iter()
                    .map(|(key, value)| {
                        let key = key.py_str();
                        path.push(key.clone());
                        let value = convert(value, path, strings);
                        path.pop();
                        Ok((key, value?))
                    })
                    .collect::<Result<_>>()?,
            ),
        })
    }
    let mut strings = BTreeMap::new();
    let value = convert(value, &mut vec![], &mut strings)?;
    Ok(HookResponse { value, strings })
}

#[cfg(test)]
#[path = "executor_hooks_numeric_tests.rs"]
mod numeric_tests;

#[cfg(test)]
#[path = "executor_hooks_surrogate_tests.rs"]
mod surrogate_tests;
