//! Library branches of cli/memory.py. Explicit DB and UTF-8 argv; no discovery.
use crate::mir_core::memory::{distill, store};
use std::{fmt, path::Path};

const START: &str = "<!-- mir:generated:start -->";
const END: &str = "<!-- mir:generated:end -->";
const RENDER_USAGE: &str = concat!(
    "usage: mir memory render [-h] [--target {memory-map,lessons,all}]\n",
    "                         [--output-path OUTPUT_PATH] [--apply] [--db DB]\n"
);
#[derive(Debug)]
struct DirectoryError(std::path::PathBuf);
impl fmt::Display for DirectoryError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            f,
            "[Errno 21] Is a directory: {}",
            crate::executor_execute::repr(self.0.to_str().unwrap_or_default())
        )
    }
}
impl std::error::Error for DirectoryError {}

pub fn render_memory_map_section(conn: &rusqlite::Connection) -> rusqlite::Result<String> {
    let rows = distill::recall_ingested_index(conn)?;
    let mut lines = vec![
        "## Keyword \u{2192} File Index (DB projection)".to_owned(),
        String::new(),
        "| Keyword | File | Title |".to_owned(),
        "|---|---|---|".to_owned(),
    ];
    if rows.is_empty() {
        lines.push("| (no ingested documents) | \u{2014} | \u{2014} |".to_owned());
    }
    for row in rows {
        let kws = if row.keywords.is_empty() {
            "\u{2014}".to_owned()
        } else {
            row.keywords.join(", ")
        };
        let path = if row.path.is_empty() {
            &row.slug
        } else {
            &row.path
        };
        let title = if row.title.is_empty() {
            &row.slug
        } else {
            &row.title
        };
        lines.push(format!("| {kws} | {path} | {title} |"));
    }
    Ok(lines.join("\n"))
}
pub fn render_lessons_section(conn: &rusqlite::Connection) -> rusqlite::Result<String> {
    let lessons = distill::recall_lessons(conn)?;
    let mut lines = vec![
        "## Active Lessons (DB projection)".to_owned(),
        String::new(),
    ];
    if lessons.is_empty() {
        lines.push("- None recorded yet.".to_owned());
    }
    for lesson in lessons {
        let text = lesson
            .text
            .trim_matches(crate::executor_brief_authority::python_space);
        lines.push(format!("- **{}**: {text}", lesson.slug));
    }
    Ok(lines.join("\n"))
}
pub(crate) fn inject_markers(existing: &str, generated: &str) -> String {
    let block = format!("{START}\n{generated}\n{END}");
    if let (Some(start), Some(end)) = (existing.find(START), existing.find(END)) {
        return format!(
            "{}{block}{}",
            &existing[..start],
            &existing[end + END.len()..]
        );
    }
    let mut sep = if !existing.is_empty() && !existing.ends_with("\n\n") {
        "\n\n".to_owned()
    } else {
        "\n".to_owned()
    };
    if !existing.ends_with('\n') {
        sep.insert(0, '\n');
    }
    format!("{existing}{sep}{block}\n")
}
/// Direct render branch, with no discovery and no process output side effects.
pub fn render(
    conn: &rusqlite::Connection,
    target: &str,
    apply: bool,
    output: Option<&Path>,
) -> Result<Output, Error> {
    let run = || -> Result<Output, Box<dyn std::error::Error>> {
        let mut sections = Vec::new();
        if matches!(target, "memory-map" | "all") {
            sections.push(render_memory_map_section(conn)?);
        }
        if matches!(target, "lessons" | "all") {
            sections.push(render_lessons_section(conn)?);
        }
        let body = sections.join("\n\n");
        let Some(path) = output.filter(|_| apply) else {
            return Ok((0, format!("{START}\n{body}\n{END}\n").into_bytes(), vec![]));
        };
        let existing = if path.is_file() {
            // Path.read_text uses universal newlines.
            std::fs::read_to_string(path)?
                .replace("\r\n", "\n")
                .replace('\r', "\n")
        } else {
            if let Some(parent) = path.parent().filter(|p| !p.as_os_str().is_empty()) {
                std::fs::create_dir_all(parent)?;
            }
            String::new()
        };
        let updated = inject_markers(&existing, &body);
        if path.is_dir() {
            return Err(Box::new(DirectoryError(path.to_owned())));
        }
        #[cfg(windows)]
        let updated = updated.replace('\n', "\r\n");
        // Path.write_text writes in place: it keeps the mode bits and follows a symlink.
        std::fs::write(path, updated)?;
        Ok((
            0,
            format!("render applied \u{2192} {}\n", path.display()).into_bytes(),
            vec![],
        ))
    };
    run().map_err(Error)
}
#[derive(Clone, Copy)]
enum RenderAction {
    Help,
    Target,
    Output,
    Apply,
    Db,
}
const RENDER_OPTIONS: &[OptionSpec<RenderAction>] = &[
    OptionSpec {
        action: RenderAction::Help,
        name: "--help",
        metavar: None,
        help: "show this help message and exit",
    },
    OptionSpec {
        action: RenderAction::Target,
        name: "--target",
        metavar: Some("{memory-map,lessons,all}"),
        help: "which projection to render (default: all)",
    },
    OptionSpec {
        action: RenderAction::Output,
        name: "--output-path",
        metavar: Some("OUTPUT_PATH"),
        help: "target file path for --apply (default: none = stdout\n                        only)",
    },
    OptionSpec {
        action: RenderAction::Apply,
        name: "--apply",
        metavar: None,
        help: concat!(
            "write projection into the output file (default: dry-\n",
            "                        run stdout)"
        ),
    },
    OptionSpec {
        action: RenderAction::Db,
        name: "--db",
        metavar: Some("DB"),
        help: "",
    },
];
fn render_main(argv: &[&str], explicit_db: &Path, root: &Path) -> Result<Output, Error> {
    let fail = |message: String| {
        (
            2,
            vec![],
            format!("{RENDER_USAGE}mir memory render: error: {message}\n").into_bytes(),
        )
    };
    let (mut target, mut output, mut db, mut apply) = ("all", None, explicit_db, false);
    let mut unknown = Vec::new();
    let mut i = 1;
    let mut options = true;
    while let Some(&token) = argv.get(i) {
        i += 1;
        if options && token == "--" {
            options = false;
            continue;
        }
        if !options {
            unknown.push(token);
            continue;
        }
        let (name, explicit) = token
            .split_once('=')
            .map_or((token, None), |(n, v)| (n, Some(v)));
        let name = if name == "-h" { "--help" } else { name };
        let exact = RENDER_OPTIONS.iter().find(|o| o.name == name);
        let matches: Vec<_> = RENDER_OPTIONS
            .iter()
            .filter(|o| name.starts_with("--") && o.name.starts_with(name))
            .collect();
        let option = match (exact, matches.as_slice()) {
            (Some(o), _) => o,
            (None, [o]) => *o,
            (None, []) => {
                unknown.push(token);
                continue;
            }
            (None, _) => {
                return Ok(fail(format!(
                    "ambiguous option: {name} could match {}",
                    matches
                        .iter()
                        .map(|o| o.name)
                        .collect::<Vec<_>>()
                        .join(", ")
                )));
            }
        };
        let value = if option.metavar.is_some() {
            match explicit {
                Some(v) => v,
                None => {
                    let Some(&v) = argv.get(i).filter(|v| !option_like(v)) else {
                        return Ok(fail(format!("argument {name}: expected one argument")));
                    };
                    i += 1;
                    v
                }
            }
        } else {
            if let Some(v) = explicit {
                return Ok(fail(format!(
                    "argument {name}: ignored explicit argument {}",
                    crate::executor_execute::repr(v)
                )));
            }
            ""
        };
        match option.action {
            RenderAction::Help => {
                let mut text = format!("{RENDER_USAGE}\noptions:\n");
                for o in RENDER_OPTIONS {
                    let label = if let Some(m) = o.metavar {
                        format!("{} {m}", o.name)
                    } else if o.name == "--help" {
                        "-h, --help".to_owned()
                    } else {
                        o.name.to_owned()
                    };
                    if label.len() > 20 {
                        text.push_str(&format!("  {label}\n                        {}\n", o.help));
                    } else if o.help.is_empty() {
                        text.push_str(&format!("  {label}\n"));
                    } else {
                        text.push_str(&format!("  {label:22}{}\n", o.help));
                    }
                }
                return Ok((0, text.into_bytes(), vec![]));
            }
            RenderAction::Target => {
                if !matches!(value, "all" | "memory-map" | "lessons") {
                    return Ok(fail(format!(
                        "argument --target: invalid choice: {} \
                        (choose from memory-map, lessons, all)",
                        crate::executor_execute::repr(value)
                    )));
                }
                target = value;
            }
            RenderAction::Output => output = Some(Path::new(value)),
            RenderAction::Apply => apply = true,
            RenderAction::Db => db = Path::new(value),
        }
    }
    if !unknown.is_empty() {
        return Ok(diagnostic(
            &format!("unrecognized arguments: {}", unknown.join(" ")),
            true,
        ));
    }
    // The message keeps the spelling given; the file opens relative to the working directory.
    let shown = db;
    let db = root.join(db);
    if !db.is_file() {
        return Ok((
            2,
            format!(
                "no memory.db at {} \u{2014} run `mir migrate up` first\n",
                shown.display()
            )
            .into_bytes(),
            vec![],
        ));
    }
    let conn = store::connect(&db, None).map_err(|e| Error(Box::new(e)))?;
    let resolved_output = output.map(|p| root.join(p));
    let mut result = render(&conn.conn, target, apply, resolved_output.as_deref())?;
    if let Some(label) = output.filter(|_| apply) {
        result.1 = format!("render applied \u{2192} {}\n", label.display()).into_bytes();
    }
    Ok(result)
}

pub type Output = (i32, Vec<u8>, Vec<u8>);
#[derive(Debug)]
pub struct Error(Box<dyn std::error::Error>);
impl Error {
    /// Captured diagnostics emitted before a branch raised a reference exception.
    pub fn stderr(&self) -> &str {
        if self.0.downcast_ref::<GcFailure>().is_some() {
            GC_DOCTOR_WARNING
        } else {
            ""
        }
    }
    pub fn python_class(&self) -> &'static str {
        if let Some(e) = self.0.downcast_ref::<GcFailure>() {
            return e.0.python_class();
        }
        if self.0.downcast_ref::<DirectoryError>().is_some() {
            return "IsADirectoryError";
        }
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
struct OptionSpec<A = Action> {
    action: A,
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
    if matches!(
        argv.first(),
        Some(&"insert" | &"ingest-md" | &"render" | &"gc" | &"doctor" | &"reconcile-missing")
    ) {
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
    if matches!(argv.first(), Some(&"gc" | &"doctor" | &"reconcile-missing")) {
        return check_main(argv, explicit_db, root, clock);
    }
    if argv.first() == Some(&"render") {
        return render_main(argv, explicit_db, root);
    }
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
            (choose from ephemeral, persistent)",
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

// The vector loader is deliberately unavailable in this isolated library slice.
use crate::executor_policy_query::ascii_json_text;
const GC_DOCTOR_WARNING: &str = "sqlite-vec unavailable, FTS5-only mode: fixture unavailable\n";
#[derive(Debug)]
struct GcFailure(store::Error);
impl fmt::Display for GcFailure {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        self.0.fmt(f)
    }
}
impl std::error::Error for GcFailure {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        Some(&self.0)
    }
}
#[derive(Clone, Copy)]
enum CheckAction {
    DryRun,
    Help,
    Apply,
    Json,
    Db,
    Root,
}
const GC_OPTIONS: &[OptionSpec<CheckAction>] = &[
    OptionSpec {
        action: CheckAction::Help,
        name: "--help",
        metavar: None,
        help: "show this help message and exit",
    },
    OptionSpec {
        action: CheckAction::Apply,
        name: "--apply",
        metavar: None,
        help: "apply expiry updates (default: dry-run)",
    },
    OptionSpec {
        action: CheckAction::Json,
        name: "--json",
        metavar: None,
        help: "emit machine-readable counts",
    },
    OptionSpec {
        action: CheckAction::Db,
        name: "--db",
        metavar: Some("DB"),
        help: "",
    },
];
const DOCTOR_OPTIONS: &[OptionSpec<CheckAction>] = &[
    OptionSpec {
        action: CheckAction::Help,
        name: "--help",
        metavar: None,
        help: "show this help message and exit",
    },
    OptionSpec {
        action: CheckAction::Root,
        name: "--project-root",
        metavar: Some("PROJECT_ROOT"),
        help: "repository root containing harness_a.toml (default:\n                        cwd)",
    },
    OptionSpec {
        action: CheckAction::Json,
        name: "--json",
        metavar: None,
        help: "emit machine-readable evidence",
    },
];
const RECONCILE_OPTIONS: &[OptionSpec<CheckAction>] = &[
    OptionSpec {
        action: CheckAction::Help,
        name: "--help",
        metavar: None,
        help: "show this help message and exit",
    },
    OptionSpec {
        action: CheckAction::Root,
        name: "--project-root",
        metavar: Some("PROJECT_ROOT"),
        help: "project root for relative path resolution (default:\n                        cwd)",
    },
    OptionSpec {
        action: CheckAction::DryRun,
        name: "--dry-run",
        metavar: None,
        help: "report count without writing any rows",
    },
    OptionSpec {
        action: CheckAction::Db,
        name: "--db",
        metavar: Some("DB"),
        help: "",
    },
];
fn check_main(
    argv: &[&str],
    db: &Path,
    root: &Path,
    clock: impl Fn() -> std::time::SystemTime,
) -> Result<Output, Error> {
    let gc = argv.first() == Some(&"gc");
    let reconcile = argv.first() == Some(&"reconcile-missing");
    let mut dry_run = false;
    let (specs, usage, action) = if gc {
        (
            GC_OPTIONS,
            "usage: mir memory gc [-h] [--apply] [--json] [--db DB]\n",
            "gc",
        )
    } else if reconcile {
        (
            RECONCILE_OPTIONS,
            concat!(
                "usage: mir memory reconcile-missing [-h] [--project-root PROJECT_ROOT]\n",
                "                                    [--dry-run] [--db DB]\n"
            ),
            "reconcile-missing",
        )
    } else {
        (
            DOCTOR_OPTIONS,
            "usage: mir memory doctor [-h] [--project-root PROJECT_ROOT] [--json]\n",
            "doctor",
        )
    };
    let fail = |s| {
        (
            2,
            vec![],
            format!("{usage}mir memory {action}: error: {s}\n").into_bytes(),
        )
    };
    let cwd = root;
    let (mut db, mut project, mut apply, mut as_json) = (db, None, false, false);
    let (mut i, mut options) = (1, true);
    let mut unknown = Vec::new();
    while let Some(&token) = argv.get(i) {
        i += 1;
        if options && token == "--" {
            options = false;
            continue;
        }
        let (name, explicit) = token
            .split_once('=')
            .map_or((token, None), |(k, v)| (k, Some(v)));
        let name = if name == "-h" { "--help" } else { name };
        let exact = specs.iter().find(|s| options && s.name == name);
        let matches: Vec<_> = specs
            .iter()
            .filter(|s| options && name.starts_with("--") && s.name.starts_with(name))
            .collect();
        let spec = match (exact, matches.as_slice()) {
            (Some(s), _) => s,
            (None, [s]) => *s,
            (None, []) => {
                unknown.push(token);
                continue;
            }
            _ => {
                return Ok(fail(format!(
                    "ambiguous option: {name} could match {}",
                    matches
                        .iter()
                        .map(|s| s.name)
                        .collect::<Vec<_>>()
                        .join(", ")
                )));
            }
        };
        let value = if spec.metavar.is_some() {
            match explicit {
                Some(v) => v,
                None => {
                    let Some(&v) = argv.get(i).filter(|v| !option_like(v)) else {
                        return Ok(fail(format!("argument {name}: expected one argument")));
                    };
                    i += 1;
                    v
                }
            }
        } else {
            if let Some(v) = explicit {
                let label = if name == "--help" { "-h/--help" } else { name };
                return Ok(fail(format!(
                    "argument {label}: ignored explicit argument {}",
                    crate::executor_execute::repr(v)
                )));
            }
            ""
        };
        match spec.action {
            CheckAction::Help => {
                let mut text = format!("{usage}\noptions:\n");
                for s in specs {
                    let label = match s.metavar {
                        Some(v) => format!("{} {v}", s.name),
                        None if s.name == "--help" => "-h, --help".into(),
                        None => s.name.into(),
                    };
                    if s.help.is_empty() {
                        text.push_str(&format!("  {label}\n"));
                    } else if gc {
                        text.push_str(&format!("  {label:12}{}\n", s.help));
                    } else if label.len() > 22 {
                        text.push_str(&format!("  {label}\n                        {}\n", s.help));
                    } else {
                        text.push_str(&format!("  {label:22}{}\n", s.help));
                    }
                }
                return Ok((0, text.into_bytes(), vec![]));
            }
            CheckAction::DryRun => dry_run = true,
            CheckAction::Apply => apply = true,
            CheckAction::Json => as_json = true,
            CheckAction::Db => db = Path::new(value),
            CheckAction::Root => project = Some(value),
        }
    }
    if !unknown.is_empty() {
        return Ok(diagnostic(
            &format!("unrecognized arguments: {}", unknown.join(" ")),
            true,
        ));
    }
    if !gc && !reconcile {
        // Python Path(...).resolve(strict=False) against the working directory.
        let root =
            std::path::absolute(cwd.join(project.unwrap_or(""))).map_err(|e| Error(Box::new(e)))?;
        let root = crate::supply::resolve(&root)
            .map_err(|e| Error(Box::new(std::io::Error::other(format!("{e:?}")))))?;
        return doctor_main(&root, as_json, clock);
    }
    // The message keeps the spelling given; the file opens relative to the working directory.
    let shown = db;
    let db = &cwd.join(db);
    if !db.is_file() {
        return Ok((
            2,
            format!(
                "no memory.db at {} \u{2014} run `mir migrate up` first\n",
                shown.display()
            )
            .into_bytes(),
            vec![],
        ));
    }
    let conn = store::connect(db, None).map_err(|e| Error(Box::new(e)))?;
    if reconcile {
        let count = distill::reconcile_missing_source(
            &conn.conn,
            project.map(Path::new),
            cwd,
            dry_run,
            clock,
        )
        .map_err(|e| Error(Box::new(e)))?;
        let prefix = if dry_run {
            "dry_run: would_expire"
        } else {
            "expired"
        };
        // The frozen CLI disables the optional vector loader's logger.
        return Ok((0, format!("{prefix}={count}\n").into_bytes(), vec![]));
    }
    let result = crate::mir_core::audit_log::AuditLog::with_clock(&conn.conn, clock)
        .gc_scan(!apply)
        .map_err(|e| Error(Box::new(GcFailure(e))))?;
    let text = if as_json {
        let mut payload = result.clone();
        payload["applied"] = serde_json::json!(apply);
        format!("{}\n", ascii_json_text(&payload.to_string()))
    } else {
        format!(
            "{}{} kept_active={}\n",
            if apply {
                "expired="
            } else {
                "dry_run: would_expire="
            },
            result["expired"],
            result["kept_active"]
        )
    };
    Ok((0, text.into_bytes(), GC_DOCTOR_WARNING.as_bytes().to_vec()))
}
fn doctor_main(
    root: &Path,
    as_json: bool,
    clock: impl Fn() -> std::time::SystemTime,
) -> Result<Output, Error> {
    use crate::mir_core::config::loader;
    use serde_json::json;
    let mut report = json!({"status":"not_ready","errors":[],"memory":{
        "required":true,"backend":"unknown","db_path":".mir/memory.db",
        "integrity":"not_checked","schema_version":null,
        "latest_schema_version":store::latest_schema_version(),"fts5":"not_checked",
        "round_trip":"not_checked","archives_configured":0,"archives_registered":0,
        "archives_synced":0},"vector":{"mode":"off","sqlite_vec":"not_checked",
        "embedding":"disabled","status":"off"}});
    let mut errors = Vec::<String>::new();
    let mut code = 1;
    let mut stderr = String::new();
    let mut run = || -> Result<(), Box<dyn std::error::Error>> {
        if !root.is_dir() {
            code = 2;
            errors.push(format!(
                "project root is not a directory: {}",
                root.display()
            ));
            return Ok(());
        }
        if !root.join("harness_a.toml").is_file() {
            code = 2;
            errors.push("active harness_a.toml is missing".into());
            return Ok(());
        }
        // Home is injected as root; no host-specific discovery in this port slice.
        let cfg = match loader::load_config(Some(root), root, root) {
            Ok(c) => c,
            Err(e) => {
                code = 2;
                errors.push(e.to_string());
                return Ok(());
            }
        };
        let config = cfg.to_dict();
        let memory = &config["memory"];
        let archives = memory["external_archives"]
            .as_array()
            .ok_or_else(|| std::io::Error::other("invalid archive configuration"))?;
        report["memory"]["required"] = memory["required"].clone();
        report["memory"]["backend"] = memory["backend"].clone();
        report["memory"]["archives_configured"] = json!(archives.len());
        report["vector"]["mode"] = memory["vector_mode"].clone();
        if memory["enabled"] != true || memory["required"] != true {
            errors.push("portable baseline requires memory enabled=true and required=true".into());
        }
        if archives.is_empty() {
            errors.push("at least one external archive must be configured".into());
        }
        for archive in archives {
            let path = loader::resolve_path(root, archive["root"].as_str().unwrap_or(""), root)?;
            if !path.is_dir() {
                errors.push(format!(
                    "configured archive root is missing: {} ({})",
                    crate::executor_execute::repr(archive["slug"].as_str().unwrap_or("")),
                    path.display()
                ));
            }
        }
        let db = loader::resolve_memory_db(root, &cfg, root)?;
        report["memory"]["db_path"] = json!(
            db.strip_prefix(root)
                .unwrap_or(&db)
                .to_str()
                .ok_or_else(|| std::io::Error::other("non-UTF-8 DB path"))?
                .replace('\\', "/")
        );
        if !db.is_file() {
            errors.push(format!("memory database is missing: {}", db.display()));
            return Ok(());
        }
        let connection = store::connect(&db, None)?;
        stderr.push_str(GC_DOCTOR_WARNING);
        let conn = &connection.conn;
        report["vector"]["sqlite_vec"] = json!("unavailable");
        let integrity: Vec<String> = conn
            .prepare("PRAGMA integrity_check")?
            .query_map([], |r| r.get(0))?
            .collect::<rusqlite::Result<_>>()?;
        report["memory"]["integrity"] = json!(integrity.join(", "));
        if integrity != ["ok"] {
            errors.push(format!(
                "SQLite integrity_check failed: {}",
                integrity.join(", ")
            ));
        }
        let version = store::schema_version(conn)?;
        let latest = store::latest_schema_version();
        report["memory"]["schema_version"] = json!(version);
        if version != latest {
            let repr = |v: &Option<String>| {
                v.as_deref()
                    .map_or("None".into(), crate::executor_execute::repr)
            };
            errors.push(format!(
                "schema version {} is not latest {}",
                repr(&version),
                repr(&latest)
            ));
        }
        let objects: Vec<String> = conn
            .prepare("SELECT name FROM sqlite_master WHERE type IN ('table','view')")?
            .query_map([], |r| r.get(0))?
            .collect::<rusqlite::Result<_>>()?;
        let missing: Vec<_> = [
            "entities",
            "external_archives",
            "external_chunks",
            "external_chunks_fts",
            "external_documents",
            "external_store_meta",
            "facts",
            "facts_fts",
            "schema_migrations",
        ]
        .into_iter()
        .filter(|s| !objects.iter().any(|o| o == s))
        .collect();
        if missing.is_empty() {
            report["memory"]["fts5"] = json!("ok");
            let probe = || -> Result<(), Box<dyn std::error::Error>> {
                conn.execute_batch("BEGIN")?;
                let triple = distill::Triple::new(
                    "mir-memory-doctor",
                    "doctor_probe",
                    "mirdoctor00000000000000000000000000000000",
                );
                distill::insert_triple(conn, &triple, "ephemeral", &clock)?;
                if distill::fts_search(conn, &triple.object_literal, 1, false)?.is_empty() {
                    return Err(
                        std::io::Error::other("inserted fact was not returned by FTS5").into(),
                    );
                }
                Ok(())
            };
            let result = probe();
            conn.execute_batch("ROLLBACK")?;
            match result {
                Ok(()) => report["memory"]["round_trip"] = json!("ok"),
                Err(e) => {
                    report["memory"]["round_trip"] = json!("failed");
                    errors.push(format!("rollback-only FTS5 probe failed: {e}"));
                }
            }
        } else {
            errors.push(format!(
                "required memory tables are missing: {}",
                missing.join(", ")
            ));
        }
        let registered: Vec<(i64, String, String, Option<String>)> = conn
            .prepare("SELECT id,slug,root_path,last_scanned_at FROM external_archives")?
            .query_map([], |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?, r.get(3)?)))?
            .collect::<rusqlite::Result<_>>()?;
        report["memory"]["archives_registered"] = json!(registered.len());
        if registered.is_empty() {
            errors.push("no external archives are registered".into());
        }
        let mut synced = 0;
        for archive in archives {
            let slug = archive["slug"].as_str().unwrap_or("");
            let quoted = crate::executor_execute::repr(slug);
            let Some(row) = registered.iter().find(|r| r.1 == slug) else {
                errors.push(format!("configured archive is not registered: {quoted}"));
                continue;
            };
            let expected =
                loader::resolve_path(root, archive["root"].as_str().unwrap_or(""), root)?;
            let actual = loader::resolve_path(root, &row.2, root)?;
            if actual != expected {
                errors.push(format!(
                    "archive root drift for {quoted}: {} != {}",
                    actual.display(),
                    expected.display()
                ));
            }
            let current: bool = conn.query_row(
                "SELECT EXISTS(SELECT 1 FROM external_store_meta
                WHERE key=? AND value=?)",
                rusqlite::params![
                    format!("schema_metadata_version:archive:{}", row.0),
                    crate::mir_core::memory::external_store::CURRENT_METADATA_VERSION
                ],
                |r| r.get(0),
            )?;
            if row.3.is_none() || !current {
                errors.push(format!(
                    "archive has no successful current sync evidence: {quoted}"
                ));
            } else {
                synced += 1;
            }
        }
        report["memory"]["archives_synced"] = json!(synced);
        let documents: i64 =
            conn.query_row("SELECT COUNT(*) FROM external_documents", [], |r| r.get(0))?;
        let chunks: i64 =
            conn.query_row("SELECT COUNT(*) FROM external_chunks", [], |r| r.get(0))?;
        report["memory"]["documents_indexed"] = json!(documents);
        report["memory"]["chunks_indexed"] = json!(chunks);
        report["memory"]["archive_fts_probe"] = json!("not_checked");
        if documents < 1 || chunks < 1 {
            errors.push("archive sync produced no searchable documents/chunks".into());
        } else {
            let probe = || -> Result<(), Box<dyn std::error::Error>> {
                let mut samples = conn.prepare(
                    "SELECT a.root_path,d.relative_path,
                    c.byte_start,c.byte_end FROM external_chunks c
                    JOIN external_documents d ON d.id=c.document_id
                    JOIN external_archives a ON a.id=d.archive_id ORDER BY c.id",
                )?;
                let mut rows = samples.query([])?;
                let token_pattern = regex::Regex::new(r"[A-Za-z0-9_\u00C0-\uFFFF]+")?;
                let mut token = None;
                while let Some(row) = rows.next()? {
                    let path: String = row.get(0)?;
                    let relative: String = row.get(1)?;
                    let start = usize::try_from(row.get::<_, i64>(2)?)?;
                    let end = usize::try_from(row.get::<_, i64>(3)?)?;
                    let file = Path::new(&path).join(relative);
                    let bytes = std::fs::read(&file).map_err(|e| {
                        std::io::Error::other(
                            crate::executor_brief_profile::python_os_error_message(&e, &file),
                        )
                    })?;
                    let snippet =
                        std::str::from_utf8(&bytes[start.min(bytes.len())..end.min(bytes.len())])?;
                    if let Some(found) = token_pattern
                        .find_iter(snippet)
                        .find(|m| m.as_str().chars().count() >= 6)
                    {
                        token = Some(found.as_str().to_owned());
                        break;
                    }
                }
                let token = token.ok_or_else(|| {
                    std::io::Error::other("indexed archive contains no stable probe token")
                })?;
                let query = distill::sanitize_fts_query(&token)
                    .map_err(|e| std::io::Error::other(format!("{e:?}")))?;
                let found: bool = conn.query_row(
                    "SELECT EXISTS(SELECT c.id
                    FROM external_chunks_fts f JOIN external_chunks c ON c.id=f.rowid
                    WHERE external_chunks_fts MATCH ? LIMIT 1)",
                    [query],
                    |r| r.get(0),
                )?;
                if !found {
                    return Err(std::io::Error::other(
                        "indexed archive token was not returned by FTS5",
                    )
                    .into());
                }
                Ok(())
            };
            match probe() {
                Ok(()) => report["memory"]["archive_fts_probe"] = json!("ok"),
                Err(e) => {
                    report["memory"]["archive_fts_probe"] = json!("failed");
                    errors.push(format!("archive FTS5 probe failed: {e}"));
                }
            }
        }
        if memory["vector_mode"] != "off" {
            report["vector"]["status"] = json!("unavailable");
        }
        Ok(())
    };
    if let Err(e) = run() {
        errors.push(format!("memory doctor operational failure: {e}"));
    }
    if errors.is_empty() {
        code = 0;
        report["status"] = json!("ready");
    }
    report["errors"] = json!(errors);
    let text = if as_json {
        // json.dumps(sort_keys=True) with the default ensure_ascii=True.
        format!("{}\n", ascii_json_text(&report.to_string()))
    } else {
        let mut text = format!(
            "memory doctor: {}\n",
            report["status"].as_str().unwrap_or("")
        );
        for error in &errors {
            text.push_str(&format!("  [not-ready] {error}\n"));
        }
        if errors.is_empty() {
            for (label, value) in [
                ("db", &report["memory"]["db_path"]),
                ("schema", &report["memory"]["schema_version"]),
                ("archives", &report["memory"]["archives_registered"]),
                ("vector", &report["vector"]["status"]),
            ] {
                text.push_str(&format!(
                    "  {label}: {}\n",
                    value
                        .as_str()
                        .map_or_else(|| value.to_string(), str::to_owned)
                ));
            }
        }
        text
    };
    Ok((code, text.into_bytes(), stderr.into_bytes()))
}
