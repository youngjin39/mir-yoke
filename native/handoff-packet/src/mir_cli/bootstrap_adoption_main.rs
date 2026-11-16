//! Library orchestration and observable host boundaries for adoption receipts.
use super::*;
use crate::mir_cli::{adoption_native, changes};

pub struct JqRequest {
    pub argv: Vec<String>,
    pub cwd: Option<String>,
    pub input: Option<Vec<u8>>,
    pub capture_output: bool,
    pub check: bool,
}
pub struct JqOutput {
    pub returncode: i32,
    pub stdout: Vec<u8>,
}
pub enum ValidationKind<'a> {
    Profile,
    SurfaceContract,
    RequiredRuntimeEvidence(&'a str),
    BootstrapGate,
    CanonicalAppliedHelper { relative: &'a str, label: &'a str },
    PythonLauncher,
    ContentOnboarding,
    Memory,
    Phase2,
}
pub struct ValidationRequest<'a> {
    pub root: &'a Path,
    pub kind: ValidationKind<'a>,
    pub value: &'a Value,
}
pub struct ValidationOutput {
    pub errors: Vec<String>,
    pub evidence: Value,
    pub exceptions: Vec<Value>,
}
impl ValidationRequest<'_> {
    pub fn name(&self) -> &'static str {
        match self.kind {
            ValidationKind::Profile => "_validate_profile",
            ValidationKind::SurfaceContract => "_validate_surface_contract",
            ValidationKind::RequiredRuntimeEvidence(_) => "_validate_required_runtime_evidence",
            ValidationKind::BootstrapGate => "_validate_bootstrap_gate",
            ValidationKind::CanonicalAppliedHelper { .. } => "_validate_canonical_applied_helper",
            ValidationKind::PythonLauncher => "_validate_python_launcher",
            ValidationKind::ContentOnboarding => "_validate_content_onboarding",
            ValidationKind::Memory => "_validate_memory",
            ValidationKind::Phase2 => "_validate_phase2",
        }
    }
    /// Mirrors the Python mock boundary without executing or evaluating Python.
    pub fn python_call(&self) -> Value {
        let root = wire(self.root);
        let (args, kwargs) = match self.kind {
            ValidationKind::Profile
            | ValidationKind::SurfaceContract
            | ValidationKind::ContentOnboarding
            | ValidationKind::Memory
            | ValidationKind::Phase2 => (json!([root, self.value]), json!({})),
            ValidationKind::RequiredRuntimeEvidence(name) => {
                (json!([self.value]), json!({"surface_name":name}))
            }
            ValidationKind::CanonicalAppliedHelper { relative, label } => {
                (json!([root, relative]), json!({"label":label}))
            }
            ValidationKind::BootstrapGate | ValidationKind::PythonLauncher => {
                (json!([root]), json!({}))
            }
        };
        json!([self.name(), args, kwargs])
    }
}
fn validate(
    request: ValidationRequest<'_>,
    source: &Path,
    package: &Path,
    host: &mut dyn Host,
) -> Result<ValidationOutput, Error> {
    if let Some(result) = host.validation(&request) {
        return result;
    }
    let root = request.root;
    let value = request.value;
    let mut exceptions = Vec::new();
    let (errors, evidence) = match request.kind {
        ValidationKind::Profile => validate_profile(root, value, host),
        ValidationKind::SurfaceContract => {
            let (errors, surfaces, found) = validate_surface_contract(root, value, host)?;
            exceptions = found;
            (errors, Value::Object(surfaces))
        }
        ValidationKind::RequiredRuntimeEvidence(name) => {
            (validate_required_runtime_evidence(value, name), Value::Null)
        }
        ValidationKind::BootstrapGate => validate_bootstrap_gate(root, host)?,
        ValidationKind::CanonicalAppliedHelper { relative, label } => {
            validate_canonical_applied_helper(root, relative, label, source, package, host)
        }
        ValidationKind::PythonLauncher => validate_python_launcher(root, host),
        ValidationKind::ContentOnboarding => validate_content_onboarding(root, value, host)?,
        ValidationKind::Memory => validate_memory(root, value, host)?,
        ValidationKind::Phase2 => validate_phase2(root, value, host)?,
    };
    Ok(ValidationOutput {
        errors,
        evidence,
        exceptions,
    })
}

pub fn evidence_digest(relative: &str, path: &Path, host: &mut dyn Host) -> Result<String, Error> {
    if let Some(result) = host.digest(relative, path) {
        return result;
    }
    if relative != ".claude/settings.json" {
        return Ok(crate::digest::sha256(&read(path, host)?));
    }
    let result = host
        .jq(&JqRequest {
            argv: vec![
                "jq".into(),
                "-S".into(),
                "-c".into(),
                "if (.hooks | type) == \"object\" and (.hooks | length) > 0 \
            then {hooks: .hooks} else error(\"non-empty hooks object required\") end"
                    .into(),
                wire(path),
            ],
            cwd: None,
            input: None,
            capture_output: true,
            check: false,
        })
        .map_err(|e| {
            adoption(format!(
                "cannot digest settings hook evidence: {}",
                jq_spawn_message(&e)
            ))
        })?;
    // bytes.strip uses ASCII whitespace, unlike the validators' Python text strip.
    if result.returncode != 0 || result.stdout.iter().all(|b| b" \t\n\r\x0b\x0c".contains(b)) {
        return Err(adoption(
            "settings evidence requires readable JSON with non-empty hooks",
        ));
    }
    let mut body = result.stdout;
    while body.last() == Some(&b'\n') {
        body.pop();
    }
    body.push(b'\n');
    Ok(crate::digest::sha256(&body))
}
pub fn evidence_digests(
    root: &Path,
    surfaces: &Value,
    host: &mut dyn Host,
) -> Result<Vec<Value>, Error> {
    if let Some(result) = host.digests(root, surfaces) {
        return result;
    }
    let mut paths = BTreeSet::new();
    if let Some(surfaces) = surfaces.as_object() {
        for surface in surfaces.values() {
            if let Some(evidence) = surface.get("evidence_paths").and_then(Value::as_array) {
                paths.extend(evidence.iter().map(|v| match v {
                    Value::String(s) => s.clone(),
                    _ => value_repr(v),
                }));
            }
        }
    }
    let mut evidence = Vec::new();
    for relative in paths {
        match evidence_digest(&relative, &root.join(&relative), host) {
            Ok(digest) => evidence.push(json!({"path":relative,"sha256":digest})),
            Err(Error::Io { .. }) => continue,
            Err(error) => return Err(error),
        }
    }
    Ok(evidence)
}
fn ascii_json(text: String) -> String {
    text.chars()
        .map(|c| {
            if c.is_ascii() {
                c.to_string()
            } else {
                c.encode_utf16(&mut [0; 2])
                    .iter()
                    .map(|u| format!("\\u{u:04x}"))
                    .collect::<String>()
            }
        })
        .collect()
}
fn json_string(value: &Value, pretty: bool) -> Result<String, Error> {
    let text = if pretty {
        serde_json::to_string_pretty(value)
    } else {
        serde_json::to_string(value)
    }
    .map_err(|e| Error::Json(e.to_string()))?;
    Ok(ascii_json(text))
}
fn receipt_json(payload: &Value, windows: bool) -> Result<String, Error> {
    let body = format!("{}\n", json_string(payload, true)?);
    // Python Path.write_text(newline=None) translates every LF on Windows.
    Ok(if windows {
        body.replace('\n', "\r\n")
    } else {
        body
    })
}
pub fn atomic_write_json<H: Host + ?Sized>(
    path: &Path,
    payload: &Value,
    host: &mut H,
) -> Result<(), Error> {
    let parent = path.parent().unwrap_or_else(|| Path::new("."));
    fs::create_dir_all(parent).map_err(|e| io_error(parent, e))?;
    let name = path
        .file_name()
        .unwrap_or_default()
        .to_str()
        .ok_or_else(|| adoption("non-UTF-8 receipt name"))?;
    let temporary = tempfile::Builder::new()
        .prefix(&format!(".{name}."))
        .tempfile_in(parent)
        .map_err(|e| io_error(parent, e))?;
    // Close mkstemp's descriptor before write_text, as in the reference.
    let temporary = temporary.into_temp_path();
    let body = receipt_json(payload, cfg!(windows))?;
    fs::write(&temporary, body).map_err(|e| io_error(&temporary, e))?;
    host.replace(&temporary, path)
        .map_err(|e| io_error(path, e))?;
    // TempPath owns cleanup on both success and failure.
    Ok(())
}

pub fn emit(as_json: bool, report: &Value, host: &mut dyn Host) -> Result<(), Error> {
    let mut output = if as_json {
        format!("{}\n", json_string(report, false)?)
    } else {
        format!(
            "mir bootstrap-adoption: {}\n",
            report["status"].as_str().unwrap_or("None")
        )
    };
    if !as_json {
        if let Some(errors) = report.get("errors").and_then(Value::as_array) {
            for error in errors {
                output.push_str(&format!(
                    "  [not-ready] {}\n",
                    error.as_str().unwrap_or("None")
                ));
            }
        }
        if report["receipt_written"] == true {
            output.push_str("  receipt: .mir/bootstrap-receipt.json\n");
        }
    }
    host.stdout(&output)
        .map_err(|e| io_error(Path::new("<stdout>"), e))
}

pub fn write_receipt_with(
    path: &Path,
    value: &Value,
    before: impl FnOnce(&Path, &Path) -> io::Result<()>,
) -> Result<(), Error> {
    write_receipt_for_platform(path, value, cfg!(windows), before)
}

fn write_receipt_for_platform(
    path: &Path,
    value: &Value,
    windows: bool,
    before: impl FnOnce(&Path, &Path) -> io::Result<()>,
) -> Result<(), Error> {
    let parent = path.parent().unwrap_or_else(|| Path::new("."));
    fs::create_dir_all(parent).map_err(|e| io_error(parent, e))?;
    let data = receipt_json(value, windows)?;
    #[cfg(unix)]
    {
        use io::Write;
        let temporary = tempfile::Builder::new()
            .prefix(".bootstrap-receipt.json.")
            .make_in(parent, |candidate| {
                crate::adoption_fs::StagedFile::create(parent, candidate)
            })
            .map_err(|e| io_error(parent, e))?;
        let (mut staged, mut inert) = temporary.into_parts();
        inert.disable_cleanup(true);
        staged
            .file
            .write_all(data.as_bytes())
            .map_err(|e| io_error(&staged.path, e))?;
        before(&staged.path, path).map_err(|e| io_error(path, e))?;
        staged.publish(parent, path).map_err(|e| {
            let mut error = io_error(&staged.path, e);
            if let Error::Io { message, .. } = &mut error {
                message.push_str(&format!(" -> {}", repr(&wire(path))));
            }
            error
        })?;
        Ok(())
    }
    #[cfg(not(unix))]
    {
        use io::Write;
        let mut temporary = tempfile::Builder::new()
            .prefix(".bootstrap-receipt.json.")
            .tempfile_in(parent)
            .map_err(|e| io_error(parent, e))?;
        temporary
            .write_all(data.as_bytes())
            .map_err(|e| io_error(path, e))?;
        before(temporary.path(), path).map_err(|e| io_error(path, e))?;
        if path.ancestors().any(Path::is_symlink) {
            return Err(adoption("linked receipt path"));
        }
        persist_receipt(temporary, path, |source, destination, error| {
            let operation = crate::executor_text::IoOperation::Replace;
            let class = crate::executor_text::windows_error_code(&error, operation).0;
            let rendered = crate::adoption_fs::windows_error(
                &error,
                Some(source),
                Some(destination),
                operation,
                crate::executor_text::FilenameArgument::Path,
            );
            Error::Io {
                class,
                message: rendered
                    .strip_prefix(&format!("{class}: "))
                    .unwrap()
                    .to_owned(),
            }
        })
    }
}

// Keep persistence executable on Mac while replacing only the platform renderer.
#[cfg(any(windows, test))]
fn persist_receipt(
    temporary: tempfile::NamedTempFile,
    path: &Path,
    render: impl FnOnce(&Path, &Path, io::Error) -> Error,
) -> Result<(), Error> {
    temporary
        .persist(path)
        .map_err(|e| render(e.file.path(), path, e.error))?;
    Ok(())
}

pub(super) fn install_evaluator<H: Host + ?Sized>(
    root: &Path,
    source: &Path,
    local: Option<&Path>,
    host: &mut H,
) -> Option<Value> {
    let system = match std::env::consts::OS {
        "macos" => "Darwin",
        "linux" => "Linux",
        "windows" => "Windows",
        _ => "",
    };
    let target = crate::mir_core::capabilities::native::host_target(system, std::env::consts::ARCH);
    let native_artifacts = host.env("MIR_CAPABILITY_NATIVE_ARTIFACTS");
    let home = host
        .env(if cfg!(windows) { "USERPROFILE" } else { "HOME" })
        .map(PathBuf::from);
    struct ArtifactHost<'a, H: Host + ?Sized>(&'a mut H);
    impl<H: Host + ?Sized> adoption_native::InstallHost for ArtifactHost<'_, H> {
        fn read(&mut self, url: &str, size: u64) -> io::Result<Vec<u8>> {
            if !url.starts_with("http://") && !url.starts_with("https://") {
                return crate::mir_core::capabilities::native::read(url, size);
            }
            let result =
                crate::mir_cli::embedding_http::HttpTransport::default().artifact(url, size);
            let response = match result {
                Ok(response) => response,
                Err(error) => {
                    if error.class == "UnsupportedProtocol" {
                        self.0
                            .stderr(&format!("{}: {}\n", error.class, error.message))?;
                    }
                    return Err(io::Error::other(error.message));
                }
            };
            if !(200..300).contains(&response.status) {
                return Err(io::Error::other(format!("HTTP {}", response.status)));
            }
            if response.body.len() as u64 > size {
                return Err(io::Error::other("native artifact exceeds recorded size"));
            }
            Ok(response.body)
        }
    }
    adoption_native::install_evaluator(
        root,
        &adoption_native::InstallOptions {
            target: target.as_deref(),
            native_artifacts: native_artifacts.as_deref(),
            source_root: Some(source),
            local_source: local,
            home: home.as_deref(),
            ..Default::default()
        },
        &mut ArtifactHost(host),
    )
}

fn resolve(path: &Path, cwd: &Path, host: &mut dyn Host) -> Result<PathBuf, Error> {
    let text = path
        .to_str()
        .ok_or_else(|| adoption("non-UTF-8 project root"))?;
    let path = if text == "~" || text.starts_with("~/") {
        let home = host
            .env(if cfg!(windows) { "USERPROFILE" } else { "HOME" })
            .ok_or_else(|| adoption("Could not determine home directory."))?;
        PathBuf::from(home).join(text.strip_prefix("~/").unwrap_or(""))
    } else {
        path.to_owned()
    };
    let path = if path.is_absolute() {
        path
    } else {
        cwd.join(path)
    };
    if path.exists() {
        let resolved = fs::canonicalize(&path).map_err(|e| io_error(&path, e))?;
        // canonicalize adds a verbatim prefix on Windows; pathlib.resolve does not.
        #[cfg(windows)]
        let resolved = PathBuf::from(
            resolved
                .to_str()
                .ok_or_else(|| adoption("non-UTF-8 project root"))?
                .trim_start_matches("\\\\?\\"),
        );
        return Ok(resolved);
    }
    // Path.resolve(strict=False) also resolves existing ancestors of absent targets.
    let parent = path
        .parent()
        .ok_or_else(|| adoption("project root has no parent"))?;
    let parent = resolve(parent, cwd, host)?;
    match path.file_name() {
        Some(name) => Ok(parent.join(name)),
        None => Ok(parent),
    }
}

pub fn main(
    argv: Option<&[&str]>,
    source: &Path,
    package: &Path,
    host: &mut dyn Host,
) -> Result<i32, Error> {
    let cwd = host.cwd().map_err(|e| io_error(Path::new("."), e))?;
    let ambient = if argv.is_none() {
        host.argv()
    } else {
        Vec::new()
    };
    let ambient_refs: Vec<_> = ambient.iter().skip(1).map(String::as_str).collect();
    let arguments = argv.unwrap_or(&ambient_refs);
    let parsed = parse(arguments, &cwd);
    host.stdout(parsed[1].as_str().unwrap_or(""))
        .map_err(|e| io_error(Path::new("<stdout>"), e))?;
    host.stderr(parsed[2].as_str().unwrap_or(""))
        .map_err(|e| io_error(Path::new("<stderr>"), e))?;
    if let Some(code) = parsed[0]["error"][1].as_str() {
        return Err(Error::SystemExit(code.parse().unwrap_or(2)));
    }
    let ns = &parsed[0]["value"];
    let root = resolve(
        Path::new(ns["project_root"].as_str().unwrap_or(".")),
        &cwd,
        host,
    )?;
    let before = changes::snapshot_project(&root).map_err(|e| io_error(&root, e))?;
    let apply = ns["apply"] == true;
    let as_json = ns["json"] == true;
    let (manifest, manifest_bytes) =
        match load_json_bytes(&root.join("config/bootstrap-adoption.json"), host) {
            Ok(loaded) => loaded,
            Err(Error::Adoption(error)) => {
                emit(
                    as_json,
                    &json!({"schema_version":1,"status":"not_ready","apply":apply,
                "receipt_written":false,"changed_paths":[],"errors":[error.to_string()]}),
                    host,
                )?;
                return Ok(2);
            }
            Err(error) => return Err(error),
        };
    let mut errors = Vec::new();
    if manifest["schema_version"].as_f64() != Some(1.0) && manifest["schema_version"] != true {
        errors.push("config/bootstrap-adoption.json schema_version must be 1".into());
    }
    const ALLOWED: &[&str] = &[
        "$schema",
        "schema_version",
        "project_slug",
        "repository_archetype",
        "profile",
        "mir_yoke_source_commit",
        "surfaces",
    ];
    let extra: Vec<_> = manifest
        .as_object()
        .into_iter()
        .flat_map(|o| o.keys())
        .filter(|k| !ALLOWED.contains(&k.as_str()))
        .cloned()
        .collect();
    if !extra.is_empty() {
        errors.push(format!(
            "adoption manifest has unknown fields: {}",
            list_repr(&extra)
        ));
    }
    let commit = &manifest["mir_yoke_source_commit"];
    if !commit.as_str().is_some_and(|s| {
        s.len() == 40
            && s.bytes()
                .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
    }) {
        errors.push("mir_yoke_source_commit must be a lowercase 40-hex Git commit".into());
    }
    let mut check = |kind, value, errors: &mut Vec<String>| {
        let result = validate(
            ValidationRequest {
                root: &root,
                kind,
                value,
            },
            source,
            package,
            host,
        )?;
        errors.extend(result.errors);
        Ok::<_, Error>((result.evidence, result.exceptions))
    };
    let (profile, _) = check(ValidationKind::Profile, &manifest, &mut errors)?;
    let (surfaces, exceptions) = check(ValidationKind::SurfaceContract, &manifest, &mut errors)?;
    let mut gate = json!({"status":"not_checked"});
    let mut launcher = gate.clone();
    let mut content = gate.clone();
    let mut memory = json!({"status":"not_checked","queries":[]});
    let mut phase2 = json!({"status":"not_checked","exceptions":[]});
    if surfaces.as_object().is_some_and(|o| !o.is_empty()) {
        for (name, kind, relative, label, output) in [
            (
                "bootstrap_start_gate",
                ValidationKind::BootstrapGate,
                ".claude/hooks/_lib/bootstrap-gate.sh",
                "bootstrap gate helper",
                &mut gate,
            ),
            (
                "managed_python_launcher",
                ValidationKind::PythonLauncher,
                LAUNCHER,
                "managed Python launcher",
                &mut launcher,
            ),
        ] {
            let surface = &surfaces[name];
            let disposition = surface["disposition"].as_str().unwrap_or("");
            if ["applied", "repository_owned"].contains(&disposition) {
                check(
                    ValidationKind::RequiredRuntimeEvidence(name),
                    surface,
                    &mut errors,
                )?;
                *output = check(kind, &Value::Null, &mut errors)?.0;
                if disposition == "applied" {
                    output["canonical"] = check(
                        ValidationKind::CanonicalAppliedHelper { relative, label },
                        &Value::Null,
                        &mut errors,
                    )?
                    .0;
                }
            }
        }
        let surface = &surfaces["content_onboarding"];
        let disposition = surface["disposition"].as_str().unwrap_or("");
        let content_error =
            manifest["profile"] == "content_workspace" && disposition == "not_applicable";
        if content_error {
            errors.push("content_workspace cannot mark content_onboarding not_applicable".into());
        } else if ["applied", "repository_owned"].contains(&disposition) {
            content = check(
                ValidationKind::ContentOnboarding,
                &manifest["profile"],
                &mut errors,
            )?
            .0;
        } else if ["not_applicable", "exception"].contains(&disposition) {
            content = json!({"status":disposition,"reason":surface["reason"]});
        }
        let surface = &surfaces["memory_acceptance"];
        if ["applied", "repository_owned"].contains(&surface["disposition"].as_str().unwrap_or(""))
        {
            memory = check(ValidationKind::Memory, surface, &mut errors)?.0;
        } else if surface["disposition"] == "exception" {
            memory = json!({"status":"exception","queries":[],"reason":surface["reason"]});
        }
        let surface = &surfaces["phase2_spec"];
        if ["applied", "repository_owned"].contains(&surface["disposition"].as_str().unwrap_or(""))
        {
            phase2 = check(ValidationKind::Phase2, surface, &mut errors)?.0;
        } else if surface["disposition"] == "exception" {
            phase2 = json!({"status":"exception","exceptions":exceptions.iter()
                .find(|v| v["surface"] == "phase2_spec").into_iter().collect::<Vec<_>>()});
        }
    }
    let evidence = match evidence_digests(&root, &surfaces, host) {
        Ok(evidence) => evidence,
        Err(Error::Adoption(error)) => {
            errors.push(error.to_string());
            Vec::new()
        }
        Err(error) => return Err(error),
    };
    let status = if errors.is_empty() {
        "ready"
    } else {
        "not_ready"
    };
    let mut receipt = json!({"schema_version":1,"status":status,
        "mode":"existing_repository_adoption",
        "project":{"slug":manifest["project_slug"],
            "repository_archetype":manifest["repository_archetype"],
            "profile":manifest["profile"]}, "source":{"mir_yoke_commit":commit},
        "manifest":{"path":"config/bootstrap-adoption.json",
            "sha256":crate::digest::sha256(&manifest_bytes)},
        "evidence":evidence,"profile":profile,"surfaces":surfaces,"bootstrap_start_gate":gate,
        "managed_python_launcher":launcher,"content_onboarding":content,"memory_acceptance":memory,
        "phase2":phase2,"exceptions":exceptions,"errors":errors});
    let mut receipt_written = false;
    if apply && status == "ready" {
        if let Some(evaluator) = host.install_evaluator(
            &root,
            source,
            ns["native_evaluator"].as_str().map(Path::new),
        ) {
            receipt["native_evaluator"] = evaluator;
        }
        host.write_receipt(&root.join(".mir/bootstrap-receipt.json"), &receipt)?;
        receipt_written = true;
    }
    let mut report = receipt;
    report["apply"] = json!(apply);
    report["receipt_written"] = json!(receipt_written);
    report["changed_paths"] = json!(changes::changed_paths(
        &before,
        &changes::snapshot_project(&root).map_err(|e| io_error(&root, e))?
    ));
    report["reference_assets"] = json!(
        surfaces
            .as_object()
            .into_iter()
            .flat_map(|o| o.iter())
            .map(
                |(name, surface)| json!({"asset":name,"disposition":surface["disposition"],
            "evidence_paths":surface.get("evidence_paths").cloned().unwrap_or_else(|| json!([]))})
            )
            .collect::<Vec<_>>()
    );
    emit(as_json, &report, host)?;
    Ok(if status == "ready" { 0 } else { 2 })
}

#[cfg(test)]
mod receipt_tests {
    use super::*;

    #[test]
    fn pc3_receipt_real_directory_failure_keeps_both_names() {
        let root = tempfile::tempdir().unwrap();
        let root = root.path().canonicalize().unwrap();
        let destination = root.join("receipt.json");
        fs::create_dir(&destination).unwrap();
        let temporary = tempfile::Builder::new()
            .prefix(".bootstrap-receipt.json.")
            .tempfile_in(&root)
            .unwrap();
        let source = temporary.path().to_owned();
        let result = persist_receipt(temporary, &destination, |from, to, error| {
            assert_eq!(from, source);
            assert_eq!(to, destination);
            assert!(error.raw_os_error().is_some());
            // The error is a real persist failure; only Windows rendering is simulated.
            Error::Io {
                class: "PermissionError",
                message: format!(
                    "[WinError 5] access denied: {} -> {}",
                    repr(&wire(from)),
                    repr(&wire(to))
                ),
            }
        })
        .unwrap_err();
        assert_eq!(result.class(), "PermissionError");
        assert_eq!(
            result.to_string(),
            format!(
                "[WinError 5] access denied: {} -> {}",
                repr(&wire(&source)),
                repr(&wire(&destination))
            )
        );
        assert!(!source.exists());
        assert!(destination.is_dir());
        assert_eq!(fs::read_dir(root).unwrap().count(), 1);
    }

    #[test]
    fn public_writer_selects_windows_serialization() {
        let fixture: Value = serde_json::from_str(include_str!(
            "../../tests/fixtures/y-e14-receipt-bytes.json"
        ))
        .unwrap();
        let temp = tempfile::tempdir().unwrap();
        let base = temp.path().canonicalize().unwrap();
        for windows in [false, true] {
            let path = base.join("receipt.json");
            write_receipt_for_platform(&path, &fixture["payload"], windows, |_, _| Ok(())).unwrap();
            let logical = fixture["logical"].as_str().unwrap();
            let expected = if windows {
                logical.replace('\n', "\r\n")
            } else {
                logical.into()
            };
            assert_eq!(
                fs::read(path).unwrap(),
                expected.as_bytes(),
                "windows={windows}"
            );
        }
    }

    #[test]
    fn windows_receipt_bytes_match_pinned_p3() {
        let fixture: Value =
            serde_json::from_str(include_str!("../../tests/fixtures/w2/unify2-s4.json")).unwrap();
        for (mode, record) in fixture["records"].as_object().unwrap() {
            let logical = record["value"]["receipts"][".mir/bootstrap-receipt.json"]
                .as_str()
                .unwrap();
            let payload: Value = serde_json::from_str(logical).unwrap();
            let windows = receipt_json(&payload, true).unwrap();
            let hex: String = windows
                .as_bytes()
                .iter()
                .map(|b| format!("{b:02x}"))
                .collect();
            assert_eq!(
                json!(hex),
                record["files"][".mir/bootstrap-receipt.json"],
                "{mode}"
            );
            assert_eq!(
                receipt_json(&payload, false).unwrap(),
                logical,
                "{mode}: Unix"
            );
        }
    }
}
