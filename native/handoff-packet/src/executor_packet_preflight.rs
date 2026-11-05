//! Read-only representation checks before packet ownership or target hook imports.
use crate::{executor_development_packet::supports, executor_execute};
use serde_json::Value;
use std::{fs, path::Path};

fn file_supported(path: &str, cwd: &Path, brief: bool) -> bool {
    let path = Path::new(path);
    let path = if path.is_absolute() {
        path.to_owned()
    } else {
        cwd.join(path)
    };
    // The owned validation path retains file, encoding and syntax diagnostics.
    fs::read_to_string(path).map_or(true, |text| {
        let text = text.replace("\r\n", "\n").replace('\r', "\n");
        if brief {
            brief_supported(&text)
        } else {
            supports(&text)
        }
    })
}

fn brief_supported(text: &str) -> bool {
    supports(text)
        && serde_json::from_str::<Value>(text).map_or(true, |value| {
            value["expanded_goal"].as_str().is_none_or(supports)
        })
}

fn argv_supported(argv: &[String]) -> bool {
    supports(&executor_execute::prompt(argv))
}

/// Input precedence matches resolve_args: a raw input file wins over shell argv.
pub(crate) fn execute(argv: &[String], cwd: &Path) -> bool {
    let Ok(schema) = serde_json::from_str::<Value>(include_str!(
        "../tests/fixtures/executor_admission_schema.json"
    )) else {
        return false;
    };
    let mut codex_args = None;
    let mut codex_args_file = None;
    let mut dispatch_brief = None;
    let mut index = argv
        .iter()
        .position(|word| word == "execute")
        .map_or(argv.len(), |index| index + 1);
    while let Some(token) = argv.get(index) {
        let (flag, inline) = token
            .split_once('=')
            .map_or((token.as_str(), None), |(flag, value)| (flag, Some(value)));
        let Some(option) = schema["execute"].as_array().and_then(|options| {
            options.iter().find(|option| {
                option["flags"]
                    .as_array()
                    .is_some_and(|flags| flags.iter().any(|value| value == flag))
            })
        }) else {
            // The caller has already checked the schema; preserve parser errors.
            return true;
        };
        if matches!(
            option["kind"].as_str(),
            Some("_StoreAction" | "_AppendAction")
        ) {
            let value = inline.or_else(|| {
                index += 1;
                argv.get(index).map(String::as_str)
            });
            match option["dest"].as_str() {
                Some("codex_args") => codex_args = value,
                Some("codex_args_file") => codex_args_file = value,
                Some("dispatch_brief") => dispatch_brief = value,
                _ => (),
            }
        }
        index += 1;
    }
    let input_supported = if let Some(path) = codex_args_file {
        file_supported(path, cwd, false)
    } else {
        codex_args.is_none_or(|text| {
            executor_execute::shell_words(text).map_or(true, |argv| argv_supported(&argv))
        })
    };
    input_supported && dispatch_brief.is_none_or(|path| file_supported(path, cwd, true))
}

/// Inspect the existing row without migrating its registry or authorizing targets.
pub(crate) fn resume(row: &Value, cwd: &Path) -> bool {
    let argv = row["codex_args"].as_array().and_then(|argv| {
        argv.iter()
            .map(|value| value.as_str().map(str::to_owned))
            .collect::<Option<Vec<_>>>()
    });
    let saved = row["dispatch_options_json"]
        .as_str()
        .and_then(|text| serde_json::from_str::<Value>(text).ok());
    let brief = saved
        .as_ref()
        .and_then(|saved| saved["dispatch_brief"].as_str())
        .filter(|path| !path.is_empty())
        .or_else(|| row["dispatch_brief_path"].as_str());
    argv.is_none_or(|argv| argv_supported(&argv))
        && brief.is_none_or(|path| file_supported(path, cwd, true))
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    use std::{
        path::PathBuf,
        sync::atomic::{AtomicU64, Ordering},
    };

    static SERIAL: AtomicU64 = AtomicU64::new(0);
    struct Scratch(PathBuf);
    impl Scratch {
        fn new() -> Self {
            let path = std::env::current_dir().unwrap().join(format!(
                ".packet-preflight-{}-{}",
                std::process::id(),
                SERIAL.fetch_add(1, Ordering::Relaxed)
            ));
            fs::create_dir(&path).unwrap();
            Self(path)
        }
        fn write(&self, name: &str, text: &str) {
            fs::write(self.0.join(name), text).unwrap();
        }
    }
    impl Drop for Scratch {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.0);
        }
    }
    fn args(words: &[&str]) -> Vec<String> {
        words.iter().map(|word| (*word).to_owned()).collect()
    }

    #[test]
    fn shell_argv_checks_the_extracted_packet_and_preserves_parser_errors() {
        let cwd = Path::new(".");
        assert!(!execute(
            &args(&["execute", "--codex-args", r#"exec '{"task":"\ud800"}'"#]),
            cwd
        ));
        assert!(!execute(
            &args(&["execute", "--codex-args=exec '{\"task\":NaN}'"]),
            cwd
        ));
        assert!(!execute(
            &args(&[
                "--jobs-db",
                "jobs.db",
                "execute",
                "--codex-args",
                r#"exec '{"task":"\ud800"}'"#
            ]),
            cwd
        ));
        assert!(execute(
            &args(&["execute", "--codex-args", "'unterminated"]),
            cwd
        ));
        assert!(execute(
            &args(&["execute", "--codex-args", "'{malformed'"]),
            cwd
        ));
        assert!(execute(&args(&["execute", "--codex-args", "plain"]), cwd));
    }

    #[test]
    fn brief_checks_both_the_outer_payload_and_nested_packet_text() {
        assert!(!brief_supported(r#"{"target_agent":"\ud800"}"#));
        assert!(!brief_supported(
            &json!({"expanded_goal":r#"{"task":"\ud800"}"#}).to_string()
        ));
        assert!(!brief_supported(
            &json!({"expanded_goal":r#"{"kind":NaN}"#}).to_string()
        ));
        assert!(brief_supported(
            &json!({"expanded_goal":r#"{"task":"Caf\u00e9"}"#}).to_string()
        ));
        assert!(brief_supported("{malformed"));
    }

    #[test]
    fn raw_files_take_precedence_and_missing_files_keep_owned_diagnostics() {
        let scratch = Scratch::new();
        scratch.write("raw.txt", r#"{"task":"\ud800"}"#);
        scratch.write("safe.txt", "plain task");
        assert!(!execute(
            &args(&["execute", "--codex-args-file", "raw.txt"]),
            &scratch.0
        ));
        assert!(execute(
            &args(&[
                "execute",
                "--codex-args",
                r#"'{"task":"\ud800"}'"#,
                "--codex-args-file",
                "safe.txt"
            ]),
            &scratch.0
        ));
        assert!(execute(
            &args(&["execute", "--codex-args-file", "missing.txt"]),
            &scratch.0
        ));
        scratch.write(
            "brief.json",
            &json!({"expanded_goal":r#"{"task":"\ud800"}"#}).to_string(),
        );
        assert!(!execute(
            &args(&["execute", "--dispatch", "--dispatch-brief", "brief.json"]),
            &scratch.0
        ));
    }

    #[test]
    fn resume_checks_saved_argv_and_effective_saved_brief() {
        let scratch = Scratch::new();
        scratch.write("safe.json", "{}");
        scratch.write(
            "unsupported.json",
            &json!({"expanded_goal":r#"{"task":"\ud800"}"#}).to_string(),
        );
        let mut row = json!({"codex_args":["exec", r#"{"task":"\ud800"}"#],"dispatch_brief_path":"safe.json"});
        assert!(!resume(&row, &scratch.0));
        row["codex_args"] = json!(["plain task"]);
        row["dispatch_options_json"] =
            json!(json!({"dispatch_brief":"unsupported.json"}).to_string());
        assert!(!resume(&row, &scratch.0));
        row["dispatch_options_json"] = json!(json!({"dispatch_brief":""}).to_string());
        assert!(resume(&row, &scratch.0));
    }
}
