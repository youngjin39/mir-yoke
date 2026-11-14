//! Explicit-checkout CLI behind the POSIX user-runtime launcher.
#![forbid(unsafe_code)]
use crate::{
    adoption_fs, executor_text as text,
    mir_cli::bootstrap_adoption as input,
    user_runtime_install::{quoted as quote, *},
    user_runtime_transaction::{RuntimePlan, apply_transaction},
};
use std::{
    ffi::OsString,
    io::{self, IsTerminal, Write},
    path::{Path, PathBuf},
    process::Command,
};
fn width() -> usize {
    std::env::var("COLUMNS")
        .ok()
        .and_then(|v| crate::executor_execute_parser::integer_text(&v))
        .and_then(|v| v.parse::<usize>().ok())
        .filter(|n| *n > 0)
        .unwrap_or(80)
        .saturating_sub(2)
        .max(11)
}
fn usage() -> String {
    let prog = "install_user_runtime_agents.py";
    let parts = [
        "[-h]",
        "--claude-home",
        "CLAUDE_HOME",
        "--codex-home",
        "CODEX_HOME",
        "[--apply]",
    ];
    let mut out = format!("usage: {prog}");
    let indent = if (7 + prog.len()) * 4 <= width() * 3 {
        7 + prog.len() + 1
    } else {
        out.push('\n');
        7
    };
    let mut length = if out.ends_with('\n') { 0 } else { out.len() };
    for part in parts {
        if length > 0 && length + 1 + part.len() > width() {
            out.push('\n');
            length = 0;
        }
        if length == 0 {
            out.push_str(&" ".repeat(indent));
            length = indent;
        } else {
            out.push(' ');
            length += 1;
        }
        out.push_str(part);
        length += part.len();
    }
    out.push('\n');
    out
}
fn wrap(text: &str, width: usize) -> Vec<String> {
    let mut lines = vec![String::new()];
    for word in text.split_whitespace() {
        let pieces: Vec<_> = if word.as_bytes()[0].is_ascii_alphabetic() {
            word.split_inclusive('-').collect()
        } else {
            vec![word]
        };
        for (i, piece) in pieces.iter().enumerate() {
            let current = {
                let i = lines.len() - 1;
                &mut lines[i]
            };
            let space = usize::from(!current.is_empty() && i == 0);
            if piece.len() <= width
                && current.len() + space + piece.len() > width
                && !current.is_empty()
            {
                lines.push(String::new());
            }
            let current = {
                let i = lines.len() - 1;
                &mut lines[i]
            };
            if !current.is_empty() && i == 0 {
                current.push(' ');
            }
            let mut rest = *piece;
            while !rest.is_empty() {
                let index = lines.len() - 1;
                let available = width.saturating_sub(lines[index].len());
                if available == 0 {
                    lines.push(String::new());
                    continue;
                }
                let length = available.min(rest.len());
                lines[index].push_str(&rest[..length]);
                rest = &rest[length..];
                if !rest.is_empty() {
                    lines.push(String::new());
                }
            }
        }
    }
    lines
}
fn help() -> String {
    let description = "Install reviewed Yoke agents and Claude commands into explicit user homes. This is deliberately separate from plugin activation. It reads only the checked-in capability allowlists, never infers a home directory, and writes only with --apply.";
    let mut out = format!("\n{}\n\noptions:\n", wrap(description, width()).join("\n"));
    let position = 24.min(width().saturating_sub(20).max(4));
    for (label, message) in [
        ("-h, --help", "show this help message and exit"),
        ("--claude-home CLAUDE_HOME", ""),
        ("--codex-home CODEX_HOME", ""),
        ("--apply", "perform the otherwise dry-run sync"),
    ] {
        out.push_str(&format!("  {label}"));
        if message.is_empty() {
            out.push('\n');
            continue;
        }
        let same_line = label.len() <= position.saturating_sub(4);
        if same_line {
            out.push_str(&" ".repeat(position - label.len() - 2));
        } else {
            out.push('\n');
            out.push_str(&" ".repeat(position));
        }
        out.push_str(
            &wrap(message, width().saturating_sub(position).max(11))
                .join(&format!("\n{}", " ".repeat(position))),
        );
        out.push('\n');
    }
    out
}
fn error(class: &'static str, message: impl Into<String>) -> Error {
    Error {
        class,
        message: message.into(),
    }
}
type Output = (i32, String, String);
fn diag(message: String) -> Output {
    (
        2,
        String::new(),
        format!(
            "{}install_user_runtime_agents.py: error: {message}\n",
            usage()
        ),
    )
}
const OPTIONS: [&str; 5] = ["-h", "--help", "--claude-home", "--codex-home", "--apply"];
fn option_like(value: &str) -> bool {
    // CPython 3.12.13 argparse.py:2320-2408 (_parse_optional/_get_option_tuples):
    // exact, single character, '=' exact, prefix tuples, negative number, space.
    if !value.starts_with('-') {
        return false;
    }
    if OPTIONS.contains(&value) {
        return true;
    }
    if value == "-" {
        return false;
    }
    let (prefix, explicit) = value
        .split_once('=')
        .map_or((value, false), |(name, _)| (name, true));
    if explicit && OPTIONS.contains(&prefix) {
        return true;
    }
    let short: String = value.chars().take(2).collect();
    let prefix_match = OPTIONS.iter().any(|option| {
        if value.starts_with("--") {
            option.starts_with(prefix)
        } else {
            *option == short || option.starts_with(prefix)
        }
    });
    if prefix_match {
        return true;
    }
    // Reuse the executor's Python-compatible Unicode negative-number matcher.
    !crate::executor_execute_parser::value_token(value) && !value.contains(' ')
}
fn parse(raw: &[OsString]) -> Result<(PathBuf, PathBuf, bool), Output> {
    let options = &OPTIONS[1..];
    let (mut homes, mut apply, mut unknown, mut i) = ([None, None], false, Vec::new(), 0);
    while i < raw.len() {
        let arg = text::os_text(&raw[i]);
        i += 1;
        if arg == "--" {
            unknown.push(arg);
            unknown.extend(raw[i..].iter().map(|v| text::os_text(v)));
            break;
        }
        let (name, value) = arg
            .split_once('=')
            .map_or((arg.as_str(), None), |(n, v)| (n, Some(v)));
        let matches: Vec<_> = options
            .iter()
            .filter(|o| **o == name || (name.starts_with("--") && o.starts_with(name)))
            .copied()
            .collect();
        if matches.len() > 1 {
            return Err(diag(format!(
                "ambiguous option: {arg} could match {}",
                matches.join(", ")
            )));
        }
        let selected = if name.starts_with("-h") {
            Some("--help")
        } else {
            matches.first().copied()
        };
        let Some(option) = selected else {
            unknown.push(arg);
            continue;
        };
        if option == "--help" || option == "--apply" {
            if value.is_some() && (name == "-h" || !name.starts_with("-h")) {
                return Err(diag(format!(
                    "argument {}: ignored explicit argument {}",
                    if option == "--help" {
                        "-h/--help"
                    } else {
                        option
                    },
                    text::repr_points(
                        &text::os_points(&raw[i - 1])
                            .into_iter()
                            .skip_while(|p| *p != 61)
                            .skip(1)
                            .collect::<Vec<_>>()
                    )
                )));
            }
            if option == "--help" {
                return Err((0, format!("{}{}", usage(), help()), String::new()));
            }
            apply = true;
            continue;
        }
        let path = if value.is_some() {
            // Split the OsStr itself so surrogateescape path bytes survive '='.
            use std::os::unix::ffi::{OsStrExt, OsStringExt};
            OsString::from_vec(
                raw[i - 1]
                    .as_bytes()
                    .splitn(2, |b| *b == b'=')
                    .nth(1)
                    .unwrap_or_default()
                    .to_vec(),
            )
        } else {
            if i == raw.len() || option_like(&text::os_text(&raw[i])) {
                return Err(diag(format!("argument {option}: expected one argument")));
            }
            let v = raw[i].clone();
            i += 1;
            v
        };
        homes[usize::from(option == "--codex-home")] = Some(PathBuf::from(path));
    }
    let missing: Vec<_> = ["--claude-home", "--codex-home"]
        .into_iter()
        .enumerate()
        .filter_map(|(i, n)| homes[i].is_none().then_some(n))
        .collect();
    if !missing.is_empty() {
        return Err(diag(format!(
            "the following arguments are required: {}",
            missing.join(", ")
        )));
    }
    if !unknown.is_empty() {
        return Err(diag(format!(
            "unrecognized arguments: {}",
            unknown.join(" ")
        )));
    }
    Ok((
        homes[0].take().unwrap_or_default(),
        homes[1].take().unwrap_or_default(),
        apply,
    ))
}
fn source_commit(root: &Path) -> Result<String, Error> {
    let git = |args: &[&str]| -> Result<(bool, String), Error> {
        let result = Command::new("git")
            .arg("-C")
            .arg(root)
            .args(args)
            .output()
            .map_err(|e| {
                let e = input::io_error(Path::new("git"), e);
                error(e.class(), e.to_string())
            })?;
        let stdout = input::decode(result.stdout).map_err(|e| error(e.class(), e.to_string()))?;
        input::decode(result.stderr).map_err(|e| error(e.class(), e.to_string()))?;
        Ok((result.status.success(), stdout))
    };
    let (success, status) = git(&["status", "--porcelain"])?;
    if !success {
        return Err(error("SyncError", "cannot establish clean Yoke source"));
    }
    if !status.is_empty() {
        return Err(error(
            "SyncError",
            "Yoke source is dirty; commit or clean it before syncing",
        ));
    }
    let (success, head) = git(&["rev-parse", "HEAD"])?;
    let commit = crate::python_json::python_strip(&head);
    if !success
        || commit.len() != 40
        || !commit
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
    {
        return Err(error("SyncError", "cannot resolve Yoke source Git commit"));
    }
    Ok(commit.into())
}
fn names<'a>(files: impl Iterator<Item = &'a crate::python_json::Text>) -> String {
    let items: Vec<_> = files.map(|f| quote(&f.codepoints)).collect();
    format!("[{}]", items.join(", "))
}
fn cleanup_missing_with(
    missing: &[&Path],
    mut before_unlink: impl FnMut(&Path),
) -> Result<(), Error> {
    let mut missing = missing.to_vec();
    missing.sort_by_key(|p| std::cmp::Reverse(p.components().count()));
    for path in missing {
        if path_metadata(path, true)
            .map_err(|e| error("SyncError", format!("apply failed before transaction: {e}")))?
            .is_none()
        {
            continue;
        }
        let failure = |e| {
            let description = text::io_error(e, path);
            let message = description
                .split_once(": ")
                .map_or(description.as_str(), |(_, m)| m);
            error(
                "SyncError",
                format!("apply failed before transaction: {message}"),
            )
        };
        let parent = adoption_fs::parent(Path::new("/"), path).map_err(failure)?;
        before_unlink(path);
        parent.unlink(&parent.name, true).map_err(failure)?;
    }
    Ok(())
}
fn apply_with(
    homes: [&Path; 2],
    files: [Vec<ManagedFile>; 2],
    stale: [Vec<StaleFile>; 2],
    commit: &str,
    before: impl FnOnce(),
) -> Result<(), Error> {
    let created = homes.map(|p| !p.exists());
    let missing: Vec<_> = homes
        .iter()
        .flat_map(|p| p.ancestors().take_while(|p| !p.exists()))
        .collect();
    before();
    for home in homes {
        let missing: Vec<_> = home.ancestors().take_while(|p| !p.exists()).collect();
        for path in missing.into_iter().rev() {
            adoption_fs::mkdir(Path::new("/"), path, 0o777).map_err(|e| {
                let e = input::io_error(path, e);
                error("SyncError", format!("apply failed before transaction: {e}"))
            })?;
        }
        if !home.is_dir() {
            return Err(error(
                "SyncError",
                format!(
                    "apply failed before transaction: [Errno 17] File exists: {}",
                    text::repr_points(&text::os_points(home.as_os_str()))
                ),
            ));
        }
    }
    let [claude, codex] = homes.map(capture_home_identity);
    let wrap = |e: Error| {
        if e.class == "SyncError" {
            e
        } else {
            error("SyncError", format!("apply failed before transaction: {e}"))
        }
    };
    let identities = [claude.map_err(wrap)?, codex.map_err(wrap)?];
    if runtime_homes_overlap(&identities[0], &identities[1]) {
        cleanup_missing_with(&missing, |_| {})?;
        return Err(error(
            "SyncError",
            "--claude-home and --codex-home must not overlap",
        ));
    }
    let plans: Vec<_> = identities
        .into_iter()
        .zip(files)
        .zip(stale)
        .enumerate()
        .map(|(i, ((identity, files), stale))| RuntimePlan {
            receipt: make_receipt(if i == 0 { "claude" } else { "codex" }, commit, &files),
            identity,
            files,
            stale,
            created_home: created[i],
        })
        .collect();
    apply_transaction(&plans)
}
fn install(root: &Path, claude: &Path, codex: &Path, apply: bool) -> Result<String, Error> {
    let claude = require_safe_home(claude)?;
    let codex = require_safe_home(codex)?;
    if claude.as_os_str().as_encoded_bytes().starts_with(b"//")
        == codex.as_os_str().as_encoded_bytes().starts_with(b"//")
        && (claude.starts_with(&codex) || codex.starts_with(&claude))
    {
        return Err(error(
            "SyncError",
            "--claude-home and --codex-home must not overlap",
        ));
    }
    let commit = source_commit(root)?;
    let (cf, df) = load_sources(root)?;
    let (cr, cs) = validate_targets(&claude, "claude", &cf)?;
    let (dr, ds) = validate_targets(&codex, "codex", &df)?;
    let report = format!(
        "{{\"planned\": {{\"claude\": {}, \"codex\": {}}}, \"planned_removals\": {{\"claude\": {}, \"codex\": {}}}, \"receipts\": {{\"claude\": {}, \"codex\": {}}}, \"shadowing\": \"project-local files take precedence over these user-level files.\", \"source_commit\": \"{commit}\", \"status\": \"{}\"}}\n",
        names(cf.iter().map(|f| &f.source_relative)),
        names(df.iter().map(|f| &f.source_relative)),
        names(cs.iter().map(|f| &f.source_relative)),
        names(ds.iter().map(|f| &f.source_relative)),
        quote(&text::os_points(cr.as_os_str())),
        quote(&text::os_points(dr.as_os_str())),
        if apply { "applied" } else { "dry_run" }
    );
    if apply {
        apply_with([&claude, &codex], [cf, df], [cs, ds], &commit, || {})?;
    }
    Ok(report)
}
// Stdout's standard-library writer suppresses EBADF; a duplicated File preserves
// the descriptor's access mode and exposes the Python-visible write failure.
struct OutputStream;
impl Write for OutputStream {
    fn write(&mut self, bytes: &[u8]) -> io::Result<usize> {
        use std::os::fd::AsFd;
        let descriptor = io::stdout().as_fd().try_clone_to_owned()?;
        std::fs::File::from(descriptor).write(bytes)
    }
    fn flush(&mut self) -> io::Result<()> {
        Ok(())
    }
}
fn output_error(e: &io::Error) -> String {
    match e.raw_os_error() {
        Some(libc::EBADF) => "[Errno 9] Bad file descriptor".into(),
        Some(libc::EPIPE) => "[Errno 32] Broken pipe".into(),
        _ => e.to_string(),
    }
}
/// Consume the explicit provider binding before Python-visible argv.
pub fn run(raw: &[OsString]) -> i32 {
    let Some((root, args)) = raw.split_first() else {
        let _ = io::stderr().write_all(b"error: explicit provider checkout is required\n");
        return 2;
    };
    let parsed = parse(args);
    let parser = parsed.is_err();
    let help = matches!(&parsed, Err((0, _, _)));
    let result = match parsed {
        Err(result) => result,
        Ok((claude, codex, apply)) => match install(Path::new(root), &claude, &codex, apply) {
            Ok(out) => (0, out, String::new()),
            Err(mut e) => {
                if e.class != "SyncError" {
                    e.message.insert_str(0, "unexpected installer failure: ");
                }
                (2, String::new(), format!("error: {e}\n"))
            }
        },
    };
    let (code, out, err) = result;
    let buffered = !io::stdout().is_terminal()
        && !std::env::var_os("PYTHONUNBUFFERED").is_some_and(|v| !v.is_empty() && v != "0");
    let mut stdout = io::BufWriter::with_capacity(if buffered { 8192 } else { 0 }, OutputStream);
    if let Err(e) = stdout.write_all(out.as_bytes()) {
        if help {
            return code;
        }
        let _ = io::stderr().write_all(
            format!(
                "error: unexpected installer failure: {}\n",
                output_error(&e)
            )
            .as_bytes(),
        );
        return 2;
    }
    if io::stderr().write_all(err.as_bytes()).is_err() {
        return if buffered {
            120
        } else if parser {
            code
        } else {
            1
        };
    }
    if let Err(e) = stdout.flush() {
        let message = if e.kind() == io::ErrorKind::BrokenPipe {
            "BrokenPipeError: [Errno 32] Broken pipe".into()
        } else {
            format!("OSError: {}", output_error(&e))
        };
        let _ = io::stderr().write_all(format!("Exception ignored in: <_io.TextIOWrapper name='<stdout>' mode='w' encoding='utf-8'>\n{message}\n").as_bytes());
        return 120;
    }
    code
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    #[test]
    fn overlap_cleanup_contains_ancestor_swap() {
        let tmp = tempfile::tempdir().unwrap();
        let root = fs::canonicalize(tmp.path()).unwrap();
        let parent = root.join("parent");
        let parked = root.join("parked");
        let outside = root.join("outside");
        fs::create_dir_all(parent.join("home")).unwrap();
        fs::create_dir_all(outside.join("home")).unwrap();
        cleanup_missing_with(&[&parent.join("home")], |_| {
            fs::rename(&parent, &parked).unwrap();
            std::os::unix::fs::symlink(&outside, &parent).unwrap();
        })
        .unwrap();
        assert!(outside.join("home").is_dir());
        assert!(!parked.join("home").exists());
        assert_eq!(fs::read_dir(outside).unwrap().count(), 1);
    }
    #[test]
    #[cfg(target_os = "macos")] // Frozen rmdir errno is the macOS reference's 66.
    fn overlap_cleanup_errors_match_reference() {
        let tmp = tempfile::tempdir().unwrap();
        let root = fs::canonicalize(tmp.path()).unwrap();
        fs::create_dir(root.join("b")).unwrap();
        let result = cleanup_missing_with(&[&root.join("b")], |path| {
            fs::write(path.join("child"), b"foreign").unwrap();
        });
        let corpus: serde_json::Value = serde_json::from_str(include_str!(
            "../../../tests/fixtures/user_runtime_install/case-alias.json"
        ))
        .unwrap();
        assert_eq!(
            result
                .unwrap_err()
                .message
                .replace(root.to_str().unwrap(), "{ROOT}"),
            format!(
                "apply failed before transaction: {}",
                corpus["helpers"]["cleanup_error"].as_str().unwrap()
            )
        );
        assert_eq!(fs::read(root.join("b/child")).unwrap(), b"foreign");
    }
    #[test]
    fn cleanup_metadata_errors_match_reference() {
        use std::os::unix::fs::PermissionsExt;
        let tmp = tempfile::tempdir().unwrap();
        let root = fs::canonicalize(tmp.path()).unwrap();
        let denied = root.join("denied");
        fs::create_dir_all(denied.join("home")).unwrap();
        fs::set_permissions(&denied, fs::Permissions::from_mode(0o0)).unwrap();
        let privileged = fs::metadata(denied.join("home")).is_ok();
        let result = cleanup_missing_with(&[&denied.join("home")], |_| {});
        fs::set_permissions(&denied, fs::Permissions::from_mode(0o700)).unwrap();
        if privileged {
            return;
        } // Root bypasses the permission-denial scenario.
        let corpus: serde_json::Value = serde_json::from_str(include_str!(
            "../../../tests/fixtures/user_runtime_install/case-alias.json"
        ))
        .unwrap();
        assert_eq!(
            result
                .unwrap_err()
                .message
                .replace(root.to_str().unwrap(), "{ROOT}"),
            format!(
                "apply failed before transaction: {}",
                corpus["helpers"]["cleanup_stat_error"].as_str().unwrap()
            )
        );
        assert!(denied.join("home").is_dir());
    }
    #[test]
    fn creation_rejects_ancestor_swap() {
        let tmp = tempfile::tempdir().unwrap();
        let root = fs::canonicalize(tmp.path()).unwrap();
        let parent = root.join("parent");
        let outside = root.join("outside");
        fs::create_dir(&parent).unwrap();
        fs::create_dir(&outside).unwrap();
        let claude = require_safe_home(&parent.join("claude")).unwrap();
        let codex = root.join("codex");
        let result = apply_with(
            [&claude, &codex],
            [vec![], vec![]],
            [vec![], vec![]],
            &"f".repeat(40),
            || {
                fs::remove_dir(&parent).unwrap();
                std::os::unix::fs::symlink(&outside, &parent).unwrap();
            },
        );
        assert!(result.is_err());
        assert_eq!(fs::read_dir(outside).unwrap().count(), 0);
    }
}
