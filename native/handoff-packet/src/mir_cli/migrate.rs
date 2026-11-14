//! Argparse-compatible migrate CLI, library only; no live dispatch.
use super::memory::Output;
use crate::{executor_execute::repr, mir_core::memory::store};
use std::path::{Path, PathBuf};

const TOP: &str = "usage: mir migrate [-h] {up,status} ...\n";
// Same option-table pattern as mir_cli::relations.
const OPTIONS: &[(&str, Option<&str>)] = &[("--help", None), ("--db", Some("DB"))];
fn usage(action: &str) -> String {
    if action.is_empty() {
        TOP.into()
    } else {
        format!("usage: mir migrate {action} [-h] [--db DB]\n")
    }
}
fn diag(action: &str, message: &str) -> Output {
    let prog = format!(" {action}").trim_end().to_owned();
    (
        2,
        vec![],
        format!("{}mir migrate{prog}: error: {message}\n", usage(action)).into_bytes(),
    )
}
fn help(action: &str) -> Output {
    let body = if action.is_empty() {
        concat!(
            "\npositional arguments:\n  {up,status}\n",
            "    up         apply pending SQL migrations\n",
            "    status     show current schema version\n\noptions:\n",
            "  -h, --help   show this help message and exit\n",
        )
    } else {
        "\noptions:\n  -h, --help  show this help message and exit\n  --db DB\n"
    };
    (0, (usage(action) + body).into_bytes(), vec![])
}
fn option_like(s: &str) -> bool {
    // CPython argparse: ^-\d+$|^-\d*\.\d+$ (including its final-newline anchor).
    let negative = s.strip_suffix('\n').unwrap_or(s);
    let negative = negative.strip_prefix('-').is_some_and(|n| {
        let digits = |v: &str| {
            !v.is_empty()
                && v.chars().all(|c| {
                    // The pinned Python 3.12 regex uses Unicode 15, not 16.
                    crate::python_decimal::decimal_digit(c).is_some()
                        && !matches!(c as u32, 0x10d40..=0x10d49 | 0x116d0..=0x116e3
                                | 0x11bf0..=0x11bf9 | 0x16130..=0x16139 | 0x16d70..=0x16d79
                                | 0x1ccf0..=0x1ccf9 | 0x1e5f1..=0x1e5fa)
                })
        };
        digits(n)
            || n.split_once('.')
                .is_some_and(|(a, b)| (a.is_empty() || digits(a)) && digits(b))
    });
    // Known options and prefixes precede the space fallback in _parse_optional.
    let name = s.split_once('=').map_or(s, |(name, _)| name);
    let known = s.starts_with("-h")
        || OPTIONS
            .iter()
            .any(|o| name.starts_with("--") && o.0.starts_with(name));
    s.len() > 1 && s.starts_with('-') && (known || (!negative && !s.contains(' ')))
}
/// `cwd` supplies default_db_path's only ambient input: cwd/.mir/memory.db.
/// `connect` supplies store.connect, including extension availability/reason.
/// Python exceptions reach `failure` unchanged; Output uses exit 1 for that boundary.
/// Both commands intentionally use the reference's writable connection.
pub fn main(
    argv: &[&str],
    cwd: &Path,
    connect: impl FnOnce(&Path) -> Result<store::Connection, store::Error>,
    failure: impl FnOnce(store::Error),
) -> Output {
    main_with_cwd(argv, || Ok(cwd.to_owned()), connect, failure)
}
/// Resolve cwd only for the default DB, after argparse's help/refusal paths.
pub fn main_with_cwd(
    argv: &[&str],
    cwd: impl FnOnce() -> Result<PathBuf, store::Error>,
    connect: impl FnOnce(&Path) -> Result<store::Connection, store::Error>,
    failure: impl FnOnce(store::Error),
) -> Output {
    let Some(&action) = argv.first() else {
        return diag("", "the following arguments are required: action");
    };
    if let Some((name, value)) = action.split_once('=')
        && (name == "-h" || (name.starts_with("--") && "--help".starts_with(name)))
    {
        return diag(
            "",
            &format!(
                "argument -h/--help: ignored explicit argument {}",
                repr(value)
            ),
        );
    }
    if action.starts_with("-h") && !action.starts_with("-h=") || action == "--help" {
        return help("");
    }
    if !matches!(action, "up" | "status") {
        return diag(
            "",
            &format!(
                "argument action: invalid choice: {} (choose from up, status)",
                repr(action)
            ),
        );
    }
    let (mut db, mut unknown, mut options) = (None, vec![], true);
    let mut i = 1;
    while let Some(&token) = argv.get(i) {
        i += 1;
        if !options || !option_like(token) {
            unknown.push(token);
            continue;
        }
        if token == "--" {
            options = false;
            unknown.push(token);
            continue;
        }
        // argparse processes a concatenated short help option before its tail.
        if token.starts_with("-h") && !token.starts_with("-h=") {
            return help(action);
        }
        let (name, explicit) = token
            .split_once('=')
            .map_or((token, None), |(a, b)| (a, Some(b)));
        let name = if name == "-h" { "--help" } else { name };
        let exact = OPTIONS.iter().find(|o| o.0 == name);
        let matches = OPTIONS
            .iter()
            .filter(|o| name.starts_with("--") && o.0.starts_with(name))
            .collect::<Vec<_>>();
        let option = match (exact, matches.as_slice()) {
            (Some(o), _) => o,
            (None, [o]) => *o,
            (None, []) => {
                unknown.push(token);
                continue;
            }
            (None, _) => {
                return diag(
                    action,
                    &format!(
                        "ambiguous option: {name} could match {}",
                        matches.iter().map(|o| o.0).collect::<Vec<_>>().join(", ")
                    ),
                );
            }
        };
        if option.1.is_none() {
            if let Some(v) = explicit {
                return diag(
                    action,
                    &format!("argument -h/--help: ignored explicit argument {}", repr(v)),
                );
            }
            return help(action);
        }
        db = Some(if let Some(v) = explicit {
            v
        } else {
            let Some(&v) = argv.get(i).filter(|v| !option_like(v)) else {
                return diag(action, "argument --db: expected one argument");
            };
            i += 1;
            v
        });
    }
    if !unknown.is_empty() {
        return diag(
            "",
            &format!("unrecognized arguments: {}", unknown.join(" ")),
        );
    }
    let mut stderr = vec![];
    let result = (|| -> Result<String, store::Error> {
        let default;
        let path = if let Some(s) = db {
            Path::new(if s.is_empty() { "." } else { s })
        } else {
            default = cwd()?.join(".mir/memory.db");
            &default
        };
        let c = connect(path)?;
        if !c.vec_available {
            stderr =
                format!("sqlite-vec unavailable, FTS5-only mode: {}\n", c.vec_reason).into_bytes();
        }
        let mut stdout = String::new();
        if action == "up" {
            let applied = store::apply_migrations(&c.conn)?;
            stdout = if applied.is_empty() {
                "already up to date\n".into()
            } else {
                format!("applied {}: {}\n", applied.len(), applied.join(", "))
            };
        }
        let version = store::schema_version(&c.conn)?;
        let version = version
            .as_deref()
            .unwrap_or(if action == "up" { "None" } else { "(none)" });
        stdout.push_str(&format!("schema_version: {version}\n"));
        if action == "up" {
            stdout.push_str(&format!(
                "sqlite-vec: {}\n",
                if c.vec_available { "ok" } else { "unavailable" }
            ));
        }
        Ok(stdout)
    })();
    match result {
        Ok(stdout) => (0, stdout.into_bytes(), stderr),
        Err(e) => {
            // Python exposes SQLite's message without rusqlite's SQL/offset annotation.
            let e = match e {
                store::Error::Sql(rusqlite::Error::SqlInputError { error, msg, .. }) => {
                    store::Error::Sql(rusqlite::Error::SqliteFailure(error, Some(msg)))
                }
                other => other,
            };
            failure(e);
            (1, vec![], stderr)
        }
    }
}
