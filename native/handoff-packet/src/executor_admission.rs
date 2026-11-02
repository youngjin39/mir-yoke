//! Library admission only: no database access, provider launch, or CLI dispatch.
//! Dynamic target options decline after hello, before any target hook call.
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
#[derive(Debug)]
pub enum Admission {
    Admitted {
        root: PathBuf,
        cross_target: bool,
        args: Value,
        // Boxed: the child handle makes this variant large on Windows.
        bridge: Option<Box<LocalBridge>>,
        /// Present only for command admission; the owner exits this lease.
        writer_handle: Option<String>,
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
        // Python's resolve() never returns the Windows verbatim prefix.
        Ok(path) => Ok(crate::supply::plain(path)),
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
// Admission may fail after entering the outer CLI lease. Closing the transport
// kills its child, so release the context explicitly before that happens.
struct WriterLease {
    bridge: Option<LocalBridge>,
    handle: Option<String>,
}
impl std::ops::Deref for WriterLease {
    type Target = Option<LocalBridge>;
    fn deref(&self) -> &Self::Target {
        &self.bridge
    }
}
impl std::ops::DerefMut for WriterLease {
    fn deref_mut(&mut self) -> &mut Self::Target {
        &mut self.bridge
    }
}
impl Drop for WriterLease {
    fn drop(&mut self) {
        if let (Some(bridge), Some(handle)) = (self.bridge.as_mut(), self.handle.take()) {
            let _ = bridge.call(
                "writer_scope.exit",
                vec![Value::Null],
                json!({"handles":{"0":handle}}),
            );
        }
    }
}
/// Malformed/unknown argv is left untouched for Python's argparse diagnostics.
/// Target imports occur only after the first home authorization.
pub fn admit(request: Request<'_>) -> Result<Admission, BridgeError> {
    admit_inner(request, false)
}
/// Enter the command's writer lease before preparation, matching the Python CLI.
pub fn admit_execute(request: Request<'_>) -> Result<Admission, BridgeError> {
    admit_inner(request, true)
}

fn admit_inner(request: Request<'_>, command_scope: bool) -> Result<Admission, BridgeError> {
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
    let mut root = resolved(root_arg, request.cwd)?;
    let home = resolved(request.invoking_home, request.cwd)?;
    if root.to_str().is_none() || home.to_str().is_none() {
        return Ok(decline("non UTF-8 path"));
    }
    let mut home_bridge = None;
    if let Some(refused) = authorize(&request, &home, &root, &args, &mut home_bridge, false)? {
        return Ok(refused);
    }
    let mut bridge = match LocalBridge::start_in(bridge_config(&request, &root), request.cwd) {
        Ok(bridge) => bridge,
        Err(error) if command_scope => return Ok(refusal(error.to_string())),
        Err(_) => return Ok(decline("target bridge failed before hello")),
    };
    if bridge
        .as_ref()
        .is_some_and(|b| b.hello()["register_execute_options"] == true)
    {
        if command_scope {
            return Ok(refusal(
                "local import dynamically registered execute options; native ownership is final, invoke Python explicitly".into(),
            ));
        }
        return Ok(decline("target registers execute options"));
    }
    if let Some(refused) = authorize(&request, &home, &root, &args, &mut home_bridge, false)? {
        return Ok(refused);
    }
    let mut writer_handle = None;
    if command_scope && let Some(local) = bridge.as_mut() {
        let reply = local.call(
            "writer_scope",
            vec![path_value(&root).ok_or(BridgeError::Protocol("non UTF-8 path"))?],
            json!({}),
        )?;
        if reply["ok"] == false {
            return Ok(refusal(format!(
                "{}: {}",
                reply["error"]["type"].as_str().unwrap_or(""),
                reply["error"]["message"].as_str().unwrap_or("")
            )));
        }
        if let Some(handle) = reply["handle"].as_str() {
            writer_handle = Some(handle.to_owned());
            let entered = local.call(
                "writer_scope.enter",
                vec![Value::Null],
                json!({"handles":{"0":handle}}),
            )?;
            if entered["ok"] == false {
                return Ok(refusal(format!(
                    "{}: {}",
                    entered["error"]["type"].as_str().unwrap_or(""),
                    entered["error"]["message"].as_str().unwrap_or("")
                )));
            }
        }
    }
    let mut bridge = WriterLease {
        bridge,
        handle: writer_handle,
    };
    if command_scope {
        let change = !args["change_id"].is_null();
        let category = !args["category"].is_null();
        if change != category {
            return Ok(refusal(
                "--change-id and --category must be supplied together".into(),
            ));
        }
        if !change && args["dispatch"] != true {
            return Ok(refusal(
                "--change-id and --category are required outside --dispatch".into(),
            ));
        }
    }
    if command == "execute" {
        if let Some(refused) = authorize(&request, &home, &root, &args, &mut home_bridge, true)? {
            return Ok(refused);
        }
        if let Some(local) = bridge.as_mut() {
            let reply = local.call(
                "pre_execute",
                vec![
                    json!({"$type":"namespace","value":args}),
                    path_value(&root).ok_or(BridgeError::Protocol("non UTF-8 path"))?,
                ],
                json!({}),
            )?;
            if reply["ok"] == false {
                let error = &reply["error"];
                let message = error["message"].as_str().unwrap_or("");
                return Ok(refusal(if reply["error_category"] == "value_error" {
                    format!("argument parse error: {message}")
                } else {
                    format!("{}: {message}", error["type"].as_str().unwrap_or(""))
                }));
            }
            args = reply["args"][0]["value"].clone();
            if !args.is_object() {
                return Err(BridgeError::Protocol("missing post-hook namespace"));
            }
            if command_scope
                && (args["dispatch"] == true
                    || args["execution_backend"]
                        .as_str()
                        .is_some_and(|backend| backend != "codex")
                    || !args["target_agent"].is_null()
                    || !args["dispatch_brief"].is_null())
            {
                return Ok(refusal(
                    "pre_execute selected an unsupported native execution path".into(),
                ));
            }
        }
        let redirected = args["repo_root"]["value"]
            .as_str()
            .or_else(|| args["repo_root"].as_str())
            .ok_or(BridgeError::Protocol("invalid post-hook repo_root"))?;
        let redirected = resolved(Path::new(redirected), request.cwd)?;
        if redirected != root {
            let guard: &mut Option<LocalBridge> = if root == home {
                &mut bridge
            } else {
                &mut home_bridge
            };
            if let Some(refused) = authorize(&request, &home, &redirected, &args, guard, true)? {
                return Ok(refused);
            }
            if command_scope {
                return Ok(refusal(
                    "pre_execute redirected the native execution root; refusing after admission"
                        .into(),
                ));
            }
        }
        root = redirected;
    }
    if command == "execute" {
        let output = git(&request, &root, "--is-inside-work-tree")?;
        if !output.status.success() || output.stdout.trim_ascii() != b"true" {
            return Ok(refusal(format!(
                "argument parse error: repo root is not a git repository: {}",
                root.display()
            )));
        }
        let Some(value) = path_value(&root) else {
            return Ok(decline("non UTF-8 path"));
        };
        args["repo_root"] = value;
    }
    Ok(Admission::Admitted {
        cross_target: root != home,
        root,
        args,
        bridge: bridge.bridge.take().map(Box::new),
        writer_handle: bridge.handle.take(),
    })
}

fn bridge_config(request: &Request<'_>, root: &Path) -> BridgeConfig {
    BridgeConfig {
        interpreter: request.interpreter.into(),
        target_root: root.into(),
        bridge_script: request.bridge_script.into(),
        environment: request.environment.clone(),
        timeout: Duration::from_secs(10),
    }
}
fn authorize(
    request: &Request<'_>,
    home: &Path,
    root: &Path,
    args: &Value,
    bridge: &mut Option<LocalBridge>,
    preparation: bool,
) -> Result<Option<Admission>, BridgeError> {
    if root == home {
        return Ok(None);
    }
    let output = git(request, home, "--show-toplevel")?;
    if !output.status.success()
        || std::str::from_utf8(&output.stdout)
            .ok()
            .and_then(|s| resolved(Path::new(s.trim()), request.cwd).ok())
            .as_deref()
            != Some(home)
    {
        return Ok(None);
    }
    if bridge.is_none() {
        *bridge = LocalBridge::start_in(bridge_config(request, home), request.cwd)?;
    }
    if let Some(bridge) = bridge {
        let reply = bridge.call(
            "authorize_target",
            vec![
                path_value(home).ok_or(BridgeError::Protocol("non UTF-8 home"))?,
                path_value(root).ok_or(BridgeError::Protocol("non UTF-8 root"))?,
                json!({"$type":"namespace","value":args}),
            ],
            json!({}),
        )?;
        if reply["ok"] == false {
            let prefix = if preparation {
                "argument parse error: "
            } else {
                ""
            };
            return Ok(Some(refusal(format!(
                "{prefix}authorize_target refused {}: {}: {}",
                root.display(),
                reply["error"]["type"].as_str().unwrap_or(""),
                reply["error"]["message"].as_str().unwrap_or("")
            ))));
        }
    }
    Ok(None)
}
