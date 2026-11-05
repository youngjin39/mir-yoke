//! Mapping validation with guarded reads. Unsupported symbol grammars forward.
use crate::{
    digest::sha256,
    guard::Guard,
    handoff::{CONTRACT, pointer as ptr},
};
use serde_json::{Value, json};
use std::collections::HashSet;

type Result<T> = std::result::Result<T, &'static str>;

#[derive(Default)]
pub struct Checker {
    pub errors: Vec<Value>,
    pub warnings: Vec<Value>,
    pub checked_refs: HashSet<String>,
    pub line_refs: HashSet<String>,
}

// Keep Python's unbounded integers exact by forwarding out-of-range versions.
#[derive(Eq, PartialEq, Ord, PartialOrd)]
struct Version(u64, u64, u64, Vec<(u8, u64, String)>);
fn version(raw: &Value) -> Result<Option<Version>> {
    let Some(text) = raw.as_str() else {
        return Ok(None);
    };
    if !text.is_ascii() {
        return Ok(None);
    }
    let (main, build) = text
        .split_once('+')
        .map_or((text, None), |(a, b)| (a, Some(b)));
    let identifier =
        |s: &str| !s.is_empty() && s.bytes().all(|b| b.is_ascii_alphanumeric() || b == b'-');
    if build.is_some_and(|b| !b.split('.').all(identifier)) {
        return Ok(None);
    }
    let (core, pre) = main
        .split_once('-')
        .map_or((main, None), |(a, b)| (a, Some(b)));
    let parts: Vec<_> = core.split('.').collect();
    if parts.len() != 3
        || parts.iter().any(|p| {
            p.is_empty()
                || !p.bytes().all(|b| b.is_ascii_digit())
                || (p.len() > 1 && p.starts_with('0'))
        })
    {
        return Ok(None);
    }
    let mut nums = Vec::new();
    for p in parts {
        nums.push(p.parse().map_err(|_| "FORWARD")?);
    }
    let mut prerelease = Vec::new();
    if let Some(pre) = pre {
        for p in pre.split('.') {
            if !identifier(p) {
                return Ok(None);
            }
            if p.bytes().all(|b| b.is_ascii_digit()) {
                if p.len() > 1 && p.starts_with('0') {
                    return Ok(None);
                }
                prerelease.push((0, p.parse().map_err(|_| "FORWARD")?, String::new()));
            } else {
                prerelease.push((1, 0, p.into()));
            }
        }
    } else {
        prerelease.push((2, 0, String::new()));
    }
    Ok(Some(Version(nums[0], nums[1], nums[2], prerelease)))
}

impl Checker {
    pub fn new() -> Self {
        Self::default()
    }
    fn error(&mut self, at: &str, message: &str) {
        self.errors
            .push(json!({"pointer":at,"message":message,"code":"E_VALIDATION"}));
    }
    fn warn(&mut self, at: &str, message: &str) {
        self.warnings
            .push(json!({"pointer":at,"message":message,"code":"W_VALIDATION"}));
    }
    fn object(&mut self, value: &Value, at: &str) -> Value {
        if !value.is_object() {
            self.error(at, "expected an object");
            return json!({});
        }
        value.clone()
    }
    fn array(&mut self, value: &Value, at: &str) -> Vec<Value> {
        match value.as_array() {
            Some(v) => v.clone(),
            None => {
                self.error(at, "expected a list");
                Vec::new()
            }
        }
    }
    fn text(&mut self, value: &Value, at: &str, message: &str) -> bool {
        // Python str.strip includes C0 separators absent from Rust trim.
        if value.as_str().is_none_or(|s| {
            s.trim_matches(|c: char| c.is_whitespace() || ('\u{1c}'..='\u{1f}').contains(&c))
                .is_empty()
        }) {
            self.error(at, message);
            false
        } else {
            true
        }
    }
    pub fn ref_check(
        &mut self,
        value: &Value,
        at: &str,
        covered: bool,
        io: &mut Guard,
    ) -> Result<()> {
        self.checked_refs.insert(at.into());
        if !self.text(value, at, "needs a ref") {
            return Ok(());
        }
        let value = value.as_str().unwrap_or("");
        let path = value.split('#').next().unwrap_or("");
        // Unicode decimal suffixes use Python's regex/int semantics.
        if !path.is_ascii()
            && path
                .rsplit_once(':')
                .is_some_and(|(_, n)| n.chars().all(char::is_numeric))
        {
            return Err("FORWARD");
        }
        let line = path
            .rsplit_once(':')
            .filter(|(_, n)| !n.is_empty() && n.bytes().all(|b| b.is_ascii_digit()));
        if line.is_some() {
            self.line_refs.insert(at.into());
        }
        let raw = line.map_or(path, |(p, _)| p);
        let drive = raw.as_bytes().get(1) == Some(&b':') && raw.as_bytes()[0].is_ascii_alphabetic();
        if raw.starts_with('/')
            || raw.starts_with("\\\\")
            || (drive
                && raw
                    .as_bytes()
                    .get(2)
                    .is_some_and(|b| *b == b'/' || *b == b'\\'))
        {
            self.error(at, "absolute ref is not allowed");
            return Ok(());
        }
        if raw.is_empty() || raw.contains('\\') || drive {
            self.error(at, "ref must be repo-relative");
            return Ok(());
        }
        if raw.split('/').any(|p| p == "..") {
            self.error(
                at,
                "ref escapes repository: parent traversal is not allowed",
            );
            return Ok(());
        }
        let target = io.path(raw, true)?;
        if !io.exists(raw)? {
            self.error(at, "ref path does not exist");
            return Ok(());
        }
        let suffix = target
            .extension()
            .and_then(|s| s.to_str())
            .unwrap_or("")
            .to_ascii_lowercase();
        if let Some((_, name)) = value.split_once('#') {
            // shortcut: non-JSON grammars remain with Python until a parity-tested parser exists.
            if suffix != "json" {
                return Err("FORWARD");
            }
            let text = read_text(io, raw)?;
            if !json_symbol(&text, name)? {
                self.error(
                    at,
                    &format!("symbol anchor not found (check name not found): {name}"),
                );
            }
        }
        if covered {
            let text = read_text(io, raw)?;
            if let Some((_, number)) = line {
                let number: usize = number.parse().map_err(|_| "FORWARD")?;
                if number == 0 {
                    self.error(at, "check line must be positive");
                } else if number > python_lines(&text) {
                    self.error(at, "check line exceeds file line count");
                }
            }
            if matches!(suffix.as_str(), "md" | "txt" | "rst") {
                self.warn(
                    at,
                    "covered needs a repeatable check; a document is not one",
                );
            }
        }
        Ok(())
    }
    fn refs(&mut self, value: &Value, at: &str, io: &mut Guard) -> Result<()> {
        for (i, v) in self.array(value, at).iter().enumerate() {
            let loc = ptr(at, i);
            if v.is_object() {
                self.ref_check(&v["ref"], &ptr(&loc, "ref"), false, io)?;
            } else {
                self.ref_check(v, &loc, false, io)?;
            }
        }
        Ok(())
    }
    fn common_relation(&mut self, relation: &Value, at: &str, contract: &Value, required: bool) {
        let rule = contract["relations"]
            .as_array()
            .into_iter()
            .flatten()
            .find(|r| r["id"] == relation["common"]);
        let Some(rule) = rule else {
            self.error(&ptr(at, "common"), "unknown relation");
            return;
        };
        if !required {
            return;
        }
        for side in ["from", "to"] {
            let value = &relation[side];
            let loc = ptr(at, side);
            let values = if value == "*" {
                vec![json!("*")]
            } else {
                self.array(value, &loc)
            };
            if values.is_empty() {
                self.error(&loc, "needs non-empty endpoints");
            }
            for (j, v) in values.iter().enumerate() {
                let known = contract["concepts"]
                    .as_array()
                    .into_iter()
                    .flatten()
                    .any(|c| c["id"] == *v);
                let allowed = array_ref(&rule[side]);
                if !v.is_string()
                    || (!known && value != "*")
                    || (!allowed.contains(&json!("*")) && !allowed.contains(v))
                {
                    self.error(&ptr(&loc, j), "endpoint not allowed");
                }
            }
        }
    }
    pub fn mapping(&mut self, raw: &Value, io: &mut Guard) -> Result<Value> {
        let contract: Value = serde_json::from_slice(CONTRACT).map_err(|_| "E_FORMAT")?;
        let m = self.object(raw, "");
        for key in array_ref(&contract["mapping"]["required_keys"]) {
            let key = key.as_str().unwrap_or("");
            if m.get(key).is_none() {
                self.error(&ptr("", key), "missing required key");
            }
        }
        if m["schema"] != "mir-semantic-mapping/v1" {
            self.error("/schema", "invalid mapping schema");
        }
        let d = self.object(&m["contract"], "/contract");
        if d["id"] != contract["contract_id"] {
            self.error("/contract/id", "contract id mismatch");
        }
        let validated = version(&d["version"])?;
        if validated.is_none() {
            self.error("/contract/version", "invalid semver");
        }
        let range = d["version_range"]
            .as_str()
            .and_then(|r| r.strip_prefix(">="))
            .and_then(|r| r.split_once(" <"));
        let bounds = if let Some((a, b)) = range {
            if a.contains(['-', '+']) || b.contains(['-', '+']) {
                None
            } else {
                version(&json!(a))?.zip(version(&json!(b))?)
            }
        } else {
            None
        };
        let current = version(&contract["version"])?.ok_or("E_FORMAT")?;
        match bounds {
            Some((low, high)) if low < high => {
                if !(low <= current && current < high) {
                    self.error(
                        "/contract/version_range",
                        "version mismatch (E10): contract outside range",
                    );
                } else if let Some(v) = &validated {
                    if !(low <= *v && *v < high) {
                        self.error(
                            "/contract/version",
                            "validated version outside its range (E10)",
                        );
                    } else if *v > current {
                        self.error(
                            "/contract/version",
                            "validated version is newer than the loaded contract (E10)",
                        );
                    } else if *v < current {
                        self.warn(
                            "/contract/version",
                            "validated against an older contract; re-validate (E10)",
                        );
                    }
                }
            }
            _ => self.error(
                "/contract/version_range",
                "invalid version_range; use >=A.B.C <X.Y.Z",
            ),
        }
        if let Some(hash) = d.get("sha256")
            && *hash != json!(sha256(CONTRACT))
        {
            self.warn(
                "/contract/sha256",
                "contract sha256 differs from loaded file",
            );
        }
        if !io.exists(".mir/repo-profile.toml")? {
            self.error("/namespace", "missing Profile: .mir/repo-profile.toml");
        } else {
            let profile = read_text(io, ".mir/repo-profile.toml")?;
            if !profile.is_ascii() {
                return Err("FORWARD");
            }
            let slug = profile_slug(&profile);
            match slug {
                None => self.error("/namespace", "Profile needs a slug = \"...\" key"),
                Some(s) if m["namespace"] != s => self.error(
                    "/namespace",
                    "namespace mismatch with repository Profile slug",
                ),
                _ => {}
            }
        }
        self.refs(&m["canonical_index"], "/canonical_index", io)?;
        let concepts = self.object(&m["concepts"], "/concepts");
        for concept in array_ref(&contract["concepts"]) {
            let name = concept["id"].as_str().unwrap_or("");
            let at = ptr("/concepts", name);
            let Some(raw) = concepts.get(name) else {
                self.error(&at, &format!("missing concept: {name}"));
                continue;
            };
            let e = self.object(raw, &at);
            match e["status"].as_str() {
                Some("mapped") => {
                    let local = self.array(&e["local"], &ptr(&at, "local"));
                    if local.is_empty() {
                        self.error(&ptr(&at, "local"), "mapped needs a non-empty local list");
                    }
                    for (i, raw) in local.iter().enumerate() {
                        let at = ptr(&ptr(&at, "local"), i);
                        let item = self.object(raw, &at);
                        self.text(
                            &item["name"],
                            &ptr(&at, "name"),
                            "expected a non-empty string",
                        );
                        self.ref_check(&item["ref"], &ptr(&at, "ref"), false, io)?;
                    }
                }
                Some("absent" | "not_applicable") => {
                    self.text(
                        &e["reason"],
                        &ptr(&at, "reason"),
                        "needs a non-empty reason",
                    );
                }
                _ => self.error(&ptr(&at, "status"), "invalid concept status"),
            }
        }
        for (i, raw) in self
            .array(&m["vocabularies"], "/vocabularies")
            .iter()
            .enumerate()
        {
            let at = ptr("/vocabularies", i);
            let v = self.object(raw, &at);
            self.text(&v["name"], &ptr(&at, "name"), "expected a non-empty string");
            self.ref_check(&v["ref"], &ptr(&at, "ref"), false, io)?;
            let words = self.object(&v["values"], &ptr(&at, "values"));
            for (word, raw) in words.as_object().into_iter().flatten() {
                let at = ptr(&ptr(&at, "values"), word);
                let values = self.object(raw, &at);
                if let Some(local) = values.get("local_only") {
                    self.text(
                        local,
                        &ptr(&at, "local_only"),
                        "expected a non-empty string",
                    );
                    if values.as_object().map_or(0, |m| m.len()) != 1 {
                        self.error(&at, "local_only cannot be combined with axes");
                    }
                    continue;
                }
                if values.as_object().is_none_or(|m| m.is_empty()) {
                    self.error(&at, "value needs a non-empty axis map");
                }
                for (axis, value) in values.as_object().into_iter().flatten() {
                    if let Some(axis_spec) = contract["axes"].get(axis) {
                        if value
                            .as_str()
                            .is_none_or(|s| axis_spec["values"].get(s).is_none())
                        {
                            self.error(&ptr(&at, axis), "unknown axis value");
                        }
                    } else {
                        self.error(&ptr(&at, axis), "unknown axis");
                    }
                }
            }
        }
        let required =
            validated.is_some_and(|v| v >= Version(1, 1, 0, vec![(2, 0, String::new())]));
        for (i, raw) in self.array(&m["relations"], "/relations").iter().enumerate() {
            let at = ptr("/relations", i);
            let r = self.object(raw, &at);
            self.text(
                &r["local"],
                &ptr(&at, "local"),
                "needs a non-empty local relation",
            );
            match (r.get("common"), r.get("local_only")) {
                (Some(_), None) => self.common_relation(&r, &at, &contract, required),
                (None, Some(v)) => {
                    self.text(v, &ptr(&at, "local_only"), "expected a non-empty string");
                }
                _ => self.error(&at, "relation needs either common or local_only"),
            }
            if let Some(v) = r.get("ref") {
                self.ref_check(v, &ptr(&at, "ref"), false, io)?;
            }
        }
        let domain = self.object(&m["domain"], "/domain");
        for key in ["concepts", "relations", "invariants"] {
            let at = ptr("/domain", key);
            for (i, raw) in self.array(&domain[key], &at).iter().enumerate() {
                let at = ptr(&at, i);
                let e = self.object(raw, &at);
                self.ref_check(&e["ref"], &ptr(&at, "ref"), false, io)?;
                if key == "invariants"
                    && let Some(v) = e.get("check")
                {
                    self.ref_check(v, &ptr(&at, "check"), true, io)?;
                }
                if key == "relations" && e.get("common").is_some() {
                    self.common_relation(&e, &at, &contract, required);
                }
            }
        }
        let qs = self.array(&m["questions"], "/questions");
        if qs.is_empty() {
            self.error("/questions", "at least one question is required");
        } else if qs.len() < 3 {
            self.warn("/questions", "fewer than three domain questions");
        }
        for (i, raw) in qs.iter().enumerate() {
            let at = ptr("/questions", i);
            let q = self.object(raw, &at);
            for key in ["id", "question"] {
                self.text(&q[key], &ptr(&at, key), "expected a non-empty string");
            }
            self.refs(&q["evidence"], &ptr(&at, "evidence"), io)?;
        }
        for (i, raw) in self
            .array(&m["error_cases"], "/error_cases")
            .iter()
            .enumerate()
        {
            let at = ptr("/error_cases", i);
            let c = self.object(raw, &at);
            if !c["id"].is_string()
                || !contract["error_cases"]
                    .as_array()
                    .into_iter()
                    .flatten()
                    .any(|v| v["id"] == c["id"])
            {
                self.error(&ptr(&at, "id"), "unknown error case");
            }
            if !matches!(
                c["status"].as_str(),
                Some("covered" | "planned" | "not_applicable")
            ) {
                self.error(&ptr(&at, "status"), "invalid error case status");
            }
            if c["status"] == "covered" && c.get("check").is_none() {
                self.error(&ptr(&at, "check"), "covered needs a check ref");
            } else if let Some(v) = c.get("check") {
                self.ref_check(v, &ptr(&at, "check"), c["status"] == "covered", io)?;
            }
        }
        let s = self.object(&m["knowledge_supply"], "/knowledge_supply");
        if !array_ref(&contract["mapping"]["knowledge_supply_values"]).contains(&s["memory_keeper"])
        {
            self.error(
                "/knowledge_supply/memory_keeper",
                "invalid knowledge supply value",
            );
        }
        if s["memory_keeper"] == "connected" && s.get("binding").is_none() && !required {
            self.error("/knowledge_supply/binding", "connected needs a binding ref");
        } else if let Some(v) = s.get("binding") {
            if !required {
                self.ref_check(v, "/knowledge_supply/binding", false, io)?;
            } else if !matches!(v.as_str(), Some("on_demand_stdio" | "resident_stdio")) {
                self.error("/knowledge_supply/binding", "invalid binding value");
            }
        }
        self.refs(&m["entrypoints"], "/entrypoints", io)?;
        // Parent owns shared entry iteration; preserve extension refs as well.
        for (at, entry) in crate::handoff::map_entries(&m) {
            for (at, reference) in crate::handoff::located_refs(entry, &at) {
                if !self.checked_refs.contains(&at) {
                    self.ref_check(&json!(reference), &at, false, io)?;
                }
            }
        }
        Ok(d["version"].clone())
    }
}

fn read_text(io: &mut Guard, path: &str) -> Result<String> {
    String::from_utf8(io.read(path)?)
        .map(|s| s.replace("\r\n", "\n").replace('\r', "\n"))
        .map_err(|_| "E_IO")
}
fn python_lines(text: &str) -> usize {
    if text.is_empty() {
        return 0;
    }
    let mut count = text
        .chars()
        .filter(|c| {
            matches!(
                c,
                '\n' | '\u{b}'
                    | '\u{c}'
                    | '\u{1c}'
                    | '\u{1d}'
                    | '\u{1e}'
                    | '\u{85}'
                    | '\u{2028}'
                    | '\u{2029}'
            )
        })
        .count();
    if !text.ends_with([
        '\n', '\u{b}', '\u{c}', '\u{1c}', '\u{1d}', '\u{1e}', '\u{85}', '\u{2028}', '\u{2029}',
    ]) {
        count += 1;
    }
    count
}
fn profile_slug(text: &str) -> Option<&str> {
    // re.MULTILINE \s may consume newlines before/after the declaration.
    for (start, _) in
        std::iter::once((0, "")).chain(text.match_indices('\n').map(|(i, s)| (i + 1, s)))
    {
        let tail = text[start..].trim_start_matches(python_whitespace);
        let Some(tail) = tail.strip_prefix("slug") else {
            continue;
        };
        let tail = tail.trim_start_matches(python_whitespace);
        let Some(tail) = tail.strip_prefix('=') else {
            continue;
        };
        let Some(tail) = tail.trim_start_matches(python_whitespace).strip_prefix('"') else {
            continue;
        };
        let Some(end) = tail.find('"') else {
            continue;
        };
        let slug = &tail[..end];
        if slug.is_empty() || slug.contains('\n') {
            continue;
        }
        let after = tail[end + 1..].trim_start_matches(python_whitespace);
        if after.is_empty() || after.starts_with('#') {
            return Some(slug);
        }
        // Regex may stop its whitespace at the immediate newline.
        if tail[end + 1..]
            .chars()
            .take_while(|c| python_whitespace(*c))
            .any(|c| c == '\n')
        {
            return Some(slug);
        }
    }
    None
}
fn json_symbol(text: &str, name: &str) -> Result<bool> {
    if name.is_empty() {
        return Ok(false);
    }
    let document = crate::wire::parse(text.as_bytes())?;
    if text.starts_with('\u{feff}') {
        return Ok(false);
    }
    if name.contains('/') || name.contains('~') {
        let mut value = &document;
        for part in name.strip_prefix('/').unwrap_or(name).split('/') {
            let mut chars = part.chars();
            while let Some(c) = chars.next() {
                if c == '~' && !matches!(chars.next(), Some('0' | '1')) {
                    return Ok(false);
                }
            }
            let key = part.replace("~1", "/").replace("~0", "~");
            match value {
                Value::Object(m) => {
                    let Some(v) = m.get(&key) else {
                        return Ok(false);
                    };
                    value = v;
                }
                Value::Array(a) => {
                    if key.is_empty()
                        || !key.bytes().all(|b| b.is_ascii_digit())
                        || (key.len() > 1 && key.starts_with('0'))
                    {
                        return Ok(false);
                    }
                    let Ok(i) = key.parse::<usize>() else {
                        return Ok(false);
                    };
                    let Some(v) = a.get(i) else { return Ok(false) };
                    value = v;
                }
                _ => return Ok(false),
            }
        }
        return Ok(true);
    }
    let candidate = name.rsplit('.').next().unwrap_or("");
    let mut values = vec![&document];
    while let Some(value) = values.pop() {
        match value {
            Value::Object(m) => {
                if m.contains_key(name) || m.contains_key(candidate) {
                    return Ok(true);
                }
                values.extend(m.values());
            }
            Value::Array(a) => values.extend(a),
            _ => {}
        }
    }
    Ok(false)
}

fn array_ref(value: &Value) -> &[Value] {
    value.as_array().map(Vec::as_slice).unwrap_or(&[])
}

fn python_whitespace(c: char) -> bool {
    c.is_whitespace() || ('\u{1c}'..='\u{1f}').contains(&c)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn profile_slug_matches_multiline_python_whitespace() {
        assert_eq!(
            profile_slug("# comment\n[repo]\nslug = \"sample\" # comment\n"),
            Some("sample")
        );
        assert_eq!(
            profile_slug("slug\n=\u{1c}\"sample\"\nother = 1\n"),
            Some("sample")
        );
        assert_eq!(profile_slug("slug = \"bad\" trailing\n"), None);
        assert_eq!(profile_slug("slug = \"\"\n"), None);
    }

    #[test]
    fn json_symbols_resolve_keys_and_escaped_pointers() {
        let document = r#"{"a/b": [{"~name": null}], "nested": {"symbol": false}}"#;
        assert_eq!(json_symbol(document, "/a~1b/0/~0name"), Ok(true));
        assert_eq!(json_symbol(document, "module.symbol"), Ok(true));
        assert_eq!(json_symbol(document, "/a~1b/00"), Ok(false));
        assert_eq!(json_symbol(document, "/a~2b"), Ok(false));
        assert_eq!(json_symbol("{", "symbol"), Err("E_FORMAT"));
    }

    #[test]
    fn semantic_version_order_and_overflow() {
        let ordered = [
            "1.0.0-alpha",
            "1.0.0-alpha.1",
            "1.0.0-alpha.beta",
            "1.0.0-beta",
            "1.0.0-beta.2",
            "1.0.0-beta.11",
            "1.0.0-rc.1",
            "1.0.0",
        ];
        for pair in ordered.windows(2) {
            assert!(matches!(
                (version(&json!(pair[0])), version(&json!(pair[1]))),
                (Ok(Some(low)), Ok(Some(high))) if low < high
            ));
        }
        assert!(matches!(version(&json!("1.0.0-01")), Ok(None)));
        assert!(matches!(
            version(&json!("999999999999999999999999.0.0")),
            Err("FORWARD")
        ));
    }

    #[test]
    fn covered_line_count_matches_python_splitlines() {
        assert_eq!(python_lines(""), 0);
        assert_eq!(python_lines("one\n"), 1);
        assert_eq!(python_lines("one\u{85}two\u{2028}"), 2);
        assert_eq!(python_lines("\n\n"), 2);
    }
}
