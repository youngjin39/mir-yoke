//! Yoke's own advisory, without shell or interpreter dependencies.
//!
//! Parity is frozen under en_US.UTF-8: count Unicode scalars, remove command-
//! substitution NULs and trailing LF, then lowercase before tokenizing. Python
//! Unicode word characters (except underscore) are categories L and N, not the
//! regex crate's broader Unicode word class (which also admits combining marks).
//! Unicode database versions beyond the frozen inputs are intentionally unpinned.
use regex::Regex;
use serde_json::Value;
use std::io::Read;

const INVALID: &str = "[UserPromptSubmit] WARNING: Invalid prompt payload or Python unavailable; context retrieval skipped.\n";
const UNREADABLE: &str =
    "[UserPromptSubmit] WARNING: Prompt payload unavailable; context retrieval skipped.\n";
const STOPWORDS: &str = "a an the is it in on at to for of and or but be are was were been by with as this that these those from into how what why when where which do does did have has had not no all if its i we you he she they them their our my your can will would could should may about up out over then so than more also just some any such each both";

pub fn run(mut input: impl Read) -> (String, &'static str) {
    let mut bytes = Vec::new();
    if input.read_to_end(&mut bytes).is_err() {
        return (String::new(), UNREADABLE);
    }
    // Bash variables cannot hold NUL, including NUL outside the JSON string.
    bytes.retain(|b| *b != 0);
    let Ok(value) = serde_json::from_slice::<Value>(&bytes) else {
        return (String::new(), INVALID);
    };
    let Some(object) = value.as_object() else {
        return (String::new(), INVALID);
    };
    // Additional hook envelope fields are deliberately ignored.
    let prompt = match object.get("prompt") {
        None => "",
        Some(Value::String(prompt)) => prompt.as_str(),
        Some(_) => return (String::new(), INVALID),
    };
    let prompt = prompt.replace('\0', "");
    let prompt = prompt.trim_end_matches('\n');
    if prompt.chars().count() < 40 {
        return (String::new(), "");
    }
    if prompt.trim_start().starts_with(['/', '<']) {
        return (String::new(), "");
    }
    let Ok(tokens) = Regex::new(r"[\p{L}\p{N}]+") else {
        return (
            String::new(),
            "[UserPromptSubmit] WARNING: Prompt tokenization unavailable; context retrieval skipped.\n",
        );
    };
    let lower = prompt.to_lowercase();
    let terms: Vec<_> = tokens
        .find_iter(&lower)
        .map(|token| token.as_str())
        .filter(|token| {
            token.chars().count() > 2 && !STOPWORDS.split_whitespace().any(|s| s == *token)
        })
        .take(6)
        .collect();
    if terms.is_empty() {
        (String::new(), "")
    } else {
        (
            format!(
                "[context-pull] Candidate retrieval: scripts/mir.sh context pull \"{}\"\n",
                terms.join(" ")
            ),
            "",
        )
    }
}
