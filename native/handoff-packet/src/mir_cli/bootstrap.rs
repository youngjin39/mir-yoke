//! Library-only bootstrap identity, argument and storage policy.
#[path = "bootstrap_authored.rs"]
mod authored;
#[path = "bootstrap_core_adoption.rs"]
mod core_adoption;
#[path = "bootstrap_main_host.rs"]
mod main_host;
#[path = "bootstrap_process_host.rs"]
mod process_host;
#[path = "bootstrap_schema.rs"]
mod schema;
pub use core_adoption::core_adoption_operation;
pub use process_host::ProductionHost;
#[path = "bootstrap_main.rs"]
mod main_port;
#[path = "bootstrap_memory.rs"]
mod memory;
pub use main_port::{MainOutput, main};
#[path = "bootstrap_surfaces.rs"]
mod surfaces;
pub use memory::{build_projection_updates, stage_memory_db, validate_content_memory_acceptance};
pub use surfaces::{
    ARCHITECTURE_OUTPUTS, ARCHITECTURE_SEQUENCE, validate_architecture_evidence,
    validate_json_file, validate_surfaces,
};
#[path = "bootstrap_authored_text.rs"]
mod authored_text;
#[path = "bootstrap_release.rs"]
mod release;
pub use authored::{
    CommandOutput, CommandRequest, ensure_authored_files, reset_provider_contract_state,
    reset_provider_task_state, validate_existing_profile,
};
#[path = "bootstrap_capabilities.rs"]
mod capabilities;
#[path = "bootstrap_capability_config.rs"]
mod capability_config;
pub use authored_text::{
    PROFILE_CHOICES, memory_config_text, product_contract_text, repo_profile_text,
};
pub use capabilities::{
    CATALOG_TEMPLATE_BY_PROFILE, CapabilityOutput, activate_capabilities, capability_lock_evidence,
    compile_adopter_agent_catalog, finalize_capabilities, load_capability_sources, scalar_evidence,
};
pub use release::{
    is_raw_provider_checkout, is_safe_existing_project_file, normalise_git_url,
    release_payload_digests, rewrite_release_matched, source_control_ownership,
};
#[path = "bootstrap_content.rs"]
mod content;
use super::bootstrap_adoption::is_python_space;
use crate::executor_execute::repr;
use crate::python_json::{Text, Value as PyValue};
pub use content::{
    acceptance_query, build_content_onboarding, content_archive_args, content_archive_globs,
    discoverable_content_files, load_content_onboarding, parse_content_archives,
    project_definition_text, project_relative, scan_content_candidates, supported_content_files,
};
use regex::Regex;
use serde_json::{Value, json};
use std::{
    fmt,
    path::{Path, PathBuf},
};

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Error {
    pub class: String,
    pub message: String,
    pub message_text: Option<crate::python_json::Text>,
    pub mro: Vec<String>,
}
impl Error {
    pub fn new(class: impl Into<String>, message: impl Into<String>) -> Self {
        let class = class.into();
        let mro = match class.as_str() {
            "CapabilityError" => vec!["mir.core.capabilities.manager.CapabilityError".into()],
            "CapabilityConfigError" => {
                vec!["mir.core.capabilities.config.CapabilityConfigError".into()]
            }
            _ => vec![],
        };
        Self {
            class,
            message: message.into(),
            message_text: None,
            mro,
        }
    }
}
impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.message)
    }
}
impl std::error::Error for Error {}

/// All process environment and storage observations are supplied by the caller.
pub trait Host: Sized {
    fn env(&mut self, name: &str) -> Option<String>;
    /// shutil.which remains an injected observation; no executable is launched.
    fn which(&mut self, _name: &str) -> Option<PathBuf> {
        None
    }
    /// os.replace, including Windows replacement of an existing destination.
    fn replace(&mut self, source: &Path, destination: &Path) -> Result<(), Error> {
        tempfile::TempPath::try_from_path(source)
            .and_then(|p| p.persist(destination).map_err(|e| e.error))
            .map_err(|e| authored::io_error(destination, e))
    }
    fn resolve(&mut self, path: &Path) -> Result<PathBuf, Error>;
    fn expanduser(&mut self, path: &Path) -> Result<PathBuf, Error>;
    fn is_dir(&mut self, path: &Path) -> bool;
    fn writable(&mut self, path: &Path) -> bool;
    fn device(&mut self, path: &Path) -> Result<u64, Error>;
    /// Later caller slices supply subprocess execution; library tests reject unscripted calls.
    fn run(&mut self, _request: &CommandRequest) -> Result<CommandOutput, Error> {
        Err(Error::new("AssertionError", "unexpected"))
    }
    /// Optional jsonschema dependency stays at the host boundary in this library-only slice.
    fn validate_boundary_schema(&mut self, _value: &Value, _schema: &Value) -> Result<(), Error> {
        Err(Error::new(
            "NotImplementedError",
            "bootstrap boundary schema validator is not connected",
        ))
    }
    /// Preserve source order for jsonschema's diagnostic pprint.
    fn validate_boundary_schema_repr(
        &mut self,
        value: &Value,
        schema: &Value,
        _instance_repr: &str,
    ) -> Result<(), Error> {
        self.validate_boundary_schema(value, schema)
    }
    fn validate_boundary_schema_source(
        &mut self,
        value: &Value,
        schema: &Value,
        instance: &str,
        _schema_source: &str,
    ) -> Result<(), Error> {
        let ordered = crate::python_json::parse(instance)
            .map_err(|e| Error::new(e.exception, e.to_string()))?;
        self.validate_boundary_schema_repr(value, schema, &ordered.repr())
    }
    /// The real compiler is the default; callers can still inject this boundary.
    fn compile_adopter_agent_catalog(
        &mut self,
        root: &Path,
        profile: &str,
    ) -> Result<Vec<String>, Error> {
        compile_adopter_agent_catalog(root, profile)
    }
    /// Models the Python import separately from execution failures.
    fn capability_import(&mut self) -> Result<(), Error> {
        Ok(())
    }
    fn capability_import_for(&mut self, _root: &Path, _finalize: bool) -> Result<(), Error> {
        self.capability_import()
    }
    /// Caller-supplied provider execution; CapabilityOutput::run uses the B30-P01 CLI.
    fn capability_main(&mut self, _argv: &[String]) -> Result<CapabilityOutput, Error> {
        Err(Error::new(
            "NotImplementedError",
            "bootstrap capability CLI host is not connected",
        ))
    }
    fn validate_artifacts(&mut self, records: &Value, plugins: &Value) -> Result<(), Error> {
        crate::mir_core::capabilities::native::validate_artifacts(records, plugins, false)
            .map_err(authored::value_error)
    }
    /// Injectable config validation defaults to the Rust loader's plugins projection.
    fn capability_config_plugins(&mut self, path: &Path) -> Result<Value, Error> {
        capabilities::capability_config_plugins(path)
    }
    /// Per-connection vec loading is injectable without changing process-global state.
    fn bootstrap_memory_connect(
        &mut self,
        path: &Path,
    ) -> Result<crate::mir_core::memory::store::Connection, Error> {
        memory::connect(path)
    }
    fn cwd(&mut self) -> Result<PathBuf, Error> {
        self.resolve(Path::new("."))
    }
    fn platform_system(&mut self) -> String {
        if cfg!(windows) {
            "Windows"
        } else if cfg!(target_os = "macos") {
            "Darwin"
        } else {
            "Linux"
        }
        .into()
    }
    fn platform_release(&mut self) -> Result<String, Error> {
        Ok(String::new())
    }
    fn python_version(&mut self) -> String {
        String::new()
    }
    fn in_virtualenv(&mut self) -> bool {
        // A Rust caller supplies Python prefix attestation by overriding this boundary.
        self.env("VIRTUAL_ENV")
            .is_some_and(|value| !value.is_empty())
    }
    fn python_argv0(&mut self) -> PathBuf {
        PathBuf::from("mir")
    }
    fn now_iso(&mut self) -> Result<String, Error> {
        crate::mir_core::audit_log::now_iso(std::time::SystemTime::now())
            .map_err(|error| Error::new("ValueError", error.to_string()))
    }
    fn source_control_ownership(&mut self, root: &Path) -> Result<(Vec<String>, Value), Error> {
        let result = source_control_ownership(root, self)?;
        Ok((main_port::strings(&result[0]), result[1].clone()))
    }
    fn storage_preflight(
        &mut self,
        root: &Path,
        requested: Option<&Path>,
    ) -> Result<(Vec<String>, Value), Error> {
        storage_preflight(root, requested, self)
    }
    fn validate_project_identity(
        &mut self,
        purpose: Option<&str>,
        stack: &[String],
    ) -> Vec<String> {
        validate_project_identity(purpose, stack)
    }
    fn validate_surfaces(&mut self, root: &Path) -> Result<(Vec<String>, Value), Error> {
        validate_surfaces(root, self)
    }
    fn load_capability_sources(&mut self, root: &Path, profile: &str) -> Result<Value, Error> {
        load_capability_sources(root, profile)
    }
    fn load_profile(&mut self, root: &Path) -> Result<Value, Error> {
        core_adoption::load_profile(root)
    }
    fn load_boundary(&mut self, root: &Path) -> Result<Value, Error> {
        core_adoption::load_boundary(root, self)
    }
    fn is_provider_owner(&mut self, profile: &Value, boundary: &Value) -> Result<bool, Error> {
        core_adoption::is_provider_owner(profile, boundary)
    }
    fn validate_existing_profile(&mut self, path: &Path, profile: &str) -> Result<Value, Error> {
        validate_existing_profile(path, profile)
    }
    fn is_raw_provider_checkout(&mut self, root: &Path) -> Result<bool, Error> {
        is_raw_provider_checkout(root, self)
    }
    fn load_config(&mut self, root: &Path) -> Result<Value, Error> {
        let home = self.expanduser(Path::new("~"))?;
        main_host::load_config(root, &home)
    }
    fn resolve_memory_db(&mut self, root: &Path, cfg: &Value) -> Result<PathBuf, Error> {
        let home = self.expanduser(Path::new("~"))?;
        main_host::resolve_memory_db(root, cfg, &home)
    }
    // Preserve the Python authored-files boundary's independently observable arguments.
    #[allow(clippy::too_many_arguments)]
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
        ensure_authored_files(
            root, slug, profile, purpose, stack, onboarding, definition, replace, self,
        )
    }
    fn stage_memory_db(&mut self, path: &Path) -> Result<PathBuf, Error> {
        stage_memory_db(path)
    }
    fn apply_migrations(&mut self, connection: &rusqlite::Connection) -> Result<(), Error> {
        crate::mir_core::memory::store::apply_migrations(connection)
            .map(|_| ())
            .map_err(memory::store_error)
    }
    fn context_main(&mut self, argv: &[String]) -> Result<(i32, String), Error> {
        let home = self.expanduser(Path::new("~"))?;
        main_host::context_main(
            Path::new(&argv[4]),
            Path::new(&argv[2]),
            &home,
            &self.now_iso()?,
        )
    }
    fn run_doctor(&mut self, root: &Path, db: &Path) -> Result<(i32, Value), Error> {
        let home = self.expanduser(Path::new("~"))?;
        main_host::run_doctor(root, db, &home)
    }
    fn build_projection_updates(
        &mut self,
        root: &Path,
        db: &Path,
    ) -> Result<std::collections::BTreeMap<PathBuf, String>, Error> {
        build_projection_updates(root, db, self)
    }
    fn validate_content_memory_acceptance(
        &mut self,
        root: &Path,
        db: &Path,
        slug: &str,
        onboarding: &Value,
    ) -> Result<(Vec<String>, Value), Error> {
        validate_content_memory_acceptance(root, db, slug, onboarding, self)
    }
    fn build_content_onboarding(
        &mut self,
        root: &Path,
        purpose: &str,
        stack: &[String],
        archives: &[String],
    ) -> Result<(Value, String), Error> {
        build_content_onboarding(root, purpose, stack, archives)
    }
    fn validate_architecture_evidence(
        &mut self,
        root: &Path,
    ) -> Result<(Vec<String>, Value), Error> {
        validate_architecture_evidence(root)
    }
    fn activate_capabilities(
        &mut self,
        root: &Path,
        profile: &str,
    ) -> Result<(String, crate::python_json::Value), Error> {
        activate_capabilities(root, profile, self)
    }
    fn finalize_capabilities(
        &mut self,
        root: &Path,
        prior: Option<&Value>,
    ) -> Result<(String, crate::python_json::Value), Error> {
        finalize_capabilities(root, prior, self)
    }
    fn apply_adopter_slim(
        &mut self,
        root: &Path,
        cli: &Path,
        defer_commit: bool,
    ) -> Result<Value, Error> {
        core_adoption::apply_adopter_slim(root, cli, defer_commit, self)
    }
    fn rollback_adopter_slim(&mut self, root: &Path, report: &Value) -> Result<(), Error> {
        core_adoption::rollback_adopter_slim(root, report, self)
    }
    fn commit_adopter_slim(&mut self, root: &Path, report: &Value) -> Result<(), Error> {
        core_adoption::commit_adopter_slim(root, report, self)
    }
    fn slim_process_alive(&mut self, _pid: i64) -> Result<bool, Error> {
        Err(Error::new(
            "NotImplementedError",
            "slim process liveness host is not connected",
        ))
    }
    /// Executes with Python's clean environment, including removal of tool-environment keys.
    fn slim_run_clean(&mut self, _request: &CommandRequest) -> Result<CommandOutput, Error> {
        Err(Error::new(
            "NotImplementedError",
            "slim clean subprocess host is not connected",
        ))
    }
    /// Deterministic check/use seam; production does nothing.
    fn slim_before_move(&mut self, _root: &Path, _source: &Path, _destination: &Path) {}
    /// Observe or deny a prepared descriptor-relative rename before executing it.
    fn slim_replace(
        &mut self,
        _source: &Path,
        _destination: &Path,
        operation: &mut dyn FnMut() -> Result<(), Error>,
    ) -> Result<(), Error> {
        operation()
    }
    /// Raw descriptor operations preserve Python's errors without a filename.
    fn slim_write(
        &mut self,
        file: &mut std::fs::File,
        body: &[u8],
        _phase: &str,
    ) -> std::io::Result<()> {
        std::io::Write::write_all(file, body)
    }
    fn slim_fsync(&mut self, file: &std::fs::File, _phase: &str) -> std::io::Result<()> {
        file.sync_all()
    }
    fn slim_pid(&mut self) -> u32 {
        std::process::id()
    }
    fn slim_transaction_id(&mut self) -> String {
        use std::sync::atomic::{AtomicU64, Ordering};
        static NEXT: AtomicU64 = AtomicU64::new(0);
        let entropy = format!(
            "{:?}-{}-{}",
            std::time::SystemTime::now(),
            self.slim_pid(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        );
        // The journal requires UUID's 32-hex shape; hosts may supply a UUID source.
        crate::digest::sha256(entropy.as_bytes())[..32].to_owned()
    }
    fn install_runtime_verifier(
        &mut self,
        root: &Path,
        source_root: &Path,
    ) -> Result<Option<Value>, Error> {
        let system = self.platform_system();
        let target =
            crate::mir_core::capabilities::native::host_target(&system, std::env::consts::ARCH);
        let artifacts = self.env("MIR_CAPABILITY_NATIVE_ARTIFACTS");
        let home = self.expanduser(Path::new("~"))?;
        let options = crate::mir_cli::adoption_native::InstallOptions {
            target: target.as_deref(),
            native_artifacts: artifacts.as_deref(),
            source_root: Some(source_root),
            home: Some(&home),
            ..Default::default()
        };
        Ok(crate::mir_cli::adoption_native::install_runtime_verifier(
            root,
            &options,
            &mut crate::mir_cli::adoption_native::LocalHost,
        ))
    }
    fn atomic_write_text(&mut self, path: &Path, body: &str) -> Result<(), Error> {
        atomic_write_text(path, body, self)
    }
    fn atomic_write_json(&mut self, path: &Path, value: &PyValue) -> Result<(), Error> {
        atomic_write_json(path, value, self)
    }
}
pub const EXTERNAL_STORAGE_PATHS: [(&str, &str); 3] = [
    ("UV_CACHE_DIR", "uv/cache"),
    ("UV_PYTHON_INSTALL_DIR", "uv/python"),
    ("MIR_CAPABILITY_HOME", "mir/capabilities"),
];

#[derive(Debug, Clone)]
pub struct ParseOutput {
    pub code: i32,
    pub stdout: String,
    pub stderr: String,
    pub value: Option<Value>,
}
const USAGE: &str = concat!(
    "usage: mir bootstrap [-h] [--project-root PROJECT_ROOT] [--slug SLUG]\n",
    "                     --profile PROFILE [--purpose PURPOSE] [--stack STACK]\n",
    "                     [--archive CLASSIFICATION=PATH]\n",
    "                     [--storage-root STORAGE_ROOT] [--json] [--finalize]\n",
    "                     [--architecture-initialized]\n",
    "                     [--skip-capability-activation]\n",
);
const OPTIONS: [&str; 14] = [
    "--help",
    "--project-root",
    "--slug",
    "--profile",
    "--purpose",
    "--stack",
    "--archive",
    "--storage-root",
    "--json",
    "--finalize",
    "--architecture-initialized",
    "--skip-capability-activation",
    "--allow-incomplete",
    "-h",
];
fn parse_error(message: String) -> ParseOutput {
    ParseOutput {
        code: 2,
        stdout: String::new(),
        stderr: format!("{USAGE}mir bootstrap: error: {message}\n"),
        value: None,
    }
}
fn help() -> String {
    format!(
        "{USAGE}\noptions:\n{}",
        concat!(
            "  -h, --help            show this help message and exit\n",
            "  --project-root PROJECT_ROOT\n",
            "  --slug SLUG\n",
            "  --profile PROFILE     required project archetype; no implicit code_app\n",
            "                        default\n",
            "  --purpose PURPOSE     non-placeholder project mission (required in phase 1)\n",
            "  --stack STACK         technology or working-medium item; repeat or pass\n",
            "                        comma-separated values\n",
            "  --archive CLASSIFICATION=PATH\n",
            "                        classify an existing content path for onboarding\n",
            "                        (content_workspace)\n",
            "  --storage-root STORAGE_ROOT\n",
            "                        shared external-volume root configured by setup.sh\n",
            "  --json\n",
            "  --finalize            phase 2: verify capabilities after restarting the\n",
            "                        agent runtime\n",
            "  --architecture-initialized\n",
            "                        attest that mir-core:design then mir-core:spec-\n",
            "                        architect initialized the project\n",
            "  --skip-capability-activation\n",
            "                        test/development only: leave bootstrap incomplete\n",
            "                        unless --allow-incomplete\n",
        )
    )
}
/// Mirror argparse's observable namespace and its stdout/stderr exit boundary.
pub fn parse(argv: &[String], cwd: &Path) -> ParseOutput {
    let mut value = json!({"project_root": cwd, "slug": null, "profile": null,
        "purpose": null, "stack": [], "archive": [], "storage_root": null,
        "json": false, "finalize": false, "architecture_initialized": false,
        "skip_capability_activation": false, "allow_incomplete": false});
    let mut unknown = Vec::new();
    let mut index = 0;
    let mut positional = false;
    while index < argv.len() {
        let arg = &argv[index];
        if arg == "--" {
            positional = true;
            unknown.push(arg.clone());
            index += 1;
            continue;
        }
        let (authored, explicit) = arg
            .split_once('=')
            .map_or((arg.as_str(), None), |(name, value)| (name, Some(value)));
        if !positional && arg.starts_with("-h") && arg != "-h" {
            return parse_error(format!(
                "argument -h/--help: ignored explicit argument {}",
                repr(explicit.unwrap_or(&arg[2..]))
            ));
        }
        let matches: Vec<_> = OPTIONS
            .iter()
            .copied()
            .filter(|option| {
                !positional
                    && (*option == authored
                        || authored.starts_with("--") && option.starts_with(authored))
            })
            .collect();
        let option = if OPTIONS.contains(&authored) && !positional {
            authored
        } else if matches.len() == 1 {
            matches[0]
        } else if matches.len() > 1 {
            return parse_error(format!(
                "ambiguous option: {authored} could match {}",
                matches.join(", ")
            ));
        } else {
            unknown.push(arg.clone());
            index += 1;
            continue;
        };
        let flag = matches!(
            option,
            "--help"
                | "-h"
                | "--json"
                | "--finalize"
                | "--architecture-initialized"
                | "--skip-capability-activation"
                | "--allow-incomplete"
        );
        if flag {
            if let Some(explicit) = explicit {
                let option = if matches!(option, "--help" | "-h") {
                    "-h/--help"
                } else {
                    option
                };
                return parse_error(format!(
                    "argument {option}: ignored explicit argument {}",
                    repr(explicit)
                ));
            }
            if matches!(option, "--help" | "-h") {
                return ParseOutput {
                    code: 0,
                    stdout: help(),
                    stderr: String::new(),
                    value: None,
                };
            }
            value[option.trim_start_matches('-').replace('-', "_")] = json!(true);
        } else {
            let raw = if let Some(explicit) = explicit {
                explicit
            } else {
                index += 1;
                let Some(next) = argv.get(index).filter(|next| !is_option(next)) else {
                    return parse_error(format!("argument {option}: expected one argument"));
                };
                next
            };
            let key = option.trim_start_matches('-').replace('-', "_");
            if matches!(option, "--stack" | "--archive") {
                if let Some(items) = value[&key].as_array_mut() {
                    items.push(json!(raw));
                }
            } else if matches!(option, "--project-root" | "--storage-root") {
                value[&key] = json!(authored_path(raw));
            } else {
                value[&key] = json!(raw);
            }
        }
        index += 1;
    }
    if value["profile"].is_null() {
        return parse_error("the following arguments are required: --profile".into());
    }
    if !unknown.is_empty() {
        return parse_error(format!("unrecognized arguments: {}", unknown.join(" ")));
    }
    ParseOutput {
        code: 0,
        stdout: String::new(),
        stderr: String::new(),
        value: Some(value),
    }
}
fn is_option(value: &str) -> bool {
    let negative_number =
        Regex::new(r"^-\d+$|^-\d*\.\d+$").is_ok_and(|pattern| pattern.is_match(value));
    value.starts_with('-') && value != "-" && !value.contains(' ') && !negative_number
}
fn authored_path(raw: &str) -> String {
    // pathlib removes redundant separators and dot segments, but preserves `..`.
    let leading = if raw.starts_with("//") && !raw.starts_with("///") {
        "//"
    } else if raw.starts_with('/') {
        "/"
    } else {
        ""
    };
    let parts: Vec<_> = raw
        .split('/')
        .filter(|part| !part.is_empty() && *part != ".")
        .collect();
    let path = format!("{leading}{}", parts.join("/"));
    if path.is_empty() { ".".into() } else { path }
}

pub fn normalise_slug(raw: &str) -> Result<String, Error> {
    let mut slug = String::new();
    let mut replacing = false;
    for ch in raw.trim_matches(is_python_space).to_lowercase().chars() {
        if ch.is_ascii_lowercase() || ch.is_ascii_digit() || ch == '_' || ch == '-' {
            slug.push(ch);
            replacing = false;
        } else if !replacing {
            slug.push('-');
            replacing = true;
        }
    }
    let slug = slug.trim_matches(['-', '_']);
    if slug.is_empty() || slug.len() > 64 {
        return Err(Error::new(
            "ValueError",
            format!(
                "project slug {} cannot be normalized to a valid slug",
                repr(raw)
            ),
        ));
    }
    Ok(slug.into())
}
pub fn normalise_stack(values: &[String]) -> Vec<String> {
    let mut stack = Vec::new();
    for item in values
        .iter()
        .flat_map(|value| value.split(','))
        .map(|item| item.trim_matches(is_python_space))
    {
        if !item.is_empty() && !stack.iter().any(|value| value == item) {
            stack.push(item.to_owned());
        }
    }
    stack
}
fn placeholder(value: &str) -> bool {
    // Python's word class is letters/numbers/underscore, excluding combining marks.
    let value = value.replace(['\u{130}', '\u{131}'], "i");
    Regex::new(concat!(
        r"(?i)(?:^|[^\p{L}\p{N}_])",
        r"(?:describe|placeholder|replace[ -]?me|tbd|todo|unknown)",
        r"(?:$|[^\p{L}\p{N}_])",
    ))
    .is_ok_and(|pattern| pattern.is_match(&value))
}
pub fn validate_project_identity(purpose: Option<&str>, stack: &[String]) -> Vec<String> {
    let mut errors = Vec::new();
    if purpose.is_none_or(|value| value.trim_matches(is_python_space).is_empty()) {
        errors.push("--purpose is required during bootstrap phase 1".into());
    } else if purpose.is_some_and(|value| value.contains(['\n', '\r'])) {
        errors.push("--purpose must be a single line".into());
    } else if purpose.is_some_and(placeholder) {
        errors.push("--purpose must not contain placeholder text".into());
    }
    if stack.is_empty() {
        errors.push("at least one --stack value is required during bootstrap phase 1".into());
    }
    for item in stack {
        if placeholder(item) {
            errors.push(format!(
                "--stack must not contain placeholder text: {}",
                repr(item)
            ));
        }
    }
    errors
}

fn expanded(host: &mut impl Host, path: &Path) -> Result<PathBuf, Error> {
    let path = host.expanduser(path)?;
    host.resolve(&path)
}
pub fn storage_preflight(
    root: &Path,
    requested: Option<&Path>,
    host: &mut impl Host,
) -> Result<(Vec<String>, Value), Error> {
    let Some(requested) = requested else {
        return Ok((
            Vec::new(),
            json!({"mode": "host-default", "root": null,
            "same_filesystem_as_project": null, "large_payloads": {}}),
        ));
    };
    let storage = expanded(host, requested)?;
    let environment = host.resolve(&root.join(".venv"))?;
    let mut report = json!({"mode": "external-first", "root": storage,
        "project_environment": environment, "same_filesystem_as_project": false,
        "large_payloads": {}});
    let mut errors = Vec::new();
    if !host.is_dir(&storage) {
        errors.push(format!(
            "external storage root is not a directory: {}",
            storage.display()
        ));
        return Ok((errors, report));
    }
    if !host.writable(&storage) {
        errors.push(format!(
            "external storage root is not writable: {}",
            storage.display()
        ));
    }
    let mut configured = Vec::new();
    for (name, relative) in EXTERNAL_STORAGE_PATHS {
        let expected = host.resolve(&storage.join(relative))?;
        let Some(raw) = host.env(name).filter(|raw| !raw.is_empty()) else {
            errors.push(format!(
                "{name} is not configured; invoke bootstrap through setup.sh \
                with --storage-root"
            ));
            continue;
        };
        let actual = expanded(host, Path::new(&raw))?;
        report["large_payloads"][name] = json!(actual);
        if actual != expected {
            errors.push(format!(
                "{name} must resolve to {}, got {}",
                expected.display(),
                actual.display()
            ));
        } else if !host.is_dir(&actual) {
            errors.push(format!("{name} directory is missing: {}", actual.display()));
        } else {
            configured.push(actual);
        }
    }
    let runtime_id = host.env("MIR_BOOTSTRAP_RUNTIME_ID").unwrap_or_default();
    let runtime_root = host.resolve(&storage.join("mir/cli").join(&runtime_id))?;
    for (name, leaf) in [("UV_TOOL_DIR", "tools"), ("UV_TOOL_BIN_DIR", "bin")] {
        let Some(raw) = host.env(name).filter(|raw| !raw.is_empty()) else {
            errors.push(format!(
                "{name} is not configured; invoke bootstrap through setup.sh \
                with --storage-root"
            ));
            continue;
        };
        let actual = expanded(host, Path::new(&raw))?;
        report["large_payloads"][name] = json!(actual);
        if runtime_id.is_empty() || actual != runtime_root.join(leaf) {
            errors.push(format!(
                "{name} must use the setup-derived project runtime under \
                {}, got {}",
                storage.join("mir/cli").display(),
                actual.display()
            ));
        } else if !host.is_dir(&actual) {
            errors.push(format!("{name} directory is missing: {}", actual.display()));
        } else {
            configured.push(actual);
        }
    }
    let environment = host.resolve(&root.join(".venv"))?;
    match host
        .env("UV_PROJECT_ENVIRONMENT")
        .filter(|raw| !raw.is_empty())
    {
        None => {
            errors.push("UV_PROJECT_ENVIRONMENT is not configured for project-local .venv".into())
        }
        Some(raw) => {
            let actual = expanded(host, Path::new(&raw))?;
            if actual != environment {
                errors.push(format!(
                    "UV_PROJECT_ENVIRONMENT must resolve to {}, got {}",
                    environment.display(),
                    actual.display()
                ));
            }
        }
    }
    let same_filesystem = (|| {
        let project_device = host.device(root)?;
        if configured.len() != EXTERNAL_STORAGE_PATHS.len() + 2
            || host.device(&storage)? != project_device
        {
            return Ok(false);
        }
        for path in &configured {
            if host.device(path)? != project_device {
                return Ok(false);
            }
        }
        Ok::<_, Error>(true)
    })();
    match same_filesystem {
        Err(error) => {
            if !matches!(
                error.class.as_str(),
                "OSError"
                    | "FileNotFoundError"
                    | "PermissionError"
                    | "NotADirectoryError"
                    | "IsADirectoryError"
            ) {
                return Err(error);
            }
            errors.push(format!("external storage filesystem check failed: {error}"));
        }
        Ok(same) => {
            report["same_filesystem_as_project"] = json!(same);
            if !same {
                errors.push(
                    "external storage root and project must use the same filesystem \
                    so uv can clone/link cached packages instead of copying them"
                        .into(),
                );
            }
        }
    }
    Ok((errors, report))
}

/// Reuse the authored writer with an injectable os.replace boundary.
pub fn atomic_write_text(path: &Path, body: &str, host: &mut impl Host) -> Result<(), Error> {
    authored::atomic_write_with(path, body, false, |a, b| host.replace(a, b))
}
pub fn atomic_write_json(
    path: &Path,
    payload: impl Into<PyValue>,
    host: &mut impl Host,
) -> Result<(), Error> {
    let body = payload.into().json_sorted(true) + "\n";
    authored::atomic_write_with(path, &body, true, |a, b| host.replace(a, b))
}
/// Return the exact stdout text; caller connection belongs to a later slice.
pub fn emit(as_json: bool, receipt: impl Into<PyValue>) -> Result<Text, Error> {
    let receipt = receipt.into();
    if as_json {
        return Ok((receipt.json_sorted(false) + "\n").into());
    }
    let status = receipt["status"].py_str();
    let mut out = Text::from(format!("mir bootstrap: {status}\n"));
    for error in receipt["errors"].as_array().into_iter().flatten() {
        let text = error
            .as_text()
            .cloned()
            .unwrap_or_else(|| error.py_str().into());
        out = out
            .concat(&Text::from("  [not-ready] "))
            .concat(&text)
            .concat(&"\n".into());
    }
    if status == "restart_required" {
        out = out.concat(&Text::from(concat!(
            "  selected global plugins are hash-verified for required runtimes\n",
            "  begin a new session for every required activation runtime\n",
            "  attest the namespaced skill catalog from each required session\n",
            "  optional runtime installation and discovery evidence is advisory\n",
            "  run mir-core:design then mir-core:spec-architect, then finalize\n",
        )));
    }
    out = out.concat(&"  receipt: .mir/bootstrap-receipt.json\n".into());
    Ok(out)
}
