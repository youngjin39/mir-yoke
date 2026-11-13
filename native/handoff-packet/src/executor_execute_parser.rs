//! The common execute argparse surface, independent of target-owned Python.
use crate::{executor_execute::repr, executor_text};
use serde_json::{Value, json};
use std::{ffi::OsString, path::Path};

use crate::python_decimal;

const PROG: &str = "python -m tools.mir_executor";
const ADMISSION_USAGE: &str = r#"usage: python -m tools.mir_executor execute [--change-id ID] [--category NAME]
                                            [--codex-args QUOTED_STRING | --codex-args-file PATH]
                                            [--timeout SECONDS]
                                            [--model MODEL]
                                            [--reasoning-effort EFFORT]
                                            [--stall-timeout SECONDS]
                                            [--jobs-db PATH]
                                            [--repo-root PATH]
                                            [--family FAMILY]
                                            [--artifacts-dir ARTIFACTS_DIR]
                                            [--async] [--background]
                                            [--dispatch]
                                            [--max-codex-attempts N]
                                            [--finalize-lock-timeout SECONDS]
                                            [--execution-backend BACKEND]
                                            [--expect-changes | --no-expect-changes]
                                            [--allow-harness-self-modify]
                                            [--allow-path PATH]
                                            [--verify-cmd COMMAND]
                                            [--dispatch-brief PATH]
"#;
const ROOT_USAGE: &str = "usage: python -m tools.mir_executor [-h] [--jobs-db PATH]\n                                    {execute,status,result,cancel,resume,list-jobs,sweep}\n                                    ...\n";
const ROOT_HELP: &str = r#"usage: python -m tools.mir_executor [-h] [--jobs-db PATH]
                                    {execute,status,result,cancel,resume,list-jobs,sweep}
                                    ...

Mir Executor — isolated delegated execution with optional TDD ledger update.

positional arguments:
  {execute,status,result,cancel,resume,list-jobs,sweep}
    execute             Run a delegated command; ledger identity is optional
                        in dispatch mode.
    status              Print job status from the JobRegistry.
    result              Print job result (exit_code, stdout, stderr, duration)
                        from the JobRegistry.
    cancel              Request cancellation of a background job.
    resume              Resume a job from its persisted DispatchBrief and
                        stored registry state.
    list-jobs           List background jobs, optionally filtered by status.
    sweep               Report advisory-overdue jobs and orphan dispatch
                        worktrees.

options:
  -h, --help            show this help message and exit
  --jobs-db PATH        Override path to jobs.db (default:
                        <repo_root>/tasks/jobs.db).
"#;
const HELP: &str = r#"usage: python -m tools.mir_executor execute [-h] [--change-id ID]
                                            [--category NAME]
                                            [--codex-args QUOTED_STRING | --codex-args-file PATH]
                                            [--timeout SECONDS]
                                            [--model MODEL]
                                            [--reasoning-effort EFFORT]
                                            [--stall-timeout SECONDS]
                                            [--jobs-db PATH]
                                            [--repo-root PATH]
                                            [--family FAMILY]
                                            [--artifacts-dir ARTIFACTS_DIR]
                                            [--async] [--background]
                                            [--dispatch]
                                            [--max-codex-attempts N]
                                            [--finalize-lock-timeout SECONDS]
                                            [--execution-backend BACKEND]
                                            [--expect-changes | --no-expect-changes]
                                            [--allow-harness-self-modify]
                                            [--allow-path PATH]
                                            [--verify-cmd COMMAND]
                                            [--dispatch-brief PATH]

options:
  -h, --help            show this help message and exit
  --change-id ID        Optional tdd.json change entry id; required outside
                        --dispatch.
  --category NAME       Optional tdd.json category; required outside
                        --dispatch. One of: unit, integration, e2e, browser,
                        edge, architecture, availability, load, soak,
                        security, compatibility, transaction_locking.
  --codex-args QUOTED_STRING
                        Arguments for legacy Codex invocation. In --dispatch
                        mode, exec-shaped flags are dropped and the positional
                        prompt is sent to the MCP Codex backend.
  --codex-args-file PATH
                        Read UTF-8 file content and use it as one raw
                        positional prompt argument, without shlex
                        tokenization.
  --timeout SECONDS     Optional hard subprocess timeout in seconds.
  --model MODEL         Optional Codex model name (e.g. a codex model id);
                        omit to inherit Codex defaults.
  --reasoning-effort EFFORT
                        Optional Codex model_reasoning_effort (free string);
                        omit to inherit Codex defaults.
  --stall-timeout SECONDS
                        Optional no-progress MCP stall timeout in seconds.
  --jobs-db PATH        Override path to jobs.db (default:
                        <repo_root>/tasks/jobs.db).
  --repo-root PATH      Repository root path. Used to locate tasks/tdd.json.
  --family FAMILY       Optional job family.
  --artifacts-dir ARTIFACTS_DIR
  --async, -a           Use asyncio-based async subprocess
                        (asyncio.TimeoutError on timeout).
  --background, -b      Background mode: print job_id immediately, then run
                        Codex and update job status on completion. MVP: runs
                        in same process (true daemon is OOS).
  --dispatch            Run the delegated dispatch helper with an isolated
                        worktree, one attempt by default, and the outage
                        guard.
  --max-codex-attempts N
                        Explicit dispatch attempt budget (default: 1). Values
                        above one opt into retrying the same dispatch.
  --finalize-lock-timeout SECONDS
                        Maximum wait for the short merge-finalize lock
                        (default: 30). This never stops a running delegated
                        agent.
  --execution-backend BACKEND
                        ADR-61 dispatch-only backend request. Used only when
                        the sub-agent policy permits selection; omitted
                        requests retain the Codex preference.
  --expect-changes, --no-expect-changes
                        Require a dispatch to produce a git diff before merge
                        (default: true). Use --no-expect-changes for
                        legitimate no-op or verify-only dispatches.
  --allow-harness-self-modify
                        Allow dispatch merge-back for liftable harness
                        prefixes (.claude/, .ai-harness/, config/, docs/) when
                        also allowlisted. tasks/ remains denied.
  --allow-path PATH     Repeatable ADR-60 dispatch merge allowlist path.
  --verify-cmd COMMAND  Repeatable ADR-60 dispatch verification command to re-
                        run before merge.
  --dispatch-brief PATH
                        Persisted DispatchBrief JSON. In --dispatch mode,
                        expanded_goal is used as the MCP prompt when --codex-
                        args contains no prompt positional.
"#;

pub(crate) enum Parsed {
    Args(Value),
    Output {
        text: String,
        code: i32,
        error: bool,
        admission: Option<Value>,
    },
}
fn output(text: String, code: i32, error: bool) -> Parsed {
    Parsed::Output {
        text,
        code,
        error,
        admission: None,
    }
}
fn after_admission(mut parsed: Parsed, args: Value) -> Parsed {
    if let Parsed::Output { admission, .. } = &mut parsed {
        *admission = Some(args);
    }
    parsed
}
fn usage(help: bool) -> String {
    let text = HELP.split("\n\n").next().unwrap_or("");
    if help {
        format!("{text}\n")
    } else {
        ADMISSION_USAGE.into()
    }
}
fn failure(message: String, final_parse: bool) -> Parsed {
    output(
        format!("{}{PROG} execute: error: {message}\n", usage(final_parse)),
        2,
        true,
    )
}
// The reference is CPython 3.12 (Unicode 15); the shared digit table also
// includes Unicode 16 digits, which its int()/float() do not yet accept.
fn numeric_text(raw: &str) -> String {
    raw.chars()
        .map(|c| {
            let digit = if matches!(u32::from(c),
            0x10d40..=0x10d49 | 0x116d0..=0x116e3 | 0x11bf0..=0x11bf9
            | 0x16130..=0x16139 | 0x16d70..=0x16d79 | 0x1ccf0..=0x1ccf9
            | 0x1e5f1..=0x1e5fa)
            {
                None
            } else {
                python_decimal::decimal_digit(c)
            };
            digit.map_or(c, |digit| char::from(b'0' + digit as u8))
        })
        .collect()
}
fn negative(text: &str) -> bool {
    regex::Regex::new(r"^-([0-9]+|[0-9]*\.[0-9]+)$")
        .is_ok_and(|re| re.is_match(&numeric_text(text.strip_suffix('\n').unwrap_or(text))))
}
fn value_token(text: &str) -> bool {
    !text.starts_with('-') || text == "-" || negative(text)
}
fn abbreviates(arg: &str, name: &str) -> bool {
    arg.starts_with("--") && arg.len() > 2 && name.starts_with(arg)
}
fn path_argument(raw: &OsString, inline: bool) -> std::path::PathBuf {
    if !inline {
        return raw.into();
    }
    #[cfg(unix)]
    {
        use std::os::unix::ffi::{OsStrExt, OsStringExt};
        let bytes = raw.as_bytes();
        let start = bytes
            .iter()
            .position(|byte| *byte == b'=')
            .map_or(0, |index| index + 1);
        OsString::from_vec(bytes[start..].to_vec()).into()
    }
    #[cfg(windows)]
    {
        use std::os::windows::ffi::{OsStrExt, OsStringExt};
        let units = raw.encode_wide().collect::<Vec<_>>();
        let start = units
            .iter()
            .position(|unit| *unit == u16::from(b'='))
            .map_or(0, |index| index + 1);
        OsString::from_wide(&units[start..]).into()
    }
    #[cfg(not(any(unix, windows)))]
    {
        raw.to_str()
            .and_then(|text| text.split_once('=').map(|(_, value)| value))
            .unwrap_or("")
            .into()
    }
}
pub(crate) fn requested(raw: &[OsString]) -> bool {
    let mut index = 0;
    while let Some(arg) = raw.get(index) {
        let arg = executor_text::os_text(arg);
        if arg == "execute" {
            return true;
        }
        let key = arg.split('=').next().unwrap_or("");
        if abbreviates(key, "--jobs-db") || abbreviates(key, "--repo-root") {
            index += if arg.contains('=') { 1 } else { 2 };
        } else if arg.starts_with('-') {
            index += 1;
        } else {
            return false;
        }
    }
    false
}
pub(crate) fn dispatch(raw: &[OsString]) -> bool {
    let schema: Value = serde_json::from_str(include_str!(
        "../tests/fixtures/executor_admission_schema.json"
    ))
    .unwrap_or(Value::Null);
    let mut index = 0;
    let mut command = false;
    while let Some(arg) = raw.get(index) {
        let arg = executor_text::os_text(arg);
        if arg == "execute" {
            command = true;
        }
        if arg == "--" && command {
            return false;
        }
        if arg == "--dispatch" && command {
            return true;
        }
        if !arg.contains('=')
            && let Some(options) = schema["execute"].as_array()
        {
            let option = options.iter().find(|option| {
                option["flags"].as_array().is_some_and(|flags| {
                    flags
                        .iter()
                        .filter_map(Value::as_str)
                        .any(|flag| flag == arg || abbreviates(&arg, flag))
                })
            });
            if option.is_some_and(|option| {
                matches!(
                    option["kind"].as_str(),
                    Some("_StoreAction" | "_AppendAction")
                )
            }) {
                index += 1;
            }
        }
        index += 1;
    }
    false
}
pub(crate) fn parse(raw_argv: &[OsString], cwd: &Path) -> Parsed {
    let words = raw_argv
        .iter()
        .map(|arg| executor_text::os_text(arg))
        .collect::<Vec<_>>();
    // cli.main's preliminary parser sees these options even after the subcommand.
    let mut index = 0;
    while let Some(arg) = words.get(index) {
        if arg == "--" {
            break;
        }
        let (key, inline) = arg
            .split_once('=')
            .map_or((arg.as_str(), false), |(key, _)| (key, true));
        if let Some(name) = ["--repo-root", "--jobs-db"]
            .into_iter()
            .find(|name| abbreviates(key, name))
            && !inline
        {
            if !words.get(index + 1).is_some_and(|arg| value_token(arg)) {
                let prog =
                    std::env::var("MIR_EXECUTOR_ARGPARSE_PROG").unwrap_or_else(|_| "-c".into());
                return output(
                    format!(
                        "usage: {prog} [--repo-root REPO_ROOT] [--jobs-db JOBS_DB] [subcommand]\n{prog}: error: argument {name}: expected one argument\n"
                    ),
                    2,
                    true,
                );
            }
            index += 1;
        }
        index += 1;
    }
    let schema: Value = match serde_json::from_str(include_str!(
        "../tests/fixtures/executor_admission_schema.json"
    )) {
        Ok(schema) => schema,
        Err(error) => return output(format!("ValueError: {error}\n"), 1, true),
    };
    let options = schema["execute"].as_array().cloned().unwrap_or_default();
    let mut args = json!({"subcommand":"execute", "jobs_db":null});
    for option in &options {
        if option["default"] != "==SUPPRESS==" {
            let key = option["dest"].as_str().unwrap_or("");
            args[key] = if option["default"]["value"] == "$cwd" {
                crate::executor_admission::path_value(cwd).unwrap_or(Value::Null)
            } else {
                option["default"].clone()
            };
        }
    }
    let mut command = false;
    let mut help = false;
    let mut global_help = false;
    let mut global_ended = false;
    let mut help_error = None;
    let mut unknown = Vec::new();
    let mut source = None;
    let mut index = 0;
    let integer_pattern = regex::Regex::new(r"^[0-9](?:_?[0-9])*$");
    let float_pattern = regex::Regex::new(
        r"(?i)^[+-]?(?:(?:[0-9](?:_?[0-9])*(?:\.(?:[0-9](?:_?[0-9])*)?)?|\.[0-9](?:_?[0-9])*)(?:e[+-]?[0-9](?:_?[0-9])*)?|inf(?:inity)?|nan)$",
    );
    while index < words.len() {
        let arg = &words[index];
        if !command && arg == "--" && !global_ended {
            global_ended = true;
            index += 1;
            continue;
        }
        if !command && arg == "execute" {
            command = true;
            index += 1;
            continue;
        }
        if command && arg == "--" {
            unknown.extend(words[index..].iter().cloned());
            break;
        }
        if !command && (global_ended || !arg.starts_with('-') || arg.contains(' ')) {
            return output(
                format!(
                    "{}{PROG}: error: argument subcommand: invalid choice: {} (choose from execute, status, result, cancel, resume, list-jobs, sweep)\n",
                    ROOT_USAGE.replace(" [-h]", ""),
                    repr(arg)
                ),
                2,
                true,
            );
        }
        let (key, inline) = arg
            .split_once('=')
            .map_or((arg.as_str(), None), |(key, value)| (key, Some(value)));
        if key == "-h" || abbreviates(key, "--help") {
            if let Some(value) = inline {
                help_error = Some(format!(
                    "argument -h/--help: ignored explicit argument {}",
                    repr(value)
                ));
            }
            if command {
                help = true;
            } else {
                global_help = true;
            }
            index += 1;
            continue;
        }
        let candidates = options
            .iter()
            .filter_map(|option| {
                option["flags"]
                    .as_array()?
                    .iter()
                    .filter_map(Value::as_str)
                    .filter(|flag| *flag == key || abbreviates(key, flag))
                    .map(move |flag| (option, flag))
                    .next()
            })
            .collect::<Vec<_>>();
        let exact = candidates.iter().find(|(_, flag)| *flag == key).copied();
        let selected = if let Some(exact) = exact {
            Some(exact)
        } else if candidates.len() == 1 {
            candidates.first().copied()
        } else {
            None
        };
        if candidates.len() > 1 && selected.is_none() {
            let matches = candidates
                .iter()
                .map(|(_, flag)| *flag)
                .collect::<Vec<_>>()
                .join(", ");
            return failure(
                format!("ambiguous option: {arg} could match {matches}"),
                false,
            );
        }
        let Some((option, flag)) = selected.filter(|(_, flag)| command || *flag == "--jobs-db")
        else {
            unknown.push(arg.clone());
            index += 1;
            continue;
        };
        let dest = option["dest"].as_str().unwrap_or("");
        let kind = option["kind"].as_str().unwrap_or("");
        let boolean = matches!(kind, "_StoreTrueAction" | "BooleanOptionalAction");
        let value = if boolean {
            if let Some(inline) = inline {
                return failure(
                    format!(
                        "argument {}: ignored explicit argument {}",
                        option["flags"]
                            .as_array()
                            .unwrap_or(&Vec::new())
                            .iter()
                            .filter_map(Value::as_str)
                            .collect::<Vec<_>>()
                            .join("/"),
                        repr(inline)
                    ),
                    false,
                );
            }
            json!(!flag.starts_with("--no-"))
        } else {
            let raw = if let Some(raw) = inline {
                raw
            } else {
                index += 1;
                let Some(raw) = words.get(index).filter(|raw| value_token(raw)) else {
                    return failure(format!("argument {flag}: expected one argument"), false);
                };
                raw
            };
            if matches!(dest, "codex_args" | "codex_args_file") {
                if let Some(previous) = source
                    && previous != dest
                {
                    let other = if previous == "codex_args" {
                        "--codex-args"
                    } else {
                        "--codex-args-file"
                    };
                    return failure(
                        format!("argument {flag}: not allowed with argument {other}"),
                        false,
                    );
                }
                source = Some(dest);
            }
            let type_name = option["type"].as_str().unwrap_or("");
            match type_name {
                "Path" => {
                    crate::executor_admission::path_value(&crate::executor_admission::lexical(
                        &path_argument(&raw_argv[index], inline.is_some()),
                    ))
                    .unwrap_or(Value::Null)
                }
                _ if dest == "jobs_db"
                    && path_argument(&raw_argv[index], inline.is_some())
                        .to_str()
                        .is_none() =>
                {
                    crate::executor_admission::path_value(&path_argument(
                        &raw_argv[index],
                        inline.is_some(),
                    ))
                    .unwrap_or(Value::Null)
                }
                "int" | "_positive_int" | "_nonnegative_int" => {
                    let normalized = numeric_text(raw.trim());
                    let digits = normalized.strip_prefix(['+', '-']).unwrap_or(&normalized);
                    let valid = integer_pattern.as_ref().is_ok_and(|re| re.is_match(digits));
                    let digit_count = digits.bytes().filter(u8::is_ascii_digit).count();
                    if !valid || digit_count > 4300 {
                        let name = if type_name == "int" { "int" } else { type_name };
                        return failure(
                            format!(
                                "argument {flag}: invalid {name} value: {}",
                                crate::executor_development_packet::py_repr(raw)
                            ),
                            false,
                        );
                    }
                    let number = digits.replace('_', "");
                    let digits = number.trim_start_matches('0');
                    let number = if digits.is_empty() {
                        "0".to_owned()
                    } else if normalized.starts_with('-') {
                        format!("-{digits}")
                    } else {
                        digits.to_owned()
                    };
                    if type_name == "_positive_int" && (number == "0" || number.starts_with('-')) {
                        return failure(
                            format!("argument {flag}: must be a positive integer"),
                            false,
                        );
                    }
                    if type_name == "_nonnegative_int" && number.starts_with('-') {
                        return failure(
                            format!("argument {flag}: must be a non-negative integer"),
                            false,
                        );
                    }
                    match number.parse::<i64>() {
                        Ok(n) => json!(n),
                        Err(_) => json!({"__native_integer":number}),
                    }
                }
                "float" => {
                    let normalized = numeric_text(raw.trim());
                    let valid = float_pattern
                        .as_ref()
                        .is_ok_and(|re| re.is_match(&normalized));
                    match normalized.replace('_', "").parse::<f64>() {
                        Ok(n) if valid && n.is_finite() => json!(n),
                        Ok(n) if valid => json!({"__native_float":n.to_string()}),
                        _ => {
                            return failure(
                                format!(
                                    "argument {flag}: invalid float value: {}",
                                    crate::executor_development_packet::py_repr(raw)
                                ),
                                false,
                            );
                        }
                    }
                }
                _ => {
                    let points = executor_text::os_points(
                        path_argument(&raw_argv[index], inline.is_some()).as_os_str(),
                    );
                    if points.iter().any(|point| (0xd800..=0xdfff).contains(point)) {
                        args["__native_arg_codepoints"][dest] = json!(points);
                    }
                    json!(raw)
                }
            }
        };
        if let Some(choices) = option["choices"].as_array()
            && !choices.contains(&value)
        {
            return failure(
                format!(
                    "argument {flag}: invalid choice: {} (choose from {})",
                    repr(value.as_str().unwrap_or("")),
                    choices
                        .iter()
                        .map(|value| value.as_str().unwrap_or(""))
                        .collect::<Vec<_>>()
                        .join(", ")
                ),
                false,
            );
        }
        if kind == "_AppendAction" {
            if args.get(dest).is_none() {
                args[dest] = json!([]);
            }
            if let Some(items) = args[dest].as_array_mut() {
                items.push(value);
            }
        } else {
            args[dest] = value;
        }
        index += 1;
    }
    if global_help {
        if let Some(error) = help_error {
            return after_admission(failure(error, true), args);
        }
        return after_admission(output(ROOT_HELP.into(), 0, false), args);
    }
    if help {
        if let Some(error) = help_error {
            return after_admission(failure(error, true), args);
        }
        return after_admission(output(HELP.into(), 0, false), args);
    }
    if !unknown.is_empty() {
        return after_admission(
            output(
                format!(
                    "{ROOT_USAGE}{PROG}: error: unrecognized arguments: {}\n",
                    unknown.join(" ")
                ),
                2,
                true,
            ),
            args,
        );
    }
    Parsed::Args(args)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[cfg(unix)]
    #[test]
    fn direct_path_values_preserve_non_utf8_bytes() {
        use std::os::unix::ffi::OsStringExt;
        let cwd = Path::new("/synthetic");
        let name = OsString::from_vec(b"prompt-\xff/./".to_vec());
        for option in ["--repo-root", "--codex-args-file", "--jobs-db"] {
            let key = match option {
                "--repo-root" => "repo_root",
                "--codex-args-file" => "codex_args_file",
                _ => "jobs_db",
            };
            for inline in [false, true] {
                let mut argv = vec![OsString::from("execute")];
                if inline {
                    let mut value = OsString::from(format!("{option}="));
                    value.push(&name);
                    argv.push(value);
                } else {
                    argv.extend([OsString::from(option), name.clone()]);
                }
                let Parsed::Args(args) = parse(&argv, cwd) else {
                    panic!("path argument rejected");
                };
                assert_eq!(
                    crate::executor_execute::value_path(&args[key], cwd),
                    cwd.join(OsString::from_vec(b"prompt-\xff".to_vec())),
                    "non-UTF8 bytes must not become escaped text"
                );
            }
        }
    }

    #[cfg(unix)]
    #[test]
    fn direct_path_default_preserves_non_utf8_cwd() {
        use std::os::unix::ffi::OsStringExt;
        let cwd = std::path::PathBuf::from(OsString::from_vec(b"/synthetic-\xff".to_vec()));
        let Parsed::Args(args) = parse(&[OsString::from("execute")], &cwd) else {
            panic!("default cwd rejected");
        };
        assert_eq!(
            crate::executor_execute::value_path(&args["repo_root"], &cwd),
            cwd
        );
    }

    #[test]
    fn direct_dispatch_respects_end_options_and_option_values() {
        let raw = |items: &[&str]| items.iter().map(OsString::from).collect::<Vec<_>>();
        assert!(!dispatch(&raw(&["execute", "--", "--dispatch"])));
        assert!(!dispatch(&raw(&["execute", "--codex-args=--dispatch"])));
        assert!(dispatch(&raw(&["execute", "--dispatch"])));
        assert!(dispatch(&raw(&["--", "execute", "--dispatch"])));
    }

    #[test]
    fn direct_repeated_global_terminator_is_an_invalid_subcommand() {
        let raw = ["--", "--", "execute"].map(OsString::from);
        let Parsed::Output {
            text, code, error, ..
        } = parse(&raw, Path::new("/synthetic"))
        else {
            panic!("expected root parser failure");
        };
        assert_eq!((code, error), (2, true));
        assert_eq!(
            text,
            "usage: python -m tools.mir_executor [--jobs-db PATH]\n                                    {execute,status,result,cancel,resume,list-jobs,sweep}\n                                    ...\npython -m tools.mir_executor: error: argument subcommand: invalid choice: '--' (choose from execute, status, result, cancel, resume, list-jobs, sweep)\n"
        );
    }

    #[test]
    fn direct_native_source_has_only_named_compatibility_declines() {
        let source = include_str!("executor_execute.rs");
        let direct = source
            .split("let (argv, environment, python, parsed) = if direct {")
            .nth(1)
            .unwrap()
            .split("let Some(argv) = preflight(raw)")
            .next()
            .unwrap();
        assert_eq!(direct.matches("executor_protocol::decline(").count(), 2);
        assert!(direct.contains("execute stream codec or error handler"));
        assert!(direct.contains("execute invoking-home local parser extension"));
        assert!(source.contains("Ok(Admission::Decline { reason, .. }) if !direct"));
    }
}

#[cfg(test)]
#[path = "executor_execute_parser_numeric_tests.rs"]
mod numeric_tests;
