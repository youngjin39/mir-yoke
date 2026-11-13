//! Explicit persistent access to a target-owned local hook module.
//! Unknown reply fields are accepted for forward-compatible diagnostics.
use serde_json::{Value, json};
use std::{
    collections::BTreeMap,
    ffi::OsString,
    io::{self, BufRead, BufReader, Write},
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    sync::mpsc::{self, Receiver, Sender},
    thread::{self, JoinHandle},
    time::Duration,
};

pub const PROTOCOL: &str = "mir-executor.local@1";
pub const MAX_FRAME_BYTES: usize = 1024 * 1024;
pub struct BridgeConfig {
    pub interpreter: PathBuf,
    pub target_root: PathBuf,
    pub bridge_script: PathBuf,
    pub environment: BTreeMap<OsString, OsString>,
    pub timeout: Duration,
}
#[derive(Debug)]
pub enum BridgeError {
    Io(io::Error),
    Json(serde_json::Error),
    Protocol(&'static str),
    Configuration(String),
    FrameTooLarge,
    Timeout,
    Closed,
}
impl std::fmt::Display for BridgeError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Io(error) => write!(f, "local bridge I/O: {error}"),
            Self::Json(error) => write!(f, "local bridge JSON: {error}"),
            Self::Protocol(message) => write!(f, "local bridge protocol: {message}"),
            Self::Configuration(message) => f.write_str(message),
            Self::FrameTooLarge => f.write_str("local bridge frame exceeds limit"),
            Self::Timeout => f.write_str("local bridge timed out"),
            Self::Closed => f.write_str("local bridge is closed"),
        }
    }
}
impl std::error::Error for BridgeError {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            Self::Io(error) => Some(error),
            Self::Json(error) => Some(error),
            _ => None,
        }
    }
}
impl From<io::Error> for BridgeError {
    fn from(value: io::Error) -> Self {
        Self::Io(value)
    }
}
impl From<serde_json::Error> for BridgeError {
    fn from(value: serde_json::Error) -> Self {
        Self::Json(value)
    }
}
type Result<T> = std::result::Result<T, BridgeError>;
#[derive(Debug)]
pub struct LocalBridge {
    child: Child,
    requests: Option<Sender<Vec<u8>>>,
    responses: Receiver<Result<Value>>,
    worker: Option<JoinHandle<()>>,
    hello: Value,
    next_id: u64,
    timeout: Duration,
    closed: bool,
}
// Parser callbacks share the selected bridge's cached local module and writer lifetime.
const PARSER_BRIDGE: &str = r#"
import contextlib, io, runpy, sys
script = sys.argv.pop(1)
sys.argv[0] = script
scope = runpy.run_path(script, run_name='__mir_bridge__')
Bridge = scope['Bridge']
original = Bridge.call
def call(self, frame):
    if frame.get('hook') != 'bridge.parse_execute':
        return original(self, frame)
    output, errors = io.StringIO(), io.StringIO()
    args, code = None, 0
    with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
        try:
            from tools.mir_executor.cli_parser import _build_parser
            argv, root = scope['_decode'](frame['args'])
            args = vars(_build_parser(root).parse_args(argv))
        except SystemExit as exc:
            if exc.code is None:
                code = 0
            elif isinstance(exc.code, int):
                code = int(exc.code)
                # CPython converts the status through C long before exit().
                limit = 2**31 - 1 if sys.platform == 'win32' else sys.maxsize
                if not -limit - 1 <= code <= limit:
                    code = -1
            else:
                code = 1
                print(exc.code, file=sys.stderr)
        except Exception as exc:
            code = 1
            print(type(exc).__name__ + ': ' + str(exc), file=sys.stderr)
    return dict(version=scope['VERSION'], id=frame['id'], ok=True, handle=None, error=None,
        result=dict(args=scope['_encode'](args), code=code, stdout=output.getvalue(), stderr=errors.getvalue()))
Bridge.call = call
sys.exit(scope['main']())
"#;
impl LocalBridge {
    /// No child is started when the target has no local hook file.
    pub fn start(config: BridgeConfig) -> Result<Option<Self>> {
        let cwd = config.target_root.clone();
        Self::start_in(config, &cwd)
    }
    /// Admission preserves the invoking command's working directory for hooks.
    pub fn start_in(config: BridgeConfig, cwd: &Path) -> Result<Option<Self>> {
        Self::start_inner(config, cwd, false)
    }
    pub(crate) fn start_with_parser(config: BridgeConfig, cwd: &Path) -> Result<Option<Self>> {
        Self::start_inner(config, cwd, true)
    }
    fn start_inner(config: BridgeConfig, cwd: &Path, parser: bool) -> Result<Option<Self>> {
        let policy = crate::executor_admission::native_policy(&config.target_root)
            .map_err(BridgeError::Configuration)?;
        if crate::executor_local::python_local_hooks_disabled(&config.target_root)
            .map_err(BridgeError::Configuration)?
        {
            return Ok(None);
        }
        match config
            .target_root
            .join("tools/mir_executor/local.py")
            .metadata()
        {
            Err(error)
                if matches!(
                    error.kind(),
                    io::ErrorKind::NotFound | io::ErrorKind::NotADirectory
                ) =>
            {
                return Ok(None);
            }
            Err(error) => return Err(error.into()),
            Ok(metadata) if !metadata.is_file() => {
                return Err(BridgeError::Protocol("local hook is not a file"));
            }
            Ok(_) => {}
        }
        if !config.interpreter.is_absolute()
            || !config.target_root.is_absolute()
            || !config.bridge_script.is_absolute()
        {
            return Err(BridgeError::Protocol(
                "interpreter, target and bridge paths must be absolute",
            ));
        }
        let mut command = Command::new(&config.interpreter);
        command.arg("-I");
        if parser {
            command.args(["-c", PARSER_BRIDGE]);
        }
        let mut child = command
            .arg(&config.bridge_script)
            .arg(&config.target_root)
            .current_dir(cwd)
            .env_clear()
            .envs(&config.environment)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::inherit())
            .spawn()?;
        let Some(mut stdin) = child.stdin.take() else {
            let _ = child.kill();
            let _ = child.wait();
            return Err(BridgeError::Protocol("missing child stdin"));
        };
        let Some(stdout) = child.stdout.take() else {
            let _ = child.kill();
            let _ = child.wait();
            return Err(BridgeError::Protocol("missing child stdout"));
        };
        let (requests, incoming) = mpsc::channel::<Vec<u8>>();
        let (outgoing, responses) = mpsc::channel();
        let worker = thread::spawn(move || {
            let mut reader = BufReader::new(stdout);
            if !send_frame(&mut reader, &outgoing) {
                return;
            }
            for request in incoming {
                if let Err(error) = stdin.write_all(&request).and_then(|()| stdin.flush()) {
                    let _ = outgoing.send(Err(error.into()));
                    return;
                }
                if !send_frame(&mut reader, &outgoing) {
                    return;
                }
            }
        });
        let mut bridge = Self {
            child,
            requests: Some(requests),
            responses,
            worker: Some(worker),
            hello: Value::Null,
            next_id: 1,
            timeout: config.timeout,
            closed: false,
        };
        let hello = bridge.receive()?;
        if hello.get("version").and_then(Value::as_str) != Some(PROTOCOL)
            || !hello
                .get("hooks")
                .is_some_and(|v| v.as_array().is_some_and(|a| a.iter().all(Value::is_string)))
            || !hello
                .get("register_execute_options")
                .is_some_and(Value::is_boolean)
        {
            return Err(BridgeError::Protocol("invalid hello"));
        }
        // Computed Python exports cannot be determined by the conservative
        // source preflight. Check hello before any callback or writer scope.
        if let Some(policy) = policy {
            for hook in policy.covered_hooks() {
                if hello["hooks"]
                    .as_array()
                    .is_some_and(|hooks| hooks.iter().any(|v| v == hook))
                {
                    return Err(BridgeError::Configuration(format!(
                        "native local policy configuration error: {hook} is also present in local.py"
                    )));
                }
            }
        }
        bridge.hello = hello;
        Ok(Some(bridge))
    }
    pub fn hello(&self) -> &Value {
        &self.hello
    }
    /// Returns the entire reply, preserving target-owned handles and hook errors.
    /// Options may contain `kwargs`, `handles`, and `force_handle` only.
    pub fn call(&mut self, hook: &str, args: Vec<Value>, options: Value) -> Result<Value> {
        if self.closed {
            return Err(BridgeError::Closed);
        }
        let Some(options) = options.as_object() else {
            return Err(BridgeError::Protocol("options must be an object"));
        };
        if options
            .keys()
            .any(|key| !matches!(key.as_str(), "kwargs" | "handles" | "force_handle"))
        {
            return Err(BridgeError::Protocol("unsupported call option"));
        }
        let id = self.next_id;
        self.next_id = self
            .next_id
            .checked_add(1)
            .ok_or(BridgeError::Protocol("request id exhausted"))?;
        let mut request = json!({"version":PROTOCOL,"id":id,"hook":hook,"args":args});
        if let Some(object) = request.as_object_mut() {
            object.extend(options.clone());
        }
        let mut frame = serde_json::to_vec(&request)?;
        if frame.len() >= MAX_FRAME_BYTES {
            return Err(BridgeError::FrameTooLarge);
        }
        frame.push(b'\n');
        if self
            .requests
            .as_ref()
            .ok_or(BridgeError::Closed)?
            .send(frame)
            .is_err()
        {
            self.close();
            return Err(BridgeError::Closed);
        }
        let response = self.receive()?;
        if response.get("version").and_then(Value::as_str) != Some(PROTOCOL)
            || response.get("id").and_then(Value::as_u64) != Some(id)
            || !response.get("ok").is_some_and(Value::is_boolean)
            || response.get("result").is_none()
            || !response
                .get("handle")
                .is_some_and(|value| value.is_null() || value.is_string())
            || (response.get("ok") == Some(&Value::Bool(false))
                && !response.get("error").is_some_and(|error| {
                    error.get("type").is_some_and(Value::is_string)
                        && error.get("message").is_some_and(Value::is_string)
                }))
        {
            self.close();
            return Err(BridgeError::Protocol("invalid response"));
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
    fn close(&mut self) {
        if self.closed {
            return;
        }
        self.closed = true;
        self.requests.take();
        let _ = self.child.kill();
        let _ = self.child.wait();
        // Descendants may retain pipes; cleanup must not wait indefinitely on them.
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
impl Drop for LocalBridge {
    fn drop(&mut self) {
        self.close();
    }
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
            return Err(BridgeError::Protocol("unexpected end of frame"));
        }
        let newline = available.iter().position(|byte| *byte == b'\n');
        let size = newline.unwrap_or(available.len());
        if frame.len() + size >= MAX_FRAME_BYTES {
            return Err(BridgeError::FrameTooLarge);
        }
        frame.extend_from_slice(&available[..size]);
        reader.consume(size + usize::from(newline.is_some()));
        if newline.is_some() {
            return Ok(serde_json::from_slice(&frame)?);
        }
    }
}
