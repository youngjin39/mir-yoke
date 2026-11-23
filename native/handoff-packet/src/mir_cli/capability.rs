//! Library-only capability CLI. Provider execution is explicitly caller supplied.
#![forbid(unsafe_code)]
pub use super::bootstrap::Error;
use super::{changes, memory::Output};
use crate::executor_execute::repr;
use crate::python_json::{Text, Value as PyValue};
use serde_json::{Map, Value, json};
use std::path::Path;

const COMMANDS: &[&str] = &[
    "status",
    "check",
    "sync",
    "update",
    "finalize",
    "attest",
    "deregister",
];
const APPLY_COMMANDS: &[&str] = &["sync", "update", "finalize", "attest", "deregister"];

/// The CLI owns parsing and evidence; the caller owns provider authority and state.
pub trait Manager {
    fn initialize(
        &mut self,
        project_root: &Path,
        config_path: Option<&Path>,
        capability_home: Option<&Path>,
    ) -> Result<(), Error>;
    fn call(
        &mut self,
        method: &str,
        args: Vec<Value>,
        kwargs: Map<String, Value>,
    ) -> Result<PyValue, Error>;
}

fn usage(command: &str) -> String {
    if command.is_empty() {
        return format!(
            "usage: mir capability [-h]\n                      {{{}}}\n                      ...\n",
            COMMANDS.join(",")
        );
    }
    let pad = " ".repeat(23 + command.len());
    if command == "deregister" {
        return format!(
            "usage: mir capability deregister [-h] --project-root PROJECT_ROOT\n\
{pad}[--config CONFIG] --capability-home\n\
{pad}CAPABILITY_HOME [--json] [--apply]\n"
        );
    }
    let tail = match command {
        "status" => "[--profile PROFILE]".into(),
        "check" => "[--profile PROFILE] [--mcp | --no-mcp]".into(),
        "sync" | "update" => "[--profile PROFILE] [--mcp | --no-mcp] [--apply]".into(),
        "finalize" => "[--apply] [--after-restart]".into(),
        _ => format!(
            "--runtime {{claude-code,codex-cli-desktop}}\n\
{pad}[--observed-skill OBSERVED_SKILL]\n\
{pad}[--observed-hook OBSERVED_HOOK] [--apply]\n\
{pad}[--mcp-evidence MCP_EVIDENCE]"
        ),
    };
    format!(
        "usage: mir capability {command} [-h] [--project-root PROJECT_ROOT]\n\
{pad}[--config CONFIG]\n\
{pad}[--capability-home CAPABILITY_HOME] [--json]\n{pad}{tail}\n"
    )
}
fn diag(command: &str, message: &str) -> Output {
    let suffix = if command.is_empty() {
        String::new()
    } else {
        format!(" {command}")
    };
    (
        2,
        vec![],
        format!(
            "{}mir capability{suffix}: error: {message}\n",
            usage(command)
        )
        .into_bytes(),
    )
}
fn help(command: &str) -> Output {
    let mut out = usage(command);
    if command.is_empty() {
        out.push_str(&format!(
            "\npositional arguments:\n  {{{}}}\n\noptions:\n  -h, --help            show this help message and exit\n",
            COMMANDS.join(",")
        ));
    } else {
        out.push_str(concat!(
            "\noptions:\n  -h, --help            show this help message and exit\n",
            "  --project-root PROJECT_ROOT\n  --config CONFIG\n",
            "  --capability-home CAPABILITY_HOME\n  --json\n"
        ));
        if ["status", "check", "sync", "update"].contains(&command) {
            out.push_str("  --profile PROFILE\n");
        }
        if ["check", "sync", "update"].contains(&command) {
            out.push_str(concat!(
                "  --mcp, --no-mcp       explicitly select mir-mcp (or remove it with --no-\n",
                "                        mcp); otherwise retain the lock\n"
            ));
        }
        if ["sync", "update"].contains(&command) {
            out.push_str(concat!(
                "  --apply               materialize the pinned provider and update its exact-\n",
                "                        SHA lock\n"
            ));
        }
        if command == "finalize" {
            out.push_str(concat!(
                "  --apply\n",
                "  --after-restart       confirm that operator observations came from restarted\n",
                "                        runtime sessions\n"
            ));
        }
        if command == "deregister" {
            out.push_str("  --apply\n");
        }
        if command == "attest" {
            out.push_str(concat!(
                "  --runtime {claude-code,codex-cli-desktop}\n",
                "  --observed-skill OBSERVED_SKILL\n",
                "                        operator-observed namespaced skill from the current\n",
                "                        runtime catalog\n  --observed-hook OBSERVED_HOOK\n",
                "                        operator-observed namespaced hook from the current\n",
                "                        runtime session\n  --apply\n",
                "  --mcp-evidence MCP_EVIDENCE\n",
                "                        JSON object of operator-observed MCP evidence keyed by\n",
                "                        package name\n"
            ));
        }
    }
    (0, out.into_bytes(), vec![])
}
fn option_like(value: &str) -> bool {
    value.len() > 1 && value.starts_with('-') && value[1..].parse::<f64>().is_err()
}
/// Dispatch without discovering or creating a provider.
pub fn main(argv: &[&str], manager: &mut impl Manager) -> Result<Output, Error> {
    main_with_paths(argv, manager, Path::to_owned)
}
pub fn main_with_paths(
    argv: &[&str],
    manager: &mut impl Manager,
    path: impl Fn(&Path) -> std::path::PathBuf,
) -> Result<Output, Error> {
    let Some(&command) = argv.first() else {
        return Ok(diag("", "the following arguments are required: command"));
    };
    if matches!(command, "-h" | "--help") {
        return Ok(help(""));
    }
    if !COMMANDS.contains(&command) {
        return Ok(diag(
            "",
            &format!(
                "argument command: invalid choice: {} (choose from {})",
                repr(command),
                COMMANDS.join(", ")
            ),
        ));
    }
    let mut options = vec![
        ("--help", false),
        ("--project-root", true),
        ("--config", true),
        ("--capability-home", true),
        ("--json", false),
    ];
    if ["status", "check", "sync", "update"].contains(&command) {
        options.push(("--profile", true));
    }
    if ["check", "sync", "update"].contains(&command) {
        options.extend([("--mcp", false), ("--no-mcp", false)]);
    }
    if APPLY_COMMANDS.contains(&command) {
        options.push(("--apply", false));
    }
    if command == "finalize" {
        options.push(("--after-restart", false));
    }
    if command == "attest" {
        options.extend([
            ("--runtime", true),
            ("--observed-skill", true),
            ("--observed-hook", true),
            ("--mcp-evidence", true),
        ]);
    }
    let mut values = Map::new();
    let (mut skills, mut hooks, mut unknown) = (vec![], vec![], vec![]);
    let (mut i, mut parse_options) = (1, true);
    while let Some(&token) = argv.get(i) {
        i += 1;
        if token == "--" && parse_options {
            if command == "deregister" {
                unknown.push(token);
            }
            parse_options = false;
            continue;
        }
        if !parse_options || !option_like(token) {
            unknown.push(token);
            continue;
        }
        let (name, explicit) = token
            .split_once('=')
            .map_or((token, None), |(n, v)| (n, Some(v)));
        let name = if name == "-h" { "--help" } else { name };
        let exact = options.iter().find(|o| o.0 == name);
        let matching: Vec<_> = options
            .iter()
            .filter(|o| name.starts_with("--") && o.0.starts_with(name))
            .collect();
        let option = match (exact, matching.as_slice()) {
            (Some(o), _) => o,
            (None, [o]) => *o,
            (None, []) => {
                unknown.push(token);
                continue;
            }
            _ => {
                return Ok(diag(
                    command,
                    &format!(
                        "ambiguous option: {name} could match {}",
                        matching.iter().map(|o| o.0).collect::<Vec<_>>().join(", ")
                    ),
                ));
            }
        };
        let value = if option.1 {
            if let Some(v) = explicit {
                v
            } else {
                let Some(&v) = argv.get(i).filter(|v| !option_like(v)) else {
                    return Ok(diag(
                        command,
                        &format!("argument {}: expected one argument", option.0),
                    ));
                };
                i += 1;
                v
            }
        } else {
            if let Some(v) = explicit {
                return Ok(diag(
                    command,
                    &format!(
                        "argument {}: ignored explicit argument {}",
                        option.0,
                        repr(v)
                    ),
                ));
            }
            ""
        };
        match option.0 {
            "--help" => return Ok(help(command)),
            "--runtime" if !["claude-code", "codex-cli-desktop"].contains(&value) => {
                return Ok(diag(
                    command,
                    &format!(
                        concat!(
                            "argument --runtime: invalid choice: {} ",
                            "(choose from claude-code, codex-cli-desktop)"
                        ),
                        repr(value)
                    ),
                ));
            }
            "--observed-skill" => skills.push(json!(value)),
            "--observed-hook" => hooks.push(json!(value)),
            "--mcp" => {
                values.insert("mcp".into(), json!(true));
            }
            "--no-mcp" => {
                values.insert("mcp".into(), json!(false));
            }
            key => {
                values.insert(
                    key.into(),
                    if option.1 { json!(value) } else { json!(true) },
                );
            }
        }
    }
    if command == "attest" && !values.contains_key("--runtime") {
        return Ok(diag(
            command,
            "the following arguments are required: --runtime",
        ));
    }
    if command == "deregister" {
        let missing: Vec<_> = ["--project-root", "--capability-home"]
            .into_iter()
            .filter(|option| !values.contains_key(*option))
            .collect();
        if !missing.is_empty() {
            return Ok(diag(
                command,
                &format!(
                    "the following arguments are required: {}",
                    missing.join(", ")
                ),
            ));
        }
    }
    if !unknown.is_empty() {
        return Ok(diag(
            "",
            &format!("unrecognized arguments: {}", unknown.join(" ")),
        ));
    }
    let mut run = || -> Result<PyValue, Error> {
        use super::bootstrap::Host;
        let mut host = super::bootstrap::ProductionHost::default();
        let root = path(Path::new(
            values
                .get("--project-root")
                .and_then(Value::as_str)
                .unwrap_or("."),
        ));
        let root = host.expanduser(&root)?;
        let root = host.resolve(&root)?;
        manager.initialize(
            &root,
            values
                .get("--config")
                .and_then(Value::as_str)
                .map(Path::new)
                .map(&path)
                .as_deref(),
            values
                .get("--capability-home")
                .and_then(Value::as_str)
                .map(Path::new)
                .map(&path)
                .as_deref(),
        )?;
        let before = if matches!(command, "status" | "deregister") {
            None
        } else {
            Some(
                changes::snapshot_project(&root)
                    .map_err(|e| Error::new("OSError", e.to_string()))?,
            )
        };
        let mut kwargs = Map::new();
        let args = match command {
            "status" | "check" | "sync" | "update" => {
                if let Some(v) = values.get("mcp") {
                    kwargs.insert("mcp".into(), v.clone());
                }
                vec![values.get("--profile").cloned().unwrap_or(Value::Null)]
            }
            "finalize" => {
                kwargs.insert(
                    "after_restart".into(),
                    json!(values.contains_key("--after-restart")),
                );
                vec![]
            }
            "deregister" => vec![],
            _ => {
                if let Some(path) = values.get("--mcp-evidence").and_then(Value::as_str) {
                    let evidence = crate::mir_core::capabilities::mcp::closed_json(Path::new(path))
                        .ok_or_else(|| {
                            Error::new("CapabilityError", "cannot read MCP evidence JSON object")
                        })?;
                    kwargs.insert("observed_mcp".into(), evidence);
                }
                vec![values["--runtime"].clone(), json!(skills), json!(hooks)]
            }
        };
        if APPLY_COMMANDS.contains(&command) {
            kwargs.insert("apply".into(), json!(values.contains_key("--apply")));
        }
        let mut result = manager.call(command, args, kwargs)?;
        let PyValue::Object(ref mut object) = result else {
            return Err(Error::new(
                "TypeError",
                format!(
                    "'{}' object does not support item assignment",
                    result.type_name()
                ),
            ));
        };
        if let Some(before) = before {
            object.insert(
                "changed_paths".into(),
                PyValue::Array(
                    changes::changed_paths(
                        &before,
                        &changes::snapshot_project(&root)
                            .map_err(|e| Error::new("OSError", e.to_string()))?,
                    )
                    .into_iter()
                    .map(|s| PyValue::String(s.into()))
                    .collect(),
                ),
            );
        } else {
            let mut evidence = crate::python_json::Object::default();
            let reason = if command == "deregister" {
                "registry-only-operation"
            } else {
                "read-only-operation"
            };
            for (k, v) in [("status", "not-applicable"), ("reason", reason)] {
                evidence.insert(k.into(), PyValue::String(v.into()));
            }
            object.insert("change_evidence".into(), PyValue::Object(evidence));
        }
        Ok(result)
    };
    match run() {
        Ok(value) => Ok((
            0,
            format!("{}\n", value.json_sorted(!values.contains_key("--json"))).into_bytes(),
            vec![],
        )),
        Err(e)
            if e.mro.iter().any(|c| {
                matches!(
                    c.as_str(),
                    "mir.core.capabilities.manager.CapabilityError"
                        | "mir.core.capabilities.config.CapabilityConfigError"
                )
            }) =>
        {
            let message = e.message_text.unwrap_or_else(|| e.message.into());
            let text = Text::from("ERROR: ").concat(&message).concat(&"\n".into());
            Ok((
                1,
                vec![],
                text.render()
                    .map_err(|e| Error::new("UnicodeEncodeError", e))?,
            ))
        }
        Err(e) => Err(e),
    }
}
