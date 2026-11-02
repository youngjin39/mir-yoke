//! Library admission only: no database access, provider launch, or CLI dispatch.
//! Unported grammar and target-local Python options decline before any hook import.
use crate::local_bridge::{BridgeConfig, BridgeError, LocalBridge};
use serde_json::{Value, json};
use std::{
    collections::BTreeMap,
    ffi::OsString,
    fs, io,
    path::{Path, PathBuf},
    process::Command,
    time::Duration,
};

pub struct Request<'a> {
    pub argv: &'a [String],
    pub cwd: &'a Path,
    /// Package repository, independent of cwd and HOME.
    pub invoking_home: &'a Path,
    pub environment: &'a BTreeMap<OsString, OsString>,
    pub interpreter: &'a Path,
    pub bridge_script: &'a Path,
}
#[derive(Debug, PartialEq)]
pub enum Admission {
    Admitted {
        root: PathBuf,
        cross_target: bool,
        args: Value,
    },
    Refused {
        code: i32,
        stderr: Vec<u8>,
    },
    Decline {
        code: i32,
        reason: &'static str,
    },
}
fn decline(reason: &'static str) -> Admission {
    Admission::Decline { code: 64, reason }
}
fn resolved(path: &Path, cwd: &Path) -> io::Result<PathBuf> {
    let path = if path.is_absolute() {
        path.to_owned()
    } else {
        cwd.join(path)
    };
    match fs::canonicalize(&path) {
        Ok(path) => Ok(path),
        Err(e) if e.kind() == io::ErrorKind::NotFound => {
            let Some(parent) = path.parent() else {
                return Err(e);
            };
            let Some(name) = path.file_name() else {
                return Err(e);
            };
            Ok(resolved(parent, cwd)?.join(name))
        }
        Err(e) => Err(e),
    }
}
fn path_value(path: &Path) -> Option<Value> {
    Some(json!({"$type":"path","value":path.to_str()?}))
}
fn git(request: &Request<'_>, root: &Path, flag: &str) -> io::Result<std::process::Output> {
    Command::new("git")
        .args(["-C"])
        .arg(root)
        .args(["rev-parse", flag])
        .current_dir(request.cwd)
        .env_clear()
        .envs(request.environment)
        .output()
}
fn refusal(message: String) -> Admission {
    Admission::Refused {
        code: 1,
        stderr: format!("[mir_executor] {message}\n").into_bytes(),
    }
}
/// Malformed/unknown argv is left untouched for Python's argparse diagnostics.
/// A target with any local.py is currently declined: determining dynamic option
/// registration by importing it would run target code before the home guard.
pub fn admit(request: Request<'_>) -> Result<Admission, BridgeError> {
    let Some(command) = request.argv.first() else {
        return Ok(decline("help"));
    };
    if command == "resume" {
        return Ok(decline("saved target requires Python resume"));
    }
    let schema: Value = serde_json::from_str(include_str!(
        "../tests/fixtures/executor_admission_schema.json"
    ))?;
    let Some(options) = schema[command].as_array() else {
        return Ok(decline("unsupported command"));
    };
    let mut args = json!({"subcommand":command, "jobs_db":null});
    for option in options {
        if option["default"] != "==SUPPRESS==" {
            args[option["dest"].as_str().unwrap_or("")] = if option["default"]["value"] == "$cwd" {
                let Some(value) = path_value(request.cwd) else {
                    return Ok(decline("non UTF-8 path"));
                };
                value
            } else {
                option["default"].clone()
            };
        }
    }
    let mut index = 1;
    while index < request.argv.len() {
        let token = &request.argv[index];
        let (flag, inline) = token
            .split_once('=')
            .map(|(a, b)| (a, Some(b)))
            .unwrap_or((token.as_str(), None));
        let Some(option) = options.iter().find(|o| {
            o["flags"]
                .as_array()
                .is_some_and(|f| f.iter().any(|v| v == flag))
        }) else {
            return Ok(decline("unknown option"));
        };
        let Some(dest) = option["dest"].as_str() else {
            return Ok(decline("unknown destination"));
        };
        let value = match option["kind"].as_str() {
            Some("_StoreTrueAction" | "BooleanOptionalAction") => {
                if inline.is_some() {
                    return Ok(decline("boolean value"));
                };
                json!(!flag.starts_with("--no-"))
            }
            Some("_StoreAction" | "_AppendAction") => {
                let raw = if let Some(raw) = inline {
                    raw
                } else {
                    index += 1;
                    let Some(raw) = request.argv.get(index) else {
                        return Ok(decline("missing option value"));
                    };
                    if raw.starts_with('-') {
                        return Ok(decline("ambiguous option value"));
                    };
                    raw
                };
                match option["type"].as_str() {
                    Some("Path") => json!({"$type":"path","value":raw}),
                    Some("int" | "_positive_int" | "_nonnegative_int") => {
                        let Ok(n) = raw.parse::<i64>() else {
                            return Ok(decline("integer syntax"));
                        };
                        if (option["type"] == "_positive_int" && n < 1)
                            || (option["type"] == "_nonnegative_int" && n < 0)
                        {
                            return Ok(decline("integer bounds"));
                        };
                        json!(n)
                    }
                    Some("float") => {
                        let Ok(n) = raw.parse::<f64>() else {
                            return Ok(decline("float syntax"));
                        };
                        if !n.is_finite() {
                            return Ok(decline("nonfinite float"));
                        };
                        json!(n)
                    }
                    _ => json!(raw),
                }
            }
            _ => return Ok(decline("unsupported action")),
        };
        if let Some(choices) = option["choices"].as_array()
            && !choices.contains(&value)
        {
            return Ok(decline("invalid choice"));
        };
        if option["kind"] == "_AppendAction" {
            if args.get(dest).is_none() {
                args[dest] = json!([])
            }
            if let Some(values) = args[dest].as_array_mut() {
                values.push(value)
            }
        } else {
            args[dest] = value
        }
        index += 1;
    }
    for option in options {
        if option["required"] == true && args[option["dest"].as_str().unwrap_or("")].is_null() {
            return Ok(decline("missing required option"));
        }
    }
    if !args["codex_args"].is_null() && !args["codex_args_file"].is_null() {
        return Ok(decline("mutually exclusive options"));
    }
    let root_arg = args["repo_root"]["value"]
        .as_str()
        .map(Path::new)
        .unwrap_or(request.cwd);
    let root = resolved(root_arg, request.cwd)?;
    let home = resolved(request.invoking_home, request.cwd)?;
    if root.join("tools/mir_executor/local.py").try_exists()? {
        return Ok(decline(
            "target Python hooks require whole-command fallback",
        ));
    }
    if root.to_str().is_none() || home.to_str().is_none() {
        return Ok(decline("non UTF-8 path"));
    }
    let cross_target = root != home;
    // main invokes the home guard twice, then execute preparation invokes it once.
    let calls = if command == "execute" { 3 } else { 2 };
    if cross_target {
        let output = git(&request, &home, "--show-toplevel")?;
        let stdout = std::str::from_utf8(&output.stdout).ok();
        let is_home = output.status.success()
            && stdout
                .and_then(|s| resolved(Path::new(s.trim()), request.cwd).ok())
                .as_ref()
                == Some(&home);
        if is_home {
            let config = BridgeConfig {
                interpreter: request.interpreter.into(),
                target_root: home.clone(),
                bridge_script: request.bridge_script.into(),
                environment: request.environment.clone(),
                timeout: Duration::from_secs(10),
            };
            if let Some(mut bridge) = LocalBridge::start(config)? {
                for _ in 0..calls {
                    let (Some(home_value), Some(root_value)) =
                        (path_value(&home), path_value(&root))
                    else {
                        return Ok(decline("non UTF-8 path"));
                    };
                    let reply = bridge.call(
                        "authorize_target",
                        vec![
                            home_value,
                            root_value,
                            json!({"$type":"namespace","value":args}),
                        ],
                        json!({}),
                    )?;
                    if reply["ok"] == false {
                        return Ok(refusal(format!(
                            "authorize_target refused {}: {}: {}",
                            root.display(),
                            reply["error"]["type"].as_str().unwrap_or(""),
                            reply["error"]["message"].as_str().unwrap_or("")
                        )));
                    }
                }
            }
        }
    }
    if command == "execute" {
        let output = git(&request, &root, "--is-inside-work-tree")?;
        if !output.status.success() || output.stdout.trim_ascii() != b"true" {
            return Ok(refusal(format!(
                "ValueError: repo root is not a git repository: {}",
                root.display()
            )));
        }
        let Some(value) = path_value(&root) else {
            return Ok(decline("non UTF-8 path"));
        };
        args["repo_root"] = value;
    }
    Ok(Admission::Admitted {
        root,
        cross_target,
        args,
    })
}
