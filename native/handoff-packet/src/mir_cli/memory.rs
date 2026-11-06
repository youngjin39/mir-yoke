//! Query branch of cli/memory.py. Explicit DB and UTF-8 argv; no discovery.
use crate::mir_core::memory::{distill, store};
use std::{fmt, path::Path};

pub type Output = (i32, Vec<u8>, Vec<u8>);
#[derive(Debug)]
pub struct Error(Box<dyn std::error::Error>);
impl Error {
    pub fn python_class(&self) -> &'static str {
        let sql = self.0.downcast_ref::<rusqlite::Error>().or_else(|| {
            match self.0.downcast_ref::<distill::SearchError>() {
                Some(distill::SearchError::Sql(e)) => Some(e),
                Some(distill::SearchError::Sanitize(_)) | None => None,
            }
        });
        if sql.is_some() {
            return "OperationalError";
        }
        if let Some(store::Error::Sql(rusqlite::Error::SqliteFailure(e, _))) =
            self.0.downcast_ref::<store::Error>()
            && e.code == rusqlite::ErrorCode::NotADatabase
        {
            return "DatabaseError";
        }
        self.0
            .downcast_ref::<store::Error>()
            .map_or("RuntimeError", store::Error::python_class)
    }
}
impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        self.0.fmt(f)
    }
}
impl std::error::Error for Error {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        Some(self.0.as_ref())
    }
}
const WARNING: &str = "sqlite-vec unavailable, FTS5-only mode: sqlite-vec package not installed: import of sqlite_vec halted; None in sys.modules\n";
const USAGE: &str = "usage: mir memory [-h]\n                  {insert,query,ingest-md,render,reconcile-missing,doctor,gc}\n                  ...\n";

const QUERY_USAGE: &str =
    "usage: mir memory query [-h] [--limit LIMIT] [--history] [--db DB] keyword\n";
enum Action {
    Help,
    Limit,
    History,
    Db,
}
struct OptionSpec {
    action: Action,
    name: &'static str,
    metavar: Option<&'static str>,
    help: &'static str,
}
const OPTIONS: &[OptionSpec] = &[
    OptionSpec {
        action: Action::Help,
        name: "--help",
        metavar: None,
        help: "show this help message and exit",
    },
    OptionSpec {
        action: Action::Limit,
        name: "--limit",
        metavar: Some("LIMIT"),
        help: "",
    },
    OptionSpec {
        action: Action::History,
        name: "--history",
        metavar: None,
        help: "include expired and superseded facts",
    },
    OptionSpec {
        action: Action::Db,
        name: "--db",
        metavar: Some("DB"),
        help: "",
    },
];
fn diagnostic(message: &str, parent: bool) -> Output {
    let (usage, prog) = if parent {
        (USAGE, "mir memory")
    } else {
        (QUERY_USAGE, "mir memory query")
    };
    (
        2,
        vec![],
        format!("{usage}{prog}: error: {message}\n").into_bytes(),
    )
}
fn help() -> Output {
    let mut text = format!("{QUERY_USAGE}\npositional arguments:\n  keyword\n\noptions:\n");
    for option in OPTIONS {
        let label = match option.metavar {
            Some(value) => format!("{} {value}", option.name),
            None if option.name == "--help" => "-h, --help".to_owned(),
            None => option.name.to_owned(),
        };
        if option.help.is_empty() {
            text.push_str(&format!("  {label}\n"));
        } else {
            text.push_str(&format!("  {label:15}{}\n", option.help));
        }
    }
    (0, text.into_bytes(), vec![])
}
// argparse permits negative decimal numbers as values despite the leading '-'.
fn option_like(token: &str) -> bool {
    let negative_number = token.strip_prefix('-').is_some_and(|n| {
        !n.is_empty()
            && (n.bytes().all(|b| b.is_ascii_digit())
                || n.split_once('.').is_some_and(|(a, b)| {
                    !b.is_empty()
                        && a.bytes().all(|c| c.is_ascii_digit())
                        && b.bytes().all(|c| c.is_ascii_digit())
                }))
    });
    token.len() > 1 && token.starts_with('-') && !negative_number
}
struct Query<'a> {
    keyword: &'a str,
    db: Option<&'a str>,
    limit: i64,
    history: bool,
}
fn parse<'a>(argv: &[&'a str]) -> Result<Query<'a>, Output> {
    let (mut keyword, mut db, mut limit, mut history) = (None, None, 10, false);
    let mut unknown = Vec::new();
    let mut options = true;
    let mut i = usize::from(argv.first() == Some(&"query"));
    while let Some(&token) = argv.get(i) {
        i += 1;
        if options && token == "--" {
            options = false;
            continue;
        }
        if options && option_like(token) {
            let (name, explicit) = token
                .split_once('=')
                .map_or((token, None), |(n, v)| (n, Some(v)));
            let name = if name == "-h" { "--help" } else { name };
            let exact = OPTIONS.iter().find(|o| o.name == name);
            let matches: Vec<_> = OPTIONS
                .iter()
                .filter(|o| name.starts_with("--") && o.name.starts_with(name))
                .collect();
            let option = match (exact, matches.as_slice()) {
                (Some(option), _) => option,
                (None, [option]) => *option,
                (None, []) => {
                    unknown.push(token);
                    continue;
                }
                (None, _) => {
                    return Err(diagnostic(
                        &format!(
                            "ambiguous option: {name} could match {}",
                            matches
                                .iter()
                                .map(|o| o.name)
                                .collect::<Vec<_>>()
                                .join(", ")
                        ),
                        false,
                    ));
                }
            };
            let value = if option.metavar.is_some() {
                match explicit {
                    Some(value) => Some(value),
                    None => {
                        let Some(&value) = argv.get(i).filter(|v| !option_like(v)) else {
                            return Err(diagnostic(
                                &format!("argument {}: expected one argument", option.name),
                                false,
                            ));
                        };
                        i += 1;
                        Some(value)
                    }
                }
            } else {
                if let Some(value) = explicit {
                    return Err(diagnostic(
                        &format!(
                            "argument {}: ignored explicit argument {}",
                            option.name,
                            crate::executor_execute::repr(value)
                        ),
                        false,
                    ));
                }
                None
            };
            match option.action {
                Action::Help => return Err(help()),
                Action::History => history = true,
                Action::Db => db = value,
                Action::Limit => {
                    let value = value.unwrap_or_default();
                    limit = value.parse().map_err(|_| {
                        diagnostic(
                            &format!(
                                "argument --limit: invalid int value: {}",
                                crate::executor_execute::repr(value)
                            ),
                            false,
                        )
                    })?;
                }
            }
        } else if keyword.is_none() {
            keyword = Some(token);
        } else {
            unknown.push(token);
        }
    }
    let keyword = keyword
        .ok_or_else(|| diagnostic("the following arguments are required: keyword", false))?;
    if !unknown.is_empty() {
        return Err(diagnostic(
            &format!("unrecognized arguments: {}", unknown.join(" ")),
            true,
        ));
    }
    Ok(Query {
        keyword,
        db,
        limit,
        history,
    })
}

/// Mirrors memory.main(["query", ...]) with a required caller-supplied DB fallback.
/// Parsing (including help/errors) precedes DB access; no discovery or live caller.
/// Optional vector import is unavailable, matching the frozen reference context.
pub fn main(argv: &[&str], explicit_db: &Path) -> Result<Output, Error> {
    let Query {
        keyword,
        db,
        limit,
        history,
    } = match parse(argv) {
        Ok(query) => query,
        Err(output) => return Ok(output),
    };
    let path = db.map_or(explicit_db, Path::new);
    let db = path.display();
    if !path.is_file() {
        return Ok((
            2,
            format!("no memory.db at {db} \u{2014} run `mir migrate up` first\n").into_bytes(),
            vec![],
        ));
    }
    let run = || -> Result<Output, Box<dyn std::error::Error>> {
        let conn = store::connect(path, None)?;
        let rows = distill::fts_search(&conn.conn, keyword, limit, history)?;
        let mut out = String::new();
        if rows.is_empty() {
            out = format!(
                "no matches for {}\n",
                crate::executor_execute::repr(keyword)
            );
        }
        for (fid, predicate, body) in rows {
            let status = if history {
                let status: Option<String> =
                    conn.conn
                        .query_row("SELECT status FROM facts WHERE id = ?", [fid], |r| r.get(0))?;
                format!(
                    "[{}]  ",
                    status
                        .filter(|s| !s.is_empty())
                        .as_deref()
                        .unwrap_or("unknown")
                )
            } else {
                String::new()
            };
            out.push_str(&format!("  #{fid}  {status}{predicate}  {body}\n"));
        }
        Ok((0, out.into_bytes(), WARNING.as_bytes().to_vec()))
    };
    run().map_err(Error)
}
