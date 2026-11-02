use handoff_packet::local_bridge::{BridgeConfig, BridgeError, LocalBridge, PROTOCOL};
use serde_json::{Value, json};
use std::{collections::BTreeMap, fs, path::PathBuf, time::Duration};

struct Fixture(PathBuf);
static NEXT_FIXTURE: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);
impl Fixture {
    fn new(script: &str) -> Self {
        let base = std::env::var_os("MIR_LOCAL_BRIDGE_TEST_SCRATCH")
            .map(PathBuf::from)
            .unwrap_or_else(std::env::temp_dir);
        let root = base.join(format!(
            "client-{}-{}",
            std::process::id(),
            NEXT_FIXTURE.fetch_add(1, std::sync::atomic::Ordering::Relaxed)
        ));
        fs::create_dir_all(root.join("tools/mir_executor")).unwrap();
        fs::write(root.join("tools/mir_executor/local.py"), "").unwrap();
        fs::write(root.join("bridge.py"), script).unwrap();
        Self(root)
    }
    fn config(&self) -> BridgeConfig {
        BridgeConfig {
            interpreter: test_interpreter(),
            target_root: self.0.clone(),
            bridge_script: self.0.join("bridge.py"),
            environment: BTreeMap::new(),
            timeout: Duration::from_secs(10),
        }
    }
}
impl Drop for Fixture {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}
const HELLO: &str = "import json,sys\nv='mir-executor.local@1'\nprint(json.dumps({'version':v,'hooks':['echo'],'register_execute_options':False}),flush=True)\n";
#[test]
fn absent_local_does_not_launch_interpreter() {
    let fixture = Fixture::new("");
    fs::remove_file(fixture.0.join("tools/mir_executor/local.py")).unwrap();
    let mut config = fixture.config();
    config.interpreter = fixture.0.join("missing-python");
    assert!(LocalBridge::start(config).unwrap().is_none());
}
#[test]
fn persistent_child_preserves_response_and_handles() {
    let fixture = Fixture::new(&format!(
        "{HELLO}count=0\nfor line in sys.stdin:\n r=json.loads(line);count+=1\n print(json.dumps({{'version':v,'id':r['id'],'ok':True,'result':[count,r['args'],r.get('handles',{{}})],'handle':'h1'}}),flush=True)\n"
    ));
    let mut bridge = LocalBridge::start(fixture.config()).unwrap().unwrap();
    assert_eq!(bridge.hello()["version"], PROTOCOL);
    assert_eq!(
        bridge
            .call("echo", vec![json!("a")], json!({"handles":{"0":"h1"}}))
            .unwrap()["result"],
        json!([1,["a"],{"0":"h1"}])
    );
    assert_eq!(
        bridge.call("echo", vec![], json!({})).unwrap()["result"][0],
        2
    );
}
#[test]
fn rejects_invalid_reply_id_version_and_frame() {
    for response in [
        "{'version':v,'id':999,'ok':True,'result':None}",
        "{'version':'wrong','id':r['id'],'ok':True}",
        "{'version':v,'id':r['id'],'ok':'yes'}",
    ] {
        let fixture = Fixture::new(&format!(
            "{HELLO}r=json.loads(sys.stdin.readline())\nprint(json.dumps({response}),flush=True)\n"
        ));
        let mut bridge = LocalBridge::start(fixture.config()).unwrap().unwrap();
        let response = bridge.call("echo", vec![], json!({}));
        assert!(
            matches!(response, Err(BridgeError::Protocol(_))),
            "{response:?}"
        );
        assert!(matches!(
            bridge.call("echo", vec![], json!({})),
            Err(BridgeError::Closed)
        ));
    }
    let fixture = Fixture::new("print('x'*1048577,flush=True)\n");
    assert!(matches!(
        LocalBridge::start(fixture.config()),
        Err(BridgeError::FrameTooLarge)
    ));
}
#[test]
fn times_out_and_reaps_child() {
    let fixture = Fixture::new("import time\ntime.sleep(30)\n");
    let mut config = fixture.config();
    config.timeout = Duration::from_millis(100);
    let start = std::time::Instant::now();
    assert!(matches!(
        LocalBridge::start(config),
        Err(BridgeError::Timeout)
    ));
    assert!(start.elapsed() < Duration::from_secs(3));
}
#[test]
fn rejects_reserved_request_overrides_and_oversized_calls() {
    let fixture = Fixture::new(HELLO);
    let mut bridge = LocalBridge::start(fixture.config()).unwrap().unwrap();
    assert!(matches!(
        bridge.call("echo", vec![], json!({"id":8})),
        Err(BridgeError::Protocol(_))
    ));
    assert!(matches!(
        bridge.call("echo", vec![Value::String("x".repeat(1048576))], json!({})),
        Err(BridgeError::FrameTooLarge)
    ));
}

fn test_interpreter() -> PathBuf {
    if let Some(path) = std::env::var_os("MIR_LOCAL_BRIDGE_TEST_PYTHON") {
        return PathBuf::from(path);
    }
    // Windows runners provide `python` but not always `python3`.
    let output = ["python3", "python"]
        .iter()
        .find_map(|name| {
            std::process::Command::new(name)
                .args(["-c", "import sys; print(sys.executable)"])
                .output()
                .ok()
                .filter(|output| output.status.success())
        })
        .expect("Python fixture interpreter");
    PathBuf::from(String::from_utf8(output.stdout).unwrap().trim())
}
#[test]
fn write_timeout_covers_a_child_that_never_reads_stdin() {
    let fixture = Fixture::new(&format!("{HELLO}import time\ntime.sleep(30)\n"));
    let mut config = fixture.config();
    config.timeout = Duration::from_millis(150);
    let mut bridge = LocalBridge::start(config).unwrap().unwrap();
    let start = std::time::Instant::now();
    assert!(matches!(
        bridge.call("echo", vec![json!("x".repeat(512 * 1024))], json!({})),
        Err(BridgeError::Timeout)
    ));
    assert!(start.elapsed() < Duration::from_secs(3));
}
#[test]
fn real_bridge_preserves_objects_errors_and_context_identity() {
    let fixture = Fixture::new("");
    fs::write(
        fixture.0.join("tools/mir_executor/local.py"),
        r#"
from contextlib import contextmanager
active = False
def validate_brief(brief):
    brief["validated"] = True
    return brief
def before_run(brief):
    assert brief["validated"]
    brief["runs"] = brief.get("runs", 0) + 1
    return brief
@contextmanager
def writer_scope():
    global active
    active = True
    try:
        yield
    finally:
        active = False
def after_run():
    return active
def on_job_event():
    raise ValueError("fixture failure")
"#,
    )
    .unwrap();
    let mut config = fixture.config();
    config.bridge_script =
        PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../tools/mir_executor/local_bridge.py");
    let mut bridge = LocalBridge::start(config).unwrap().unwrap();
    assert_eq!(bridge.hello()["register_execute_options"], false);
    let validated = bridge
        .call("validate_brief", vec![json!({})], json!({}))
        .unwrap();
    let handle = validated["handle"].as_str().unwrap();
    for run in 1..=2 {
        let reply = bridge
            .call(
                "before_run",
                vec![Value::Null],
                json!({"handles":{"0":handle}}),
            )
            .unwrap();
        assert_eq!(reply["result"]["runs"], run);
    }
    let scope = bridge.call("writer_scope", vec![], json!({})).unwrap();
    let scope_handle = scope["handle"].as_str().unwrap();
    for (operation, expected) in [("writer_scope.enter", true), ("writer_scope.exit", false)] {
        assert_eq!(
            bridge
                .call(
                    operation,
                    vec![Value::Null],
                    json!({"handles":{"0":scope_handle}})
                )
                .unwrap()["ok"],
            true
        );
        assert_eq!(
            bridge.call("after_run", vec![], json!({})).unwrap()["result"],
            expected
        );
    }
    let error = bridge.call("on_job_event", vec![], json!({})).unwrap();
    assert_eq!(error["ok"], false);
    assert_eq!(error["error"]["type"], "ValueError");
    assert_eq!(
        bridge.call("after_run", vec![], json!({})).unwrap()["ok"],
        true
    );
}

#[test]
fn frame_limit_includes_newline_delimiter() {
    let fixture = Fixture::new(
        "import json\nh={'version':'mir-executor.local@1','hooks':[],'register_execute_options':False,'padding':''}\ns=json.dumps(h,separators=(',',':'))\nh['padding']='x'*(1048576-len(s))\nprint(json.dumps(h,separators=(',',':')),flush=True)\n",
    );
    assert!(matches!(
        LocalBridge::start(fixture.config()),
        Err(BridgeError::FrameTooLarge)
    ));
}

#[test]
#[cfg(unix)]
fn drop_kills_and_reaps_direct_child() {
    let fixture = Fixture::new(&format!(
        "import os,pathlib\npathlib.Path('child-pid').write_text(str(os.getpid()))\n{HELLO}import time\ntime.sleep(30)\n"
    ));
    let bridge = LocalBridge::start(fixture.config()).unwrap().unwrap();
    let pid = fs::read_to_string(fixture.0.join("child-pid")).unwrap();
    drop(bridge);
    let status = std::process::Command::new(test_interpreter()).args(["-I", "-c", "import os,sys\ntry: os.kill(int(sys.argv[1]),0)\nexcept ProcessLookupError: sys.exit(0)\nsys.exit(1)", &pid]).status().unwrap();
    assert!(status.success());
}
