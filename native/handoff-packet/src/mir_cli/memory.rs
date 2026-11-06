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
const WARNING: &str = "sqlite-vec unavailable, FTS5-only mode: sqlite-vec package not installed: \
    import of sqlite_vec halted; None in sys.modules\n";
const USAGE: &str = concat!(
    "usage: mir memory [-h]\n",
    "                  {insert,query,ingest-md,render,reconcile-missing,doctor,gc}\n",
    "                  ...\n"
);

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
    if matches!(argv.first(), Some(&"insert" | &"ingest-md")) {
        return main_with_clock(
            argv,
            explicit_db,
            &std::env::current_dir().map_err(|e| Error(Box::new(e)))?,
            std::time::SystemTime::now,
        );
    }
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

/// Explicit root and clock keep the port isolated from process-global cwd changes.
pub fn main_with_clock(
    argv: &[&str],
    explicit_db: &Path,
    root: &Path,
    clock: impl Fn() -> std::time::SystemTime,
) -> Result<Output, Error> {
    let insert = argv.first() == Some(&"insert");
    let action = if insert { "insert" } else { "ingest-md" };
    let usage = if insert {
        "usage: mir memory insert [-h] --subject SUBJECT --predicate PREDICATE --object\n\
         \x20                        OBJ [--consent {ephemeral,persistent}] [--db DB]\n"
    } else {
        "usage: mir memory ingest-md [-h] [--db DB] [--whitelist WHITELIST] path\n"
    };
    let fail = |message: String| {
        (
            2,
            vec![],
            format!("{usage}mir memory {action}: error: {message}\n").into_bytes(),
        )
    };
    let names: &[&str] = if insert {
        &[
            "--help",
            "--subject",
            "--predicate",
            "--object",
            "--consent",
            "--db",
        ]
    } else {
        &["--help", "--db", "--whitelist"]
    };
    let mut fields = std::collections::BTreeMap::new();
    let mut globs = Vec::new();
    let mut path = None;
    let mut unknown = Vec::new();
    let mut i = 1;
    let mut options = true;
    while let Some(&token) = argv.get(i) {
        i += 1;
        if options && token == "--" {
            options = false;
            continue;
        }
        if options && option_like(token) {
            let (name, explicit) = token
                .split_once('=')
                .map_or((token, None), |(k, v)| (k, Some(v)));
            let name = if name == "-h" { "--help" } else { name };
            let matches: Vec<_> = names
                .iter()
                .filter(|n| **n == name || (name.starts_with("--") && n.starts_with(name)))
                .collect();
            let name = match matches.as_slice() {
                [name] => **name,
                [] => {
                    unknown.push(token);
                    continue;
                }
                _ => {
                    return Ok(fail(format!(
                        "ambiguous option: {name} could match {}",
                        matches.iter().map(|s| **s).collect::<Vec<_>>().join(", ")
                    )));
                }
            };
            if name == "--help" {
                if let Some(value) = explicit {
                    return Ok(fail(format!(
                        "argument -h/--help: ignored explicit argument {}",
                        crate::executor_execute::repr(value)
                    )));
                }
                let text = if insert {
                    "\noptions:\n  -h, --help            show this help message and exit\n\
                     \x20 --subject SUBJECT\n  --predicate PREDICATE\n  --object OBJ\n\
                     \x20 --consent {ephemeral,persistent}\n  --db DB\n"
                } else {
                    "\npositional arguments:\n\
                     \x20 path                  path to a whitelisted markdown file\n\n\
                     options:\n  -h, --help            show this help message and exit\n\
                     \x20 --db DB\n  --whitelist WHITELIST\n\
                     \x20                       override default fnmatch glob (default:\n\
                     \x20                       docs/decisions/adr-*.md)\n"
                };
                return Ok((0, format!("{usage}{text}").into_bytes(), vec![]));
            }
            let value = match explicit {
                Some(value) => value,
                None => {
                    let Some(&value) = argv.get(i).filter(|v| !option_like(v)) else {
                        return Ok(fail(format!("argument {name}: expected one argument")));
                    };
                    i += 1;
                    value
                }
            };
            if name == "--whitelist" {
                globs.push(value);
            } else {
                fields.insert(name, value);
            }
        } else if !insert && path.is_none() {
            path = Some(token);
        } else {
            unknown.push(token);
        }
    }
    let required: Vec<_> = if insert {
        ["--subject", "--predicate", "--object"]
            .into_iter()
            .filter(|k| !fields.contains_key(k))
            .collect()
    } else if path.is_none() {
        vec!["path"]
    } else {
        vec![]
    };
    if !required.is_empty() {
        return Ok(fail(format!(
            "the following arguments are required: {}",
            required.join(", ")
        )));
    }
    if !unknown.is_empty() {
        return Ok(fail(format!(
            "unrecognized arguments: {}",
            unknown.join(" ")
        )));
    }
    let consent = fields.get("--consent").copied().unwrap_or("ephemeral");
    if !matches!(consent, "ephemeral" | "persistent") {
        return Ok(fail(format!(
            "argument --consent: invalid choice: {} \
            (choose from 'ephemeral', 'persistent')",
            crate::executor_execute::repr(consent)
        )));
    }
    let db = fields.get("--db").map_or(explicit_db, Path::new);
    if !db.is_file() {
        return Ok((
            2,
            format!(
                "no memory.db at {} \u{2014} run `mir migrate up` first\n",
                db.display()
            )
            .into_bytes(),
            vec![],
        ));
    }
    let mut run = || -> Result<Output, Box<dyn std::error::Error>> {
        let conn = store::connect(db, None)?;
        if insert {
            let triple = distill::Triple::new(
                fields["--subject"],
                fields["--predicate"],
                fields["--object"],
            );
            let id = distill::insert_triple(&conn.conn, &triple, consent, &clock)?;
            conn.conn.execute_batch("COMMIT")?;
            return Ok((0, format!("fact id={id}\n").into_bytes(), vec![]));
        }
        if globs.is_empty() {
            globs.extend_from_slice(distill::DEFAULT_WHITELIST);
        }
        let source = root.join(path.unwrap_or_default());
        let result = match distill::ingest_markdown_file(&source, &conn.conn, root, &globs, &clock)
        {
            Ok(result) => result,
            Err(distill::WriteError::Relation(e)) => {
                return Ok((2, vec![], format!("error: {e}\n").into_bytes()));
            }
            Err(e) => return Err(Box::new(e)),
        };
        let hash = &result.file_hash[..result.file_hash.len().min(12)];
        let text = if result.no_op {
            format!(
                "no_op[{}]: hash={}\u{2026}\n",
                result.no_op_reason,
                if hash.is_empty() { "n/a" } else { hash }
            )
        } else {
            format!(
                "ingested: facts+={} superseded={} links+={} hash={hash}\u{2026}\n",
                result.facts_inserted, result.facts_superseded, result.fact_links_added
            )
        };
        Ok((0, text.into_bytes(), vec![]))
    };
    run().map_err(Error)
}
