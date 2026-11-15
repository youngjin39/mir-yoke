use super::capability::Manager;
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value, json};
use std::io::{BufRead, BufReader, Read, Seek, Write};
#[cfg(unix)]
use std::os::fd::AsRawFd;
use std::path::Path;
use std::process::{Child, Command, ExitStatus, Stdio};
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
/// Text redirection performed by the pinned caller; raw fd writes inherit.
#[cfg(unix)]
#[derive(Clone, Copy)]
pub enum Output {
    Console,
    Activate,
    Finalize,
}
pub struct ProductionManager {
    child: Child,
    input: Option<Box<dyn Write>>,
    output: BufReader<Box<dyn Read>>,
    stderr: Option<std::fs::File>,
    #[cfg(unix)]
    duplex: Option<std::os::unix::net::UnixStream>,
    pub last_reply: Option<Reply>,
}
impl ProductionManager {
    fn command(cli: &Path, root: &Path) -> Command {
        let mut command = Command::new(cli);
        command
            .args(["run-python", "--project-root"])
            .arg(root)
            .args(["--", "-m", "mir.cli.capability_manager_bridge"])
            .current_dir(root);
        command
    }
    /// Same JSON lines over duplex stdin, leaving fd1/2 on the caller's streams.
    #[cfg(unix)]
    pub fn start_with_output(cli: &Path, root: &Path, output: Output) -> std::io::Result<Self> {
        let (duplex, child_socket) = std::os::unix::net::UnixStream::pair()?;
        let input = duplex.try_clone()?;
        let reader = duplex.try_clone()?;
        let child = Self::command(cli, root)
            .arg(match output {
                Output::Console => "console",
                Output::Activate => "activate",
                Output::Finalize => "finalize",
            })
            .stdin(Stdio::from(std::os::fd::OwnedFd::from(child_socket)))
            .spawn()?;
        Ok(Self {
            child,
            input: Some(Box::new(input)),
            output: BufReader::new(Box::new(reader)),
            stderr: None,
            duplex: Some(duplex),
            last_reply: None,
        })
    }
    pub fn start(cli: &Path, root: &Path) -> std::io::Result<Self> {
        let stderr = tempfile::tempfile()?;
        let mut child = Self::command(cli, root)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(stderr.try_clone()?)
            .spawn()?;
        let input = child.stdin.take().map(|s| Box::new(s) as Box<dyn Write>);
        let output = child.stdout.take().ok_or(std::io::ErrorKind::BrokenPipe)?;
        #[cfg(unix)]
        crate::executor_process_unix::nonblocking(output.as_raw_fd())?;
        Ok(Self {
            child,
            input,
            output: BufReader::new(Box::new(output)),
            stderr: Some(stderr),
            #[cfg(unix)]
            duplex: None,
            last_reply: None,
        })
    }
    pub fn request(&mut self, request: Value) -> Result<Reply, Error> {
        let exchange = || -> std::io::Result<String> {
            #[cfg(unix)]
            if let Some(socket) = &self.duplex {
                socket.set_nonblocking(false)?;
            }
            let input = self.input.as_mut().ok_or(std::io::ErrorKind::BrokenPipe)?;
            writeln!(input, "{request}")?;
            input.flush()?;
            #[cfg(unix)]
            if let Some(socket) = &self.duplex {
                socket.set_nonblocking(true)?;
            }
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
        #[cfg(unix)]
        if let Some(socket) = &self.duplex {
            let _ = socket.shutdown(std::net::Shutdown::Write);
        }
        for _ in 0..50 {
            if self.child.try_wait().ok().flatten().is_some() {
                break;
            }
            std::thread::sleep(std::time::Duration::from_millis(1));
        }
        let _ = self.child.kill();
        let status = self.child.wait();
        let stderr = self.stderr.as_mut().map(|stderr| {
            Ok(stderr.rewind().and_then(|()| {
                let size = stderr.metadata()?.len();
                BufReader::new(stderr).take(size).bytes().collect()
            }))
        });
        Error {
            kind,
            message,
            status,
            stderr,
        }
    }
    pub fn finish(&mut self) -> Result<(), Error> {
        let error = self.stop(Failure::Child, "manager child failed".into());
        let success = error.status.as_ref().is_ok_and(ExitStatus::success);
        let clean = !matches!(error.stderr, Some(Err(_) | Ok(Err(_))));
        if success && clean { Ok(()) } else { Err(error) }
    }
    fn transport(error: Error) -> super::capability::Error {
        super::capability::Error::new("RuntimeError", error.message)
    }
    pub fn import(&mut self) -> Result<(), super::capability::Error> {
        self.invoke(json!({"op":"import"})).map(|_| ())
    }
    fn invoke(&mut self, request: Value) -> Result<Value, super::capability::Error> {
        self.last_reply = None;
        let terminal = request["op"] == "call";
        let reply = self.request(request).map_err(Self::transport)?;
        let result = match &reply.error {
            Some(e) => Err(super::capability::Error::new(
                e.class.clone(),
                e.message.clone(),
            )),
            None => Ok(reply.value.clone()),
        };
        self.last_reply = Some(reply);
        if terminal || result.is_err() {
            let finished = self.finish().map_err(Self::transport);
            if result.is_ok() {
                finished?;
            }
        }
        result
    }
}
impl Manager for ProductionManager {
    fn initialize(
        &mut self,
        p: &Path,
        c: Option<&Path>,
        h: Option<&Path>,
    ) -> Result<(), super::capability::Error> {
        let encode = |path: &Path| {
            serde_json::to_value(path)
                .map_err(|e| super::capability::Error::new("UnicodeEncodeError", e.to_string()))
        };
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
    fn call(
        &mut self,
        op: &str,
        args: Vec<Value>,
        k: Map<String, Value>,
    ) -> Result<Value, super::capability::Error> {
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
