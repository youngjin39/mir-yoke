//! Library-only installed-distribution runner. Execution is supplied by the caller.
use super::ontology_check::{self, Doc, Result, error};
use crate::executor_development_packet::py_repr;
use serde_json::json;
use std::{
    cmp::Ordering,
    collections::BTreeMap,
    fs,
    path::{Path, PathBuf},
};

pub const PLUGIN: &str = "mir-core@mir-yoke";
pub const CHECKER: &str = "skills/ontology/scripts/ontology_check.py";
pub const SEMVER: &str = ontology_check::SEMVER;
#[derive(Clone, Debug)]
pub struct Distribution {
    pub version: String,
    pub checker: PathBuf,
    pub reason: String,
}
impl Distribution {
    pub fn new(version: &str, checker: PathBuf, reason: &str) -> Self {
        #[cfg(windows)]
        let checker = crate::executor_admission::lexical(&checker);
        Self {
            version: version.into(),
            checker,
            reason: reason.into(),
        }
    }
}
fn io(e: std::io::Error) -> ontology_check::Error {
    error("OSError", e.to_string())
}
/// Homes are supplied in Path.home(), account-home order (deduplicated below).
pub struct Context {
    pub homes: Vec<PathBuf>,
    pub explicit: Option<String>,
    pub repo: PathBuf,
    pub python: String,
}
/// Keep integer spelling for ordering; Python semver integers have no word limit.
fn version_parts(version: &str) -> Result<(Vec<String>, Option<String>)> {
    let invalid = || {
        error(
            "ValueError",
            format!("invalid distribution version: {version}"),
        )
    };
    let re = regex::Regex::new(&format!(r"\A{SEMVER}\z"))
        .map_err(|e| error("ValueError", e.to_string()))?;
    let c = re.captures(version).ok_or_else(invalid)?;
    let pre = c.get(4).map(|m| m.as_str().to_owned());
    if pre.as_ref().is_some_and(|p| {
        p.split('.')
            .any(|s| s.bytes().all(|b| b.is_ascii_digit()) && s.len() > 1 && s.starts_with('0'))
    }) {
        return Err(invalid());
    }
    Ok(((1..4).map(|i| c[i].to_owned()).collect(), pre))
}
pub fn version_key(version: &str) -> Result<Doc> {
    let (core, pre) = version_parts(version)?;
    let parts: Vec<String> = pre
        .as_deref()
        .unwrap_or("")
        .split('.')
        .map(|p| {
            if !p.is_empty() && p.bytes().all(|b| b.is_ascii_digit()) {
                format!("[0, {p}]")
            } else {
                format!("[1, {}]", json!(p))
            }
        })
        .collect();
    ontology_check::load_json(&format!(
        "[{}, {}, {}, {}, [{}]]",
        core[0],
        core[1],
        core[2],
        pre.is_none(),
        parts.join(", ")
    ))
}
pub fn valid_version(version: &str) -> bool {
    version_parts(version).is_ok()
}
fn numeric(a: &str, b: &str) -> Ordering {
    a.len().cmp(&b.len()).then_with(|| a.cmp(b))
}
fn compare(a: &str, b: &str) -> Ordering {
    let (Ok((ac, ap)), Ok((bc, bp))) = (version_parts(a), version_parts(b)) else {
        return a.cmp(b);
    };
    for (a, b) in ac.iter().zip(&bc) {
        let c = numeric(a, b);
        if c != Ordering::Equal {
            return c;
        }
    }
    let c = ap.is_none().cmp(&bp.is_none());
    if c != Ordering::Equal {
        return c;
    }
    let aa: Vec<_> = ap.as_deref().unwrap_or("").split('.').collect();
    let bb: Vec<_> = bp.as_deref().unwrap_or("").split('.').collect();
    for (a, b) in aa.iter().zip(&bb) {
        let an = !a.is_empty() && a.bytes().all(|b| b.is_ascii_digit());
        let bn = !b.is_empty() && b.bytes().all(|b| b.is_ascii_digit());
        let c = (!an)
            .cmp(&!bn)
            .then_with(|| if an && bn { numeric(a, b) } else { a.cmp(b) });
        if c != Ordering::Equal {
            return c;
        }
    }
    aa.len().cmp(&bb.len())
}
pub fn cache_root(home: &Path, runtime: &str) -> PathBuf {
    let path = home.join(runtime).join("plugins/cache/mir-yoke/mir-core");
    #[cfg(windows)]
    let path = crate::executor_admission::lexical(&path);
    path
}
pub fn cached_versions(home: &Path, runtime: &str) -> Result<Vec<PathBuf>> {
    let entries = match fs::read_dir(cache_root(home, runtime)) {
        Ok(e) => e,
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => return Ok(vec![]),
        Err(e) => return Err(io(e)),
    };
    let mut out = Vec::new();
    for entry in entries {
        let p = entry.map_err(io)?.path();
        if p.is_dir()
            && p.file_name()
                .and_then(|s| s.to_str())
                .is_some_and(valid_version)
        {
            out.push(p);
        }
    }
    Ok(out)
}
pub(crate) fn expand(path: &str, home: &Path) -> PathBuf {
    let path = if path == "~" {
        home.to_path_buf()
    } else if let Some(tail) = path.strip_prefix("~/") {
        home.join(tail)
    } else {
        PathBuf::from(path)
    };
    #[cfg(windows)]
    let path = crate::executor_admission::lexical(&path);
    path
}
pub fn claude_active(home: &Path) -> Result<Vec<Distribution>> {
    let metadata = home.join(".claude/plugins/installed_plugins.json");
    #[cfg(windows)]
    let metadata = crate::executor_admission::lexical(&metadata);
    if !metadata.is_file() {
        return Ok(vec![]);
    }
    let invalid = || {
        error(
            "OSError",
            format!("invalid active Claude metadata: {}", metadata.display()),
        )
    };
    let raw = fs::read_to_string(&metadata).map_err(io)?;
    let v: serde_json::Value = serde_json::from_str(&raw).map_err(|_| invalid())?;
    let plugins = v.as_object().ok_or_else(invalid)?.get("plugins");
    let records = match plugins {
        None => return Ok(vec![]),
        Some(p) => p.as_object().ok_or_else(invalid)?.get(PLUGIN),
    };
    let Some(records) = records else {
        return Ok(vec![]);
    };
    let mut active = Vec::new();
    for r in records.as_array().ok_or_else(invalid)? {
        let version = r
            .get("version")
            .and_then(|v| v.as_str())
            .ok_or_else(invalid)?;
        let install = r
            .get("installPath")
            .and_then(|v| v.as_str())
            .ok_or_else(invalid)?;
        if install.is_empty() || !valid_version(version) {
            return Err(invalid());
        }
        active.push(Distribution::new(
            version,
            expand(install, home).join(CHECKER),
            "active Claude record",
        ));
    }
    Ok(active)
}
pub fn codex_fields(config: &Path) -> Result<BTreeMap<String, String>> {
    let table = regex::Regex::new(concat!(
        r#"^\[\s*plugins\s*\.\s*["']mir-core@mir-yoke["']"#,
        r"\s*\]\s*(?:#.*)?$"
    ))
    .map_err(|e| error("ValueError", e.to_string()))?;
    let assignment = regex::Regex::new(r"^(enabled|version)\s*=\s*(.*)$")
        .map_err(|e| error("ValueError", e.to_string()))?;
    let mut fields = BTreeMap::new();
    let mut selected = false;
    for line in fs::read_to_string(config).map_err(io)?.lines() {
        let line = line.trim();
        if line.starts_with('[') {
            selected = table.is_match(line);
        } else if selected && let Some(c) = assignment.captures(line) {
            let key = c[1].to_owned();
            if fields.contains_key(&key) {
                return Err(error(
                    "OSError",
                    format!("duplicate active Codex field: {key}"),
                ));
            }
            fields.insert(key, c[2].split('#').next().unwrap_or("").trim().into());
        }
    }
    Ok(fields)
}
pub fn codex_active(home: &Path) -> Result<Vec<Distribution>> {
    let config = home.join(".codex/config.toml");
    #[cfg(windows)]
    let config = crate::executor_admission::lexical(&config);
    if !config.is_file() {
        return Ok(vec![]);
    }
    let fields = codex_fields(&config)?;
    if fields.is_empty() || fields.get("enabled").is_some_and(|s| s == "false") {
        return Ok(vec![]);
    }
    if !fields.get("enabled").is_some_and(|s| s == "true") {
        return Err(error(
            "OSError",
            format!("invalid active Codex enabled field: {}", config.display()),
        ));
    }
    let version = if let Some(raw) = fields.get("version") {
        let re = regex::Regex::new(r#"^["']([^"']+)["']$"#)
            .map_err(|e| error("ValueError", e.to_string()))?;
        match re.captures(raw) {
            Some(c) if valid_version(&c[1]) => c[1].to_owned(),
            _ => {
                return Err(error(
                    "OSError",
                    format!("invalid active Codex version: {}", config.display()),
                ));
            }
        }
    } else {
        let versions = cached_versions(home, ".codex")?;
        if versions.len() != 1 {
            return Err(error(
                "OSError",
                format!(
                    "active Codex distribution is {}: {}",
                    if versions.is_empty() {
                        "missing"
                    } else {
                        "ambiguous"
                    },
                    config.display()
                ),
            ));
        }
        versions[0]
            .file_name()
            .and_then(|s| s.to_str())
            .unwrap_or("")
            .into()
    };
    Ok(vec![Distribution::new(
        &version,
        cache_root(home, ".codex").join(&version).join(CHECKER),
        "active Codex configuration",
    )])
}
pub fn select_active_distribution(active: Vec<Distribution>) -> Result<Distribution> {
    let versions: std::collections::BTreeSet<_> =
        active.iter().map(|d| d.version.as_str()).collect();
    if versions.len() != 1 {
        return Err(error(
            "OSError",
            format!(
                "runtime distributions disagree: {}",
                versions.into_iter().collect::<Vec<_>>().join(", ")
            ),
        ));
    }
    for d in &active {
        if !d.checker.is_file() {
            return Err(error(
                "OSError",
                format!(
                    "active ontology distribution is missing: {}",
                    d.checker.display()
                ),
            ));
        }
    }
    let mut selected = active
        .into_iter()
        .next()
        .ok_or_else(|| error("IndexError", "list index out of range"))?;
    selected.checker = resolve(&selected.checker)?;
    Ok(selected)
}
/// Resolve existing paths without Windows extended-length display prefixes.
pub(crate) fn resolve(path: &Path) -> Result<PathBuf> {
    let resolved = fs::canonicalize(path).map_err(io)?;
    #[cfg(windows)]
    if let Some(text) = resolved.to_str().and_then(|s| s.strip_prefix(r"\\?\")) {
        return Ok(PathBuf::from(text));
    }
    Ok(resolved)
}
pub fn select_distribution(ctx: &Context, stderr: &mut String) -> Result<Distribution> {
    if let Some(explicit) = &ctx.explicit {
        let home = ctx
            .homes
            .first()
            .map(PathBuf::as_path)
            .unwrap_or(Path::new(""));
        let checker = expand(explicit, home);
        if explicit.is_empty() || !checker.is_file() {
            return Err(error(
                "OSError",
                format!(
                    "MIR_ONTOLOGY_CHECKER is not a file: {}",
                    if explicit.is_empty() {
                        ".".into()
                    } else {
                        checker.display().to_string()
                    }
                ),
            ));
        }
        let version = checker
            .ancestors()
            .nth(4)
            .and_then(|p| p.file_name())
            .and_then(|s| s.to_str())
            .filter(|v| valid_version(v))
            .unwrap_or("unknown");
        return Ok(Distribution::new(
            version,
            resolve(&checker)?,
            "MIR_ONTOLOGY_CHECKER override",
        ));
    }
    let mut homes = Vec::new();
    for home in &ctx.homes {
        if !homes.contains(&home) {
            homes.push(home);
        }
    }
    let mut active = Vec::new();
    for home in &homes {
        active.extend(claude_active(home)?);
        active.extend(codex_active(home)?);
    }
    if !active.is_empty() {
        return select_active_distribution(active);
    }
    let mut candidates = Vec::new();
    for home in homes {
        for runtime in [".codex", ".claude"] {
            for p in cached_versions(home, runtime)? {
                if p.join(CHECKER).is_file() {
                    candidates.push(Distribution::new(
                        p.file_name().and_then(|s| s.to_str()).unwrap_or(""),
                        p.join(CHECKER),
                        "newest cached semver fallback",
                    ));
                }
            }
        }
    }
    let mut best: Option<Distribution> = None;
    for d in candidates {
        if best
            .as_ref()
            .is_none_or(|b| compare(&d.version, &b.version) == Ordering::Greater)
        {
            best = Some(d);
        }
    }
    let mut d = best.ok_or_else(|| {
        error(
            "OSError",
            concat!(
                "Yoke ontology distribution is missing; ",
                "install mir-core or set MIR_ONTOLOGY_CHECKER"
            ),
        )
    })?;
    stderr.push_str(&format!(
        "mir_ontology: warning: no active distribution; fallback to cached version {}\n",
        d.version
    ));
    d.checker = resolve(&d.checker)?;
    Ok(d)
}
pub fn find_checker(ctx: &Context, stderr: &mut String) -> Result<PathBuf> {
    Ok(select_distribution(ctx, stderr)?.checker)
}
pub use ontology_check::Output;
pub trait Dispatch {
    /// argv retains the reference executable/tool prefix; no subprocess is created here.
    fn run(&mut self, argv: &[String], checker: bool) -> Result<Output>;
}
pub struct LibraryDispatch<'a> {
    pub checker: &'a ontology_check::Context<'a>,
    pub mk: &'a mut dyn super::mk_query::MainHost,
    pub cwd: &'a Path,
}
impl Dispatch for LibraryDispatch<'_> {
    fn run(&mut self, argv: &[String], checker: bool) -> Result<Output> {
        let args = argv
            .get(2..)
            .ok_or_else(|| error("ValueError", "missing tool prefix"))?;
        Ok(if checker {
            ontology_check::main(args, self.checker)
        } else {
            super::mk_query::main(args, self.cwd, self.mk)
        })
    }
}
pub fn main(argv: &[String], ctx: &Context, dispatch: &mut dyn Dispatch) -> Output {
    let mut out = Output {
        exit: 2,
        stdout: String::new(),
        stderr: String::new(),
    };
    let usage = "usage: mir_ontology_runner.py [-h] [--which] [{mapping,impact,lookup,mk}] ...\n";
    let mut which = false;
    let mut i = 0;
    while argv.get(i).is_some_and(|a| a == "--which") {
        which = true;
        i += 1;
    }
    if argv.get(i).is_some_and(|a| a == "--help" || a == "-h") {
        out.exit = 0;
        out.stdout = format!(
            "{usage}{}",
            concat!(
                "\nCopy to scripts/mir_ontology.py to run installed ontology tools (Python\n",
                "3.11+).\n\npositional arguments:\n  {mapping,impact,lookup,mk}\n  arguments\n",
                "\noptions:\n  -h, --help            show this help message and exit\n",
                "  --which               show selected version, path and reason\n"
            )
        );
        return out;
    }
    let command = argv.get(i).map(String::as_str);
    let invalid = match command {
        None if !which => Some("a command or --which is required".into()),
        Some(c) if !["mapping", "impact", "lookup", "mk"].contains(&c) => Some(format!(
            concat!(
                "argument command: invalid choice: {} ",
                "(choose from mapping, impact, lookup, mk)"
            ),
            py_repr(c)
        )),
        _ => None,
    };
    if let Some(message) = invalid {
        out.stderr = format!("{usage}mir_ontology_runner.py: error: {message}\n");
        return out;
    }
    let result = (|| {
        let d = select_distribution(ctx, &mut out.stderr)?;
        if which {
            out.stdout = format!(
                "version: {}\npath: {}\nreason: {}\n",
                d.version,
                d.checker.display(),
                d.reason
            );
            return Ok(0);
        }
        let command = command.unwrap_or("");
        let mut forwarded = argv[i + 1..].to_vec();
        let tool = if command == "mk" {
            d.checker.with_file_name("mk_query.py")
        } else {
            d.checker
        };
        let mut args = vec![ctx.python.clone(), tool.display().to_string()];
        if command == "mk" {
            let soft = if forwarded.first().is_some_and(|s| s == "query") {
                let soft = forwarded.iter().skip(2).any(|s| s == "--soft");
                forwarded = forwarded
                    .into_iter()
                    .enumerate()
                    .filter(|(i, s)| *i < 2 || s != "--soft")
                    .map(|(_, s)| s)
                    .collect();
                soft
            } else if forwarded.last().is_some_and(|s| s == "--soft") {
                forwarded.pop();
                true
            } else {
                false
            };
            args.extend(["--repo".into(), ctx.repo.display().to_string()]);
            if soft {
                args.push("--soft".into());
            }
        } else {
            args.extend([
                command.into(),
                "--repo".into(),
                ctx.repo.display().to_string(),
            ]);
        }
        args.extend(forwarded);
        if !tool.is_file() {
            return Err(error(
                "OSError",
                format!("Yoke ontology distribution is missing: {}", tool.display()),
            ));
        }
        let child = dispatch.run(&args, command != "mk")?;
        out.stdout.push_str(&child.stdout);
        out.stderr.push_str(&child.stderr);
        Ok(child.exit)
    })();
    match result {
        Ok(exit) => out.exit = exit,
        Err(e) => out.stderr.push_str(&format!("mir_ontology: {e}\n")),
    }
    out
}
