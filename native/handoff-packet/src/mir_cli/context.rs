//! FTS context pull/profile helpers and sync; sync admission lives in context_sync.
#![forbid(unsafe_code)]
use crate::mir_core::context::profile_task_context::{
    ProfileTaskContext, ordered_python_str, python_str, string_list,
};
use serde_json::Value;
pub fn profile_context_lines(profile: &ProfileTaskContext) -> Vec<String> {
    let context = &profile.value;
    if context.is_null() {
        return Vec::new();
    }
    let repo = &context["repository"];
    let mut line = format!(
        "[repository] {} type={}",
        repo["slug"].as_str().unwrap_or("unknown"),
        repo["repository_type"].as_str().unwrap_or("unknown")
    );
    let purpose = python_str(repo.get("purpose").unwrap_or(&Value::String(String::new())))
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ");
    if !purpose.is_empty() {
        line.push_str(&format!(" purpose={purpose}"));
    }
    let mut lines = vec![line];
    let stack = string_list(&repo["technology_stack"]);
    if !stack.is_empty() {
        lines.push(format!("[repository-stack] {}", stack.join(", ")));
    }
    let safety = &context["safety"];
    for key in ["protected_paths", "generated_paths"] {
        let values = string_list(&safety[key]);
        if !values.is_empty() {
            lines.push(format!("[safety] {key}={}", values.join(", ")));
        }
    }
    for (section, values) in [
        ("preserve", &profile.preserve),
        ("boundaries", &profile.boundaries),
    ] {
        for (key, value) in values {
            // Python equality with False also excludes integer and floating zero.
            let skip = match value {
                toml::Value::String(text) => text.is_empty(),
                toml::Value::Array(items) => items.is_empty(),
                toml::Value::Boolean(flag) => !flag,
                toml::Value::Integer(number) => *number == 0,
                toml::Value::Float(number) => *number == 0.0,
                _ => false,
            };
            if skip {
                continue;
            }
            let rendered = if let toml::Value::Array(items) = value {
                items
                    .iter()
                    .map(ordered_python_str)
                    .collect::<Vec<_>>()
                    .join(", ")
            } else {
                ordered_python_str(value)
            };
            lines.push(format!("[safety] {section}.{key}={rendered}"));
        }
    }
    let mut gates = profile
        .gates
        .iter()
        .filter(|(_, value)| value.as_bool() == Some(true))
        .map(|(key, _)| key.as_str())
        .collect::<Vec<_>>();
    gates.sort_unstable();
    if !gates.is_empty() {
        lines.push(format!("[safety] enabled_gates={}", gates.join(", ")));
    }
    for item in context["selected_refs"].as_array().into_iter().flatten() {
        lines.push(format!(
            "[context-ref] {} {}",
            python_str(&item["kind"]),
            python_str(&item["path"])
        ));
    }
    let fresh = &context["freshness"];
    let mut line = format!(
        "[profile-freshness] state={} base={}",
        python_str(&fresh["state"]),
        python_str(&fresh["base_commit"])
    );
    let changed = string_list(&fresh["changed_selected"]);
    if !changed.is_empty() {
        line.push_str(&format!(" changed={}", changed.join(",")));
    }
    line.push_str(&format!(" reason={}", python_str(&fresh["reason"])));
    lines.push(line);
    if context["needs_investigation"] == true {
        lines.push(
            "[context-advisory] inspect only the selected or uncertain boundary before expanding"
                .into(),
        );
    }
    for warning in string_list(&context["warnings"]) {
        lines.push(format!("[context-advisory] {warning}"));
    }
    lines
}
pub fn profile_search_scopes(context: &Value) -> Value {
    if context.is_null() {
        return Value::Null;
    }
    let mut scopes = string_list(&context["task"]["target_paths"]);
    let has_targets = !scopes.is_empty();
    for item in context["selected_refs"].as_array().into_iter().flatten() {
        if has_targets
            && ["code_scope", "non_code_scope"].contains(&item["kind"].as_str().unwrap_or(""))
        {
            continue;
        }
        if let Some(p) = item["path"].as_str() {
            scopes.push(p.into());
        }
    }
    let mut compact = Vec::new();
    for scope in scopes {
        if !scope.is_empty() && !compact.contains(&scope) {
            compact.push(scope);
        }
    }
    serde_json::json!((!compact.is_empty()).then_some(compact))
}

use crate::mir_core::{
    config::loader,
    memory::{distill, external_store, store},
};
use serde_json::json;
use std::{collections::BTreeSet, path::Path};

pub const NEAR_DUP_THRESHOLD: f64 = 0.85;
const SUFFIX: &str = "\u{2026}[truncated]";
const VEC_NOTICE: &str = concat!(
    "sqlite-vec unavailable, FTS5-only mode: sqlite-vec package not installed: ",
    "import of sqlite_vec halted; None in sys.modules\n"
);
type Result<T> = std::result::Result<T, Box<dyn std::error::Error>>;
pub type Output = (i32, Vec<u8>, Vec<u8>);
/// Library-only sync. Configuration is supplied by the owner, without discovery.
pub fn do_sync(
    db: &external_store::ExternalStore<'_>,
    cfg: &Value,
    project_root: &Path,
    home: &Path,
) -> std::result::Result<(i32, String), external_store::HelperError> {
    do_sync_with_embedding(db, cfg, project_root, home, false, || Ok(None))
}
/// Inject the embedding factory without connecting a live backend or caller.
pub fn do_sync_with_embedding<'e>(
    db: &external_store::ExternalStore<'_>,
    cfg: &Value,
    project_root: &Path,
    home: &Path,
    reindex_missing_vectors: bool,
    build_embed_fn: impl FnOnce() -> std::result::Result<
        Option<&'e mut external_store::EmbedFn<'e>>,
        external_store::HelperError,
    >,
) -> std::result::Result<(i32, String), external_store::HelperError> {
    use crate::mir_core::config::loader::resolve_path;
    let os_error =
        |e: crate::mir_core::config::loader::ConfigLoadError| external_store::HelperError {
            kind: "OSError",
            message: e.to_string(),
        };
    // resolve_archive_root: expanduser, join to the resolved project root, resolve(strict=False).
    let project_root = resolve_path(project_root, ".", home).map_err(os_error)?;
    for archive in cfg["memory"]["external_archives"]
        .as_array()
        .into_iter()
        .flatten()
    {
        // Like _do_sync, consume the already-resolved config without revalidating it.
        let mut a = external_store::Registration {
            slug: archive["slug"].as_str().unwrap_or("").into(),
            root_path: archive["root"].as_str().unwrap_or("").into(),
            mode: archive["mode"].as_str().unwrap_or("indexed").into(),
            owner: "family:your-harness".into(),
            glob_include: string_list(&archive["glob_include"]),
            glob_exclude: string_list(&archive["glob_exclude"]),
            historical_glob: string_list(&archive["historical_glob"]),
            chunk_size: archive["chunk_size"].as_i64().unwrap_or(800),
            chunk_overlap: archive["chunk_overlap"].as_i64().unwrap_or(100),
        };
        let root = resolve_path(&project_root, &a.root_path, home).map_err(os_error)?;
        a.root_path = root
            .to_str()
            .ok_or_else(|| external_store::HelperError {
                kind: "ValueError",
                message: "archive path is not UTF-8".into(),
            })?
            .into();
        if a.glob_include.is_empty() {
            a.glob_include.push("**/*.md".into());
        }
        db.register(&a)?;
    }
    let rows = db
        .connection
        .conn
        .prepare("SELECT id,slug FROM external_archives ORDER BY id")?
        .query_map([], |r| Ok((r.get::<_, i64>(0)?, r.get::<_, String>(1)?)))?
        .collect::<std::result::Result<Vec<_>, _>>()?;
    if rows.is_empty() {
        return Ok((0, "no archives configured\n".into()));
    }
    let (mut failed, mut output) = (false, String::new());
    if reindex_missing_vectors {
        if cfg["memory"]["embedding"]["enabled"] != true {
            return Ok((
                2,
                "missing-vector reindex requires memory.embedding.enabled=true\n".into(),
            ));
        }
        if !db.connection.vec_available {
            return Ok((2, "missing-vector reindex requires sqlite-vec\n".into()));
        }
    }
    let mut embed_fn = match build_embed_fn() {
        Ok(backend) => backend,
        Err(e) if e.kind == "NativeRouteUnavailable" => return Err(e),
        Err(e) if reindex_missing_vectors => {
            return Ok((
                1,
                format!("missing-vector reindex embedding backend unavailable: {e}\n"),
            ));
        }
        Err(e) => {
            if cfg["memory"]["embedding"]["required"] == true
                || cfg["memory"]["vector_mode"] == "required"
            {
                return Ok((1, format!("required embedding backend unavailable: {e}\n")));
            }
            output.push_str(&format!(
                "[degraded] embedding unavailable \u{2014} FTS-only sync: {e}\n"
            ));
            None
        }
    };
    let fingerprint = cfg["memory"]["embedding"]["fingerprint"].as_str();
    if reindex_missing_vectors {
        let Some(encode) = embed_fn else {
            return Ok((
                2,
                "missing-vector reindex requires an embedding backend\n".into(),
            ));
        };
        for (id, slug) in rows {
            let result =
                match db.reindex_missing_vectors(id, Some(encode), fingerprint.unwrap_or("")) {
                    Err(e) if e.kind == "ExternalStoreError" => {
                        failed = true;
                        output.push_str(&format!("{slug}: vector reindex refused: {e}\n"));
                        continue;
                    }
                    other => other?,
                };
            output.push_str(&format!(
                "{slug}: vector_coverage={}/{} reindexed={} unchanged={}\n",
                result.indexed, result.eligible, result.reindexed, result.unchanged
            ));
            if !result.failed.is_empty() {
                failed = true;
            }
            for (rel, reason) in result.failed {
                output.push_str(&format!("  [failed] {rel}: {reason}\n"));
            }
        }
        return Ok((i32::from(failed), output));
    }
    for (id, slug) in rows {
        let mut result = match db.scan_with_vectors(
            id,
            embed_fn
                .as_mut()
                .map(|f| &mut **f as &mut external_store::EmbedFn<'_>),
            fingerprint,
            None,
        ) {
            Err(e) if e.kind == "ExternalStoreError" => {
                failed = true;
                output.push_str(&format!("{slug}: vector indexing refused: {}\n", e.message));
                continue;
            }
            other => other?,
        };
        if !result.failed.is_empty()
            && embed_fn.is_some()
            && cfg["memory"]["vector_mode"] == "optional"
        {
            output.push_str(&format!(
                "[degraded] {slug}: vector indexing failed \u{2014} retrying FTS-only\n"
            ));
            result = db.scan(id, None)?;
        }
        for (rel, reason) in &result.failed {
            output.push_str(&format!("  [failed] {rel}: {reason}\n"));
        }
        output.push_str(&format!(
            "{slug}: inserted={} reindexed={} unchanged={} deleted={}",
            result.inserted, result.reindexed, result.unchanged, result.deleted
        ));
        if !result.failed.is_empty() {
            failed = true;
            output.push_str(&format!(" failed={}", result.failed.len()));
        }
        output.push('\n');
    }
    Ok((i32::from(failed), output))
}
/// Frozen FTS fixture factory result; the console uses the configured provider.
#[derive(Clone, Copy)]
pub enum EmbeddingState {
    Absent,
    Present,
    Failed,
}
pub fn shingles(text: &str) -> BTreeSet<String> {
    let text = text
        .to_lowercase()
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ");
    let chars = text.chars().collect::<Vec<_>>();
    if chars.len() < 8 {
        return if text.is_empty() {
            BTreeSet::new()
        } else {
            BTreeSet::from([text])
        };
    }
    chars.windows(8).map(|s| s.iter().collect()).collect()
}
pub fn jaccard(a: &BTreeSet<String>, b: &BTreeSet<String>) -> f64 {
    if a.is_empty() || b.is_empty() {
        return 0.0;
    }
    a.intersection(b).count() as f64 / a.union(b).count() as f64
}
fn truncate(text: &str, bytes: usize) -> String {
    if bytes < SUFFIX.len() {
        return String::new();
    }
    if text.len() <= bytes {
        return text.into();
    }
    let mut end = bytes - SUFFIX.len();
    while !text.is_char_boundary(end) {
        end -= 1;
    }
    format!("{}{SUFFIX}", &text[..end])
}
/// Explicit key order for Python json.dumps byte parity, without a global map change.
fn object(fields: &[(&str, String)]) -> String {
    format!(
        "{{{}}}",
        fields
            .iter()
            .map(|(k, v)| format!("{}: {v}", json!(k)))
            .collect::<Vec<_>>()
            .join(", ")
    )
}
fn ordered(v: &Value, keys: &[&str]) -> String {
    object(
        &keys
            .iter()
            .filter_map(|k| v.get(k).map(|v| (*k, json_text(v))))
            .collect::<Vec<_>>(),
    )
}
fn json_text(v: &Value) -> String {
    if let Some(items) = v.as_array() {
        return format!(
            "[{}]",
            items.iter().map(json_text).collect::<Vec<_>>().join(", ")
        );
    }
    let keys: &[&str] = if v.get("repository").is_some() {
        &[
            "repository",
            "task",
            "safety",
            "selected_refs",
            "freshness",
            "needs_investigation",
            "warnings",
        ]
    } else if v.get("repository_type").is_some() {
        &[
            "slug",
            "repository_type",
            "purpose",
            "technology_stack",
            "profile_verified_at",
        ]
    } else if v.get("target_paths").is_some() {
        &["query", "risk", "target_paths"]
    } else if v.get("protected_paths").is_some() {
        &[
            "protected_paths",
            "generated_paths",
            "preserve",
            "boundaries",
            "gates",
        ]
    } else if v.get("base_commit").is_some() {
        &[
            "state",
            "base_commit",
            "head",
            "changed_selected",
            "changed_selected_count",
            "reason",
        ]
    } else if v.get("kind").is_some() {
        &["kind", "path"]
    } else if v.get("source_content_ids").is_some() {
        &[
            "id",
            "status",
            "subject",
            "predicate",
            "object",
            "source_content_ids",
        ]
    } else if v.get("archive_slug").is_some() {
        &[
            "archive_slug",
            "relative_path",
            "byte_start",
            "byte_end",
            "score",
            "status",
            "snippet",
        ]
    } else {
        return crate::executor_development_packet::render(v);
    };
    ordered(v, keys)
}
fn fact_prefix(f: &Value) -> String {
    let sources = f["source_content_ids"]
        .as_array()
        .into_iter()
        .flatten()
        .map(Value::to_string)
        .collect::<Vec<_>>()
        .join(",");
    format!(
        "[fact] #{} [{}] {} {} [sources:{}] ",
        f["id"],
        f["status"].as_str().unwrap_or(""),
        f["subject"].as_str().unwrap_or(""),
        f["predicate"].as_str().unwrap_or(""),
        if sources.is_empty() {
            "unknown"
        } else {
            &sources
        }
    )
}
const UNSAFE_PATTERNS: &[&str] = &[
    concat!(
        r"(?is)\b(?:ignore|disregard|override)\b.{0,80}",
        r"\b(?:all|any|previous|prior|earlier|above|system|developer)\b.{0,40}",
        r"\b(?:instructions?|directions?|rules?|guidance)\b"
    ),
    concat!(
        r"(?is)\b(?:you\s+must|must|immediately|now)\b.{0,60}",
        r"\b(?:execute|run|invoke|call)\b.{0,40}",
        r"\b(?:tools?|commands?|shell|bash|terminal)\b"
    ),
    r"(?is)\b(?:reveal|print|exfiltrate)\b.{0,80}\b(?:system prompt|credentials?|secrets?)\b",
    r"(?i)<\s*/?\s*(?:system|assistant|developer|tool)\b",
    r"\bsk-[A-Za-z0-9_-]{20,}\b",
    r"\b(?:ghp|gho)_[A-Za-z0-9]{36}\b",
    r"\bAIza[A-Za-z0-9_-]{35}\b",
    r"\bxoxb-[0-9A-Za-z-]{20,}\b",
    r"\bAKIA[A-Z0-9]{16}\b",
    r"(?i)\baws_secret_access_key\s*=\s*\S+",
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
];
fn search_fact_rows(
    c: &rusqlite::Connection,
    q: &str,
    k: i64,
    history: bool,
) -> Result<(Vec<Value>, Vec<i64>)> {
    let status = if history {
        ""
    } else {
        "AND f.status = 'active'"
    };
    let sql = format!(
        "SELECT f.id,f.status,COALESCE(s.slug,s.canonical_name,'unknown-subject'),
         f.predicate,COALESCE(f.object_literal,o.slug,''),COALESCE(
         (SELECT GROUP_CONCAT(DISTINCT p.content_item_id) FROM provenance p
         WHERE p.fact_id=f.id AND p.content_item_id IS NOT NULL),CAST(f.created_from AS TEXT),'')
         FROM facts_fts x JOIN facts f ON f.id=x.rowid
         LEFT JOIN entities s ON s.id=f.subject_entity_id
         LEFT JOIN entities o ON o.id=f.object_entity_id WHERE facts_fts MATCH ? {status}
         ORDER BY bm25(facts_fts), f.id ASC LIMIT ?"
    );
    let mut stmt = c.prepare(&sql)?;
    let rows = stmt.query_map(
        rusqlite::params![
            distill::sanitize_fts_query(q).map_err(|e| std::io::Error::other(format!("{e:?}")))?,
            k
        ],
        |r| {
            let ids: String = r.get(5)?;
            Ok(
                json!({"id":r.get::<_,i64>(0)?,"status":r.get::<_,String>(1)?,
            "subject":r.get::<_,String>(2)?,"predicate":r.get::<_,String>(3)?,
            "object":r.get::<_,String>(4)?,"source_content_ids":ids.split(',')
                .filter_map(|s| s.parse::<i64>().ok()).collect::<Vec<_>>()}),
            )
        },
    )?;
    let patterns = UNSAFE_PATTERNS
        .iter()
        .map(|p| regex::Regex::new(p))
        .collect::<std::result::Result<Vec<_>, _>>()?;
    let (mut safe, mut blocked) = (Vec::new(), Vec::new());
    for row in rows {
        let f = row?;
        let body = format!(
            "{} {} {}",
            f["subject"].as_str().unwrap_or(""),
            f["predicate"].as_str().unwrap_or(""),
            f["object"].as_str().unwrap_or("")
        );
        if patterns.iter().any(|p| p.is_match(&body)) {
            if let Some(id) = f["id"].as_i64() {
                blocked.push(id);
            }
        } else {
            safe.push(f);
        }
    }
    Ok((safe, blocked))
}
fn human_facts(facts: Vec<Value>) -> Vec<Value> {
    let (mut out, mut remaining) = (Vec::new(), 2048usize);
    for mut f in facts {
        let prefix = fact_prefix(&f);
        let body = f["object"].as_str().unwrap_or("");
        let sep = usize::from(!out.is_empty());
        let size = prefix.len() + body.len() + sep;
        if size <= remaining {
            remaining -= size;
            out.push(f);
            continue;
        }
        let budget = remaining.saturating_sub(prefix.len() + sep);
        if budget >= SUFFIX.len() {
            f["object"] = json!(truncate(body, budget));
            out.push(f);
        }
        break;
    }
    out
}
fn json_facts(facts: &[Value]) -> String {
    let mut out = Vec::new();
    for f in facts {
        let mut next = out.clone();
        next.push(f.clone());
        if json_text(&json!(next)).len() <= 2048 {
            out = next;
            continue;
        }
        let body = f["object"].as_str().unwrap_or("");
        let (mut low, mut high, mut best) = (0, body.len(), None);
        while low <= high {
            let mid = (low + high) / 2;
            let mut trial = f.clone();
            trial["object"] = json!(truncate(body, mid));
            let mut next = out.clone();
            next.push(trial.clone());
            if json_text(&json!(next)).len() <= 2048 {
                best = Some(trial);
                low = mid + 1;
            } else if mid == 0 {
                break;
            } else {
                high = mid - 1;
            }
        }
        if let Some(f) = best.filter(|f| f["object"].as_str().unwrap_or("").contains(SUFFIX)) {
            out.push(f);
        }
        break;
    }
    json_text(&json!(out))
}

#[derive(Clone, Copy)]
enum Action {
    Help,
    History,
    Json,
    K,
    Path,
    Risk,
    Db,
    Root,
}
struct OptionSpec {
    name: &'static str,
    value: bool,
    action: Action,
}
const OPTIONS: &[OptionSpec] = &[
    OptionSpec {
        name: "--help",
        value: false,
        action: Action::Help,
    },
    OptionSpec {
        name: "--history",
        value: false,
        action: Action::History,
    },
    OptionSpec {
        name: "--json",
        value: false,
        action: Action::Json,
    },
    OptionSpec {
        name: "--k",
        value: true,
        action: Action::K,
    },
    OptionSpec {
        name: "--path",
        value: true,
        action: Action::Path,
    },
    OptionSpec {
        name: "--risk",
        value: true,
        action: Action::Risk,
    },
    OptionSpec {
        name: "--db",
        value: true,
        action: Action::Db,
    },
    OptionSpec {
        name: "--project-root",
        value: true,
        action: Action::Root,
    },
];
/// Library boundary: all relative paths use cwd; no caller or environment discovery.
/// Retrieval consumes no wall clock; profile freshness uses the existing Git helper.
pub fn main(argv: &[&str], cwd: &Path, embedding: EmbeddingState) -> Result<Output> {
    main_inner(argv, cwd, Some(embedding), &Path::to_path_buf)
}
pub fn console(
    argv: &[&str],
    cwd: &Path,
    path: &dyn Fn(&Path) -> std::path::PathBuf,
) -> Result<Output> {
    main_inner(argv, cwd, None, path)
}
const PULL_USAGE: &str = "usage: mir context pull [-h] [--history] [--json] [--k K]\n                        [--path TARGET_PATHS] [--risk {low,normal,high}]\n                        [--db DB] [--project-root PROJECT_ROOT]\n                        query\n";
const PULL_HELP: &str = "\npositional arguments:\n  query                 search query\n\noptions:\n  -h, --help            show this help message and exit\n  --history             include expired/archived docs and facts\n  --json                machine-readable JSON output\n  --k K                 number of results (default: 8)\n  --path TARGET_PATHS   repository-relative task target (repeatable)\n  --risk {low,normal,high}\n                        main-agent task risk classification (default: normal)\n  --db DB\n  --project-root PROJECT_ROOT\n";
fn main_inner(
    argv: &[&str],
    cwd: &Path,
    embedding: Option<EmbeddingState>,
    path: &dyn Fn(&Path) -> std::path::PathBuf,
) -> Result<Output> {
    let (mut query, mut history, mut json_output, mut k) = (None, false, false, 8i64);
    let mut k_overflow = false;
    let (mut paths, mut risk, mut db, mut root) = (Vec::new(), "normal", None, None);
    let fail = |message: &str| {
        (
            2,
            Vec::new(),
            format!("{PULL_USAGE}mir context pull: error: {message}\n").into_bytes(),
        )
    };
    if argv.first() != Some(&"pull") {
        return Ok(fail("expected pull"));
    }
    let option_names: Vec<_> = OPTIONS.iter().map(|o| o.name).collect();
    let option_like = |s: &str| super::context_sync::option_like_with(s, &option_names);
    let (mut i, mut unknown, mut positional_only) = (1, Vec::new(), false);
    while i < argv.len() {
        let token = argv[i];
        i += 1;
        if !positional_only && token == "--" {
            positional_only = true;
            if query.is_some() {
                unknown.push(token);
            }
            continue;
        }
        if positional_only || !option_like(token) {
            if query.is_none() {
                query = Some(token);
            } else {
                unknown.push(token);
            }
            continue;
        }
        let (name, mut inline) = token
            .split_once('=')
            .map_or((token, None), |(a, b)| (a, Some(b)));
        let name = if name.starts_with("-h") && !name.starts_with("--") {
            inline = super::context_sync::short_help_error(token);
            "--help"
        } else {
            name
        };
        let matches: Vec<_> = OPTIONS
            .iter()
            .filter(|o| o.name == name || (name.starts_with("--") && o.name.starts_with(name)))
            .collect();
        if matches.len() > 1 {
            return Ok(fail(&format!(
                "ambiguous option: {name} could match {}",
                matches
                    .iter()
                    .map(|o| o.name)
                    .collect::<Vec<_>>()
                    .join(", ")
            )));
        }
        if let Some(opt) = matches.first() {
            let label = if matches!(opt.action, Action::Help) {
                "-h/--help"
            } else {
                opt.name
            };
            let value = if opt.value {
                if let Some(v) = inline {
                    v
                } else {
                    let Some(v) = argv.get(i).filter(|v| !option_like(v)) else {
                        return Ok(fail(&format!("argument {label}: expected one argument")));
                    };
                    i += 1;
                    v
                }
            } else {
                if let Some(v) = inline {
                    return Ok(fail(&format!(
                        "argument {label}: ignored explicit argument {}",
                        crate::executor_execute::repr(v)
                    )));
                }
                ""
            };
            match opt.action {
                Action::Help => {
                    return Ok((
                        0,
                        format!("{PULL_USAGE}{PULL_HELP}").into_bytes(),
                        Vec::new(),
                    ));
                }
                Action::History => history = true,
                Action::Json => json_output = true,
                Action::K => match python_k(value) {
                    Some(Some(v)) => {
                        k = v;
                        k_overflow = false;
                    }
                    Some(None) => k_overflow = true,
                    None => {
                        return Ok(fail(&format!(
                            "argument --k: invalid int value: {}",
                            python_int_repr(value)
                        )));
                    }
                },
                Action::Path => paths.push(value),
                Action::Risk => {
                    if !["low", "normal", "high"].contains(&value) {
                        return Ok(fail(&format!(
                            "argument --risk: invalid choice: {} (choose from low, normal, high)",
                            crate::executor_execute::repr(value)
                        )));
                    }
                    risk = value;
                }
                Action::Db => db = Some(super::context_sync::python_path(&path(Path::new(value)))),
                Action::Root => {
                    root = Some(super::context_sync::python_path(&path(Path::new(value))))
                }
            }
        } else {
            unknown.push(token);
        }
    }
    let Some(query) = query else {
        return Ok(fail("the following arguments are required: query"));
    };
    if !unknown.is_empty() {
        return Ok((2, Vec::new(), format!("usage: mir context [-h] {{pull,sync}} ...\nmir context: error: unrecognized arguments: {}\n", unknown.join(" ")).into_bytes()));
    }
    let actual_cwd;
    let cwd = if embedding.is_none() {
        actual_cwd = match std::env::current_dir() {
            Ok(p) => p,
            Err(e) => {
                return Ok((
                    1,
                    Vec::new(),
                    super::context_sync::cwd_error(e).into_bytes(),
                ));
            }
        };
        actual_cwd.as_path()
    } else {
        cwd
    };
    let db = db
        .map(|p| if embedding.is_some() { cwd.join(p) } else { p })
        .unwrap_or_else(|| cwd.join(".mir/memory.db"));
    let root = root.unwrap_or_else(|| {
        let parent = db.parent().unwrap_or(cwd);
        if db.file_name().is_some_and(|n| n == "memory.db")
            && parent.file_name().is_some_and(|n| n == ".mir")
        {
            parent.parent().unwrap_or(cwd).to_owned()
        } else {
            parent.to_owned()
        }
    });
    let home = std::env::var_os("HOME")
        .map(std::path::PathBuf::from)
        .unwrap_or_else(|| cwd.to_owned());
    let root = loader::resolve_path(
        cwd,
        &crate::executor_text::os_text(cwd.join(root).as_os_str()),
        &home,
    )?;
    if !db.is_file() {
        return Ok((
            2,
            format!(
                "no memory.db at {} — run 'mir migrate up' first\n",
                crate::executor_text::os_text(db.as_os_str())
            )
            .into_bytes(),
            Vec::new(),
        ));
    }
    let cfg = match loader::load_config(
        Some(&root),
        if embedding.is_none() { &home } else { cwd },
        cwd,
    ) {
        Ok(cfg) => cfg.to_dict(),
        Err(e) => {
            return Ok((
                2,
                format!("invalid memory configuration: {e}\n").into_bytes(),
                Vec::new(),
            ));
        }
    };
    let connection = store::connect(
        &db,
        store::ConnectOptions {
            timeout: None,
            vec_loading: if embedding.is_none() {
                store::VecLoading::Bundled
            } else {
                store::VecLoading::Disabled
            },
        },
    )?;
    let c = &connection.conn;
    let profile = crate::mir_core::context::profile_task_context::build_profile_task_context(
        &root, query, &paths, risk,
    )?;
    let scopes = if history {
        Vec::new()
    } else {
        string_list(&profile_search_scopes(&profile.value))
    };
    let mut degraded = matches!(embedding, Some(EmbeddingState::Failed));
    let mut notices = Vec::<String>::new();
    if degraded {
        notices.push("[degraded] embedding unavailable \u{2014} FTS-only results".into());
    }
    let mut backend = if embedding.is_none() && cfg["memory"]["embedding"]["enabled"] == true {
        match super::context_sync::backend(&cfg["memory"]["embedding"]) {
            Ok(provider) => Some(provider),
            Err(_) => {
                degraded = true;
                notices.push("[degraded] embedding unavailable \u{2014} FTS-only results".into());
                None
            }
        }
    } else {
        None
    };
    let clock = crate::executor_execute::utc_now;
    let es = external_store::ExternalStore::new(&connection, &clock)?;
    let enabled = backend.is_some();
    let mut encode = |texts: &[String]| {
        backend
            .as_mut()
            .ok_or_else(|| external_store::HelperError {
                kind: "RuntimeError",
                message: "embedding provider unavailable".into(),
            })?
            .encode(texts)
            .map_err(|e| external_store::HelperError {
                kind: "RuntimeError",
                message: e.message,
            })
    };
    if k_overflow {
        return Ok((
            1,
            Vec::new(),
            b"OverflowError: Python int too large to convert to SQLite INTEGER\n".to_vec(),
        ));
    }
    let (facts, blocked) = search_fact_rows(c, query, k, history)?;
    if !blocked.is_empty() {
        notices.push(format!(
            "[unsafe-memory] unsafe fact(s) omitted: {}",
            blocked
                .iter()
                .map(i64::to_string)
                .collect::<Vec<_>>()
                .join(",")
        ));
    }
    let facts = human_facts(facts);
    let archives: i64 = c.query_row("SELECT COUNT(*) FROM external_archives", [], |r| r.get(0))?;
    if archives == 0 {
        notices.push(
            concat!(
                "no archives configured \u{2014} run 'mir context sync' after adding ",
                "[[memory.external_archives]] to harness_a.toml"
            )
            .into(),
        );
    }
    // An embedding/search error retries exactly once without the provider.
    let hits = if archives == 0 {
        Vec::new()
    } else {
        match es.search(
            query,
            k,
            &scopes,
            history,
            enabled.then_some(&mut encode),
            if enabled {
                cfg["memory"]["embedding"]["fingerprint"].as_str()
            } else {
                None
            },
        ) {
            Ok(hits) => hits,
            Err(_) if enabled => {
                degraded = true;
                notices.push("[degraded] embedding unavailable — FTS-only results".into());
                es.search(query, k, &scopes, history, None, None)
                    .unwrap_or_default()
            }
            Err(_) => Vec::new(),
        }
    };
    let (mut chunks, mut seen) = (Vec::new(), Vec::new());
    for hit in hits {
        let data = std::fs::read(Path::new(&hit.root).join(&hit.relative_path));
        let data = match data {
            Ok(data) if crate::digest::sha256(&data) == hit.file_hash => data,
            _ => {
                notices.push("[stale] index entry skipped \u{2014} run 'mir context sync'".into());
                continue;
            }
        };
        // Python slicing clamps an out-of-range or inverted range to a short or empty slice.
        let end = hit.byte_end.min(data.len());
        let snippet = String::from_utf8_lossy(&data[hit.byte_start.min(end)..end]).into_owned();
        let sh = shingles(&snippet);
        if seen
            .iter()
            .any(|old| jaccard(&sh, old) > NEAR_DUP_THRESHOLD)
        {
            continue;
        }
        seen.push(sh);
        chunks.push(
            json!({"archive_slug":hit.archive_slug,"relative_path":hit.relative_path,
            "byte_start":hit.byte_start,"byte_end":hit.byte_end,"score":hit.score,
            "status":hit.status,"snippet":snippet}),
        );
        if chunks.len() as i64 >= k {
            break;
        }
    }
    let mut remaining = 6144isize;
    let mut bounded = Vec::new();
    for mut chunk in chunks {
        if remaining <= 0 {
            break;
        }
        let snippet = chunk["snippet"].as_str().unwrap_or("");
        let size = indented_len(snippet);
        if size <= remaining as usize {
            remaining -= size as isize + 1;
        } else {
            let avail = remaining - 2 - SUFFIX.len() as isize;
            if avail <= 0 {
                break;
            }
            let bytes = snippet.as_bytes();
            let text = format!(
                "{}{SUFFIX}",
                String::from_utf8_lossy(&bytes[..avail as usize])
            );
            remaining -= indented_len(&text) as isize + 1;
            chunk["snippet"] = json!(text);
        }
        bounded.push(chunk);
    }
    let out = if json_output {
        object(&[
            ("degraded", json!(degraded).to_string()),
            ("notices", json_text(&json!(notices))),
            ("repository_context", json_text(&profile.value)),
            ("facts", json_facts(&facts)),
            ("chunks", json_text(&json!(bounded))),
        ]) + "\n"
    } else {
        let mut lines = profile_context_lines(&profile);
        if archives != 0 {
            lines.extend(notices.clone());
        }
        for f in &facts {
            lines.push(format!(
                "{}{}",
                fact_prefix(f),
                f["object"].as_str().unwrap_or("")
            ));
        }
        if archives == 0 {
            lines.extend(notices);
        }
        for chunk in bounded {
            lines.push(format!(
                "[chunk] [{}] {}:{}@{}-{} score={:.6}",
                chunk["status"].as_str().unwrap_or(""),
                chunk["archive_slug"].as_str().unwrap_or(""),
                chunk["relative_path"].as_str().unwrap_or(""),
                chunk["byte_start"],
                chunk["byte_end"],
                chunk["score"].as_f64().unwrap_or(0.0)
            ));
            for line in splitlines(chunk["snippet"].as_str().unwrap_or("")) {
                lines.push(format!("  {line}"));
            }
        }
        if lines.is_empty() {
            String::new()
        } else {
            lines.join("\n") + "\n"
        }
    };
    let stderr = if embedding.is_some() {
        VEC_NOTICE.into()
    } else if connection.vec_available {
        String::new()
    } else {
        format!(
            "sqlite-vec unavailable, FTS5-only mode: {}\n",
            connection.vec_reason
        )
    };
    Ok((0, out.into_bytes(), stderr.into_bytes()))
}
fn splitlines(s: &str) -> Vec<&str> {
    let mut lines = s
        .split([
            '\n', '\r', '\u{b}', '\u{c}', '\u{1c}', '\u{1d}', '\u{1e}', '\u{85}', '\u{2028}',
            '\u{2029}',
        ])
        .collect::<Vec<_>>();
    if lines.last() == Some(&"") {
        lines.pop();
    }
    lines
}
fn indented_len(s: &str) -> usize {
    let lines = splitlines(s);
    if lines.is_empty() {
        2
    } else {
        lines.iter().map(|s| s.len() + 2).sum::<usize>() + lines.len() - 1
    }
}

fn python_int_repr(value: &str) -> String {
    let mut quoted = crate::executor_execute::repr(value);
    // Unicode 16 additions were unassigned (and therefore escaped by repr) in Python 3.12.
    for c in value.chars().filter(|c| {
        matches!(*c as u32,
        0x10d40..=0x10d49 | 0x116d0..=0x116e3 | 0x11bf0..=0x11bf9
        | 0x16130..=0x16139 | 0x16d70..=0x16d79 | 0x1ccf0..=0x1ccf9 | 0x1e5f1..=0x1e5fa)
    }) {
        quoted = quoted.replace(c, &format!("\\U{:08x}", c as u32));
    }
    quoted
}
pub(super) fn python_k(value: &str) -> Option<Option<i64>> {
    let value = value.trim_matches(char::is_whitespace);
    let (negative, value) = if let Some(v) = value.strip_prefix('-') {
        (true, v)
    } else {
        (false, value.strip_prefix('+').unwrap_or(value))
    };
    let mut text = String::new();
    let mut digit = false;
    for c in value.chars() {
        if c == '_' {
            if !digit {
                return None;
            }
            digit = false;
        } else {
            text.push(char::from(
                b'0' + if matches!(c as u32, 0x10d40..=0x10d49 | 0x116d0..=0x116e3
                    | 0x11bf0..=0x11bf9 | 0x16130..=0x16139 | 0x16d70..=0x16d79
                    | 0x1ccf0..=0x1ccf9 | 0x1e5f1..=0x1e5fa)
                {
                    return None;
                } else {
                    crate::python_decimal::decimal_digit(c)? as u8
                },
            ));
            digit = true;
        }
    }
    // CPython limits decimal conversion to 4300 digits, excluding underscores/sign.
    if !digit || text.len() > 4300 {
        return None;
    }
    if negative {
        text.insert(0, '-');
    }
    Some(text.parse::<i64>().ok())
}
