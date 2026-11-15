//! Library-only port of the bundled ontology checker. No caller is connected.
use crate::{
    digest::sha256, executor_development_packet::py_repr, executor_policy_query::ascii_json_text,
    python_text::casefold,
};
use serde::{
    Deserialize,
    de::{MapAccess, SeqAccess, Visitor},
};
use serde_json::{Value, json};
use std::{
    collections::BTreeSet,
    fmt, fs,
    path::{Path, PathBuf},
};
pub const DEFAULT_CONTRACT: &str = "references/common-contract.json";
pub const NUMBER: &str = r"(?:0|[1-9][0-9]*)";
pub const CORE: &str = r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)";
pub const SEMVER: &str = concat!(
    r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)",
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?",
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
);
pub const VERSION_RANGE: &str = concat!(
    r">=((?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)) ",
    r"<((?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*))"
);
pub const MAPPING_BUDGET: usize = 32768;
pub type Result<T> = std::result::Result<T, Error>;
#[derive(Clone, Debug)]
pub struct Error {
    pub class: String,
    pub message: String,
}
impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.message)
    }
}
impl std::error::Error for Error {}
pub fn error(class: &str, message: impl Into<String>) -> Error {
    Error {
        class: class.into(),
        message: message.into(),
    }
}
/// Ordered JSON is necessary: Python traverses dictionaries in insertion order.
#[derive(Clone, Debug, PartialEq)]
pub enum Doc {
    Scalar(Value),
    Array(Vec<Doc>),
    Object(Vec<(String, Doc)>),
}
impl<'de> Deserialize<'de> for Doc {
    fn deserialize<D: serde::Deserializer<'de>>(d: D) -> std::result::Result<Self, D::Error> {
        struct V;
        impl<'de> Visitor<'de> for V {
            type Value = Doc;
            fn expecting(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
                f.write_str("JSON")
            }
            fn visit_unit<E>(self) -> std::result::Result<Doc, E> {
                Ok(Doc::null())
            }
            fn visit_bool<E>(self, v: bool) -> std::result::Result<Doc, E> {
                Ok(Doc::from(json!(v)))
            }
            fn visit_i64<E>(self, v: i64) -> std::result::Result<Doc, E> {
                Ok(Doc::from(json!(v)))
            }
            fn visit_u64<E>(self, v: u64) -> std::result::Result<Doc, E> {
                Ok(Doc::from(json!(v)))
            }
            fn visit_f64<E>(self, v: f64) -> std::result::Result<Doc, E> {
                Ok(Doc::from(json!(v)))
            }
            fn visit_str<E>(self, v: &str) -> std::result::Result<Doc, E> {
                Ok(Doc::from(json!(v)))
            }
            fn visit_map<A: MapAccess<'de>>(self, mut a: A) -> std::result::Result<Doc, A::Error> {
                let mut out = Vec::new();
                while let Some((k, v)) = a.next_entry::<String, Doc>()? {
                    if let Some((_, old)) = out.iter_mut().find(|(key, _)| key == &k) {
                        *old = v;
                    } else {
                        out.push((k, v));
                    }
                }
                Ok(Doc::Object(out))
            }
            fn visit_seq<A: SeqAccess<'de>>(self, mut a: A) -> std::result::Result<Doc, A::Error> {
                let mut out = Vec::new();
                while let Some(v) = a.next_element()? {
                    out.push(v);
                }
                Ok(Doc::Array(out))
            }
        }
        d.deserialize_any(V)
    }
}
impl From<Value> for Doc {
    fn from(v: Value) -> Self {
        match v {
            Value::Array(a) => Self::Array(a.into_iter().map(Self::from).collect()),
            Value::Object(m) => {
                Self::Object(m.into_iter().map(|(k, v)| (k, Self::from(v))).collect())
            }
            v => Self::Scalar(v),
        }
    }
}
static NULL: Doc = Doc::Scalar(Value::Null);
// Ordered object construction; values are already typed documents.
macro_rules! object {
    ($($key:literal => $value:expr),* $(,)?) => {
        object(vec![$(($key, $value)),*])
    };
}
impl Doc {
    pub fn null() -> Self {
        NULL.clone()
    }
    pub fn get(&self, key: &str) -> &Self {
        self.items()
            .iter()
            .find(|(k, _)| k == key)
            .map_or(&NULL, |(_, v)| v)
    }
    pub fn has(&self, key: &str) -> bool {
        self.items().iter().any(|(k, _)| k == key)
    }
    pub fn set(&mut self, key: &str, v: Doc) {
        if let Self::Object(m) = self {
            if let Some((_, old)) = m.iter_mut().find(|(k, _)| k == key) {
                *old = v;
            } else {
                m.push((key.into(), v));
            }
        }
    }
    pub fn remove(&mut self, key: &str) {
        if let Self::Object(m) = self {
            m.retain(|(k, _)| k != key);
        }
    }
    pub fn text(&self) -> Option<&str> {
        if let Self::Scalar(Value::String(s)) = self {
            Some(s)
        } else {
            None
        }
    }
    pub fn items(&self) -> &[(String, Doc)] {
        if let Self::Object(m) = self { m } else { &[] }
    }
    pub fn list(&self) -> &[Doc] {
        if let Self::Array(a) = self { a } else { &[] }
    }
    pub fn value(&self) -> Value {
        match self {
            Self::Scalar(v) => v.clone(),
            Self::Array(a) => json!(a.iter().map(Self::value).collect::<Vec<_>>()),
            Self::Object(m) => {
                Value::Object(m.iter().map(|(k, v)| (k.clone(), v.value())).collect())
            }
        }
    }
    pub fn dump(&self, sorted: bool, indent: Option<usize>) -> String {
        fn render(d: &Doc, sorted: bool, indent: Option<usize>, level: usize) -> String {
            let sep = if indent.is_some() { ",\n" } else { ", " };
            let pad = |l| " ".repeat(indent.unwrap_or(0) * l);
            let wrap = |a, b, rows: Vec<String>| {
                if rows.is_empty() {
                    format!("{a}{b}")
                } else if indent.is_some() {
                    format!("{a}\n{}\n{}{b}", rows.join(sep), pad(level))
                } else {
                    format!("{a}{}{b}", rows.join(sep))
                }
            };
            match d {
                Doc::Scalar(v) => ascii_json_text(&v.to_string()),
                Doc::Array(a) => wrap(
                    "[",
                    "]",
                    a.iter()
                        .map(|v| {
                            format!("{}{}", pad(level + 1), render(v, sorted, indent, level + 1))
                        })
                        .collect(),
                ),
                Doc::Object(m) => {
                    let mut rows: Vec<_> = m.iter().collect();
                    if sorted {
                        rows.sort_by(|a, b| a.0.cmp(&b.0));
                    }
                    wrap(
                        "{",
                        "}",
                        rows.iter()
                            .map(|(k, v)| {
                                format!(
                                    "{}{}: {}",
                                    pad(level + 1),
                                    ascii_json_text(&json!(k).to_string()),
                                    render(v, sorted, indent, level + 1)
                                )
                            })
                            .collect(),
                    )
                }
            }
        }
        render(self, sorted, indent, 0)
    }
}
pub fn object(rows: Vec<(&str, Doc)>) -> Doc {
    Doc::Object(rows.into_iter().map(|(k, v)| (k.into(), v)).collect())
}
fn s(v: impl Into<String>) -> Doc {
    Doc::from(json!(v.into()))
}
fn arr(v: Vec<Doc>) -> Doc {
    Doc::Array(v)
}
pub fn load_json(text: &str) -> Result<Doc> {
    serde_json::from_str(text).map_err(|e| {
        let message = if text.trim() == "{" {
            "Expecting property name enclosed in double quotes: line 1 column 2 (char 1)".into()
        } else {
            e.to_string()
        };
        error("JSONDecodeError", message)
    })
}
fn captures(pattern: &str, text: &str) -> Option<Vec<String>> {
    static CACHE: std::sync::OnceLock<
        std::sync::Mutex<std::collections::HashMap<String, fancy_regex::Regex>>,
    > = std::sync::OnceLock::new();
    let mut cache = CACHE.get_or_init(Default::default).lock().ok()?;
    if !cache.contains_key(pattern) {
        if cache.len() >= 1024 {
            cache.clear();
        }
        cache.insert(pattern.into(), fancy_regex::Regex::new(pattern).ok()?);
    }
    let re = cache.get(pattern)?;
    let c = re.captures(text).ok()??;
    Some(
        (0..c.len())
            .map(|i| c.get(i).map_or("", |m| m.as_str()).into())
            .collect(),
    )
}
fn matched(pattern: &str, text: &str) -> bool {
    captures(pattern, text).is_some()
}
pub fn version_key(value: &Doc) -> Option<Doc> {
    let c = captures(&format!("\\A{SEMVER}\\z"), value.text()?)?;
    let mut parts = Vec::new();
    if c[4].is_empty() {
        parts.push(Doc::from(json!([2, ""])));
    } else {
        for part in c[4].split('.') {
            if part.bytes().all(|b| b.is_ascii_digit()) {
                if part.len() > 1 && part.starts_with('0') {
                    return None;
                }
                parts.push(Doc::from(json!([0, part.parse::<u64>().ok()?])));
            } else {
                parts.push(Doc::from(json!([1, part])));
            }
        }
    }
    Some(arr(vec![
        Doc::from(json!(c[1].parse::<u64>().ok()?)),
        Doc::from(json!(c[2].parse::<u64>().ok()?)),
        Doc::from(json!(c[3].parse::<u64>().ok()?)),
        arr(parts),
    ]))
}
type Version = (u64, u64, u64, Vec<(u64, String)>);
fn version(v: &Doc) -> Option<Version> {
    let k = version_key(v)?.value();
    Some((
        k[0].as_u64()?,
        k[1].as_u64()?,
        k[2].as_u64()?,
        k[3].as_array()?
            .iter()
            .map(|p| {
                (
                    p[0].as_u64().unwrap_or(0),
                    p[1].as_str()
                        .map(str::to_owned)
                        .unwrap_or_else(|| format!("{:020}", p[1].as_u64().unwrap_or(0))),
                )
            })
            .collect(),
    ))
}
pub fn pointer(base: &str, key: impl fmt::Display) -> String {
    format!(
        "{base}/{}",
        key.to_string().replace('~', "~0").replace('/', "~1")
    )
}
pub trait Reader {
    fn path(&self, value: &str, allow_missing: bool) -> Result<PathBuf>;
    fn exists(&self, value: &str) -> Result<bool>;
    fn read(&self, value: &str) -> Result<Vec<u8>>;
    fn validate_json(&self, _text: &str) -> Result<()> {
        Ok(())
    }
}
fn io_error(e: std::io::Error, p: &Path) -> Error {
    let (class, code, message) = match e.kind() {
        std::io::ErrorKind::NotFound => ("FileNotFoundError", 2, "No such file or directory"),
        std::io::ErrorKind::PermissionDenied if cfg!(windows) => {
            ("PermissionError", 13, "Permission denied")
        }
        std::io::ErrorKind::IsADirectory => ("IsADirectoryError", 21, "Is a directory"),
        _ => ("OSError", e.raw_os_error().unwrap_or(0), "IO error"),
    };
    error(
        class,
        format!(
            "[Errno {code}] {message}: {}",
            py_repr(&p.display().to_string())
        ),
    )
}
pub fn read(p: &Path) -> Result<Vec<u8>> {
    if cfg!(not(windows)) && p.is_dir() {
        return Err(error(
            "IsADirectoryError",
            format!(
                "[Errno 21] Is a directory: {}",
                py_repr(&p.display().to_string())
            ),
        ));
    }
    fs::read(p).map_err(|e| io_error(e, p))
}
fn text_bytes(b: Vec<u8>) -> Result<String> {
    String::from_utf8(b)
        .map(|s| s.replace("\r\n", "\n").replace('\r', "\n"))
        .map_err(|e| error("UnicodeDecodeError", e.to_string()))
}
fn resolve(path: &Path) -> Result<PathBuf> {
    match fs::canonicalize(path) {
        Ok(p) => Ok(p),
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => {
            let parent = path.parent().ok_or_else(|| io_error(e, path))?;
            Ok(resolve(parent)?.join(path.file_name().unwrap_or_default()))
        }
        Err(e) => Err(io_error(e, path)),
    }
}
pub struct Checker<'a> {
    pub io: Option<&'a dyn Reader>,
    pub errors: Vec<Doc>,
    pub warnings: Vec<Doc>,
    pub checked_refs: BTreeSet<String>,
    pub line_refs: BTreeSet<String>,
}
impl<'a> Checker<'a> {
    pub fn new(io: Option<&'a dyn Reader>) -> Self {
        Self {
            io,
            errors: vec![],
            warnings: vec![],
            checked_refs: BTreeSet::new(),
            line_refs: BTreeSet::new(),
        }
    }
    fn finding(&self, at: &str, message: &str, code: &str) -> Doc {
        let mut d = object! {
            "pointer" => s(at),
            "message" => s(message),
        };
        if self.io.is_some() {
            d.set("code", s(code));
        }
        d
    }
    pub fn error(&mut self, at: &str, message: &str) {
        self.errors.push(self.finding(at, message, "E_VALIDATION"));
    }
    pub fn warn(&mut self, at: &str, message: &str) {
        self.warnings
            .push(self.finding(at, message, "W_VALIDATION"));
    }
    pub fn read_text(&self, relative: &str) -> Result<String> {
        text_bytes(
            self.io
                .ok_or_else(|| error("ValueError", "reader required"))?
                .read(relative)?,
        )
    }
    pub fn object(&mut self, v: &Doc, at: &str) -> Doc {
        if matches!(v, Doc::Object(_)) {
            v.clone()
        } else {
            self.error(at, "expected an object");
            object! {}
        }
    }
    pub fn array(&mut self, v: &Doc, at: &str) -> Vec<Doc> {
        if let Doc::Array(a) = v {
            a.clone()
        } else {
            self.error(at, "expected a list");
            vec![]
        }
    }
    pub fn text(&mut self, v: &Doc, at: &str, message: &str) -> bool {
        if v.text().is_none_or(|s| s.trim().is_empty()) {
            self.error(at, message);
            false
        } else {
            true
        }
    }
    pub fn ref_check(&mut self, v: &Doc, at: &str, root: &Path) -> Result<Option<PathBuf>> {
        self.checked_refs.insert(at.into());
        if !self.text(v, at, "needs a ref") {
            return Ok(None);
        }
        let value = v.text().unwrap_or_default();
        let (path, name) = value
            .split_once('#')
            .map_or((value, None), |(p, n)| (p, Some(n)));
        if matched(r":\d+$", path) {
            self.line_refs.insert(at.into());
        }
        let raw = ref_path(value);
        let drive = raw.as_bytes().get(1) == Some(&b':');
        if raw.starts_with('/') || (drive && raw[2..].starts_with(['\\', '/'])) {
            self.error(at, "absolute ref is not allowed");
            return Ok(None);
        }
        if raw.is_empty() || raw.contains('\\') || drive {
            self.error(at, "ref must be repo-relative");
            return Ok(None);
        }
        if raw.split('/').any(|p| p == "..") {
            self.error(
                at,
                "ref escapes repository: parent traversal is not allowed",
            );
            return Ok(None);
        }
        let target = if let Some(io) = self.io {
            io.path(&raw, true)?
        } else {
            resolve(&root.join(&raw))?
        };
        if self.io.is_none() && !target.starts_with(root) {
            self.error(at, "ref escapes repository");
            return Ok(None);
        }
        let exists = if let Some(io) = self.io {
            io.exists(&raw)?
        } else {
            target.exists()
        };
        if !exists {
            self.error(at, "ref path does not exist");
            return Ok(None);
        }
        if let Some(name) = name {
            let found = if self.io.is_none() && !target.is_file() {
                false
            } else {
                let text = if self.io.is_some() {
                    self.read_text(&raw)?
                } else {
                    text_bytes(read(&target)?)?
                };
                if let Some(io) = self.io
                    && suffix(&target) == ".json"
                {
                    io.validate_json(&text)?;
                }
                resolves_symbol(&text, name, &suffix(&target), None)?
            };
            if !found {
                self.error(
                    at,
                    &format!("symbol anchor not found (check name not found): {name}"),
                );
            }
        }
        Ok(Some(target))
    }
    pub fn covered_check(&mut self, v: &Doc, at: &str, root: &Path) -> Result<()> {
        let Some(target) = self.ref_check(v, at, root)? else {
            return Ok(());
        };
        if self.io.is_none() && !target.is_file() {
            self.error(at, "check ref must name a file");
            return Ok(());
        }
        let raw = v.text().unwrap_or_default();
        let path = raw.split('#').next().unwrap_or_default();
        let text = if self.io.is_some() {
            self.read_text(&ref_path(raw))?
        } else {
            text_bytes(read(&target)?)?
        };
        if let Some(c) = captures(r":(\d+)$", path) {
            let number = c[1].parse::<usize>().unwrap_or(usize::MAX);
            if number < 1 {
                self.error(at, "check line must be positive");
            } else if number > text.lines().count() {
                self.error(at, "check line exceeds file line count");
            }
        }
        if [".md", ".txt", ".rst"].contains(&suffix(&target).as_str()) {
            self.warn(
                at,
                "covered needs a repeatable check; a document is not one",
            );
        }
        Ok(())
    }
    pub fn refs(&mut self, v: &Doc, at: &str, root: &Path) -> Result<()> {
        for (i, r) in self.array(v, at).iter().enumerate() {
            let p = pointer(at, i);
            if matches!(r, Doc::Object(_)) {
                self.ref_check(r.get("ref"), &pointer(&p, "ref"), root)?;
            } else {
                self.ref_check(r, &p, root)?;
            }
        }
        Ok(())
    }
    pub fn ids(&mut self, c: &Doc, key: &str) -> BTreeSet<String> {
        let mut found = BTreeSet::new();
        for (i, raw) in self
            .array(c.get(key), &format!("/{key}"))
            .iter()
            .enumerate()
        {
            let at = pointer(&format!("/{key}"), i);
            let entry = self.object(raw, &at);
            let v = entry.get("id");
            if self.text(v, &format!("{at}/id"), "expected a non-empty string") {
                let v = v.text().unwrap_or_default();
                if !found.insert(v.into()) {
                    self.error(&format!("{at}/id"), &format!("duplicate id: {v}"));
                }
            }
        }
        found
    }
    pub fn contract(&mut self, raw: &Doc) -> Doc {
        let c = self.object(raw, "");
        if c.get("schema").text() != Some("mir-semantic-contract/v1") {
            self.error("/schema", "invalid contract schema");
        }
        if version_key(c.get("version")).is_none() {
            self.error("/version", "invalid semver");
        }
        let rules = self.ids(&c, "rules");
        let concepts = self.ids(&c, "concepts");
        self.ids(&c, "relations");
        self.ids(&c, "error_cases");
        for (i, r) in self
            .array(c.get("relations"), "/relations")
            .iter()
            .enumerate()
        {
            if !matches!(r, Doc::Object(_)) {
                continue;
            }
            for side in ["from", "to"] {
                let at = format!("{}/{side}", pointer("/relations", i));
                for (j, v) in self.array(r.get(side), &at).iter().enumerate() {
                    if v.text().is_none_or(|s| s != "*" && !concepts.contains(s)) {
                        self.error(&pointer(&at, j), "unknown endpoint concept");
                    }
                }
            }
        }
        for (i, r) in self
            .array(c.get("error_cases"), "/error_cases")
            .iter()
            .enumerate()
        {
            if !matches!(r, Doc::Object(_)) {
                continue;
            }
            let at = format!("{}/rules", pointer("/error_cases", i));
            for (j, v) in self.array(r.get("rules"), &at).iter().enumerate() {
                if v.text().is_none_or(|s| !rules.contains(s)) {
                    self.error(&pointer(&at, j), "unknown rule");
                }
            }
        }
        let axes = self.object(c.get("axes"), "/axes");
        if axes.items().is_empty() {
            self.error("/axes", "axes need non-empty value maps");
        }
        for (axis, raw) in axes.items() {
            let at = pointer("/axes", axis);
            let axis = self.object(raw, &at);
            if axis.get("values").items().is_empty() {
                self.error(&format!("{at}/values"), "axis needs a non-empty value map");
            }
        }
        let spec = self.object(c.get("mapping"), "/mapping");
        for key in ["required_keys", "knowledge_supply_values"] {
            for (i, v) in self
                .array(spec.get(key), &format!("/mapping/{key}"))
                .iter()
                .enumerate()
            {
                self.text(
                    v,
                    &pointer(&format!("/mapping/{key}"), i),
                    "expected a non-empty string",
                );
            }
        }
        c
    }
    pub fn common_relation(&mut self, r: &Doc, at: &str, c: &Doc, required: bool) {
        let common = r.get("common").text();
        let rule = c
            .get("relations")
            .list()
            .iter()
            .find(|e| e.get("id").text() == common);
        if common.is_none() || rule.is_none() {
            self.error(&format!("{at}/common"), "unknown relation");
        } else if required {
            for side in ["from", "to"] {
                let v = r.get(side);
                let allowed = rule.unwrap_or(&NULL).get(side).list();
                let values = if v.text() == Some("*") {
                    vec![s("*")]
                } else {
                    self.array(v, &format!("{at}/{side}"))
                };
                if values.is_empty() {
                    self.error(&format!("{at}/{side}"), "needs non-empty endpoints");
                }
                for (j, e) in values.iter().enumerate() {
                    if e.text().is_none()
                        || (!c.get("concepts").list().iter().any(|x| x.get("id") == e)
                            && v.text() != Some("*"))
                        || (!allowed.contains(&s("*")) && !allowed.contains(e))
                    {
                        self.error(&pointer(&format!("{at}/{side}"), j), "endpoint not allowed");
                    }
                }
            }
        }
    }
    pub fn mapping(&mut self, raw: &Doc, c: &Doc, bytes: &[u8], root: &Path) -> Result<Doc> {
        let m = self.object(raw, "");
        for key in c.get("mapping").get("required_keys").list() {
            let key = key.text().unwrap_or_default();
            if !m.has(key) {
                self.error(&pointer("", key), "missing required key");
            }
        }
        if m.get("schema").text() != Some("mir-semantic-mapping/v1") {
            self.error("/schema", "invalid mapping schema");
        }
        let d = self.object(m.get("contract"), "/contract");
        if d.get("id") != c.get("contract_id") {
            self.error("/contract/id", "contract id mismatch");
        }
        let validated = version(d.get("version"));
        if validated.is_none() {
            self.error("/contract/version", "invalid semver");
        }
        let bounds = d
            .get("version_range")
            .text()
            .and_then(|s| captures(&format!("\\A{VERSION_RANGE}\\z"), s));
        let bounds = bounds.and_then(|b| Some((version(&s(&b[1]))?, version(&s(&b[2]))?)));
        if bounds.as_ref().is_none_or(|(lo, hi)| lo >= hi) {
            self.error(
                "/contract/version_range",
                "invalid version_range; use >=A.B.C <X.Y.Z",
            );
        } else if let Some((lo, hi)) = bounds {
            let loaded = version(c.get("version"));
            if loaded.as_ref().is_none_or(|v| v < &lo || v >= &hi) {
                self.error(
                    "/contract/version_range",
                    "version mismatch (E10): contract outside range",
                );
            } else if let Some(v) = &validated {
                if v < &lo || v >= &hi {
                    self.error(
                        "/contract/version",
                        "validated version outside its range (E10)",
                    );
                } else if Some(v) > loaded.as_ref() {
                    self.error(
                        "/contract/version",
                        "validated version is newer than the loaded contract (E10)",
                    );
                } else if Some(v) < loaded.as_ref() {
                    self.warn(
                        "/contract/version",
                        "validated against an older contract; re-validate (E10)",
                    );
                }
            }
        }
        if d.has("sha256") && d.get("sha256").text() != Some(&sha256(bytes)) {
            self.warn(
                "/contract/sha256",
                "contract sha256 differs from loaded file",
            );
        }
        let profile = ".mir/repo-profile.toml";
        let exists = if let Some(io) = self.io {
            io.exists(profile)?
        } else {
            root.join(profile).is_file()
        };
        if !exists {
            self.error("/namespace", "missing Profile: .mir/repo-profile.toml");
        } else {
            let text = if self.io.is_some() {
                self.read_text(profile)?
            } else {
                text_bytes(read(&root.join(profile))?)?
            };
            let slug = captures(r#"(?m)^\s*slug\s*=\s*"([^"\n]+)"\s*(?:#.*)?$"#, &text);
            if let Some(slug) = slug {
                if m.get("namespace").text() != Some(&slug[1]) {
                    self.error(
                        "/namespace",
                        "namespace mismatch with repository Profile slug",
                    );
                }
            } else {
                self.error("/namespace", r#"Profile needs a slug = "..." key"#);
            }
        }
        self.refs(m.get("canonical_index"), "/canonical_index", root)?;
        let concepts = self.object(m.get("concepts"), "/concepts");
        for concept in c.get("concepts").list() {
            let name = concept.get("id").text().unwrap_or_default();
            let at = pointer("/concepts", name);
            if !concepts.has(name) {
                self.error(&at, &format!("missing concept: {name}"));
                continue;
            }
            let entry = self.object(concepts.get(name), &at);
            match entry.get("status").text() {
                Some("mapped") => {
                    let local = self.array(entry.get("local"), &format!("{at}/local"));
                    if local.is_empty() {
                        self.error(
                            &format!("{at}/local"),
                            "mapped needs a non-empty local list",
                        );
                    }
                    for (i, raw) in local.iter().enumerate() {
                        let at = pointer(&format!("{at}/local"), i);
                        let item = self.object(raw, &at);
                        self.text(
                            item.get("name"),
                            &format!("{at}/name"),
                            "expected a non-empty string",
                        );
                        self.ref_check(item.get("ref"), &format!("{at}/ref"), root)?;
                    }
                }
                Some("absent" | "not_applicable") => {
                    self.text(
                        entry.get("reason"),
                        &format!("{at}/reason"),
                        "needs a non-empty reason",
                    );
                }
                _ => self.error(&format!("{at}/status"), "invalid concept status"),
            }
        }
        for (i, raw) in self
            .array(m.get("vocabularies"), "/vocabularies")
            .iter()
            .enumerate()
        {
            let at = pointer("/vocabularies", i);
            let v = self.object(raw, &at);
            self.text(
                v.get("name"),
                &format!("{at}/name"),
                "expected a non-empty string",
            );
            self.ref_check(v.get("ref"), &format!("{at}/ref"), root)?;
            for (word, raw) in self
                .object(v.get("values"), &format!("{at}/values"))
                .items()
            {
                let at = pointer(&format!("{at}/values"), word);
                let values = self.object(raw, &at);
                if values.has("local_only") {
                    self.text(
                        values.get("local_only"),
                        &format!("{at}/local_only"),
                        "expected a non-empty string",
                    );
                    if values.items().len() != 1 {
                        self.error(&at, "local_only cannot be combined with axes");
                    }
                    continue;
                }
                if values.items().is_empty() {
                    self.error(&at, "value needs a non-empty axis map");
                }
                for (axis, v) in values.items() {
                    if !c.get("axes").has(axis) {
                        self.error(&pointer(&at, axis), "unknown axis");
                    } else if v
                        .text()
                        .is_none_or(|v| !c.get("axes").get(axis).get("values").has(v))
                    {
                        self.error(&pointer(&at, axis), "unknown axis value");
                    }
                }
            }
        }
        let required = validated.is_some() && validated >= version(&s("1.1.0"));
        for (i, raw) in self
            .array(m.get("relations"), "/relations")
            .iter()
            .enumerate()
        {
            let at = pointer("/relations", i);
            let r = self.object(raw, &at);
            self.text(
                r.get("local"),
                &format!("{at}/local"),
                "needs a non-empty local relation",
            );
            if r.has("common") == r.has("local_only") {
                self.error(&at, "relation needs either common or local_only");
            } else if r.has("common") {
                self.common_relation(&r, &at, c, required);
            } else {
                self.text(
                    r.get("local_only"),
                    &format!("{at}/local_only"),
                    "expected a non-empty string",
                );
            }
            if r.has("ref") {
                self.ref_check(r.get("ref"), &format!("{at}/ref"), root)?;
            }
        }
        let domain = self.object(m.get("domain"), "/domain");
        for key in ["concepts", "relations", "invariants"] {
            let at = format!("/domain/{key}");
            for (i, raw) in self.array(domain.get(key), &at).iter().enumerate() {
                let at = pointer(&at, i);
                let e = self.object(raw, &at);
                self.ref_check(e.get("ref"), &format!("{at}/ref"), root)?;
                if key == "invariants" && e.has("check") {
                    self.covered_check(e.get("check"), &format!("{at}/check"), root)?;
                }
                if key == "relations" && e.has("common") {
                    self.common_relation(&e, &at, c, required);
                }
            }
        }
        let questions = self.array(m.get("questions"), "/questions");
        if questions.is_empty() {
            self.error("/questions", "at least one question is required");
        } else if questions.len() < 3 {
            self.warn("/questions", "fewer than three domain questions");
        }
        for (i, raw) in questions.iter().enumerate() {
            let at = pointer("/questions", i);
            let q = self.object(raw, &at);
            for key in ["id", "question"] {
                self.text(
                    q.get(key),
                    &format!("{at}/{key}"),
                    "expected a non-empty string",
                );
            }
            self.refs(q.get("evidence"), &format!("{at}/evidence"), root)?;
        }
        for (i, raw) in self
            .array(m.get("error_cases"), "/error_cases")
            .iter()
            .enumerate()
        {
            let at = pointer("/error_cases", i);
            let e = self.object(raw, &at);
            if e.get("id").text().is_none()
                || !c
                    .get("error_cases")
                    .list()
                    .iter()
                    .any(|x| x.get("id") == e.get("id"))
            {
                self.error(&format!("{at}/id"), "unknown error case");
            }
            let status = e.get("status").text();
            if !matches!(status, Some("covered" | "planned" | "not_applicable")) {
                self.error(&format!("{at}/status"), "invalid error case status");
            }
            if status == Some("covered") && !e.has("check") {
                self.error(&format!("{at}/check"), "covered needs a check ref");
            } else if status == Some("covered") {
                self.covered_check(e.get("check"), &format!("{at}/check"), root)?;
            } else if e.has("check") {
                self.ref_check(e.get("check"), &format!("{at}/check"), root)?;
            }
        }
        let supply = self.object(m.get("knowledge_supply"), "/knowledge_supply");
        if !c
            .get("mapping")
            .get("knowledge_supply_values")
            .list()
            .contains(supply.get("memory_keeper"))
        {
            self.error(
                "/knowledge_supply/memory_keeper",
                "invalid knowledge supply value",
            );
        }
        if supply.get("memory_keeper").text() == Some("connected")
            && !supply.has("binding")
            && !required
        {
            self.error("/knowledge_supply/binding", "connected needs a binding ref");
        } else if supply.has("binding") {
            if !required {
                self.ref_check(supply.get("binding"), "/knowledge_supply/binding", root)?;
            } else if !matches!(
                supply.get("binding").text(),
                Some("on_demand_stdio" | "resident_stdio")
            ) {
                self.error("/knowledge_supply/binding", "invalid binding value");
            }
        }
        self.refs(m.get("entrypoints"), "/entrypoints", root)?;
        for (at, e) in map_entries(&m) {
            for (p, r) in entry_refs(&e, &at) {
                if !self.checked_refs.contains(&p) {
                    self.ref_check(&s(r), &p, root)?;
                }
            }
        }
        Ok(d.get("version").clone())
    }
}
fn suffix(path: &Path) -> String {
    path.extension()
        .and_then(|s| s.to_str())
        .map_or(String::new(), |s| format!(".{}", s.to_lowercase()))
}
pub type JsonValidator<'a> = &'a dyn Fn(&str) -> Result<()>;
pub fn resolves_symbol(
    text: &str,
    name: &str,
    suffix: &str,
    validate: Option<JsonValidator<'_>>,
) -> Result<bool> {
    if name.is_empty() {
        return Ok(false);
    }
    let candidates = [name, name.rsplit('.').next().unwrap_or(name)];
    let mut text = text.to_owned();
    if [".md", ".markdown", ".mdx"].contains(&suffix) {
        if let Ok(re) = regex::Regex::new(r"<!--[\s\S]*?-->") {
            text = re.replace_all(&text, "").into_owned();
        }
        let slug_re = regex::Regex::new(r"[^\w -]").ok();
        let mut seen = BTreeSet::new();
        let mut fence: Option<String> = None;
        let mut lines = vec![];
        for line in text.lines() {
            if let Some(c) = captures(r"^ {0,3}(`{3,}|~{3,})", line) {
                if fence.is_none() {
                    fence = Some(c[1].clone());
                } else if fence.as_ref().is_some_and(|f| {
                    f.starts_with(c[1].chars().next().unwrap_or(' ')) && c[1].len() >= f.len()
                }) {
                    fence = None;
                }
                continue;
            }
            if fence.is_some() {
                continue;
            }
            lines.push(line);
            if let Some(c) = captures(r"^ {0,3}#{1,6}\s+(.+?)\s*#*\s*$", line) {
                let title = &c[1];
                let slug = slug_re.as_ref().map_or(String::new(), |re| {
                    re.replace_all(&title.to_lowercase(), "").replace(' ', "-")
                });
                let mut unique = slug.clone();
                let mut count = 0;
                while seen.contains(&unique) {
                    count += 1;
                    unique = format!("{slug}-{count}");
                }
                seen.insert(unique.clone());
                if name == unique || candidates.contains(&title.as_str()) {
                    return Ok(true);
                }
            }
        }
        text = lines.join("\n");
    }
    if suffix == ".json" {
        if let Some(validate) = validate {
            validate(&text)?;
        }
        let Ok(doc) = serde_json::from_str::<Value>(&text) else {
            return Ok(false);
        };
        if name.contains(['/', '~']) {
            let mut v = &doc;
            for part in name.strip_prefix('/').unwrap_or(name).split('/') {
                if matched(r"~(?![01])", part) {
                    return Ok(false);
                }
                let key = part.replace("~1", "/").replace("~0", "~");
                v = match v {
                    Value::Object(m) => {
                        if let Some(v) = m.get(&key) {
                            v
                        } else {
                            return Ok(false);
                        }
                    }
                    Value::Array(a) if matched(&format!("\\A{NUMBER}\\z"), &key) => {
                        let Some(v) = key.parse::<usize>().ok().and_then(|i| a.get(i)) else {
                            return Ok(false);
                        };
                        v
                    }
                    _ => return Ok(false),
                };
            }
            return Ok(true);
        }
        let mut values = vec![&doc];
        while let Some(v) = values.pop() {
            match v {
                Value::Object(m) => {
                    if candidates.iter().any(|s| m.contains_key(*s)) {
                        return Ok(true);
                    }
                    values.extend(m.values());
                }
                Value::Array(a) => values.extend(a),
                _ => {}
            }
        }
        return Ok(false);
    }
    let mut modifiers =
        r"(?:(?:export|default|public|private|protected|static|async|pub|open)\s+)*";
    let kotlin = [".kt", ".kts", ".dart"].contains(&suffix);
    if kotlin {
        if let Ok(re) = regex::Regex::new(r"/\*[\s\S]*?\*/|//[^\n]*") {
            text = re.replace_all(&text, "").into_owned();
        }
        modifiers = r"(?:(?:\w+|@[\w.]+(?:\([^\n]*?\))?)\s+)*";
    }
    for candidate in candidates {
        let symbol = regex::escape(candidate);
        let boundary = if kotlin {
            r"(?=\s*(?:[({:<=>]|\b(?:extends|implements|with)\b|$))"
        } else {
            r"(?![\w$])"
        };
        let mut patterns = vec![
            format!(
                concat!(
                    r"(?m)^\s*{}",
                    r"(?:def|class|function|const|let|var|interface|type|enum|struct|",
                    r"fn|func|val|fun|object)",
                    r"\s+(?:<[^>\n]+>\s*)?{}{}"
                ),
                modifiers, symbol, boundary
            ),
            format!(r"(?m)^\s*{symbol}\s*(?::|=(?!=))"),
            format!(r#"(?m)^\s*["']?{symbol}["']?\s*=(?!=)"#),
            format!(r"(?m)^\s*\[\[?\s*{symbol}\s*\]\]?\s*(?:#.*)?$"),
            format!(r#"(?m)^\s*(?:test|it|describe)\s*\(\s*["']{symbol}["']"#),
        ];
        if [".sh", ".bash", ".zsh"].contains(&suffix) {
            patterns.push(format!(r"(?m)^\s*(?:function\s+)?{symbol}\s*\(\s*\)\s*\{{"));
            patterns.push(format!(r"(?m)^\s*function\s+{symbol}\s*\{{"));
        }
        if patterns.iter().any(|p| matched(p, &text)) {
            return Ok(true);
        }
    }
    Ok(false)
}
pub fn map_entries(m: &Doc) -> Vec<(String, Doc)> {
    let mut out = vec![];
    for section in [
        "canonical_index",
        "concepts",
        "relations",
        "domain",
        "questions",
        "error_cases",
        "vocabularies",
        "entrypoints",
        "knowledge_supply",
    ] {
        let v = m.get(section);
        if section == "domain" && matches!(v, Doc::Object(_)) {
            for (kind, entries) in v.items() {
                for (i, e) in entries.list().iter().enumerate() {
                    out.push((pointer(&pointer("/domain", kind), i), e.clone()));
                }
            }
        } else if section == "concepts" && matches!(v, Doc::Object(_)) {
            for (k, e) in v.items() {
                out.push((pointer("/concepts", k), e.clone()));
            }
        } else if let Doc::Array(a) = v {
            for (i, e) in a.iter().enumerate() {
                out.push((pointer(&format!("/{section}"), i), e.clone()));
            }
        } else if section == "knowledge_supply" && matches!(v, Doc::Object(_)) {
            out.push(("/knowledge_supply".into(), v.clone()));
        }
    }
    out
}
pub fn entry_refs(e: &Doc, at: &str) -> Vec<(String, String)> {
    let mut out = vec![];
    if let Some(s) = e.text() {
        out.push((at.into(), s.into()));
    } else if let Doc::Array(a) = e {
        for (i, v) in a.iter().enumerate() {
            out.extend(entry_refs(v, &pointer(at, i)));
        }
    } else {
        for (k, v) in e.items() {
            let p = pointer(at, k);
            if ["ref", "check"].contains(&k.as_str()) && v.text().is_some() {
                out.push((p, v.text().unwrap_or_default().into()));
            } else if k == "binding" && v.text().is_some() {
                if !matches!(v.text(), Some("on_demand_stdio" | "resident_stdio")) {
                    out.push((p, v.text().unwrap_or_default().into()));
                }
            } else if k == "evidence" && matches!(v, Doc::Array(_)) || matches!(v, Doc::Object(_)) {
                out.extend(entry_refs(v, &p));
            } else {
                for (i, v) in v.list().iter().enumerate() {
                    if matches!(v, Doc::Array(_) | Doc::Object(_)) {
                        out.extend(entry_refs(v, &pointer(&p, i)));
                    }
                }
            }
        }
    }
    out
}
pub fn ref_path(r: &str) -> String {
    let path = r.split('#').next().unwrap_or_default();
    captures(r":\d+$", path).map_or_else(|| path.into(), |c| path[..path.len() - c[0].len()].into())
}
fn posix(p: &str) -> String {
    let prefix = if p.starts_with("//") && !p.starts_with("///") {
        "//"
    } else if p.starts_with('/') {
        "/"
    } else {
        ""
    };
    let parts = p
        .split('/')
        .filter(|s| !s.is_empty() && *s != ".")
        .collect::<Vec<_>>()
        .join("/");
    if parts.is_empty() && prefix.is_empty() {
        ".".into()
    } else {
        format!("{prefix}{parts}")
    }
}
pub fn touches(path: &str, changed: &[String]) -> bool {
    let p = posix(path);
    changed
        .iter()
        .any(|s| s == &p || s.starts_with(&format!("{}/", p.trim_end_matches('/'))))
}
/// The adapter receives argv and the Python subprocess timeout; implementations own execution.
pub trait GitRunner {
    fn run(&self, argv: &[String], timeout: u64) -> Result<GitOutput>;
}
pub struct GitOutput {
    pub returncode: i32,
    pub stdout: Vec<u8>,
    pub stderr: Vec<u8>,
}
pub fn changed_paths(
    paths: Option<&[String]>,
    base: &str,
    root: &Path,
    git: &dyn GitRunner,
) -> Result<Vec<String>> {
    let mut out = BTreeSet::new();
    if let Some(paths) = paths {
        for raw in paths {
            let p = Path::new(raw);
            let path = if p.is_absolute() {
                p.strip_prefix(root).map_err(|_| {
                    error(
                        "ValueError",
                        format!("'{raw}' is not in the subpath of '{}'", root.display()),
                    )
                })?
            } else {
                p
            };
            let path = path
                .to_str()
                .ok_or_else(|| error("UnicodeError", "non-UTF-8 path"))?;
            if path.split('/').any(|p| p == "..") {
                return Err(error(
                    "ValueError",
                    "changed paths must stay within the repository",
                ));
            }
            out.insert(posix(path));
        }
    } else {
        if base.starts_with('-') {
            return Err(error(
                "ValueError",
                "git diff BASE must be a revision, not an option",
            ));
        }
        for rev in [vec!["--cached", base], vec![]] {
            let mut argv = vec![
                "git".into(),
                "-C".into(),
                root.display().to_string(),
                "diff".into(),
            ];
            argv.extend(
                [
                    "--no-ext-diff",
                    "--no-textconv",
                    "--no-renames",
                    "--name-only",
                    "-z",
                ]
                .map(String::from),
            );
            argv.extend(rev.into_iter().map(String::from));
            argv.push("--".into());
            let r = git.run(&argv, 10)?;
            if r.returncode != 0 {
                return Err(error(
                    "ValueError",
                    format!(
                        "git diff failed: {}",
                        String::from_utf8_lossy(&r.stderr).trim()
                    ),
                ));
            }
            let text =
                String::from_utf8(r.stdout).map_err(|e| error("UnicodeError", e.to_string()))?;
            out.extend(text.split('\0').filter(|s| !s.is_empty()).map(String::from));
        }
    }
    Ok(out.into_iter().collect())
}
pub fn impact(
    m: &Doc,
    root: &Path,
    changed: &[String],
    git_diff: bool,
    io: Option<&dyn Reader>,
) -> Result<Doc> {
    let (mut affected, mut stale, mut undeclared) = (vec![], vec![], vec![]);
    let (mut paths, mut checks) = (BTreeSet::new(), BTreeSet::new());
    for (at, e) in map_entries(m) {
        let refs = entry_refs(&e, &at);
        if refs.iter().any(|(_, r)| touches(&ref_path(r), changed)) {
            affected.push(object! {
                "pointer" => s(&at),
                "refs" => arr(refs.iter().map(|(_, r)| s(r)).collect()),
            });
            paths.extend(refs.iter().map(|(_, r)| ref_path(r)));
            if at.starts_with("/domain/invariants/") && matches!(e, Doc::Object(_)) {
                if let Some(check) = e.get("check").text() {
                    checks.insert(check.to_owned());
                } else if !e.has("check") {
                    undeclared.push(object! {
                        "pointer" => s(&at),
                        "ref" => e.get("ref").clone(),
                        "message" => s("no check declared; no test link inferred"),
                    });
                }
            }
        }
        for (p, r) in refs {
            let mut check = Checker::new(io);
            if git_diff
                && matched(r":\d+$", r.split('#').next().unwrap_or_default())
                && touches(&ref_path(&r), changed)
            {
                stale.push(object! {
                    "pointer" => s(&p),
                    "ref" => s(&r),
                    "message" => s(format!("re-anchor to a symbol: {at}")),
                });
            }
            let result = if p.ends_with("/check")
                && matches!(e, Doc::Object(_))
                && (at.starts_with("/domain/invariants/")
                    || (at.starts_with("/error_cases/")
                        && e.get("status").text() == Some("covered")))
            {
                check.covered_check(&s(&r), &p, root)
            } else {
                check.ref_check(&s(&r), &p, root).map(|_| ())
            };
            if let Err(e) = result {
                if io.is_some() {
                    return Err(e);
                }
                check.error(&p, "ref could not be resolved");
            }
            for mut f in check.errors {
                f.set("ref", s(&r));
                stale.push(f);
            }
        }
    }
    for e in m.get("error_cases").list() {
        if e.get("status").text() == Some("covered")
            && let Some(r) = e.get("check").text()
            && (touches(&ref_path(r), changed) || paths.iter().any(|p| touches(p, &[ref_path(r)])))
        {
            checks.insert(r.to_owned());
        }
    }
    Ok(object! {
        "changed_paths" => Doc::from(json!(changed)),
        "affected_entries" => arr(affected),
        "checks_to_run" => Doc::from(json!(checks)),
        "undeclared_check_links" => arr(undeclared),
        "stale_refs" => arr(stale),
        "revalidate" => Doc::from(json!(changed.iter().any(|s| s == ".mir/ontology-map.json"))),
    })
}
pub fn lookup(m: &Doc, query: &str, limit: usize, io: Option<&dyn Reader>) -> Result<Doc> {
    let words = |s: &str| -> BTreeSet<String> {
        regex::Regex::new(r"[\p{L}\p{N}]+")
            .ok()
            .map_or_else(BTreeSet::new, |re| {
                re.find_iter(&casefold(s))
                    .map(|m| m.as_str().to_owned())
                    .collect()
            })
    };
    let terms = words(query);
    let mut matches = vec![];
    for (at, e) in map_entries(m) {
        if !["/questions/", "/concepts/", "/domain/"]
            .iter()
            .any(|s| at.starts_with(s))
        {
            continue;
        }
        let score = terms
            .intersection(&words(&format!("{at} {}", e.dump(false, None))))
            .count();
        if score == 0 {
            continue;
        }
        let mut refs = vec![];
        for (_, r) in entry_refs(&e, &at) {
            if !refs.contains(&r) {
                refs.push(r);
            }
        }
        matches.push((
            score,
            object! {
                "pointer" => s(at),
                "score" => Doc::from(json!(score)),
                "entry" => e,
                "evidence" => Doc::from(json!(refs)),
            },
        ));
    }
    matches.sort_by_key(|(score, _)| std::cmp::Reverse(*score));
    matches.truncate(limit);
    if let Some(io) = io {
        for (_, m) in &matches {
            for r in m.get("evidence").list() {
                io.path(&ref_path(r.text().unwrap_or_default()), true)?;
            }
        }
    }
    Ok(object! {
        "contract" => if m.has("contract") { m.get("contract").clone() } else { object! {} },
        "matches" => arr(matches.into_iter().map(|(_, m)| m).collect()),
    })
}
pub fn positive_int(raw: &str) -> Result<i64> {
    // Python int(): whitespace, a sign, underscores between digits, Unicode digits, any size.
    let v = super::relations_query::cli_integer(raw).ok_or_else(|| {
        error(
            "ValueError",
            format!("invalid literal for int() with base 10: {}", py_repr(raw)),
        )
    })?;
    if v < 1 {
        Err(error("ArgumentTypeError", "must be positive"))
    } else {
        Ok(v)
    }
}
pub fn finalize_handoff_pins(mut pins: Doc, paths: &[String]) -> Doc {
    let mut inventory = vec![];
    let mut unknowns = pins.get("unknowns").list().to_vec();
    let mut add = |pin: String, pointer: String, kind: &str, required: bool, value: &Doc| {
        let available = !matches!(value, Doc::Scalar(Value::Null))
            && !matches!(value.text(), Some("" | "untracked"));
        inventory.push(object! {
            "pin" => s(&pin),
            "pointer" => s(pointer),
            "kind" => s(kind),
            "required" => Doc::from(json!(required)),
            "availability" => s(if available { "available" } else { "unknown" }),
        });
        let reason = s(format!("{pin}: unavailable"));
        if required && !available && !unknowns.contains(&reason) {
            unknowns.push(reason);
        }
    };
    for (pin, key, kind) in [
        ("repository_root", "repository_root", "path"),
        ("head", "head", "commit"),
        ("mapping.identity", "mapping_path", "path"),
        ("mapping.version", "mapping_version", "version"),
        ("mapping.digest", "mapping_sha256", "sha256"),
        ("contract.identity", "contract_id", "id"),
        ("contract.version", "contract_version", "version"),
        ("contract.digest", "contract_sha256", "sha256"),
    ] {
        add(pin.into(), format!("/{key}"), kind, true, pins.get(key));
    }
    for (i, _) in paths.iter().enumerate() {
        let source = pins.get("sources").list().get(i).unwrap_or(&NULL);
        add(
            format!("sources[{i}].digest"),
            format!("/sources/{i}/sha256"),
            "sha256",
            true,
            source.get("sha256"),
        );
        add(
            format!("sources[{i}].revision"),
            format!("/sources/{i}/revision"),
            "last_change_commit",
            false,
            source.get("revision"),
        );
    }
    pins.set("unknowns", arr(unknowns));
    pins.set("pin_inventory", arr(inventory));
    pins
}
pub trait PinRunner {
    fn run(&self, label: &str, args: &[String]) -> Result<Doc>;
}
pub struct Context<'a> {
    pub git: &'a dyn GitRunner,
    pub observed_at: &'a str,
}
fn git_pin(
    ctx: &Context<'_>,
    runner: Option<&dyn PinRunner>,
    root: &Path,
    label: &str,
    args: &[&str],
    unknowns: &mut Vec<Doc>,
) -> Option<Doc> {
    let result = if let Some(r) = runner {
        r.run(label, &args.iter().map(|s| (*s).into()).collect::<Vec<_>>())
    } else {
        let mut argv = vec![
            "git".into(),
            "--no-optional-locks".into(),
            "--literal-pathspecs".into(),
            "-C".into(),
            root.display().to_string(),
        ];
        argv.extend(args.iter().map(|s| (*s).into()));
        ctx.git.run(&argv, 5).and_then(|r| {
            if r.returncode == 0 && label.ends_with("modified_vs_head") {
                Ok(Doc::from(json!(r.stdout)))
            } else if r.returncode == 0 {
                String::from_utf8(r.stdout)
                    .map(|s| {
                        if label == "dirty" {
                            s
                        } else {
                            s.trim().to_owned()
                        }
                    })
                    .map(s)
                    .map_err(|e| error("UnicodeError", e.to_string()))
            } else {
                Ok(Doc::null())
            }
        })
    };
    match result {
        Ok(Doc::Scalar(Value::Null)) => {
            unknowns.push(s(format!("{label}: git command failed")));
            None
        }
        Ok(v) => Some(v),
        Err(e) => {
            unknowns.push(s(format!("{label}: {e}")));
            None
        }
    }
}
pub fn handoff_pins(
    repo: &Path,
    paths: &[String],
    report: &Doc,
    io: Option<&dyn Reader>,
    runner: Option<&dyn PinRunner>,
    ctx: &Context<'_>,
) -> Result<Doc> {
    if io.is_some() && runner.is_none() {
        return Err(error(
            "ValueError",
            "guarded handoff_pins requires git_runner",
        ));
    }
    let root = resolve(repo)?;
    let mut pins = object! {
        "repository_root" => s(root.display().to_string()),
        "head" => Doc::null(),
        "dirty" => Doc::null(),
        "sources" => arr(vec![]),
    };
    let mut unknowns = vec![];
    for key in [
        "mapping_path",
        "mapping_version",
        "mapping_sha256",
        "contract_id",
        "contract_version",
        "contract_sha256",
    ] {
        pins.set(key, report.get(key).clone());
        if report.get(key) == &NULL {
            unknowns.push(s(format!("{key}: unavailable")));
        }
    }
    pins.set("observed_at", s(ctx.observed_at));
    let head = git_pin(
        ctx,
        runner,
        &root,
        "head",
        &["rev-parse", "--verify", "HEAD"],
        &mut unknowns,
    );
    pins.set("head", head.clone().unwrap_or_else(Doc::null));
    let status_args = if runner.is_some() {
        vec![
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
            "--ignore-submodules=all",
        ]
    } else {
        vec!["status", "--porcelain", "--untracked-files=all"]
    };
    let status = git_pin(ctx, runner, &root, "dirty", &status_args, &mut unknowns);
    pins.set(
        "dirty",
        status.map_or_else(Doc::null, |v| {
            Doc::from(json!(
                v.text().is_some_and(|s| !s.is_empty()) || v == Doc::from(json!(true))
            ))
        }),
    );
    let mut sources = vec![];
    for raw in paths {
        let mut source = object! {
            "path" => s(raw),
            "revision" => Doc::null(),
            "sha256" => Doc::null(),
            "modified_vs_head" => Doc::null(),
        };
        let path = if let Some(io) = io {
            io.path(raw, true)?
        } else {
            resolve(&root.join(raw))?
        };
        let relative = path
            .strip_prefix(&root)
            .map_err(|_| error("ValueError", "outside repository"))?
            .to_str()
            .ok_or_else(|| error("UnicodeError", "non-UTF-8 path"))?
            .replace('\\', "/");
        source.set("path", s(&relative));
        let payload = if let Some(io) = io {
            if !io.exists(raw)? {
                unknowns.push(s(format!("{relative}: file unavailable")));
                sources.push(source);
                continue;
            }
            io.read(raw)?
        } else {
            match read(&path) {
                Ok(b) => b,
                Err(e) => {
                    unknowns.push(s(format!("{relative}: file unavailable: {e}")));
                    sources.push(source);
                    continue;
                }
            }
        };
        source.set("sha256", s(sha256(&payload)));
        let revision = git_pin(
            ctx,
            runner,
            &root,
            &format!("{relative}.revision"),
            &["log", "-1", "--format=%H", "--", &relative],
            &mut unknowns,
        );
        if let Some(revision) = revision {
            let revision = if revision.text() == Some("") {
                s("untracked")
            } else {
                revision
            };
            if revision.text() != Some("untracked") {
                source.set("revision_kind", s("last_change_commit"));
            }
            source.set("revision", revision);
        }
        if source.get("revision").text() == Some("untracked") {
            unknowns.push(s(format!("{relative}.modified_vs_head: untracked")));
        } else if head.is_some() {
            let v = if runner.is_some() {
                git_pin(
                    ctx,
                    runner,
                    &root,
                    &format!("{relative}.modified_vs_head"),
                    &[
                        "diff",
                        "--quiet",
                        "--no-ext-diff",
                        "--no-textconv",
                        "--ignore-submodules=all",
                        "HEAD",
                        "--",
                        &relative,
                    ],
                    &mut unknowns,
                )
            } else {
                git_pin(
                    ctx,
                    runner,
                    &root,
                    &format!("{relative}.modified_vs_head"),
                    &["show", &format!("HEAD:{relative}")],
                    &mut unknowns,
                )
                .map(|v| Doc::from(json!(v.value() != json!(payload))))
            };
            source.set("modified_vs_head", v.unwrap_or_else(Doc::null));
        } else {
            unknowns.push(s(format!("{relative}.modified_vs_head: HEAD unavailable")));
        }
        sources.push(source);
    }
    pins.set("sources", arr(sources));
    pins.set("unknowns", arr(unknowns));
    Ok(finalize_handoff_pins(pins, paths))
}
pub struct Output {
    pub exit: i32,
    pub stdout: String,
    pub stderr: String,
}
const USAGE: &str = "usage: ontology_check.py [-h] {contract,mapping,impact,lookup} ...\n";
fn usage(command: &str) -> String {
    match command {
        "lookup" => concat!(
            "usage: ontology_check.py lookup [-h] [--contract CONTRACT] --repo REPO\n",
            "                                [--json] [--limit LIMIT]\n",
            "                                query\n"
        )
        .into(),
        "mapping" => concat!(
            "usage: ontology_check.py mapping [-h] [--handoff [PATH ...]]\n",
            "                                 [--contract CONTRACT] --repo REPO [--json]\n"
        )
        .into(),
        "impact" => concat!(
            "usage: ontology_check.py impact [-h] [--contract CONTRACT] --repo REPO\n",
            "                                [--json] (--paths PATHS [PATHS ...] | ",
            "--git-diff [BASE])\n",
            "                                [--strict]\n"
        )
        .into(),
        _ => "usage: ontology_check.py contract [-h] [--contract CONTRACT]\n".into(),
    }
}
fn cli_error(command: &str, message: &str) -> Output {
    let u = if command.is_empty() {
        USAGE.into()
    } else {
        usage(command)
    };
    Output {
        exit: 2,
        stdout: String::new(),
        stderr: format!(
            "{u}ontology_check.py{}: error: {message}\n",
            if command.is_empty() {
                String::new()
            } else {
                format!(" {command}")
            }
        ),
    }
}
fn display(v: &Doc) -> String {
    v.text().map(str::to_owned).unwrap_or_else(|| {
        if v == &NULL {
            "None".into()
        } else {
            v.dump(false, None)
        }
    })
}
/// argv excludes the script name. Environment-sensitive operations are injected.
pub fn main(argv: &[String], ctx: &Context<'_>) -> Output {
    let command = argv.first().map(String::as_str).unwrap_or("");
    if !["contract", "mapping", "impact", "lookup"].contains(&command) {
        let chosen = if command.is_empty() || command.starts_with('-') {
            argv.iter()
                .find(|s| !s.starts_with('-'))
                .map(String::as_str)
                .unwrap_or("")
        } else {
            command
        };
        return cli_error(
            "",
            &format!(
                "argument command: invalid choice: {} \
(choose from contract, mapping, impact, lookup)",
                py_repr(chosen)
            ),
        );
    }
    let (mut repo, mut contract) = (None, PathBuf::from(DEFAULT_CONTRACT));
    let (mut json_output, mut strict, mut diff) = (false, false, None);
    let (mut paths, mut handoff) = (None, None);
    let (mut query, mut limit) = (String::new(), 3usize);
    let mut i = 1;
    while i < argv.len() {
        let arg = &argv[i];
        i += 1;
        match arg.as_str() {
            "--json" => json_output = true,
            "--strict" => strict = true,
            "--contract" | "--repo" | "--limit" => {
                let Some(v) = argv.get(i) else {
                    return cli_error(command, &format!("argument {arg}: expected one argument"));
                };
                i += 1;
                match arg.as_str() {
                    "--contract" => contract = PathBuf::from(v),
                    "--repo" => repo = Some(PathBuf::from(v)),
                    _ => match positive_int(v) {
                        Ok(n) => limit = n as usize,
                        // argparse reports a type function's ValueError as an invalid value.
                        Err(e) if e.class == "ValueError" => {
                            let message = format!("invalid positive_int value: {}", py_repr(v));
                            return cli_error(command, &format!("argument --limit: {message}"));
                        }
                        Err(e) => return cli_error(command, &format!("argument --limit: {e}")),
                    },
                }
            }
            "--paths" | "--handoff" => {
                let mut values = vec![];
                while i < argv.len() && !argv[i].starts_with('-') {
                    values.push(argv[i].clone());
                    i += 1;
                }
                if arg == "--paths" {
                    paths = Some(values);
                } else {
                    handoff = Some(values);
                }
            }
            "--git-diff" => {
                diff = Some(if i < argv.len() && !argv[i].starts_with('-') {
                    let s = argv[i].clone();
                    i += 1;
                    s
                } else {
                    "HEAD".into()
                });
            }
            s if command == "lookup" && !s.starts_with('-') => query = s.into(),
            _ => return cli_error(command, &format!("unrecognized arguments: {arg}")),
        }
    }
    if command != "contract" && repo.is_none() {
        return cli_error(command, "the following arguments are required: --repo");
    }
    if command == "impact" && paths.is_none() && diff.is_none() {
        return cli_error(
            command,
            "one of the arguments --paths --git-diff is required",
        );
    }
    let mut checker = Checker::new(None);
    let mut io_problem = false;
    let mut selection = None;
    let (mut cv, mut mv, mut mp, mut ms, mut ci, mut cs) = (
        Doc::null(),
        Doc::null(),
        Doc::null(),
        Doc::null(),
        Doc::null(),
        Doc::null(),
    );
    let work = || -> Result<()> {
        let payload = read(&contract)?;
        let c = checker.contract(&load_json(&text_bytes(payload.clone())?)?);
        cv = c.get("version").clone();
        ci = c.get("contract_id").clone();
        cs = s(sha256(&payload));
        if command != "contract" && checker.errors.is_empty() {
            let root = resolve(repo.as_deref().unwrap_or(Path::new(".")))?;
            if !root.is_dir() {
                return Err(error("OSError", "repository root is not a directory"));
            }
            if command == "impact" {
                selection = Some(impact(
                    &object! {},
                    &root,
                    &changed_paths(
                        paths.as_deref(),
                        diff.as_deref().unwrap_or(""),
                        &root,
                        ctx.git,
                    )?,
                    false,
                    None,
                )?);
            }
            let file = root.join(".mir/ontology-map.json");
            let text = match read(&file) {
                Ok(b) => {
                    let text = text_bytes(b.clone())?;
                    mp = s(".mir/ontology-map.json");
                    ms = s(sha256(&b));
                    text
                }
                Err(e) if e.class == "FileNotFoundError" && command == "impact" => {
                    checker.error("", "mapping file is missing");
                    "{}".into()
                }
                Err(e) => return Err(e),
            };
            if text.len() > MAPPING_BUDGET {
                checker.warn(
                    "/",
                    &format!(
                        "mapping is {} bytes, over the {MAPPING_BUDGET}-byte budget",
                        text.len()
                    ),
                );
            }
            let m = match load_json(&text) {
                Ok(m) => m,
                Err(_) if command == "impact" => {
                    checker.error("", "mapping is invalid JSON");
                    object! {}
                }
                Err(e) => return Err(e),
            };
            mv = checker.mapping(&m, &c, &payload, &root)?;
            let m = if matches!(m, Doc::Object(_)) {
                m
            } else {
                object! {}
            };
            if command == "impact" {
                let changed = selection
                    .as_ref()
                    .unwrap_or(&NULL)
                    .get("changed_paths")
                    .list()
                    .iter()
                    .map(display)
                    .collect::<Vec<_>>();
                selection = Some(impact(&m, &root, &changed, diff.is_some(), None)?);
            } else if command == "lookup" {
                selection = Some(lookup(&m, &query, limit, None)?);
            }
        }
        Ok(())
    };
    let mut work = work;
    if let Err(e) = work() {
        checker.error("", &format!("IO problem: {e}"));
        io_problem = true;
    }
    let mut report = object! {
        "ok" => Doc::from(json!(checker.errors.is_empty())),
        "errors" => arr(checker.errors.clone()),
        "warnings" => arr(checker.warnings.clone()),
        "contract_version" => cv.clone(),
        "mapping_version" => mv.clone(),
        "line_ref_count" => Doc::from(json!(checker.line_refs.len())),
    };
    if command == "mapping" {
        for (k, v) in [
            ("mapping_path", mp.clone()),
            ("mapping_sha256", ms.clone()),
            ("contract_id", ci.clone()),
            ("contract_sha256", cs.clone()),
        ] {
            report.set(k, v);
        }
        if let Some(paths) = handoff
            && let Ok(pins) = handoff_pins(
                repo.as_deref().unwrap_or(Path::new(".")),
                &paths,
                &report,
                None,
                None,
                ctx,
            )
        {
            report.set("handoff", pins);
        }
    }
    let mut stdout = String::new();
    let mut line = |s: String| {
        stdout.push_str(&s);
        stdout.push('\n');
    };
    let selected = ["impact", "lookup"].contains(&command);
    if selected {
        if let Some(sel) = &selection {
            for (k, v) in sel.items() {
                report.set(k, v.clone());
            }
        }
        if json_output {
            line(report.dump(false, None));
        } else {
            if let Some(sel) = &selection {
                if command == "impact" {
                    line("affected entries:".into());
                    for e in sel.get("affected_entries").list() {
                        line(format!(
                            "  {}: {}",
                            display(e.get("pointer")),
                            join(e.get("refs"))
                        ));
                    }
                    line("checks to run (selection only):".into());
                    for r in sel.get("checks_to_run").list() {
                        line(format!("  {}", display(r)));
                    }
                    line("undeclared check links (no inference):".into());
                    for e in sel.get("undeclared_check_links").list() {
                        line(format!(
                            "  {}: {}",
                            display(e.get("pointer")),
                            display(e.get("message"))
                        ));
                    }
                    line("stale refs:".into());
                    for e in sel.get("stale_refs").list() {
                        line(format!(
                            "  {}: {}: {}",
                            display(e.get("pointer")),
                            display(e.get("ref")),
                            display(e.get("message"))
                        ));
                    }
                    if sel.get("revalidate") == &Doc::from(json!(true)) {
                        line("map changed: re-validate".into());
                    }
                } else {
                    line(format!(
                        "{} {}",
                        display(sel.get("contract").get("id")),
                        display(sel.get("contract").get("version"))
                    ));
                    for e in sel.get("matches").list() {
                        line(format!(
                            "{}: {}",
                            display(e.get("pointer")),
                            e.get("entry").dump(false, None)
                        ));
                        line(format!("  evidence: {}", join(e.get("evidence"))));
                    }
                }
            }
            for e in &checker.errors {
                line(format!(
                    "ERROR {}: {}",
                    display(e.get("pointer")),
                    display(e.get("message"))
                ));
            }
        }
    } else if json_output {
        line(report.dump(false, None));
    } else {
        if command == "mapping" {
            line(format!(
                "INFO {} line-number refs (1.x compatibility)",
                checker.line_refs.len()
            ));
            line(format!(
                "INFO mapping {} sha256 {}; contract {} sha256 {}",
                display(&mp),
                display(&ms),
                display(&ci),
                display(&cs)
            ));
        }
        for (label, findings) in [("ERROR", &checker.errors), ("WARN", &checker.warnings)] {
            for e in findings {
                line(format!(
                    "{label} {}: {}",
                    display(e.get("pointer")),
                    display(e.get("message"))
                ));
            }
        }
        line(format!(
            "{} errors, {} warnings; contract {}, mapping {}",
            checker.errors.len(),
            checker.warnings.len(),
            display(&cv),
            display(&mv)
        ));
        if report.has("handoff") {
            line("handoff pins:".into());
            line(report.get("handoff").dump(false, Some(2)));
        }
    }
    let exit = if io_problem {
        2
    } else if selected {
        i32::from(
            command == "impact"
                && strict
                && (!checker.errors.is_empty()
                    || selection
                        .as_ref()
                        .is_some_and(|s| !s.get("stale_refs").list().is_empty())),
        )
    } else {
        i32::from(!checker.errors.is_empty())
    };
    Output {
        exit,
        stdout,
        stderr: String::new(),
    }
}
fn join(v: &Doc) -> String {
    v.list().iter().map(display).collect::<Vec<_>>().join(", ")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn errno_filename_repr_matches_shared_helper() {
        let root = tempfile::tempdir().unwrap();
        let path = root.path().join("missing'with\\backslash");
        assert_eq!(
            io_error(fs::read(&path).unwrap_err(), &path).message,
            crate::executor_brief_profile::python_os_error_message(
                &fs::read(&path).unwrap_err(),
                &path
            )
        );
    }

    #[test]
    fn directory_errno_filename_repr() {
        let root = tempfile::tempdir().unwrap();
        let path = root.path().join("directory'with\\backslash");
        fs::create_dir_all(&path).unwrap();
        let failure = read(&path).unwrap_err();
        assert_eq!(
            failure.class,
            if cfg!(windows) {
                "PermissionError"
            } else {
                "IsADirectoryError"
            }
        );
        assert_eq!(
            failure.message,
            format!(
                "{}: {}",
                if cfg!(windows) {
                    "[Errno 13] Permission denied"
                } else {
                    "[Errno 21] Is a directory"
                },
                py_repr(&path.display().to_string())
            )
        );
    }

    #[cfg(windows)]
    #[test]
    fn windows_errno_filename_repr_matches_capture() {
        let root = tempfile::tempdir().unwrap();
        let path = root.path().join("absent");
        let failure = read(&path).unwrap_err();
        let capture: serde_json::Value = serde_json::from_str(include_str!(
            "../../tests/fixtures/wt-path-records-b33-windows.json"
        ))
        .unwrap();
        let unknown =
            capture["records"]["core"]["pins"]["value"][0]["value"][0]["value"]["unknowns"][6]
                .as_str()
                .unwrap();
        let expected = unknown.strip_prefix("absent: file unavailable: ").unwrap();
        assert_eq!(failure.class, "FileNotFoundError");
        assert_eq!(
            failure.message.replace(
                &root.path().display().to_string().replace('\\', "\\\\"),
                "<tmp>"
            ),
            expected
        );
    }

    struct NoGit;
    impl GitRunner for NoGit {
        fn run(&self, _: &[String], _: u64) -> Result<GitOutput> {
            panic!("argparse refusal must not invoke Git");
        }
    }

    fn assert_argparse_repr(quotes: bool) {
        let fixture: serde_json::Value = serde_json::from_str(include_str!(
            "../../tests/fixtures/wt-path-records-repr.json"
        ))
        .unwrap();
        for record in fixture["records"].as_array().unwrap() {
            let value = record["value"].as_str().unwrap();
            if value.contains('\'') != quotes {
                continue;
            }
            let output = main(
                &[value.into()],
                &Context {
                    git: &NoGit,
                    observed_at: "unused",
                },
            );
            assert_eq!(
                output.exit,
                record["exit"].as_i64().unwrap() as i32,
                "{value:?}"
            );
            assert_eq!(
                output.stdout,
                record["stdout"].as_str().unwrap(),
                "{value:?}"
            );
            assert_eq!(
                output.stderr,
                record["stderr"].as_str().unwrap(),
                "{value:?}"
            );
        }
    }

    #[test]
    fn argparse_repr_paths_match_pinned_python() {
        assert_argparse_repr(false);
    }

    #[test]
    fn argparse_repr_quotes_match_pinned_python() {
        assert_argparse_repr(true);
    }
}
