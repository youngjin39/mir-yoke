//! HTTP(S) transport for the configured oMLX provider. No redirect or retry.
use crate::mir_core::memory::backends::omlx_http::{
    HttpError, HttpRequest, HttpResponse, Transport,
};
use std::io::Write;
use std::process::{Command, Stdio};

pub struct HttpTransport;
impl Transport for HttpTransport {
    fn send(&mut self, request: HttpRequest) -> Result<HttpResponse, HttpError> {
        let mut cmd = Command::new("/usr/bin/curl");
        cmd.args(["-q", "--silent", "--show-error", "--include", "--max-time"])
            .arg(request.timeout["read"].to_string())
            .args(["--request", &request.method]);
        for (name, value) in request.headers {
            cmd.arg("--header").arg(format!("{name}: {value}"));
        }
        let mut child = cmd
            .args(["--data-binary", "@-", "--url", &request.url])
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .map_err(|e| HttpError::new("OSError", e.to_string()))?;
        if let Some(mut input) = child.stdin.take() {
            input
                .write_all(request.body.to_string().as_bytes())
                .map_err(|e| HttpError::new("OSError", e.to_string()))?;
        }
        let out = child
            .wait_with_output()
            .map_err(|e| HttpError::new("OSError", e.to_string()))?;
        if !out.status.success() {
            return Err(match out.status.code() {
                Some(28) => HttpError::new("ReadTimeout", "timed out"),
                Some(7) => HttpError::new("ConnectError", "[Errno 61] Connection refused"),
                Some(52) => HttpError::new(
                    "RemoteProtocolError",
                    "Server disconnected without sending a response.",
                ),
                _ => HttpError::new(
                    "RequestError",
                    String::from_utf8_lossy(&out.stderr).trim_end().to_owned(),
                ),
            });
        }
        let mut bytes = out.stdout.as_slice();
        loop {
            let end = bytes
                .windows(4)
                .position(|s| s == b"\r\n\r\n")
                .ok_or_else(|| {
                    HttpError::new(
                        "RemoteProtocolError",
                        "Server disconnected without sending a response.",
                    )
                })?;
            let header = String::from_utf8_lossy(&bytes[..end]);
            let line = header
                .split('\n')
                .next()
                .unwrap_or("")
                .trim_end_matches('\r');
            let mut parts = line.splitn(3, ' ');
            parts.next();
            let status = parts
                .next()
                .and_then(|s| s.parse::<u16>().ok())
                .ok_or_else(|| HttpError::new("RemoteProtocolError", "illegal status line"))?;
            let reason = parts.next().unwrap_or("").to_owned();
            bytes = &bytes[end + 4..];
            if status < 200 || reason == "Connection established" {
                continue;
            }
            return Ok(HttpResponse {
                status,
                reason,
                body: bytes.to_vec(),
            });
        }
    }
}
