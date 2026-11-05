use crate::forward::Forward;
use serde_json::{Value, json};
const MODERN: &str = "2026-07-28";
const LEGACY: &str = "2025-11-25";
const VERSION: &str = "0.13.70";
const PV: &str = "io.modelcontextprotocol/protocolVersion";
const CAPS: &str = "io.modelcontextprotocol/clientCapabilities";
const INFO: &str = "io.modelcontextprotocol/clientInfo";
pub fn error(id: Value, n: i32, code: &str) -> Value {
    json!({"jsonrpc":"2.0","id":id,"error":{"code":n,"message":code,"data":{"code":code}}})
}
fn info(v: &Value) -> bool {
    v.is_object() && v["name"].is_string() && v["version"].is_string()
}
fn keys(v: &Value, allowed: &[&str]) -> bool {
    v.as_object()
        .is_some_and(|o| o.keys().all(|k| allowed.contains(&k.as_str())))
}
#[derive(Default)]
pub struct Protocol {
    pending: bool,
    initialized: bool,
    worker: bool,
}
pub enum Response {
    Value(Value),
    Raw(Vec<u8>),
    Silent,
}
impl Protocol {
    pub fn worker() -> Self {
        Self {
            pending: false,
            initialized: true,
            worker: true,
        }
    }
    pub fn request(&mut self, v: &Value, raw: &[u8], forward: &Forward) -> Response {
        let mut id = v.get("id").cloned().unwrap_or(Value::Null);
        let has_id = v.get("id").is_some();
        let valid_id = id.as_str().is_some_and(|s| s.len() <= 256)
            || id
                .as_i64()
                .is_some_and(|n| n.unsigned_abs() <= 9007199254740991);
        if has_id && !valid_id {
            id = Value::Null;
            return Response::Value(error(id, -32602, "E_SCHEMA"));
        }
        let schema = |id| Response::Value(error(id, -32602, "E_SCHEMA"));
        if !keys(v, &["jsonrpc", "id", "method", "params"])
            || v["jsonrpc"] != "2.0"
            || !v["method"].is_string()
        {
            return schema(id);
        }
        let empty = json!({});
        let params = v.get("params").unwrap_or(&empty);
        if !params.is_object() || params.get("_meta").is_some_and(|m| !m.is_object()) {
            return schema(id);
        }
        let method = v["method"].as_str().unwrap_or("");
        if method == "notifications/initialized" {
            if has_id || !self.pending || params != &empty {
                return schema(id);
            }
            self.pending = false;
            self.initialized = true;
            return Response::Silent;
        }
        if !has_id {
            return Response::Silent;
        }
        if method == "initialize" {
            if self.initialized
                || self.pending
                || !keys(
                    params,
                    &["protocolVersion", "clientInfo", "capabilities", "_meta"],
                )
                || !params["protocolVersion"].is_string()
                || !info(&params["clientInfo"])
                || !params["capabilities"].is_object()
            {
                return schema(id);
            }
            self.pending = true;
            return Response::Value(json!({"jsonrpc":"2.0","id":id,"result":{
                "protocolVersion":LEGACY,"capabilities":{"tools":{}},"serverInfo":{"name":"mir-mcp","version":VERSION}}}));
        }
        let meta = &params["_meta"];
        let modern = params.get("_meta").is_some() && !(self.initialized && meta.get(PV).is_none());
        let mut requested = "";
        if modern {
            let Some(version) = meta[PV].as_str() else {
                return schema(id);
            };
            requested = version;
            if version == MODERN
                && (!meta[CAPS].is_object() || meta.get(INFO).is_some_and(|i| !info(i)))
            {
                return schema(id);
            }
        }
        if (modern && requested != MODERN) || (!modern && !self.initialized) {
            let mut e = error(id, -32022, "E_VERSION");
            e["error"]["message"] = json!("Unsupported protocol version");
            e["error"]["data"]["supported"] = json!([MODERN, LEGACY]);
            e["error"]["data"]["requested"] = json!(requested);
            return Response::Value(e);
        }
        let ordinary: Vec<_> = params
            .as_object()
            .into_iter()
            .flat_map(|o| o.keys())
            .filter(|k| k.as_str() != "_meta")
            .collect();
        let mut result = match method {
            "server/discover" if modern && ordinary.is_empty() => {
                json!({"supportedVersions":[MODERN,LEGACY],"capabilities":{"tools":{}},"_meta":{ "io.modelcontextprotocol/serverInfo":{"name":"mir-mcp","version":VERSION}}})
            }
            "tools/list" if ordinary.is_empty() => {
                match serde_json::from_str(include_str!("../tools.json")) {
                    Ok(v) => v,
                    Err(_) => return Response::Value(error(id, -32603, "E_FORMAT")),
                }
            }
            "tools/call"
                if ordinary.len() == 2
                    && ordinary.iter().any(|k| k.as_str() == "name")
                    && ordinary.iter().any(|k| k.as_str() == "arguments") =>
            {
                if self.worker {
                    crate::native::call(params["name"].as_str().unwrap_or(""), &params["arguments"])
                } else {
                    let response = if matches!(
                        params["name"].as_str(),
                        Some(
                            "handoff_pins"
                                | "ontology_validate"
                                | "ontology_lookup"
                                | "ontology_impact"
                        )
                    ) {
                        Forward::native(raw).and_then(|bytes| {
                            let value = crate::wire::parse(&bytes)?;
                            if value["result"]["structuredContent"]["error"]["code"] == "FORWARD" {
                                forward.call(raw)
                            } else {
                                Ok(bytes)
                            }
                        })
                    } else {
                        forward.call(raw)
                    };
                    match response {
                        Ok(bytes) => return Response::Raw(bytes),
                        Err(code) => {
                            json!({"content":[{"type":"text","text":format!("{{\"code\":\"{code}\"}}") }],"structuredContent":{
                        "ok":false,"data":null,"error":{"code":code},"next_cursor":null,"profile_protections":"available"},"isError":true})
                        }
                    }
                }
            }
            "tools/list" | "tools/call" | "server/discover" => return schema(id),
            _ => return Response::Value(error(id, -32601, "E_SCHEMA")),
        };
        if modern {
            result["resultType"] = json!("complete");
            if method != "tools/call" {
                result["ttlMs"] = json!(3600000);
                result["cacheScope"] = json!("public");
            }
        }
        Response::Value(json!({"jsonrpc":"2.0","id":id,"result":result}))
    }
}
