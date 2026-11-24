//! Bounded parser and traversal for the standalone selective-relations YAML subset.
use super::relation_terms::{
    PURPOSES, allowed, endpoint_path, file_relation, has_control_characters, normalized_locator,
    notices, unique,
};
use crate::digest::sha256;
use serde_json::{Value, json};
use std::{
    collections::{BTreeMap, HashSet},
    fmt,
    path::PathBuf,
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
    #[allow(
        dead_code,
        reason = "used by standalone library readers with typed refusals"
    )]
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
        // Python re.IGNORECASE folds both Turkish I variants into ASCII i.
        r"\.[0-9_]+(?:[eE][-+]?[0-9]+)?|0[xX][0-9a-fA-F_]+|0[bB][01_]+|\.[i\u{130}\u{131}]nf|\.nan)|",
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
        || path.chars().nth(1) == Some(':')
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
/// Reader errors propagate unchanged for external guards.
pub trait Reader {
    fn path(&self, relative: &str, allow_missing: bool) -> Result<PathBuf>;
    fn exists(&self, relative: &str) -> Result<bool>;
    fn read(&self, relative: &str) -> Result<Vec<u8>>;
    fn endpoint_issue(&self, relative: &str) -> Result<Option<String>> {
        self.path(relative, true)?;
        Ok((!self.exists(relative)?).then(|| "unavailable endpoint".into()))
    }
}
pub fn validate_endpoint(value: &str, reader: &dyn Reader, force: bool) -> Result<Option<String>> {
    let Some(path) = endpoint_path(value, force) else {
        return Ok(None);
    };
    let Ok(relative) = relative(Some(path)) else {
        return Ok(Some("unsafe path endpoint".into()));
    };
    reader.endpoint_issue(&relative)
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
        .collect::<Vec<_>>(),"notices":notes,
        "truncated":notes.iter().any(|s| s.starts_with("truncated:")),
        "resolved_anchors":resolved})
}
pub(crate) struct Query<'a> {
    anchor: &'a str,
    purpose: &'a str,
    depth: usize,
    max_edges: usize,
}
impl<'a> Query<'a> {
    pub(crate) fn new(
        anchor: &'a Value,
        purpose: &'a Value,
        depth: &Value,
        max_edges: &Value,
    ) -> Result<Self> {
        let purpose = purpose
            .as_str()
            .filter(|p| PURPOSES.contains(p))
            .ok_or_else(|| error("E_SCHEMA"))?;
        let depth = if depth.is_null() {
            if purpose == "dependencies" {
                1
            } else {
                DEFAULT_DEPTH
            }
        } else {
            limit(depth, MAX_DEPTH)?
        };
        let max_edges = limit(max_edges, MAX_EDGES)?;
        let anchor = anchor
            .as_str()
            .filter(|a| !a.is_empty() && !has_control_characters(a))
            .ok_or_else(|| error("E_SCHEMA"))?;
        if anchor.len() > MAX_ANCHOR_CHARS {
            return Err(error("E_LIMIT"));
        }
        Ok(Self {
            anchor,
            purpose,
            depth,
            max_edges,
        })
    }

    pub(crate) fn read(self, graph: &str, reader: &dyn Reader) -> Result<Value> {
        let Self {
            anchor,
            purpose,
            depth,
            max_edges,
        } = self;
        if let Some(path) = endpoint_path(anchor, false) {
            relative(Some(path))?;
            reader.path(path, true)?;
        }
        let source = relative(Some(graph))?;
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
                        notes.push(
                            "truncated: max-edges reached; frontier remains unexplored".into(),
                        );
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
}
