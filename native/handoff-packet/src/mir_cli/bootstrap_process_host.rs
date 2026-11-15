//! Native process/environment boundary and bounded, frozen schema validation.
use super::{CommandOutput, CommandRequest, Error, Host, authored};
use std::{
    fs,
    path::{Component, Path, PathBuf},
    process::{Command, Stdio},
};

pub struct ProductionHost;

fn os_error(path: &Path, error: std::io::Error) -> Error {
    let class = authored::io_error(path, std::io::Error::from(error.kind())).class;
    Error::new(
        class,
        crate::executor_brief_profile::python_os_error_message(&error, path),
    )
}

impl Host for ProductionHost {
    fn validate_boundary_schema(
        &mut self,
        value: &serde_json::Value,
        schema: &serde_json::Value,
    ) -> Result<(), Error> {
        validate_schema(value, schema, None)
    }
    fn validate_boundary_schema_repr(
        &mut self,
        value: &serde_json::Value,
        schema: &serde_json::Value,
        instance_repr: &str,
    ) -> Result<(), Error> {
        validate_schema(value, schema, Some(instance_repr))
    }
    fn env(&mut self, name: &str) -> Option<String> {
        std::env::var(name).ok()
    }
    fn which(&mut self, name: &str) -> Option<PathBuf> {
        let executable = |path: &Path| {
            #[cfg(unix)]
            {
                path.is_file() && crate::executor_process_unix::path_access(path, libc::X_OK)
            }
            #[cfg(not(unix))]
            {
                path.is_file()
            }
        };
        if Path::new(name)
            .parent()
            .is_some_and(|p| !p.as_os_str().is_empty())
        {
            return executable(Path::new(name)).then(|| PathBuf::from(name));
        }
        let path = std::env::var_os("PATH").unwrap_or_else(|| "/bin:/usr/bin".into());
        std::env::split_paths(&path)
            .map(|p| p.join(name))
            .find(|p| executable(p))
    }
    fn resolve(&mut self, path: &Path) -> Result<PathBuf, Error> {
        let absolute = if path.is_absolute() {
            path.to_owned()
        } else {
            std::env::current_dir()
                .map_err(|e| os_error(path, e))?
                .join(path)
        };
        let mut resolved = PathBuf::new();
        for part in absolute.components() {
            match part {
                Component::CurDir => (),
                Component::ParentDir => {
                    resolved.pop();
                }
                _ => {
                    resolved.push(part);
                    match fs::canonicalize(&resolved) {
                        Ok(path) => resolved = path,
                        Err(e)
                            if matches!(
                                e.kind(),
                                std::io::ErrorKind::NotFound | std::io::ErrorKind::NotADirectory
                            ) =>
                        {
                            // canonicalize cannot follow a dangling link, but non-strict
                            // pathlib resolution still resolves its lexical target.
                            if let Ok(target) = fs::read_link(&resolved) {
                                resolved.pop();
                                resolved = self.resolve(&resolved.join(target))?;
                            }
                        }
                        #[cfg(unix)]
                        Err(e) if e.raw_os_error() == Some(libc::ELOOP) => {
                            return Err(Error::new(
                                "RuntimeError",
                                format!(
                                    "Symlink loop from {}",
                                    crate::executor_execute::repr(&resolved.to_string_lossy())
                                ),
                            ));
                        }
                        Err(e) => return Err(os_error(&resolved, e)),
                    }
                }
            }
        }
        Ok(resolved)
    }
    fn expanduser(&mut self, path: &Path) -> Result<PathBuf, Error> {
        let mut parts = path.components();
        let Some(Component::Normal(first)) = parts.next() else {
            return Ok(path.into());
        };
        let Some(first) = first.to_str().filter(|s| s.starts_with('~')) else {
            return Ok(path.into());
        };
        let home = if first == "~" {
            std::env::var_os(if cfg!(windows) { "USERPROFILE" } else { "HOME" }).map(PathBuf::from)
        } else {
            None
        };
        #[cfg(unix)]
        let home = home.or_else(|| {
            crate::runtime_account_home((first != "~").then(|| std::ffi::OsStr::new(&first[1..])))
        });
        let home =
            home.ok_or_else(|| Error::new("RuntimeError", "Could not determine home directory."))?;
        Ok(home.join(parts.as_path()))
    }
    fn is_dir(&mut self, path: &Path) -> bool {
        path.is_dir()
    }
    fn writable(&mut self, path: &Path) -> bool {
        #[cfg(unix)]
        {
            crate::executor_process_unix::path_access(path, libc::W_OK)
        }
        #[cfg(not(unix))]
        {
            fs::metadata(path).is_ok_and(|m| !m.permissions().readonly())
        }
    }
    fn device(&mut self, path: &Path) -> Result<u64, Error> {
        #[cfg(unix)]
        {
            use std::os::unix::fs::MetadataExt;
            Ok(fs::metadata(path).map_err(|e| os_error(path, e))?.dev())
        }
        #[cfg(not(unix))]
        {
            let _ = path;
            Err(Error::new(
                "NotImplementedError",
                "bootstrap device observation requires Unix",
            ))
        }
    }
    fn platform_release(&mut self) -> Result<String, Error> {
        #[cfg(unix)]
        {
            crate::executor_process_unix::platform_release().map_err(|e| {
                Error::new(
                    "OSError",
                    format!(
                        "[Errno {}] {}",
                        e.raw_os_error().unwrap_or(0),
                        crate::executor_brief_profile::python_os_error_text(&e)
                    ),
                )
            })
        }
        #[cfg(not(unix))]
        {
            Err(Error::new(
                "NotImplementedError",
                "bootstrap platform release requires Unix",
            ))
        }
    }
    // A native executable has no Python interpreter version/prefix to attest.
    fn python_argv0(&mut self) -> PathBuf {
        std::env::args_os()
            .next()
            .unwrap_or_else(|| "mir".into())
            .into()
    }
    fn run(&mut self, request: &CommandRequest) -> Result<CommandOutput, Error> {
        execute(request, false)
    }
    fn slim_run_clean(&mut self, request: &CommandRequest) -> Result<CommandOutput, Error> {
        execute(request, true)
    }
    fn slim_process_alive(&mut self, pid: i64) -> Result<bool, Error> {
        if pid <= 0 {
            return Ok(false);
        }
        let pid = i32::try_from(pid)
            .map_err(|_| Error::new("OverflowError", "signed integer is greater than maximum"))?;
        #[cfg(unix)]
        {
            crate::executor_process_unix::process_alive(pid).map_err(|e| {
                Error::new(
                    "OSError",
                    format!(
                        "[Errno {}] {}",
                        e.raw_os_error().unwrap_or(0),
                        crate::executor_brief_profile::python_os_error_text(&e)
                    ),
                )
            })
        }
        #[cfg(not(unix))]
        {
            let _ = pid;
            Err(Error::new(
                "NotImplementedError",
                "bootstrap process liveness requires Unix",
            ))
        }
    }
}

fn execute(request: &CommandRequest, clean: bool) -> Result<CommandOutput, Error> {
    let executable = request
        .argv
        .first()
        .ok_or_else(|| Error::new("IndexError", "list index out of range"))?;
    if request.argv.iter().any(|s| s.contains('\0'))
        || request.cwd.as_os_str().as_encoded_bytes().contains(&0)
        || request
            .environment
            .iter()
            .any(|(k, v)| k.contains('\0') || v.contains('\0'))
    {
        return Err(Error::new("ValueError", "embedded null byte"));
    }
    let mut command = Command::new(executable);
    command
        .args(&request.argv[1..])
        .current_dir(&request.cwd)
        .envs(&request.environment)
        .stdin(if request.stdin_null {
            Stdio::null()
        } else {
            Stdio::inherit()
        })
        .stdout(if request.capture_output {
            Stdio::piped()
        } else {
            Stdio::inherit()
        })
        .stderr(if request.capture_output {
            Stdio::piped()
        } else {
            Stdio::inherit()
        });
    if clean {
        for key in ["PYTHONPATH", "VIRTUAL_ENV", "UV_PROJECT_ENVIRONMENT"] {
            command.env_remove(key);
        }
    }
    let output = command.output().map_err(|e| {
        let mut cwd_accessible = request.cwd.is_dir();
        #[cfg(unix)]
        {
            cwd_accessible &= crate::executor_process_unix::path_access(&request.cwd, libc::X_OK);
        }
        if cwd_accessible {
            os_error(Path::new(executable), e)
        } else {
            let error = os_error(&request.cwd, e);
            let path = crate::executor_execute::repr(&request.cwd.to_string_lossy());
            Error::new(
                error.class,
                error
                    .message
                    .replace(&format!(": {path}"), &format!(": PosixPath({path})")),
            )
        }
    })?;
    #[cfg(unix)]
    let returncode = {
        use std::os::unix::process::ExitStatusExt;
        output
            .status
            .code()
            .unwrap_or_else(|| -output.status.signal().unwrap_or(1))
    };
    #[cfg(not(unix))]
    let returncode = output.status.code().unwrap_or(1);
    let mut result = CommandOutput {
        returncode,
        stdout: output.stdout,
        stderr: output.stderr,
    };
    if request.text {
        result.stdout = authored::decode(result.stdout)?.into_bytes();
        result.stderr = authored::decode(result.stderr)?.into_bytes();
    }
    Ok(result)
}

// shortcut: admit only the Y-E16 measured keywords. Extend with pinned diagnostics
// before admitting compound schemas, schema errors, or multiline pprint output.
fn validate_schema(
    value: &serde_json::Value,
    schema: &serde_json::Value,
    instance_repr: Option<&str>,
) -> Result<(), Error> {
    let refused = || {
        Error::new(
            "NotImplementedError",
            "bootstrap boundary schema validator is not connected",
        )
    };
    if schema == true || schema.as_object().is_some_and(|m| m.is_empty()) {
        return Ok(());
    }
    let fields = schema
        .as_object()
        .filter(|m| m.len() == 1)
        .ok_or_else(refused)?;
    if fields.get("type").and_then(|t| t.as_str()) == Some("object") && value.is_object() {
        return Ok(());
    }
    let required = fields
        .get("required")
        .and_then(|v| v.as_array())
        .ok_or_else(refused)?;
    // Invalid required lists need SchemaError, never a successful empty validation.
    if required.len() != 1 || required.iter().any(|v| !v.is_string()) {
        return Err(refused());
    }
    let object = value.as_object().ok_or_else(refused)?;
    for key in required {
        let key = key.as_str().ok_or_else(refused)?;
        if object.contains_key(key) {
            continue;
        }
        let instance = instance_repr.ok_or_else(refused)?;
        let schema_text = crate::executor_brief_render::python_value_repr(schema);
        // jsonschema uses pprint(width=72, sort_dicts=False) here.
        // Refuse outside the frozen single-line representation envelope.
        if !instance.is_ascii()
            || !schema_text.is_ascii()
            || instance.len() > 72
            || schema_text.len() > 72
        {
            return Err(refused());
        }
        return Err(Error::new(
            "ValidationError",
            format!(
                "{} is a required property\n\nFailed validating 'required' in schema:\n    {}\n\nOn instance:\n    {}",
                crate::executor_execute::repr(key),
                schema_text,
                instance,
            ),
        ));
    }
    Ok(())
}
