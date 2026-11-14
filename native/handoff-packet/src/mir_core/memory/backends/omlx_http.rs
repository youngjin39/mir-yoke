//! Injected-transport port of the Python oMLX HTTP embedding backend.
use crate::mir_core::config::defaults::*;
use serde_json::{Value, json};
use std::collections::BTreeMap;

#[derive(Clone, Debug)]
pub struct BackendCfg {
    pub base_url: String,
    pub model: String,
    pub dim: i64,
    pub timeout_sec: i64,
    pub norm_tolerance: f64,
    pub api_key_env: String,
    pub auth_scheme: String,
}

impl Default for BackendCfg {
    fn default() -> Self {
        Self {
            base_url: DEFAULT_EMBEDDING_BASE_URL.into(),
            model: DEFAULT_EMBEDDING_MODEL.into(),
            dim: DEFAULT_EMBEDDING_DIM,
            timeout_sec: DEFAULT_EMBEDDING_TIMEOUT_SEC,
            norm_tolerance: DEFAULT_EMBEDDING_NORM_TOLERANCE,
            api_key_env: DEFAULT_EMBEDDING_API_KEY_ENV.into(),
            auth_scheme: "Bearer".into(),
        }
    }
}

impl BackendCfg {
    pub fn as_json(&self) -> Value {
        json!({"base_url": self.base_url, "model": self.model, "dim": self.dim,
            "timeout_sec": self.timeout_sec, "norm_tolerance": self.norm_tolerance,
            "api_key_env": self.api_key_env, "auth_scheme": self.auth_scheme})
    }
}

#[derive(Clone, Debug)]
pub struct HttpRequest {
    pub url: String,
    pub method: String,
    pub headers: BTreeMap<String, String>,
    pub body: Value,
    pub timeout: Value,
}

impl HttpRequest {
    pub fn as_json(&self) -> Value {
        json!({"url": self.url, "method": self.method, "headers": self.headers,
            "body": self.body, "timeout": self.timeout})
    }
}

#[derive(Clone, Debug)]
pub struct HttpResponse {
    pub status: u16,
    pub reason: String,
    pub body: Vec<u8>,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct HttpError {
    pub class: String,
    pub message: String,
}

impl HttpError {
    pub fn new(class: &str, message: impl Into<String>) -> Self {
        Self {
            class: class.into(),
            message: message.into(),
        }
    }
}

impl std::fmt::Display for HttpError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}: {}", self.class, self.message)
    }
}

impl std::error::Error for HttpError {}

/// The caller owns transport, connection policy and any real network authority.
pub trait Transport {
    fn send(&mut self, request: HttpRequest) -> Result<HttpResponse, HttpError>;
    fn close(&mut self) {}
}

pub struct OmlxHttpBackend<T> {
    cfg: BackendCfg,
    headers: BTreeMap<String, String>,
    transport: T,
    closed: bool,
}

impl<T: Transport> OmlxHttpBackend<T> {
    /// Resolve only the configured API key, once, through an injected environment lookup.
    pub fn new(cfg: BackendCfg, lookup: impl FnOnce(&str) -> String, transport: T) -> Self {
        let key = lookup(&cfg.api_key_env);
        let mut headers = BTreeMap::new();
        if !key.is_empty() {
            headers.insert("authorization".into(), format!("{} {key}", cfg.auth_scheme));
        }
        headers.insert("content-type".into(), "application/json".into());
        Self {
            cfg,
            headers,
            transport,
            closed: false,
        }
    }

    pub fn dimensions(&self) -> i64 {
        self.cfg.dim
    }
    pub fn config(&self) -> &BackendCfg {
        &self.cfg
    }
    pub fn is_closed(&self) -> bool {
        self.closed
    }
    pub fn transport(&self) -> &T {
        &self.transport
    }

    pub fn close(&mut self) {
        if !self.closed {
            self.closed = true;
            self.transport.close();
        }
    }

    pub fn encode(&mut self, texts: &[String]) -> Result<Vec<Vec<f64>>, HttpError> {
        if self.closed {
            return Err(HttpError::new(
                "RuntimeError",
                "Cannot send a request, as the client has been closed.",
            ));
        }
        let (base, fragment) = self
            .cfg
            .base_url
            .split_once('#')
            .unwrap_or((&self.cfg.base_url, ""));
        let url = format!(
            "{base}{}embeddings{}",
            if base.ends_with('/') { "" } else { "/" },
            if self.cfg.base_url.contains('#') {
                format!("#{fragment}")
            } else {
                String::new()
            }
        );
        let timeout = self.cfg.timeout_sec;
        let response = self.transport.send(HttpRequest {
            url: url.clone(),
            method: "POST".into(),
            headers: self.headers.clone(),
            body: json!({"model": self.cfg.model, "input": texts}),
            timeout: json!({"connect": timeout, "read": timeout,
                "write": timeout, "pool": timeout}),
        })?;
        if !(200..300).contains(&response.status) {
            let kind = match response.status {
                100..200 => "Informational response",
                300..400 => "Redirect response",
                400..500 => "Client error",
                500..600 => "Server error",
                _ => "Invalid status code",
            };
            return Err(HttpError::new(
                "HTTPStatusError",
                format!(
                    "{kind} '{} {}' for url '{url}'\nFor more information check: \
                 https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/{}",
                    response.status, response.reason, response.status
                ),
            ));
        }
        let body = parse_response(&response.body)?;
        let rows = body
            .get("data")
            .ok_or_else(|| HttpError::new("KeyError", "'data'"))?
            .as_array()
            .ok_or_else(|| HttpError::new("TypeError", "'NoneType' object is not iterable"))?;
        let mut vectors = Vec::new();
        for (i, row) in rows.iter().enumerate() {
            let v = row
                .get("embedding")
                .ok_or_else(|| HttpError::new("KeyError", "'embedding'"))?
                .as_array()
                .ok_or_else(|| {
                    HttpError::new("TypeError", "object of type 'NoneType' has no len()")
                })?;
            if v.len() as i64 != self.cfg.dim {
                return Err(HttpError::new(
                    "EmbeddingShapeError",
                    format!("row {i}: dim={} != {}", v.len(), self.cfg.dim),
                ));
            }
            let v: Vec<f64> = v.iter().map(number).collect::<Result<_, _>>()?;
            let norm = v.iter().map(|x| x * x).sum::<f64>().sqrt();
            // Deliberately preserve Python's NaN comparison (NaN is accepted).
            if (norm - 1.0).abs() > self.cfg.norm_tolerance {
                let norm = if norm.is_infinite() {
                    "inf".into()
                } else {
                    format!("{norm:.6}")
                };
                return Err(HttpError::new(
                    "EmbeddingNotNormalizedError",
                    format!("row {i}: L2 norm={norm} (tol={})", self.cfg.norm_tolerance),
                ));
            }
            vectors.push(v);
        }
        Ok(vectors)
    }
}

pub fn from_config<T: Transport>(
    cfg: BackendCfg,
    lookup: impl FnOnce(&str) -> String,
    transport: T,
) -> OmlxHttpBackend<T> {
    OmlxHttpBackend::new(cfg, lookup, transport)
}

pub fn build_default<T: Transport>(
    lookup: impl FnOnce(&str) -> String,
    transport: T,
) -> OmlxHttpBackend<T> {
    from_config(BackendCfg::default(), lookup, transport)
}

fn number(v: &Value) -> Result<f64, HttpError> {
    match v {
        Value::Number(n) => n
            .as_f64()
            .ok_or_else(|| HttpError::new("OverflowError", "int too large to convert to float")),
        Value::Bool(b) => Ok(if *b { 1.0 } else { 0.0 }),
        Value::String(s) if s == "\u{0}NaN" => Ok(f64::NAN),
        Value::String(s) if s == "\u{0}Infinity" => Ok(f64::INFINITY),
        Value::String(s) if s == "\u{0}-Infinity" => Ok(f64::NEG_INFINITY),
        _ => Err(HttpError::new(
            "TypeError",
            "can't multiply sequence by non-int of type 'str'",
        )),
    }
}

// Python's JSON reader accepts nonfinite literals; serde_json does not. Quote
// only tokens outside strings, with a private marker distinct from normal text.
fn parse_response(raw: &[u8]) -> Result<Value, HttpError> {
    let mut out = Vec::new();
    let (mut i, mut quoted, mut escaped) = (0, false, false);
    while i < raw.len() {
        let c = raw[i];
        if !quoted {
            let token = [b"-Infinity".as_slice(), b"Infinity", b"NaN"]
                .into_iter()
                .find(|token| raw[i..].starts_with(token));
            if let Some(token) = token {
                out.extend_from_slice(b"\"\\u0000");
                out.extend_from_slice(token);
                out.push(b'"');
                i += token.len();
                continue;
            }
        }
        out.push(c);
        if escaped {
            escaped = false;
        } else if quoted && c == b'\\' {
            escaped = true;
        } else if c == b'"' {
            quoted = !quoted;
        }
        i += 1;
    }
    serde_json::from_slice(&out).map_err(|e| {
        let reason = if e.to_string().starts_with("EOF while parsing an object") {
            "Expecting property name enclosed in double quotes".to_owned()
        } else {
            e.to_string()
                .split(" at line ")
                .next()
                .unwrap_or("Invalid JSON")
                .into()
        };
        let line = e.line();
        let column = e.column() + usize::from(e.is_eof());
        let pos = raw
            .split(|b| *b == b'\n')
            .take(line.saturating_sub(1))
            .map(|line| line.len() + 1)
            .sum::<usize>()
            + column.saturating_sub(1);
        HttpError::new(
            "JSONDecodeError",
            format!("{reason}: line {line} column {column} (char {pos})"),
        )
    })
}
