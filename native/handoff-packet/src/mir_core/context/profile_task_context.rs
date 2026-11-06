//! Read-only profile pointer selection; never loads referenced file bodies.
#![forbid(unsafe_code)]
use serde_json::{Value, json};
use std::{
    collections::BTreeSet,
    fs, io,
    path::{Path, PathBuf},
    process::Command,
};
use toml::Value as TomlValue;
const FIELDS: [(&str, &str); 5] = [
    ("architecture", "architecture_refs"),
    ("configuration", "configuration_paths"),
    ("verification", "verification_paths"),
    ("workflow", "workflow_refs"),
    ("exception", "exception_refs"),
];
const CODE_TERMS: &str = "bug code implementation script source src tool tools";
const CONFIG_TERMS: &str = "config configuration json profile settings toml yaml";
const EXCEPTION_TERMS: &str = "exception production protected release risk runtime secret";
const GROUPS: [(&str, &str); 6] = [
    ("code", CODE_TERMS),
    ("documentation", "adr design doc docs readme"),
    ("configuration", CONFIG_TERMS),
    ("verification", "test tests tdd validation verify"),
    ("workflow", "dispatch hook merge process workflow"),
    ("exception", EXCEPTION_TERMS),
];
use crate::executor_brief_render::python_value_repr;
use crate::executor_execute::repr;
use crate::executor_verifier::{Error, Result, matches};
/// JSON comparison data plus ordered TOML safety tables; JSON maps stay sorted.
#[derive(Debug, Default)]
pub struct ProfileTaskContext {
    pub(crate) value: Value,
    pub(crate) preserve: toml::Table,
    pub(crate) boundaries: toml::Table,
    pub(crate) gates: toml::Table,
}
impl ProfileTaskContext {
    pub fn to_value(&self) -> Value {
        self.value.clone()
    }
}
/// Python str() for a TOML value; recursive containers use Python repr().
pub(crate) fn ordered_python_str(value: &toml::Value) -> String {
    match value {
        TomlValue::String(text) => text.clone(),
        _ => ordered_python_repr(value),
    }
}
fn ordered_python_repr(value: &TomlValue) -> String {
    match value {
        TomlValue::Array(items) => {
            let items = items.iter().map(ordered_python_repr).collect::<Vec<_>>();
            format!("[{}]", items.join(", "))
        }
        TomlValue::Table(fields) => {
            let entries = fields
                .iter()
                .map(|(key, value)| format!("{}: {}", repr(key), ordered_python_repr(value)))
                .collect::<Vec<_>>();
            format!("{{{}}}", entries.join(", "))
        }
        TomlValue::String(text) => repr(text),
        TomlValue::Integer(number) => number.to_string(),
        // Python spells these nan, inf and -inf; Rust spells NaN.
        TomlValue::Float(number) if number.is_nan() => "nan".into(),
        TomlValue::Float(number) if !number.is_finite() => number.to_string(),
        TomlValue::Float(number) => python_value_repr(&json!(number)),
        TomlValue::Boolean(flag) => if *flag { "True" } else { "False" }.into(),
        // Frozen records do not cover datetime str/repr parity.
        TomlValue::Datetime(date) => date.to_string(),
    }
}
pub fn string_list(v: &Value) -> Vec<String> {
    v.as_array()
        .into_iter()
        .flatten()
        .filter_map(Value::as_str)
        .filter(|s| !s.trim().is_empty())
        .map(str::to_owned)
        .collect()
}
pub fn normalise_repo_path(value: &str) -> Option<String> {
    let candidate = value.trim().replace('\\', "/");
    let mut s = candidate.as_str();
    while let Some(rest) = s.strip_prefix("./") {
        s = rest;
    }
    let invalid = s.is_empty() || s.starts_with('/') || s.split('/').any(|p| p == "..");
    (!invalid).then(|| s.to_owned())
}
pub fn path_matches(scope: &str, target: &str) -> Result<bool> {
    let (Some(scope), Some(target)) = (normalise_repo_path(scope), normalise_repo_path(target))
    else {
        return Ok(false);
    };
    if scope.contains(['*', '?', '[']) {
        #[cfg(windows)]
        let (scope, target) = (scope.to_lowercase(), target.to_lowercase());
        if matches(&scope, &target)? {
            return Ok(true);
        }
        let prefix = scope.split('*').next().unwrap_or("").trim_end_matches('/');
        return Ok(
            !prefix.is_empty() && (target == prefix || target.starts_with(&format!("{prefix}/")))
        );
    }
    let (s, t) = (scope.trim_end_matches('/'), target.trim_end_matches('/'));
    Ok(t == s || t.starts_with(&format!("{s}/")) || s.starts_with(&format!("{t}/")))
}
pub fn query_terms(query: &str) -> Result<BTreeSet<String>> {
    // Reuse Python's pinned Unicode word membership, excluding underscore.
    let folded = crate::python_text::casefold(query);
    let matches = crate::captures(r"[^\W_]+", &folded, false).map_err(Error::Pattern)?;
    Ok(matches
        .iter()
        .map(|m| folded[m.start..m.end].to_owned())
        .filter(|s| s.chars().count() > 1)
        .collect())
}
pub fn query_matches_ref(terms: &BTreeSet<String>, kind: &str, path: &str) -> bool {
    let haystack = crate::python_text::casefold(&format!("{kind} {path}"));
    terms
        .iter()
        .any(|s| s.chars().count() >= 3 && haystack.contains(s))
}
// Path.glob uses metadata only; recursive '**' does not traverse directory symlinks.
fn glob(root: &Path, parts: &[&str], out: &mut Vec<PathBuf>) -> Result<()> {
    let Some((part, rest)) = parts.split_first() else {
        out.push(root.into());
        return Ok(());
    };
    if !part.contains(['*', '?', '[']) {
        let next = root.join(part);
        if next.exists() {
            glob(&next, rest, out)?;
        }
        return Ok(());
    }
    if *part == "**" {
        glob(root, rest, out)?;
    }
    let Ok(entries) = fs::read_dir(root) else {
        return Ok(());
    };
    for entry in entries {
        let entry = entry?;
        if *part == "**" {
            if entry.file_type()?.is_dir() {
                glob(&entry.path(), parts, out)?;
            }
            continue;
        }
        let name = entry.file_name();
        let name = name
            .to_str()
            .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidData, "non-UTF-8 profile path"))?;
        #[cfg(windows)]
        let (part_lower, name_lower) = (part.to_lowercase(), name.to_lowercase());
        #[cfg(windows)]
        let (part, name) = (part_lower.as_str(), name_lower.as_str());
        if matches(part, name)? && (rest.is_empty() || entry.path().is_dir()) {
            glob(&entry.path(), rest, out)?;
        }
    }
    Ok(())
}
pub fn reference_state(root: &Path, path: &str) -> Result<&'static str> {
    let mut candidates = Vec::new();
    if path.contains(['*', '?', '[']) {
        let parts = path
            .split('/')
            .filter(|s| !s.is_empty() && *s != ".")
            .collect::<Vec<_>>();
        if glob(root, &parts, &mut candidates).is_err() {
            return Ok("unsafe");
        }
    } else {
        let p = root.join(path);
        if p.exists() {
            candidates.push(p);
        }
    }
    if candidates.is_empty() {
        return Ok("missing");
    }
    for p in &candidates {
        match p.canonicalize() {
            Ok(p) if p.starts_with(root) => (),
            _ => return Ok("unsafe"),
        }
    }
    Ok(if candidates.len() == 1 && candidates[0].is_file() {
        "file"
    } else {
        "container"
    })
}
pub fn git_output(root: &Path, args: &[&str]) -> Result<(i32, String)> {
    let p = Command::new("git").args(args).current_dir(root).output()?;
    // subprocess text=True decodes both streams and uses universal newlines.
    let stdout = String::from_utf8(p.stdout)?;
    let _stderr = String::from_utf8(p.stderr)?;
    #[cfg(unix)]
    let code = {
        use std::os::unix::process::ExitStatusExt;
        p.status
            .code()
            .unwrap_or_else(|| -p.status.signal().unwrap_or(1))
    };
    #[cfg(windows)]
    let code = p.status.code().unwrap_or(-1);
    let text = stdout.replace("\r\n", "\n").replace('\r', "\n");
    Ok((code, text.trim().into()))
}
pub fn git_paths(root: &Path, args: &[&str]) -> Result<Vec<String>> {
    let p = Command::new("git").args(args).current_dir(root).output()?;
    if !p.status.success() {
        return Ok(Vec::new());
    }
    // Reject Python surrogateescape paths: JSON/Rust cannot preserve those code points.
    p.stdout
        .split(|b| *b == 0)
        .filter(|s| !s.is_empty())
        .map(|s| Ok(String::from_utf8(s.to_vec())?))
        .collect()
}
pub fn changed_paths(root: &Path, base: &str) -> Result<Vec<String>> {
    let range = format!("{base}..HEAD");
    let mut changed = BTreeSet::new();
    for args in [
        vec!["diff", "--name-only", "-z", &range],
        vec!["diff", "--name-only", "-z"],
        vec!["diff", "--cached", "--name-only", "-z"],
        vec!["ls-files", "--others", "--exclude-standard", "-z"],
    ] {
        changed.extend(git_paths(root, &args)?);
    }
    Ok(changed.into_iter().collect())
}
pub fn freshness(root: &Path, base: &str, selected: &[&str]) -> Result<Value> {
    let mut result = json!({
        "state": "unverified",
        "base_commit": if base.is_empty() { "unverified" } else { base },
        "head": "", "changed_selected": [], "changed_selected_count": 0,
        "reason": "profile baseline is unverified"
    });
    let (code, head) = git_output(root, &["rev-parse", "HEAD"])?;
    if code != 0 {
        result["reason"] = json!("repository HEAD is unavailable");
        return Ok(result);
    }
    result["head"] = json!(head);
    if crate::captures(r"^[0-9a-f]{40}$", base, false)
        .map_err(Error::Pattern)?
        .is_empty()
    {
        return Ok(result);
    }
    let (state, reason) =
        if git_output(root, &["cat-file", "-e", &format!("{base}^{{commit}}")])?.0 != 0 {
            ("uncertain", "profile baseline commit is unavailable")
        } else if git_output(root, &["merge-base", "--is-ancestor", base, "HEAD"])?.0 != 0 {
            ("uncertain", "profile baseline is not an ancestor of HEAD")
        } else {
            let mut changed = Vec::new();
            for path in changed_paths(root, base)? {
                for scope in selected {
                    if path_matches(scope, &path)? {
                        changed.push(path);
                        break;
                    }
                }
            }
            result["changed_selected"] = json!(changed.iter().take(50).collect::<Vec<_>>());
            result["changed_selected_count"] = json!(changed.len());
            if !changed.is_empty() {
                let reason = "task-selected paths changed since the profile baseline";
                ("review_required", reason)
            } else if head == base {
                ("current", "selected paths match the profile baseline")
            } else {
                let reason = "HEAD advanced without changes to task-selected paths";
                ("current_for_selection", reason)
            }
        };
    result["state"] = json!(state);
    result["reason"] = json!(reason);
    Ok(result)
}
pub fn empty_invalid_context(query: &str, risk: &str, warning: &str) -> ProfileTaskContext {
    ProfileTaskContext {
        value: json!({
            "repository": {"slug": "unknown", "repository_type": "unknown",
                "purpose": "", "technology_stack": []},
            "task": {"query": query, "risk": risk, "target_paths": []},
            "safety": {"protected_paths": [], "generated_paths": [],
                "preserve": {}, "boundaries": {}, "gates": {}},
            "selected_refs": [],
            "freshness": {"state": "uncertain", "base_commit": "unverified", "head": "",
                "changed_selected": [], "reason": warning},
            "needs_investigation": true, "warnings": [warning]
        }),
        ..ProfileTaskContext::default()
    }
}
pub(crate) fn python_str(v: &Value) -> String {
    v.as_str()
        .map(str::to_owned)
        .unwrap_or_else(|| python_value_repr(v))
}
fn section(v: &Value, key: &str) -> Value {
    v.get(key)
        .filter(|v| v.is_object())
        .cloned()
        .unwrap_or(json!({}))
}
fn add<'a>(selected: &mut Vec<Value>, kind: &str, values: impl IntoIterator<Item = &'a String>) {
    for value in values {
        let item = json!({"kind": kind, "path": value});
        if !selected.contains(&item) {
            selected.push(item);
        }
    }
}
fn matching(scopes: &[String], target: &str) -> Result<Vec<String>> {
    let mut out = Vec::new();
    for scope in scopes {
        if path_matches(scope, target)? {
            out.push(scope.clone());
        }
    }
    Ok(out)
}
pub fn build_profile_task_context(
    project_root: &Path,
    query: &str,
    target_paths: &[&str],
    risk: &str,
) -> Result<ProfileTaskContext> {
    if !["low", "normal", "high"].contains(&risk) {
        let message = format!("unsupported task risk: {}", repr(risk));
        return Err(Error::Invalid(message));
    }
    let root = project_root.canonicalize()?;
    let path = root.join(".mir/repo-profile.toml");
    if !path.is_file() {
        return Ok(ProfileTaskContext::default());
    }
    let invalid = |message| {
        empty_invalid_context(
            query,
            risk,
            &format!("repository profile is unreadable: {message}"),
        )
    };
    let text = match fs::read_to_string(&path) {
        Ok(s) => s,
        Err(e) => return Ok(invalid(e.to_string())),
    };
    let profile = match toml::from_str::<TomlValue>(&text) {
        Ok(p) => p,
        Err(e) => return Ok(invalid(crate::mir_core::tomllib::tomllib_error(&e, &text))),
    };
    let ordered_section = |key: &str| {
        profile
            .get(key)
            .and_then(TomlValue::as_table)
            .cloned()
            .unwrap_or_default()
    };
    let [preserve_order, boundary_order, gate_order] =
        ["preserve", "boundaries", "gates"].map(ordered_section);
    let profile = serde_json::to_value(&profile)
        .map_err(crate::Error::from)
        .map_err(Error::Pattern)?;
    let repo = section(&profile, "repo");
    let paths = section(&profile, "paths");
    let preserve = section(&profile, "preserve");
    let boundaries = section(&profile, "boundaries");
    let (mut warnings, mut targets) = (Vec::new(), Vec::new());
    for target in target_paths {
        match normalise_repo_path(target) {
            Some(path) => targets.push(path),
            None => warnings.push(format!("ignored non-repository target path: {target}")),
        }
    }
    let mut preserved = string_list(&preserve["agent_memory_paths"]);
    preserved.extend(string_list(&preserve["extra_docs"]));
    let list = string_list;
    let safety_scopes = [
        ("protected path", string_list(&paths["protected_paths"])),
        ("generated path", string_list(&paths["generated_paths"])),
        ("preserve path", preserved),
        ("live runtime boundary", list(&boundaries["live_runtime"])),
        ("secret path", string_list(&boundaries["secrets"])),
    ];
    for target in &targets {
        for (label, scopes) in &safety_scopes {
            if !matching(scopes, target)?.is_empty() {
                warnings.push(format!("target intersects {label}: {target}"));
            }
        }
    }
    let mut groups = Vec::new();
    for (kind, field) in FIELDS {
        let mut refs = Vec::new();
        for candidate in string_list(&paths[field]) {
            match normalise_repo_path(&candidate) {
                Some(path) => refs.push(path),
                None => warnings.push(format!(
                    "ignored invalid profile reference: {field}={candidate}"
                )),
            }
        }
        groups.push((kind, refs));
    }
    let scopes = |key| {
        string_list(&paths[key])
            .iter()
            .filter_map(|s| normalise_repo_path(s))
            .collect::<Vec<_>>()
    };
    let code = scopes("code_paths");
    let docs = scopes("non_code_paths");
    let terms = query_terms(query)?;
    let signalled = GROUPS
        .iter()
        .filter(|(_, words)| words.split_whitespace().any(|s| terms.contains(s)))
        .map(|(kind, _)| *kind)
        .collect::<BTreeSet<_>>();
    let mut selected = Vec::new();
    add(&mut selected, "architecture", &groups[0].1);
    for (kind, refs) in &groups {
        let matching = refs
            .iter()
            .filter(|path| query_matches_ref(&terms, kind, path));
        add(&mut selected, kind, matching);
    }
    let mut matched_target = false;
    for target in &targets {
        for (kind, scopes, extras) in [
            ("code_scope", &code, &[2][..]),
            ("non_code_scope", &docs, &[3][..]),
            ("configuration", &groups[1].1, &[3, 2][..]),
            ("verification", &groups[2].1, &[][..]),
            ("workflow", &groups[3].1, &[][..]),
            ("exception", &groups[4].1, &[][..]),
        ] {
            let matched = matching(scopes, target)?;
            if !matched.is_empty() {
                matched_target = true;
                add(&mut selected, kind, &matched);
                for i in extras {
                    add(&mut selected, groups[*i].0, &groups[*i].1);
                }
            }
        }
    }
    for (signal, kind, scopes, extras) in [
        ("code", "code_scope", &code, &[2][..]),
        ("documentation", "non_code_scope", &docs, &[3][..]),
        ("configuration", "configuration", &groups[1].1, &[][..]),
        ("verification", "verification", &groups[2].1, &[][..]),
        ("workflow", "workflow", &groups[3].1, &[][..]),
        ("exception", "exception", &groups[4].1, &[][..]),
        ("configuration", "workflow", &groups[3].1, &[][..]),
    ] {
        if signalled.contains(signal) {
            add(&mut selected, kind, scopes);
            for i in extras {
                add(&mut selected, groups[*i].0, &groups[*i].1);
            }
        }
    }
    if risk == "high" {
        for i in [3, 4, 2] {
            add(&mut selected, groups[i].0, &groups[i].1);
        }
    }
    let (mut exact, mut containers, mut safe) = (Vec::new(), Vec::new(), Vec::new());
    for item in selected {
        let p = item["path"].as_str().unwrap_or("");
        let kind = item["kind"].as_str().unwrap_or("");
        let path_kind = if FIELDS.iter().any(|(k, _)| *k == kind) {
            "reference"
        } else {
            "scope"
        };
        match reference_state(&root, p)? {
            "unsafe" => {
                warnings.push(format!("ignored unsafe profile {path_kind}: {p}"));
                continue;
            }
            "missing" => warnings.push(format!("selected profile {path_kind} is missing: {p}")),
            "file" => exact.push(p.to_owned()),
            "container" => containers.push(p.to_owned()),
            _ => (),
        }
        safe.push(item);
    }
    exact.extend(targets.clone());
    let base = repo
        .get("profile_base_commit")
        .map(python_str)
        .unwrap_or("unverified".into());
    let base = base.trim().to_lowercase();
    let selected_paths = exact.iter().map(String::as_str).collect::<Vec<_>>();
    let mut fresh = freshness(&root, &base, &selected_paths)?;
    if targets.is_empty()
        && !containers.is_empty()
        && ["current", "current_for_selection"].contains(&fresh["state"].as_str().unwrap_or(""))
    {
        fresh["state"] = json!("unverified_for_selection");
        fresh["reason"] = json!(concat!(
            "query selected directory lookup roots without a concrete target; ",
            "inspect only the relevant descendant"
        ));
    }
    let confident = matched_target || !signalled.is_empty() || risk == "high";
    let state = fresh["state"].as_str().unwrap_or("");
    let uncertain = matches!(
        state,
        "unverified" | "unverified_for_selection" | "uncertain" | "review_required"
    );
    let investigate = !confident || uncertain || !warnings.is_empty();
    let attribute = |key, default| python_str(repo.get(key).unwrap_or(&json!(default)));
    let repository = json!({
        "slug": attribute("slug", "unknown"),
        "repository_type": attribute("repository_type", "unknown"),
        "purpose": attribute("purpose", ""),
        "profile_verified_at": attribute("profile_verified_at", ""),
        "technology_stack": string_list(&repo["technology_stack"])
    });
    Ok(ProfileTaskContext {
        value: json!({
            "repository": repository,
            "task": {"query": query, "risk": risk, "target_paths": targets},
            "safety": {
                "protected_paths": string_list(&paths["protected_paths"]),
                "generated_paths": string_list(&paths["generated_paths"]),
                "preserve": preserve, "boundaries": boundaries, "gates": section(&profile, "gates")
            },
            "selected_refs": safe, "freshness": fresh,
            "needs_investigation": investigate, "warnings": warnings
        }),
        preserve: preserve_order,
        boundaries: boundary_order,
        gates: gate_order,
    })
}
