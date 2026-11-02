//! Offline-testable app-server transport. No executable selection or CLI wiring.
//! One caller owns requests; reader/writer threads keep pipe I/O outside deadlines.
//! Unknown provider fields and unissued response IDs are intentionally tolerated.
use serde_json::{Value, json};
use std::{
    io::{BufRead, BufReader, Write},
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
    Protocol(String),
    Timeout(String),
    Stall(String),
    Callback(String),
}
impl Error {
    pub fn python_class(&self) -> &'static str {
        match self {
            Self::Process(_) => "CodexMcpProcessError",
            Self::Protocol(_) => "CodexMcpProtocolError",
            Self::Timeout(_) => "CodexMcpTimeoutError",
            Self::Stall(_) => "CodexMcpStallError",
            Self::Callback(_) => "CodexMcpError",
        }
    }
}
impl std::fmt::Display for Error {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Process(s)
            | Self::Protocol(s)
            | Self::Timeout(s)
            | Self::Stall(s)
            | Self::Callback(s) => f.write_str(s),
        }
    }
}
impl std::error::Error for Error {}
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
enum Event {
    Line(String),
    Eof,
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
/// Serial request owner with concurrent stdout, stderr and stdin workers.
/// Drop/close uses Child::kill on every platform (Windows has no SIGTERM).
/// Only direct children are supported; inherited pipes in descendants are out of scope.
pub struct Client {
    child: Child,
    send: Option<Sender<Value>>,
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
    closed: bool,
}
impl Client {
    /// Spawn the explicit command supplied by the owner and initialize it.
    pub fn spawn(
        mut command: Command,
        initialize_timeout: Duration,
        kill_timeout: Duration,
    ) -> Result<Self> {
        let mut child = command
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .map_err(|e| process(e.to_string()))?;
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
        let (send, writes) = mpsc::channel::<Value>();
        let out_tx = tx.clone();
        let activity = Arc::new(Mutex::new(Instant::now()));
        let stdout_activity = activity.clone();
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
        let lines = stderr_lines.clone();
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
            for value in writes {
                if writeln!(stdin, "{value}")
                    .and_then(|()| stdin.flush())
                    .is_err()
                {
                    let _ = tx.send(Event::WriteError);
                    return;
                }
            }
        });
        let mut client = Self {
            child,
            send: Some(send),
            events,
            workers: vec![output, errors, writer],
            stderr: stderr_lines,
            malformed: Vec::new(),
            cancel: Cancellation(Arc::new(AtomicBool::new(false))),
            next_id: 1,
            pending: 0,
            activity,
            kill_timeout,
            tool_version: None,
            turn: None,
            closed: false,
        };
        let mut progress = |_: &str, _: &Value| Ok(());
        let initialized = client.request(
            "initialize",
            json!({"capabilities":{},"clientInfo":{"name":"mir_executor","version":"0.1.0"}}),
            Some(initialize_timeout),
            None,
            &mut progress,
        )?;
        client.tool_version = nonempty(&initialized["userAgent"]).map(|s| s.trim().to_owned());
        client.send(json!({"method":"initialized","params":{}}))?;
        Ok(client)
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
    pub fn close(&mut self) {
        if self.closed {
            return;
        }
        self.closed = true;
        self.pending = 0;
        self.send.take();
        // A portable hard stop also unblocks a writer stuck in a full stdin pipe.
        let _ = self.child.kill();
        let _ = self.child.wait();
        for worker in self.workers.drain(..) {
            let _ = worker.join();
        }
    }
    fn send(&self, value: Value) -> Result<()> {
        self.send
            .as_ref()
            .ok_or_else(|| process("Codex app-server stdin is unavailable"))?
            .send(value)
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
        let started = self.request(
            "thread/start",
            args,
            remaining(),
            options.stall_timeout,
            progress,
        )?;
        let thread = nonempty(&started["thread"]["id"])
            .ok_or_else(|| protocol("thread/start returned no thread id"))?
            .to_owned();
        let model = model_id(&started).or_else(|| model_id(&started["thread"]));
        self.turn = Some(Turn {
            thread: thread.clone(),
            ..Turn::default()
        });
        let started = self.request(
            "turn/start",
            json!({"threadId":thread,"input":[{"type":"text","text":options.prompt}]}),
            remaining(),
            options.stall_timeout,
            progress,
        )?;
        let turn_id = nonempty(&started["turn"]["id"])
            .ok_or_else(|| protocol("turn/start returned no turn id"))?;
        let result = self.wait(
            None,
            "turn/completed",
            remaining(),
            options.stall_timeout,
            progress,
        )?;
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
        stall: Option<Duration>,
        progress: &mut Progress<'_>,
    ) -> Result<Value> {
        let id = self.next_id;
        self.next_id += 1;
        self.pending = 1;
        if let Ok(mut at) = self.activity.lock() {
            *at = Instant::now();
        }
        self.send(json!({"id":id,"method":method,"params":params}))?;
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
    fn wait(
        &mut self,
        id: Option<u64>,
        method: &str,
        timeout: Option<Duration>,
        stall: Option<Duration>,
        progress: &mut Progress<'_>,
    ) -> Result<Value> {
        let start = Instant::now();
        loop {
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
                && self.inactive_for() > stall
            {
                return Err(Error::Stall(format!(
                    "Codex app-server request '{method}' stalled after {}s without stdout activity",
                    self.inactive_for().as_secs_f64()
                )));
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
                        match self.child.try_wait() {
                            Ok(Some(code)) => {
                                return Err(process(format!(
                                    "Codex app-server exited with code {}",
                                    code.code().unwrap_or(-1)
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
                Err(mpsc::RecvTimeoutError::Timeout) => {}
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
