//! Port of the standalone selective-relations reader, independent of YAML libraries.
use crate::{digest::sha256, executor_verifier, mir_core::relations as r};
pub use r::{
    allowed, endpoint_path, file_relation, has_control_characters, normalized_locator, notices,
    unique,
};
use serde_json::{Value, json};
use std::{
    collections::{BTreeMap, HashSet},
    fmt, fs,
    io::Read,
    path::{Path, PathBuf},
};
pub const DEFAULT_GRAPH: &str = "spec/graph.yaml";
pub const DEFAULT_DEPTH: usize = 3;
pub const DEFAULT_MAX_EDGES: usize = 16;
pub const MAX_DEPTH: usize = 4;
pub const MAX_EDGES: usize = 64;
pub const MAX_ANCHOR_CHARS: usize = 4096;
pub const MAX_GRAPH_BYTES: usize = 1024 * 1024;
pub const MAX_GRAPH_EDGES: usize = 10_000;
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum RelationsError {
    Code(&'static str),
    /// An injected reader owns its refusal class and message.
    Refusal {
        class: String,
        message: String,
    },
}
impl fmt::Display for RelationsError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Code(code) => f.write_str(code),
            Self::Refusal { message, .. } => f.write_str(message),
        }
    }
}
impl std::error::Error for RelationsError {}
pub type Result<T> = std::result::Result<T, RelationsError>;
fn error(code: &'static str) -> RelationsError {
    RelationsError::Code(code)
}
#[derive(Debug, Clone)]
pub struct Edge {
    pub source: String,
    pub relation: String,
    pub target: String,
    pub source_line: usize,
}
impl Edge {
    pub fn as_dict(&self) -> Value {
        json!({"source":self.source,"relation":self.relation,
        "target":self.target,"source_line":self.source_line})
    }
}
fn nonstring(value: &str) -> bool {
    const PATTERN: &str = concat!(
        r"(?i)\A(?:~|null|true|false|yes|no|on|off|",
        r"[-+]?(?:[0-9][0-9_]*(?::[0-9_]+)*(?:\.[0-9_]*)?(?:[eE][-+]?[0-9]+)?|",
        r"\.[0-9_]+(?:[eE][-+]?[0-9]+)?|0[xX][0-9a-fA-F_]+|0[bB][01_]+|\.inf|\.nan)|",
        r"[0-9]{4}-[0-9]{1,2}-[0-9]{1,2}(?:[Tt ].*)?)\z"
    );
    // Fixed, reviewed regex; compilation failure rejects the scalar.
    {
        static RE: std::sync::OnceLock<Option<regex::Regex>> = std::sync::OnceLock::new();
        RE.get_or_init(|| regex::Regex::new(PATTERN).ok())
            .as_ref()
            .is_none_or(|re| re.is_match(value))
    }
}
// Python str.strip also admits the four ASCII information separators.
fn python_space(c: char) -> bool {
    c.is_whitespace() || matches!(c, '\u{1c}'..='\u{1f}')
}
pub fn row(text: &str) -> Result<Vec<String>> {
    let bad = || error("E_FORMAT");
    if !text.starts_with('[') {
        return Err(bad());
    }
    let mut values = Vec::new();
    let mut i = 1;
    loop {
        while text.as_bytes().get(i) == Some(&b' ') {
            i += 1;
        }
        let quote = *text.as_bytes().get(i).ok_or_else(bad)?;
        if matches!(quote, b',' | b']') {
            return Err(bad());
        }
        let value;
        if quote == b'"' {
            let mut stream = serde_json::Deserializer::from_str(&text[i..]).into_iter::<String>();
            value = stream.next().ok_or_else(bad)?.map_err(|_| bad())?;
            i += stream.byte_offset();
        } else if quote == b'\'' {
            i += 1;
            let mut out = String::new();
            loop {
                let c = text[i..].chars().next().ok_or_else(bad)?;
                i += c.len_utf8();
                if c == '\'' {
                    if text.as_bytes().get(i) == Some(&b'\'') {
                        out.push('\'');
                        i += 1;
                    } else {
                        break;
                    }
                } else {
                    out.push(c);
                }
            }
            value = out;
        } else {
            let start = i;
            while i < text.len() && !matches!(text.as_bytes()[i], b',' | b']') {
                i += 1;
            }
            value = text[start..i].trim_matches(python_space).to_owned();
            if value.is_empty()
                || value.contains(['[', ']', '{', '}', '!', '&', '*', '#', '\'', '"', '`'])
                || value.starts_with(['@', '|', '>', '%', '?', ':'])
                || value.starts_with("- ")
                || value.ends_with(':')
                || value.contains(": ")
                || nonstring(&value)
            {
                return Err(bad());
            }
        }
        if value.is_empty() || has_control_characters(&value) {
            return Err(bad());
        }
        if value.len() > 4096 {
            return Err(error("E_LIMIT"));
        }
        values.push(value);
        while text.as_bytes().get(i) == Some(&b' ') {
            i += 1;
        }
        let sep = *text.as_bytes().get(i).ok_or_else(bad)?;
        i += 1;
        if sep == b']' {
            let tail = &text[i..];
            if !tail.is_empty()
                && !(tail.starts_with(' ')
                    && tail.trim_start_matches(python_space).starts_with('#'))
                && !tail.trim_matches(python_space).is_empty()
            {
                return Err(bad());
            }
            break;
        }
        if sep != b',' || values.len() >= 3 {
            return Err(bad());
        }
    }
    if values.len() != 3 {
        return Err(bad());
    }
    Ok(values)
}
pub fn parse_graph(raw: &[u8]) -> Result<Vec<Edge>> {
    let bad = || error("E_FORMAT");
    let text = std::str::from_utf8(raw).map_err(|_| bad())?;
    let mut edges = Vec::new();
    let (mut found, mut empty, mut indent) = (false, false, None);
    for (index, line) in text.split('\n').enumerate() {
        if line.contains('\t') || line.trim_end_matches('\r').contains('\r') {
            return Err(bad());
        }
        let line = line.trim_end_matches('\r');
        let stripped = line.trim_matches(python_space);
        if stripped.is_empty() || stripped.starts_with('#') {
            continue;
        }
        if !found {
            let header = line
                .split('#')
                .next()
                .unwrap_or_default()
                .trim_end_matches(' ');
            if !header.starts_with("edges:")
                || !["", "[]"].contains(&header[6..].trim_start_matches(' '))
            {
                return Err(bad());
            }
            found = true;
            empty = header.contains("[]");
            continue;
        }
        let leading = line.len() - line.trim_start_matches(' ').len();
        if indent.is_none() {
            indent = Some(leading);
        }
        if empty || indent != Some(leading) || !stripped.starts_with("- ") {
            return Err(bad());
        }
        let v = row(stripped[2..].trim_start_matches(python_space))?;
        edges.push(Edge {
            source: v[0].clone(),
            relation: v[1].clone(),
            target: v[2].clone(),
            source_line: index + 1,
        });
        if edges.len() > MAX_GRAPH_EDGES {
            return Err(error("E_LIMIT"));
        }
    }
    if !found || (edges.is_empty() && !empty) {
        return Err(bad());
    }
    Ok(edges)
}
pub fn relative(value: Option<&str>) -> Result<String> {
    let value = value
        .filter(|v| !v.is_empty() && !has_control_characters(v))
        .ok_or_else(|| error("E_PATH"))?;
    if value.len() > 4096 {
        return Err(error("E_LIMIT"));
    }
    let path = value.replace('\\', "/");
    if path.starts_with('/')
        || (path.as_bytes().get(1) == Some(&b':') && path.as_bytes()[0].is_ascii_alphabetic())
        || path.split('/').any(|p| p == "..")
    {
        return Err(error("E_PATH"));
    }
    let path = path
        .split('/')
        .filter(|p| !p.is_empty() && *p != ".")
        .collect::<Vec<_>>()
        .join("/");
    if path.is_empty() {
        return Err(error("E_PATH"));
    }
    Ok(path)
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
/// Reader errors propagate unchanged for external guards.
pub trait Reader {
    fn path(&self, relative: &str, allow_missing: bool) -> Result<PathBuf>;
    fn exists(&self, relative: &str) -> Result<bool>;
    fn read(&self, relative: &str) -> Result<Vec<u8>>;
    fn is_local(&self) -> bool {
        false
    }
}
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
    fn is_local(&self) -> bool {
        true
    }
}
pub fn validate_endpoint(value: &str, reader: &dyn Reader, force: bool) -> Result<Option<String>> {
    let Some(path) = endpoint_path(value, force) else {
        return Ok(None);
    };
    let Ok(relative) = relative(Some(path)) else {
        return Ok(Some("unsafe path endpoint".into()));
    };
    if !reader.is_local() {
        reader.path(&relative, true)?;
        return Ok((!reader.exists(&relative)?).then(|| "unavailable endpoint".into()));
    }
    Ok(match reader.path(&relative, true) {
        Ok(p) => (!p.exists()).then(|| "unavailable endpoint".into()),
        Err(RelationsError::Code("E_PROTECTED")) => Some("protected endpoint".into()),
        Err(_) => Some("endpoint symlink escapes root".into()),
    })
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
fn limit(v: &Value, max: usize) -> Result<usize> {
    v.as_u64()
        .filter(|n| *n >= 1 && *n <= max as u64)
        .map(|n| n as usize)
        .ok_or_else(|| error("E_SCHEMA"))
}
fn eligible(frontier: &HashSet<String>, graph: &[Edge], purpose: &str) -> bool {
    graph.iter().any(|e| {
        (frontier.contains(&e.source) && allowed(purpose, &e.relation, false))
            || (frontier.contains(&e.target) && allowed(purpose, &e.relation, true))
    })
}
fn result(
    meta: (&str, &str, &str, &str),
    edges: &[Edge],
    notes: Vec<String>,
    resolved: Vec<String>,
) -> Value {
    let (anchor, purpose, digest, source) = meta;
    json!({"anchor":anchor,"purpose":purpose,"scope":"declared_spec_relations_only",
        "source":{"graph":source,"sha256":digest},"edges":edges.iter().map(Edge::as_dict)
        .collect::<Vec<_>>(),"truncated":notes.iter().any(|s| s.starts_with("truncated:")),
        "notices":notes,"resolved_anchors":resolved})
}
pub fn query_relations(
    anchor: &Value,
    purpose: &Value,
    options: &Options<'_>,
    io: Option<&dyn Reader>,
) -> Result<Value> {
    let purpose = purpose
        .as_str()
        .filter(|p| r::PURPOSES.contains(p))
        .ok_or_else(|| error("E_SCHEMA"))?;
    let depth = if options.depth.is_null() {
        if purpose == "dependencies" {
            1
        } else {
            DEFAULT_DEPTH
        }
    } else {
        limit(&options.depth, MAX_DEPTH)?
    };
    let max_edges = limit(&options.max_edges, MAX_EDGES)?;
    let anchor = anchor
        .as_str()
        .filter(|a| !a.is_empty() && !has_control_characters(a))
        .ok_or_else(|| error("E_SCHEMA"))?;
    if anchor.len() > MAX_ANCHOR_CHARS {
        return Err(error("E_LIMIT"));
    }
    let local;
    let reader = match io {
        Some(r) => r,
        None => {
            local = LocalReader::new(options.root)?;
            &local as &dyn Reader
        }
    };
    if let Some(path) = endpoint_path(anchor, false) {
        relative(Some(path))?;
        reader.path(path, true)?;
    }
    let source = relative(Some(options.graph))?;
    let raw = reader.read(&source)?;
    if raw.len() > MAX_GRAPH_BYTES {
        return Err(error("E_LIMIT"));
    }
    let graph = parse_graph(&raw)?;
    let digest = sha256(&raw);
    let meta = (anchor, purpose, digest.as_str(), source.as_str());
    let nodes = unique(
        graph
            .iter()
            .flat_map(|e| [e.source.clone(), e.target.clone()])
            .collect(),
    );
    let file_node = graph
        .iter()
        .any(|e| e.target == anchor && file_relation(&e.relation));
    if (!nodes.iter().any(|n| n == anchor) || file_node)
        && validate_endpoint(anchor, reader, file_node)?.is_some()
    {
        return Err(error("E_PATH"));
    }
    let mut resolved = if nodes.iter().any(|n| n == anchor) {
        vec![anchor.to_owned()]
    } else {
        vec![]
    };
    if endpoint_path(anchor, false).is_some() {
        let normal = normalized_locator(anchor);
        if anchor.contains("::") {
            resolved = nodes
                .iter()
                .filter(|n| normalized_locator(n) == normal)
                .cloned()
                .collect();
        } else {
            let expanded: Vec<_> = nodes
                .iter()
                .filter(|n| {
                    endpoint_path(n, false).is_some()
                        && n.contains("::")
                        && normalized_locator(n).split("::").next() == Some(&normal)
                })
                .cloned()
                .collect();
            if !expanded.is_empty() {
                resolved = expanded;
            }
        }
    }
    if resolved.is_empty() {
        return Err(error("E_SCHEMA"));
    }
    let mut notes = Vec::new();
    if resolved.len() > max_edges {
        notes.push(format!(
            "truncated: anchor expansion omitted {} locator(s)",
            resolved.len() - max_edges
        ));
        resolved.truncate(max_edges);
    }
    let mut skipped = BTreeMap::new();
    let (mut edges, mut seen_edges) = (Vec::new(), HashSet::new());
    let mut frontier: HashSet<String> = resolved.iter().cloned().collect();
    let mut seen_nodes = frontier.clone();
    for level in 0..depth {
        let mut next = HashSet::new();
        for e in &graph {
            let forward = frontier.contains(&e.source) && allowed(purpose, &e.relation, false);
            let reverse = frontier.contains(&e.target) && allowed(purpose, &e.relation, true);
            if !(forward || reverse) {
                continue;
            }
            let issue = validate_endpoint(&e.source, reader, false)?;
            let issue = match issue {
                Some(s) => Some(s),
                None => validate_endpoint(&e.target, reader, file_relation(&e.relation))?,
            };
            if let Some(issue) = issue {
                *skipped.entry(issue).or_insert(0) += 1;
                continue;
            }
            let key = (e.source.clone(), e.relation.clone(), e.target.clone());
            if !seen_edges.contains(&key) {
                if edges.len() >= max_edges {
                    notes.push("truncated: max-edges reached; frontier remains unexplored".into());
                    return Ok(result(meta, &edges, notices(&skipped, notes), resolved));
                }
                edges.push(e.clone());
                seen_edges.insert(key);
            }
            let neighbour = if forward { &e.target } else { &e.source };
            if seen_nodes.insert(neighbour.clone()) {
                next.insert(neighbour.clone());
            }
        }
        frontier = next;
        if frontier.is_empty() {
            break;
        }
        if level + 1 == depth && eligible(&frontier, &graph, purpose) {
            notes.push("truncated: depth reached; frontier remains unexplored".into());
            break;
        }
    }
    Ok(result(meta, &edges, notices(&skipped, notes), resolved))
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
// Shared CPython decimal digit table; no change to the existing binary module.
#[path = "../python_decimal.rs"]
mod python_decimal;
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
        && !r::PURPOSES.contains(&p.as_str())
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
