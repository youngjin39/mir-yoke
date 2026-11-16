//! Offline-testable app-server transport. No executable selection or CLI wiring.
//! Unix pipe reads and frame handling belong to the deadline-driven request owner.
//! Unknown provider fields and unissued response IDs are intentionally tolerated.
use serde_json::{Value, json};
use std::{
    collections::BTreeMap,
    io::Write,
    process::{Child, Command, Stdio},
    sync::{
        Arc, Mutex,
        atomic::{AtomicBool, Ordering},
        mpsc::{self, Receiver, Sender},
    },
    thread::{self, JoinHandle},
    time::{Duration, Instant},
};

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Error {
    Process(String),
    Spawn {
        message: String,
        kind: std::io::ErrorKind,
        raw_os_error: Option<i32>,
    },
    Protocol(String),
    Timeout(String),
    Stall(String),
    Callback(String),
    Encoding(String),
}
impl Error {
    pub fn python_class(&self) -> &'static str {
        match self {
            Self::Process(_) | Self::Spawn { .. } => "CodexMcpProcessError",
            Self::Protocol(_) => "CodexMcpProtocolError",
            Self::Timeout(_) => "CodexMcpTimeoutError",
            Self::Stall(_) => "CodexMcpStallError",
            Self::Callback(_) => "CodexMcpError",
            Self::Encoding(_) => "UnicodeEncodeError",
        }
    }
}
impl std::fmt::Display for Error {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Spawn { message: s, .. }
            | Self::Process(s)
            | Self::Protocol(s)
            | Self::Timeout(s)
            | Self::Stall(s)
            | Self::Callback(s)
            | Self::Encoding(s) => f.write_str(s),
        }
    }
}
impl std::error::Error for Error {}
impl From<std::io::Error> for Error {
    fn from(error: std::io::Error) -> Self {
        Self::Spawn {
            message: error.to_string(),
            kind: error.kind(),
            raw_os_error: error.raw_os_error(),
        }
    }
}
type Result<T> = std::result::Result<T, Error>;
fn protocol(s: impl Into<String>) -> Error {
    Error::Protocol(s.into())
}
fn process(s: impl Into<String>) -> Error {
    Error::Process(s.into())
}

#[derive(Clone)]
pub struct Cancellation(Arc<AtomicBool>);
impl Cancellation {
    /// The waiting caller terminates and reaps the child before returning.
    pub fn cancel(&self) {
        self.0.store(true, Ordering::SeqCst);
    }
}
pub struct CallOptions {
    pub prompt: String,
    pub cwd: String,
    pub sandbox: String,
    pub approval_policy: String,
    pub model: Option<String>,
    pub base_instructions: Option<String>,
    pub config: Option<Value>,
    pub timeout: Option<Duration>,
    pub stall_timeout: Option<Duration>,
    /// The CLI accepts Python floats including NaN and infinities.
    pub stall_timeout_float: Option<f64>,
    /// POSIX surrogateescape input, kept outside serde's Unicode-only strings.
    pub string_codepoints: BTreeMap<&'static str, Vec<u32>>,
    /// A platform condition-wait failure occurs after queuing thread/start.
    pub wait_error: Option<&'static str>,
}
impl CallOptions {
    pub fn new(prompt: impl Into<String>, cwd: impl Into<String>) -> Self {
        Self {
            prompt: prompt.into(),
            cwd: cwd.into(),
            sandbox: "danger-full-access".into(),
            approval_policy: "never".into(),
            model: None,
            base_instructions: None,
            config: None,
            timeout: None,
            stall_timeout: None,
            stall_timeout_float: None,
            string_codepoints: BTreeMap::new(),
            wait_error: None,
        }
    }
}
#[derive(Debug)]
pub struct TurnResult {
    pub content_text: String,
    pub thread_id: String,
    pub raw_result: Value,
    pub model_id: Option<String>,
    pub token_usage: Option<Value>,
    pub tool_version: Option<String>,
}
type Progress<'a> = dyn FnMut(&str, &Value) -> std::result::Result<(), String> + 'a;
#[cfg(not(unix))]
use std::io::{BufRead, BufReader};

enum Event {
    #[cfg(not(unix))]
    Line(String),
    #[cfg(not(unix))]
    Eof,
    #[cfg(not(unix))]
    ReadError(String),
    WriteError,
}
#[derive(Default)]
struct Turn {
    thread: String,
    texts: Vec<(String, String)>,
    usage: Option<Value>,
    completed: Option<Value>,
}
// Until Client owns every pipe/worker, an exit cannot acknowledge effect release.
struct SpawnSetup<'a>(Option<&'a mut dyn FnMut(bool)>);
impl Drop for SpawnSetup<'_> {
    fn drop(&mut self) {
        if let Some(teardown) = self.0.take() {
            teardown(true);
        }
    }
}
/// Serial request owner; Unix stdout/stderr are read only by this owner.
/// Close sends SIGTERM on Unix, then escalates after kill_timeout; Windows uses Child::kill.
/// Descendant-held pipes cannot extend the bounded exit drain.
pub struct Client {
    child: Child,
    #[cfg(unix)]
    stdout: Option<Pipe<std::process::ChildStdout>>,
    #[cfg(unix)]
    stderr_pipe: Option<Pipe<std::process::ChildStderr>>,
    send: Option<Sender<(Value, Option<Sender<()>>)>>,
    events: Receiver<Event>,
    workers: Vec<JoinHandle<()>>,
    stderr: Arc<Mutex<Vec<String>>>,
    malformed: Vec<String>,
    cancel: Cancellation,
    next_id: u64,
    pending: usize,
    activity: Arc<Mutex<Instant>>,
    kill_timeout: Duration,
    tool_version: Option<String>,
    turn: Option<Turn>,
    next_wait_error: Option<&'static str>,
    closed: bool,
    teardown_uncertain: bool,
    #[cfg(all(test, unix))]
    frame_delay: Duration,
}
impl Client {
    /// Spawn the explicit command supplied by the owner and initialize it.
    pub fn spawn(
        command: Command,
        initialize_timeout: Duration,
        kill_timeout: Duration,
    ) -> Result<Self> {
        let mut client = Self::spawn_uninitialized(command, kill_timeout, &mut |_| {})?;
        client.initialize(initialize_timeout)?;
        Ok(client)
    }
    pub(crate) fn spawn_uninitialized(
        mut command: Command,
        kill_timeout: Duration,
        teardown: &mut dyn FnMut(bool),
    ) -> Result<Self> {
        #[cfg(unix)]
        {
            let number = crate::executor_process_unix::interruption();
            if number != 0 {
                return Err(process("Codex app-server client closed"));
            }
        }
        #[cfg(unix)]
        {
            use std::os::unix::process::CommandExt;
            command.process_group(0);
        }
        let mut child = command
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .map_err(Error::from)?;
        let mut setup = SpawnSetup(Some(teardown));
        let stdout = child
            .stdout
            .take()
            .ok_or_else(|| process("Codex app-server stdout is unavailable"))?;
        let stderr = child
            .stderr
            .take()
            .ok_or_else(|| process("Codex app-server stderr is unavailable"))?;
        let mut stdin = child
            .stdin
            .take()
            .ok_or_else(|| process("Codex app-server stdin is unavailable"))?;
        let (tx, events) = mpsc::channel();
        let (send, writes) = mpsc::channel::<(Value, Option<Sender<()>>)>();
        #[cfg(not(unix))]
        let out_tx = tx.clone();
        let activity = Arc::new(Mutex::new(Instant::now()));
        #[cfg(not(unix))]
        let stdout_activity = activity.clone();
        #[cfg(not(unix))]
        let output = thread::spawn(move || {
            for line in BufReader::new(stdout).lines() {
                let event = match line {
                    Ok(s) => {
                        if let Ok(mut at) = stdout_activity.lock() {
                            *at = Instant::now();
                        }
                        Event::Line(s)
                    }
                    Err(e) => Event::ReadError(e.to_string()),
                };
                if out_tx.send(event).is_err() {
                    return;
                }
            }
            let _ = out_tx.send(Event::Eof);
        });
        let stderr_lines = Arc::new(Mutex::new(Vec::new()));
        #[cfg(not(unix))]
        let lines = stderr_lines.clone();
        #[cfg(not(unix))]
        let errors = thread::spawn(move || {
            for line in BufReader::new(stderr).lines() {
                match line {
                    Ok(s) => {
                        if let Ok(mut lines) = lines.lock() {
                            lines.push(s);
                        }
                    }
                    Err(_) => return,
                }
            }
        });
        let writer = thread::spawn(move || {
            for (value, written) in writes {
                if writeln!(stdin, "{value}")
                    .and_then(|()| stdin.flush())
                    .is_err()
                {
                    let _ = tx.send(Event::WriteError);
                    return;
                }
                if let Some(written) = written {
                    let _ = written.send(());
                }
            }
        });
        let client = Self {
            child,
            #[cfg(unix)]
            stdout: Some(Pipe::new(stdout)?),
            #[cfg(unix)]
            stderr_pipe: Some(Pipe::new(stderr)?),
            send: Some(send),
            events,
            #[cfg(not(unix))]
            workers: vec![output, errors, writer],
            #[cfg(unix)]
            workers: vec![writer],
            stderr: stderr_lines,
            malformed: Vec::new(),
            cancel: Cancellation(Arc::new(AtomicBool::new(false))),
            next_id: 1,
            pending: 0,
            activity,
            kill_timeout,
            tool_version: None,
            turn: None,
            next_wait_error: None,
            closed: false,
            teardown_uncertain: false,
            #[cfg(all(test, unix))]
            frame_delay: Duration::ZERO,
        };
        setup.0 = None;
        Ok(client)
    }
    pub(crate) fn initialize(&mut self, initialize_timeout: Duration) -> Result<()> {
        let mut progress = |_: &str, _: &Value| Ok(());
        let initialized = self.request(
            "initialize",
            json!({"capabilities":{},"clientInfo":{"name":"mir_executor","version":"0.1.0"}}),
            Some(initialize_timeout),
            None,
            &mut progress,
        )?;
        self.tool_version = nonempty(&initialized["userAgent"]).map(|s| s.trim().to_owned());
        self.send_flushed(
            json!({"method":"initialized","params":{}}),
            initialize_timeout,
        )?;
        Ok(())
    }
    pub fn cancellation(&self) -> Cancellation {
        self.cancel.clone()
    }
    pub fn pending_count(&self) -> usize {
        self.pending
    }
    pub fn malformed_messages(&self) -> &[String] {
        &self.malformed
    }
    pub fn stderr_lines(&self) -> Vec<String> {
        self.stderr.lock().map(|v| v.clone()).unwrap_or_default()
    }
    pub fn is_running(&mut self) -> bool {
        self.child.try_wait().is_ok_and(|status| status.is_none())
    }
    pub fn teardown_uncertain(&self) -> bool {
        self.teardown_uncertain
    }
    fn check_interruption(&mut self) -> Result<()> {
        #[cfg(unix)]
        {
            let number = crate::executor_process_unix::interruption();
            if number != 0 {
                crate::executor_process_unix::signal_group(&self.child, number);
                thread::sleep(Duration::from_millis(5));
                crate::executor_process_unix::signal_group(&self.child, libc::SIGKILL);
                let _ = self.child.wait();
                return Err(process("Codex app-server client closed"));
            }
        }
        Ok(())
    }
    pub fn close(&mut self) {
        if self.closed {
            return;
        }
        self.closed = true;
        let _ = self.check_interruption();
        self.pending = 0;
        // Python terminates first, then escalates after kill_timeout. A blocked
        // stdin worker is released when the child exits, including on Windows.
        #[cfg(unix)]
        if self.child.try_wait().is_ok_and(|status| status.is_none()) {
            let _ = crate::executor_process_unix::terminate_owned_child(&mut self.child);
            let deadline = Instant::now() + self.kill_timeout;
            while self.child.try_wait().is_ok_and(|status| status.is_none())
                && Instant::now() < deadline
            {
                let _ = self.check_interruption();
                let _ = self.read_stderr();
                if let Some(out) = &mut self.stdout {
                    let _ = out.read_once();
                    out.bytes.clear();
                }
                thread::sleep(Duration::from_millis(5));
            }
        }
        if self.child.try_wait().is_ok_and(|status| status.is_none()) {
            let _ = self.child.kill();
        }
        let _ = self.child.wait();
        #[cfg(unix)]
        {
            // Observe the group we created, without extending the kill policy.
            // Unknown liveness cannot acknowledge release of effect ownership.
            self.teardown_uncertain = !matches!(
                crate::executor_process_unix::process_alive(-(self.child.id() as libc::pid_t)),
                Ok(false)
            );
        }
        // Python retains stdin through terminate/wait. Keep its writer alive
        // until the child has exited, then release the queue before joining.
        self.send.take();
        // Keep the existing bounded stdin-worker cleanup. Unix pipe diagnostics
        // are drained synchronously below, without waiting for descendants.
        let deadline = Instant::now() + self.kill_timeout;
        while self.workers.iter().any(|worker| !worker.is_finished()) && Instant::now() < deadline {
            let _ = self.check_interruption();
            thread::sleep(Duration::from_millis(5));
        }
        #[cfg(unix)]
        {
            // Only this owner can publish pipe data; drop handles before return.
            let until = Instant::now() + Duration::from_millis(25);
            while Instant::now() < until {
                let _ = self.check_interruption();
                if !self.read_stderr().unwrap_or(false) {
                    break;
                }
            }
            // Preserve the old cancelled-reader EOF semantics for a partial
            // diagnostic, without waiting for an inherited pipe to close.
            if let Some(pipe) = &mut self.stderr_pipe {
                pipe.eof = true;
            }
            let _ = self.read_stderr();
            self.stdout.take();
            self.stderr_pipe.take();
        }
        for worker in self.workers.drain(..) {
            // An inherited stdin must not block close. On Unix this is only
            // the unchanged writer; it cannot publish stdout/stderr state.
            if worker.is_finished() {
                let _ = worker.join();
            }
        }
        let _ = self.check_interruption();
    }
    fn send(&self, value: Value) -> Result<()> {
        self.send
            .as_ref()
            .ok_or_else(|| process("Codex app-server stdin is unavailable"))?
            .send((value, None))
            .map_err(|_| process("Codex app-server stdin write failed"))
    }
    fn send_flushed(&self, value: Value, timeout: Duration) -> Result<()> {
        let (written, received) = mpsc::channel();
        self.send
            .as_ref()
            .ok_or_else(|| process("Codex app-server stdin is unavailable"))?
            .send((value, Some(written)))
            .map_err(|_| process("Codex app-server stdin write failed"))?;
        received
            .recv_timeout(timeout)
            .map_err(|_| process("Codex app-server stdin write failed"))
    }
    pub fn call(
        &mut self,
        options: CallOptions,
        progress: &mut Progress<'_>,
    ) -> Result<TurnResult> {
        let result = self.call_inner(options, progress);
        self.turn = None;
        self.pending = 0;
        if result.is_err() {
            self.close();
        }
        result
    }
    fn call_inner(
        &mut self,
        options: CallOptions,
        progress: &mut Progress<'_>,
    ) -> Result<TurnResult> {
        check_thread_encoding(self.next_id, &options)?;
        self.next_wait_error = options.wait_error;
        let stall = options
            .stall_timeout_float
            .or_else(|| options.stall_timeout.map(|duration| duration.as_secs_f64()));
        let deadline = options.timeout.map(|d| Instant::now() + d);
        let remaining = || deadline.map(|d| d.saturating_duration_since(Instant::now()));
        let mut args = json!({"cwd":options.cwd,"sandbox":options.sandbox,"approvalPolicy":options.approval_policy});
        if let Some(model) = options.model {
            args["model"] = model.into();
        }
        if let Some(base) = options.base_instructions {
            args["baseInstructions"] = base.into();
        }
        if let Some(config) = options.config {
            args["config"] = config;
        }
        let started = self.request("thread/start", args, remaining(), stall, progress)?;
        let thread = nonempty(&started["thread"]["id"])
            .ok_or_else(|| protocol("thread/start returned no thread id"))?
            .to_owned();
        let model = model_id(&started).or_else(|| model_id(&started["thread"]));
        self.turn = Some(Turn {
            thread: thread.clone(),
            ..Turn::default()
        });
        if let Some(points) = options.string_codepoints.get("prompt") {
            let prefix = format!(
                "{{\"id\": {}, \"method\": \"turn/start\", \"params\": {{\"threadId\": {}, \"input\": [{{\"type\": \"text\", \"text\": ",
                self.next_id,
                serde_json::to_string(&thread)
                    .map_err(|error| Error::Encoding(error.to_string()))?
            );
            let mut message = crate::executor_text::text_points(&prefix);
            message.extend(crate::executor_text::json_quote_points(points));
            check_encoding(&message)?;
        }
        let started = self.request(
            "turn/start",
            json!({"threadId":thread,"input":[{"type":"text","text":options.prompt}]}),
            remaining(),
            stall,
            progress,
        )?;
        let turn_id = nonempty(&started["turn"]["id"])
            .ok_or_else(|| protocol("turn/start returned no turn id"))?;
        let result = self.wait(None, "turn/completed", remaining(), stall, progress)?;
        let completed = &result["turn"];
        if !completed.is_object() {
            return Err(protocol("turn/completed returned no turn"));
        }
        if completed["id"] != turn_id {
            return Err(protocol("turn/completed returned an unexpected turn id"));
        }
        if completed["status"] != "completed" {
            let detail = if !completed["error"].is_null() {
                rpc_error(&completed["error"])
            } else {
                completed["status"].as_str().unwrap_or("None").to_owned()
            };
            return Err(protocol(format!("Codex turn failed: {detail}")));
        }
        let turn = self
            .turn
            .as_ref()
            .ok_or_else(|| protocol("turn/completed returned no turn"))?;
        Ok(TurnResult {
            content_text: turn
                .texts
                .iter()
                .map(|(_, text)| text.as_str())
                .collect::<Vec<_>>()
                .join("\n"),
            thread_id: thread,
            model_id: model_id(&result).or_else(|| model_id(completed)).or(model),
            token_usage: usage(&result)
                .or_else(|| usage(completed))
                .or_else(|| turn.usage.clone()),
            tool_version: self.tool_version.clone(),
            raw_result: result,
        })
    }
    fn request(
        &mut self,
        method: &str,
        params: Value,
        timeout: Option<Duration>,
        stall: Option<f64>,
        progress: &mut Progress<'_>,
    ) -> Result<Value> {
        let id = self.next_id;
        self.next_id += 1;
        self.pending = 1;
        if let Ok(mut at) = self.activity.lock() {
            *at = Instant::now();
        }
        self.send(json!({"id":id,"method":method,"params":params}))?;
        if let Some(error) = self.next_wait_error.take() {
            return Err(Error::Encoding(error.into()));
        }
        let result = self.wait(Some(id), method, timeout, stall, progress);
        self.pending = 0;
        result
    }
    fn inactive_for(&self) -> Duration {
        self.activity
            .lock()
            .map(|at| at.elapsed())
            .unwrap_or_default()
    }
    #[cfg(not(unix))]
    fn wait(
        &mut self,
        id: Option<u64>,
        method: &str,
        timeout: Option<Duration>,
        stall: Option<f64>,
        progress: &mut Progress<'_>,
    ) -> Result<Value> {
        let start = Instant::now();
        let interval = stall.map(|seconds| {
            if seconds.is_nan() {
                Duration::ZERO
            } else {
                Duration::from_secs_f64((seconds / 4.0).clamp(0.01, 0.25))
            }
        });
        let mut next_watch = interval.map(|interval| start + interval);
        loop {
            self.check_interruption()?;
            if self.cancel.0.load(Ordering::SeqCst) {
                return Err(process("Codex app-server client closed"));
            }
            if id.is_none()
                && let Some(result) = self.turn.as_mut().and_then(|t| t.completed.take())
            {
                return Ok(result);
            }
            if let Some(timeout) = timeout
                && start.elapsed() >= timeout
            {
                return Err(Error::Timeout(format!(
                    "Codex app-server request '{method}' timed out after {}s",
                    timeout.as_secs_f64()
                )));
            }
            if let Some(stall) = stall
                && next_watch.is_some_and(|watch| Instant::now() >= watch)
            {
                let inactive = self.inactive_for().as_secs_f64();
                if inactive > stall || stall.is_nan() {
                    return Err(Error::Stall(format!(
                        "Codex app-server request '{method}' stalled after {inactive}s without stdout activity"
                    )));
                }
                next_watch = interval.map(|interval| Instant::now() + interval);
            }
            match self.events.recv_timeout(Duration::from_millis(5)) {
                Ok(Event::Line(line)) => {
                    let Some(message) = parse_frame(&line) else {
                        if !line.trim().is_empty() {
                            self.malformed.push(line.trim().to_owned());
                        }
                        continue;
                    };
                    if let Some(value) = self.handle(message, &line, id, progress)? {
                        return Ok(value);
                    }
                }
                Ok(Event::Eof) | Err(mpsc::RecvTimeoutError::Disconnected) => {
                    let until = Instant::now() + self.kill_timeout;
                    loop {
                        self.check_interruption()?;
                        match self.child.try_wait() {
                            Ok(Some(code)) => {
                                return Err(process(format!(
                                    "Codex app-server exited with code {}",
                                    exit_code(code)
                                )));
                            }
                            Err(e) => return Err(process(e.to_string())),
                            Ok(None) => {
                                if Instant::now() >= until {
                                    return Err(process("Codex app-server stdout closed"));
                                }
                            }
                        }
                        thread::sleep(Duration::from_millis(5));
                    }
                }
                Ok(Event::ReadError(e)) => {
                    return Err(process(format!("Codex app-server stdout read failed: {e}")));
                }
                Ok(Event::WriteError) => {
                    return Err(process("Codex app-server stdin write failed"));
                }
                Err(mpsc::RecvTimeoutError::Timeout) => {
                    if timeout.is_some_and(|limit| start.elapsed() >= limit) {
                        continue;
                    }
                    // Python's process watcher rejects calls even when a
                    // descendant retains the provider's stdout descriptor.
                    if let Ok(Some(status)) = self.child.try_wait() {
                        return Err(process(format!(
                            "Codex app-server exited with code {}",
                            exit_code(status)
                        )));
                    }
                }
            }
        }
    }
    fn handle(
        &mut self,
        message: Value,
        raw: &str,
        pending: Option<u64>,
        progress: &mut Progress<'_>,
    ) -> Result<Option<Value>> {
        let has_id = message.get("id").is_some();
        let result = message.get("result");
        let error = message.get("error");
        let method = message["method"].as_str();
        if has_id && (result.is_some() || error.is_some()) {
            let id = &message["id"];
            if !id.is_i64() && !id.is_u64() && !id.is_string() {
                return Err(protocol("app-server response has invalid id"));
            }
            // Only an issued integer request ID may resolve a pending call.
            if id.as_u64().is_none() || id.as_u64() != pending {
                return Ok(None);
            }
            if result.is_some() == error.is_some() || message.get("method").is_some() {
                return Err(protocol("app-server response has invalid envelope"));
            }
            return match error {
                Some(error) => Err(protocol(rpc_error(error))),
                None => Ok(result.cloned()),
            };
        }
        if has_id && method.is_none() {
            return Err(protocol("app-server response has invalid envelope"));
        }
        if let Some(method) = method {
            if has_id {
                let error = format!("Unsupported app-server request: {method}");
                self.send(json!({"id":message["id"],"error":{"code":-32601,"message":error}}))?;
                return Err(protocol(error));
            }
            let empty = json!({});
            let params = message.get("params").unwrap_or(&empty);
            progress(method, params).map_err(|e| {
                Error::Callback(format!("Codex app-server progress callback failed: {e}"))
            })?;
            if method == "thread/tokenUsage/updated" {
                if let Some(turn) = &mut self.turn
                    && params["threadId"].as_str() == Some(&turn.thread)
                    && params["tokenUsage"].is_object()
                {
                    turn.usage = Some(params["tokenUsage"].clone());
                }
            } else if matches!(method, "item/completed" | "turn/completed") {
                if !params.is_object() {
                    return Err(protocol(format!("{method} returned invalid params")));
                }
                let thread = nonempty(&params["threadId"])
                    .ok_or_else(|| protocol(format!("{method} returned invalid threadId")))?;
                if let Some(turn) = &mut self.turn
                    && turn.thread == thread
                    && turn.completed.is_none()
                {
                    if method == "item/completed" {
                        record_item(turn, &params["item"], "item/completed item")?;
                    } else {
                        let completed = &params["turn"];
                        if !completed.is_object()
                            || nonempty(&completed["id"]).is_none()
                            || !completed["status"].is_string()
                        {
                            return Err(protocol("turn/completed returned invalid turn"));
                        }
                        let empty = vec![];
                        let items = match completed.get("items") {
                            None => &empty,
                            Some(v) => v
                                .as_array()
                                .ok_or_else(|| protocol("turn/completed returned invalid items"))?,
                        };
                        for item in items {
                            record_item(turn, item, "turn/completed items")?;
                        }
                        turn.completed = Some(params.clone());
                    }
                }
            }
        } else {
            self.malformed.push(raw.trim().to_owned());
        }
        Ok(None)
    }
}
fn exit_code(status: std::process::ExitStatus) -> i32 {
    #[cfg(unix)]
    {
        use std::os::unix::process::ExitStatusExt;
        status
            .code()
            .or_else(|| status.signal().map(|signal| -signal))
            .unwrap_or(-1)
    }
    #[cfg(not(unix))]
    {
        status.code().unwrap_or(-1)
    }
}

fn check_encoding(points: &[u32]) -> Result<()> {
    if let Some(start) = points
        .iter()
        .position(|point| (0xd800..=0xdfff).contains(point))
    {
        let end = start
            + points[start..]
                .iter()
                .take_while(|point| (0xd800..=0xdfff).contains(*point))
                .count();
        return Err(Error::Encoding(crate::executor_text::encode_error(
            "utf-8",
            points,
            start,
            end,
            "surrogates not allowed",
        )));
    }
    Ok(())
}
fn check_thread_encoding(id: u64, options: &CallOptions) -> Result<()> {
    if options.string_codepoints.is_empty() {
        return Ok(());
    }
    let mut points = crate::executor_text::text_points(&format!(
        "{{\"id\": {id}, \"method\": \"thread/start\", \"params\": {{"
    ));
    let mut append = |key: &'static str, value: &str, first: bool| {
        if !first {
            points.extend(crate::executor_text::text_points(", "));
        }
        points.extend(crate::executor_text::json_quote_points(
            &crate::executor_text::text_points(key),
        ));
        points.extend([58, 32]);
        let plain = crate::executor_text::text_points(value);
        let raw = options.string_codepoints.get(key).unwrap_or(&plain);
        points.extend(crate::executor_text::json_quote_points(raw));
    };
    append("cwd", &options.cwd, true);
    append("sandbox", &options.sandbox, false);
    append("approvalPolicy", &options.approval_policy, false);
    if let Some(model) = &options.model {
        append("model", model, false);
    }
    if let Some(base) = &options.base_instructions {
        append("baseInstructions", base, false);
    }
    if let Some(config) = &options.config {
        points.extend(crate::executor_text::text_points(
            ", \"config\": {\"project_doc_max_bytes\": 0",
        ));
        if let Some(effort) = config["model_reasoning_effort"].as_str() {
            points.extend(crate::executor_text::text_points(
                ", \"model_reasoning_effort\": ",
            ));
            let plain = crate::executor_text::text_points(effort);
            points.extend(crate::executor_text::json_quote_points(
                options
                    .string_codepoints
                    .get("model_reasoning_effort")
                    .unwrap_or(&plain),
            ));
        }
    }
    check_encoding(&points)
}
impl Drop for Client {
    fn drop(&mut self) {
        self.close();
    }
}
fn nonempty(value: &Value) -> Option<&str> {
    value.as_str().filter(|s| !s.is_empty())
}
fn rpc_error(value: &Value) -> String {
    value["message"]
        .as_str()
        .unwrap_or("Codex app-server JSON-RPC request failed")
        .to_owned()
}
fn record_item(turn: &mut Turn, item: &Value, source: &str) -> Result<()> {
    if !item.is_object() {
        return Err(protocol(format!("{source} is not an object")));
    }
    let kind = item["type"]
        .as_str()
        .ok_or_else(|| protocol(format!("{source} has invalid type")))?;
    if kind != "agentMessage" || item["phase"] == "commentary" {
        return Ok(());
    }
    let id = nonempty(&item["id"])
        .ok_or_else(|| protocol(format!("{source} has invalid agent message fields")))?;
    let text = item["text"]
        .as_str()
        .ok_or_else(|| protocol(format!("{source} has invalid agent message fields")))?;
    if let Some((_, previous)) = turn.texts.iter_mut().find(|(key, _)| key == id) {
        *previous = text.to_owned();
    } else {
        turn.texts.push((id.to_owned(), text.to_owned()));
    }
    Ok(())
}
fn usage(value: &Value) -> Option<Value> {
    for key in ["tokenUsage", "token_usage", "usage"] {
        if value[key].is_object() {
            return Some(value[key].clone());
        }
    }
    for key in ["_meta", "metadata", "providerMetadata", "provider_metadata"] {
        if value[key].is_object()
            && let Some(found) = usage(&value[key])
        {
            return Some(found);
        }
    }
    None
}
fn model_id(value: &Value) -> Option<String> {
    for key in ["modelId", "model_id", "model"] {
        if let Some(s) = value[key].as_str().filter(|s| !s.trim().is_empty()) {
            return Some(s.trim().to_owned());
        }
    }
    for key in ["_meta", "metadata", "providerMetadata", "provider_metadata"] {
        let mut stack = vec![&value[key]];
        while let Some(nested) = stack.pop() {
            if let Some(obj) = nested.as_object() {
                for key in ["modelId", "model_id", "model"] {
                    if let Some(s) = obj
                        .get(key)
                        .and_then(Value::as_str)
                        .filter(|s| !s.trim().is_empty())
                    {
                        return Some(s.trim().to_owned());
                    }
                }
                stack.extend(obj.values().rev());
            } else if let Some(arr) = nested.as_array() {
                stack.extend(arr.iter().rev());
            }
        }
    }
    None
}
fn parse_frame(line: &str) -> Option<Value> {
    // Preflight nesting before disabling serde's smaller default recursion limit.
    // Python rejects excessive nesting as malformed and continues reading.
    let (mut depth, mut quoted, mut escaped) = (0usize, false, false);
    for c in line.chars() {
        if quoted {
            if escaped {
                escaped = false;
            } else if c == '\\' {
                escaped = true;
            } else if c == '"' {
                quoted = false;
            }
        } else {
            match c {
                '"' => quoted = true,
                '[' | '{' => {
                    depth += 1;
                    if depth >= 995 {
                        return None;
                    }
                }
                ']' | '}' => depth = depth.saturating_sub(1),
                _ => {}
            }
        }
    }
    let mut deserializer = serde_json::Deserializer::from_str(line);
    deserializer.disable_recursion_limit();
    let mut stream = deserializer.into_iter::<Value>();
    let value = stream.next()?.ok()?;
    if stream.next().is_some() {
        return None;
    }
    value.is_object().then_some(value)
}

#[cfg(unix)]
struct Pipe<R> {
    inner: R,
    bytes: Vec<u8>,
    eof: bool,
    read: usize,
}
#[cfg(unix)]
impl<R: std::io::Read + std::os::fd::AsRawFd> Pipe<R> {
    fn new(inner: R) -> std::io::Result<Self> {
        let fd = inner.as_raw_fd();
        crate::executor_process_unix::nonblocking(fd)?;
        Ok(Self {
            inner,
            bytes: vec![],
            eof: false,
            read: 0,
        })
    }
    fn read_once(&mut self) -> std::io::Result<bool> {
        if self.eof {
            return Ok(false);
        }
        let mut bytes = [0; 8192];
        match self.inner.read(&mut bytes) {
            Ok(0) => {
                self.eof = true;
                Ok(false)
            }
            Ok(n) => {
                self.read += n;
                self.bytes.extend_from_slice(&bytes[..n]);
                Ok(true)
            }
            Err(e)
                if matches!(
                    e.kind(),
                    std::io::ErrorKind::WouldBlock | std::io::ErrorKind::Interrupted
                ) =>
            {
                Ok(false)
            }
            Err(e) => Err(e),
        }
    }
    fn line(&mut self) -> std::io::Result<Option<String>> {
        let n = match self.bytes.iter().position(|b| *b == b'\n') {
            Some(n) => n + 1,
            None if self.eof && !self.bytes.is_empty() => self.bytes.len(),
            None => return Ok(None),
        };
        let mut bytes: Vec<_> = self.bytes.drain(..n).collect();
        if bytes.last() == Some(&b'\n') {
            bytes.pop();
            if bytes.last() == Some(&b'\r') {
                bytes.pop();
            }
        }
        String::from_utf8(bytes).map(Some).map_err(|_| {
            std::io::Error::new(
                std::io::ErrorKind::InvalidData,
                "stream did not contain valid UTF-8",
            )
        })
    }
    fn written_bound(&self) -> Result<usize> {
        crate::executor_process_unix::available(self.inner.as_raw_fd())
            .map(|n| self.read.saturating_add(n))
            .map_err(|e| process(e.to_string()))
    }
    fn pollfd(&self) -> libc::pollfd {
        libc::pollfd {
            fd: if self.eof { -1 } else { self.inner.as_raw_fd() },
            events: libc::POLLIN,
            revents: 0,
        }
    }
    fn has_line(&self) -> bool {
        self.bytes.contains(&b'\n') || (self.eof && !self.bytes.is_empty())
    }
}
#[cfg(unix)]
impl Client {
    fn read_stderr(&mut self) -> std::io::Result<bool> {
        let Some(pipe) = &mut self.stderr_pipe else {
            return Ok(false);
        };
        let read = pipe.read_once()?;
        loop {
            match pipe.line() {
                Ok(Some(line)) => {
                    if let Ok(mut lines) = self.stderr.lock() {
                        lines.push(line);
                    }
                }
                Ok(None) => break,
                Err(_) => {
                    // The previous stderr lines() worker stopped on decode errors.
                    pipe.eof = true;
                    pipe.bytes.clear();
                    break;
                }
            }
        }
        Ok(read)
    }
    fn wait(
        &mut self,
        id: Option<u64>,
        method: &str,
        timeout: Option<Duration>,
        stall: Option<f64>,
        progress: &mut Progress<'_>,
    ) -> Result<Value> {
        let start = Instant::now();
        let deadline = timeout.map(|t| start + t);
        let interval = stall.map(|s| {
            if s.is_nan() {
                Duration::ZERO
            } else {
                Duration::from_secs_f64((s / 4.0).clamp(0.01, 0.25))
            }
        });
        let mut next_watch = interval.map(|i| start + i);
        let mut exited = None;
        let mut stdout_closed = None;
        let mut exit_bytes = [0; 2];
        loop {
            self.check_interruption()?;
            let timed_out = || deadline.is_some_and(|d| Instant::now() >= d);
            let timeout_error = || {
                Error::Timeout(format!(
                    "Codex app-server request '{method}' timed out after {}s",
                    timeout.map_or(0.0, |t| t.as_secs_f64())
                ))
            };
            if timed_out() {
                return Err(timeout_error());
            }
            if self.cancel.0.load(Ordering::SeqCst) {
                return Err(process("Codex app-server client closed"));
            }
            if id.is_none()
                && let Some(result) = self.turn.as_mut().and_then(|t| t.completed.take())
            {
                return Ok(result);
            }
            if exited.is_none()
                && let Some(status) = self.child.try_wait().map_err(|e| process(e.to_string()))?
            {
                let out = self
                    .stdout
                    .as_ref()
                    .ok_or_else(|| process("Codex app-server stdout closed"))?;
                let err = self
                    .stderr_pipe
                    .as_ref()
                    .ok_or_else(|| process("Codex app-server stderr is unavailable"))?;
                // Snapshot only the bytes already available. Descendant writes
                // cannot extend this floor, and scheduling cannot discard it.
                exit_bytes = [out.written_bound()?, err.written_bound()?];
                exited = Some((
                    Instant::now() + Duration::from_millis(25),
                    exit_code(status),
                ));
                #[cfg(test)]
                thread::sleep(self.frame_delay);
            }
            if let Some((until, code)) = exited
                && Instant::now() >= until
                && self
                    .stdout
                    .as_ref()
                    .is_none_or(|p| p.read >= exit_bytes[0] && !p.has_line())
                && self
                    .stderr_pipe
                    .as_ref()
                    .is_none_or(|p| p.read >= exit_bytes[1])
            {
                return Err(process(format!(
                    "Codex app-server exited with code {}",
                    code
                )));
            }
            if let Some(stall) = stall
                && next_watch.is_some_and(|at| Instant::now() >= at)
            {
                let inactive = self.inactive_for().as_secs_f64();
                if inactive > stall || stall.is_nan() {
                    return Err(Error::Stall(format!(
                        "Codex app-server request '{method}' stalled after {inactive}s without stdout activity"
                    )));
                }
                next_watch = interval.map(|i| Instant::now() + i);
            }
            if matches!(self.events.try_recv(), Ok(Event::WriteError)) {
                return Err(process("Codex app-server stdin write failed"));
            }
            // Bounded chunks let continuous descendant output yield to deadlines.
            let _ = self.read_stderr();
            let pipe = self
                .stdout
                .as_mut()
                .ok_or_else(|| process("Codex app-server stdout closed"))?;
            if !pipe.has_line() {
                pipe.read_once()
                    .map_err(|e| process(format!("Codex app-server stdout read failed: {e}")))?;
            }
            let line = pipe
                .line()
                .map_err(|e| process(format!("Codex app-server stdout read failed: {e}")))?;
            if let Some(line) = line {
                if let Ok(mut at) = self.activity.lock() {
                    *at = Instant::now();
                }
                #[cfg(test)]
                thread::sleep(self.frame_delay);
                let message = parse_frame(&line);
                // Parsing and poll wakeups may cross the request deadline.
                if timed_out() {
                    return Err(timeout_error());
                }
                if let Some(message) = message {
                    if let Some(value) = self.handle(message, &line, id, progress)? {
                        self.check_interruption()?;
                        if timed_out() {
                            return Err(timeout_error());
                        }
                        return Ok(value);
                    }
                } else if !line.trim().is_empty() {
                    self.malformed.push(line.trim().to_owned());
                }
                continue;
            }
            let out = self
                .stdout
                .as_ref()
                .ok_or_else(|| process("Codex app-server stdout closed"))?;
            if out.eof && stdout_closed.is_none() {
                stdout_closed = Some(Instant::now() + self.kill_timeout);
            }
            if let Some((_, code)) = exited
                && out.eof
                && self.stderr_pipe.as_ref().is_none_or(|p| p.eof)
            {
                return Err(process(format!(
                    "Codex app-server exited with code {}",
                    code
                )));
            }
            if stdout_closed.is_some_and(|d| Instant::now() >= d) && exited.is_none() {
                return Err(process("Codex app-server stdout closed"));
            }
            let now = Instant::now();
            let mut until = now + Duration::from_millis(5);
            for d in [deadline, next_watch, exited.map(|e| e.0), stdout_closed]
                .into_iter()
                .flatten()
            {
                until = until.min(d);
            }
            let remaining = until.saturating_duration_since(now);
            let millis = remaining.as_millis().min(i32::MAX as u128) as i32;
            let mut fds = [
                out.pollfd(),
                self.stderr_pipe
                    .as_ref()
                    .ok_or_else(|| process("Codex app-server stderr is unavailable"))?
                    .pollfd(),
            ];
            crate::executor_process_unix::poll(&mut fds, millis)
                .map_err(|e| process(e.to_string()))?;
        }
    }
}

#[cfg(all(test, unix))]
mod poll_regression_tests {
    use super::*;
    fn client(script: &str) -> Client {
        let mut child = Command::new("python3")
            .args(["-c", script])
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .unwrap();
        let stdout = Pipe::new(child.stdout.take().unwrap()).unwrap();
        let stderr = Pipe::new(child.stderr.take().unwrap()).unwrap();
        let (_tx, events) = mpsc::channel();
        Client {
            child,
            stdout: Some(stdout),
            stderr_pipe: Some(stderr),
            send: None,
            events,
            workers: vec![],
            stderr: Arc::new(Mutex::new(vec![])),
            malformed: vec![],
            cancel: Cancellation(Arc::new(AtomicBool::new(false))),
            next_id: 1,
            pending: 0,
            activity: Arc::new(Mutex::new(Instant::now())),
            kill_timeout: Duration::from_millis(10),
            tool_version: None,
            turn: None,
            next_wait_error: None,
            closed: false,
            teardown_uncertain: false,
            frame_delay: Duration::ZERO,
        }
    }
    fn response(client: &mut Client, timeout: Option<Duration>) -> Result<Value> {
        client.wait(Some(1), "probe", timeout, None, &mut |_, _| Ok(()))
    }
    #[test]
    fn pipe_framing_matches_previous_bufreader() {
        use std::io::BufRead;
        use std::os::unix::net::UnixStream;
        for data in [b"one\r\ntwo\n".as_slice(), b"partial\r", b"\xff\n"] {
            let expected: Vec<_> = std::io::BufReader::new(data)
                .lines()
                .map(|r| r.map_err(|e| e.to_string()))
                .collect();
            let (input, mut output) = UnixStream::pair().unwrap();
            output.write_all(data).unwrap();
            output.shutdown(std::net::Shutdown::Write).unwrap();
            let mut pipe = Pipe::new(input).unwrap();
            while pipe.read_once().unwrap() {}
            let mut actual = vec![];
            loop {
                match pipe.line() {
                    Ok(Some(s)) => actual.push(Ok(s)),
                    Ok(None) => break,
                    Err(e) => {
                        actual.push(Err(e.to_string()));
                        break;
                    }
                }
            }
            assert_eq!(actual, expected);
        }
    }
    #[test]
    fn late_response_after_deadline_is_rejected() {
        let mut c = client("print('{\"id\":1,\"result\":{}}', flush=True)");
        c.child.wait().unwrap();
        c.frame_delay = Duration::from_millis(3);
        assert!(matches!(
            response(&mut c, Some(Duration::from_millis(1))),
            Err(Error::Timeout(_))
        ));
    }
    #[test]
    fn delayed_final_frame_is_not_dependent_on_reader_scheduling() {
        let mut c = client("print('{\"id\":1,\"result\":{\"frame\":\"FINAL\"}}', flush=True)");
        c.child.wait().unwrap();
        c.frame_delay = Duration::from_millis(80);
        // The owner is descheduled after bytes are written, before reading.
        thread::sleep(Duration::from_millis(80));
        assert_eq!(
            response(&mut c, Some(Duration::from_secs(1))).unwrap()["frame"],
            "FINAL"
        );
    }
    #[test]
    fn close_preserves_partial_stderr_from_held_pipe() {
        let mut c = client(
            "import os,time\nif os.fork()==0:\n time.sleep(0.08)\n os._exit(0)\nos.write(2,b'partial')\nos._exit(0)",
        );
        c.child.wait().unwrap();
        c.close();
        assert_eq!(c.stderr_lines(), ["partial"]);
        thread::sleep(Duration::from_millis(100));
    }
    #[test]
    fn no_publication_after_close() {
        let mut c = client("import sys; print('LATE', file=sys.stderr, flush=True)");
        c.child.wait().unwrap();
        c.close();
        assert_eq!(c.stderr_lines(), ["LATE"]);
        assert!(c.stderr_pipe.is_none() && c.stdout.is_none());
        let before = c.stderr_lines();
        assert!(!c.read_stderr().unwrap());
        assert_eq!(c.stderr_lines(), before);
    }
    #[test]
    fn continuous_exit_pipe_has_no_reader_worker() {
        let mut c = client(
            "import os,time,signal\nif os.fork()==0:\n signal.signal(signal.SIGPIPE, signal.SIG_DFL)\n end=time.monotonic()+0.3\n while time.monotonic()<end: os.write(1,b'x'*8192)\n os._exit(0)\nos._exit(0)",
        );
        c.child.wait().unwrap();
        let began = Instant::now();
        assert!(matches!(response(&mut c, None), Err(Error::Process(_))));
        assert!(began.elapsed() < Duration::from_millis(150));
        assert!(c.workers.is_empty());
        c.close(); // closes the pipe; own finite descendant gets SIGPIPE.
        thread::sleep(Duration::from_millis(320));
    }
    #[test]
    fn written_bytes_without_eof_are_drained_200_times() {
        use std::os::unix::net::UnixStream;
        for _ in 0..200 {
            let (input, mut output) = UnixStream::pair().unwrap();
            output.write_all(b"completion\npartial").unwrap();
            let mut pipe = Pipe::new(input).unwrap();
            assert!(pipe.read_once().unwrap());
            assert_eq!(pipe.line().unwrap().as_deref(), Some("completion"));
            assert!(!pipe.read_once().unwrap());
            assert_eq!(pipe.bytes, b"partial");
            // The descriptor remains owned and usable until drop.
            output.shutdown(std::net::Shutdown::Write).unwrap();
            assert!(!pipe.read_once().unwrap());
            assert_eq!(pipe.line().unwrap().as_deref(), Some("partial"));
        }
    }
    #[test]
    fn completion_after_exit_observation_is_drained_200_times() {
        for _ in 0..200 {
            let mut c = client("print('{\"id\":1,\"result\":{}}', flush=True)");
            c.child.wait().unwrap();
            assert!(response(&mut c, Some(Duration::from_secs(1))).is_ok());
        }
    }
    #[test]
    fn exit_drain_respects_request_deadline() {
        let mut c = client(
            "import os,time\nif os.fork()==0:\n time.sleep(0.08)\n os._exit(0)\nos._exit(0)",
        );
        c.child.wait().unwrap();
        let result = response(&mut c, Some(Duration::from_millis(1)));
        c.close();
        thread::sleep(Duration::from_millis(100));
        assert!(matches!(result, Err(Error::Timeout(_))));
    }
    #[test]
    fn exit_drain_has_a_cap_without_request_timeout() {
        let mut c = client(
            "import os,time\nif os.fork()==0:\n time.sleep(0.08)\n os._exit(0)\nos._exit(0)",
        );
        c.child.wait().unwrap();
        let began = Instant::now();
        assert!(matches!(response(&mut c, None), Err(Error::Process(_))));
        assert!(began.elapsed() < Duration::from_millis(150));
        c.close();
        thread::sleep(Duration::from_millis(100));
    }
}
