//! Console admission for context sync with configured oMLX embedding.
use crate::{
    executor_execute::repr,
    mir_core::{
        config::loader,
        memory::{backends::omlx_http, external_store, store},
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
pub(super) fn python_path(raw: &Path) -> PathBuf {
    let normalized: PathBuf = raw
        .components()
        .filter(|c| *c != std::path::Component::CurDir)
        .collect();
    let bytes = raw.as_os_str().as_encoded_bytes();
    if bytes.starts_with(b"//") && !bytes.starts_with(b"///") {
        let mut spelling = std::ffi::OsString::from("/");
        spelling.push(normalized);
        return PathBuf::from(spelling);
    }
    if normalized.as_os_str().is_empty() {
        PathBuf::from(".")
    } else {
        normalized
    }
}
pub(super) fn option_like(s: &str) -> bool {
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
            .any(|o| name.starts_with("--") && o.starts_with(name));
    s.len() > 1 && s.starts_with('-') && (known || (!negative && !s.contains(' ')))
}
/// Raw OS paths are restored by the root's shared scalar bridge before I/O.
pub fn console(argv: &[&str], path: impl Fn(&Path) -> PathBuf) -> Output {
    let Some(&action) = argv.first() else {
        return diag(false, "the following arguments are required: action");
    };
    let mut sync = false;
    if action == "pull" {
        return match super::context::console(argv, Path::new("."), &path) {
            Ok((code, out, err)) => (
                code,
                String::from_utf8_lossy(&out).into(),
                String::from_utf8_lossy(&err).into(),
            ),
            Err(e) => {
                let message = if let Some(error) = e.downcast_ref::<store::Error>() {
                    format!("{}: {error}\n", error.python_class())
                } else {
                    format!("{e}\n")
                };
                (1, String::new(), message)
            }
        };
    }
    let (mut db, mut root, mut reindex) = (None, None, false);
    let (mut unknown, mut i) = (Vec::new(), 0);
    while let Some(&token) = argv.get(i) {
        i += 1;
        if !sync && token == "pull" {
            let mut args = argv[i - 1..].to_vec();
            args.extend(unknown);
            return console(&args, path);
        }
        if !sync && token == "sync" {
            sync = true;
            continue;
        }
        if token == "--" {
            unknown.extend_from_slice(&argv[i - 1..]);
            break;
        }
        if token.starts_with("-h") && !token.starts_with("-h=") {
            if let Some((_, value)) = token.split_once('=') {
                return diag(
                    sync,
                    &format!(
                        "argument -h/--help: ignored explicit argument {}",
                        repr(value)
                    ),
                );
            }
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
            let Some(&v) = argv.get(i).filter(|v| !option_like(v)) else {
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
        let cwd =
            std::env::current_dir().map_err(|e| cwd_error(e).trim_end_matches('\n').to_owned())?;
        let home = std::env::var_os("HOME")
            .map(PathBuf::from)
            .unwrap_or_else(|| cwd.clone());
        let db = db
            .map(|s| python_path(&path(Path::new(s))))
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
        let emb = &cfg["memory"]["embedding"];
        let mut backend = backend(emb);
        let mut encode = |texts: &[String]| {
            backend
                .encode(texts)
                .map_err(|e| external_store::HelperError {
                    kind: "RuntimeError",
                    message: e.message,
                })
        };
        let result =
            super::context::do_sync_with_embedding(&es, &cfg, &root, &home, reindex, || {
                if emb["enabled"] == true {
                    Ok(Some(&mut encode))
                } else {
                    Ok(None)
                }
            });
        match result {
            Ok((code, out)) => Ok((code, out, stderr)),
            Err(e) => Ok((1, String::new(), format!("{stderr}{}: {e}\n", e.kind))),
        }
    })();
    result.unwrap_or_else(|e| (1, String::new(), format!("{e}\n")))
}

pub(super) fn cwd_error(e: std::io::Error) -> String {
    if e.kind() == std::io::ErrorKind::NotFound {
        "FileNotFoundError: [Errno 2] No such file or directory\n".into()
    } else {
        format!("OSError: {e}\n")
    }
}

pub(super) fn backend(
    emb: &serde_json::Value,
) -> omlx_http::OmlxHttpBackend<super::embedding_http::HttpTransport> {
    omlx_http::from_config(
        omlx_http::BackendCfg {
            base_url: emb["base_url"].as_str().unwrap_or_default().into(),
            model: emb["model"].as_str().unwrap_or_default().into(),
            dim: emb["dim"].as_i64().unwrap_or_default(),
            timeout_sec: emb["timeout_sec"].as_i64().unwrap_or_default(),
            norm_tolerance: emb["norm_tolerance"].as_f64().unwrap_or_default(),
            api_key_env: emb["api_key_env"].as_str().unwrap_or_default().into(),
            auth_scheme: emb["auth_scheme"].as_str().unwrap_or_default().into(),
        },
        |name| std::env::var(name).unwrap_or_default(),
        super::embedding_http::HttpTransport,
    )
}
