use serde_json::Value;
use std::{fs, process::Command};

#[test]
#[ignore]
fn capture_python_records() {
    let repo = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
    let setup = include_str!("fixtures/generate_y_e5.py")
        .split("archive_cfg =")
        .next()
        .unwrap();
    let setup = setup.replace(
        "repo = Path(__file__).resolve().parents[4]",
        "repo = Path(sys.argv.pop())",
    );
    let cases = r#"
assert sys.flags.utf8_mode
cases = [('i64-max','9223372036854775807'), ('i64-next','9223372036854775808'),
 ('u64-max','18446744073709551615'), ('u64-next','18446744073709551616'),
 ('30-digit','123456789012345678901234567890'), ('negative','-1'),
 ('float','1.5'), ('small','30'), ('digit-limit','1'*4301), ('digit-edge','1'*4300),
 ('underscores','+18_446_744_073_709_551_615'), ('integral-float','30.0'),
 ('hex','0xffffffffffffffff'), ('octal','0o1777777777777777777777'),
 ('binary','0b1'+'0'*64), ('pull-u64','18446744073709551615'), ('pull-limit','1'*4301)]
records = []
for name, token in cases:
 work = root / name
 work.mkdir(exist_ok=True)
 config = '[memory.embedding]\ntimeout_sec = ' + token + '\n'
 (work / 'harness_a.toml').write_text(config)
 seed = subprocess.run([sys.executable, '-I', '-X', 'utf8', str(wrapper), 'seed', 'synthetic.db'], cwd=work,
  env={'HOME':str(work), 'PATH':os.defpath}, capture_output=True)
 assert seed.returncode == 0, seed.stderr
 argv = ['context', 'pull', 'synthetic', '--db', 'synthetic.db', '--json'] if name.startswith('pull-') else ['context', 'sync', '--db', 'synthetic.db']
 out = subprocess.run([sys.executable, '-I', '-X', 'utf8', str(wrapper), *argv], cwd=work,
  env={'HOME':str(work), 'PATH':os.defpath, 'PYTHONIOENCODING':'utf-8'}, capture_output=True)
 records.append(dict(name=name, argv=argv, config=config, exit=out.returncode, stdout=out.stdout.decode().replace(str(work), '@ROOT@'), stderr=out.stderr.decode()))
assert records[0]['exit'] == 0 and records[0]['stdout'] == 'no archives configured\n', records[0]
assert records[-2]['exit'] == 0 and json.loads(records[-2]['stdout'])['degraded'] is False, records[-2]
a.output.write_text('[\n' + ',\n'.join(json.dumps(r, separators=(',', ':')) for r in records) + '\n]\n')
"#;
    // The existing generator parses argv before resolving repo: remove it before argparse.
    let setup = setup
        .replace(
            "p = argparse.ArgumentParser()",
            "repo_arg = sys.argv.pop()\np = argparse.ArgumentParser()",
        )
        .replace("repo = Path(sys.argv.pop())", "repo = Path(repo_arg)");
    let result = Command::new(repo.join(".venv/bin/python"))
        .args(["-I", "-X", "utf8", "-c", &(setup + cases), "--scratch"])
        .arg(std::env::var("MIR_NATIVE_TEST_SCRATCH").unwrap())
        .arg("--output")
        .arg(std::env::var("YFIX9_OUTPUT").unwrap())
        .arg(&repo)
        .current_dir(std::env::var("MIR_NATIVE_TEST_SCRATCH").unwrap())
        .output()
        .unwrap();
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
}

#[test]
fn timeout_console_records() {
    let records: Vec<Value> = serde_json::from_str(include_str!("fixtures/yfix9.json")).unwrap();
    assert!(records.len() >= 8);
    for r in records {
        let temp = tempfile::tempdir().unwrap();
        let root = fs::canonicalize(temp.path()).unwrap();
        fs::write(root.join("harness_a.toml"), r["config"].as_str().unwrap()).unwrap();
        let c = handoff_packet::mir_core::memory::store::connect(&root.join("synthetic.db"), None)
            .unwrap();
        handoff_packet::mir_core::memory::store::apply_migrations(&c.conn).unwrap();
        drop(c);
        let out = Command::new(env!("CARGO_BIN_EXE_mir"))
            .args(
                r["argv"]
                    .as_array()
                    .unwrap()
                    .iter()
                    .map(|a| a.as_str().unwrap()),
            )
            .env_clear()
            .env("HOME", &root)
            .current_dir(&root)
            .output()
            .unwrap();
        assert_eq!(
            out.status.code(),
            Some(r["exit"].as_i64().unwrap() as i32),
            "{} stdout={:?}",
            r["name"],
            String::from_utf8_lossy(&out.stdout)
        );
        assert_eq!(
            String::from_utf8(out.stdout)
                .unwrap()
                .replace(root.to_str().unwrap(), "@ROOT@"),
            r["stdout"],
            "{}",
            r["name"]
        );
        assert_eq!(
            String::from_utf8(out.stderr).unwrap(),
            r["stderr"],
            "{}",
            r["name"]
        );
    }
}

#[test]
fn lossless_timeout_json_and_marker_collision() {
    let temp = tempfile::tempdir().unwrap();
    let root = fs::canonicalize(temp.path()).unwrap();
    let token = "123456789012345678901234567890";
    fs::write(
        root.join("harness_a.toml"),
        format!("decoy={{__mir_toml_integer='forged'}}\n[memory.embedding]\ntimeout_sec={token}\n"),
    )
    .unwrap();
    let cfg =
        handoff_packet::mir_core::config::loader::load_config(Some(&root), &root, &root).unwrap();
    assert!(cfg.to_json().contains(&format!("\"timeout_sec\":{token}")));
    assert!(
        cfg.to_json()
            .contains("{\"__mir_toml_integer\":\"forged\"}")
    );
    assert!(
        cfg.to_dict()["memory"]["embedding"]["timeout_sec"]
            .as_i64()
            .is_none()
    );
}
