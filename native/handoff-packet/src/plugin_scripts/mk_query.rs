//! Library-only MCP client. Startup, deadlines and child cleanup are injected.
use super::ontology_check::{Doc, Error, Output, Result, error, load_json, object};
use super::ontology_runner::{expand, resolve};
use crate::{executor_brief_authority::python_space, executor_development_packet::py_repr};
use serde_json::{Value, json};
use std::{
    collections::BTreeMap,
    fs,
    io::{BufRead, Write},
    path::{Path, PathBuf},
};

pub const MAX_MESSAGE: usize = 4 * 1024 * 1024;
pub const CHILD_ENV: &[&str] = &[
    "PATH", "HOME", "USER", "LOGNAME", "LANG", "LC_ALL", "LC_CTYPE", "TMPDIR",
];
pub const FEDERATION_NAMESPACES: &[&str] =
    &["ns:core", "ns:shared-ops", "ns:fleet-ops", "ns:skills"];
pub fn unavailable(message: impl Into<String>) -> Error {
    error("Unavailable", message)
}
/// Host deadline marker; call() converts it to the public Unavailable exception.
pub fn timeout() -> Error {
    error("Timeout", "MCP request timed out")
}
fn d(v: impl Into<Value>) -> Doc {
    Doc::from(v.into())
}
fn obj(rows: Vec<(&str, Doc)>) -> Doc {
    object(rows)
}
fn empty() -> Doc {
    obj(vec![])
}

/// Like Path.resolve(strict=False), including symlink resolution of existing parents.
fn absolute(path: &Path, cwd: &Path) -> Result<PathBuf> {
    let full = if path.is_absolute() {
        path.to_path_buf()
    } else {
        cwd.join(path)
    };
    let mut out = PathBuf::new();
    for component in full.components() {
        match component {
            std::path::Component::CurDir => {}
            std::path::Component::ParentDir => {
                out.pop();
            }
            c => out.push(c.as_os_str()),
        }
        if out.exists() {
            out = resolve(&out)?;
        }
    }
    Ok(out)
}
pub fn config_path(explicit: Option<&str>, homes: &[PathBuf], cwd: &Path) -> Result<PathBuf> {
    let home = homes
        .first()
        .ok_or_else(|| error("IndexError", "list index out of range"))?;
    // The supplied first home is absolute; no ambient environment is consulted.
    if let Some(explicit) = explicit.filter(|s| !s.is_empty()) {
        return absolute(&expand(explicit, home), cwd);
    }
    let mut paths = Vec::new();
    for home in homes {
        paths.push(absolute(&home.join(".mir/knowledge-supply.json"), home)?);
    }
    Ok(paths
        .iter()
        .find(|p| p.is_file())
        .unwrap_or(&paths[0])
        .clone())
}
#[derive(Clone, Debug)]
pub struct Binding {
    pub command: Vec<String>,
    pub cwd: String,
    /// Retain integer versus floating-point JSON for injected-call observations.
    pub timeout: Value,
}
pub fn load_config(repo: &Path, path: &Path) -> Result<Binding> {
    if path.starts_with(repo) {
        return Err(unavailable(
            "configuration must be host-local, outside the repository",
        ));
    }
    if path.components().any(|c| {
        c.as_os_str()
            .to_str()
            .is_some_and(|p| p.starts_with(".env") || p == "secrets")
    }) {
        return Err(unavailable("configuration cannot be a secrets file"));
    }
    let raw = fs::read_to_string(path).map_err(|e| {
        unavailable(if e.kind() == std::io::ErrorKind::NotFound {
            "host-local configuration is missing"
        } else {
            "host-local configuration cannot be read"
        })
    })?;
    let config: Value = serde_json::from_str(&raw)
        .map_err(|_| unavailable("host-local configuration cannot be read"))?;
    let config = config
        .as_object()
        .filter(|m| m.len() == 1 && m.contains_key("memory_keeper"))
        .ok_or_else(|| unavailable("invalid host-local configuration"))?;
    let binding = config["memory_keeper"]
        .as_object()
        .filter(|m| {
            m.keys()
                .all(|k| ["command", "cwd", "timeout_sec"].contains(&k.as_str()))
        })
        .ok_or_else(|| {
            unavailable("invalid memory_keeper configuration; do not include secrets")
        })?;
    let command = binding
        .get("command")
        .and_then(Value::as_array)
        .filter(|a| !a.is_empty())
        .and_then(|a| {
            a.iter()
                .map(|v| {
                    v.as_str()
                        .filter(|s| !s.trim_matches(python_space).is_empty())
                        .map(str::to_owned)
                })
                .collect::<Option<Vec<_>>>()
        })
        .ok_or_else(|| unavailable("command must be a non-empty argument list"))?;
    let cwd = binding
        .get("cwd")
        .and_then(Value::as_str)
        .filter(|s| Path::new(s).is_absolute())
        .ok_or_else(|| unavailable("cwd must be an absolute host-local directory"))?;
    let timeout = binding.get("timeout_sec").cloned().unwrap_or(json!(30));
    if !timeout.as_f64().is_some_and(|n| n.is_finite() && n > 0.0) {
        return Err(unavailable("timeout_sec must be finite and positive"));
    }
    Ok(Binding {
        command,
        cwd: cwd.into(),
        timeout,
    })
}
fn send(writer: &mut dyn Write, fields: Vec<(&str, Doc)>) -> Result<()> {
    let mut message = vec![("jsonrpc", d("2.0"))];
    message.extend(fields);
    writer
        .write_all(format!("{}\n", obj(message).dump(false, None)).as_bytes())
        .and_then(|()| writer.flush())
        .map_err(|e| error("OSError", e.to_string()))
}
fn request(
    reader: &mut dyn BufRead,
    writer: &mut dyn Write,
    id: i64,
    method: &str,
    params: Doc,
) -> Result<Doc> {
    send(
        writer,
        vec![("id", d(id)), ("method", d(method)), ("params", params)],
    )?;
    loop {
        // A bounded take also limits allocation for a line with no newline.
        let mut line = Vec::new();
        std::io::Read::take(&mut *reader, (MAX_MESSAGE + 1) as u64)
            .read_until(b'\n', &mut line)
            .map_err(|e| error("OSError", e.to_string()))?;
        if line.is_empty() {
            return Err(unavailable("MCP server closed stdout"));
        }
        if line.len() > MAX_MESSAGE {
            return Err(unavailable(
                "MCP response exceeds the client message budget",
            ));
        }
        let text =
            std::str::from_utf8(&line).map_err(|e| error("UnicodeDecodeError", e.to_string()))?;
        let message = load_json(text).map_err(|e| {
            if text == "{\n" {
                error(
                    "JSONDecodeError",
                    concat!(
                        "Expecting property name enclosed in double quotes: ",
                        "line 2 column 1 (char 2)"
                    ),
                )
            } else {
                e
            }
        })?;
        if !matches!(message, Doc::Object(_)) || message.get("jsonrpc").text() != Some("2.0") {
            return Err(unavailable("invalid MCP response"));
        }
        if message.get("id").value() != json!(id) {
            continue;
        }
        if message.has("error") {
            return Err(unavailable("MCP request returned an error"));
        }
        if !matches!(message.get("result"), Doc::Object(_)) {
            return Err(unavailable("invalid MCP result"));
        }
        return Ok(message.get("result").clone());
    }
}
pub fn exchange(
    reader: &mut dyn BufRead,
    writer: &mut dyn Write,
    tool: &str,
    arguments: &Doc,
    client_name: &str,
) -> Result<Doc> {
    let initialized = request(
        reader,
        writer,
        1,
        "initialize",
        obj(vec![
            ("protocolVersion", d("2024-11-05")),
            ("capabilities", empty()),
            (
                "clientInfo",
                obj(vec![("name", d(client_name)), ("version", d("1.0"))]),
            ),
        ]),
    )?;
    if ![Some("2024-11-05"), Some("2025-03-26"), Some("2025-06-18")]
        .contains(&initialized.get("protocolVersion").text())
    {
        return Err(unavailable("unsupported MCP protocol version"));
    }
    send(writer, vec![("method", d("notifications/initialized"))])?;
    let result = request(
        reader,
        writer,
        2,
        "tools/call",
        obj(vec![("name", d(tool)), ("arguments", arguments.clone())]),
    )?;
    if truth(result.get("isError")) {
        return Err(unavailable("MCP tool returned an error"));
    }
    if matches!(result.get("structuredContent"), Doc::Object(_)) {
        return Ok(result.get("structuredContent").clone());
    }
    if result.get("content") == &Doc::Array(vec![]) {
        return Ok(empty());
    }
    for item in result.get("content").list() {
        if matches!(item, Doc::Object(_)) && item.get("type").text() == Some("text") {
            let value = load_json(item.get("text").text().unwrap_or(""))?;
            if matches!(value, Doc::Object(_)) {
                return Ok(value);
            }
        }
    }
    Err(unavailable("MCP tool returned no JSON object"))
}
fn truth(doc: &Doc) -> bool {
    match doc {
        Doc::Object(m) => !m.is_empty(),
        Doc::Array(a) => !a.is_empty(),
        Doc::Scalar(Value::Null) => false,
        Doc::Scalar(Value::Bool(b)) => *b,
        Doc::Scalar(Value::Number(n)) => n.as_f64() != Some(0.0),
        Doc::Scalar(Value::String(s)) => !s.is_empty(),
        Doc::Scalar(Value::Array(a)) => !a.is_empty(),
        Doc::Scalar(Value::Object(m)) => !m.is_empty(),
    }
}
/// Implementations own child creation and a worker deadline that bounds writes and startup.
/// finish must terminate the owned group on POSIX (TERM, then KILL; KILL on timeout),
/// kill a running Windows child, wait/reap, join the worker and close both pipes.
/// It is always called after successful start, including exchange/deadline failures.
pub trait ChildHost {
    fn start(
        &mut self,
        command: &[String],
        cwd: &str,
        env: &BTreeMap<String, String>,
    ) -> Result<()>;
    fn exchange(&mut self, timeout: f64, tool: &str, args: &Doc, name: &str) -> Result<Doc>;
    fn finish(&mut self, timed_out: bool);
}
pub fn call(
    host: &mut dyn ChildHost,
    binding: &Binding,
    env: &BTreeMap<String, String>,
    tool: &str,
    arguments: &Doc,
    client_name: &str,
) -> Result<Doc> {
    let env = env
        .iter()
        .filter(|(k, _)| CHILD_ENV.contains(&k.as_str()))
        .map(|(k, v)| (k.clone(), v.clone()))
        .collect();
    host.start(&binding.command, &binding.cwd, &env)
        .map_err(|_| unavailable("MCP command could not be started"))?;
    let result = host.exchange(
        binding.timeout.as_f64().unwrap_or(30.0),
        tool,
        arguments,
        client_name,
    );
    let timed_out = result.as_ref().err().is_some_and(|e| e.class == "Timeout");
    host.finish(timed_out);
    result.map_err(|_| {
        unavailable(if timed_out {
            "MCP request timed out"
        } else {
            "MCP exchange failed"
        })
    })
}
pub fn fence_namespaces(pack: &mut Doc, namespaces: Option<&[String]>) -> bool {
    let allowed: Vec<&str> = match namespaces.filter(|n| !n.is_empty()) {
        Some(n) => n.iter().map(String::as_str).collect(),
        None => FEDERATION_NAMESPACES.to_vec(),
    };
    let mut dropped = false;
    for field in ["nodes", "citations"] {
        if !pack.has(field) {
            continue;
        }
        let entries = pack.get(field).list();
        let kept: Vec<_> = entries
            .iter()
            .filter(|e| {
                matches!(e, Doc::Object(_))
                    && e.get("namespace")
                        .text()
                        .is_some_and(|n| allowed.contains(&n))
            })
            .cloned()
            .collect();
        dropped = dropped || kept.len() != entries.len();
        pack.set(field, Doc::Array(kept));
    }
    if dropped {
        let mut degradation = pack.get("degradation").list().to_vec();
        degradation.push(obj(vec![
            ("scope", d("client")),
            ("reasons", Doc::Array(vec![d("namespace_filtered")])),
        ]));
        pack.set("degradation", Doc::Array(degradation));
    }
    dropped
}
pub trait MainHost {
    fn load_config(&mut self, repo: &Path) -> Result<Binding>;
    fn call(&mut self, binding: &Binding, tool: &str, args: &Doc, name: &str) -> Result<Doc>;
}
/// Optional library composition; no OS process or environment lookup is performed.
pub struct Client<'a> {
    pub config: PathBuf,
    pub env: BTreeMap<String, String>,
    pub child: &'a mut dyn ChildHost,
}
impl MainHost for Client<'_> {
    fn load_config(&mut self, repo: &Path) -> Result<Binding> {
        load_config(repo, &self.config)
    }
    fn call(&mut self, binding: &Binding, tool: &str, args: &Doc, name: &str) -> Result<Doc> {
        call(self.child, binding, &self.env, tool, args, name)
    }
}
struct Args {
    repo: PathBuf,
    name: Option<String>,
    soft: bool,
    command: String,
    query: String,
    namespaces: Option<Vec<String>>,
    k: Option<i64>,
    verdict: String,
}
const USAGE: &str = concat!(
    "usage: mk_query.py [-h] [--repo REPO] [--client-name CLIENT_NAME] [--soft]\n",
    "                   {query,feedback} ...\n"
);
fn parse(argv: &[String], cwd: &Path) -> std::result::Result<Args, String> {
    let mut a = Args {
        repo: cwd.into(),
        name: None,
        soft: false,
        command: String::new(),
        query: String::new(),
        namespaces: None,
        k: None,
        verdict: String::new(),
    };
    let mut i = 0;
    while i < argv.len() {
        match argv[i].as_str() {
            "--soft" => a.soft = true,
            "--repo" | "--client-name" => {
                let flag = &argv[i];
                i += 1;
                let value = argv
                    .get(i)
                    .filter(|s| !s.starts_with('-'))
                    .ok_or_else(|| format!("argument {flag}: expected one argument"))?;
                if flag == "--repo" {
                    a.repo = value.into();
                } else {
                    a.name = Some(value.clone());
                }
            }
            "query" | "feedback" => {
                a.command = argv[i].clone();
                i += 1;
                break;
            }
            v => {
                return Err(format!(
                    "argument command: invalid choice: {} (choose from query, feedback)",
                    py_repr(v)
                ));
            }
        }
        i += 1;
    }
    if a.command.is_empty() {
        return Err("the following arguments are required: command".into());
    }
    if a.command == "feedback" {
        a.query = argv
            .get(i)
            .cloned()
            .ok_or("the following arguments are required: node_ref, verdict")?;
        i += 1;
        a.verdict = argv
            .get(i)
            .cloned()
            .ok_or("the following arguments are required: verdict")?;
        if !["used", "confirmed", "contradicted", "acted_on"].contains(&a.verdict.as_str()) {
            return Err(format!(
                concat!(
                    "argument verdict: invalid choice: {} (choose from used, confirmed, ",
                    "contradicted, acted_on)"
                ),
                py_repr(&a.verdict)
            ));
        }
        i += 1;
    } else {
        let mut query = None;
        while i < argv.len() {
            match argv[i].as_str() {
                "--k" => {
                    i += 1;
                    let raw = argv.get(i).ok_or("argument --k: expected one argument")?;
                    let k = super::relations_query::cli_integer(raw).ok_or_else(|| {
                        format!("argument --k: invalid int value: {}", py_repr(raw))
                    })?;
                    if !(1..=100).contains(&k) {
                        return Err(format!(
                            "argument --k: invalid choice: {} (choose from {})",
                            py_repr(&k.to_string()),
                            (1..=100)
                                .map(|n| n.to_string())
                                .collect::<Vec<_>>()
                                .join(", ")
                        ));
                    }
                    a.k = Some(k);
                }
                "--namespaces" => {
                    i += 1;
                    let start = i;
                    while argv.get(i).is_some_and(|s| !s.starts_with('-')) {
                        i += 1;
                    }
                    if i == start {
                        return Err("argument --namespaces: expected at least one argument".into());
                    }
                    a.namespaces = Some(argv[start..i].to_vec());
                    continue;
                }
                v if !v.starts_with('-') && query.is_none() => query = Some(v.to_owned()),
                _ => break,
            }
            i += 1;
        }
        a.query = query.ok_or("the following arguments are required: query")?;
    }
    if i < argv.len() {
        return Err(format!("unrecognized arguments: {}", argv[i..].join(" ")));
    }
    Ok(a)
}
fn unicode_json(doc: &Doc) -> String {
    // Preserve insertion order and Python separators with ensure_ascii=False.
    match doc {
        Doc::Object(m) => format!(
            "{{{}}}",
            m.iter()
                .map(|(k, v)| format!("{}: {}", json!(k), unicode_json(v)))
                .collect::<Vec<_>>()
                .join(", ")
        ),
        Doc::Array(a) => format!(
            "[{}]",
            a.iter().map(unicode_json).collect::<Vec<_>>().join(", ")
        ),
        Doc::Scalar(v) => v.to_string(),
    }
}
pub fn main(argv: &[String], cwd: &Path, host: &mut dyn MainHost) -> Output {
    let mut out = Output {
        exit: 2,
        stdout: String::new(),
        stderr: String::new(),
    };
    let command = argv
        .iter()
        .find(|s| ["query", "feedback"].contains(&s.as_str()))
        .map(String::as_str)
        .unwrap_or("");
    let usage = match command {
        "query" => concat!(
            "usage: mk_query.py query [-h] [--namespaces NAMESPACES [NAMESPACES ...]]\n",
            "                         [--k 1..100]\n                         query\n"
        ),
        "feedback" => concat!(
            "usage: mk_query.py feedback [-h]\n",
            "                            node_ref {used,confirmed,contradicted,acted_on}\n"
        ),
        _ => USAGE,
    };
    if argv.iter().any(|s| s == "--help" || s == "-h") {
        out.exit = 0;
        let tail = match command {
            "query" => concat!(
                "\npositional arguments:\n  query\n\noptions:\n",
                "  -h, --help            show this help message and exit\n",
                "  --namespaces NAMESPACES [NAMESPACES ...]\n  --k 1..100\n"
            ),
            "feedback" => concat!(
                "\npositional arguments:\n  node_ref\n",
                "  {used,confirmed,contradicted,acted_on}\n\noptions:\n",
                "  -h, --help            show this help message and exit\n"
            ),
            _ => concat!(
                "\nOn-demand Memory Keeper MCP stdio client; Python 3.11+, ",
                "standard library only.\n\npositional arguments:\n  {query,feedback}\n",
                "    query               retrieve a ContextPack\n",
                "    feedback            record explicit feedback for a received node ref\n",
                "\noptions:\n  -h, --help            show this help message and exit\n",
                "  --repo REPO\n  --client-name CLIENT_NAME\n",
                "                        telemetry label only; never authentication\n",
                "  --soft                exit 0 when external knowledge is unavailable\n"
            ),
        };
        out.stdout = format!("{usage}{tail}");
        return out;
    }
    let argv: Vec<String> = argv
        .iter()
        .flat_map(|arg| {
            if let Some((key, value)) = arg.split_once('=')
                && ["--repo", "--client-name", "--k", "--namespaces"].contains(&key)
            {
                vec![key.to_owned(), value.to_owned()]
            } else {
                vec![arg.clone()]
            }
        })
        .collect();
    let a = match parse(&argv, cwd) {
        Ok(a) => a,
        Err(e) => {
            let (usage, suffix) = if e.starts_with("unrecognized arguments") {
                (USAGE, String::new())
            } else {
                (
                    usage,
                    if command.is_empty() {
                        String::new()
                    } else {
                        format!(" {command}")
                    },
                )
            };
            out.stderr = format!("{usage}mk_query.py{suffix}: error: {e}\n");
            return out;
        }
    };
    let result = (|| {
        let repo = absolute(&a.repo, cwd)?;
        let binding = host.load_config(&repo)?;
        let (tool, arguments) = if a.command == "query" {
            if a.query.trim_matches(python_space).is_empty() || a.query.chars().count() > 8192 {
                return Err(unavailable(
                    "query must contain 1..8192 nonblank characters",
                ));
            }
            let mut args = obj(vec![("query", d(a.query.as_str()))]);
            if let Some(ns) = &a.namespaces {
                args.set("namespaces", Doc::from(json!(ns)));
            }
            if let Some(k) = a.k {
                args.set("k", d(k));
            }
            ("federation_serve", args)
        } else {
            (
                "feedback",
                obj(vec![
                    ("node_ref", d(a.query.as_str())),
                    ("verdict", d(a.verdict.as_str())),
                ]),
            )
        };
        let name = a
            .name
            .as_deref()
            .filter(|s| !s.is_empty())
            .map(str::to_owned)
            .unwrap_or_else(|| {
                format!(
                    "{}-agent",
                    repo.file_name().and_then(|s| s.to_str()).unwrap_or("")
                )
            });
        let mut result = host.call(&binding, tool, &arguments, &name)?;
        let filtered =
            a.command == "query" && fence_namespaces(&mut result, a.namespaces.as_deref());
        if a.command == "query"
            && result.get("status").text() != Some("refused")
            && (!truth(&result) || result.get("nodes") == &Doc::Array(vec![]))
        {
            let mut empty = obj(vec![
                ("status", d("empty")),
                ("reason", d("ContextPack contains no nodes")),
            ]);
            if filtered {
                empty.set("degradation", result.get("degradation").clone());
            }
            out.stdout = format!("{}\n", empty.dump(false, None));
            return Ok(if a.soft { 0 } else { 2 });
        }
        out.stdout = format!("{}\n", unicode_json(&result));
        Ok(0)
    })();
    match result {
        Ok(exit) => out.exit = exit,
        Err(e) => {
            let reason = if e.class == "Unavailable" {
                e.message
            } else {
                "host-local configuration unavailable".into()
            };
            out.stdout = format!(
                "{}\n",
                obj(vec![("status", d("unavailable")), ("reason", d(reason))]).dump(false, None)
            );
            out.exit = if a.soft { 0 } else { 2 };
        }
    }
    out
}
