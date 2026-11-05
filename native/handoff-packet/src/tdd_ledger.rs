//! Yoke's own ledger contract. Unknown composite category names are intentional.
use serde_json::Value;
use std::{
    fs,
    path::{Path, PathBuf},
    process::Command,
};
const CATEGORIES: &[&str] = &[
    "unit",
    "integration",
    "e2e",
    "browser",
    "edge",
    "architecture",
    "availability",
    "load",
    "soak",
    "security",
    "compatibility",
    "transaction_locking",
];
pub fn implementation(path: &str) -> bool {
    [
        "src/",
        "app/",
        "apps/",
        "packages/",
        "pipelines/",
        "infra/",
        "content/",
        "lib/",
    ]
    .iter()
    .any(|r| path.starts_with(r))
        && [
            ".py", ".js", ".ts", ".jsx", ".tsx", ".rb", ".go", ".rs", ".java", ".kt", ".swift",
            ".c", ".cc", ".cpp", ".h", ".hpp", ".sql",
        ]
        .iter()
        .any(|s| path.ends_with(s))
}
fn normalize(project: &Path, raw: &str) -> String {
    let s = raw.trim().replace('\\', "/");
    let s = s.strip_prefix("./").unwrap_or(&s);
    s.strip_prefix(&format!("{}/", project.display()).replace('\\', "/"))
        .unwrap_or(s)
        .into()
}
fn matches(target: &str, path: &str) -> bool {
    let t = target.trim();
    !t.is_empty()
        && if t.ends_with('/') {
            path.starts_with(t)
        } else {
            path == t
        }
}
fn find<'a>(data: &'a Value, path: &str) -> Option<&'a Value> {
    data["changes"].as_array()?.iter().find(|c| {
        c["target"].as_str().is_some_and(|t| matches(t, path))
            || c["targets"].as_array().is_some_and(|ts| {
                ts.iter()
                    .any(|t| t.as_str().is_some_and(|t| matches(t, path)))
            })
    })
}
fn py(value: &Value) -> String {
    match value {
        Value::Null => "None".into(),
        Value::Bool(true) => "True".into(),
        Value::Bool(false) => "False".into(),
        Value::String(s) => s.clone(),
        _ => value.to_string(),
    }
}
fn repr(value: &Value) -> String {
    if let Some(s) = value.as_str() {
        format!("'{s}'")
    } else {
        py(value)
    }
}
fn validate(c: &Value, phase: &str, order: &[String]) -> Result<Vec<String>, String> {
    let prefix = if phase == "prewrite" {
        "[TddGuard BLOCK]"
    } else {
        "[PreCommitVerification BLOCK]"
    };
    let composite = c.get("targets").is_some();
    if !composite {
        for key in ["target", "bluebrick", "design_ref"] {
            if c[key].as_str().is_none_or(|s| s.trim().is_empty()) {
                return Err(format!("{prefix} Missing '{key}' for target."));
            }
        }
    }
    let Some(_cats) = c["categories"].as_object() else {
        return Err(format!(
            "{prefix} Missing 'categories' object for target {}.",
            py(&c["target"])
        ));
    };
    let keys: Vec<&str> = if composite {
        order.iter().map(String::as_str).collect()
    } else {
        CATEGORIES.to_vec()
    };
    let label = c["target"]
        .as_str()
        .filter(|s| !s.is_empty())
        .map(str::to_owned)
        .unwrap_or_else(|| c.get("id").map(py).unwrap_or_else(|| "<unknown>".into()));
    let mut commands = Vec::new();
    for key in keys {
        let entry = &c["categories"][key];
        if !entry.is_object() {
            return Err(format!(
                "{prefix} Missing category '{key}' for target {label}."
            ));
        }
        let status = entry["status"].as_str().unwrap_or("");
        if !["pass", "covered_existing", "not_applicable"].contains(&status)
            && !(phase == "prewrite" && status == "planned")
        {
            return Err(if phase == "precommit" && status == "planned" {
                format!("{prefix} Category '{key}' is still planned for target {label}.")
            } else {
                format!(
                    "{prefix} Invalid status '{}' for category '{key}' in target {label}.",
                    py(&entry["status"])
                )
            });
        }
        if status == "not_applicable"
            && entry["reason"].as_str().is_none_or(|s| s.trim().is_empty())
        {
            return Err(format!(
                "{prefix} Category '{key}' marked not_applicable without reason for target {label}."
            ));
        }
        if ["pass", "covered_existing"].contains(&status) {
            let Some(command) = entry["command"].as_str().filter(|s| !s.trim().is_empty()) else {
                return Err(format!(
                    "{prefix} Category '{key}' requires a runnable command for target {label}."
                ));
            };
            commands.push(command.trim().into());
        }
    }
    Ok(commands)
}
fn malformed(raw: &str, error: &serde_json::Error) -> String {
    // Python JSONDecodeError uses a character offset and Python diagnostic wording.
    let line = error.line();
    let col = error.column();
    let trimmed = raw.trim_end();
    let (message, col) = if trimmed == "{" {
        ("Expecting property name enclosed in double quotes", 2)
    } else if trimmed.ends_with("[}") {
        ("Expecting value", col)
    } else if error.to_string().starts_with("key must be a string") {
        ("Expecting property name enclosed in double quotes", col)
    } else if error.is_eof() {
        ("Expecting value", col + 1)
    } else {
        ("Expecting value", col)
    };
    let pos = raw
        .lines()
        .take(line.saturating_sub(1))
        .map(|l| l.chars().count() + 1)
        .sum::<usize>()
        + col.saturating_sub(1);
    format!(
        "[TddGuard BLOCK] Malformed tasks/tdd.json: {message}: line {line} column {col} (char {pos})"
    )
}
fn load(project: &Path) -> Result<Ledger, String> {
    let path = project.join("tasks/tdd.json");
    if !path.is_file() {
        return Err("[TddGuard BLOCK] Missing tasks/tdd.json. Create the composite TDD ledger before editing code.".into());
    }
    let raw = fs::read_to_string(path).map_err(|e| e.to_string())?;
    let v: Value = serde_json::from_str(&raw).map_err(|e| malformed(&raw, &e))?;
    if !v.is_object() {
        return Err("[TddGuard BLOCK] tasks/tdd.json must contain a JSON object.".into());
    }
    if !v["changes"].is_array() {
        return Err("[TddGuard BLOCK] tasks/tdd.json must contain a 'changes' array.".into());
    }
    Ok(Ledger {
        order: category_order(&raw)?,
        data: v,
    })
}
fn git_changed(project: &Path) -> Vec<String> {
    let run = |args: &[&str]| {
        Command::new("git")
            .args(args)
            .current_dir(project)
            .output()
            .ok()
            .filter(|o| o.status.success())
            .map(|o| String::from_utf8_lossy(&o.stdout).into_owned())
    };
    let lines = |s: String| {
        s.lines()
            .filter(|s| !s.trim().is_empty())
            .map(str::to_owned)
            .collect::<Vec<_>>()
    };
    if let Some(out) = run(&["diff", "--name-only", "@{upstream}..HEAD"]) {
        if !lines(out.clone()).is_empty() {
            return lines(out);
        }
        return run(&["diff", "--name-only", "HEAD"])
            .map(lines)
            .unwrap_or_default();
    }
    for reference in ["origin/main..HEAD", "main..HEAD"] {
        if let Some(out) = run(&["diff", "--name-only", reference])
            && !out.trim().is_empty()
        {
            return lines(out);
        }
    }
    run(&["diff", "--name-only", "HEAD"])
        .map(lines)
        .unwrap_or_default()
}
fn meta(p: &str) -> bool {
    [
        "tasks/tdd.json",
        "tasks/plan.md",
        "tasks/checklist.md",
        "tasks/change_log.md",
        "tasks/lessons.md",
        "tasks/cost-log.md",
        "docs/memory-map.md",
    ]
    .contains(&p)
        || ["tasks/sessions/", "tasks/log/", "tasks/handoffs/"]
            .iter()
            .any(|s| p.starts_with(s))
}
fn merge(project: &Path, ledger: &Ledger) -> (u8, String, String) {
    let data = &ledger.data;
    let changed = git_changed(project);
    if changed.is_empty() {
        return (0, String::new(), String::new());
    }
    let mut blockers = Vec::new();
    let mut warnings = Vec::new();
    if let Some(changes) = data["changes"].as_array() {
        for (index, c) in changes.iter().enumerate() {
            let id = c.get("id").map(py).unwrap_or_else(|| "<unnamed>".into());
            let relevant = c["targets"].as_array().is_some_and(|ts| {
                ts.iter()
                    .filter_map(Value::as_str)
                    .filter(|t| !meta(t))
                    .any(|t| changed.iter().filter(|p| !meta(p)).any(|p| matches(t, p)))
            });
            let violations: Vec<_> = c["categories"]
                .as_object()
                .into_iter()
                .flat_map(|cats| {
                    ledger.order[index]
                        .iter()
                        .filter_map(|key| cats.get(key).map(|v| (key, v)))
                })
                .filter(|(_, v)| {
                    v.is_object()
                        && !["pass", "covered_existing", "not_applicable"]
                            .contains(&v["status"].as_str().unwrap_or(""))
                })
                .map(|(k, v)| format!("{k}.status={}", repr(&v["status"])))
                .collect();
            if !violations.is_empty() {
                if relevant {
                    blockers.push(format!("{id}: {}", violations.join(", ")));
                } else {
                    warnings.push(id);
                }
            }
        }
    }
    if let Some(obj) = data.as_object() {
        for (k, v) in obj {
            if k != "version"
                && k != "changes"
                && v.is_object()
                && !v["status"].is_null()
                && !["closed", "done"].contains(&v["status"].as_str().unwrap_or(""))
            {
                warnings.push(format!("{k}.status={}", repr(&v["status"])));
            }
        }
    }
    let mut err = String::new();
    if !warnings.is_empty() {
        err.push_str(&format!("[pre-merge-gate INFO] legacy/un-touched tdd entries with open categories (grandfathered, not blocking): {}\n",warnings.len()));
    }
    if !blockers.is_empty() {
        err.push_str(&format!(
            "[pre-merge-gate BLOCK] tdd.json has open categories for files in this PR:\n  - {}\n",
            blockers.join("\n  - ")
        ));
    }
    (if blockers.is_empty() { 0 } else { 2 }, String::new(), err)
}
pub fn matrix(args: &[String]) -> (u8, String, String) {
    let fail = |code, msg: String| (code, String::new(), format!("{msg}\n"));
    if args.len() < 2 {
        return fail(2,"usage: tdd-matrix-guard.py <prewrite|precommit|precommit-merge> <project_dir> [<target>]".into());
    }
    let project = fs::canonicalize(&args[1]).unwrap_or_else(|_| PathBuf::from(&args[1]));
    let mode = args[0].as_str();
    if mode != "precommit-merge" && args.len() < 3 {
        return fail(
            2,
            "usage: tdd-matrix-guard.py <prewrite|precommit> <project_dir> <target>".into(),
        );
    }
    if !["prewrite", "precommit", "precommit-merge"].contains(&mode) {
        return fail(2, format!("unknown mode: {mode}"));
    }
    let data = match load(&project) {
        Ok(v) => v,
        Err(e) => return fail(1, e),
    };
    if mode == "precommit-merge" {
        return merge(&project, &data);
    }
    let paths = if mode == "prewrite" {
        vec![normalize(&project, &args[2])]
    } else {
        if !Path::new(&args[2]).is_file() {
            return fail(
                2,
                "[PreCommitVerification BLOCK] Missing changed-file list input.".into(),
            );
        }
        match fs::read_to_string(&args[2]) {
            Ok(s) => s
                .lines()
                .map(|p| normalize(&project, p))
                .filter(|p| implementation(p))
                .collect(),
            Err(e) => return fail(1, e.to_string()),
        }
    };
    let mut commands = Vec::new();
    for path in paths {
        let Some(c) = find(&data.data, &path) else {
            return fail(
                2,
                format!(
                    "[{} BLOCK] No composite TDD entry found in tasks/tdd.json for {path}.",
                    if mode == "prewrite" {
                        "TddGuard"
                    } else {
                        "PreCommitVerification"
                    }
                ),
            );
        };
        match validate(
            c,
            mode,
            &data.order[data.data["changes"]
                .as_array()
                .and_then(|cs| cs.iter().position(|x| std::ptr::eq(x, c)))
                .unwrap_or(0)],
        ) {
            Err(e) => return fail(1, e),
            Ok(cs) => {
                for c in cs {
                    if !commands.contains(&c) {
                        commands.push(c);
                    }
                }
            }
        }
    }
    (
        0,
        if mode == "precommit" && !commands.is_empty() {
            format!("{}\n", commands.join("\n"))
        } else {
            String::new()
        },
        String::new(),
    )
}
pub fn guard(project: &Path, target: &str) -> (u8, String, String) {
    let path = target.strip_prefix("./").unwrap_or(target);
    let rel = path
        .strip_prefix(&format!("{}/", project.display()))
        .unwrap_or(path);
    if target.is_empty() || !project.is_dir() || !implementation(rel) {
        return (0, String::new(), String::new());
    }
    // The ledger is validated in-process; the retired Python helper and its
    // interpreter route are no longer consulted.
    let err = if matrix(&["prewrite".into(), project.display().to_string(), rel.into()]).0 != 0 {
        format!("[TddGuard WARN] composite TDD evidence is incomplete for {rel} (advisory only)\n")
    } else {
        String::new()
    };
    (0, String::new(), err)
}

struct Ledger {
    data: Value,
    order: Vec<Vec<String>>,
}
// Keep Python dictionary order local: preserve_order would alter unrelated
// canonical serializers throughout the crate.
enum Ordered {
    Object(Vec<(String, Ordered)>),
    Array(Vec<Ordered>),
    Scalar,
}
impl Ordered {
    fn get(&self, key: &str) -> Option<&Self> {
        if let Self::Object(entries) = self {
            entries.iter().find(|(k, _)| k == key).map(|(_, v)| v)
        } else {
            None
        }
    }
}
impl<'de> serde::Deserialize<'de> for Ordered {
    fn deserialize<D: serde::Deserializer<'de>>(d: D) -> Result<Self, D::Error> {
        struct Visitor;
        impl<'de> serde::de::Visitor<'de> for Visitor {
            type Value = Ordered;
            fn expecting(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
                f.write_str("a JSON value")
            }
            fn visit_map<M: serde::de::MapAccess<'de>>(
                self,
                mut map: M,
            ) -> Result<Ordered, M::Error> {
                let mut entries: Vec<(String, Ordered)> = Vec::new();
                while let Some((key, value)) = map.next_entry::<String, Ordered>()? {
                    if let Some(entry) = entries.iter_mut().find(|(k, _)| k == &key) {
                        entry.1 = value;
                    } else {
                        entries.push((key, value));
                    }
                }
                Ok(Ordered::Object(entries))
            }
            fn visit_seq<S: serde::de::SeqAccess<'de>>(
                self,
                mut seq: S,
            ) -> Result<Ordered, S::Error> {
                let mut entries = Vec::new();
                while let Some(value) = seq.next_element()? {
                    entries.push(value);
                }
                Ok(Ordered::Array(entries))
            }
            fn visit_unit<E: serde::de::Error>(self) -> Result<Ordered, E> {
                Ok(Ordered::Scalar)
            }
            fn visit_bool<E: serde::de::Error>(self, _: bool) -> Result<Ordered, E> {
                Ok(Ordered::Scalar)
            }
            fn visit_i64<E: serde::de::Error>(self, _: i64) -> Result<Ordered, E> {
                Ok(Ordered::Scalar)
            }
            fn visit_u64<E: serde::de::Error>(self, _: u64) -> Result<Ordered, E> {
                Ok(Ordered::Scalar)
            }
            fn visit_f64<E: serde::de::Error>(self, _: f64) -> Result<Ordered, E> {
                Ok(Ordered::Scalar)
            }
            fn visit_str<E: serde::de::Error>(self, _: &str) -> Result<Ordered, E> {
                Ok(Ordered::Scalar)
            }
        }
        d.deserialize_any(Visitor)
    }
}
fn category_order(raw: &str) -> Result<Vec<Vec<String>>, String> {
    let data: Ordered = serde_json::from_str(raw).map_err(|e| e.to_string())?;
    let Some(Ordered::Array(changes)) = data.get("changes") else {
        return Ok(Vec::new());
    };
    Ok(changes
        .iter()
        .map(|c| match c.get("categories") {
            Some(Ordered::Object(cats)) => cats.iter().map(|(k, _)| k.clone()).collect(),
            _ => Vec::new(),
        })
        .collect())
}
