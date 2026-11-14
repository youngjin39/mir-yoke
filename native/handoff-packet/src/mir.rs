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
    if argv[0] == "runtime-manifest" {
        return manifest::console(argv[1..].to_vec());
    }
    if argv[0] == "run-python" {
        python::console(argv[1..].to_vec());
    }
    if argv[0] == "policy" || argv[0] == "migrate" {
        let cwd = match std::env::current_dir() {
            Ok(path) => path,
            Err(error) => return (1, String::new(), format!("OSError: {error}\n")),
        };
        if argv[0] == "policy" && argv.get(1).is_some_and(|a| a == "resolve") {
            let raw = std::iter::once(OsString::from("policy-resolve"))
                .chain(argv[2..].iter().cloned())
                .collect::<Vec<_>>();
            if let Some((out, err, code)) = handoff_packet::executor_policy_query::run(&raw, &cwd) {
                return (code, out, err);
            }
        }
        let args = argv[1..]
            .iter()
            .map(|a| a.to_string_lossy())
            .collect::<Vec<_>>();
        let refs = args.iter().map(|a| a.as_ref()).collect::<Vec<_>>();
        let mut failure = String::new();
        let (code, out, mut err) = if argv[0] == "policy" {
            mir_cli::policy::main(&refs, |_| None)
        } else {
            use handoff_packet::mir_core::memory::store;
            let parent = std::cell::RefCell::new(std::path::PathBuf::new());
            mir_cli::migrate::main(
                &refs,
                &cwd,
                |path| {
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
                            format!("{}\n", executor_text::io_error(e, &parent.borrow()))
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
            String::from_utf8_lossy(&err).into(),
        );
    }
    if argv[0] == "loop" {
        let cwd = std::path::PathBuf::from(".");
        // Collision-free scalar tokens carry typed OS surrogates through the scalar library.
        let mut token = "MIR_ARG_SURROGATE".to_owned();
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
        while plan.contains(&token) || argv.iter().any(|a| a.to_string_lossy().contains(&token)) {
            token.push('_');
        }
        let mut replacements = Vec::new();
        let args: Vec<String> = argv[1..]
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
        let refs: Vec<_> = args.iter().map(String::as_str).collect();
        let restore = |mut text: String| {
            for (marker, point) in &replacements {
                text = text.replace(marker, &format!("\\u{point:04x}"));
            }
            text
        };
        let result = mir_cli::r#loop::main_with_write(&refs, &cwd, |path, text| {
            let mut points = Vec::new();
            let mut rest = text;
            while !rest.is_empty() {
                if let Some((marker, point)) =
                    replacements.iter().find(|(m, _)| rest.starts_with(m))
                {
                    points.push(*point);
                    rest = &rest[marker.len()..];
                } else if let Some(c) = rest.chars().next() {
                    points.push(c as u32);
                    rest = &rest[c.len_utf8()..];
                }
            }
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
                (code as i32, restore(result.stdout), restore(result.stderr))
            }
            Err(error) => (
                1,
                String::new(),
                restore(format!("{}: {}\n", error.class, error.message)),
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

fn stdout_error(error: std::io::Error) -> String {
    if error.kind() == std::io::ErrorKind::BrokenPipe {
        return "BrokenPipeError: [Errno 32] Broken pipe".into();
    }
    let message = executor_text::io_error(error, std::path::Path::new(""));
    message.strip_suffix(": ''").unwrap_or(&message).to_owned()
}

fn main() {
    if let Err(message) = executor_text::encode_console(" ", false) {
        let _ = write!(
            std::io::stderr(),
            "Fatal Python error: init_stdio_encoding: failed to get the Python codec name of the stdio encoding\nPython runtime state: core initialized\n{message}\n\nCurrent thread <ADDRESS> (most recent call first):\n  <no Python frame>\n"
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
                match stdout.as_fd().try_clone_to_owned() {
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
        Err(_) => code = 1,
    }
    std::process::exit(code);
}
