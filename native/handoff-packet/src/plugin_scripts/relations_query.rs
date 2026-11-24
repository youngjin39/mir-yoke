//! Standalone selective-relations command and local filesystem adapter.
use crate::{executor_verifier, relation_terms::PURPOSES, relations_reader::Query};
pub use crate::{
    relation_terms::{
        allowed, endpoint_path, file_relation, has_control_characters, normalized_locator, notices,
        unique,
    },
    relations_reader::{
        DEFAULT_DEPTH, DEFAULT_GRAPH, DEFAULT_MAX_EDGES, Edge, MAX_ANCHOR_CHARS, MAX_DEPTH,
        MAX_EDGES, MAX_GRAPH_BYTES, MAX_GRAPH_EDGES, Reader, RelationsError, Result, parse_graph,
        relative, row, validate_endpoint,
    },
};
use serde_json::{Value, json};
use std::{
    fs,
    io::Read,
    path::{Path, PathBuf},
};

fn error(code: &'static str) -> RelationsError {
    RelationsError::Code(code)
}
const FIXED: &[&str] = &[
    ".env*",
    "*.db*",
    "*.sqlite*",
    ".netrc",
    ".npmrc",
    ".pypirc",
    ".git-credentials",
    "credentials*",
    "token.json",
    "tokens.json",
    "id_rsa*",
    "id_ed25519*",
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "*.keystore",
];
pub struct LocalReader {
    pub root: PathBuf,
    patterns: Vec<String>,
}
// Resolve even dangling symlinks before applying containment and target protections.
fn resolve(path: &Path, allow_missing: bool, links: usize) -> Result<PathBuf> {
    if links > 40 {
        return Err(error("E_PATH"));
    }
    if let Ok(p) = fs::canonicalize(path) {
        return Ok(p);
    }
    let parent = path.parent().ok_or_else(|| error("E_PATH"))?;
    let name = path.file_name().ok_or_else(|| error("E_PATH"))?;
    let parent = resolve(parent, allow_missing, links)?;
    let candidate = parent.join(name);
    match fs::symlink_metadata(&candidate) {
        Ok(meta) if meta.file_type().is_symlink() => {
            let target = fs::read_link(&candidate).map_err(|_| error("E_PATH"))?;
            resolve(&parent.join(target), allow_missing, links + 1)
        }
        Err(e) if allow_missing && e.kind() == std::io::ErrorKind::NotFound => Ok(candidate),
        _ => Err(error("E_PATH")),
    }
}
impl LocalReader {
    pub fn new(root: &Path) -> Result<Self> {
        let root = fs::canonicalize(root).map_err(|_| error("E_PATH"))?;
        if !root.is_dir() {
            return Err(error("E_PATH"));
        }
        let mut reader = Self {
            root,
            patterns: vec![],
        };
        let profile = ".mir/repo-profile.toml";
        if reader.exists(profile)? {
            let raw = reader.read(profile)?;
            if raw.len() > 65536 {
                return Err(error("E_LIMIT"));
            }
            let parse = || -> Result<Vec<String>> {
                let text = std::str::from_utf8(&raw).map_err(|_| error("E_FORMAT"))?;
                let doc: toml::Table = toml::from_str(text).map_err(|_| error("E_FORMAT"))?;
                let mut patterns = Vec::new();
                for (section, key) in [
                    ("paths", "protected_paths"),
                    ("boundaries", "secrets"),
                    ("preserve", "agent_memory_paths"),
                ] {
                    if let Some(section) = doc.get(section) {
                        let table = section.as_table().ok_or_else(|| error("E_FORMAT"))?;
                        if let Some(values) = table.get(key) {
                            for value in values.as_array().ok_or_else(|| error("E_FORMAT"))? {
                                patterns.push(relative(value.as_str())?.to_lowercase());
                            }
                        }
                    }
                }
                if patterns.len() > 256 {
                    return Err(error("E_FORMAT"));
                }
                Ok(patterns)
            };
            reader.patterns = parse().map_err(|_| error("E_FORMAT"))?;
        }
        Ok(reader)
    }
    fn protected(&self, path: &str) -> bool {
        let path = path.to_lowercase();
        let parts: Vec<_> = path.split('/').collect();
        parts
            .iter()
            .any(|p| ["secrets", ".ssh", ".aws", ".gnupg"].contains(p))
            || parts.iter().any(|p| FIXED.iter().any(|f| glob(f, p)))
            || self.patterns.iter().any(|p| {
                glob(p, &path)
                    || (!p.contains(['*', '?', '['])
                        && path.starts_with(&format!("{}/", p.trim_end_matches('/'))))
            })
    }
}
fn glob(pattern: &str, text: &str) -> bool {
    executor_verifier::matches(pattern, text).unwrap_or(false)
}
impl Reader for LocalReader {
    fn path(&self, value: &str, allow_missing: bool) -> Result<PathBuf> {
        let pure = relative(Some(value))?;
        if self.protected(&pure) {
            return Err(error("E_PROTECTED"));
        }
        let resolved = resolve(&self.root.join(pure), allow_missing, 0)?;
        let target = resolved
            .strip_prefix(&self.root)
            .map_err(|_| error("E_PATH"))?;
        let target = target
            .to_str()
            .ok_or_else(|| error("E_PATH"))?
            .replace('\\', "/");
        if self.protected(&target) {
            return Err(error("E_PROTECTED"));
        }
        if resolved.exists() && !resolved.is_file() {
            return Err(error("E_PATH"));
        }
        Ok(resolved)
    }
    fn exists(&self, value: &str) -> Result<bool> {
        Ok(self.path(value, true)?.is_file())
    }
    fn read(&self, value: &str) -> Result<Vec<u8>> {
        let target = self.path(value, false)?;
        let mut raw = Vec::new();
        fs::File::open(target)
            .and_then(|f| f.take((MAX_GRAPH_BYTES + 1) as u64).read_to_end(&mut raw))
            .map_err(|_| error("E_IO"))?;
        if raw.len() > MAX_GRAPH_BYTES {
            return Err(error("E_LIMIT"));
        }
        Ok(raw)
    }
    fn endpoint_issue(&self, relative: &str) -> Result<Option<String>> {
        Ok(match self.path(relative, true) {
            Ok(p) => (!p.exists()).then(|| "unavailable endpoint".into()),
            Err(RelationsError::Code("E_PROTECTED")) => Some("protected endpoint".into()),
            Err(_) => Some("endpoint symlink escapes root".into()),
        })
    }
}
pub struct Options<'a> {
    pub root: &'a Path,
    pub graph: &'a str,
    pub depth: Value,
    pub max_edges: Value,
}
impl<'a> Options<'a> {
    pub fn new(root: &'a Path) -> Self {
        Self {
            root,
            graph: DEFAULT_GRAPH,
            depth: Value::Null,
            max_edges: json!(DEFAULT_MAX_EDGES),
        }
    }
}
pub fn query_relations(
    anchor: &Value,
    purpose: &Value,
    options: &Options<'_>,
    io: Option<&dyn Reader>,
) -> Result<Value> {
    let query = Query::new(anchor, purpose, &options.depth, &options.max_edges)?;
    let local;
    let reader = match io {
        Some(r) => r,
        None => {
            local = LocalReader::new(options.root)?;
            &local as &dyn Reader
        }
    };
    query.read(options.graph, reader)
}
// Explicit key order is part of the script's stdout contract (serde maps are sorted).
fn render_value(v: &Value) -> String {
    match v {
        Value::Object(m) => {
            let keys: Vec<&str> = if m.contains_key("anchor") {
                vec![
                    "anchor",
                    "purpose",
                    "scope",
                    "source",
                    "edges",
                    "notices",
                    "truncated",
                    "resolved_anchors",
                ]
            } else if m.contains_key("source_line") {
                vec!["source", "relation", "target", "source_line"]
            } else if m.contains_key("graph") {
                vec!["graph", "sha256"]
            } else {
                m.keys().map(String::as_str).collect()
            };
            format!(
                "{{{}}}",
                keys.iter()
                    .filter_map(|k| m
                        .get(*k)
                        .map(|v| format!("{}:{}", json!(k), render_value(v))))
                    .collect::<Vec<_>>()
                    .join(",")
            )
        }
        Value::Array(a) => format!(
            "[{}]",
            a.iter().map(render_value).collect::<Vec<_>>().join(",")
        ),
        _ => v.to_string(),
    }
}
pub struct Output {
    pub exit: i32,
    pub stdout: String,
    pub stderr: String,
}
const USAGE: &str = concat!(
    "usage: relations_query.py [-h] --root ROOT [--graph GRAPH] [--depth DEPTH]\n",
    "                          [--max-edges MAX_EDGES]\n",
    "                          anchor\n",
    "                          {implementation,verification,impact,dependencies}\n"
);
fn cli_error(message: &str) -> Output {
    Output {
        exit: 2,
        stdout: String::new(),
        stderr: format!("{USAGE}relations_query.py: error: {message}\n"),
    }
}
use crate::python_decimal;
pub(crate) fn cli_integer(text: &str) -> Option<i64> {
    let text = text.trim();
    let digits = text.strip_prefix(['+', '-']).unwrap_or(text);
    let mut normalized = String::new();
    let mut previous_digit = false;
    let mut count = 0;
    for c in digits.chars() {
        if c == '_' {
            if !previous_digit {
                return None;
            }
            previous_digit = false;
        } else {
            normalized.push(char::from(b'0' + python_decimal::decimal_digit(c)? as u8));
            previous_digit = true;
            count += 1;
        }
    }
    if !previous_digit || count > 4300 {
        return None;
    }
    if text.starts_with('-') {
        normalized.insert(0, '-');
    }
    // Arbitrarily large Python integers parse successfully and saturate with their sign.
    Some(normalized.parse().unwrap_or(if text.starts_with('-') {
        i64::MIN
    } else {
        i64::MAX
    }))
}
const HELP: &str = concat!(
    "\nPassive stdlib-only reader for the documented three-string YAML edge subset.\n",
    "Traversal follows mir.core.relations. Injected I/O owns every repository read\n",
    "and endpoint check; its refusals deliberately propagate to the calling server.\n",
    "\npositional arguments:\n  anchor\n",
    "  {implementation,verification,impact,dependencies}\n\noptions:\n",
    "  -h, --help            show this help message and exit\n",
    "  --root ROOT\n  --graph GRAPH\n  --depth DEPTH\n  --max-edges MAX_EDGES\n"
);
/// argv excludes the program name; this function never exits the host process.
pub fn main(argv: &[String]) -> Output {
    let mut positional = Vec::new();
    let (mut root, mut graph) = (None, DEFAULT_GRAPH.to_owned());
    let (mut depth, mut cap) = (Value::Null, json!(DEFAULT_MAX_EDGES));
    let mut i = 0;
    let mut options = true;
    while i < argv.len() {
        let raw_arg = &argv[i];
        i += 1;
        let (name, attached) = if options && raw_arg.starts_with("--") {
            raw_arg
                .split_once('=')
                .map_or((raw_arg.as_str(), None), |(a, b)| (a, Some(b)))
        } else {
            (raw_arg.as_str(), None)
        };
        let choices = ["--root", "--graph", "--depth", "--max-edges", "--help"];
        let arg = if options && name.starts_with("--") && name.len() > 2 {
            choices
                .iter()
                .find(|c| c.starts_with(name))
                .copied()
                .unwrap_or(name)
        } else {
            name
        };
        if options && ["-h", "--help"].contains(&arg) {
            if let Some(v) = attached {
                return cli_error(&format!(
                    "argument -h/--help: ignored explicit argument '{v}'"
                ));
            }
            return Output {
                exit: 0,
                stdout: format!("{USAGE}{HELP}"),
                stderr: String::new(),
            };
        }
        if options && arg == "--" {
            options = false;
            continue;
        }
        if options && ["--root", "--graph", "--depth", "--max-edges"].contains(&arg) {
            let v = if let Some(v) = attached {
                v
            } else {
                let Some(v) = argv.get(i) else {
                    return cli_error(&format!("argument {arg}: expected one argument"));
                };
                if v.starts_with('-') && v.parse::<f64>().is_err() {
                    return cli_error(&format!("argument {arg}: expected one argument"));
                }
                i += 1;
                v.as_str()
            };
            match arg {
                "--root" => root = Some(PathBuf::from(v)),
                "--graph" => graph = v.to_owned(),
                _ => {
                    let Some(n) = cli_integer(v) else {
                        return cli_error(&format!("argument {arg}: invalid int value: '{v}'"));
                    };
                    if arg == "--depth" {
                        depth = json!(n);
                    } else {
                        cap = json!(n);
                    }
                }
            }
        } else if options && arg.starts_with('-') {
            return cli_error(&format!("unrecognized arguments: {arg}"));
        } else {
            positional.push(arg.to_owned());
        }
    }
    if let Some(p) = positional.get(1)
        && !PURPOSES.contains(&p.as_str())
    {
        return cli_error(&format!(
            "argument purpose: invalid choice: {} (choose from \
implementation, verification, impact, dependencies)",
            crate::executor_development_packet::py_repr(p)
        ));
    }
    let mut missing = Vec::new();
    if positional.is_empty() {
        missing.push("anchor");
    }
    if positional.len() < 2 {
        missing.push("purpose");
    }
    if root.is_none() {
        missing.push("--root");
    }
    if !missing.is_empty() {
        return cli_error(&format!(
            "the following arguments are required: {}",
            missing.join(", ")
        ));
    }
    if positional.len() > 2 {
        return cli_error(&format!(
            "unrecognized arguments: {}",
            positional[2..].join(" ")
        ));
    }
    let root = root.unwrap_or_default();
    let o = Options {
        root: &root,
        graph: &graph,
        depth,
        max_edges: cap,
    };
    match query_relations(&json!(positional[0]), &json!(positional[1]), &o, None) {
        Ok(v) => Output {
            exit: 0,
            stdout: format!("{}\n", render_value(&v)),
            stderr: String::new(),
        },
        Err(e) => Output {
            exit: 1,
            stdout: format!("{{\"ok\": false, \"error\": {{\"code\": \"{e}\"}}}}\n"),
            stderr: String::new(),
        },
    }
}
