use super::*;
use serde_json::{Value as J, json};
use std::os::unix::fs::symlink;
fn hex(b: &[u8]) -> String {
    b.iter().map(|v| format!("{v:02x}")).collect()
}
#[test]
#[rustfmt::skip]
fn frozen_admission() {
    let corpus: J = serde_json::from_str(include_str!("../../../tests/fixtures/user_runtime_install/admission-receipts.json")).unwrap();
    let tmp = tempfile::tempdir().unwrap(); let root = tmp.path(); let mut seen = std::collections::BTreeSet::new(); let mut mismatches = Vec::new();
    let mut check = |name: &str, result: Result<J, Error>| {
        let actual = match result {
            Ok(v) => json!({"value":v,"stdout":"","stderr":""}),
            Err(e) => json!({"error":e.class,"message":e.message.replace(root.to_str().unwrap(),"{ROOT}"),"stdout":"","stderr":""}),
        };
        if actual != corpus["records"][name] { mismatches.push(format!("{name}: actual={actual}, expected={}",corpus["records"][name])); } seen.insert(name.to_owned());
    };
    for (i,p) in [".claude/agents/a.md",".claude/agents/../a.md",".claude/agents/..",".claude/agents//a.md",".claude/agents/./a.md","./.claude/agents/a.md","/.claude/agents/a.md",".claude/agents/nested/a.md",".claude/agents/a.md/",".claude/agents/한.md",".claude/agents/.md",".claude/agents/a.MD","",".claude/agents/../x.md",".claude/agents/..md"].iter().enumerate() {
        check(&format!("relative-{i}"),Ok(json!(is_safe_relative(p,".claude/agents/",if p.ends_with("/..") {""} else {".md"}))));
    }
    fs::write(root.join("regular"),b"source\0\xff\r\n").unwrap(); fs::create_dir(root.join("directory")).unwrap(); symlink(root.join("regular"),root.join("link")).unwrap();
    symlink(root.join("missing"),root.join("dangling")).unwrap(); assert!(std::process::Command::new("mkfifo").arg(root.join("fifo")).status().unwrap().success());
    for name in ["regular","missing","directory","link","dangling","fifo"] { check(&format!("source-{name}"),regular_source(root,&root.join(name)).map(|b|json!({"hex":hex(&b)}))); }
    check("source-null",regular_source(root,&root.join("null\0.md")).map(|b|json!({"hex":hex(&b)})));
    check("source-read-error", source_with(root,&root.join("regular"),|p|fs::symlink_metadata(p), |_| Err(std::io::Error::new(std::io::ErrorKind::PermissionDenied,"read denied"))).map(|_|json!(null)));
    check("source-stat-error", source_with(root,&root.join("regular"), |_| Err(std::io::Error::new(std::io::ErrorKind::PermissionDenied,"stat denied")),|p|fs::read(p)).map(|_|json!(null)));
    let home=root.join("home"); fs::create_dir_all(home.join("agents")).unwrap();
    symlink(home.join("agents"),home.join("link")).unwrap(); fs::write(home.join("file"),b"old").unwrap(); symlink(home.join("file"),home.join("agents/link")).unwrap();
    for (i,p) in [PathBuf::from("relative"),PathBuf::from("/"),PathBuf::from("//"),root.join("absent"),home.clone(),home.join("agents/../normalized"),home.join("link/nested"),home.join("file/nested"),home.join("..")].iter().enumerate() { check(&format!("home-{i}"),require_safe_home(p).map(|p|json!(p.to_str().unwrap().replace(root.to_str().unwrap(),"{ROOT}")))); }
    for p in ["agents/new.md","link/new.md","file/new.md","agents/link","agents","file","absent/new.md",".","agents/./new.md","agents//new.md","agents/new.md/"] { check(&format!("target-{p}"),safe_target(&home,Path::new(p)).map(|p|json!(p.to_str().unwrap().replace(root.to_str().unwrap(),"{ROOT}")))); }
    let long_name="x".repeat(256);
    check("home-long-name",require_safe_home(&home.join(&long_name)).map(|p|json!(p)));
    check("target-long-name",safe_target(&home,Path::new(&long_name)).map(|p|json!(p)));
    check("target-long-ancestor",safe_target(&home,&Path::new(&long_name).join("new.md")).map(|p|json!(p)));
    check("source-long-name",regular_source(root,&root.join(&long_name)).map(|b|json!({"hex":hex(&b)})));
    use std::os::unix::fs::PermissionsExt;
    let blocked=root.join("blocked");fs::create_dir(&blocked).unwrap();fs::set_permissions(&blocked,fs::Permissions::from_mode(0o000)).unwrap();
    check("home-permission",require_safe_home(&blocked.join("child")).map(|p|json!(p)));
    check("target-permission",safe_target(&blocked,Path::new("child")).map(|p|json!(p)));
    check("target-permission-ancestor",safe_target(&blocked,Path::new("child/new.md")).map(|p|json!(p)));
    check("source-permission",regular_source(root,&blocked.join("child")).map(|b|json!({"hex":hex(&b)})));
    fs::set_permissions(&blocked,fs::Permissions::from_mode(0o700)).unwrap();
    check("home-double-anchor",require_safe_home(Path::new(&format!("/{}",home.display()))).map(|p|json!(p.to_str().unwrap().replace(root.to_str().unwrap(),"{ROOT}"))));
    check("sources-allowlisted-surrogate",sources_from_bytes(Path::new("provider"),br#"{"agents":{"allowlist":[".claude/agents/\ud800.md"]},"commands":{"allowlist":{}},"profiles":{"packs":{"p":{"agents":[".claude/agents/\ud800.md"],"commands":[]}}}}"#).map(files_json));
    let low=sources_from_bytes(Path::new("provider"),br#"{"agents":{"allowlist":[".claude/agents/\udc80.md"]},"commands":{"allowlist":{}},"profiles":{"packs":{"p":{"agents":[".claude/agents/\udc80.md"],"commands":[]}}}}"#).unwrap_err(); check("sources-surrogateescape-stderr",Ok(json!({"error":low.class,"message":low.message})));
    let low=sources_from_bytes(Path::new("provider"),br#"{"agents":{"allowlist":[".claude/agents/\udcc3\udca9.md"]},"commands":{"allowlist":{}},"profiles":{"packs":{"p":{"agents":[".claude/agents/\udcc3\udca9.md"],"commands":[]}}}}"#).unwrap_err(); check("sources-surrogateescape-pair-stderr",Ok(json!({"error":low.class,"message":low.message})));
    let config_path=root.join("config/capability-sources.json");fs::create_dir(config_path.parent().unwrap()).unwrap();
    let empty=json!({"agents":{"allowlist":[]},"commands":{"allowlist":{}},"profiles":{"packs":{}}});
    let agent=".claude/agents/z.md";let command=".claude/commands/a.md"; let config=json!({"agents":{"allowlist":[agent]},"commands":{"allowlist":{command:{}}},"profiles":{"packs":{"p":{"agents":[agent,agent],"commands":[command]}}}});
    for (p,b) in [(agent,b"agent\r\n".as_slice()),(command,b"command\n"),(".codex/agents/z.toml",b"codex\n")] {
        fs::create_dir_all(root.join(p).parent().unwrap()).unwrap();fs::write(root.join(p),b).unwrap();
    }
    let mut cases=vec![("sources-empty",empty.to_string()),("sources-invalid-json","{".into()),("sources-invalid-keys","{}".into()),("sources-valid",config.to_string())];
    let mut v=empty.clone();v["agents"]["allowlist"]=json!({});cases.push(("sources-invalid-types",v.to_string()));
    let mut v=empty.clone();v["profiles"]["packs"]=json!({"bad":{}});cases.push(("sources-invalid-pack",v.to_string()));
    for (name,pack) in [("pack-type",json!([])),("agent-type",json!({"agents":[7],"commands":[]})),("agent-unlisted",json!({"agents":["unlisted"],"commands":[]})),("command-type",json!({"agents":[],"commands":[7]})),("command-unlisted",json!({"agents":[],"commands":["unlisted"]}))] {
        let mut v=config.clone();v["profiles"]["packs"]=json!({"p":pack});
        fs::write(&config_path,v.to_string()).unwrap(); check(&format!("sources-{name}"),load_sources(root).map(files_json));
    }
    for kind in ["agents","commands"] {
        let p=format!(".claude/{kind}/../bad.md");let mut v=empty.clone();v[kind]["allowlist"]=if kind=="agents" {json!([p])} else {json!({&p:{}})};
        v["profiles"]["packs"]=json!({"p":{"agents":if kind=="agents" {vec![&p]} else {vec![]},"commands":if kind=="commands" {vec![&p]} else {vec![]}}});
        fs::write(&config_path,v.to_string()).unwrap();check(&format!("sources-unsafe-{kind}"),load_sources(root).map(files_json));
    }
    for (name,text) in cases {fs::write(&config_path,text).unwrap();check(name,load_sources(root).map(files_json));}
    for (name,bytes) in malformed_configs() {fs::write(&config_path,bytes).unwrap();check(name,load_sources(root).map(files_json));}
    fs::write(&config_path,config.to_string()).unwrap();fs::remove_file(root.join(".codex/agents/z.toml")).unwrap();check("sources-missing-codex",load_sources(root).map(files_json));
    fs::remove_file(config_path).unwrap();check("sources-missing-config",load_sources(root).map(files_json)); check("hash-empty",Ok(json!(sha256_bytes(b""))));check("hash-binary",Ok(json!(sha256_bytes(&(0..=255).collect::<Vec<u8>>()))));
    assert!(mismatches.is_empty(), "{}", mismatches.join("\n"));
    for name in corpus["records"].as_object().unwrap().keys().filter(|s| !s.starts_with("cli-") && !s.starts_with("receipt-")) {assert!(seen.contains(name),"unreplayed {name}");}
}
fn files_json(files: (Vec<ManagedFile>, Vec<ManagedFile>)) -> J {
    let convert = |files: Vec<ManagedFile>| {
        files.into_iter().map(|f|json!({"source_relative":f.source_relative.as_str().unwrap(),"target_relative":f.target_relative,"content":{"hex":hex(&f.content)},"sha256":f.sha256})).collect::<Vec<_>>()
    };
    json!([convert(files.0), convert(files.1)])
}
fn malformed_configs() -> Vec<(&'static str, Vec<u8>)> {
    vec![("sources-pack-precedence",br#"{"agents":{"allowlist":[]},"commands":{"allowlist":{}},"profiles":{"packs":{"p":{"agents":[7]}}}}"#.to_vec()),("sources-top-list",b"[]".to_vec()),("sources-top-null",b"null".to_vec()),("sources-invalid-utf8",vec![255]),("sources-utf16",vec![255,254,123,0,125,0]),("sources-nan",b"NaN".to_vec()),("sources-surrogate",br#"{"agents":{"allowlist":[]},"commands":{"allowlist":{}},"profiles":{"packs":{"p":{"agents":["\ud800"],"commands":[]}}}}"#.to_vec())]
}
#[test]
#[rustfmt::skip]
fn frozen_receipts() {
    let corpus:J=serde_json::from_str(include_str!("../../../tests/fixtures/user_runtime_install/admission-receipts.json")).unwrap();
    let tmp=tempfile::tempdir().unwrap(); let root=tmp.path();
    let home=root.join("receipt-home"); fs::create_dir_all(home.join("agents")).unwrap();
    let file=|source:&str,target:&str,bytes:&[u8],sha:String| ManagedFile { source_relative:python_json::Text::new(source.chars().map(u32::from).collect()),target_relative:target.into(),content:bytes.to_vec(),sha256:sha };
    for (runtime,files) in [("claude",vec![file(".claude/agents/z.md","agents/z.md",b"agent\r\n",sha256_bytes(b"agent\r\n")),file(".claude/commands/a.md","commands/a.md",b"command\n",sha256_bytes(b"command\n"))]),("codex",vec![]),("unicode",vec![file(".claude/agents/한.md","agents/한.md",b"","0".repeat(64))])] {
        assert_eq!(json!({"value":{"hex":hex(&make_receipt(runtime,&"a".repeat(40),&files))},"stdout":"","stderr":""}),corpus["records"][format!("receipt-{runtime}")]);
    }
    let mut reversed=vec![file(".claude/commands/a.md","commands/a.md",b"command\n",sha256_bytes(b"command\n")),file(".claude/agents/z.md","agents/z.md",b"agent\r\n",sha256_bytes(b"agent\r\n"))];
    assert_eq!(hex(&make_receipt("claude",&"a".repeat(40),&reversed)),corpus["records"]["receipt-unsorted"]["value"]["hex"]);
    reversed=vec![file(".claude/agents/한😀.md","agents/한😀.md",b"","0".repeat(64))];
    assert_eq!(hex(&make_receipt("claude","\u{7f}😀",&reversed)),corpus["records"]["receipt-ascii"]["value"]["hex"]);
    let mut count=0;
    for (name,record) in corpus["records"].as_object().unwrap().iter().filter(|(k,_)|k.starts_with("receipt-case-")) {
        count+=1;let input=&record["input"]; let path=home.join(RECEIPT_NAME); let target=home.join("agents/z.md");
        for p in [&path,&target] { if p.exists() {fs::remove_file(p).unwrap();} }
        if !input["raw"].is_null() { let raw=&input["raw"]; let bytes=if let Some(s)=raw.as_str() {s.as_bytes().to_vec()} else {let s=raw["hex"].as_str().unwrap();(0..s.len()).step_by(2).map(|i|u8::from_str_radix(&s[i..i+2],16).unwrap()).collect()};fs::write(&path,bytes).unwrap(); }
        if let Some(disk)=input["disk"].as_str() {fs::write(&target,disk).unwrap();}
        let files=if input["selected"]==true {vec![file(".claude/agents/z.md","agents/z.md",b"agent\r\n",sha256_bytes(b"agent\r\n"))]} else {vec![]};
        let runtime=input["runtime"].as_str().unwrap();
        use std::os::unix::fs::PermissionsExt;
        let unreadable=if input["unreadable"]=="receipt" {&path} else {&target};
        if input.get("unreadable").is_some() {fs::set_permissions(unreadable,fs::Permissions::from_mode(0o0)).unwrap();}
        let result=if input["op"]=="load" {load_receipt(&home,runtime).map(|(p,r)|json!([p,r.is_some()]))} else {validate_targets(&home,runtime,&files).map(|(p,stale)|json!([p,stale.iter().map(|s|json!({"source_relative":s.source_relative.py_str(),"target_relative":s.target_relative,"sha256":s.sha256})).collect::<Vec<_>>()]))};
        if input.get("unreadable").is_some() {fs::set_permissions(unreadable,fs::Permissions::from_mode(0o600)).unwrap();}
        let actual=match result {Ok(v)=>json!({"value":v,"stdout":"","stderr":""}),Err(e)=>json!({"error":e.class,"message":e.message,"stdout":"","stderr":""})};
        let mut expected=record.clone();expected.as_object_mut().unwrap().remove("input");
        let actual:J=serde_json::from_str(&actual.to_string().replace(root.to_str().unwrap(),"{ROOT}")).unwrap();
        assert_eq!(actual,expected,"{name}");
    }
    assert_eq!(count,50);
}

#[test]
fn receipt_target_posix_separator() {
    use std::ffi::OsStr;
    let points = |s: &str| s.chars().map(u32::from).collect::<Vec<_>>();
    // Exercise Windows spelling even on Unix; Unix backslashes remain literal.
    assert_eq!(
        posix_path_points(OsStr::new(r"agents\한.md"), '\\'),
        points("agents/한.md")
    );
    assert_eq!(
        posix_path_points(OsStr::new(r"agents\한.md"), '/'),
        points(r"agents\한.md")
    );
    let target = Path::new("agents").join("z.md");
    let item = ManagedFile {
        source_relative: python_json::Text::new(points(".claude/agents/z.md")),
        target_relative: target,
        content: b"old".to_vec(),
        sha256: sha256_bytes(b"old"),
    };
    let receipt = make_receipt("claude", "commit", std::slice::from_ref(&item));
    let decoded: J = serde_json::from_slice(&receipt).unwrap();
    assert_eq!(
        decoded["files"][".claude/agents/z.md"]["target"],
        "agents/z.md"
    );
    let home = tempfile::tempdir().unwrap();
    fs::write(home.path().join(RECEIPT_NAME), receipt).unwrap();
    let target = home.path().join(&item.target_relative);
    fs::create_dir(target.parent().unwrap()).unwrap();
    fs::write(&target, b"old").unwrap();
    let (_, loaded) = load_receipt(home.path(), "claude").unwrap();
    assert!(receipt_allows_update(loaded.as_ref(), &item, &target).unwrap());
}
