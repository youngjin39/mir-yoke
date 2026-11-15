use super::capability::Manager;
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value, json};
use std::io::{BufRead, BufReader, Read, Seek, Write};
#[cfg(unix)]
use std::os::fd::AsRawFd;
use std::path::Path;
use std::process::{Child, ChildStdin, ChildStdout, Command, ExitStatus, Stdio};
#[derive(Debug, Deserialize, Serialize, PartialEq)]
#[serde(tag = "stream", content = "data")]
#[serde(rename_all = "lowercase", deny_unknown_fields)]
pub enum Event {
    Stdout(Vec<u8>),
    Stderr(Vec<u8>),
}
#[derive(Debug, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Exception {
    pub class: String,
    pub message: String,
}
#[derive(Debug, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Reply {
    #[serde(deserialize_with = "Value::deserialize")]
    pub value: Value,
    #[serde(deserialize_with = "Option::<Exception>::deserialize")]
    pub error: Option<Exception>,
    pub events: Vec<Event>,
}
#[derive(Debug, PartialEq, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Failure {
    Io,
    Eof,
    Malformed,
    Child,
}
#[derive(Debug)]
pub struct Error {
    pub kind: Failure,
    pub message: String,
    pub status: std::io::Result<ExitStatus>,
    pub stderr: Option<std::thread::Result<std::io::Result<Vec<u8>>>>,
}
pub struct ProductionManager {
    child: Child,
    input: Option<ChildStdin>,
    output: BufReader<ChildStdout>,
    stderr: std::fs::File,
    pub last_reply: Option<Reply>,
}
impl ProductionManager {
    pub fn start(cli: &Path, root: &Path) -> std::io::Result<Self> {
        let stderr = tempfile::tempfile()?;
        let mut child = Command::new(cli)
            .args(["run-python", "--project-root"])
            .arg(root)
            .args(["--", "-m", "mir.cli.capability_manager_bridge"])
            .current_dir(root)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(stderr.try_clone()?)
            .spawn()?;
        let input = child.stdin.take();
        let output = BufReader::new(child.stdout.take().ok_or(std::io::ErrorKind::BrokenPipe)?);
        #[cfg(unix)]
        crate::executor_process_unix::nonblocking(output.get_ref().as_raw_fd())?;
        Ok(Self {
            child,
            input,
            output,
            stderr,
            last_reply: None,
        })
    }
    pub fn request(&mut self, request: Value) -> Result<Reply, Error> {
        let exchange = || -> std::io::Result<String> {
            let input = self.input.as_mut().ok_or(std::io::ErrorKind::BrokenPipe)?;
            writeln!(input, "{request}")?;
            input.flush()?;
            let mut line = String::new();
            loop {
                let exited = self.child.try_wait()?.is_some();
                match self.output.read_line(&mut line) {
                    Ok(_) => break,
                    Err(e) if e.kind() == std::io::ErrorKind::WouldBlock && exited => break,
                    Err(e) if e.kind() == std::io::ErrorKind::WouldBlock => {
                        std::thread::sleep(std::time::Duration::from_millis(1));
                    }
                    Err(e) => return Err(e),
                }
            }
            Ok(line)
        }();
        let result = match exchange {
            Err(e) => Err((Failure::Io, e.to_string())),
            Ok(line) if line.is_empty() => Err((Failure::Eof, "manager reply EOF".into())),
            Ok(line) if !line.ends_with('\n') => Err((Failure::Malformed, "partial reply".into())),
            Ok(line) => {
                serde_json::from_str(&line).map_err(|e| (Failure::Malformed, e.to_string()))
            }
        };
        result.map_err(|(kind, message)| self.stop(kind, message))
    }
    fn stop(&mut self, kind: Failure, message: String) -> Error {
        self.input.take();
        for _ in 0..50 {
            if self.child.try_wait().ok().flatten().is_some() {
                break;
            }
            std::thread::sleep(std::time::Duration::from_millis(1));
        }
        let _ = self.child.kill();
        let status = self.child.wait();
        let stderr = self.stderr.rewind().and_then(|()| {
            let size = self.stderr.metadata()?.len();
            let reader = BufReader::new(&mut self.stderr);
            reader.take(size).bytes().collect()
        });
        Error {
            kind,
            message,
            status,
            stderr: Some(Ok(stderr)),
        }
    }
    pub fn finish(&mut self) -> Result<(), Error> {
        let error = self.stop(Failure::Child, "manager child failed".into());
        let success = error.status.as_ref().is_ok_and(ExitStatus::success);
        let clean = !matches!(error.stderr, Some(Err(_) | Ok(Err(_))));
        if success && clean { Ok(()) } else { Err(error) }
    }
    fn invoke(&mut self, request: Value) -> Result<Value, String> {
        self.last_reply = None;
        let terminal = request["op"] == "call";
        let reply = self.request(request).map_err(|e| format!("{e:?}"))?;
        let result = match &reply.error {
            Some(e) => Err(e.message.clone()),
            None => Ok(reply.value.clone()),
        };
        self.last_reply = Some(reply);
        if terminal {
            self.finish().map_err(|e| format!("{e:?}"))?;
        }
        result
    }
}
impl Manager for ProductionManager {
    fn initialize(&mut self, p: &Path, c: Option<&Path>, h: Option<&Path>) -> Result<(), String> {
        let encode = |path: &Path| serde_json::to_value(path).map_err(|e| e.to_string());
        let mut kwargs = Map::new();
        for (name, path) in [("config_path", c), ("capability_home", h)] {
            if let Some(path) = path {
                kwargs.insert(name.into(), encode(path)?);
            }
        }
        let root = encode(p)?;
        self.invoke(json!({"op":"initialize", "args":[root], "path_args":[0], "path_kwargs":kwargs.keys().collect::<Vec<_>>(), "kwargs":kwargs}))
            .map(|_| ())
    }
    fn call(&mut self, op: &str, args: Vec<Value>, k: Map<String, Value>) -> Result<Value, String> {
        self.invoke(json!({"op":"call", "method":op, "args":args, "kwargs":k}))
    }
}
impl Drop for ProductionManager {
    fn drop(&mut self) {
        self.input.take();
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}
