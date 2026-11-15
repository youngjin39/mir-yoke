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
    option_like_with(s, OPTIONS)
}
pub(super) fn option_like_with(s: &str, options: &[&str]) -> bool {
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
        || options
            .iter()
            .any(|o| name.starts_with("--") && o.starts_with(name));
    s.len() > 1 && s.starts_with('-') && (known || (!negative && !s.contains(' ')))
}
/// Raw OS paths are restored by the root's shared scalar bridge before I/O.
pub fn console(argv: &[&str], path: impl Fn(&Path) -> PathBuf) -> Output {
    console_parent(argv, path, &[])
}
fn console_parent(
    argv: &[&str],
    path: impl Fn(&Path) -> PathBuf,
    parent_unknown: &[&str],
) -> Output {
    let Some(&action) = argv.first() else {
        return diag(false, "the following arguments are required: action");
    };
    let mut sync = false;
    if action == "pull" {
        return match super::context::console_parent(argv, Path::new("/"), &path, parent_unknown) {
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
    let (mut unknown, mut i) = (parent_unknown.to_vec(), 0);
    while let Some(&token) = argv.get(i) {
        i += 1;
        if !sync && token == "pull" {
            return console_parent(&argv[i - 1..], path, &unknown);
        }
        if !sync && token == "sync" {
            sync = true;
            continue;
        }
        if token == "--"
            && !sync
            && let Some(next) = argv.get(i)
        {
            return diag(
                false,
                &format!(
                    "argument action: invalid choice: {} (choose from pull, sync)",
                    repr(next)
                ),
            );
        }
        if token == "--" {
            unknown.extend_from_slice(&argv[i - 1..]);
            break;
        }
        if token.starts_with("-h") && !token.starts_with("--") {
            if let Some(value) = short_help_error(token) {
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
            .filter(|o| {
                (sync || **o == "--help")
                    && (**o == name || (name.starts_with("--") && o.starts_with(name)))
            })
            .collect();
        let option = match matches.as_slice() {
            [o] if sync || **o == "--help" => **o,
            [] | [_] => {
                if !sync && !option_like(token) {
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
        let needs_cwd = db.is_none()
            || root.map_or_else(
                || db.is_some_and(|p| Path::new(p).is_relative()),
                |p| Path::new(p).is_relative(),
            );
        let cwd = if needs_cwd {
            std::env::current_dir().map_err(|e| cwd_error(e).trim_end_matches('\n').to_owned())?
        } else {
            PathBuf::from("/")
        };
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
        let instance = std::cell::RefCell::new(
            None::<omlx_http::OmlxHttpBackend<super::embedding_http::HttpTransport>>,
        );
        let mut encode = |texts: &[String]| {
            instance
                .borrow_mut()
                .as_mut()
                .ok_or_else(|| external_store::HelperError {
                    kind: "RuntimeError",
                    message: "embedding provider unavailable".into(),
                })?
                .encode(texts)
                .map_err(|e| external_store::HelperError {
                    kind: "RuntimeError",
                    message: e.message,
                })
        };
        let result =
            super::context::do_sync_with_embedding(&es, &cfg, &root, &home, reindex, || {
                if emb["enabled"] == true {
                    *instance.borrow_mut() = Some(backend(emb)?);
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

pub(super) fn short_help_error(token: &str) -> Option<&str> {
    let tail = token.strip_prefix('-')?.trim_start_matches('h');
    tail.strip_prefix('=')
        .or_else(|| tail.starts_with('-').then_some(tail))
}

pub(super) fn backend(
    emb: &serde_json::Value,
) -> Result<
    omlx_http::OmlxHttpBackend<super::embedding_http::HttpTransport>,
    external_store::HelperError,
> {
    let error = |kind, message| external_store::HelperError { kind, message };
    let url = emb["base_url"].as_str().unwrap_or_default();
    if url.chars().count() > 65536 {
        return Err(error("InvalidURL", "URL too long".into()));
    }
    if let Some((position, c)) = url.chars().enumerate().find(|(_, c)| c.is_ascii_control()) {
        return Err(error(
            "InvalidURL",
            format!(
                "Invalid non-printable ASCII character in URL, {} at position {position}.",
                repr(&c.to_string())
            ),
        ));
    }
    let authority = url
        .split_once("://")
        .map(|(_, s)| s.split(['/', '?', '#']).next().unwrap_or_default());
    if let Some(authority) = authority {
        let host = authority.rsplit('@').next().unwrap_or_default();
        let hostname = host.split(':').next().unwrap_or_default();
        let parts: Vec<_> = hostname.split('.').collect();
        if parts.len() == 4
            && parts
                .iter()
                .all(|p| !p.is_empty() && p.bytes().all(|b| b.is_ascii_digit()))
            && hostname.parse::<std::net::Ipv4Addr>().is_err()
        {
            return Err(error(
                "InvalidURL",
                format!("Invalid IPv4 address: {}", repr(hostname)),
            ));
        }
        if host.starts_with('[')
            && let Some((address, _)) = host.split_once(']')
        {
            let (ip, scope) = address[1..].split_once('%').unwrap_or((&address[1..], ""));
            if ip.parse::<std::net::Ipv6Addr>().is_err()
                || (address.contains('%') && (scope.is_empty() || scope.contains('%')))
            {
                return Err(error(
                    "InvalidURL",
                    format!("Invalid IPv6 address: {}", repr(&format!("{address}]"))),
                ));
            }
        }
        if let Some((_, port)) = host.rsplit_once(':').filter(|_| !host.ends_with(']'))
            && !port.is_empty()
            && super::context::python_k(port).is_none()
        {
            return Err(error("InvalidURL", format!("Invalid port: {}", repr(port))));
        }
    }
    let key = std::env::var_os(emb["api_key_env"].as_str().unwrap_or_default()).unwrap_or_default();
    let mut header: Vec<u32> = emb["auth_scheme"]
        .as_str()
        .unwrap_or_default()
        .chars()
        .map(u32::from)
        .collect();
    header.push(32);
    header.extend(crate::executor_text::os_points(&key));
    if !key.is_empty()
        && let Some((position, c)) = header.iter().copied().enumerate().find(|(_, c)| *c > 127)
    {
        let escaped = if c < 256 {
            format!("\\x{:02x}", c)
        } else if c < 65536 {
            format!("\\u{:04x}", c)
        } else {
            format!("\\U{:08x}", c)
        };
        let end = position
            + header
                .iter()
                .skip(position)
                .take_while(|c| **c > 127)
                .count();
        let detail = if end == position + 1 {
            format!("character '{escaped}' in position {position}")
        } else {
            format!("characters in position {position}-{}", end - 1)
        };
        return Err(error(
            "UnicodeEncodeError",
            format!("'ascii' codec can't encode {detail}: ordinal not in range(128)"),
        ));
    }
    if let Some(file) = std::env::var_os("SSL_CERT_FILE").filter(|s| !s.is_empty()) {
        let pem = std::fs::read(file).map_err(|e| {
            let text = crate::executor_brief_profile::python_os_error_message(&e, Path::new(""));
            error("OSError", text.strip_suffix(": ''").unwrap_or(&text).into())
        })?;
        // Bounded trust-file admission for the cited no-certificate input.
        // TLS and malformed certificate payloads remain outside this transport.
        if ![
            b"-----BEGIN CERTIFICATE-----".as_slice(),
            b"-----BEGIN TRUSTED CERTIFICATE-----",
            b"-----BEGIN X509 CRL-----",
        ]
        .iter()
        .any(|marker| pem.windows(marker.len()).any(|w| w == *marker))
        {
            return Err(error(
                "SSLError",
                "[X509: NO_CERTIFICATE_OR_CRL_FOUND] no certificate or crl found (_ssl.c:4106)"
                    .into(),
            ));
        }
    }
    // httpx constructs environment proxy mounts before NO_PROXY selection.
    for name in ["HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"] {
        let proxy = std::env::var(name).unwrap_or_default();
        if proxy.is_empty() {
            continue;
        }
        if name == "ALL_PROXY" && proxy.starts_with("ftp://") {
            return Err(error(
                "ValueError",
                format!("Unknown scheme for proxy URL URL({})", repr(&proxy)),
            ));
        }
        let authority = proxy
            .split("://")
            .nth(1)
            .unwrap_or(&proxy)
            .split('/')
            .next()
            .unwrap_or("");
        if let Some((_, port)) = authority.rsplit_once(':')
            && name != "ALL_PROXY"
            && !authority.ends_with(']')
            && !port.is_empty()
            && super::context::python_k(port).is_none()
        {
            return Err(error("InvalidURL", format!("Invalid port: {}", repr(port))));
        }
    }
    Ok(omlx_http::from_config(
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
        super::embedding_http::HttpTransport {
            unbounded_timeout: emb["timeout_sec"].as_i64().is_none(),
            ..Default::default()
        },
    ))
}
