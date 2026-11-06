//! Read-only bounded traversal of declared YAML relations; no live callers.
use super::{canonical::canonical_json, yaml};
use crate::{digest::sha256, executor_verifier::matches};
use serde_json::{Value, json};
use std::{
    collections::{BTreeMap, HashSet},
    fmt, fs,
    io::Read,
    path::{Path, PathBuf},
};
pub const DEFAULT_GRAPH: &str = "spec/graph.yaml";
pub const PURPOSES: [&str; 4] = ["implementation", "verification", "impact", "dependencies"];
const SCOPE: &str = "declared_spec_relations_only";
const BYTE_NOTICE: &str = "truncated: output byte limit reached; edges omitted";
#[derive(Debug, Clone)]
pub struct RelationError(pub String);
impl fmt::Display for RelationError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.0)
    }
}
impl std::error::Error for RelationError {}
pub type Result<T> = std::result::Result<T, RelationError>;
fn fail<T>(message: &str) -> Result<T> {
    Err(RelationError(message.into()))
}
macro_rules! require {
    ($ok:expr => $message:expr) => {
        if !$ok {
            return fail($message);
        }
    };
}
#[derive(Clone, Debug)]
pub struct Edge {
    pub source: String,
    pub relation: String,
    pub target: String,
    pub source_line: Option<usize>,
    pub provenance: Option<Value>,
}
impl Edge {
    pub fn as_dict(&self) -> Value {
        let mut v = json!({"source":self.source,"relation":self.relation,"target":self.target});
        if let Some(n) = self.source_line {
            v["source_line"] = json!(n);
        }
        if let Some(p) = &self.provenance {
            v["provenance"] = p.clone();
        }
        v
    }
}
/// JSON limits retain Python's distinction between bool, integer and string.
#[derive(Clone)]
pub struct Options<'a> {
    pub root: &'a Path,
    pub graph: &'a str,
    pub depth: Value,
    pub max_edges: Value,
    pub max_bytes: Value,
}
impl<'a> Options<'a> {
    pub fn new(root: &'a Path) -> Self {
        Self {
            root,
            graph: DEFAULT_GRAPH,
            depth: Value::Null,
            max_edges: json!(16),
            max_bytes: json!(6000),
        }
    }
}
pub fn has_control_characters(v: &str) -> bool {
    v.chars()
        .any(|c| matches!(c as u32, 0..=31 | 127..=159 | 0x2028 | 0x2029))
}
fn parts(v: &str) -> Vec<&str> {
    v.split('/')
        .filter(|p| !p.is_empty() && *p != ".")
        .collect()
}
fn unsafe_path(v: &str) -> bool {
    v.starts_with('/')
        || (v.as_bytes().get(1) == Some(&b':') && v.as_bytes()[0].is_ascii_alphabetic())
        || v.split('/').any(|p| p == "..")
}
pub fn matches_protection(path: &str, pattern: &str) -> bool {
    let folded = pattern.to_lowercase();
    let folded = folded.trim_end_matches('/');
    matches(folded, path).unwrap_or(false)
        || (!folded.contains(['*', '?', '[']) && path.starts_with(&format!("{folded}/")))
}
pub fn protected(path: &str, patterns: &[String]) -> bool {
    let lowered = path.to_lowercase();
    parts(path)
        .iter()
        .any(|p| p.to_lowercase().starts_with(".env"))
        || lowered == "secrets"
        || lowered.starts_with("secrets/")
        || lowered.starts_with(".mir/memory.db")
        || patterns.iter().any(|p| matches_protection(&lowered, p))
}
pub fn safe_relative_path(value: &Value, label: &str) -> Result<String> {
    let Some(v) = value
        .as_str()
        .filter(|s| !s.is_empty() && !has_control_characters(s))
    else {
        return fail(&format!(
            "{label} must be a non-empty repository-relative path"
        ));
    };
    let v = v.replace('\\', "/");
    let p = parts(&v).join("/");
    require!(!(unsafe_path(&v) || p.is_empty()) =>
        &format!("{label} must be a safe repository-relative path"));
    require!(!protected(&p, &[]) => &format!("{label} is protected"));
    Ok(p)
}
pub fn profile_pattern(value: &Value) -> Result<String> {
    let Some(v) = value
        .as_str()
        .filter(|s| !s.is_empty() && s.chars().count() <= 4096 && !has_control_characters(s))
    else {
        return fail("repo profile protection paths must be non-empty strings");
    };
    let v = v.replace('\\', "/");
    let p = parts(&v).join("/");
    require!(!(unsafe_path(&v) || p.is_empty()) => "repo profile protection path is unsafe");
    Ok(p)
}
fn relative(path: &Path, root: &Path) -> Option<String> {
    path.strip_prefix(fs::canonicalize(root).ok()?)
        .ok()?
        .to_str()
        .map(|s| s.replace('\\', "/"))
}
pub fn resolve_root(root: &Value) -> Result<PathBuf> {
    let Some(root) = root.as_str() else {
        return fail("root must be a path");
    };
    let root = fs::canonicalize(root).map_err(|e| {
        RelationError(
            if e.kind() == std::io::ErrorKind::NotFound {
                "root must be a directory"
            } else {
                "root is unavailable"
            }
            .into(),
        )
    })?;
    require!(root.is_dir() => "root must be a directory");
    Ok(root)
}
fn read_bounded(path: &Path, limit: u64) -> std::io::Result<Vec<u8>> {
    let mut bytes = Vec::new();
    fs::File::open(path)?
        .take(limit + 1)
        .read_to_end(&mut bytes)?;
    Ok(bytes)
}
pub fn profile_protections(root: &Path) -> Result<Vec<String>> {
    let bad = "repo profile cannot safely define protections";
    let profile = root.join(".mir/repo-profile.toml");
    match profile.symlink_metadata() {
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => return Ok(vec![]),
        Err(_) => return fail(bad),
        Ok(_) => {}
    }
    let resolved = fs::canonicalize(profile).map_err(|_| RelationError(bad.into()))?;
    let rel = relative(&resolved, root).ok_or_else(|| RelationError(bad.into()))?;
    require!(!protected(&rel, &[]) => bad);
    let raw = read_bounded(&resolved, 65536).map_err(|_| RelationError(bad.into()))?;
    require!(raw.len() <= 65536 => bad);
    let text = std::str::from_utf8(&raw).map_err(|_| RelationError(bad.into()))?;
    let doc: toml::Table = toml::from_str(text).map_err(|e| {
        let _ = super::tomllib::tomllib_error(&e, text);
        RelationError(bad.into())
    })?;
    let mut values = Vec::new();
    for (section, key) in [
        ("paths", "protected_paths"),
        ("boundaries", "secrets"),
        ("preserve", "agent_memory_paths"),
    ] {
        let Some(section) = doc.get(section) else {
            continue;
        };
        let Some(section) = section.as_table() else {
            return fail(bad);
        };
        let Some(collection) = section.get(key) else {
            continue;
        };
        let Some(collection) = collection.as_array() else {
            return fail("repo profile protections must be lists");
        };
        require!(values.len() + collection.len() <= 256 =>
        "repo profile has too many protection paths");
        for value in collection {
            values.push(profile_pattern(
                &value.as_str().map_or(Value::Null, |s| json!(s)),
            )?);
        }
    }
    Ok(unique(values))
}
fn graph_path(root: &Path, graph: &str, protections: &[String]) -> Result<(PathBuf, String)> {
    let display = safe_relative_path(&json!(graph), "graph")?;
    require!(!protected(&display, protections) => "graph is protected");
    let candidate = root.join(&display);
    let parent = candidate.parent().unwrap_or(root);
    let parent =
        resolve_missing(parent).map_err(|_| RelationError("graph parent escapes root".into()))?;
    let rel =
        relative(&parent, root).ok_or_else(|| RelationError("graph parent escapes root".into()))?;
    require!(!protected(&rel, protections) => "graph parent is protected");
    require!(candidate.is_file() => &format!("{display} is unavailable"));
    let resolved = fs::canonicalize(candidate)
        .map_err(|_| RelationError("graph symlink escapes root".into()))?;
    let rel = relative(&resolved, root)
        .ok_or_else(|| RelationError("graph symlink escapes root".into()))?;
    require!(!protected(&rel, protections) => "graph resolved target is protected");
    require!(resolved.is_file() => &format!("{display} is unavailable"));
    Ok((resolved, display))
}
fn resolve_missing(path: &Path) -> std::io::Result<PathBuf> {
    match fs::canonicalize(path) {
        Ok(p) => Ok(p),
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => {
            let Some(parent) = path.parent() else {
                return Err(e);
            };
            let Some(name) = path.file_name() else {
                return Err(e);
            };
            Ok(resolve_missing(parent)?.join(name))
        }
        Err(e) => Err(e),
    }
}
pub type Graph = (Vec<Edge>, String, String);
pub fn load_graph(root: &Path, graph: &str, protections: &[String]) -> Result<Graph> {
    let (path, display) = graph_path(root, graph, protections)?;
    let raw = read_bounded(&path, 1024 * 1024)
        .map_err(|_| RelationError(format!("{display} cannot be read")))?;
    require!(raw.len() <= 1024 * 1024 => "graph exceeds 1 MiB limit");
    let doc = yaml::compose(yaml::Input::Bytes(&raw))
        .map_err(|_| RelationError("malformed graph".into()))?;
    let Some(doc) = doc else {
        return fail("graph must be a mapping with edges");
    };
    let yaml::Kind::Mapping(mapping) = &doc.arena[doc.root].kind else {
        return fail("graph must be a mapping with edges");
    };
    let mut edge_nodes = Vec::new();
    for (key, value) in mapping {
        let key = &doc.arena[*key];
        let yaml::Kind::Scalar(s) = &key.kind else {
            return fail("graph keys must be strings");
        };
        require!(key.tag == "tag:yaml.org,2002:str" => "graph keys must be strings");
        if s == "edges" {
            edge_nodes.push(*value);
        }
    }
    require!(edge_nodes.len() == 1 => "graph must contain exactly one edges mapping");
    let yaml::Kind::Sequence(rows) = &doc.arena[edge_nodes[0]].kind else {
        return fail("graph edges must be a list");
    };
    require!(rows.len() <= 10000 => "graph exceeds 10000 edge rows");
    let mut edges = Vec::new();
    let row_error = "each graph edge must be a three-item scalar list";
    for row in rows {
        let node = &doc.arena[*row];
        let yaml::Kind::Sequence(items) = &node.kind else {
            return fail(row_error);
        };
        require!(items.len() == 3 => row_error);
        let mut values = Vec::new();
        for item in items {
            let item = &doc.arena[*item];
            let yaml::Kind::Scalar(v) = &item.kind else {
                return fail(row_error);
            };
            require!(item.tag == "tag:yaml.org,2002:str" => row_error);
            values.push(v.clone());
        }
        let valid = values
            .iter()
            .all(|v| !v.is_empty() && !has_control_characters(v));
        require!(valid => "graph edge values must be non-empty and contain no control characters");
        edges.push(Edge {
            source: values[0].clone(),
            relation: values[1].clone(),
            target: values[2].clone(),
            source_line: Some(node.line + 1),
            provenance: None,
        });
    }
    Ok((edges, sha256(&raw), display))
}
pub fn endpoint_path(value: &str, force_file: bool) -> Option<&str> {
    let path = value.split("::").next().unwrap_or_default();
    (force_file || path.contains('/') || path.starts_with('.')).then_some(path)
}
pub fn validate_endpoint(
    value: &str,
    root: &Path,
    force: bool,
    protections: &[String],
) -> Option<String> {
    let path = endpoint_path(value, force)?;
    let relative_path = match safe_relative_path(&json!(path), "endpoint") {
        Ok(p) => p,
        Err(e) => {
            return Some(
                if e.0.contains("protected") {
                    "protected endpoint"
                } else {
                    "unsafe path endpoint"
                }
                .into(),
            );
        }
    };
    let candidate = root.join(&relative_path);
    if !candidate.exists() {
        return Some("unavailable endpoint".into());
    }
    let resolved = fs::canonicalize(&candidate)
        .ok()
        .and_then(|p| relative(&p, root));
    let Some(resolved) = resolved else {
        return Some("endpoint symlink escapes root".into());
    };
    if protected(&relative_path, protections) || protected(&resolved, protections) {
        return Some("protected endpoint".into());
    }
    if !candidate.is_file() {
        return Some("unavailable file endpoint".into());
    }
    None
}
fn anchor_safe(anchor: &Value) -> Result<&str> {
    let Some(anchor) = anchor
        .as_str()
        .filter(|a| !a.is_empty() && a.chars().count() <= 4096 && !has_control_characters(a))
    else {
        return fail("anchor must be non-empty");
    };
    if let Some(path) = endpoint_path(anchor, false) {
        safe_relative_path(&json!(path), "anchor")
            .map_err(|e| RelationError(format!("anchor unsafe path endpoint: {e}")))?;
    }
    Ok(anchor)
}
pub fn normalized_locator(v: &str) -> String {
    let (path, suffix) = v.split_once("::").map_or((v, None), |(a, b)| (a, Some(b)));
    let prefix = if path.starts_with("//") && !path.starts_with("///") {
        "//"
    } else if path.starts_with('/') {
        "/"
    } else {
        ""
    };
    format!(
        "{prefix}{}{}",
        parts(path).join("/"),
        suffix.map_or(String::new(), |s| format!("::{s}"))
    )
}
fn limit(v: &Value, min: u64, max: u64, message: &str) -> Result<usize> {
    v.as_u64()
        .filter(|n| (min..=max).contains(n))
        .map(|n| n as usize)
        .ok_or_else(|| RelationError(message.into()))
}
fn limits(o: &Options<'_>, purpose: &str) -> Result<(usize, usize)> {
    let d = if o.depth.is_null() {
        json!(if purpose == "dependencies" { 1 } else { 3 })
    } else {
        o.depth.clone()
    };
    let d = limit(&d, 1, 4, "depth must be between 1 and 4")?;
    let n = limit(&o.max_edges, 1, 64, "max-edges must be between 1 and 64")?;
    limit(
        &o.max_bytes,
        1024,
        16000,
        "max-bytes must be between 1024 and 16000",
    )?;
    Ok((d, n))
}
fn allowed(p: &str, relation: &str, reverse: bool) -> bool {
    let list = match (p, reverse) {
        ("implementation", false) => {
            "has_req refines realized_by constrains implemented_in \
exposes decided_by governed_by"
        }
        ("verification", false) => "has_req refines verified_by",
        ("impact", false) => "affects blocks verified_by decided_by governed_by",
        ("dependencies", false) => "depends_on",
        ("verification", true) => "implemented_in realized_by constrains",
        ("impact", true) => "implemented_in realized_by constrains depends_on has_req",
        _ => "",
    };
    list.split_whitespace().any(|r| r == relation)
}
fn file_relation(r: &str) -> bool {
    matches!(r, "implemented_in" | "verified_by")
}
fn unique<T: PartialEq>(items: Vec<T>) -> Vec<T> {
    let mut out = Vec::new();
    for item in items {
        if !out.contains(&item) {
            out.push(item);
        }
    }
    out
}
pub fn notices(skipped: &BTreeMap<String, usize>, extra: Vec<String>) -> Vec<String> {
    skipped
        .iter()
        .map(|(r, n)| format!("skipped {r}: {n} edge(s)"))
        .chain(extra)
        .collect()
}
pub fn result(
    metadata: (&str, &str, &str, &str),
    edges: &[Edge],
    notices: Vec<String>,
    resolved: Vec<String>,
) -> Value {
    let (anchor, purpose, digest, source) = metadata;
    json!({"anchor":anchor,"purpose":purpose,"scope":SCOPE,
        "source":{"graph":source,"sha256":digest},"edges":edges.iter()
        .map(Edge::as_dict).collect::<Vec<_>>(),"truncated":notices.iter()
        .any(|n| n.starts_with("truncated:")),"notices":notices,"resolved_anchors":resolved})
}
pub fn query_relations(anchor: &Value, purpose: &str, o: &Options<'_>) -> Result<Value> {
    require!(PURPOSES.contains(&purpose) =>
        "purpose must be implementation, impact, verification, or dependencies");
    limits(o, purpose)?;
    let base = resolve_root(&json!(o.root))?;
    let protections = profile_protections(&base)?;
    anchor_safe(anchor)?;
    let (edges, digest, source) = load_graph(&base, o.graph, &protections)?;
    let loaded: Loaded<'_> = (&edges, &digest, &source, &protections);
    let o = Options {
        root: &base,
        ..o.clone()
    };
    query_loaded(anchor, purpose, &o, loaded)
}
type Loaded<'a> = (&'a [Edge], &'a str, &'a str, &'a [String]);
fn query_loaded(
    anchor: &Value,
    purpose: &str,
    o: &Options<'_>,
    loaded: Loaded<'_>,
) -> Result<Value> {
    let (graph, digest, source, protections) = loaded;
    let (depth, max_edges) = limits(o, purpose)?;
    let anchor = anchor_safe(anchor)?;
    let metadata = (anchor, purpose, digest, source);
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
        && let Some(issue) = validate_endpoint(anchor, o.root, file_node, protections)
    {
        return fail(&format!("anchor {issue}"));
    }
    let mut resolved: Vec<String> = nodes.iter().filter(|n| *n == anchor).cloned().collect();
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
    require!(!resolved.is_empty() => "unknown anchor");
    let mut extra = Vec::new();
    if resolved.len() > max_edges {
        extra.push(format!(
            "truncated: anchor expansion omitted {} locator(s)",
            resolved.len() - max_edges
        ));
        resolved.truncate(max_edges);
    }
    let mut skipped = BTreeMap::new();
    let mut output = Vec::new();
    let mut seen_edges = HashSet::new();
    let mut frontier: HashSet<_> = resolved.iter().cloned().collect();
    let mut seen_nodes = frontier.clone();
    for level in 0..depth {
        let mut next = HashSet::new();
        for e in graph {
            let forward = frontier.contains(&e.source) && allowed(purpose, &e.relation, false);
            let reverse = frontier.contains(&e.target) && allowed(purpose, &e.relation, true);
            if !forward && !reverse {
                continue;
            }
            let issue = validate_endpoint(&e.source, o.root, false, protections).or_else(|| {
                validate_endpoint(&e.target, o.root, file_relation(&e.relation), protections)
            });
            if let Some(issue) = issue {
                *skipped.entry(issue).or_default() += 1;
                continue;
            }
            let key = (&e.source, &e.relation, &e.target);
            if !seen_edges.contains(&key) {
                if output.len() >= max_edges {
                    extra.push("truncated: max-edges reached; frontier remains unexplored".into());
                    return Ok(result(
                        metadata,
                        &output,
                        notices(&skipped, extra),
                        resolved,
                    ));
                }
                output.push(e.clone());
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
        if level + 1 == depth
            && graph.iter().any(|e| {
                (frontier.contains(&e.source) && allowed(purpose, &e.relation, false))
                    || (frontier.contains(&e.target) && allowed(purpose, &e.relation, true))
            })
        {
            extra.push("truncated: depth reached; frontier remains unexplored".into());
            break;
        }
    }
    Ok(result(
        metadata,
        &output,
        notices(&skipped, extra),
        resolved,
    ))
}
fn search_bundle(anchors: &[String], purposes: &[String], reason: &str) -> Value {
    json!({"route":"search","anchors":anchors,"requested_purposes":purposes,"reason":reason,
        "scope":SCOPE,"edges":[],"notices":[],"truncated":false})
}
fn strings(v: &Value) -> Option<Vec<String>> {
    v.as_array()?
        .iter()
        .map(|v| v.as_str().map(str::to_owned))
        .collect()
}
fn edge_key(v: &Value) -> Value {
    json!([v["source"], v["relation"], v["target"]])
}
pub fn bundle_relations(anchors: &Value, purposes: &Value, o: &Options<'_>) -> Result<Value> {
    let (Some(anchors), Some(purposes)) = (strings(anchors), strings(purposes)) else {
        return fail("anchors and purposes must be lists");
    };
    let (_, max_edges) = limits(o, "implementation")?;
    for a in &anchors {
        anchor_safe(&json!(a))?;
    }
    let (anchors, purposes) = (unique(anchors), unique(purposes));
    let search = |reason| Ok(search_bundle(&anchors, &purposes, reason));
    if anchors.len() != 1 {
        return search("requires exactly one distinct anchor");
    }
    if purposes.len() < 2 {
        return search("requires at least two distinct purposes");
    }
    if purposes.iter().any(|p| !PURPOSES.contains(&p.as_str())) {
        return search("unknown purpose");
    }
    let base = resolve_root(&json!(o.root))?;
    let protections = profile_protections(&base)?;
    let (graph, digest, source) = match load_graph(&base, o.graph, &protections) {
        Ok(v) => v,
        Err(e) if e.0.contains("unavailable") => return search("graph unavailable"),
        Err(e) => return Err(e),
    };
    let anchor = &anchors[0];
    let in_nodes = graph
        .iter()
        .any(|e| &e.source == anchor || &e.target == anchor);
    let file_target = graph
        .iter()
        .any(|e| &e.target == anchor && e.relation == "implemented_in");
    let mut resolved = anchor.clone();
    let mut resolution = Value::Null;
    if file_target || (!in_nodes && endpoint_path(anchor, false).is_some()) {
        if let Some(issue) = validate_endpoint(anchor, &base, true, &protections) {
            if issue == "unavailable endpoint" {
                return search("unknown anchor");
            }
            return fail(&format!("anchor {issue}"));
        }
        let normal = normalized_locator(anchor);
        let owners: Vec<_> = graph
            .iter()
            .filter(|e| {
                e.relation == "implemented_in"
                    && normalized_locator(&e.target).split("::").next() == Some(&normal)
            })
            .collect();
        let ids = unique(owners.iter().map(|e| e.source.clone()).collect());
        if ids.len() != 1 {
            return search(if owners.is_empty() {
                "unknown anchor"
            } else {
                "ambiguous implementation owner"
            });
        }
        resolved = ids[0].clone();
        resolution = owners[0].as_dict();
    } else if !in_nodes {
        return search("unknown anchor");
    }
    let (mut merged, mut facets, mut notices) = (Vec::<Value>::new(), Vec::new(), Vec::new());
    let mut omitted = false;
    for p in &purposes {
        let loaded: Loaded<'_> = (&graph, &digest, &source, &protections);
        let o = Options {
            root: &base,
            ..o.clone()
        };
        let item = query_loaded(&json!(resolved), p, &o, loaded)?;
        let edges = item["edges"].as_array().cloned().unwrap_or_default();
        let (available, mut contributed) = (edges.len(), 0);
        for mut edge in edges {
            if let Some(old) = merged.iter_mut().find(|v| edge_key(v) == edge_key(&edge)) {
                if let Some(ps) = old["purposes"].as_array_mut() {
                    ps.push(json!(p));
                }
            } else if merged.len() < max_edges {
                edge["purposes"] = json!([p]);
                merged.push(edge);
                contributed += 1;
            } else {
                omitted = true;
            }
        }
        facets.push(
            json!({"purpose":p,"available_count":available,"edge_count":contributed,
            "coverage":if item["truncated"] == true || omitted {"truncated"}
                else if available == 0 {"empty"} else {"bounded"},"notices":item["notices"]}),
        );
        notices.extend(strings(&item["notices"]).unwrap_or_default());
    }
    if facets.iter().any(|f| f["available_count"] == 0) {
        return search("one or more requested facets have no declared evidence");
    }
    notices = unique(notices);
    if omitted {
        notices.push("truncated: global max-edges reached; facet coverage incomplete".into());
    }
    let mut v = json!({"route":"graph","anchor":anchor,"resolved_anchor":resolved,
        "resolution":resolution,"requested_purposes":purposes,"facets":facets,"scope":SCOPE,
        "source":{"graph":source,"sha256":digest},"edges":merged,
        "truncated":notices.iter().any(|n| n.starts_with("truncated:")),"notices":notices});
    refresh_bundle_facets(&mut v);
    Ok(v)
}
pub fn refresh_bundle_facets(v: &mut Value) {
    let edges = v["edges"].as_array().cloned().unwrap_or_default();
    if let Some(facets) = v.get_mut("facets").and_then(Value::as_array_mut) {
        for f in facets {
            let n = edges
                .iter()
                .filter(|e| {
                    e["purposes"]
                        .as_array()
                        .is_some_and(|ps| ps.contains(&f["purpose"]))
                })
                .count();
            f["edge_count"] = json!(n);
            if n < f["available_count"].as_u64().unwrap_or(0) as usize {
                f["coverage"] = json!("truncated");
            }
        }
    }
}
fn text(v: &Value) -> &str {
    v.as_str().unwrap_or_default()
}
fn py(v: &Value) -> String {
    match v {
        Value::Null => "None".into(),
        Value::String(s) => s.clone(),
        Value::Bool(b) => if *b { "True" } else { "False" }.into(),
        _ => v.to_string(),
    }
}
pub fn source_line(source: &str, line: &Value) -> String {
    let source = if source == DEFAULT_GRAPH {
        "graph.yaml"
    } else {
        source
    };
    format!("{source}:{line}")
}
pub fn render_edge(e: &Value, source: &str) -> String {
    let rendered = ["source", "relation", "target"]
        .map(|k| text(&e[k]))
        .join(" ");
    let p = &e["provenance"];
    if !p.is_object() {
        return if e.get("source_line").is_some() {
            format!("{rendered} ({})", source_line(source, &e["source_line"]))
        } else {
            rendered
        };
    }
    let evidence = if p["sources"].is_array() {
        p["sources"].as_array().cloned().unwrap_or_default()
    } else if p.get("sources").is_none() {
        vec![]
    } else {
        vec![p.clone()]
    };
    let evidence = evidence
        .iter()
        .filter(|v| v.is_object())
        .map(|v| {
            format!(
                "path={}:{},fact_id={},content_item_id={},sha256={},summary={},summary_basis={},\
reason={},reason_basis={}",
                v["source_path"],
                py(&v["source_line"]),
                py(&v["fact_id"]),
                py(&v["content_item_id"]),
                py(&v["source_hash"]),
                v["summary"],
                py(&v["summary_basis"]),
                v["reason"],
                py(&v["reason_basis"])
            )
        })
        .collect::<Vec<_>>()
        .join(";");
    format!(
        "{rendered} (database={}, evidence=[{evidence}])",
        py(&p["database"])
    )
}
pub fn render_source(v: &Value) -> Result<String> {
    let get = |key| text(&v[key]);
    if v.get("graph").is_some() {
        Ok(format!("source={} sha256={}", get("graph"), get("sha256")))
    } else if v.get("memory_db").is_some() {
        let mode = v["mode"].as_str().unwrap_or("read_only");
        Ok(format!("source={} mode={mode}", get("memory_db")))
    } else {
        fail("result source metadata is invalid")
    }
}
fn truncate(v: &mut Value) -> Result<()> {
    require!(!(v["edges"].as_array_mut().and_then(Vec::pop).is_none()) =>
        "max-bytes cannot contain required result metadata");
    refresh_bundle_facets(v);
    if let Some(ns) = v["notices"].as_array_mut()
        && !ns.contains(&json!(BYTE_NOTICE))
    {
        ns.push(json!(BYTE_NOTICE));
    }
    v["truncated"] = json!(true);
    Ok(())
}
pub fn render_json(v: &Value, max_bytes: usize) -> Result<String> {
    let mut v = v.clone();
    loop {
        let output = canonical_json(&v, Some(&[])) + "\n";
        if output.len() <= max_bytes {
            return Ok(output);
        }
        truncate(&mut v)?;
    }
}
pub fn render_human(v: &Value, max_bytes: usize) -> Result<String> {
    render_text(v, max_bytes, false)
}
pub fn render_bundle_human(v: &Value, max_bytes: usize) -> Result<String> {
    render_text(v, max_bytes, true)
}
fn render_text(v: &Value, max_bytes: usize, bundle: bool) -> Result<String> {
    let mut v = v.clone();
    let get = |key| text(&v[key]);
    let source = &v["source"];
    let mut lines = Vec::new();
    if bundle {
        lines.push(format!("route={}", text(&v["route"])));
        if v["route"] == "search" {
            lines.extend([
                format!("reason={}", get("reason")),
                format!("scope={}", get("scope")),
            ]);
        } else {
            lines.push(format!(
                "anchor={} resolved_anchor={}",
                get("anchor"),
                get("resolved_anchor")
            ));
            let purposes = strings(&v["requested_purposes"])
                .unwrap_or_default()
                .join(",");
            lines.push(format!("purposes={purposes}"));
            let resolution = &v["resolution"];
            if resolution.is_object() {
                let rendered = if resolution.get("source_line").is_some() {
                    let graph = source["graph"].as_str().unwrap_or(DEFAULT_GRAPH);
                    format!(
                        "implemented_in {}",
                        source_line(graph, &resolution["source_line"])
                    )
                } else {
                    render_edge(resolution, "memory.db")
                };
                lines.push(format!("resolution={rendered}"));
            }
            lines.push(render_source(&v["source"])?);
        }
    } else {
        let (anchor, purpose, scope) = (get("anchor"), get("purpose"), get("scope"));
        lines.push(format!("anchor={anchor} purpose={purpose} scope={scope}"));
        lines.push(render_source(source)?);
        if v["resolved_anchors"] != json!([v["anchor"]]) {
            let anchors = strings(&v["resolved_anchors"])
                .unwrap_or_default()
                .join(",");
            lines.push(format!("resolved_anchors={anchors}"));
        }
    }
    loop {
        let mut output = lines.clone();
        if let Some(facets) = v["facets"].as_array() {
            for f in facets {
                let (purpose, n, coverage) =
                    (text(&f["purpose"]), &f["edge_count"], text(&f["coverage"]));
                output.push(format!("facet={purpose} edges={n} coverage={coverage}"));
            }
        }
        let source = &v["source"];
        let fallback = (!bundle).then(|| source["memory_db"].as_str()).flatten();
        let source = source["graph"].as_str().or(fallback).unwrap_or("memory.db");
        if let Some(edges) = v["edges"].as_array() {
            output.extend(edges.iter().map(|e| render_edge(e, source)));
        }
        let notices = strings(&v["notices"]).unwrap_or_default();
        output.extend(notices.iter().map(|n| format!("notice: {n}")));
        let output = output.join("\n") + "\n";
        if output.len() <= max_bytes {
            return Ok(output);
        }
        truncate(&mut v)?;
    }
}
