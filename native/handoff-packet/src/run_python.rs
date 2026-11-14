//! Native managed-interpreter selection. Python only executes consumer extensions.
#![forbid(unsafe_code)]
#![cfg_attr(
    not(test),
    deny(clippy::unwrap_used, clippy::expect_used, clippy::panic)
)]

use std::ffi::{OsStr, OsString};
use std::io::Write;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};

// This stdlib adapter deliberately does not import a provider implementation.
// runpy and CPython remain responsible for Python extension execution semantics.
const BOOTSTRAP: &str = r#"
import argparse, contextlib, importlib.util, os, runpy, signal, sys, traceback
from pathlib import Path
@contextlib.contextmanager
def execution(root, argv):
    prior_argv, prior_cwd, prior_path = sys.argv, Path.cwd(), list(sys.path)
    sys.argv = argv
    sys.path.insert(0, str(root))
    try:
        os.chdir(root)
        yield
    finally:
        sys.argv = prior_argv
        sys.path[:] = prior_path
        os.chdir(prior_cwd)
def exception_line(exc):
    text = traceback.format_exception_only(type(exc), exc)[-1]
    return text.replace('\r\n', '\n').replace('\r', '\n').removesuffix('\n').rsplit('\n', 1)[-1] + '\n'
def main():
    parser = argparse.ArgumentParser(prog='mir run-python')
    parser.add_argument('--project-root', type=Path, required=True)
    parser.add_argument('python_args', nargs=argparse.REMAINDER)
    namespace = parser.parse_args(sys.argv[1:])
    root = namespace.project_root.expanduser().resolve(strict=True)
    args = list(namespace.python_args)
    if args[:1] == ['--']: args = args[1:]
    if not args:
        print('run-python requires a script path or -m module', file=sys.stderr)
        return 2
    mode = args[0]
    if mode in ('-c', '-m') and len(args) < 2:
        print('run-python ' + mode + (' requires source code' if mode == '-c' else ' requires a module name'), file=sys.stderr)
        return 2
    if mode not in ('-c', '-', '-m'):
        script = Path(mode)
        if not script.is_absolute(): script = root / script
        try:
            script = script.resolve(strict=True)
            script.relative_to(root)
        except (OSError, ValueError) as exc:
            print(f'hook helper must be a real file inside {root}: {exc}', file=sys.stderr)
            return 2
        if not script.is_file() or script.is_symlink():
            print(f'hook helper must be a non-symlink file: {script}', file=sys.stderr)
            return 2
    try:
        source = sys.stdin.read() if mode == '-' else args[1] if mode == '-c' else None
        argv = (['-c', *args[2:]] if mode == '-c' else ['-', *args[1:]] if mode == '-' else
                [args[1], *args[2:]] if mode == '-m' else [str(script), *args[1:]])
        with execution(root, argv):
            if mode in ('-c', '-'):
                exec(compile(source, '<mir-run-python>' if mode == '-c' else '<stdin>', 'exec'), {'__name__': '__main__'})
            elif mode == '-m':
                if importlib.util.find_spec(args[1]) is None:
                    print(f'hook helper module is unavailable: {args[1]}', file=sys.stderr)
                    return 2
                runpy.run_module(args[1], run_name='__main__', alter_sys=True)
            else:
                runpy.run_path(str(script), run_name='__main__')
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 1
    return 0
# Restore the caller-visible argv that the installed console command supplies.
sys.argv[0] = sys.argv.pop(1)
console_directory = sys.argv.pop(1)
root_console = int(sys.argv.pop(1))
__file__ = os.path.abspath(sys.argv[0])
sys.orig_argv[:] = [sys.orig_argv[0], *sys.argv]
if root_console:
    del sys.argv[1]
if sys.path and not sys.flags.safe_path:
    sys.path[0] = console_directory
try:
    result = main()
except SystemExit:
    raise
except KeyboardInterrupt as exc:
    # CPython terminates an unhandled SIGINT with the original signal status.
    sys.stderr.write(exception_line(exc))
    sys.stderr.flush()
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    os.kill(os.getpid(), signal.SIGINT)
except BaseException as exc:
    sys.stderr.write(exception_line(exc))
    result = 1
raise SystemExit(result)
"#;

fn executable(path: &Path) -> bool {
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        path.metadata()
            .is_ok_and(|metadata| metadata.permissions().mode() & 0o111 != 0)
    }
    #[cfg(not(unix))]
    path.is_file()
}

fn program(name: &str) -> Option<PathBuf> {
    std::env::var_os("PATH").and_then(|path| {
        std::env::split_paths(&path)
            .map(|entry| entry.join(name))
            .find(|path| executable(path))
    })
}

fn query(receipt: &Path, expression: &str, required: bool, quiet: bool) -> String {
    let output = Command::new("jq")
        .args([
            OsStr::new("-r"),
            OsStr::new(expression),
            receipt.as_os_str(),
        ])
        .stderr(if quiet {
            Stdio::null()
        } else {
            Stdio::inherit()
        })
        .output();
    // Assignments in the reference run under set -e. Test and argument
    // substitutions intentionally retain their enclosing command's status.
    if required {
        match &output {
            Ok(output) if !output.status.success() => {
                #[cfg(unix)]
                {
                    use std::os::unix::process::ExitStatusExt;
                    std::process::exit(
                        output
                            .status
                            .code()
                            .unwrap_or_else(|| 128 + output.status.signal().unwrap_or(0)),
                    );
                }
                #[cfg(not(unix))]
                std::process::exit(output.status.code().unwrap_or(1));
            }
            Err(_) => std::process::exit(127),
            _ => (),
        }
    }
    output
        .ok()
        .and_then(|output| String::from_utf8(output.stdout).ok())
        .map(|output| output.trim_end_matches('\n').to_owned())
        .unwrap_or_default()
}

fn hash(path: &Path) -> String {
    let mut command = if program("sha256sum").is_some() {
        Command::new("sha256sum")
    } else if program("shasum").is_some() {
        let mut command = Command::new("shasum");
        command.args(["-a", "256"]);
        command
    } else {
        return String::new();
    };
    let output = command.arg(path).stderr(Stdio::null()).output().ok();
    let Some(output) = output else {
        return String::new();
    };
    // The reference's pipeline uses the actual awk output, even on failure.
    // Checking only that awk exists would admit a receipt the pipeline rejects.
    let Ok(mut awk) = Command::new("awk")
        .arg("{print $1}")
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()
    else {
        return String::new();
    };
    if let Some(mut input) = awk.stdin.take() {
        let _ = input.write_all(&output.stdout);
    }
    awk.wait_with_output()
        .ok()
        .and_then(|output| String::from_utf8(output.stdout).ok())
        .map(|output| output.trim_end_matches('\n').to_owned())
        .unwrap_or_default()
}

fn runtime_directory(external: &Path) -> Option<PathBuf> {
    // The reference runs this exact command substitution in a Bash child.
    // Keep dirname's PATH lookup, CDPATH's output/selection, and pwd -P bytes.
    let output = Command::new("/bin/bash")
        .arg("-c")
        .arg(format!(
            "{}cd -- \"$(dirname -- \"$1\")/..\" 2>/dev/null && pwd -P || true",
            "\n".repeat(43)
        ))
        .arg(std::env::args_os().next().unwrap_or_default())
        .arg(external)
        .stdin(Stdio::inherit())
        .stderr(Stdio::inherit())
        .output()
        .ok()?;
    #[cfg(unix)]
    {
        use std::os::unix::ffi::OsStringExt;
        let mut bytes = output.stdout;
        while bytes.last() == Some(&b'\n') {
            bytes.pop();
        }
        if bytes.is_empty() {
            return None;
        }
        Some(PathBuf::from(OsString::from_vec(bytes)))
    }
    #[cfg(not(unix))]
    {
        let output = String::from_utf8(output.stdout).ok()?;
        let output = output.trim_end_matches('\n');
        (!output.is_empty()).then(|| PathBuf::from(output))
    }
}

fn launch(mut command: Command, shell_line: Option<usize>) -> ! {
    #[cfg(unix)]
    {
        use std::os::unix::process::CommandExt;
        if let Some(line) = shell_line {
            // Bash owns exec's ENOEXEC fallback, exported shell state, and
            // platform-specific errors. It immediately replaces itself, keeping
            // the caller PID/signals after selection and validation finish.
            // Keep the frozen launcher's line number for failed-exec diagnostics.
            let mut shell = Command::new("/bin/bash");
            shell
                .arg("-c")
                .arg(format!("set -euo pipefail{}exec \"$@\"", "\n".repeat(line)))
                .arg(std::env::args_os().next().unwrap_or_default())
                .arg(command.get_program())
                .args(command.get_args());
            command = shell;
        }
        let error = command.exec();
        eprintln!("[mir hook] cannot execute managed interpreter: {error}");
        std::process::exit(if error.kind() == std::io::ErrorKind::NotFound {
            127
        } else {
            126
        });
    }
    #[cfg(not(unix))]
    {
        let _ = shell_line;
        let code = match command.status() {
            Ok(status) => status.code().unwrap_or(1),
            Err(error) => {
                eprintln!("[mir hook] cannot execute managed interpreter: {error}");
                127
            }
        };
        std::process::exit(code);
    }
}

fn refusal(root: &Path, kind: &str) -> ! {
    let adoption = root.join("config/bootstrap-adoption.json").is_file();
    let hint = if kind == "unavailable" {
        if adoption {
            "create the project environment (uv sync); ./setup.sh is refused while config/bootstrap-adoption.json exists"
        } else {
            "run setup.sh first (inside WSL on Windows hosts)"
        }
    } else if adoption {
        "reissue the receipt with uv run --project <provider worktree> mir bootstrap-adoption --apply"
    } else {
        "rerun setup.sh (inside WSL on Windows hosts)"
    };
    let message = match kind {
        "runtime" => "receipt-bound external Mir runtime is invalid",
        "receipt" => "receipt-bound external Mir Python is invalid",
        _ => "external Mir Python unavailable",
    };
    eprintln!("[mir hook] {message}; {hint}");
    std::process::exit(127);
}

// ENV is not sourced by non-interactive Bash; the pinned platform's Bash 3.2
// does not import BASHOPTS. Imported functions, BASH_ENV and shell options can
// act before selection. The allowlist is covered by frozen reference records.
fn startup_requires_reference() -> bool {
    std::env::vars_os().any(|(name, value)| {
        // Bash preserves an inherited export attribute when these script-local
        // variables are reassigned. Leave that pre-selection state to Bash.
        if matches!(
            name.to_str(),
            Some(
                "PROJECT_DIR"
                    | "_MIR_RECEIPT"
                    | "_MIR_EXTERNAL_CLI"
                    | "_MIR_EXTERNAL_SHA"
                    | "_MIR_RUNTIME_ROOT"
                    | "_MIR_RUNTIME_MANIFEST"
                    | "_MIR_RUNTIME_MANIFEST_SHA"
            )
        ) {
            return true;
        }
        if name == "BASH_ENV" {
            return !value.is_empty();
        }
        if name == "SHELLOPTS" {
            return value.to_str().is_none_or(|options| {
                options.split(':').any(|option| {
                    !matches!(
                        option,
                        "" | "braceexpand"
                            | "hashall"
                            | "interactive-comments"
                            | "errexit"
                            | "nounset"
                            | "pipefail"
                            | "emacs"
                            | "errtrace"
                            | "functrace"
                            | "histexpand"
                            | "history"
                            | "ignoreeof"
                            | "keyword"
                            | "monitor"
                            | "noclobber"
                            | "noglob"
                            | "nolog"
                            | "notify"
                            | "physical"
                            | "posix"
                            | "privileged"
                            | "vi"
                    )
                })
            });
        }
        name.to_str()
            .is_some_and(|name| name.starts_with("BASH_FUNC_") && name.ends_with("%%"))
            && value.as_encoded_bytes().starts_with(b"() {")
    })
}

#[allow(dead_code)]
fn main() {
    dispatch(
        std::env::args_os().skip(1).collect(),
        env!("CARGO_BIN_NAME") == "run-python",
        false,
    );
}
pub fn console(args: Vec<OsString>) -> ! {
    dispatch(args, true, true)
}
fn dispatch(args: Vec<OsString>, installed_console: bool, root_console: bool) -> ! {
    if installed_console {
        // Installed Python console scripts bind to their own environment. Do
        // not silently switch dependencies to a project or host interpreter.
        let python = std::env::current_exe().ok().and_then(|path| {
            path.parent().and_then(|directory| {
                [directory.join("python"), directory.join("python.exe")]
                    .into_iter()
                    .find(|path| executable(path))
            })
        });
        let Some(python) = python else {
            refusal(Path::new("."), "unavailable");
        };
        let console_directory = python.parent().and_then(|path| path.canonicalize().ok());
        let Some(console_directory) = console_directory else {
            refusal(Path::new("."), "unavailable");
        };
        let mut command = Command::new(&python);
        command
            .arg("-c")
            .arg(BOOTSTRAP)
            .arg(std::env::args_os().next().unwrap_or_default())
            .arg(console_directory)
            .arg(if root_console { "1" } else { "0" })
            .args(args);
        launch(command, None);
    }
    // Silent migration fallback, strictly before probes, commands or output.
    if startup_requires_reference() {
        std::process::exit(64);
    }
    let root = std::env::var_os("CLAUDE_PROJECT_DIR")
        .filter(|value| !value.is_empty())
        .or_else(|| std::env::var_os("MIR_PROJECT_DIR").filter(|value| !value.is_empty()))
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("."));
    let receipt = root.join(".mir/bootstrap-receipt.json");
    if program("jq").is_some()
        && receipt.is_file()
        && Command::new("jq")
            .args([
                OsStr::new("-e"),
                OsStr::new(".cli | type == \"object\""),
                receipt.as_os_str(),
            ])
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status()
            .is_ok_and(|status| status.success())
    {
        let external = PathBuf::from(query(&receipt, ".cli.executable // empty", true, true));
        let sha = query(&receipt, ".cli.sha256 // empty", true, true);
        if external.as_os_str().is_empty()
            || !executable(&external)
            || sha.is_empty()
            || hash(&external) != sha
        {
            refusal(&root, "receipt");
        }
        if !query(&receipt, ".cli.runtime_manifest // empty", false, true).is_empty() {
            let runtime = runtime_directory(&external);
            let manifest = query(&receipt, ".cli.runtime_manifest // empty", true, true);
            let manifest_sha = query(
                &receipt,
                ".cli.runtime_manifest_sha256 // empty",
                true,
                true,
            );
            let manifest_path = Path::new(&manifest);
            let valid = runtime.as_ref().is_some_and(|runtime| {
                manifest_path.as_os_str() == runtime.join("runtime-manifest.json").as_os_str()
                    && manifest_path.is_file()
                    && !manifest_path.is_symlink()
                    && hash(manifest_path) == manifest_sha
                    && Command::new(&external)
                        .args(["runtime-manifest", "verify", "--runtime-root"])
                        .arg(runtime)
                        .args([
                            "--manifest",
                            &manifest,
                            "--source-url",
                            &query(&receipt, ".cli.source_url // empty", false, false),
                            "--source-commit",
                            &query(&receipt, ".cli.source_commit // empty", false, false),
                            "--constraints-sha256",
                            &query(&receipt, ".cli.constraints_sha256 // empty", false, false),
                        ])
                        .stdout(Stdio::null())
                        .stderr(Stdio::null())
                        .status()
                        .is_ok_and(|status| status.success())
            });
            if !valid {
                refusal(&root, "runtime");
            }
        }
        let mut command = Command::new(external);
        command
            .arg("run-python")
            .arg("--project-root")
            .arg(&root)
            .arg("--")
            .args(args);
        launch(command, Some(61));
    }
    let python = [
        root.join(".venv/bin/python"),
        root.join(".venv/Scripts/python.exe"),
    ]
    .into_iter()
    .find(|path| executable(path));
    let (mut command, line) = if let Some(python) = python {
        let line = if python.ends_with("Scripts/python.exe") {
            75
        } else {
            71
        };
        (Command::new(python), line)
    } else if let Some(uv) = program("uv") {
        let mut command = Command::new(uv);
        command.arg("run").arg("--project").arg(&root).arg("python");
        (command, 79)
    } else {
        refusal(&root, "unavailable");
    };
    command.args(args);
    launch(command, Some(line));
}
