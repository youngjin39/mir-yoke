//! Content, immutable memory and native phase-2 evidence, without caller wiring.
use super::*;
use crate::mir_core::{memory::distill::sanitize_fts_query, yaml};
use rusqlite::{Connection, OpenFlags, params_from_iter, types::Value as SqlValue};

pub const LAYER_KEYS: [&str; 4] = ["l1", "l2", "l3", "l4"];
pub const COUNT_KEYS: [&str; 5] = ["total", "filled", "derived", "na", "tbd"];
pub const REVIEW_KEYS: [&str; 5] = [
    "project_structure",
    "memory",
    "discoverability",
    "requirements",
    "organization",
];

/// Mirrors sqlite3.connect(uri, uri=True); flags are observable to injected hosts.
pub struct SqliteRequest {
    pub uri: String,
    pub uri_mode: bool,
    pub read_only: bool,
}
pub trait MemoryConnection {
    fn execute(&mut self, sql: &str, params: &[Value]) -> Result<Vec<Vec<Value>>, String>;
}
struct SqliteConnection(Connection);
impl MemoryConnection for SqliteConnection {
    fn execute(&mut self, sql: &str, params: &[Value]) -> Result<Vec<Vec<Value>>, String> {
        let parameters = params
            .iter()
            .map(|v| match v {
                Value::Null => Ok(SqlValue::Null),
                Value::String(s) => Ok(SqlValue::Text(s.clone())),
                _ => Err("unsupported SQLite parameter".to_string()),
            })
            .collect::<Result<Vec<_>, _>>()?;
        let run = || -> rusqlite::Result<Vec<Vec<Value>>> {
            let mut statement = self.0.prepare(sql)?;
            let width = statement.column_count();
            let rows = statement.query_map(params_from_iter(parameters), |row| {
                (0..width)
                    .map(|i| {
                        Ok(match row.get::<_, SqlValue>(i)? {
                            SqlValue::Null => Value::Null,
                            SqlValue::Integer(n) => json!(n),
                            SqlValue::Real(n) => json!(n),
                            SqlValue::Text(s) => json!(s),
                            SqlValue::Blob(b) => json!(b),
                        })
                    })
                    .collect()
            })?;
            rows.collect()
        };
        run().map_err(sqlite_message)
    }
}
fn sqlite_message(error: rusqlite::Error) -> String {
    match error {
        rusqlite::Error::SqliteFailure(_, Some(message)) => message,
        // Python exposes sqlite3_errmsg, not rusqlite's SQL/offset annotation.
        rusqlite::Error::SqlInputError { msg, .. } => msg,
        other => other.to_string(),
    }
}
pub fn open_memory(request: &SqliteRequest) -> Result<Box<dyn MemoryConnection>, String> {
    let mut flags = OpenFlags::SQLITE_OPEN_NO_MUTEX;
    flags |= if request.read_only {
        OpenFlags::SQLITE_OPEN_READ_ONLY
    } else {
        OpenFlags::SQLITE_OPEN_READ_WRITE | OpenFlags::SQLITE_OPEN_CREATE
    };
    if request.uri_mode {
        flags |= OpenFlags::SQLITE_OPEN_URI;
    }
    Connection::open_with_flags(&request.uri, flags)
        .map(|c| Box::new(SqliteConnection(c)) as Box<dyn MemoryConnection>)
        .map_err(sqlite_message)
}

pub(crate) const TEXT_EXTENSIONS: &[&str] =
    &["md", "txt", "rst", "json", "yaml", "yml", "toml", "csv"];
const OTHER_EXTENSIONS: &[&str] = &[
    "doc", "docx", "htm", "html", "odt", "pages", "pdf", "ppt", "pptx", "rtf", "xls", "xlsx",
];
const SCAN_EXCLUDES: &[&str] = &[
    "app",
    "config",
    "docs",
    "examples",
    "global-rules",
    "lib",
    "plugins",
    "scripts",
    "spec",
    "src",
    "tasks",
    "tests",
    "tools",
    "AGENTS.md",
    "ARCHITECTURE.md",
    "BOOTSTRAP.md",
    "CHANGELOG.md",
    "CLAUDE.md",
    "CONTRIBUTING.md",
    "MIGRATION.md",
    "README.md",
    "SECURITY.md",
    "harness_a.toml",
    "llms.txt",
    "pyproject.toml",
    "template_protected_paths.yaml",
    "uv.lock",
];
fn sorted_children_typed(path: &Path) -> Result<Vec<PathBuf>, Error> {
    let mut children = fs::read_dir(path)
        .map_err(|e| io_error(path, e))?
        .map(|entry| entry.map(|e| e.path()))
        .collect::<io::Result<Vec<_>>>()
        .map_err(|e| io_error(path, e))?;
    children.sort();
    Ok(children)
}
pub(crate) fn discover_content_typed(
    root: &Path,
    path: &Path,
    files: &mut Vec<PathBuf>,
) -> Result<(), Error> {
    if path.is_symlink() {
        return Err(adoption(format!(
            "content archive contains a symlink: {}",
            wire(path.strip_prefix(root).unwrap_or(path))
        )));
    }
    if path.is_file() {
        let ext = path
            .extension()
            .and_then(|s| s.to_str())
            .unwrap_or("")
            .to_lowercase();
        if TEXT_EXTENSIONS.contains(&ext.as_str()) || OTHER_EXTENSIONS.contains(&ext.as_str()) {
            files.push(path.into());
        }
    } else if path.is_dir() {
        for child in sorted_children_typed(path)? {
            discover_content_typed(root, &child, files)?;
        }
    }
    Ok(())
}
pub fn scan_content_candidates(root: &Path) -> Result<Vec<Value>, String> {
    scan_content_candidates_typed(root).map_err(|error| error.to_string())
}
pub(crate) fn scan_content_candidates_typed(root: &Path) -> Result<Vec<Value>, Error> {
    let mut candidates = Vec::new();
    for child in sorted_children_typed(root)? {
        let name = child.file_name().and_then(|s| s.to_str()).unwrap_or("");
        if name.starts_with('.') || SCAN_EXCLUDES.contains(&name) {
            continue;
        }
        if child.is_symlink() {
            return Err(adoption(format!(
                "content archive path must not be a symlink: {name}"
            )));
        }
        let mut files = Vec::new();
        discover_content_typed(root, &child, &mut files)?;
        if files.is_empty() {
            continue;
        }
        let formats: BTreeSet<_> = files
            .iter()
            .filter_map(|p| p.extension().and_then(|s| s.to_str()))
            .map(str::to_lowercase)
            .collect();
        candidates.push(json!({"path":name,
            "kind":if child.is_dir(){"directory"}else{"file"},
            "formats":formats, "document_count":files.len(),
            "memory_indexable":formats.iter().any(|s| TEXT_EXTENSIONS.contains(&s.as_str()))}));
    }
    Ok(candidates)
}

pub fn validate_content_onboarding(
    root: &Path,
    selected_profile: &Value,
    host: &mut dyn Host,
) -> Result<(Vec<String>, Value), Error> {
    let mut errors = Vec::new();
    let raw = match load_json_bytes(&root.join("config/content-onboarding.json"), host) {
        Ok((raw, _)) => raw,
        Err(Error::Adoption(e)) => return Ok((vec![e.to_string()], json!({}))),
        Err(e) => return Err(e),
    };
    if !py_equal(&raw["schema_version"], &json!(1)) {
        errors.push("config/content-onboarding.json schema_version must be 1".into());
    }
    if raw["profile"] != "content_workspace" {
        errors.push("content onboarding profile must be content_workspace".into());
    }
    if selected_profile != "content_workspace" {
        errors.push("content onboarding is applied to a non-content adoption profile".into());
    }
    let archives = raw["archives"].as_array().filter(|a| !a.is_empty());
    if archives.is_none() {
        errors.push("content onboarding must contain classified archives".into());
    }
    let mut classified = Vec::new();
    for (index, archive) in archives.into_iter().flatten().enumerate() {
        if !archive.is_object() {
            errors.push(format!(
                "content onboarding archives[{index}] must be an object"
            ));
            continue;
        }
        let parse = || -> Result<_, Error> {
            let label = non_placeholder_text(
                &archive["classification"],
                &format!("content onboarding archives[{index}].classification"),
            )?;
            let (path, normalized) = tracked_path(
                root,
                &archive["path"],
                &format!("content onboarding archives[{index}].path"),
            )?;
            Ok((label, path, normalized))
        };
        match parse() {
            Ok((label, path, normalized)) => {
                if !path.exists() {
                    errors.push(format!(
                        "classified content archive is missing: {normalized}"
                    ));
                }
                classified.push((label, normalized));
            }
            Err(Error::Adoption(e)) => errors.push(e.to_string()),
            Err(e) => return Err(e),
        }
    }
    if classified
        .iter()
        .map(|(label, _)| label)
        .collect::<BTreeSet<_>>()
        .len()
        != classified.len()
    {
        errors.push("content onboarding archive classifications must be unique".into());
    }
    if classified
        .iter()
        .map(|(_, path)| path)
        .collect::<BTreeSet<_>>()
        .len()
        != classified.len()
    {
        errors.push("content onboarding archive paths must be unique".into());
    }
    for (index, (_, path)) in classified.iter().enumerate() {
        for (_, other) in &classified[index + 1..] {
            if path != other
                && (Path::new(path).starts_with(other) || Path::new(other).starts_with(path))
            {
                errors.push(format!(
                    "content onboarding archive paths must not overlap: {}, {}",
                    repr(path),
                    repr(other)
                ));
            }
        }
    }
    if !raw["scan"].is_object() {
        errors.push("content onboarding must contain scan evidence".into());
    } else if raw["scan"]["unclassified"] != json!([]) {
        errors.push("content onboarding contains unclassified candidates".into());
    }
    let live = host.scan_content_candidates(root).unwrap_or_else(|e| {
        errors.push(format!("content onboarding live scan failed: {e}"));
        Vec::new()
    });
    let uncovered: Vec<_> = live
        .iter()
        .filter_map(|candidate| {
            let path = candidate["path"].as_str().unwrap_or("");
            (!classified
                .iter()
                .any(|(_, c)| Path::new(path).starts_with(c)))
            .then(|| path.to_string())
        })
        .collect();
    if !uncovered.is_empty() {
        errors.push(format!(
            "content onboarding live scan has unclassified candidates: {}",
            list_repr(&uncovered)
        ));
    }
    let report = json!({"status":status(&errors), "manifest":"config/content-onboarding.json",
        "classifications":classified.iter().map(|(label,path)|
            json!({"classification":label,"path":path})).collect::<Vec<_>>(),
        "unclassified":uncovered});
    Ok((errors, report))
}

const MEMORY_OBJECTS_SQL: &str = "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')";
const MEMORY_QUERY_SQL: &str = concat!(
    "SELECT a.slug, a.root_path, d.relative_path ",
    "FROM external_chunks_fts f ",
    "JOIN external_chunks c ON c.id = f.rowid ",
    "JOIN external_documents d ON d.id = c.document_id ",
    "JOIN external_archives a ON a.id = d.archive_id ",
    "WHERE external_chunks_fts MATCH ? ",
    "AND a.slug = ? AND d.relative_path = ? LIMIT 1"
);
fn memory_uri(path: &Path) -> String {
    let path = wire(path);
    let prefix = if cfg!(windows) && path.starts_with("//") {
        "file:"
    } else if cfg!(windows) {
        "file:///"
    } else {
        "file://"
    };
    let mut uri = prefix.to_string();
    for (index, byte) in path.bytes().enumerate() {
        if byte.is_ascii_alphanumeric()
            || b"/-._~".contains(&byte)
            || (cfg!(windows) && index == 1 && byte == b':')
        {
            uri.push(char::from(byte));
        } else {
            uri.push_str(&format!("%{byte:02X}"));
        }
    }
    format!("{uri}?mode=ro&immutable=1")
}
pub fn validate_memory(
    root: &Path,
    surface: &Value,
    host: &mut dyn Host,
) -> Result<(Vec<String>, Value), Error> {
    let Some(queries) = surface["queries"].as_array().filter(|q| !q.is_empty()) else {
        return Ok((
            vec!["memory_acceptance requires at least one live FTS query".into()],
            json!({"status":"fail", "queries":[]}),
        ));
    };
    let path = root.join(".mir/memory.db");
    if !path.is_file() {
        return Ok((
            vec!["memory database is missing: .mir/memory.db".into()],
            json!({"status":"fail", "queries":[]}),
        ));
    }
    let mut errors = Vec::new();
    let mut results = Vec::new();
    // Drop closes on every exit, including a failed PRAGMA or malformed schema.
    let mut check =
        || -> Result<(), String> {
            let resolved = path
                .canonicalize()
                .map_err(|e| io_error(&path, e).to_string())?;
            let mut db = host.sqlite_open(&SqliteRequest {
                uri: memory_uri(&resolved),
                uri_mode: true,
                read_only: true,
            })?;
            db.execute("PRAGMA query_only = ON", &[])?;
            let objects = db.execute(MEMORY_OBJECTS_SQL, &[])?;
            let missing: Vec<String> = [
                "external_archives",
                "external_documents",
                "external_chunks",
                "external_chunks_fts",
            ]
            .into_iter()
            .filter(|name| !objects.iter().any(|row| row.first() == Some(&json!(name))))
            .map(str::to_string)
            .collect::<BTreeSet<_>>()
            .into_iter()
            .collect();
            if !missing.is_empty() {
                errors.push(format!(
                    "memory FTS tables are missing: {}",
                    list_repr(&missing)
                ));
            } else {
                for (index, spec) in queries.iter().enumerate() {
                    if !spec.is_object() {
                        errors.push(format!(
                            "memory_acceptance queries[{index}] must be an object"
                        ));
                        continue;
                    }
                    let mut values = Vec::new();
                    for key in ["archive_slug", "query", "expected_path"] {
                        match non_placeholder_text(
                            &spec[key],
                            &format!("memory_acceptance queries[{index}].{key}"),
                        ) {
                            Ok(value) => values.push(value),
                            Err(e) => {
                                errors.push(e.to_string());
                                break;
                            }
                        }
                    }
                    if values.len() != 3 {
                        continue;
                    }
                    let (slug, query, expected) = (&values[0], &values[1], &values[2]);
                    let sanitized = sanitize_fts_query(query).map_err(|e| format!("{e:?}"))?;
                    let rows = db.execute(
                        MEMORY_QUERY_SQL,
                        &[json!(sanitized), json!(slug), json!(expected)],
                    )?;
                    let row = rows.first();
                    results.push(json!({"archive_slug":slug, "query":query,
                    "expected_path":expected, "status":if row.is_some(){"pass"}else{"fail"},
                    "live_path":row.and_then(|r|r.get(2)),
                    "archive_root":row.and_then(|r|r.get(1))}));
                    if row.is_none() {
                        errors.push(format!(concat!(
                        "project-specific memory query returned no exact archive/path hit: ",
                        "{} {} -> {}"), repr(slug), repr(query), repr(expected)));
                    }
                }
            }
            Ok(())
        };
    if let Err(e) = check() {
        errors.push(format!("memory read-only FTS check failed: {e}"));
    }
    if !results.iter().any(|r| r["status"] == "pass") {
        errors.push("memory acceptance requires at least one live project-specific FTS hit".into());
    }
    let report = json!({"status":status(&errors), "database":".mir/memory.db",
        "mode":"immutable_read_only", "queries":results});
    Ok((errors, report))
}

// Python numeric equality includes bool == int; count validation excludes bools.
fn py_equal(a: &Value, b: &Value) -> bool {
    match (a, b) {
        (Value::Bool(a), Value::Number(b)) | (Value::Number(b), Value::Bool(a)) => {
            b.as_f64() == Some(if *a { 1.0 } else { 0.0 })
        }
        (Value::Number(a), Value::Number(b)) => a.as_f64() == b.as_f64(),
        (Value::Object(a), Value::Object(b)) => {
            a.len() == b.len()
                && a.iter()
                    .all(|(k, v)| b.get(k).is_some_and(|b| py_equal(v, b)))
        }
        (Value::Array(a), Value::Array(b)) => {
            a.len() == b.len() && a.iter().zip(b).all(|(a, b)| py_equal(a, b))
        }
        _ => a == b,
    }
}
fn exact_keys(value: &Value, keys: &[&str]) -> bool {
    value
        .as_object()
        .is_some_and(|o| o.len() == keys.len() && keys.iter().all(|k| o.contains_key(*k)))
}
fn counts(value: &Value) -> Value {
    Value::Object(
        COUNT_KEYS
            .iter()
            .map(|k| ((*k).into(), value[*k].clone()))
            .collect(),
    )
}

/// Construct JSON-compatible safe YAML using the existing YAML 1.1 composer.
/// Mappings use last-key-wins, as yaml.safe_load does for ordinary mappings.
fn yaml_value(
    doc: &yaml::Node,
    index: usize,
    active: &mut BTreeSet<usize>,
) -> Result<Value, String> {
    if !active.insert(index) {
        return Err("recursive YAML evidence".into());
    }
    let node = &doc.arena[index];
    let value = match &node.kind {
        yaml::Kind::Sequence(items) => Value::Array(
            items
                .iter()
                .map(|i| yaml_value(doc, *i, active))
                .collect::<Result<_, _>>()?,
        ),
        yaml::Kind::Mapping(items) => {
            let mut result = Map::new();
            for (k, v) in items {
                let key = yaml_value(doc, *k, active)?;
                let key = key
                    .as_str()
                    .map(str::to_string)
                    .unwrap_or_else(|| value_repr(&key));
                result.insert(key, yaml_value(doc, *v, active)?);
            }
            Value::Object(result)
        }
        yaml::Kind::Scalar(s) => match node.tag.as_str() {
            "tag:yaml.org,2002:null" => Value::Null,
            "tag:yaml.org,2002:bool" => {
                json!(matches!(s.to_lowercase().as_str(), "true" | "yes" | "on"))
            }
            "tag:yaml.org,2002:int" => {
                let text = s.replace('_', "");
                let (negative, text) = if let Some(s) = text.strip_prefix('-') {
                    (true, s)
                } else {
                    (false, text.strip_prefix('+').unwrap_or(&text))
                };
                let parsed = if let Some(s) = text.strip_prefix("0x") {
                    i64::from_str_radix(s, 16)
                } else if let Some(s) = text.strip_prefix("0b") {
                    i64::from_str_radix(s, 2)
                } else if text.len() > 1 && text.starts_with('0') {
                    i64::from_str_radix(text, 8)
                } else {
                    text.parse::<i64>()
                };
                json!(
                    parsed
                        .map(|n| if negative { -n } else { n })
                        .map_err(|e| e.to_string())?
                )
            }
            "tag:yaml.org,2002:float" => json!(
                s.replace('_', "")
                    .parse::<f64>()
                    .map_err(|e| e.to_string())?
            ),
            "tag:yaml.org,2002:str" | "tag:yaml.org,2002:timestamp" => json!(s),
            tag => {
                return Err(format!(
                    "could not determine a constructor for the tag {tag:?}"
                ));
            }
        },
    };
    active.remove(&index);
    Ok(value)
}
fn load_yaml(text: &str) -> Result<Value, String> {
    // The composer's error preserves class but lacks PyYAML's marked diagnostics.
    // Render the unterminated flow sequence diagnostic from its source location.
    let doc = yaml::compose(yaml::Input::Text(text)).map_err(|e| {
        if text.trim_matches(is_python_space) == "[" {
            let column = text.find('[').unwrap_or(0);
            format!(
                concat!(
                    "while parsing a flow node\n",
                    "expected the node content, but found '<stream end>'\n",
                    "  in \"<unicode string>\", line 1, column {}:\n",
                    "    {}\n    {}^"
                ),
                text.chars().count() + 1,
                text,
                " ".repeat(column + 1)
            )
        } else {
            e.message
        }
    })?;
    doc.map(|doc| yaml_value(&doc, doc.root, &mut BTreeSet::new()))
        .unwrap_or(Ok(Value::Null))
}

pub fn validate_phase2(
    root: &Path,
    surface: &Value,
    host: &mut dyn Host,
) -> Result<(Vec<String>, Value), Error> {
    let mut errors = Vec::new();
    let mut coverage = surface["coverage"].clone();
    if !coverage.is_object() {
        errors.push("phase2_spec requires four-layer coverage".into());
        coverage = json!({});
    } else if !exact_keys(&coverage, &LAYER_KEYS) {
        errors.push("phase2_spec coverage must contain exactly l1, l2, l3, and l4".into());
    }
    for layer in LAYER_KEYS {
        let row = &coverage[layer];
        if !row.is_object() {
            errors.push(format!("phase2_spec coverage is missing {layer}"));
            continue;
        }
        let values = COUNT_KEYS.map(|k| row[k].as_u64());
        if values.iter().any(Option::is_none) {
            errors.push(format!(
                "phase2_spec coverage {layer} counts must be non-negative integers"
            ));
            continue;
        }
        let values = values.map(|v| u128::from(v.unwrap_or(0)));
        if values[0] == 0 {
            errors.push(format!(
                "phase2_spec coverage {layer}.total must be greater than zero"
            ));
        }
        if values[1..].iter().sum::<u128>() != values[0] {
            errors.push(format!(
                "phase2_spec coverage {layer} counts do not sum to total"
            ));
        }
        if values[4] != 0 {
            errors.push(format!(
                "phase2_spec coverage {layer} has unresolved TBD items"
            ));
        }
    }
    let mut ai_ready = surface["ai_ready"].clone();
    if !ai_ready.is_object() {
        errors.push("phase2_spec requires ai_ready counts".into());
        ai_ready = json!({});
    } else {
        let values = ["ready", "incomplete", "blocked"].map(|k| ai_ready[k].as_u64());
        if values.iter().any(Option::is_none) {
            errors.push("phase2_spec ai_ready counts must be non-negative integers".into());
        } else if values[0] == Some(0) || values[1] != Some(0) || values[2] != Some(0) {
            errors.push("phase2_spec ai_ready requires ready>0 and incomplete=blocked=0".into());
        }
    }
    if !py_equal(&surface["open_gaps"], &json!(0)) {
        errors.push("phase2_spec open_gaps must equal zero".into());
    }
    let full_review = &surface["full_review"];
    if !exact_keys(full_review, &REVIEW_KEYS) {
        errors.push("phase2_spec full_review must contain exactly five review keys".into());
    } else if REVIEW_KEYS.iter().any(|k| full_review[*k] != "pass") {
        errors.push("phase2_spec full_review must pass every review key".into());
    }
    let native = &surface["native_evidence"];
    let mut native_report = json!({"status":"fail"});
    let declared = surface["evidence_paths"]
        .as_array()
        .cloned()
        .unwrap_or_default();
    if !native.is_object() {
        errors.push("phase2_spec requires native_evidence field mappings".into());
    } else {
        if !exact_keys(
            native,
            &[
                "format",
                "meta_path",
                "coverage_key",
                "gaps_path",
                "review_path",
            ],
        ) {
            errors.push(
                concat!(
                    "phase2_spec native_evidence must contain exactly format, ",
                    "meta_path, coverage_key, gaps_path, and review_path"
                )
                .into(),
            );
        }
        if native["format"] != "mir_spec_yaml_v1" {
            errors.push("phase2_spec native_evidence format must be mir_spec_yaml_v1".into());
        }
        let coverage_key = &native["coverage_key"];
        if coverage_key != "coverage" && coverage_key != "completeness" {
            errors.push(
                concat!(
                    "phase2_spec native_evidence coverage_key must be ",
                    "coverage or completeness"
                )
                .into(),
            );
        }
        let mut documents = json!({});
        let mut paths = json!({});
        for field in ["meta_path", "gaps_path", "review_path"] {
            let (path, normalized) = match tracked_path(
                root,
                &native[field],
                &format!("phase2_spec native_evidence.{field}"),
            ) {
                Ok(pair) => pair,
                Err(Error::Adoption(e)) => {
                    errors.push(e.to_string());
                    continue;
                }
                Err(e) => return Err(e),
            };
            paths[field] = json!(normalized);
            if !declared.contains(&json!(normalized)) {
                errors.push(format!(
                    "phase2_spec native evidence must be listed in evidence_paths: {normalized}"
                ));
            }
            let document = match read_text(&path, host)
                .map_err(|e| e.to_string())
                .and_then(|text| load_yaml(&text))
            {
                Ok(doc) => doc,
                Err(e) => {
                    errors.push(format!(
                        "phase2_spec native evidence is unreadable: {normalized}: {e}"
                    ));
                    continue;
                }
            };
            if !document.is_object() {
                errors.push(format!(
                    "phase2_spec native evidence must contain a mapping: {normalized}"
                ));
                continue;
            }
            documents[field] = document;
        }
        let meta = &documents["meta_path"];
        let native_coverage = coverage_key.as_str().and_then(|k| meta.get(k));
        if let Some(native_coverage) = native_coverage.filter(|v| v.is_object()) {
            for layer in LAYER_KEYS {
                let native_row = &native_coverage[layer];
                if !native_row.is_object() {
                    errors.push(format!("phase2_spec native coverage is missing {layer}"));
                    continue;
                }
                let manifest_counts = if coverage[layer].is_object() {
                    counts(&coverage[layer])
                } else {
                    Value::Null
                };
                if !py_equal(&counts(native_row), &manifest_counts) {
                    errors.push(format!(
                        "phase2_spec manifest coverage {layer} does not match native evidence"
                    ));
                }
            }
        } else {
            errors.push(format!(
                "phase2_spec native meta is missing mapped coverage key {}",
                value_repr(coverage_key)
            ));
        }
        if !py_equal(&meta["ai_ready"], &ai_ready) {
            errors.push("phase2_spec manifest ai_ready does not match native evidence".into());
        }
        let gaps = &documents["gaps_path"]["gaps"];
        if let Some(gaps) = gaps.as_array() {
            if !py_equal(&json!(gaps.len()), &surface["open_gaps"]) {
                errors.push("phase2_spec manifest open_gaps does not match native evidence".into());
            }
        } else {
            errors.push("phase2_spec native gaps evidence must contain a gaps array".into());
        }
        let reviews = &documents["review_path"]["reviews"];
        let mut statuses = json!({});
        let mut review_evidence = json!({});
        if !exact_keys(reviews, &REVIEW_KEYS) {
            errors.push(
                concat!(
                    "phase2_spec native review evidence must contain exactly ",
                    "five review dimensions"
                )
                .into(),
            );
        } else {
            for dimension in REVIEW_KEYS {
                let row = &reviews[dimension];
                if !exact_keys(row, &["status", "evidence_paths", "verification"]) {
                    errors.push(format!(
                        concat!(
                            "phase2_spec native review dimension must contain exactly status, ",
                            "evidence_paths, and verification: {}"
                        ),
                        dimension
                    ));
                    continue;
                }
                statuses[dimension] = row["status"].clone();
                let evidence = row["evidence_paths"].as_array().filter(|paths| {
                    !paths.is_empty()
                        && paths.iter().map(value_repr).collect::<BTreeSet<_>>().len()
                            == paths.len()
                });
                if evidence.is_none() {
                    errors.push(format!(
                        "phase2_spec native review {dimension} requires unique evidence_paths"
                    ));
                }
                let mut verified = Vec::new();
                for path in evidence.into_iter().flatten() {
                    let normalized = match tracked_path(
                        root,
                        path,
                        &format!("phase2_spec native review {dimension} evidence"),
                    ) {
                        Ok((_, normalized)) => normalized,
                        Err(Error::Adoption(e)) => {
                            errors.push(e.to_string());
                            continue;
                        }
                        Err(e) => return Err(e),
                    };
                    if !declared.contains(&json!(normalized)) {
                        errors.push(format!(
                            concat!(
                                "phase2_spec native review evidence must be listed in ",
                                "evidence_paths: {}"
                            ),
                            normalized
                        ));
                    }
                    verified.push(normalized);
                }
                let verification = non_placeholder_text(
                    &row["verification"],
                    &format!("phase2_spec native review {dimension}.verification"),
                )
                .unwrap_or_else(|e| {
                    errors.push(e.to_string());
                    String::new()
                });
                review_evidence[dimension] = json!({"status":row["status"],
                    "evidence_paths":verified,"verification":verification});
            }
        }
        if !py_equal(&statuses, full_review) {
            errors.push("phase2_spec full_review does not match native review evidence".into());
        }
        native_report = json!({"status":status(&errors),"format":native["format"],
            "paths":paths,"reviews":review_evidence});
    }
    for relative in &declared {
        let text = relative
            .as_str()
            .map(str::to_string)
            .unwrap_or_else(|| value_repr(relative));
        let Ok(body) = read_text(&root.join(&text), host) else {
            continue;
        };
        if body.trim_matches(is_python_space).is_empty() {
            errors.push(format!("phase2_spec evidence is empty: {text}"));
        } else if !native_report["paths"]
            .as_object()
            .is_some_and(|p| p.values().any(|v| v == relative))
            && contains_unresolved_placeholder(&body)
        {
            errors.push(format!(
                "phase2_spec evidence contains placeholder text: {text}"
            ));
        }
    }
    let report = json!({"status":status(&errors),"coverage":coverage,"ai_ready":ai_ready,
        "open_gaps":surface["open_gaps"],"full_review":full_review,
        "native_evidence":native_report,"exceptions":[]});
    Ok((errors, report))
}
