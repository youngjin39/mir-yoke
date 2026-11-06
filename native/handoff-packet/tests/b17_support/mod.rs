//! Synthetic inputs mirror Python CASES; no expected fixture cell is reused.
use handoff_packet::mir_core::memory::backends::omlx_http::{
    BackendCfg, HttpError, HttpRequest, HttpResponse, OmlxHttpBackend, Transport, build_default,
    from_config,
};
use serde_json::{Value, json};

pub fn exempt_headers() -> &'static [&'static str] {
    &[
        "user-agent",
        "accept",
        "accept-encoding",
        "connection",
        "host",
        "content-length",
    ]
}

struct Synthetic {
    mode: String,
    requests: Vec<Value>,
}

impl Transport for Synthetic {
    fn send(&mut self, request: HttpRequest) -> Result<HttpResponse, HttpError> {
        self.requests.push(request.as_json());
        if self.mode == "timeout" {
            return Err(HttpError::new("TimeoutException", "synthetic timeout"));
        }
        let vectors = match self.mode.as_str() {
            "wrong_dim" => vec!["[1.0]"],
            "zero" => vec!["[0.0,0.0]"],
            "norm" => vec!["[2.0,0.0]"],
            "tolerance_inside" => vec!["[1.0005,0.0]"],
            "tolerance_outside" => vec!["[1.002,0.0]"],
            "nan" => vec!["[NaN,0.0]"],
            "inf" => vec!["[Infinity,0.0]"],
            "count_empty" | "empty_input" => vec![],
            "count_excess" => vec!["[1.0,0.0]"; 3],
            _ => vec!["[1.0,0.0]"],
        };
        let body = if self.mode == "json" {
            "{".into()
        } else {
            // Keep nonfinite JSON literals as bytes, just as json.dumps does.
            let rows = vectors
                .iter()
                .map(|v| format!("{{\"embedding\":{v}}}"))
                .collect::<Vec<_>>()
                .join(",");
            format!("{{\"data\":[{rows}]}}")
        };
        Ok(HttpResponse {
            status: if self.mode == "status" { 503 } else { 200 },
            reason: if self.mode == "status" {
                "Service Unavailable"
            } else {
                "OK"
            }
            .into(),
            body: body.into_bytes(),
        })
    }
}

fn observe(result: Result<Vec<Vec<f64>>, HttpError>) -> Value {
    match result {
        Err(error) => json!({"error": [error.class, error.message]}),
        Ok(rows) => {
            let rows: Vec<Vec<Value>> = rows
                .into_iter()
                .map(|row| {
                    row.into_iter()
                        .map(|x| {
                            if x.is_nan() {
                                json!("NaN")
                            } else if x == f64::INFINITY {
                                json!("Infinity")
                            } else if x == f64::NEG_INFINITY {
                                json!("-Infinity")
                            } else {
                                json!(x)
                            }
                        })
                        .collect()
                })
                .collect();
            json!({"value": rows})
        }
    }
}

pub fn replay(name: &str) -> Value {
    let mode = name.strip_prefix("http.").expect("HTTP case name");
    let transport = Synthetic {
        mode: mode.into(),
        requests: Vec::new(),
    };
    let cfg = BackendCfg {
        base_url: "https://embedding.invalid/v1/".into(),
        model: "synthetic-model".into(),
        dim: 2,
        timeout_sec: 7,
        norm_tolerance: 0.001,
        api_key_env: "SYNTHETIC_KEY".into(),
        auth_scheme: "Token".into(),
    };
    let key = if mode == "no_key" {
        ""
    } else {
        "synthetic-key"
    };
    let lookup = |name: &str| {
        assert_eq!(
            name,
            if mode == "default" {
                "OMLX_API_KEY"
            } else {
                "SYNTHETIC_KEY"
            }
        );
        key.to_owned()
    };
    let mut backend = match mode {
        "default" => build_default(lookup, transport),
        "config" => from_config(cfg, lookup, transport),
        _ => OmlxHttpBackend::new(cfg, lookup, transport),
    };
    let cfg = backend.config().as_json();
    let dim = backend.dimensions();
    let before = backend.is_closed();
    let texts = if mode == "empty_input" {
        Vec::new()
    } else {
        vec!["alpha".into(), "\u{e9}".into()]
    };
    let first = observe(backend.encode(&texts));
    let after_encode = backend.is_closed();
    let second = observe(backend.encode(&texts));
    backend.close();
    backend.close();
    let closed = backend.is_closed();
    let after_close = observe(backend.encode(&texts));
    json!({"value": {"dim": dim, "cfg": cfg, "before": before, "first": first,
        "after_encode": after_encode, "second": second, "closed": closed,
        "after_close": after_close, "requests": backend.transport().requests}})
}
