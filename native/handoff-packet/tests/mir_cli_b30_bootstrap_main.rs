//! Frozen B30 main replay, including real helpers in both synthetic end-to-end cells.
#![forbid(unsafe_code)]
use handoff_packet::mir_cli::bootstrap::{self as m, Error, Host};
use rusqlite::{Connection, types::ValueRef};
use serde_json::{Value, json};
use std::{
    collections::BTreeMap,
    fs,
    path::{Path, PathBuf},
};
#[path = "../src/digest.rs"]
mod digest;

fn put(root: &Path, name: &str, body: impl AsRef<[u8]>) {
    let path = root.join(name);
    fs::create_dir_all(path.parent().unwrap()).unwrap();
    fs::write(path, body).unwrap();
}
fn py_json(value: &Value) -> String {
    match value {
        Value::Array(items) => format!(
            "[{}]",
            items.iter().map(py_json).collect::<Vec<_>>().join(", ")
        ),
        Value::Object(items) => {
            let items: BTreeMap<_, _> = items.iter().collect();
            format!(
                "{{{}}}",
                items
                    .into_iter()
                    .map(|(key, value)| format!("{}: {}", py_json(&json!(key)), py_json(value)))
                    .collect::<Vec<_>>()
                    .join(", ")
            )
        }
        _ => value
            .to_string()
            .chars()
            .map(|ch| {
                if ch.is_ascii() {
                    ch.to_string()
                } else {
                    ch.encode_utf16(&mut [0; 2])
                        .iter()
                        .map(|unit| format!("\\u{unit:04x}"))
                        .collect()
                }
            })
            .collect(),
    }
}
fn compact(value: Value, root: &Path) -> Value {
    match value {
        Value::String(body) => {
            #[cfg(windows)]
            let body = windows_paths(&body, root.to_str().unwrap());
            #[cfg(not(windows))]
            let body = body.replace(root.to_str().unwrap(), "<tmp>");
            let len = body.chars().count();
            if len > 512 {
                json!({"len":len,"sha256":digest::sha256(body.as_bytes())})
            } else {
                json!(body)
            }
        }
        Value::Array(items) => {
            Value::Array(items.into_iter().map(|item| compact(item, root)).collect())
        }
        Value::Object(items) => Value::Object(
            items
                .into_iter()
                .map(|(key, item)| (key, compact(item, root)))
                .collect(),
        ),
        value => value,
    }
}
#[cfg(windows)]
fn windows_paths(body: &str, root: &str) -> String {
    // JSON output embeds escaped paths; preserve every unrelated JSON escape and space.
    let ordinary = root.trim_start_matches("\\\\?\\");
    let mut roots = vec![root.into(), ordinary.into(), ordinary.replace('\\', "/")];
    roots.extend(roots.clone().into_iter().map(|path: String| {
        let escaped = serde_json::to_string(&path).unwrap();
        escaped[1..escaped.len() - 1].to_owned()
    }));
    roots.sort_by_key(|path| std::cmp::Reverse(path.len()));
    let mut text = body.to_owned();
    for path in roots {
        text = text.replace(&path, "<tmp>");
    }
    text.split("<tmp>")
        .enumerate()
        .map(|(index, part)| {
            if index == 0 {
                return part.to_owned();
            }
            let end = part
                .find(|ch: char| {
                    ch.is_whitespace() || ['"', '\'', ',', ')', ']', '}'].contains(&ch)
                })
                .unwrap_or(part.len());
            format!(
                "<tmp>{}{}",
                part[..end].replace("\\\\", "/").replace('\\', "/"),
                &part[end..]
            )
        })
        .collect()
}
fn query(db: &Connection, sql: &str) -> Value {
    let mut statement = db.prepare(sql).unwrap();
    let columns = statement.column_count();
    let rows = statement
        .query_map([], |row| {
            Ok(Value::Array(
                (0..columns)
                    .map(|index| match row.get_ref(index).unwrap() {
                        ValueRef::Null => Value::Null,
                        ValueRef::Integer(value) => json!(value),
                        ValueRef::Real(value) => json!(value),
                        ValueRef::Text(value) => json!(std::str::from_utf8(value).unwrap()),
                        ValueRef::Blob(_) => panic!("unexpected blob in bootstrap database"),
                    })
                    .collect(),
            ))
        })
        .unwrap()
        .collect::<Result<Vec<_>, _>>()
        .unwrap();
    json!(rows)
}
fn files(root: &Path, current: &Path, result: &mut BTreeMap<String, Value>) {
    let mut paths = fs::read_dir(current)
        .unwrap()
        .map(|entry| entry.unwrap().path())
        .collect::<Vec<_>>();
    paths.sort();
    for path in paths {
        if path.is_dir() {
            files(root, &path, result);
            continue;
        }
        let name = path.file_name().unwrap().to_str().unwrap();
        if !path.is_file() || name.ends_with("-wal") || name.ends_with("-shm") {
            continue;
        }
        let body = if path.extension().is_some_and(|extension| extension == "db") {
            let db = Connection::open(&path).unwrap();
            py_json(&json!([
                [
                    query(&db, "PRAGMA journal_mode"),
                    query(&db, "PRAGMA user_version"),
                    query(&db, "PRAGMA schema_version")
                ],
                query(
                    &db,
                    "SELECT version,name FROM schema_migrations ORDER BY version"
                ),
                query(
                    &db,
                    concat!(
                        "SELECT type,name,tbl_name,sql FROM sqlite_master ",
                        "ORDER BY type,name,tbl_name,sql"
                    )
                )
            ]))
        } else {
            let body = fs::read_to_string(&path).unwrap();
            #[cfg(windows)]
            let body = body.replace("\r\n", "\n");
            body
        };
        result.insert(
            path.strip_prefix(root)
                .unwrap()
                .to_str()
                .unwrap()
                .replace('\\', "/"),
            json!(body),
        );
    }
}

#[test]
fn replay_all_116_frozen_records() {
    let records: BTreeMap<String, Value> =
        serde_json::from_str(include_str!("fixtures/w2/b30-bootstrap-main.json")).unwrap();
    assert_eq!(records.len(), 116);
    let mut failures = Vec::new();
    let mut replayed = 0;
    for (name, expected) in records {
        let temp = tempfile::tempdir_in(std::env::temp_dir()).unwrap();
        let root = temp.path().canonicalize().unwrap();
        let actual = replay(&root, &name);
        replayed += 1;
        eprintln!("REPLAY {name}");
        if actual != expected {
            failures.push(format!("{name}\nactual: {actual}\nexpected: {expected}"));
        }
    }
    assert_eq!(replayed, 116);
    eprintln!("B30 bootstrap main: replayed={replayed}, exempt=0, total=116");
    assert!(failures.is_empty(), "{}", failures.join("\n"));
}
struct BoundaryHost {
    root: PathBuf,
    mode: String,
    scenario: String,
    calls: Vec<Value>,
}
impl BoundaryHost {
    fn new(root: &Path, mode: &str, scenario: Option<&str>) -> Self {
        Self {
            root: root.into(),
            mode: mode.into(),
            scenario: scenario.unwrap_or("").into(),
            calls: vec![],
        }
    }
}
impl Host for BoundaryHost {
    fn env(&mut self, name: &str) -> Option<String> {
        match name {
            "HOME" | "TMPDIR" => Some(self.root.to_str().unwrap().into()),
            "VIRTUAL_ENV" if self.scenario != "no_venv" => Some(self.root.to_str().unwrap().into()),
            "MIR_BOOTSTRAP_CLI_PATH" if self.scenario.starts_with("cli_") => {
                Some(self.root.join("cli").to_str().unwrap().into())
            }
            "MIR_BOOTSTRAP_RUNTIME_MANIFEST" if self.scenario == "cli_manifest" => {
                Some(self.root.join("manifest.json").to_str().unwrap().into())
            }
            _ => None,
        }
    }
    fn which(&mut self, name: &str) -> Option<PathBuf> {
        Some(self.root.join(name))
    }
    fn resolve(&mut self, path: &Path) -> Result<PathBuf, Error> {
        assert!(
            path.starts_with(&self.root),
            "resolve outside root: {path:?}"
        );
        Ok(path.into())
    }
    fn expanduser(&mut self, path: &Path) -> Result<PathBuf, Error> {
        Ok(if path == Path::new("~") {
            self.root.clone()
        } else {
            path.into()
        })
    }
    fn is_dir(&mut self, path: &Path) -> bool {
        assert!(path.starts_with(&self.root));
        path.is_dir()
    }
    fn writable(&mut self, path: &Path) -> bool {
        assert!(path.starts_with(&self.root));
        true
    }
    fn device(&mut self, path: &Path) -> Result<u64, Error> {
        assert!(path.starts_with(&self.root));
        Ok(1)
    }
    fn run(&mut self, request: &m::CommandRequest) -> Result<m::CommandOutput, Error> {
        assert_eq!(request.cwd, self.root);
        assert!(request.environment.is_empty());
        assert!(request.stdin_null);
        self.calls
            .push(json!([request.argv, request.cwd, null, -3]));
        Ok(m::CommandOutput {
            returncode: 0,
            stdout: vec![],
            stderr: vec![],
        })
    }
    fn cwd(&mut self) -> Result<PathBuf, Error> {
        Ok(self.root.clone())
    }
    fn platform_system(&mut self) -> String {
        if self.mode == "windows" || self.scenario == "help_windows" {
            "Windows"
        } else if self.mode == "platform" {
            "Other"
        } else {
            "Linux"
        }
        .into()
    }
    fn platform_release(&mut self) -> Result<String, Error> {
        if self.scenario == "uname_failure" {
            return Err(Error::new("OSError", "uname failed"));
        }
        Ok("test".into())
    }
    fn python_version(&mut self) -> String {
        "test".into()
    }
    fn in_virtualenv(&mut self) -> bool {
        self.scenario != "no_venv"
    }
    fn python_argv0(&mut self) -> PathBuf {
        self.root.join("mir")
    }
    fn now_iso(&mut self) -> Result<String, Error> {
        Ok("fixed".into())
    }
}
struct Observer {
    boundary: BoundaryHost,
    helpers: Vec<Value>,
}
impl Observer {
    fn scripted(&mut self, name: &str) -> Option<Result<Value, Error>> {
        if self.boundary.mode == "synthetic_e2e" {
            return None;
        }
        let mode = self.boundary.mode.as_str();
        let scenario = self.boundary.scenario.as_str();
        let refusal = match name {
            "_source_control_ownership" if mode == "ownership" => Some("ownership"),
            "_storage_preflight" if mode == "storage" => Some("storage"),
            "_validate_project_identity" if mode == "identity" => Some("identity"),
            "_validate_surfaces" if mode == "surface" => Some("surface"),
            "_validate_architecture_evidence" if mode == "architecture" => Some("architecture"),
            "_validate_content_memory_acceptance" if mode == "acceptance" => Some("acceptance"),
            _ => None,
        };
        let failure = match name {
            "_validate_existing_profile" if mode == "existing" => Some(("ValueError", "existing")),
            "_build_content_onboarding" if mode == "onboarding" => {
                Some(("ValueError", "onboarding"))
            }
            "_build_projection_updates" if mode == "projection" => {
                Some(("ValueError", "projection"))
            }
            "load_config" if scenario == "harness_invalid" => Some(("ConfigLoadError", "harness")),
            "apply_adopter_slim" if mode == "slim" => Some(("SlimError", "slim")),
            "commit_adopter_slim" if mode == "commit" => Some(("SlimError", "commit")),
            "rollback_adopter_slim" if scenario == "rollback_failure" => {
                Some(("SlimError", "rollback"))
            }
            _ => None,
        };
        self.helpers.push(json!(name));
        if let Some((class, message)) = failure {
            let message = if matches!(message, "slim" | "commit") {
                message.into()
            } else {
                format!("{message} refused")
            };
            return Some(Err(Error::new(class, message)));
        }
        let errors = if scenario == "dup_errors"
            && matches!(name, "_storage_preflight" | "_validate_surfaces")
        {
            vec!["shared refused".to_string()]
        } else {
            refusal
                .map(|message| vec![format!("{message} refused")])
                .unwrap_or_default()
        };
        let profile = json!({"repo":{"purpose":"Build tools","technology_stack":["Rust"]}});
        Some(Ok(match name {
            "_source_control_ownership"
            | "_storage_preflight"
            | "_validate_surfaces"
            | "_validate_architecture_evidence"
            | "_validate_content_memory_acceptance" => json!([errors, {}]),
            "_validate_project_identity" => json!(errors),
            "load_profile" => profile,
            "load_boundary" | "_load_capability_sources" => json!({}),
            "is_provider_owner" => json!(mode == "provider"),
            "_is_raw_provider_checkout" => json!(mode == "raw"),
            "_validate_existing_profile" => {
                let mut profile = profile;
                if scenario == "profile_purpose" {
                    profile["repo"]["purpose"] = json!("Other purpose");
                }
                if scenario == "profile_stack" {
                    profile["repo"]["technology_stack"] = json!(["Python"]);
                }
                profile
            }
            "load_config" => json!({"memory":{"enabled":mode != "disabled","required":true,
            "vector_mode":match scenario {
                "vector_required" => "required",
                "optional_vector" => "optional",
                _ => "off",
            }}}),
            "resolve_memory_db" => json!(self.boundary.root.join(".mir/memory.db")),
            "_activate_capabilities" if scenario == "reason_missing" => json!(["failed", {}]),
            "_activate_capabilities" | "_finalize_capabilities" => {
                if (name == "_activate_capabilities" && mode == "activation")
                    || (name == "_finalize_capabilities" && mode == "finalize_failure")
                {
                    json!(["failed",{"reason":if mode == "activation" {
                        "activation refused"
                    } else { "finalize refused" }}])
                } else {
                    json!(["ready", {}])
                }
            }
            "apply_adopter_slim" => {
                if scenario == "slim_applied" {
                    for path in [".mir/slim.lock", ".mir/slim-transaction.json"] {
                        put(&self.boundary.root, path, "{}");
                    }
                    json!({"status":"applied"})
                } else {
                    json!({})
                }
            }
            "commit_adopter_slim" | "rollback_adopter_slim" => Value::Null,
            "install_runtime_verifier" => {
                assert_eq!(scenario, "cli_manifest");
                json!({"status":"scripted"})
            }
            "_build_content_onboarding" => {
                let manifest = if scenario == "content_stale" {
                    json!({})
                } else if scenario == "content_unclassified" {
                    json!({"scan":{"unclassified":[{"path":"notes","formats":["md"]}]}})
                } else if scenario.starts_with("content_") {
                    manifest()
                } else {
                    json!({"scan":{"unclassified":[]}})
                };
                json!([
                    manifest,
                    if scenario == "content_unclassified" {
                        ""
                    } else {
                        "Definition"
                    }
                ])
            }
            "_build_projection_updates" => {
                let path = self.boundary.root.join("docs/projection.md");
                json!({path.to_str().unwrap():"Projection"})
            }
            _ => panic!("unscripted helper {name}"),
        }))
    }
}
fn manifest() -> Value {
    json!({"schema_version":1,"profile":"content_workspace","purpose":"Build tools",
        "technology_stack":["Rust"],"archives":[{"classification":"notes","path":"docs"}],
        "scan":{"unclassified":[]}})
}
macro_rules! forward {
    ($name:ident ($($arg:ident: $kind:ty),*) -> $output:ty) => {
        fn $name(&mut self, $($arg: $kind),*) -> $output {
            self.boundary.$name($($arg),*)
        }
    };
}
macro_rules! script {
    ($name:ident, $python:literal, ($($arg:ident: $kind:ty),*) -> $output:ty) => {
        fn $name(&mut self, $($arg: $kind),*) -> Result<$output, Error> {
            if let Some(value) = self.scripted($python) {
                return Ok(serde_json::from_value(value?).unwrap());
            }
            self.boundary.$name($($arg),*)
        }
    };
}
type Evidence = (Vec<String>, Value);
impl Host for Observer {
    fn replace(&mut self, source: &Path, target: &Path) -> Result<(), Error> {
        #[cfg(unix)]
        if self.boundary.scenario == "leaf-race" {
            fs::remove_file(target).unwrap();
            std::os::unix::fs::symlink(self.boundary.root.join("outside"), target).unwrap();
        }
        m::ProductionHost::default().replace(source, target)
    }
    forward!(env(name: &str) -> Option<String>);
    forward!(which(name: &str) -> Option<PathBuf>);
    forward!(resolve(path: &Path) -> Result<PathBuf, Error>);
    forward!(expanduser(path: &Path) -> Result<PathBuf, Error>);
    forward!(is_dir(path: &Path) -> bool);
    forward!(writable(path: &Path) -> bool);
    forward!(device(path: &Path) -> Result<u64, Error>);
    forward!(run(request: &m::CommandRequest) -> Result<m::CommandOutput, Error>);
    forward!(cwd() -> Result<PathBuf, Error>);
    forward!(platform_system() -> String);
    forward!(platform_release() -> Result<String, Error>);
    forward!(python_version() -> String);
    forward!(in_virtualenv() -> bool);
    forward!(python_argv0() -> PathBuf);
    forward!(now_iso() -> Result<String, Error>);
    script!(source_control_ownership, "_source_control_ownership", (root: &Path) -> Evidence);
    script!(storage_preflight, "_storage_preflight",
        (root: &Path, requested: Option<&Path>) -> Evidence);
    script!(validate_surfaces, "_validate_surfaces", (root: &Path) -> Evidence);
    script!(load_capability_sources, "_load_capability_sources",
        (root: &Path, profile: &str) -> Value);
    script!(load_profile, "load_profile", (root: &Path) -> Value);
    script!(load_boundary, "load_boundary", (root: &Path) -> Value);
    script!(validate_existing_profile, "_validate_existing_profile",
        (path: &Path, profile: &str) -> Value);
    script!(is_raw_provider_checkout, "_is_raw_provider_checkout", (root: &Path) -> bool);
    script!(load_config, "load_config", (root: &Path) -> Value);
    script!(resolve_memory_db, "resolve_memory_db", (root: &Path, config: &Value) -> PathBuf);
    script!(build_projection_updates, "_build_projection_updates",
        (root: &Path, db: &Path) -> BTreeMap<PathBuf, String>);
    script!(validate_content_memory_acceptance, "_validate_content_memory_acceptance",
        (root: &Path, db: &Path, slug: &str, onboarding: &Value) -> Evidence);
    fn activate_capabilities(
        &mut self,
        root: &Path,
        profile: &str,
    ) -> Result<(String, handoff_packet::python_json::Value), Error> {
        if let Some(value) = self.carrier() {
            return Ok(value);
        }
        if let Some(value) = self.scripted("_activate_capabilities") {
            let (status, evidence): (String, Value) = serde_json::from_value(value?).unwrap();
            return Ok((
                status,
                handoff_packet::python_json::parse(&evidence.to_string()).unwrap(),
            ));
        }
        self.boundary.activate_capabilities(root, profile)
    }
    script!(validate_architecture_evidence, "_validate_architecture_evidence",
        (root: &Path) -> Evidence);
    script!(build_content_onboarding, "_build_content_onboarding",
        (root: &Path, purpose: &str, stack: &[String], archives: &[String]) -> (Value, String));
    script!(apply_adopter_slim, "apply_adopter_slim",
        (root: &Path, external_cli: &Path, defer_commit: bool) -> Value);
    script!(rollback_adopter_slim, "rollback_adopter_slim",
        (root: &Path, state: &Value) -> ());
    script!(commit_adopter_slim, "commit_adopter_slim", (root: &Path, state: &Value) -> ());
    script!(install_runtime_verifier, "install_runtime_verifier",
        (root: &Path, source: &Path) -> Option<Value>);
    fn finalize_capabilities(
        &mut self,
        root: &Path,
        prior: Option<&Value>,
    ) -> Result<(String, handoff_packet::python_json::Value), Error> {
        if let Some(value) = self.carrier() {
            return Ok(value);
        }
        if let Some(value) = self.scripted("_finalize_capabilities") {
            if self.boundary.scenario == "prior_receipt" {
                self.helpers.push(json!({"prior_receipt":prior}));
            }
            let (status, evidence): (String, Value) = serde_json::from_value(value?).unwrap();
            return Ok((
                status,
                handoff_packet::python_json::parse(&evidence.to_string()).unwrap(),
            ));
        }
        self.boundary.finalize_capabilities(root, prior)
    }
    fn validate_project_identity(
        &mut self,
        purpose: Option<&str>,
        stack: &[String],
    ) -> Vec<String> {
        if let Some(value) = self.scripted("_validate_project_identity") {
            return serde_json::from_value(value.unwrap()).unwrap();
        }
        self.boundary.validate_project_identity(purpose, stack)
    }
    fn is_provider_owner(&mut self, profile: &Value, boundary: &Value) -> Result<bool, Error> {
        if let Some(value) = self.scripted("is_provider_owner") {
            return Ok(serde_json::from_value(value?).unwrap());
        }
        self.boundary.is_provider_owner(profile, boundary)
    }
    fn ensure_authored_files(
        &mut self,
        root: &Path,
        slug: &str,
        profile: &str,
        purpose: &str,
        stack: &[String],
        onboarding: Option<&Value>,
        definition: Option<&str>,
        replace: bool,
    ) -> Result<(), Error> {
        if self.boundary.mode == "authored" {
            return Err(Error::new("ValueError", "authored refused"));
        }
        self.boundary.ensure_authored_files(
            root, slug, profile, purpose, stack, onboarding, definition, replace,
        )
    }
    fn stage_memory_db(&mut self, path: &Path) -> Result<PathBuf, Error> {
        if self.boundary.mode == "stage" {
            return Err(Error::new("OSError", "stage"));
        }
        self.boundary.stage_memory_db(path)
    }
    fn apply_migrations(&mut self, db: &Connection) -> Result<(), Error> {
        if self.boundary.mode == "migrate" {
            return Err(Error::new("ValueError", "migrate"));
        }
        self.boundary.apply_migrations(db)?;
        if matches!(
            self.boundary.scenario.as_str(),
            "vector_required" | "optional_vector"
        ) {
            db.execute(
                concat!(
                    "INSERT INTO external_store_meta VALUES ",
                    "('schema_metadata_version:archive:sample','1')"
                ),
                [],
            )
            .unwrap();
        }
        Ok(())
    }
    fn context_main(&mut self, argv: &[String]) -> Result<(i32, String), Error> {
        if self.boundary.mode == "synthetic_e2e" {
            return self.boundary.context_main(argv);
        }
        if matches!(
            self.boundary.scenario.as_str(),
            "vector_required" | "optional_vector"
        ) {
            let db = Connection::open(&argv[2]).unwrap();
            self.helpers.push(query(
                &db,
                "SELECT key,value FROM external_store_meta ORDER BY key",
            ));
        }
        Ok((
            if self.boundary.mode == "sync" { 3 } else { 0 },
            String::new(),
        ))
    }
    fn run_doctor(&mut self, root: &Path, db: &Path) -> Result<(i32, Value), Error> {
        if self.boundary.mode == "synthetic_e2e" {
            return self.boundary.run_doctor(root, db);
        }
        Ok(if self.boundary.mode == "doctor" {
            (1, json!({"errors":["doctor refused"]}))
        } else {
            (0, json!({}))
        })
    }
    fn atomic_write_text(&mut self, path: &Path, body: &str) -> Result<(), Error> {
        if self.boundary.mode == "publish" && path.file_name().unwrap() == "projection.md" {
            return Err(Error::new("OSError", "publish"));
        }
        self.boundary.atomic_write_text(path, body)
    }
    fn atomic_write_json(
        &mut self,
        path: &Path,
        value: &handoff_packet::python_json::Value,
    ) -> Result<(), Error> {
        if self.boundary.scenario == "os" {
            fs::create_dir(path).unwrap();
        }
        if self.boundary.mode == "receipt" {
            return Err(Error::new("OSError", "receipt"));
        }
        self.boundary.atomic_write_json(path, value)
    }
}

fn case_args(root: &Path, mode: &str, as_json: bool, scenario: &str) -> Vec<String> {
    let mut args = vec![
        "--project-root".into(),
        root.to_str().unwrap().into(),
        "--slug".into(),
        "sample".into(),
        "--profile".into(),
        "code_app".into(),
        "--purpose".into(),
        "Build tools".into(),
        "--stack".into(),
        "Rust".into(),
    ];
    if as_json {
        args.push("--json".into());
    }
    match mode {
        "help" => args = vec!["--help".into()],
        "short_help" => args = vec!["-h".into()],
        "missing_profile" => args.clear(),
        "unknown" => args.push("--bad".into()),
        "dry_run" => args.push("--dry-run".into()),
        "apply" => args.push("--apply".into()),
        "slug" => args.extend(["--slug".into(), "!".into()]),
        "profile" => args.extend(["--profile".into(), "bad".into()]),
        "root" => args.extend([
            "--project-root".into(),
            root.join("absent").to_str().unwrap().into(),
        ]),
        _ if mode.starts_with("missing:") => args.push(mode[8..].into()),
        _ => (),
    }
    if ["finalize", "architecture", "slim", "receipt", "commit"]
        .iter()
        .any(|prefix| mode.starts_with(prefix))
    {
        args.push("--finalize".into());
        if mode != "finalize_no_attestation" {
            args.push("--architecture-initialized".into());
        }
        if mode != "finalize_missing" {
            put(root, ".mir/repo-profile.toml", "profile");
        }
    }
    if ["existing", "provider"].contains(&mode) {
        put(root, ".mir/repo-profile.toml", "profile");
    }
    if ["skip", "allow", "synthetic_e2e"].contains(&mode) {
        args.push("--skip-capability-activation".into());
        if mode != "skip" {
            args.push("--allow-incomplete".into());
        }
    }
    if mode == "archive" || scenario == "archive_identity" {
        args.extend(["--archive".into(), "notes=docs".into()]);
    }
    if ["content", "acceptance", "onboarding", "finalize_content"].contains(&mode) {
        args.extend(["--profile".into(), "content_workspace".into()]);
    }
    if scenario == "help_windows" {
        args = vec!["--help".into()];
    }
    if scenario.starts_with("content_") {
        let purpose = if scenario == "content_existing" {
            "Other purpose"
        } else {
            "Build tools"
        };
        let body = format!(
            concat!(
                "{{\"schema_version\": 1, \"profile\": \"content_workspace\", ",
                "\"purpose\": \"{}\", \"technology_stack\": [\"Rust\"], ",
                "\"archives\": [{{\"classification\": \"notes\", \"path\": \"docs\"}}], ",
                "\"scan\": {{\"unclassified\": []}}}}"
            ),
            purpose
        );
        put(root, "config/content-onboarding.json", body);
        if scenario == "content_purpose" {
            args.extend(["--purpose".into(), "Different purpose".into()]);
        }
        if scenario == "content_stack" {
            args.extend(["--stack".into(), "Python".into()]);
        }
    }
    match scenario {
        "prior_receipt" => put(
            root,
            ".mir/bootstrap-receipt.json",
            "{\"marker\":\"prior\"}",
        ),
        "harness_invalid" => put(root, "harness_a.toml", "invalid"),
        "cli_file" | "cli_manifest" => put(root, "cli", "synthetic cli"),
        _ => (),
    }
    if mode == "synthetic_e2e" {
        for name in concat!(
            "CLAUDE.md AGENTS.md .claude/settings.json .codex/config.toml ",
            ".codex/hooks.json .ai-harness/deny-list.yaml ",
            ".claude/agents/main-orchestrator.md .codex/agents/main-orchestrator.toml ",
            "config/sub-agent-policy.json config/adopter-boundary.json ",
            "config/adopter-payload.json .claude/hooks/a.sh"
        )
        .split_whitespace()
        {
            put(
                root,
                name,
                if name.ends_with(".json") {
                    "{\"hooks\":{\"Stop\":[]}}"
                } else {
                    ""
                },
            );
        }
        put(
            root,
            "config/capability-sources.json",
            concat!(
                "{\"source\": {\"url\": \"https://example.invalid/provider\", \"ref\": \"main\"}, ",
                "\"profiles\": {\"packs\": {\"code_app\": []}}}"
            ),
        );
    }
    args
}
fn replay(root: &Path, name: &str) -> Value {
    let parts: Vec<_> = name.split('.').collect();
    let (mode, scenario, as_json) = if parts[1] == "argument_missing" {
        (format!("missing:{}", parts[2]), "", false)
    } else {
        let value = parts[parts.len() - 2];
        let mode = match value {
            "help_windows" => "help",
            "prior_receipt" | "profile_purpose" | "profile_stack" | "slim_applied" => {
                "finalize_ready"
            }
            "content_purpose" | "content_stack" | "content_stale" | "content_valid" => {
                "finalize_content"
            }
            "content_existing" | "content_reuse" | "content_unclassified" => "content",
            "rollback_failure" => "receipt",
            "reason_missing" => "activation",
            "archive_identity" => "identity",
            "no_venv" | "harness_invalid" | "vector_required" | "cli_file" | "cli_missing"
            | "cli_manifest" | "dup_errors" | "optional_vector" => "ready",
            value => value,
        };
        (
            mode.into(),
            if mode == value { "" } else { value },
            parts.last() == Some(&"json"),
        )
    };
    let args = case_args(root, &mode, as_json, scenario);
    let mut host = Observer {
        boundary: BoundaryHost::new(root, &mode, Some(scenario)),
        helpers: vec![],
    };
    match m::main(&mut host, &args) {
        Ok(output) => {
            let mut written = BTreeMap::new();
            files(root, root, &mut written);
            compact(
                json!({"value":{"exit":output.exit,"stdout":output.stdout.as_str().unwrap(),
                "stderr":output.stderr,"files":written,"subprocess":host.boundary.calls,
                "scripts_called":host.helpers}}),
                root,
            )
        }
        Err(error) => {
            json!({"error":[error.class,error.message.replace(root.to_str().unwrap(),"<tmp>")]})
        }
    }
}

#[test]
fn uname_failure_propagates() {
    let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("target/mig-scratch/Y-E15");
    fs::create_dir_all(&root).unwrap();
    let temp = tempfile::tempdir_in(root).unwrap();
    let root = temp.path();
    let mut host = Observer {
        boundary: BoundaryHost::new(root, "ready", Some("uname_failure")),
        helpers: vec![],
    };
    let args = case_args(root, "ready", false, "");
    let Err(error) = m::main(&mut host, &args) else {
        panic!("uname failure must propagate");
    };
    assert_eq!(
        (error.class.as_str(), error.message.as_str()),
        ("OSError", "uname failed")
    );
}

impl Observer {
    fn carrier(&self) -> Option<(String, handoff_packet::python_json::Value)> {
        use handoff_packet::python_json as py;
        let r = self
            .boundary
            .scenario
            .starts_with('{')
            .then(|| py::parse(&self.boundary.scenario).unwrap())?;
        Some((r["status"].as_str().unwrap().into(), r["evidence"].clone()))
    }
}
#[test]
fn receipt_observation_matches_python_read_text() {
    let temp = tempfile::tempdir().unwrap();
    let receipt = temp.path().join("receipt");
    fs::write(&receipt, b"a\r\nb\rc\n\\r\\n").unwrap();
    assert_eq!(receipt_text(&receipt), receipt_os_record()["observation"]);
}

fn receipt_text(path: &Path) -> String {
    // Path.read_text uses universal newlines; JSON escapes remain literal text.
    fs::read_to_string(path)
        .unwrap()
        .replace("\r\n", "\n")
        .replace('\r', "\n")
}

fn receipt_os_record() -> Value {
    let name = if cfg!(windows) {
        "b30-receipt-os-windows.json"
    } else {
        "b30-receipt-os-unix.json"
    };
    let path = Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("tests/fixtures")
        .join(name);
    let body = fs::read_to_string(path)
        .expect("capture OS record with tests/fixtures/generate_b30_receipt_os.py first");
    let record: Value = serde_json::from_str(&body).unwrap();
    assert_eq!(
        record["reference_pin"],
        "5f8f69f94e09b64c5e4d07d329ed17797c35e6cb"
    );
    assert_eq!(record["platform"] == "win32", cfg!(windows));
    record
}

#[test]
fn main_carriers_match_pinned_python() {
    use handoff_packet::python_json as py;
    let records = py::parse(include_str!("fixtures/y-e17b2b1b2b.json")).unwrap();
    for r in records.as_array().unwrap() {
        let temp = tempfile::tempdir().unwrap();
        let root = temp.path().canonicalize().unwrap();
        let mode = r["mode"].as_str().unwrap();
        let args = case_args(&root, mode, r["json"] == py::Value::Bool(true), "");
        let mut host = Observer {
            boundary: BoundaryHost::new(&root, mode, Some(&r.json_sorted(false))),
            helpers: vec![],
        };
        let out = m::main(&mut host, &args).unwrap();
        assert_eq!(out.exit.to_string(), r["result"]["exit"].json_sorted(false));
        assert_eq!(
            out.stdout.render().unwrap(),
            r["result"]["stdout"].as_text().unwrap().render().unwrap()
        );
        assert_eq!(out.stderr, r["result"]["stderr"].as_str().unwrap());
        if r["json"] == py::Value::Bool(false) && r["status"].as_str() == Some("failed") {
            let message = r["evidence"]["reason"].as_text().unwrap();
            let prefix = py::Text::from("  [not-ready] capability activation failed: ");
            assert_eq!(
                out.stdout_prints.get(1),
                Some(&prefix.concat(message).concat(&"\n".into()))
            );
            let last = out.stdout_prints.last().unwrap().as_str();
            assert_eq!(last, Some("  receipt: .mir/bootstrap-receipt.json\n"));
        }
        let receipt = root.join(".mir/bootstrap-receipt.json");
        if r["receipt"].is_null() {
            assert!(!receipt.exists());
        } else {
            assert_eq!(
                receipt_text(&receipt).replace(root.to_str().unwrap(), "{ROOT}"),
                r["receipt"].as_str().unwrap()
            );
        }
    }
}

#[test]
fn receipt_os_failures_and_leaf_race() {
    let exceptions = receipt_os_record()["exceptions"].clone();
    let temp = tempfile::tempdir().unwrap();
    let root = temp.path().canonicalize().unwrap();
    let mut host = Observer {
        boundary: BoundaryHost::new(&root, "ready", Some("os")),
        helpers: vec![],
    };
    let out = m::main(&mut host, &case_args(&root, "ready", true, "")).unwrap();
    assert_eq!(out.exit, 1);
    assert!(
        out.stdout
            .as_str()
            .unwrap()
            .contains("bootstrap receipt publish failed:")
    );
    assert!(host.helpers.contains(&json!("rollback_adopter_slim")));
    host.boundary.scenario.clear();
    let target = root.join(".mir/bootstrap-receipt.json");
    assert_eq!(
        m::atomic_write_json(&target, &json!({}), &mut host)
            .unwrap_err()
            .class,
        exceptions["destination_directory"].as_str().unwrap()
    );
    put(&root, "file", "old");
    let file = root.join("file");
    assert_eq!(
        m::atomic_write_json(&file.join("child/receipt"), &json!({}), &mut host)
            .unwrap_err()
            .class,
        exceptions["parent_file"].as_str().unwrap()
    );
    #[cfg(unix)]
    {
        put(&root, "receipt", "old");
        let target = root.join("receipt");
        put(&root, "outside/sentinel", "unchanged");
        host.boundary.scenario = "leaf-race".into();
        m::atomic_write_json(&target, &json!({"ok":true}), &mut host).unwrap();
        assert_eq!(
            fs::read(root.join("outside/sentinel")).unwrap(),
            b"unchanged"
        );
        assert_eq!(fs::read_dir(root.join("outside")).unwrap().count(), 1);
        assert!(
            !fs::symlink_metadata(target)
                .unwrap()
                .file_type()
                .is_symlink()
        );
    }
}
