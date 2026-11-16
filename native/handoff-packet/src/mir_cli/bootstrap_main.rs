//! Bootstrap orchestration with explicit host boundaries and no CLI registration.
use super::{Error, Host, authored};
use crate::python_json::{Text, Value as PyValue};
use serde_json::{Value, json};
use std::{
    collections::BTreeMap,
    fs,
    path::{Path, PathBuf},
};

#[derive(Debug, Clone, PartialEq)]
pub struct MainOutput {
    pub exit: Value,
    pub stdout: Text,
    pub stdout_prints: Vec<Text>,
    pub stderr: String,
}

pub(super) fn strings(value: &Value) -> Vec<String> {
    value
        .as_array()
        .into_iter()
        .flatten()
        .map(authored::python_str)
        .collect()
}
fn output(code: i32, stdout_prints: Vec<Text>, stderr: String) -> MainOutput {
    let stdout = stdout_prints
        .iter()
        .fold(Text::from(""), |a, b| a.concat(b));
    MainOutput {
        exit: json!(code),
        stdout,
        stdout_prints,
        stderr,
    }
}
fn refused(message: impl AsRef<str>) -> MainOutput {
    output(2, vec![], format!("{}\n", message.as_ref()))
}
fn config_error(error: &Error) -> bool {
    value_error(error) || error.class == "ConfigLoadError" || io_error(error)
}
fn value_error(error: &Error) -> bool {
    matches!(
        error.class.as_str(),
        "ValueError" | "BoundaryError" | "AdoptionError" | "JSONDecodeError"
    )
}
fn io_error(error: &Error) -> bool {
    matches!(
        error.class.as_str(),
        "OSError"
            | "FileNotFoundError"
            | "PermissionError"
            | "NotADirectoryError"
            | "IsADirectoryError"
            | "FileExistsError"
    )
}
fn invalid(errors: &mut Vec<String>, invalid_config: &mut bool, error: Error) {
    errors.push(error.message);
    *invalid_config = true;
}
fn snapshot(root: &Path) -> Result<BTreeMap<String, String>, Error> {
    crate::mir_cli::changes::snapshot_project_with_error(root, authored::io_error)
}
fn unlink(path: &Path, missing_ok: bool) -> Result<(), Error> {
    match fs::remove_file(path) {
        Ok(()) => Ok(()),
        Err(error) if missing_ok && error.kind() == std::io::ErrorKind::NotFound => Ok(()),
        Err(error) => Err(authored::io_error(path, error)),
    }
}
fn suffixed(path: &Path, suffix: &str) -> PathBuf {
    let mut value = path.as_os_str().to_os_string();
    value.push(suffix);
    value.into()
}
fn merged(status: &str, evidence: PyValue) -> PyValue {
    let mut result = crate::python_json::Object::default();
    result.insert("status".into(), PyValue::String(status.into()));
    if let PyValue::Object(fields) = evidence {
        for (key, value) in fields.into_entries() {
            result.insert(key, value);
        }
    }
    PyValue::Object(result)
}
fn receipt_value(base: &Value, capability: &PyValue, errors: &[Text]) -> PyValue {
    let mut receipt = PyValue::from(base);
    if let PyValue::Object(fields) = &mut receipt {
        fields.insert("capabilities".into(), capability.clone());
        fields.insert(
            "errors".into(),
            PyValue::Array(errors.iter().cloned().map(PyValue::String).collect()),
        );
    }
    receipt
}

fn prepare_content(
    host: &mut impl Host,
    root: &Path,
    ns: &Value,
    finalize: bool,
    purpose: &mut Option<String>,
    stack: &mut Vec<String>,
) -> Result<(Option<Value>, Option<String>), Error> {
    let path = root.join("config/content-onboarding.json");
    if finalize {
        if !path.is_file() {
            return Err(authored::value_error(
                "content_workspace finalize requires config/content-onboarding.json",
            ));
        }
        let onboarding = super::load_content_onboarding(&path)?;
        let Some(manifest_purpose) = onboarding["purpose"].as_str() else {
            return Err(authored::value_error(
                "content onboarding manifest requires purpose and technology_stack",
            ));
        };
        if !onboarding["technology_stack"].is_array() {
            return Err(authored::value_error(
                "content onboarding manifest requires purpose and technology_stack",
            ));
        }
        *purpose = Some(manifest_purpose.into());
        *stack = strings(&onboarding["technology_stack"]);
        let definition = super::project_definition_text(manifest_purpose, stack);
        if ns["purpose"].as_str().is_some_and(|value| {
            !value.is_empty() && value.trim_matches(super::is_python_space) != manifest_purpose
        }) {
            return Err(authored::value_error(
                "--purpose conflicts with content onboarding manifest",
            ));
        }
        if !strings(&ns["stack"]).is_empty()
            && super::normalise_stack(&strings(&ns["stack"])) != *stack
        {
            return Err(authored::value_error(
                "--stack conflicts with content onboarding manifest",
            ));
        }
        let archives = super::content_archive_args(&onboarding)?;
        let (refreshed, _) =
            host.build_content_onboarding(root, manifest_purpose, stack, &archives)?;
        if refreshed != onboarding {
            return Err(authored::value_error(concat!(
                "content onboarding manifest is stale; rerun Phase 1 with all ",
                "--archive classifications before finalize"
            )));
        }
        return Ok((Some(onboarding), Some(definition)));
    }
    let mut archives = strings(&ns["archive"]);
    if path.is_file() && archives.is_empty() {
        let existing = super::load_content_onboarding(&path)?;
        if existing["purpose"] != json!(purpose) || existing["technology_stack"] != json!(stack) {
            return Err(authored::value_error(
                "bootstrap identity conflicts with config/content-onboarding.json",
            ));
        }
        archives = super::content_archive_args(&existing)?;
    }
    let (onboarding, definition) =
        host.build_content_onboarding(root, purpose.as_deref().unwrap_or(""), stack, &archives)?;
    let unclassified = &onboarding["scan"]["unclassified"];
    if unclassified
        .as_array()
        .is_some_and(|items| !items.is_empty())
    {
        let paths = unclassified
            .as_array()
            .into_iter()
            .flatten()
            .filter(|item| item.is_object())
            .map(|item| {
                format!(
                    "{} [{}]",
                    authored::python_str(&item["path"]),
                    strings(&item["formats"]).join(", ")
                )
            })
            .collect::<Vec<_>>()
            .join(", ");
        return Err(authored::value_error(format!(
            "unclassified existing content detected; rerun with \
            --archive CLASSIFICATION=PATH for: {paths}"
        )));
    }
    Ok((Some(onboarding), Some(definition)))
}

/// Matches Python main's return value, parser SystemExit and captured streams.
pub fn main(host: &mut impl Host, argv: &[String]) -> Result<MainOutput, Error> {
    let help_only = argv.len() == 1 && matches!(argv[0].as_str(), "-h" | "--help");
    if !help_only {
        match host.platform_system().as_str() {
            "Windows" => {
                return Ok(refused(concat!(
                    "Native Windows automated bootstrap is unsupported. ",
                    "Run setup.sh inside WSL, or use agent-guided ",
                    "existing-repository/reference adaptation."
                )));
            }
            "Darwin" | "Linux" => (),
            _ => {
                return Ok(refused(concat!(
                    "Automated bootstrap supports macOS, Linux, and WSL. ",
                    "Use agent-guided existing-repository/reference adaptation on this platform."
                )));
            }
        }
    }
    let parsed = super::parse(argv, &host.cwd()?);
    let Some(ns) = parsed.value else {
        return Ok(MainOutput {
            exit: json!(["SystemExit", parsed.code]),
            stdout_prints: vec![parsed.stdout.clone().into()],
            stdout: parsed.stdout.into(),
            stderr: parsed.stderr,
        });
    };
    let expanded = host.expanduser(Path::new(ns["project_root"].as_str().unwrap_or(".")))?;
    let root = host.resolve(&expanded)?;
    if !host.is_dir(&root) {
        return Ok(refused(format!(
            "project root is not a directory: {}",
            root.display()
        )));
    }
    let (ownership_errors, ownership_report) = host.source_control_ownership(&root)?;
    if !ownership_errors.is_empty() {
        return Ok(refused(ownership_errors.join("\n")));
    }
    let before = snapshot(&root)?;
    let raw_slug = ns["slug"]
        .as_str()
        .filter(|value| !value.is_empty())
        .map(str::to_owned)
        .unwrap_or_else(|| {
            root.file_name()
                .unwrap_or_default()
                .to_string_lossy()
                .into_owned()
        });
    let slug = match super::normalise_slug(&raw_slug) {
        Ok(slug) => slug,
        Err(error) if error.class == "ValueError" => return Ok(refused(error.message)),
        Err(error) => return Err(error),
    };
    let raw_profile = ns["profile"].as_str().unwrap_or("");
    let profile = match raw_profile {
        "hybrid" => "hybrid_pipeline",
        "infra" => "infra_runtime",
        value => value,
    };
    if !super::PROFILE_CHOICES.contains(&profile) {
        return Ok(refused(format!(
            "unknown profile {}; choose one of {}",
            crate::executor_execute::repr(raw_profile),
            super::PROFILE_CHOICES.join(", ")
        )));
    }
    let finalize = ns["finalize"] == true;
    let mut purpose = ns["purpose"]
        .as_str()
        .map(|value| value.trim_matches(super::is_python_space).to_owned());
    let mut stack = super::normalise_stack(&strings(&ns["stack"]));
    let mut onboarding = None;
    let mut definition = None;
    let mut errors = Vec::new();
    let mut invalid_config = false;
    let mut memory_report = json!({});
    let mut projection_updates = BTreeMap::new();
    let mut working_db = None;
    let mut staged_db = false;
    let mut architecture_evidence = json!({});
    let mut architecture_attested = false;
    let mut content_acceptance = json!({"status": "not_required"});
    let storage_arg = ns["storage_root"].as_str().map(Path::new);
    let (storage_errors, storage_report) = host.storage_preflight(&root, storage_arg)?;
    if !storage_errors.is_empty() {
        errors.extend(storage_errors);
        invalid_config = true;
    }
    let receipt_path = root.join(".mir/bootstrap-receipt.json");
    let prior_receipt = if receipt_path.is_file() {
        match authored::json_text(&receipt_path) {
            Ok(value) => value.is_object().then_some(value),
            Err(error) if io_error(&error) || error.class == "JSONDecodeError" => None,
            Err(error) => return Err(error),
        }
    } else {
        None
    };
    let identity_valid = if finalize {
        true
    } else {
        let identity_errors = host.validate_project_identity(purpose.as_deref(), &stack);
        let valid = identity_errors.is_empty();
        if !valid {
            errors.extend(identity_errors);
            invalid_config = true;
        }
        valid
    };
    if profile == "content_workspace" && identity_valid {
        match prepare_content(host, &root, &ns, finalize, &mut purpose, &mut stack) {
            Ok((manifest, body)) => {
                onboarding = manifest;
                definition = body;
            }
            Err(error) if error.class == "ValueError" => {
                invalid(&mut errors, &mut invalid_config, error)
            }
            Err(error) => return Err(error),
        }
    } else if !finalize && identity_valid && !strings(&ns["archive"]).is_empty() {
        invalid(
            &mut errors,
            &mut invalid_config,
            authored::value_error("--archive is supported only with --profile content_workspace"),
        );
    }
    let (python_version, in_virtualenv) = host.python_runtime()?;
    if !in_virtualenv {
        errors.push("mir bootstrap must run from the copied uv tool environment".into());
    }
    let (surface_errors, hook_runtime) = host.validate_surfaces(&root)?;
    errors.extend(surface_errors);
    if let Err(error) = host.load_capability_sources(&root, profile) {
        if io_error(&error) || matches!(error.class.as_str(), "ValueError" | "JSONDecodeError") {
            invalid(&mut errors, &mut invalid_config, error);
        } else {
            return Err(error);
        }
    }
    let profile_path = root.join(".mir/repo-profile.toml");
    let mut replace_provider = false;
    if profile_path.exists() {
        let existing = (|| -> Result<(), Error> {
            let current_profile = host.load_profile(&root)?;
            let current_boundary = host.load_boundary(&root)?;
            replace_provider =
                !finalize && host.is_provider_owner(&current_profile, &current_boundary)?;
            let data = if replace_provider {
                current_profile
            } else {
                host.validate_existing_profile(&profile_path, profile)?
            };
            let repo = &data["repo"];
            if finalize && repo.is_object() {
                if purpose.is_some() && repo["purpose"] != json!(purpose) {
                    return Err(authored::value_error(
                        "project purpose conflicts between profile and onboarding manifest",
                    ));
                }
                if !stack.is_empty() && repo["technology_stack"] != json!(stack) {
                    return Err(authored::value_error(
                        "project stack conflicts between profile and onboarding manifest",
                    ));
                }
                purpose = Some(authored::python_str(&repo["purpose"]));
                stack = strings(&repo["technology_stack"]);
            }
            Ok(())
        })();
        if let Err(error) = existing {
            if value_error(&error) {
                invalid(&mut errors, &mut invalid_config, error);
            } else {
                return Err(error);
            }
        }
    } else if finalize {
        invalid(
            &mut errors,
            &mut invalid_config,
            authored::value_error("--finalize requires the phase 1 .mir/repo-profile.toml"),
        );
    } else {
        replace_provider = host.is_raw_provider_checkout(&root)?;
    }
    if root.join("harness_a.toml").exists()
        && let Err(error) = host.load_config(&root)
    {
        if error.class == "ConfigLoadError" {
            invalid(&mut errors, &mut invalid_config, error);
        } else {
            return Err(error);
        }
    }
    let mut cfg = None;
    let mut db_path = root.join(".mir/memory.db");
    if errors.is_empty() {
        let authored_result = (|| -> Result<(), Error> {
            let Some(purpose) = purpose.as_deref().filter(|_| !stack.is_empty()) else {
                return Err(Error::new("AssertionError", ""));
            };
            host.ensure_authored_files(
                &root,
                &slug,
                profile,
                purpose,
                &stack,
                onboarding.as_ref(),
                definition.as_deref(),
                replace_provider,
            )?;
            let config = host.load_config(&root)?;
            if config["memory"]["enabled"] != true || config["memory"]["required"] != true {
                errors.push("bootstrap requires memory enabled=true and required=true".into());
            }
            cfg = Some(config);
            if let Some(config) = cfg.as_ref() {
                db_path = host.resolve_memory_db(&root, config)?;
            }
            working_db = Some(host.stage_memory_db(&db_path)?);
            staged_db = true;
            Ok(())
        })();
        if let Err(error) = authored_result {
            if config_error(&error) {
                invalid(&mut errors, &mut invalid_config, error);
            } else {
                return Err(error);
            }
        }
    }
    if let Some(config) = cfg.as_ref().filter(|_| errors.is_empty()) {
        let db = working_db
            .as_ref()
            .ok_or_else(|| Error::new("AssertionError", ""))?;
        let memory_result = (|| -> Result<(), Error> {
            let connection = host.bootstrap_memory_connect(db)?;
            host.apply_migrations(&connection.conn)?;
            if config["memory"]["vector_mode"] == "required" {
                connection
                    .conn
                    .execute(
                        concat!(
                            "DELETE FROM external_store_meta ",
                            "WHERE key LIKE 'schema_metadata_version:archive:%'"
                        ),
                        [],
                    )
                    .map_err(|error| {
                        super::memory::store_error(crate::mir_core::memory::store::Error::Sql(
                            error,
                        ))
                    })?;
            }
            drop(connection);
            let argv = vec![
                "sync".into(),
                "--db".into(),
                db.to_string_lossy().into_owned(),
                "--project-root".into(),
                root.to_string_lossy().into_owned(),
            ];
            let (code, captured) = host.context_main(&argv)?;
            if code != 0 {
                let detail = captured.trim_matches(super::is_python_space);
                errors.push(format!(
                    "memory archive sync failed: {}",
                    if detail.is_empty() {
                        format!("exit {code}")
                    } else {
                        detail.into()
                    }
                ));
            }
            Ok(())
        })();
        if let Err(error) = memory_result {
            errors.push(format!("memory bootstrap failed: {error}"));
        }
        if errors.is_empty() {
            let (code, report) = host.run_doctor(&root, db)?;
            memory_report = report;
            if code != 0 {
                for message in strings(&memory_report["errors"]) {
                    let message = format!("memory doctor: {message}");
                    if !errors.contains(&message) {
                        errors.push(message);
                    }
                }
            } else {
                match host.build_projection_updates(&root, db) {
                    Ok(updates) => projection_updates = updates,
                    Err(error) => {
                        errors.push(format!("memory projection preparation failed: {error}"))
                    }
                }
                if profile == "content_workspace" && errors.is_empty() {
                    let manifest = onboarding
                        .as_ref()
                        .ok_or_else(|| Error::new("AssertionError", ""))?;
                    let (acceptance_errors, report) =
                        host.validate_content_memory_acceptance(&root, db, &slug, manifest)?;
                    errors.extend(acceptance_errors);
                    content_acceptance = report;
                }
            }
        }
    }
    let skip = ns["skip_capability_activation"] == true;
    let allow = ns["allow_incomplete"] == true;
    let mut errors: Vec<Text> = errors.into_iter().map(Text::from).collect();
    let capability;
    if skip {
        capability = PyValue::from(
            &json!({"status": "skipped", "reason": "explicit test/development boundary"}),
        );
        if !allow {
            errors.push("capability activation was skipped; bootstrap cannot be ready".into());
        }
    } else if errors.is_empty() {
        let (status, evidence) = if finalize {
            if ns["architecture_initialized"] != true {
                (
                    "failed".into(),
                    PyValue::from(&json!({"reason": concat!(
                    "--finalize requires --architecture-initialized after ",
                    "explicit mir-core:design then mir-core:spec-architect execution") })),
                )
            } else {
                let (architecture_errors, evidence) = host.validate_architecture_evidence(&root)?;
                architecture_evidence = evidence;
                if !architecture_errors.is_empty() {
                    (
                        "failed".into(),
                        PyValue::from(&json!({"reason": architecture_errors.join("; ")})),
                    )
                } else {
                    let result = host.finalize_capabilities(&root, prior_receipt.as_ref())?;
                    architecture_attested = result.0 == "ready";
                    result
                }
            }
        } else {
            host.activate_capabilities(&root, profile)?
        };
        capability = merged(
            if !finalize && status == "ready" {
                "restart_required"
            } else {
                &status
            },
            evidence.clone(),
        );
        if status != "ready" {
            let reason = evidence
                .get("reason")
                .cloned()
                .unwrap_or(PyValue::String("unknown".into()));
            let reason = reason
                .as_text()
                .cloned()
                .unwrap_or_else(|| reason.py_str().into());
            errors.push(Text::from("capability activation failed: ").concat(&reason));
        }
    } else {
        capability =
            PyValue::from(&json!({"status":"not_run","reason":"preflight or memory failure"}));
    }
    let mut unique_errors = Vec::new();
    for error in errors {
        if !unique_errors.contains(&error) {
            unique_errors.push(error);
        }
    }
    let mut complete = unique_errors.is_empty() && capability["status"].as_str() == Some("ready");
    let restart =
        unique_errors.is_empty() && capability["status"].as_str() == Some("restart_required");
    let mut allowed = unique_errors.is_empty() && allow && skip;
    if unique_errors.is_empty() && (complete || restart || allowed) {
        let publish = (|| -> Result<(), Error> {
            if staged_db {
                let working = working_db
                    .as_ref()
                    .ok_or_else(|| Error::new("AssertionError", ""))?;
                for suffix in ["-shm", "-wal"] {
                    unlink(&suffixed(&db_path, suffix), true)?;
                }
                host.replace(working, &db_path)?;
                working_db = Some(db_path.clone());
            }
            for (path, body) in projection_updates {
                host.atomic_write_text(&path, &body)?;
            }
            Ok(())
        })();
        if let Err(error) = publish {
            if !io_error(&error) {
                return Err(error);
            }
            unique_errors.push(format!("memory projection publish failed: {error}").into());
            complete = false;
            allowed = false;
        }
    }
    if staged_db && let Some(working) = working_db.as_ref().filter(|working| **working != db_path) {
        for suffix in ["", "-shm", "-wal"] {
            let path = suffixed(working, suffix);
            if path.exists() {
                unlink(&path, false)?;
            }
        }
    }
    let mut slim_report = json!({"status": "not_run"});
    let cli_raw = host.env("MIR_BOOTSTRAP_CLI_PATH");
    if complete {
        let external_cli = cli_raw
            .as_ref()
            .filter(|value| !value.is_empty())
            .map(PathBuf::from)
            .unwrap_or_else(|| host.python_argv0());
        match host.apply_adopter_slim(&root, &external_cli, true) {
            Ok(report) => slim_report = report,
            Err(error) if error.class == "SlimError" => {
                unique_errors.push(format!("adopter slim failed: {error}").into());
                complete = false;
            }
            Err(error) => return Err(error),
        }
    }
    let status = if complete {
        "ready"
    } else if restart {
        "restart_required"
    } else {
        "incomplete"
    };
    let receipt_cli = slim_report["external_cli"]
        .as_str()
        .filter(|value| !value.is_empty())
        .map(str::to_owned)
        .or(cli_raw);
    let mut receipt_cli_path = None;
    let mut receipt_cli_hash = None;
    if let Some(raw) = receipt_cli.filter(|value| !value.is_empty()) {
        let expanded = host.expanduser(Path::new(&raw))?;
        // abspath normalizes lexical components without resolving symlinks.
        let cwd = host.cwd()?;
        let absolute = if expanded.is_absolute() {
            expanded
        } else {
            cwd.join(expanded)
        };
        let path = super::main_host::abspath(&absolute);
        if path.is_file() {
            let bytes = fs::read(&path).map_err(|error| authored::read_error(&path, error))?;
            receipt_cli_hash = Some(crate::digest::sha256(&bytes));
        }
        receipt_cli_path = Some(path);
    }
    let runtime_verifier = if receipt_cli_path.is_some()
        && host
            .env("MIR_BOOTSTRAP_RUNTIME_MANIFEST")
            .is_some_and(|value| !value.is_empty())
    {
        host.install_runtime_verifier(&root, &root)?
    } else {
        None
    };
    let mut cli = json!({"executable":receipt_cli_path,"sha256":receipt_cli_hash,
        "externalized":receipt_cli_path.is_some()});
    for (key, name) in [
        ("runtime_id", "MIR_BOOTSTRAP_RUNTIME_ID"),
        ("source_url", "MIR_BOOTSTRAP_SOURCE_URL"),
        ("source_commit", "MIR_BOOTSTRAP_SOURCE_COMMIT"),
        ("source_lock_sha256", "MIR_BOOTSTRAP_SOURCE_LOCK_SHA256"),
        ("constraints_sha256", "MIR_BOOTSTRAP_CONSTRAINTS_SHA256"),
        ("runtime_manifest", "MIR_BOOTSTRAP_RUNTIME_MANIFEST"),
        (
            "runtime_manifest_sha256",
            "MIR_BOOTSTRAP_RUNTIME_MANIFEST_SHA256",
        ),
    ] {
        cli[key] = json!(host.env(name));
    }
    if let Some(verifier) = runtime_verifier.filter(|value| {
        !value.is_null() && value.as_object().is_none_or(|fields| !fields.is_empty())
    }) {
        cli["runtime_verifier"] = verifier;
    }
    let mut memory = memory_report
        .get("memory")
        .cloned()
        .unwrap_or_else(|| json!({}));
    memory["topology"] = json!("per_repository_sqlite_fts5");
    memory["portable_sources"] = json!("tracked_markdown_archives_reindexable_cross_machine");
    memory["shared_database_or_vector_service"] = json!("unsupported");
    let mut receipt = json!({"schema_version":1,"status":status,"project_slug":slug,
        "profile":profile,"platform":{"os":host.platform_system().to_lowercase(),
            "release":host.platform_release()?,"python":python_version,
            "hook_runtime":hook_runtime},"storage":storage_report,"source_control":ownership_report,
        "cli":cli,"slim":slim_report,"memory":memory,"content_onboarding":content_acceptance,
        "vector":memory_report.get("vector").cloned().unwrap_or_else(|| json!({})),
        "shared_embedding_endpoint":"optional",
        "architecture_initialization":{"required":true,"sequence":super::ARCHITECTURE_SEQUENCE,
            "applies_regardless_of_first_request_type":true,"attested":architecture_attested,
            "evidence":architecture_evidence}});
    let mut after = snapshot(&root)?;
    if slim_report["status"] == "applied" {
        after.remove(".mir/slim-transaction.json");
        after.remove(".mir/slim.lock");
    }
    let mut changed = crate::mir_cli::changes::changed_paths(&before, &after);
    changed.push(".mir/bootstrap-receipt.json".into());
    changed.sort();
    changed.dedup();
    receipt["changed_paths"] = json!(changed);
    if let Err(error) = host.atomic_write_json(
        &receipt_path,
        &receipt_value(&receipt, &capability, &unique_errors),
    ) {
        if !io_error(&error) {
            return Err(error);
        }
        let rollback_error = match host.rollback_adopter_slim(&root, &slim_report) {
            Ok(()) => None,
            Err(error) if error.class == "SlimError" => Some(error.message),
            Err(error) => return Err(error),
        };
        receipt["status"] = json!("incomplete");
        unique_errors.push(format!("bootstrap receipt publish failed: {error}").into());
        if let Some(error) = rollback_error {
            unique_errors.push(error.into());
        }
        return Ok(output(
            1,
            super::emit_prints(
                ns["json"] == true,
                receipt_value(&receipt, &capability, &unique_errors),
            )?,
            String::new(),
        ));
    }
    if let Err(error) = host.commit_adopter_slim(&root, &slim_report) {
        if error.class != "SlimError" {
            return Err(error);
        }
        unique_errors.push(format!("slim commit cleanup failed: {error}").into());
        return Ok(output(
            1,
            super::emit_prints(
                ns["json"] == true,
                receipt_value(&receipt, &capability, &unique_errors),
            )?,
            String::new(),
        ));
    }
    let code = if complete || restart || allowed {
        0
    } else if invalid_config {
        2
    } else {
        1
    };
    Ok(output(
        code,
        super::emit_prints(
            ns["json"] == true,
            receipt_value(&receipt, &capability, &unique_errors),
        )?,
        String::new(),
    ))
}
