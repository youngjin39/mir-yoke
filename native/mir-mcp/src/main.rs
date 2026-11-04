#![forbid(unsafe_code)]
#![deny(clippy::unwrap_used, clippy::expect_used, clippy::panic)]
mod forward;
mod protocol;
mod wire;
use forward::Forward;
use protocol::{Protocol, Response, error};
use serde_json::Value;
use std::io::{self, BufRead, Write};
const FRAME: usize = 65536;
const OUTPUT: usize = 16384;
fn serve(forward: Forward) -> io::Result<()> {
    let stdin = io::stdin();
    let mut input = stdin.lock();
    let stdout = io::stdout();
    let mut out = stdout.lock();
    let mut state = Protocol::default();
    loop {
        let mut raw = Vec::new();
        let mut oversized = false;
        loop {
            let chunk = input.fill_buf()?;
            if chunk.is_empty() {
                break;
            }
            let n = chunk
                .iter()
                .position(|b| *b == b'\n')
                .map_or(chunk.len(), |p| p + 1);
            let end = chunk[n - 1] == b'\n';
            if raw.len() + n > FRAME {
                oversized = true;
            }
            if !oversized {
                raw.extend_from_slice(&chunk[..n]);
            }
            input.consume(n);
            if end {
                break;
            }
        }
        if raw.is_empty() && !oversized {
            return Ok(());
        }
        let response = if oversized {
            Response::Value(error(Value::Null, -32600, "E_LIMIT"))
        } else {
            match wire::parse(&raw) {
                Ok(v) => state.request(&v, &raw, &forward),
                Err(code) => Response::Value(error(
                    Value::Null,
                    if code == "E_FORMAT" { -32700 } else { -32600 },
                    code,
                )),
            }
        };
        let bytes = match response {
            Response::Silent => continue,
            Response::Raw(bytes) => bytes,
            Response::Value(v) => {
                let mut bytes = serde_json::to_vec(&v)?;
                if bytes.len() + 1 > OUTPUT {
                    bytes = serde_json::to_vec(&error(v["id"].clone(), -32603, "E_LIMIT"))?;
                }
                bytes.push(b'\n');
                bytes
            }
        };
        if out.write_all(&bytes).and_then(|()| out.flush()).is_err() {
            return Ok(());
        }
    }
}
fn main() {
    let mut args = std::env::args_os().skip(1);
    let mut python = None;
    let mut script = None;
    while let Some(arg) = args.next() {
        if arg == "--reference-python" {
            python = args.next();
        } else if arg == "--reference-script" {
            script = args.next();
        } else {
            std::process::exit(2);
        }
    }
    let (Some(python), Some(script)) = (python, script) else {
        std::process::exit(2);
    };
    if serve(Forward { python, script }).is_err() {
        std::process::exit(1);
    }
}
