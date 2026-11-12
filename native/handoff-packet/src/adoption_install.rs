//! Private adoption host. Consumer Python dispatch remains unchanged.
#![forbid(unsafe_code)]
#![deny(clippy::unwrap_used, clippy::expect_used, clippy::panic)]
use handoff_packet::mir_cli::{
    adoption_native::{self, InstallOptions, LocalHost},
    project_hooks,
};
use serde_json::Value;
use std::{
    io::{self, Read, Write},
    path::Path,
};

fn path<'a>(request: &'a Value, name: &str) -> Option<&'a Path> {
    request.get(name)?.as_str().map(Path::new)
}
fn home_prefix(path: &Path) -> Option<&str> {
    path.components()
        .find(|part| !matches!(part, std::path::Component::CurDir))
        .and_then(|part| part.as_os_str().to_str())
        .filter(|part| part.starts_with('~'))
}
fn network_pin(pin: &Value) -> bool {
    pin.get("url").and_then(Value::as_str).is_some_and(|url| {
        matches!(
            handoff_packet::mir_core::capabilities::native::local_source(url),
            Ok(None)
        )
    })
}
fn dispatch(request: &Value) -> Option<(i32, Vec<u8>, Vec<u8>)> {
    let operation = request.get("operation")?.as_str()?;
    // Complete admission before any project read or write.
    match operation {
        "install-artifact" => {
            let root = path(request, "root")?;
            let name = request.get("name")?.as_str()?;
            if ![
                "bootstrap-gate",
                "runtime-verify",
                "executor-query",
                "delegation-gate",
                "project-hooks",
            ]
            .contains(&name)
            {
                return None;
            }
            let tilde = path(request, "local_source").and_then(home_prefix);
            if tilde.is_some_and(|part| part != "~") {
                // Named account lookup is outside this private local host subset.
                return None;
            }
            let environment_home = std::env::var_os("HOME").map(std::path::PathBuf::from);
            let home = path(request, "home").or(environment_home.as_deref());
            if home.is_none() && tilde == Some("~") {
                return None;
            }
            let source_root = path(request, "source_root");
            let explicit_pin = source_root.is_none()
                || request.get("artifact_pin").and_then(Value::as_bool) == Some(true);
            let disabled = request.get("disabled").and_then(Value::as_bool) == Some(true)
                || std::env::var("MIR_CAPABILITY_NATIVE_ARTIFACTS")
                    .ok()
                    .as_deref()
                    == Some("0");
            let options = InstallOptions {
                target: request.get("target").and_then(Value::as_str),
                native_artifacts: disabled.then_some("0"),
                source_root,
                local_source: path(request, "local_source"),
                artifact_pin: explicit_pin.then(|| request.get("pin")).flatten(),
                home,
            };
            if options.local_source.is_none() {
                let unsupported_size = if let Some(pin) = options.artifact_pin {
                    project_hooks::unsupported_read_size(pin)
                } else {
                    options.source_root.is_some_and(|source| {
                        project_hooks::unsupported_provider_read_size(source, name, options.target)
                    })
                };
                if unsupported_size {
                    return None;
                }
                let pin = options.artifact_pin.cloned().or_else(|| {
                    adoption_native::provider_pin(options.source_root?, name, options.target?)
                });
                if pin.as_ref().is_some_and(network_pin) {
                    return None;
                }
            }
            let result = adoption_native::install(root, name, &options, &mut LocalHost);
            let mut bytes = serde_json::to_vec(&result).ok()?;
            bytes.push(b'\n');
            Some((0, bytes, vec![]))
        }
        "project-hooks" => {
            let root = request.get("root")?.as_str()?;
            let action = request.get("action")?.as_str()?;
            if !["install", "check"].contains(&action) {
                return None;
            }
            let metadata = request.get("metadata")?;
            let target = request.get("target").and_then(Value::as_str);
            let disabled = request.get("disabled").and_then(Value::as_bool) == Some(true)
                || std::env::var("MIR_CAPABILITY_NATIVE_ARTIFACTS")
                    .ok()
                    .as_deref()
                    == Some("0");
            if target.is_some_and(|target| {
                project_hooks::unsupported_read_size(
                    &metadata["native_artifacts"]["project-hooks"]["targets"][target],
                )
            }) {
                return None;
            }
            if project_hooks::provider_pin(metadata, target, disabled)
                .is_ok_and(|(_, pin)| network_pin(&pin))
            {
                return None;
            }
            Some(project_hooks::main(
                &[action, "--project-root", root],
                metadata,
                target,
                disabled,
                |root, pin| {
                    adoption_native::install_project_hooks(
                        root,
                        &InstallOptions {
                            target,
                            artifact_pin: Some(pin),
                            ..InstallOptions::default()
                        },
                        &mut LocalHost,
                    )
                },
                project_hooks::run_probe,
            ))
        }
        _ => None,
    }
}
fn main() {
    let args: Vec<_> = std::env::args_os().skip(1).collect();
    if args.as_slice() == ["--mir-warmup"] {
        return;
    }
    if !args.is_empty() {
        std::process::exit(64);
    }
    let mut bytes = Vec::new();
    if io::stdin().read_to_end(&mut bytes).is_err() {
        std::process::exit(64);
    }
    let request = match serde_json::from_slice::<Value>(&bytes) {
        Ok(value) => value,
        Err(_) => std::process::exit(64),
    };
    let Some((code, stdout, stderr)) = dispatch(&request) else {
        std::process::exit(64);
    };
    if io::stdout().write_all(&stdout).is_err() || io::stderr().write_all(&stderr).is_err() {
        std::process::exit(64);
    }
    std::process::exit(code);
}
