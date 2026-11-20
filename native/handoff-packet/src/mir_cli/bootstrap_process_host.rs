//! Native process/environment boundary and bounded, frozen schema validation.
use super::{CommandOutput, CommandRequest, Error, Host, authored};
use std::{
    fs,
    path::{Component, Path, PathBuf},
    process::{Command, Stdio},
};

#[derive(Default)]
pub struct ProductionHost {
    #[cfg(unix)]
    manager: Option<crate::mir_cli::capability_manager::ProductionManager>,
}
impl ProductionHost {
    /// Import once before the caller redirects text or initializes the provider.
    #[cfg(unix)]
    pub fn import_capabilities(
        &mut self,
        cli: &Path,
        root: &Path,
        output: crate::mir_cli::capability_manager::Output,
    ) -> Result<&mut crate::mir_cli::capability_manager::ProductionManager, Error> {
        match self.manager {
            Some(ref mut manager) => Ok(manager),
            None => {
                let mut manager =
                    crate::mir_cli::capability_manager::ProductionManager::start_with_output(
                        cli, root, output,
                    )
                    .map_err(|e| os_error(cli, e))?;
                manager.import()?;
                Ok(self.manager.insert(manager))
            }
        }
    }
}

fn os_error(path: &Path, error: std::io::Error) -> Error {
    let class = authored::io_error(path, std::io::Error::from(error.kind())).class;
    Error::new(
        class,
        crate::executor_brief_profile::python_os_error_message(&error, path),
    )
}

impl Host for ProductionHost {
    #[cfg(unix)]
    fn capability_import_for(&mut self, root: &Path, finalize: bool) -> Result<(), Error> {
        use crate::mir_cli::capability_manager::Output;
        if self.manager.is_none() {
            let cli = std::env::current_exe().map_err(|e| os_error(Path::new("."), e))?;
            self.import_capabilities(
                &cli,
                root,
                if finalize {
                    Output::Finalize
                } else {
                    Output::Activate
                },
            )?;
        }
        Ok(())
    }
    #[cfg(unix)]
    fn capability_main(&mut self, argv: &[String]) -> Result<super::CapabilityOutput, Error> {
        let mut manager = self
            .manager
            .take()
            .ok_or_else(|| Error::new("RuntimeError", "capability manager was not imported"))?;
        let mut output = super::CapabilityOutput::run(argv, &mut manager)?;
        let captured = crate::python_json::Text::from_wtf8(&manager.captured)
            .map_err(authored::adopt_error)?;
        output.stdout = captured.concat(&output.stdout);
        if argv.first().is_some_and(|s| s == "finalize") && !output.stderr.is_empty() {
            use std::io::Write;
            use std::os::fd::AsFd;
            let stream_error = |e| {
                let mut error = os_error(Path::new(""), e);
                error.message = error
                    .message
                    .strip_suffix(": ''")
                    .unwrap_or(&error.message)
                    .to_owned();
                error
            };
            let bytes = crate::executor_text::encode_console(&output.stderr.py_str(), true)
                .map_err(|e| Error::new("UnicodeEncodeError", e))?;
            let descriptor = std::io::stderr()
                .as_fd()
                .try_clone_to_owned()
                .map_err(stream_error)?;
            std::fs::File::from(descriptor)
                .write_all(&bytes)
                .map_err(stream_error)?;
            output.stderr = "".into();
        }
        Ok(output)
    }
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
    fn validate_boundary_schema_source(
        &mut self,
        _value: &serde_json::Value,
        _schema: &serde_json::Value,
        instance: &str,
        schema: &str,
    ) -> Result<(), Error> {
        super::schema::validate(instance, schema)
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
                // A Windows prefix is not an absolute anchor by itself: in
                // particular, \\?\C: cannot be canonicalized before RootDir.
                // UNC prefixes likewise need their (possibly implicit) root.
                Component::Prefix(_) => resolved.push(part),
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
        #[cfg(windows)]
        if !matches!(absolute.components().next(), Some(Component::Prefix(p)) if p.kind().is_verbatim())
        {
            // pathlib preserves an explicitly supplied verbatim prefix, but
            // ordinary drive/UNC paths keep their ordinary spelling.
            resolved = crate::supply::plain(resolved);
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
    fn python_runtime(&mut self) -> Result<(String, bool), Error> {
        // Match run-python's installed-console binding, never a PATH interpreter.
        // Only stdlib observations run here; no provider code is imported.
        let cli = std::env::current_exe().map_err(|e| os_error(Path::new("."), e))?;
        #[cfg(target_os = "macos")]
        let cli = cli.canonicalize().map_err(|e| os_error(&cli, e))?;
        let directory = cli.parent().unwrap_or(Path::new("."));
        let python = directory.join(if cfg!(windows) {
            "python.exe"
        } else {
            "python"
        });
        let result = Command::new(&python)
            .args([
                "-I",
                "-X",
                "utf8",
                "-c",
                concat!(
                    "import json, os, platform, sys; ",
                    "print('\\0' + json.dumps([platform.python_version(), ",
                    "bool(os.environ.get('VIRTUAL_ENV') or sys.prefix != sys.base_prefix)]) + '\\0')"
                ),
            ])
            .stdin(Stdio::null())
            .output()
            .map_err(|e| os_error(&python, e))?;
        if !result.status.success() {
            return Err(Error::new(
                "RuntimeError",
                format!("Python runtime attestation failed: {}", result.status),
            ));
        }
        // Keep site's Python 3.12 venv prefixes, excluding startup output from the frame.
        let mut frame = result.stdout.rsplitn(3, |byte| *byte == 0);
        let observation = match (frame.next(), frame.next(), frame.next()) {
            (Some(_), Some(json), Some(_)) => json,
            _ => &[],
        };
        serde_json::from_slice(observation)
            .map_err(|_| Error::new("RuntimeError", "invalid Python runtime attestation"))
    }
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
        #[cfg_attr(not(unix), allow(unused_mut))]
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

fn validate_schema(
    value: &serde_json::Value,
    schema: &serde_json::Value,
    _instance_repr: Option<&str>,
) -> Result<(), Error> {
    super::schema::validate(&value.to_string(), &schema.to_string())
}
