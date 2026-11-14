//! Console admission for context sync; embedding transport closes in Y-E6.
use crate::{
    executor_execute::repr,
    mir_core::{
        config::loader,
        memory::{external_store, store},
    },
};
use std::path::{Path, PathBuf};
const TOP: &str = "usage: mir context [-h] {pull,sync} ...\n";
const SYNC: &str = "usage: mir context sync [-h] [--reindex-missing-vectors] [--db DB]\n                        [--project-root PROJECT_ROOT]\n";
const OPTIONS: &[&str] = &[
    "--help",
    "--reindex-missing-vectors",
    "--db",
    "--project-root",
];
type Output = (i32, String, String);
fn diag(sync: bool, message: &str) -> Output {
    (
        2,
        String::new(),
        format!(
            "{}mir context{}: error: {message}\n",
            if sync { SYNC } else { TOP },
            if sync { " sync" } else { "" }
        ),
    )
}
fn help(sync: bool) -> Output {
    let body = if sync {
        "\noptions:\n  -h, --help            show this help message and exit\n  --reindex-missing-vectors\n                        explicitly backfill missing vector rows; never falls\n                        back to FTS-only\n  --db DB\n  --project-root PROJECT_ROOT\n"
    } else {
        "\npositional arguments:\n  {pull,sync}\n    pull       ADR-53 D2: hybrid context retrieval\n    sync       ADR-53 D2: scan all configured archives\n\noptions:\n  -h, --help   show this help message and exit\n"
    };
    (
        0,
        format!("{}{body}", if sync { SYNC } else { TOP }),
        String::new(),
    )
}
/// Raw OS paths are restored by the root's shared scalar bridge before I/O.
pub fn console(argv: &[&str], path: impl Fn(&Path) -> PathBuf) -> Output {
    let Some(&action) = argv.first() else {
        return diag(false, "the following arguments are required: action");
    };
    let sync = action == "sync";
    if action == "pull" {
        return (
            64,
            String::new(),
            "mir: native context pull unavailable (pending Y-E6)\n".into(),
        );
    }
    let (mut db, mut root, mut reindex) = (None, None, false);
    let (mut unknown, mut i) = (Vec::new(), usize::from(sync));
    while let Some(&token) = argv.get(i) {
        i += 1;
        if token == "--" {
            unknown.extend_from_slice(&argv[i - 1..]);
            break;
        }
        if token.starts_with("-h") && !token.starts_with("-h=") {
            return help(sync);
        }
        let (name, explicit) = token
            .split_once('=')
            .map_or((token, None), |(a, b)| (a, Some(b)));
        let name = if name == "-h" { "--help" } else { name };
        let matches: Vec<_> = OPTIONS
            .iter()
            .filter(|o| **o == name || (name.starts_with("--") && o.starts_with(name)))
            .collect();
        let option = match matches.as_slice() {
            [o] if sync || **o == "--help" => **o,
            [] | [_] => {
                if !sync && !token.starts_with('-') {
                    return diag(
                        false,
                        &format!(
                            "argument action: invalid choice: {} (choose from pull, sync)",
                            repr(token)
                        ),
                    );
                }
                unknown.push(token);
                continue;
            }
            _ => {
                return diag(
                    sync,
                    &format!(
                        "ambiguous option: {name} could match {}",
                        matches.iter().map(|s| **s).collect::<Vec<_>>().join(", ")
                    ),
                );
            }
        };
        if ["--help", "--reindex-missing-vectors"].contains(&option) {
            if let Some(v) = explicit {
                let label = if option == "--help" {
                    "-h/--help"
                } else {
                    option
                };
                return diag(
                    sync,
                    &format!("argument {label}: ignored explicit argument {}", repr(v)),
                );
            }
            if option == "--help" {
                return help(sync);
            }
            reindex = true;
            continue;
        }
        let value = if let Some(v) = explicit {
            v
        } else {
            let Some(&v) = argv.get(i).filter(|v| !super::migrate::option_like(v)) else {
                return diag(sync, &format!("argument {option}: expected one argument"));
            };
            i += 1;
            v
        };
        if option == "--db" {
            db = Some(value);
        } else {
            root = Some(value);
        }
    }
    if !unknown.is_empty() {
        return diag(
            false,
            &format!("unrecognized arguments: {}", unknown.join(" ")),
        );
    }
    if !sync {
        return diag(false, "the following arguments are required: action");
    }
    let result = (|| -> Result<Output, String> {
        let cwd = std::env::current_dir().map_err(|e| format!("OSError: {e}"))?;
        let home = std::env::var_os("HOME")
            .map(PathBuf::from)
            .unwrap_or_else(|| cwd.clone());
        let db = db
            .map(|s| path(Path::new(if s.is_empty() { "." } else { s })))
            .unwrap_or_else(|| cwd.join(".mir/memory.db"));
        let parent = db.parent().unwrap_or(Path::new("."));
        let inferred = if db.file_name().is_some_and(|n| n == "memory.db")
            && parent.file_name().is_some_and(|n| n == ".mir")
        {
            parent.parent().unwrap_or(Path::new("."))
        } else {
            parent
        };
        let root = root
            .map(|s| path(Path::new(if s.is_empty() { "." } else { s })))
            .unwrap_or_else(|| inferred.to_owned());
        let root = loader::resolve_path(
            &cwd,
            &crate::executor_text::os_text(cwd.join(root).as_os_str()),
            &home,
        )
        .map_err(|e| format!("OSError: {e}"))?;
        if !db.is_file() {
            return Ok((
                2,
                format!(
                    "no memory.db at {} — run 'mir migrate up' first\n",
                    crate::executor_text::os_text(db.as_os_str())
                ),
                String::new(),
            ));
        }
        let cfg = match loader::load_config(Some(&root), &home, &cwd) {
            Ok(c) => c.to_dict(),
            Err(e) => {
                return Ok((
                    2,
                    format!("invalid memory configuration: {e}\n"),
                    String::new(),
                ));
            }
        };
        let conn = store::connect(
            &db,
            store::ConnectOptions {
                timeout: None,
                vec_loading: store::VecLoading::Bundled,
            },
        )
        .map_err(|e| format!("{}: {e}", e.python_class()))?;
        let stderr = if conn.vec_available {
            String::new()
        } else {
            format!(
                "sqlite-vec unavailable, FTS5-only mode: {}\n",
                conn.vec_reason
            )
        };
        let clock = crate::executor_execute::utc_now;
        let es = external_store::ExternalStore::new(&conn, &clock)
            .map_err(|e| format!("{}: {e}", e.kind))?;
        let result =
            super::context::do_sync_with_embedding(&es, &cfg, &root, &home, reindex, || {
                if cfg["memory"]["embedding"]["enabled"] == true {
                    Err(external_store::HelperError {
                        kind: "NativeRouteUnavailable",
                        message: "native embedding provider pending Y-E6".into(),
                    })
                } else {
                    Ok(None)
                }
            });
        // shortcut: enabled providers remain explicit until Y-E6; never claim FTS success.
        if result
            .as_ref()
            .is_err_and(|e| e.kind == "NativeRouteUnavailable")
        {
            return Ok((
                64,
                String::new(),
                "mir: native embedding provider unavailable (pending Y-E6)\n".into(),
            ));
        }
        match result {
            Ok((code, out)) => Ok((code, out, stderr)),
            Err(e) => Ok((1, String::new(), format!("{stderr}{}: {e}\n", e.kind))),
        }
    })();
    result.unwrap_or_else(|e| (1, String::new(), format!("{e}\n")))
}
