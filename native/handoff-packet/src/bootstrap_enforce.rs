//! Protocol 1 port of the pinned incomplete-bootstrap shell policy.
//! External payload/manifest objects tolerate unknown fields, as jq does.
use crate::bootstrap_state::{linked, logical_directory, read_json, regular};
use regex::Regex;
use serde_json::Value;
use std::{
    fs,
    path::Path,
    process::{Command, Stdio},
};

fn matches(pattern: &str, text: &str) -> bool {
    Regex::new(pattern).is_ok_and(|re| re.is_match(text))
}

// jq -r formats composite values; Bash substitution drops NUL and trailing LF.
fn raw(value: &Value, default: &str) -> String {
    let text = match value {
        Value::Null | Value::Bool(false) => default.into(),
        Value::String(s) => s.clone(),
        _ => serde_json::to_string_pretty(value).unwrap_or_default(),
    };
    text.replace('\0', "").trim_end_matches('\n').into()
}

pub fn instructions(state: &str, root: &Path) -> String {
    let mut output = format!(
        "bootstrap_gate: required (state={state})\nnormal_mutation: blocked until .mir/bootstrap-receipt.json has status=ready\n"
    );
    let manifest = root.join("config/bootstrap-adoption.json");
    if manifest.is_file() {
        let pin = fs::read(&manifest)
            .ok()
            .and_then(|bytes| crate::bootstrap_json::instruction_pin(&bytes))
            .unwrap_or_default();
        let pin = if pin.is_empty() {
            "the mir_yoke_source_commit in config/bootstrap-adoption.json"
        } else {
            &pin
        };
        output.push_str(&format!("existing_repository: complete tracked adoption evidence, then reissue the receipt\nrecovery_command: uv run --project <provider worktree> mir bootstrap-adoption --apply\nrecovery_source: detached provider worktree at {pin}, with a clean tree\n"));
    } else {
        output.push_str("phase_1: run setup.sh with --profile, --purpose, and --stack (inside WSL on Windows hosts)\nphase_2: restart, run mir-core:design then mir-core:spec-architect, write coverage/gap evidence, and finalize\n");
    }
    output
}

fn allowed_path(path: &str, root: &Path) -> bool {
    let path = path.replace('\\', "/");
    let Some(root_text) = root.to_str() else {
        return false;
    };
    let project = root_text.replace('\\', "/");
    let project = project.strip_suffix('/').unwrap_or(&project);
    let normalized = if let Some(path) = path.strip_prefix(&format!("{project}/")) {
        path
    } else {
        if path.starts_with('/') || matches(r"^[A-Za-z]:/", &path) {
            return false;
        }
        &path
    };
    let normalized = normalized.strip_prefix("./").unwrap_or(normalized);
    if normalized.split('/').any(|c| c == ".." || c == ".") {
        return false;
    }
    let mut current = root.to_path_buf();
    for component in normalized.split('/').filter(|c| !c.is_empty()) {
        current.push(component);
        if linked(&current) {
            return false;
        }
    }
    if normalized.starts_with("spec/")
        || matches!(
            normalized,
            "config/bootstrap-adoption.json" | "config/content-onboarding.json"
        )
    {
        return true;
    }
    let manifest = root.join("config/bootstrap-adoption.json");
    if !regular(&manifest) {
        return false;
    }
    let manifest = read_json(&manifest).unwrap_or(Value::Null);
    let surfaces: Vec<_> = match &manifest["surfaces"] {
        Value::Object(o) => o.values().collect(),
        Value::Array(a) => a.iter().collect(),
        _ => Vec::new(),
    };
    // jq builds the entire array before index(); later scalars still fail.
    if surfaces.iter().any(|s| !s.is_object() && !s.is_null()) {
        return false;
    }
    surfaces.into_iter().any(|s| match &s["evidence_paths"] {
        Value::Array(a) => a.iter().any(|p| p.as_str() == Some(normalized)),
        Value::Object(o) => o.values().any(|p| p.as_str() == Some(normalized)),
        _ => false,
    })
}

fn patch_allowed(patch: &str, root: &Path) -> bool {
    if matches(r"(?m)^\*\*\* Move to:", patch)
        || matches(
            r"(?m)^\*\*\* Delete File: (.*[/\\])?config[/\\]bootstrap-adoption\.json$",
            patch,
        )
    {
        return false;
    }
    let Ok(re) = Regex::new(r"(?m)^\*\*\* (Add|Update|Delete) File: (.*)$") else {
        return false;
    };
    let mut found = false;
    for capture in re.captures_iter(patch) {
        let path = &capture[2];
        if path.is_empty() {
            continue;
        }
        found = true;
        if !allowed_path(path, root) {
            return false;
        }
    }
    found
}

fn shell_patch_allowed(command: &str, root: &Path) -> bool {
    command.split('\n').next() == Some("apply_patch <<'PATCH'")
        && command.split('\n').next_back() == Some("PATCH")
        && command.split('\n').filter(|line| *line == "PATCH").count() == 1
        && patch_allowed(command, root)
}

fn git_output(root: &Path, args: &[&str], safe: bool) -> Option<std::process::Output> {
    let mut command = Command::new("git");
    command.args(["--no-replace-objects", "--no-lazy-fetch"]);
    if safe {
        command.args([
            "-c",
            "core.hooksPath=/dev/null",
            "-c",
            "core.fsmonitor=false",
            "-c",
            "core.attributesFile=/dev/null",
        ]);
    }
    command
        .arg("-C")
        .arg(root)
        .args(args)
        .stdin(Stdio::null())
        .stderr(Stdio::null())
        .output()
        .ok()
}
fn git_text(root: &Path, args: &[&str], safe: bool) -> Option<String> {
    let result = git_output(root, args, safe)?;
    if !result.status.success() {
        return None;
    }
    String::from_utf8(result.stdout)
        .ok()
        .map(|s| s.trim_end_matches('\n').into())
}
fn official_origin(root: &Path) -> bool {
    matches!(
        git_text(root, &["remote", "get-url", "origin"], false).as_deref(),
        Some(
            "https://github.com/youngjin39/mir-yoke.git" | "git@github.com:youngjin39/mir-yoke.git"
        )
    )
}
fn provider_source(root: &Path) -> bool {
    let profile = root.join(".mir/repo-profile.toml");
    if profile.exists() || linked(&profile) {
        return regular(&profile) && fs::read_to_string(profile).is_ok_and(|text| {
            text.split('\n').any(|line| matches(r#"^[[:space:]]*slug[[:space:]]*=[[:space:]]*"mir-yoke""#, line))
            && text.split('\n').any(|line| matches(r#"^[[:space:]]*repository_type[[:space:]]*=[[:space:]]*"public_harness_template""#, line))
        });
    }
    official_origin(root)
}
fn unsafe_extensions(root: &Path) -> bool {
    if git_output(root, &["config", "--get-regexp", r"^(filter\..*\.(clean|smudge|process|required)|core\.(hooksPath|fsmonitor|attributesFile))$"], false).is_some_and(|o| o.status.success()) { return true; }
    let Some(common) = git_text(root, &["rev-parse", "--git-common-dir"], false) else {
        return true;
    };
    let common = if common.starts_with('/') {
        Path::new(&common).to_path_buf()
    } else {
        root.join(common)
    };
    let attributes = common.join("info/attributes");
    attributes.exists() || linked(&attributes)
}

fn git_add_allowed(command: &str, root: &Path) -> bool {
    let Ok(re) = Regex::new(
        r#"^[[:space:]]*git[[:space:]]+add[[:space:]]+--[[:space:]]+("[^"]+"|'[^']+'|[^[:space:]'"]+)[[:space:]]*$"#,
    ) else {
        return false;
    };
    let Some(capture) = re.captures(command) else {
        return false;
    };
    let path = &capture[1];
    let path = if path.starts_with(['\'', '"']) {
        &path[1..path.len() - 1]
    } else {
        path
    };
    if path.starts_with(':')
        || path.contains(['*', '?', '[', ']', '{', '}', '$', '~', '\\', '!', '(', ')'])
    {
        return false;
    }
    // The shell prefixes even an absolute argument; Path::join would discard root.
    let Some(root_text) = root.to_str() else {
        return false;
    };
    let file = format!("{root_text}/{path}");
    allowed_path(path, root) && regular(Path::new(&file))
}

fn pinned_commit(root: &Path) -> String {
    raw(
        &read_json(&root.join("config/bootstrap-adoption.json")).unwrap_or(Value::Null)["mir_yoke_source_commit"],
        "",
    )
}

fn worktree_add_allowed(command: &str, root: &Path) -> bool {
    let Ok(re) = Regex::new(
        r#"^[[:space:]]*git[[:space:]]+--no-replace-objects[[:space:]]+--no-lazy-fetch[[:space:]]+-c[[:space:]]+core\.hooksPath=/dev/null[[:space:]]+-c[[:space:]]+core\.fsmonitor=false[[:space:]]+-c[[:space:]]+core\.attributesFile=/dev/null[[:space:]]+-C[[:space:]]+"([^"]+)"[[:space:]]+worktree[[:space:]]+add[[:space:]]+--detach[[:space:]]+"([^"]+)"[[:space:]]+([0-9a-f]{40})[[:space:]]*$"#,
    ) else {
        return false;
    };
    let Some(capture) = re.captures(command) else {
        return false;
    };
    let (source, target, commit) = (&capture[1], &capture[2], &capture[3]);
    if source.contains(['$', '\\', '!']) || target.contains(['$', '\\', '!']) {
        return false;
    }
    let source_path = Path::new(source);
    if !source.starts_with('/')
        || !source_path.is_dir()
        || linked(source_path)
        || logical_directory(source_path)
            .as_deref()
            .map(Path::as_os_str)
            != Some(source_path.as_os_str())
        || !official_origin(source_path)
        || unsafe_extensions(source_path)
        || !regular(&root.join("config/bootstrap-adoption.json"))
        || commit != pinned_commit(root)
        || git_text(
            source_path,
            &["cat-file", "-e", &format!("{commit}^{{commit}}")],
            false,
        )
        .is_none()
    {
        return false;
    }
    let Some((parent, name)) = target.rsplit_once('/') else {
        return false;
    };
    let parent = Path::new(parent);
    if !parent.is_dir() || linked(parent) {
        return false;
    }
    let Some(real_parent) = logical_directory(parent) else {
        return false;
    };
    let temp = logical_directory(Path::new(&nonempty_env("TMPDIR", "/tmp")));
    let provider =
        logical_directory(&Path::new(&nonempty_env("HOME", "/nonexistent")).join(".mir/providers"));
    if temp.as_ref() != Some(&real_parent) && provider.as_ref() != Some(&real_parent) {
        return false;
    }
    let Some(real_text) = real_parent.to_str() else {
        return false;
    };
    target == format!("{real_text}/{name}")
        && name == format!("mir-yoke-bootstrap-{}", &commit[..12])
        && !Path::new(target).exists()
        && !linked(Path::new(target))
}

fn nonempty_env(name: &str, default: &str) -> String {
    std::env::var(name)
        .ok()
        .filter(|s| !s.is_empty())
        .unwrap_or_else(|| default.into())
}

fn safe_single_command(command: &str, root: &Path) -> bool {
    if command.contains(['\n', '\r', ';', '&', '|', '<', '>', '\x60']) || command.contains("$(") {
        return false;
    }
    let adoption = root.join("config/bootstrap-adoption.json").exists();
    if matches(
        r"^[[:space:]]*(\./setup\.sh|\.\\setup\.ps1)([[:space:]].*)?[[:space:]]*$",
        command,
    ) {
        return !adoption;
    }
    let uv_project = r#"(--project[[:space:]]+("[^"]+"|'[^']+'|[^[:space:]]+)[[:space:]]+)?"#;
    let verb = if adoption {
        "bootstrap-adoption"
    } else {
        "bootstrap"
    };
    if matches(
        &format!(
            r"^[[:space:]]*uv[[:space:]]+run[[:space:]]+{uv_project}mir[[:space:]]+{verb}([[:space:]].*)?[[:space:]]*$"
        ),
        command,
    ) {
        let marker = if command.contains("mir bootstrap-adoption") {
            "mir bootstrap-adoption"
        } else {
            "mir bootstrap"
        };
        let args = command.split_once(marker).map_or(command, |(_, args)| args);
        let Ok(re) =
            Regex::new(r#"(^|[[:space:]])--project-root[[:space:]]+(\.|"\."|'\.')([[:space:]]|$)"#)
        else {
            return false;
        };
        return !matches(r"(^|[[:space:]])--project", &re.replace_all(args, " "));
    }
    if matches(
        r"^[[:space:]]*git[[:space:]]+status([[:space:]].*)?[[:space:]]*$",
        command,
    ) || git_add_allowed(command, root)
        || worktree_add_allowed(command, root)
    {
        return true;
    }
    if matches(
        r"^[[:space:]]*git[[:space:]]+diff([[:space:]].*)?[[:space:]]*$",
        command,
    ) {
        return !["--output", "--ext-diff", "--textconv"]
            .iter()
            .any(|s| command.contains(s));
    }
    if matches(
        r"^[[:space:]]*(ls|pwd|head|tail|jq)([[:space:]].*)?[[:space:]]*$",
        command,
    ) {
        return true;
    }
    matches(r"^[[:space:]]*rg([[:space:]].*)?[[:space:]]*$", command) && !command.contains("--pre")
}

fn uv_project_allowed(command: &str, root: &Path) -> bool {
    let command = command.trim_start_matches(|c: char| c.is_ascii_whitespace());
    let Some(rest) = command.strip_prefix("uv run --project ") else {
        return true;
    };
    let source = if let Some(rest) = rest.strip_prefix('"') {
        rest.split('"').next().unwrap_or("")
    } else if let Some(rest) = rest.strip_prefix('\'') {
        rest.split('\'').next().unwrap_or("")
    } else {
        rest.split(|c: char| c.is_ascii_whitespace())
            .next()
            .unwrap_or("")
    };
    let path = Path::new(source);
    if source.is_empty()
        || !path.is_dir()
        || linked(path)
        || logical_directory(path).as_deref().map(Path::as_os_str) != Some(path.as_os_str())
        || !provider_source(path)
        || unsafe_extensions(path)
    {
        return false;
    }
    let expected = pinned_commit(root);
    !expected.is_empty()
        && git_text(path, &["rev-parse", "HEAD"], false).as_deref() == Some(expected.as_str())
        && git_text(
            path,
            &["status", "--porcelain", "--untracked-files=normal"],
            true,
        )
        .as_deref()
            == Some("")
}

fn workdir_allowed(input: &Value, root: &Path) -> bool {
    let requested = raw(&input["workdir"], "");
    if requested.is_empty() {
        return true;
    }
    let project = logical_directory(root);
    project.is_some() && project == logical_directory(Path::new(&requested))
}

pub fn enforce(payload: &[u8], root: &Path) -> (String, i32) {
    let (state, code) = crate::bootstrap_state::evaluate(root);
    if code == 64 {
        return (String::new(), 64);
    }
    if code == 0 {
        return (String::new(), 0);
    }
    let state = raw(&state["state"], "invalid");
    // jq selects only the fields below; other payload fields are immaterial.
    let payload: Value = serde_json::from_slice(payload).unwrap_or(Value::Null);
    let tool = raw(&payload["tool_name"], "");
    let input = &payload["tool_input"];
    let command = raw(&input["command"], "");
    let adoption = root.join("config/bootstrap-adoption.json").is_file();
    if state == "invalid" && !adoption {
        if tool == "Bash"
            && workdir_allowed(input, root)
            && safe_single_command(&command, root)
            && uv_project_allowed(&command, root)
        {
            return (String::new(), 0);
        }
        return ("[BootstrapGate BLOCK] bootstrap is invalid; repair the receipt-bound runtime with setup.sh\n".into(), 2);
    }
    let allowed = match tool.as_str() {
        "Bash" => {
            if !workdir_allowed(input, root) {
                return ("[BootstrapGate BLOCK] bootstrap command workdir must remain the current project\n".into(), 2);
            }
            shell_patch_allowed(&command, root)
                || (safe_single_command(&command, root) && uv_project_allowed(&command, root))
        }
        "Write" | "Edit" => allowed_path(&first_raw(input, &["file_path", "path"]), root),
        "apply_patch" | "ApplyPatch" => patch_allowed(
            &first_raw(input, &["command", "input", "patch", "content"]),
            root,
        ),
        _ => false,
    };
    if allowed {
        return (String::new(), 0);
    }
    let mut error = format!(
        "[BootstrapGate BLOCK] bootstrap is {state}; normal work must wait for Phase 2 ready receipt\n[BootstrapGate BLOCK] only setup/adoption, memory/spec verification, and declared evidence edits are allowed\n"
    );
    if state == "invalid" && adoption {
        error.push_str("[BootstrapGate BLOCK] restore the drifted declared evidence, then reissue with uv run --project <provider worktree> mir bootstrap-adoption --apply\n");
    }
    (error, 2)
}

fn first_raw(input: &Value, fields: &[&str]) -> String {
    fields
        .iter()
        .map(|field| &input[*field])
        .find(|v| !v.is_null() && **v != false)
        .map_or_else(String::new, |v| raw(v, ""))
}
