#[path = "support/executable.rs"]
mod executable;
use serde_json::Value;
use std::{fs, process::Command};

#[path = "support/unify2_s6.rs"]
mod platform;

fn fixture_python() -> std::path::PathBuf {
    std::env::var_os("Y_E2_PYTHON").map_or_else(
        || {
            std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
                .join("../../.venv")
                .join(if cfg!(windows) {
                    "Scripts/python.exe"
                } else {
                    "bin/python"
                })
        },
        Into::into,
    )
}

fn provision_interpreter(source: &std::path::Path, root: &std::path::Path) -> std::path::PathBuf {
    let target = root.join("interpreter");
    assert!(
        source.is_file() && root.is_dir(),
        "fixture source={source:?}, destination={target:?}, parent_exists={}; set Y_E2_PYTHON to an existing interpreter",
        root.is_dir()
    );
    eprintln!("fixture source={source:?}, destination={target:?}, parent_exists=true");
    // A Windows venv launcher cannot be relocated by copying python.exe alone.
    // Let the installed interpreter supply pyvenv.cfg and its launcher/DLL layout.
    let out = isolated_command(source, root)
        .args(["-I", "-m", "venv", "--without-pip"])
        .arg(&target)
        .output()
        .unwrap_or_else(|e| panic!("venv source={source:?}, destination={target:?}: {e}"));
    assert!(out.status.success(), "venv source={source:?}: {out:?}");
    target.join(if cfg!(windows) { "Scripts" } else { "bin" })
}

fn isolated_command(executable: &std::path::Path, root: &std::path::Path) -> Command {
    let mut command = Command::new(executable);
    command
        .env_clear()
        .env("HOME", root)
        .env("USERPROFILE", root)
        .env("PYTHONIOENCODING", "utf-8")
        .current_dir(root);
    // Keep only the Windows loader's OS location, never host Python/PATH settings.
    #[cfg(windows)]
    for name in ["SystemRoot", "WINDIR"] {
        if let Some(value) = std::env::var_os(name) {
            command.env(name, value);
        }
    }
    command
}

#[test]
fn fixture_interpreter_starts_with_its_own_prefix_and_stdlib() {
    let temp = tempfile::tempdir().unwrap();
    let root = fs::canonicalize(temp.path()).unwrap();
    let bin = provision_interpreter(&fixture_python(), &root);
    let out = isolated_command(&bin.join(format!("python{}", std::env::consts::EXE_SUFFIX)), &root)
        .args(["-I", "-c", "import argparse, ctypes, runpy, sqlite3, sys; from pathlib import Path; assert Path(sys.prefix).resolve() == Path(sys.argv[1]).resolve(), sys.prefix; assert sys.prefix != sys.base_prefix"])
        // ntpath.realpath preserves a supplied \\?\ prefix, while sys.prefix
        // from the Windows venv uses an ordinary path. Resolve both from cwd.
        .arg("interpreter")
        .output()
        .unwrap();
    assert!(out.status.success(), "{out:?}");
    assert!(out.stdout.is_empty());
    assert!(out.stderr.is_empty());
}

fn expected_records(windows: bool, exists_message: &str) -> Vec<Value> {
    let mut records: Vec<Value> = serde_json::from_str(include_str!("fixtures/y-e2.json")).unwrap();
    for r in &mut records {
        for key in ["stdout", "stderr", "manifest"] {
            if let Some(text) = r[key].as_str() {
                r[key] = platform::expected_text(text, windows).into();
            }
        }
    }
    if windows {
        let frozen: Value =
            serde_json::from_str(include_str!("fixtures/y-e2-windows.json")).unwrap();
        for r in &mut records {
            // The verify setup reuses the captured create manifest, including its mode.
            if r["manifest"].is_string() {
                r["manifest"] = unhex(&frozen["records"][0]["manifest_hex"]).into();
            }
            if let Some(win) = frozen["records"]
                .as_array()
                .unwrap()
                .iter()
                .find(|w| w["argv"] == r["argv"])
            {
                r["exit"] = win["exit"].clone();
                for key in ["stdout", "stderr"] {
                    r[key] = unhex(&win[format!("{key}_hex")]).into();
                }
                if win["argv"][0] == "migrate" {
                    r["stderr"] = format!(
                        "FileExistsError: [WinError 183] {exists_message}: 'helper.py'\r\n"
                    )
                    .into();
                }
            }
        }
    }
    records
}

fn unhex(value: &Value) -> String {
    let bytes = value.as_str().unwrap().as_bytes().as_chunks::<2>();
    assert!(bytes.1.is_empty());
    String::from_utf8(
        bytes
            .0
            .iter()
            .map(|b| u8::from_str_radix(std::str::from_utf8(b).unwrap(), 16).unwrap())
            .collect(),
    )
    .unwrap()
}

fn exists_message() -> String {
    let message = std::io::Error::from_raw_os_error(183).to_string();
    message
        .strip_suffix(" (os error 183)")
        .unwrap_or(&message)
        .trim_end_matches([' ', '\r', '\n', '.'])
        .into()
}

#[test]
fn windows_manifest_selects_frozen_bytes() {
    let frozen: Value = serde_json::from_str(include_str!("fixtures/y-e2-windows.json")).unwrap();
    let records = expected_records(true, "unused");
    let row = &frozen["records"][0];
    let selected = records.iter().find(|r| r["argv"] == row["argv"]).unwrap();
    assert_eq!(selected["exit"], row["exit"]);
    for key in ["stdout", "stderr", "manifest"] {
        assert_eq!(selected[key], unhex(&row[format!("{key}_hex")]), "{key}");
    }
    assert_eq!(
        records
            .iter()
            .find(|r| r["setup"] == true && r["argv"][0] == "runtime-manifest")
            .unwrap()["manifest"],
        selected["manifest"]
    );
    let manifest: Value = serde_json::from_str(selected["manifest"].as_str().unwrap()).unwrap();
    assert_eq!(manifest["entries"][0]["mode"], 438);
}

#[test]
fn windows_migrate_selects_os_locale() {
    let frozen: Value = serde_json::from_str(include_str!("fixtures/y-e2-windows.json")).unwrap();
    let row = &frozen["records"][1];
    let captured = unhex(&row["stderr_hex"]);
    let locale = captured
        .strip_prefix("FileExistsError: [WinError 183] ")
        .unwrap()
        .strip_suffix(": 'helper.py'\r\n")
        .unwrap();
    for message in [locale, "File already exists", &exists_message()] {
        let records = expected_records(true, message);
        let selected = records.iter().find(|r| r["argv"] == row["argv"]).unwrap();
        assert_eq!(selected["exit"], row["exit"]);
        assert_eq!(selected["stdout"], unhex(&row["stdout_hex"]));
        assert_eq!(
            selected["stderr"],
            format!("FileExistsError: [WinError 183] {message}: 'helper.py'\r\n")
        );
        if message == locale {
            assert_eq!(selected["stderr"], captured);
        }
    }
    assert_eq!(
        expected_records(false, "unused"),
        serde_json::from_str::<Vec<Value>>(include_str!("fixtures/y-e2.json")).unwrap()
    );
}

fn check_family(family: &str) {
    let records = expected_records(cfg!(windows), &exists_message());
    for r in records.iter().filter(|r| r["argv"][0] == family) {
        let temp = tempfile::tempdir().unwrap();
        let root = fs::canonicalize(temp.path()).unwrap();
        #[cfg(windows)]
        let bin = provision_interpreter(&fixture_python(), &root);
        #[cfg(unix)]
        let bin = {
            let bin = root.join("bin");
            fs::create_dir(&bin).unwrap();
            std::os::unix::fs::symlink(fixture_python(), bin.join("python")).unwrap();
            bin
        };
        let mir = bin.join(format!("mir{}", std::env::consts::EXE_SUFFIX));
        #[cfg(unix)]
        executable::copy(env!("CARGO_BIN_EXE_mir"), &mir).unwrap();
        #[cfg(windows)]
        fs::copy(env!("CARGO_BIN_EXE_mir"), &mir).unwrap();
        fs::create_dir(root.join("config")).unwrap();
        fs::write(
            root.join("config/model-routing.lock.json"),
            r#"{"policy": {}}"#,
        )
        .unwrap();
        fs::create_dir(root.join("runtime")).unwrap();
        fs::write(root.join("runtime/data"), "payload\n").unwrap();
        fs::write(root.join("helper.py"), "print('script extension')\n").unwrap();
        if r["setup"] == true {
            if family == "runtime-manifest" {
                let body = records.iter().find(|r| r["manifest"].is_string()).unwrap();
                fs::write(
                    root.join("runtime/manifest.json"),
                    body["manifest"].as_str().unwrap(),
                )
                .unwrap();
            } else {
                let c =
                    handoff_packet::mir_core::memory::store::connect(&root.join("memory.db"), None)
                        .unwrap();
                handoff_packet::mir_core::memory::store::apply_migrations(&c.conn).unwrap();
            }
        }
        let output = isolated_command(&mir, &root)
            .args(
                r["argv"]
                    .as_array()
                    .unwrap()
                    .iter()
                    .map(|a| a.as_str().unwrap()),
            )
            .output()
            .unwrap();
        let normalize = |bytes: Vec<u8>| {
            String::from_utf8(bytes)
                .unwrap()
                .replace(root.to_str().unwrap(), "@ROOT@")
        };
        assert_eq!(
            output.status.code(),
            Some(r["exit"].as_i64().unwrap() as i32),
            "{}",
            r["argv"]
        );
        assert_eq!(
            normalize(output.stdout),
            r["stdout"].as_str().unwrap(),
            "{}",
            r["argv"]
        );
        assert_eq!(
            normalize(output.stderr),
            r["stderr"].as_str().unwrap(),
            "{}",
            r["argv"]
        );
        if family == "migrate" && r["exit"] == 0 && r["argv"][1] == "up" {
            let c = rusqlite::Connection::open(root.join("memory.db")).unwrap();
            assert_eq!(
                c.query_row("SELECT MAX(version) FROM schema_migrations", [], |r| r
                    .get::<_, String>(
                    0
                ))
                .unwrap(),
                "018"
            );
        }
        if let Some(body) = r["manifest"].as_str() {
            assert_eq!(
                fs::read_to_string(root.join("runtime/manifest.json")).unwrap(),
                body
            );
        }
    }
}
#[test]
fn policy() {
    check_family("policy");
}
#[test]
fn runtime_manifest() {
    check_family("runtime-manifest");
}
#[test]
fn run_python() {
    check_family("run-python");
}
#[test]
fn migrate() {
    check_family("migrate");
}

#[test]
fn missing_managed_interpreter_refuses() {
    let temp = tempfile::tempdir().unwrap();
    let mir = temp
        .path()
        .join(format!("mir{}", std::env::consts::EXE_SUFFIX));
    #[cfg(unix)]
    executable::copy(env!("CARGO_BIN_EXE_mir"), &mir).unwrap();
    #[cfg(windows)]
    fs::copy(env!("CARGO_BIN_EXE_mir"), &mir).unwrap();
    let out = Command::new(mir)
        .args(["run-python", "--help"])
        .env_clear()
        .env("HOME", temp.path())
        .current_dir(temp.path())
        .output()
        .unwrap();
    assert_eq!(out.status.code(), Some(127));
    assert!(out.stdout.is_empty());
    assert_eq!(out.stderr, b"[mir hook] external Mir Python unavailable; run setup.sh first (inside WSL on Windows hosts)\n");
}
