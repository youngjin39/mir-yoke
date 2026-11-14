//! Native console root. Caller/package switching belongs to the closing slice.
use handoff_packet::{executor_text, mir_cli, mir_front};
use std::{ffi::OsString, io::Write};

#[path = "runtime_manifest.rs"]
mod manifest;
#[path = "run_python.rs"]
mod python;

fn run(argv: &[OsString]) -> (i32, String, String) {
    if let Some((code, out, err)) = mir_front::root(argv) {
        return (
            code,
            String::from_utf8_lossy(&out).into(),
            String::from_utf8_lossy(&err).into(),
        );
    }
    if argv[0] == "context" {
        let (args, replacements) = scalar_args(&argv[1..], "");
        let refs = args.iter().map(String::as_str).collect::<Vec<_>>();
        let (code, out, err) =
            mir_cli::context_sync::console(&refs, |p| scalar_path(p, &replacements));
        return (
            code,
            restore(out, &replacements),
            restore(err, &replacements),
        );
    }
    if argv[0] == "runtime-manifest" {
        return manifest::console(argv[1..].to_vec());
    }
    if argv[0] == "run-python" {
        python::console(argv.to_vec());
    }
    if argv[0] == "policy" || argv[0] == "migrate" {
        if argv[0] == "policy" && argv.get(1).is_some_and(|a| a == "resolve") {
            let cwd = match std::env::current_dir() {
                Ok(path) => path,
                Err(error) => return (1, String::new(), format!("OSError: {error}\n")),
            };
            let raw = std::iter::once(OsString::from("policy-resolve"))
                .chain(argv[2..].iter().cloned())
                .collect::<Vec<_>>();
            if let Some((out, err, code)) = handoff_packet::executor_policy_query::run(&raw, &cwd) {
                return (code, out, err);
            }
        }
        let (args, replacements) = scalar_args(&argv[1..], "");
        let refs = args.iter().map(String::as_str).collect::<Vec<_>>();
        let mut failure = String::new();
        let (code, out, mut err) = if argv[0] == "policy" {
            mir_cli::policy::main(&refs, |_| None)
        } else {
            use handoff_packet::mir_core::memory::store;
            let parent = std::cell::RefCell::new(std::path::PathBuf::new());
            mir_cli::migrate::main_with_cwd(
                &refs,
                || std::env::current_dir().map_err(store::Error::Io),
                |path| {
                    let path = scalar_path(path, &replacements);
                    let path = path.as_path();
                    *parent.borrow_mut() = path.parent().unwrap_or(path).to_owned();
                    store::connect(
                        path,
                        store::ConnectOptions {
                            timeout: None,
                            vec_loading: store::VecLoading::Bundled,
                        },
                    )
                },
                |error| {
                    failure = match error {
                        store::Error::Io(e) => {
                            let message = executor_text::io_error(e, &parent.borrow());
                            let message = if parent.borrow().as_os_str().is_empty() {
                                message.strip_suffix(": ''").unwrap_or(&message)
                            } else {
                                &message
                            };
                            format!("{message}\n")
                        }
                        other => format!("{}: {other}\n", other.python_class()),
                    };
                },
            )
        };
        err.extend_from_slice(failure.as_bytes());
        return (
            code,
            String::from_utf8_lossy(&out).into(),
            restore(String::from_utf8_lossy(&err).into(), &replacements),
        );
    }
    if argv[0] == "loop" {
        let cwd = std::path::PathBuf::from(".");
        // Collision-free scalar tokens carry typed OS surrogates through the scalar library.
        let needs_plan = argv[1..].iter().any(|a| a.to_str().is_none())
            && argv.get(1).is_some_and(|a| a == "mark")
            && !argv[1..].iter().any(|a| a == "--help" || a == "-h");
        let plan = if needs_plan
            && std::fs::metadata(cwd.join("tasks/plan.md")).is_ok_and(|m| m.is_file())
        {
            std::fs::read_to_string(cwd.join("tasks/plan.md")).unwrap_or_default()
        } else {
            String::new()
        };
        let (args, replacements) = scalar_args(&argv[1..], &plan);
        let refs: Vec<_> = args.iter().map(String::as_str).collect();
        let result = mir_cli::r#loop::main_with_write(&refs, &cwd, |path, text| {
            let points = scalar_points(text, &replacements);
            if let Some(start) = points.iter().position(|p| (0xd800..=0xdfff).contains(p)) {
                let end = start
                    + points[start..]
                        .iter()
                        .take_while(|p| (0xd800..=0xdfff).contains(*p))
                        .count();
                let message = executor_text::encode_error(
                    "utf-8",
                    &points,
                    start,
                    end,
                    "surrogates not allowed",
                );
                return Err(
                    handoff_packet::mir_core::conductor::dispatch_brief::Error::named(
                        "UnicodeEncodeError",
                        message.trim_start_matches("UnicodeEncodeError: "),
                    ),
                );
            }
            handoff_packet::mir_core::conductor::dispatch_brief::atomic_write(path, text, |_, _| {
                Ok(())
            })
        });
        return match result {
            Ok(result) => {
                let code = result
                    .status
                    .as_i64()
                    .or_else(|| result.status.get(1)?.as_i64())
                    .unwrap_or(1);
                (
                    code as i32,
                    restore(result.stdout, &replacements),
                    restore(result.stderr, &replacements),
                )
            }
            Err(error) => (
                1,
                String::new(),
                restore(
                    format!("{}: {}\n", error.class, error.message),
                    &replacements,
                ),
            ),
        };
    }
    // shortcut: remaining families bind in later entry slices; never forward to Python.
    (
        64,
        String::new(),
        format!(
            "mir: native route unavailable: {} (pending entry closure)\n",
            argv[0].to_string_lossy()
        ),
    )
}

// Reuse the loop scalar bridge for argparse; raw paths are restored before I/O.
fn scalar_args(argv: &[OsString], plan: &str) -> (Vec<String>, Vec<(String, u32)>) {
    let mut token = "MIR_ARG_SURROGATE".to_owned();
    while plan.contains(&token) || argv.iter().any(|a| a.to_string_lossy().contains(&token)) {
        token.push('_');
    }
    let mut replacements = Vec::new();
    let args: Vec<String> = argv
        .iter()
        .map(|a| {
            executor_text::os_points(a)
                .into_iter()
                .map(|p| {
                    char::from_u32(p).map(|c| c.to_string()).unwrap_or_else(|| {
                        let marker = format!("{token}{}END", replacements.len());
                        replacements.push((marker.clone(), p));
                        marker
                    })
                })
                .collect()
        })
        .collect();
    (args, replacements)
}
fn restore(mut text: String, replacements: &[(String, u32)]) -> String {
    for (marker, point) in replacements {
        text = text.replace(marker, &format!("\\u{point:04x}"));
    }
    text
}
fn scalar_points(text: &str, replacements: &[(String, u32)]) -> Vec<u32> {
    let mut points = Vec::new();
    let mut rest = text;
    while !rest.is_empty() {
        if let Some((marker, point)) = replacements.iter().find(|(m, _)| rest.starts_with(m)) {
            points.push(*point);
            rest = &rest[marker.len()..];
        } else if let Some(c) = rest.chars().next() {
            points.push(c as u32);
            rest = &rest[c.len_utf8()..];
        }
    }
    points
}
fn scalar_path(path: &std::path::Path, replacements: &[(String, u32)]) -> std::path::PathBuf {
    if path.to_str().is_none() || replacements.is_empty() {
        return path.to_owned();
    }
    let points = scalar_points(&executor_text::os_text(path.as_os_str()), replacements);
    #[cfg(unix)]
    {
        use std::os::unix::ffi::OsStringExt;
        let mut bytes = Vec::new();
        for point in points {
            if let Some(c) = char::from_u32(point) {
                bytes.extend(c.to_string().as_bytes());
            } else {
                bytes.push((point - 0xdc00) as u8);
            }
        }
        OsString::from_vec(bytes).into()
    }
    #[cfg(windows)]
    {
        use std::os::windows::ffi::OsStringExt;
        let mut wide = Vec::new();
        for point in points {
            if let Some(c) = char::from_u32(point) {
                wide.extend(c.encode_utf16(&mut [0; 2]).iter().copied());
            } else {
                wide.push(point as u16);
            }
        }
        OsString::from_wide(&wide).into()
    }
    #[cfg(not(any(unix, windows)))]
    executor_text::points_text(&points).into()
}

fn stdout_error(error: std::io::Error) -> String {
    if error.kind() == std::io::ErrorKind::BrokenPipe {
        return "BrokenPipeError: [Errno 32] Broken pipe".into();
    }
    let message = executor_text::io_error(error, std::path::Path::new(""));
    message.strip_suffix(": ''").unwrap_or(&message).to_owned()
}

#[cfg(all(test, unix))]
mod tests {
    #[test]
    fn injected_stdout_dup_child() {
        if std::env::var_os("MIR_TEST_STDOUT_DUP_EMFILE").is_some() {
            super::main();
        }
    }

    #[test]
    fn stdout_dup_failure() {
        let r: serde_json::Value =
            serde_json::from_str(include_str!("../tests/fixtures/y-e4.json")).unwrap();
        // The pinned console succeeds under RLIMIT_NOFILE=3; only os.dup fails.
        assert_eq!(r["no_dup_console"]["exit"], 0);
        let temp = tempfile::tempdir().unwrap();
        let out = std::process::Command::new(std::env::current_exe().unwrap())
            .args([
                "--exact",
                "tests::injected_stdout_dup_child",
                "--nocapture",
                "--quiet",
            ])
            .env_clear()
            .env("HOME", temp.path())
            .env("MIR_TEST_STDOUT_DUP_EMFILE", "1")
            .current_dir(temp.path())
            .output()
            .unwrap();
        assert_eq!(out.status.code(), Some(1));
        // The harness prints its preamble before entering the test.
        assert_eq!(out.stdout, b"\nrunning 1 test\n");
        assert_eq!(
            out.stderr,
            format!("{}\n", r["no_dup_console"]["dup_error"].as_str().unwrap()).as_bytes()
        );
    }
}

fn main() {
    if let Err(message) = executor_text::console_encoding() {
        let stage = if message.starts_with("LookupError: unknown encoding:") {
            "init_stdio_encoding: failed to get the Python codec name of the stdio encoding"
        } else {
            "init_sys_streams: can't initialize sys standard streams"
        };
        let _ = write!(
            std::io::stderr(),
            "Fatal Python error: {stage}\nPython runtime state: core initialized\n{message}\n\nCurrent thread <ADDRESS> (most recent call first):\n  <no Python frame>\n"
        );
        std::process::exit(1);
    }
    let args: Vec<_> = std::env::args_os().skip(1).collect();
    let (mut code, out, mut err) = run(&args);
    match executor_text::encode_console(&out, false) {
        Ok(bytes) => {
            // CPython buffers small piped writes until interpreter shutdown. A failure
            // there has status 120; large writes fail during the command (status 1).
            let stdout = std::io::stdout();
            #[cfg(unix)]
            let capacity = {
                use std::os::{fd::AsFd, unix::fs::MetadataExt};
                stdout
                    .as_fd()
                    .try_clone_to_owned()
                    .ok()
                    .and_then(|fd| std::fs::File::from(fd).metadata().ok())
                    .map_or(8192, |m| m.blksize().clamp(8192, 8 * 1024 * 1024) as usize)
            };
            #[cfg(not(unix))]
            let capacity = 8192;
            #[cfg(unix)]
            let writer = {
                use std::os::fd::AsFd;
                let cloned = stdout.as_fd().try_clone_to_owned();
                // Only the unit-test binary admits fault injection; release and
                // integration-test console binaries have no environment seam.
                #[cfg(test)]
                let cloned = if std::env::var_os("MIR_TEST_STDOUT_DUP_EMFILE").is_some() {
                    Err(std::io::Error::from_raw_os_error(libc::EMFILE))
                } else {
                    cloned
                };
                match cloned {
                    Ok(fd) => std::fs::File::from(fd),
                    Err(error) => {
                        let _ = writeln!(std::io::stderr(), "{}", stdout_error(error));
                        std::process::exit(1);
                    }
                }
            };
            #[cfg(not(unix))]
            let writer = stdout.lock();
            let mut stream = std::io::BufWriter::with_capacity(capacity, writer);
            if let Err(error) = stream.write_all(&bytes) {
                code = 1;
                err = format!("{}\n", stdout_error(error));
            } else if let Err(error) = stream.flush() {
                code = 120;
                let encoding = std::env::var("PYTHONIOENCODING").unwrap_or_else(|_| "utf-8".into());
                let encoding = encoding.split(':').next().unwrap_or("utf-8");
                err = format!(
                    "Exception ignored in: <_io.TextIOWrapper name='<stdout>' mode='w' encoding='{encoding}'>\n{}\n",
                    stdout_error(error)
                );
            }
        }
        Err(message) => {
            code = 1;
            err = format!("{message}\n");
        }
    }
    match executor_text::encode_console(&err, true) {
        Ok(bytes) => {
            if std::io::stderr().write_all(&bytes).is_err() {
                code = 1;
            }
        }
        Err(message) => {
            // Even a codec without native diagnostic bytes must fail visibly.
            let _ = writeln!(std::io::stderr(), "{message}");
            code = 1;
        }
    }
    std::process::exit(code);
}
