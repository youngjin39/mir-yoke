//! Relation vocabulary and locator rules shared by the two YAML readers.
use std::collections::BTreeMap;

pub const PURPOSES: [&str; 4] = ["implementation", "verification", "impact", "dependencies"];

pub fn has_control_characters(v: &str) -> bool {
    v.chars()
        .any(|c| matches!(c as u32, 0..=31 | 127..=159 | 0x2028 | 0x2029))
}

pub fn endpoint_path(value: &str, force_file: bool) -> Option<&str> {
    let path = value.split("::").next().unwrap_or_default();
    (force_file || path.contains('/') || path.starts_with('.')).then_some(path)
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
        path.split('/')
            .filter(|p| !p.is_empty() && *p != ".")
            .collect::<Vec<_>>()
            .join("/"),
        suffix.map_or(String::new(), |s| format!("::{s}"))
    )
}

pub fn allowed(p: &str, relation: &str, reverse: bool) -> bool {
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
pub fn file_relation(r: &str) -> bool {
    matches!(r, "implemented_in" | "verified_by")
}
pub fn unique<T: PartialEq>(items: Vec<T>) -> Vec<T> {
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
