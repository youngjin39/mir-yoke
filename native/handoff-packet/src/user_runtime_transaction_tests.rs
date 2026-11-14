use super::*;
use crate::user_runtime_install::{RECEIPT_NAME, capture_home_identity, sha256_bytes};
use serde_json::{Value as J, json};
use std::{
    fs,
    os::unix::fs::{PermissionsExt, symlink},
    path::PathBuf,
};

#[test]
#[rustfmt::skip]
fn frozen_syscall_transactions() {
    let corpus:J=serde_json::from_str(include_str!("../../../tests/fixtures/user_runtime_install/transaction-fixes.json")).unwrap();
    for (name, record) in corpus["records"].as_object().unwrap() {
        if name=="ordering" {continue;}
        if name=="fsync-errno" {
            use std::io::Write;
            let file=tempfile::NamedTempFile::new().unwrap();
            let error=fs::File::open(file.path()).unwrap().write_all(b"x").unwrap_err();
            assert_eq!(error.raw_os_error(),Some(libc::EBADF));
            let error=io_context(None,error);
            assert_eq!(json!({"class":error.class,"message":error.message}),*record);continue;
        }
        let tmp=tempfile::tempdir().unwrap();let root=tmp.path().canonicalize().unwrap();
        let mut plans=plans(&root,false);
        for p in &mut plans {p.receipt=b"receipt".to_vec();for file in [&p.files[0].target_relative,&p.stale[0].target_relative,&PathBuf::from(RECEIPT_NAME)] {fs::write(p.identity.path.join(file),b"old").unwrap();}p.stale[0].sha256=sha256_bytes(b"old");}
        let mut trace=vec![];let mut changed=false;let operation=record["operation"].as_str().unwrap();let home=record["home"].as_u64().unwrap() as usize;
        let result=transaction_with(&plans,|op,i,_| {
            trace.push(format!("{op}:{i}"));
            if op==operation && i==home && !changed {changed=true;let target=plans[i].identity.path.join(if op=="snapshot" {"agents/a.md"} else if op=="receipt" {""} else {"agents"});fs::set_permissions(target,fs::Permissions::from_mode(if op=="snapshot" {0} else {0o555})).unwrap();}
            if operation=="restore" && op=="receipt" && i==home {return Err(Error {class:"OSError",message:"injected".into()});}Ok(())
        });
        let mut error=result.unwrap_err();
        // Normalize only the random basename, keeping the syscall directory.
        while let Some(start)=error.message.find(".mir-install-") {let end=start+error.message[start..].find(char::from(39)).unwrap();error.message.replace_range(start..end,".temporary");}
        let mut rows=vec![];
        fn walk(home:usize, base:&Path, path:&Path, rows:&mut Vec<J>) {let mut entries:Vec<_>=fs::read_dir(path).unwrap().map(|e|e.unwrap().path()).collect();entries.sort();for p in entries {let m=fs::metadata(&p).unwrap();let mode=m.permissions().mode()&0o777;if mode==0 {fs::set_permissions(&p,fs::Permissions::from_mode(0o600)).unwrap();}let hex=|b:&[u8]|b.iter().map(|b|format!("{b:02x}")).collect::<String>();rows.push(json!([home,hex(p.strip_prefix(base).unwrap().as_os_str().as_encoded_bytes()),mode,if m.is_dir(){None}else{Some(hex(&fs::read(&p).unwrap()))}]));if m.is_dir(){walk(home,base,&p,rows);}}}
        for (i,p) in plans.iter().enumerate(){walk(i,&p.identity.path,&p.identity.path,&mut rows);}
        let home_modes:Vec<_>=plans.iter().map(|p|fs::metadata(&p.identity.path).unwrap().permissions().mode()&0o777).collect();
        let actual=json!({"home_modes":home_modes,"trace":trace,"error":{"class":error.class,"message":error.message.replace(root.to_str().unwrap(),"{ROOT}")},"tree":rows});
        for p in &plans {for dir in [&p.identity.path,&p.identity.path.join("agents")] {fs::set_permissions(dir,fs::Permissions::from_mode(0o755)).unwrap();}}
        assert_eq!(actual,json!({"home_modes":record["home_modes"],"trace":record["trace"],"error":record["error"],"tree":record["tree"]}),"{name}");
    }
}

#[test]
#[rustfmt::skip]
fn frozen_surrogate_restore_order() {
    use std::os::unix::ffi::OsStringExt;
    let corpus:J=serde_json::from_str(include_str!("../../../tests/fixtures/user_runtime_install/transaction-fixes.json")).unwrap();let record=&corpus["records"]["ordering"];
    let tmp=tempfile::tempdir().unwrap();let root=tmp.path().canonicalize().unwrap();let mut plans=plans(&root,false);let plan=&mut plans[0];
    fs::write(plan.identity.path.join(RECEIPT_NAME),b"old").unwrap();
    let surrogate=PathBuf::from(std::ffi::OsString::from_vec(b"agents/\xff.md".to_vec()));let unicode=PathBuf::from("agents/\u{e000}.md");fs::write(plan.identity.path.join(&unicode),b"foreign").unwrap();
    let desired=BTreeMap::from([(surrogate,Some(b"new".to_vec())),(unicode,Some(b"new".to_vec())),(RECEIPT_NAME.into(),Some(b"receipt".to_vec()))]);
    let snapshots:Vec<_>=ordered_desired(desired).into_iter().map(|(relative,after)|Snapshot {relative,before:Some(b"old".to_vec()),after}).collect();let mut restored=vec![];let mut error=None;
    for snap in snapshots.iter().rev() {restored.push(crate::executor_text::os_text(snap.relative.as_os_str()));if let Err(e)=restore(plan,snap){error=Some(sync(format!("apply failed; rollback incomplete: injected; {e}")));break;}}
    let hex=|bytes:&[u8]|bytes.iter().map(|b|format!("{b:02x}")).collect::<String>();
    let order:Vec<_>=snapshots.iter().map(|s|hex(s.relative.as_os_str().as_encoded_bytes())).collect();
    let tree:serde_json::Map<String,J>=snapshots.iter().map(|s| {let bytes=if s.relative.as_os_str().as_encoded_bytes().contains(&255) {s.after.clone().unwrap()} else {fs::read(plan.identity.path.join(&s.relative)).unwrap()};(hex(s.relative.as_os_str().as_encoded_bytes()),json!(hex(&bytes)))}).collect();
    let e=error.unwrap();assert_eq!(json!({"restore_order":restored,"error":{"class":e.class,"message":e.message.replace(plan.identity.path.to_str().unwrap(),"{ROOT}")},"snapshot_order":order,"tree":tree}),*record);
}
#[rustfmt::skip]
fn plans(root: &Path, created: bool) -> Vec<RuntimePlan> {
    (0..2).map(|i| {
        let home=root.join(format!("homes/{i}")); fs::create_dir_all(&home).unwrap();
        if !created { for (relative,content) in [("agents/a.md",b"old".as_slice()),("agents/stale.md",b"stale"),(RECEIPT_NAME,b"old-receipt")] {
            let p=home.join(relative); fs::create_dir_all(p.parent().unwrap()).unwrap(); fs::write(&p,content).unwrap(); fs::set_permissions(p,fs::Permissions::from_mode(0o600)).unwrap();
        } }
        let text=||crate::python_json::Text::new(".claude/agents/a.md".chars().map(u32::from).collect());
        RuntimePlan {identity:capture_home_identity(&home).unwrap(),files:vec![ManagedFile {source_relative:text(),target_relative:"agents/a.md".into(),content:b"new".to_vec(),sha256:sha256_bytes(b"new")}],stale:if created {vec![]} else {vec![StaleFile {source_relative:text(),target_relative:"agents/stale.md".into(),sha256:sha256_bytes(b"stale")}]},receipt:b"new-receipt".to_vec(),created_home:created}
    }).collect()
}
#[rustfmt::skip]
fn tree(root: &Path) -> J {
    fn walk(root:&Path, dir:&Path, files:&mut serde_json::Map<String,J>, base:&Path) {
        for entry in fs::read_dir(dir).unwrap() { let p=entry.unwrap().path(); let m=fs::symlink_metadata(&p).unwrap();
            let (kind,bytes)=if m.is_symlink() {("symlink",fs::read_link(&p).unwrap().to_str().unwrap().replace(base.to_str().unwrap(),"{ROOT}").into_bytes())} else if m.is_dir() {walk(root,&p,files,base);("directory",vec![])} else {assert!(m.is_file(),"unexpected entry {}",p.display());("file",fs::read(&p).unwrap())};
            files.insert(p.strip_prefix(root).unwrap().to_str().unwrap().into(),json!({"hex":bytes.iter().map(|b|format!("{b:02x}")).collect::<String>(),"mode":m.permissions().mode()&0o777,"kind":kind}));
        }
    }
    let mut homes=serde_json::Map::new(); for i in 0..2 {let home=root.join(format!("homes/{i}")); let mut files=serde_json::Map::new();if home.exists(){walk(&home,&home,&mut files,root);} homes.insert(i.to_string(),json!({"exists":home.exists(),"home_mode":fs::symlink_metadata(&home).ok().map(|m|m.permissions().mode()&0o777),"files":files}));} json!(homes)
}
#[rustfmt::skip]
fn replay(root:&Path, plans:&[RuntimePlan], record:&J, retry:bool) -> J {
    let mut trace=vec![]; let mut edited=false;
    let result=transaction_with(plans,|op,i,_| {
        let event=format!("{op}:{i}");trace.push(event.clone());
        if !retry && record["foreign_edit"]==true && op=="restore" && i==0 && !edited {fs::write(root.join("homes/0/agents/a.md"),b"foreign").unwrap();edited=true;}
        if !retry && op=="cleanup" && i==0 && let Some(change)=record["cleanup_change"].as_str() {
            let agents=root.join("homes/0/agents");if change=="nonempty" {fs::write(agents.join("foreign"),b"foreign").unwrap();} else {fs::remove_dir(&agents).unwrap();if change=="file" {fs::write(&agents,b"foreign").unwrap();fs::set_permissions(&agents,fs::Permissions::from_mode(0o644)).unwrap();} else {let outside=root.join("outside");fs::create_dir(&outside).unwrap();symlink(outside,&agents).unwrap();}}
        }
        if !retry && record["failures"].as_array().unwrap().iter().any(|f|f.as_str()==Some(&event)) {return Err(Error {class:if record["interrupt"]==true {"KeyboardInterrupt"} else {"OSError"},message:"injected".into()});} Ok(())
    });
    if record["cleanup_change"]=="symlink" {assert!(fs::symlink_metadata(root.join("homes/0/agents")).unwrap().is_symlink());}
    let error=result.err().map(|e|json!({"class":e.class,"message":e.message.replace(root.to_str().unwrap(),"{ROOT}")}));json!({"trace":trace,"error":error,"tree":tree(root)})
}
#[test]
#[rustfmt::skip]
fn frozen_transactions() {
    // Environment-only expectations derived from pinned Python's os errno and lstat; frozen records stay unchanged.
    fn platform(v:&mut J) {match v {J::Object(m)=>{if cfg!(target_os="linux") && m.get("kind")==Some(&json!("symlink")) {m.insert("mode".into(),json!(0o777));} for v in m.values_mut() {platform(v);}},J::Array(a)=>{for v in a {platform(v);}},J::String(s) if !cfg!(target_os="macos") =>{*s=s.replace("[Errno 66] Directory not empty",&format!("[Errno {}] Directory not empty",libc::ENOTEMPTY));},_=>()}}
    let mut corpus:J=serde_json::from_str(include_str!("../../../tests/fixtures/user_runtime_install/transactions.json")).unwrap(); platform(&mut corpus); let mut count=0;
    for (name,record) in corpus["records"].as_object().unwrap() {
        let tmp=tempfile::tempdir().unwrap();let root=tmp.path().canonicalize().unwrap();let plans=plans(&root,record["created_home"].as_bool().unwrap());
        let actual=replay(&root,&plans,record,false); let expected=json!({"trace":record["trace"],"error":record["error"],"tree":record["tree"]});assert_eq!(actual,expected,"{name}");
        if let Some(retry)=record.get("retry_result") {assert_eq!(&replay(&root,&plans,record,true),retry,"{name} retry");} count+=1;
    }
    assert_eq!(count,28);
}
#[test]
#[rustfmt::skip]
fn transaction_swapped_home_stays_contained() {
    for phase in ["payload","restore","cleanup"] {
        let tmp=tempfile::tempdir().unwrap();let root=tmp.path().canonicalize().unwrap();let plans=plans(&root,phase=="cleanup"); let outside=root.join("outside");fs::create_dir_all(outside.join("agents")).unwrap();
        for p in ["agents/a.md","agents/stale.md",RECEIPT_NAME] {fs::write(outside.join(p),b"foreign").unwrap();}
        let before:Vec<_>=["agents/a.md","agents/stale.md",RECEIPT_NAME].iter().map(|p|(PathBuf::from(p),fs::read(outside.join(p)).unwrap())).collect();let mut swapped=false;
        let result=transaction_with(&plans,|op,i,_| {
            if op==phase && i==0 && !swapped {fs::rename(root.join("homes/0"),root.join("moved")).unwrap();symlink(&outside,root.join("homes/0")).unwrap();swapped=true;}
            if phase!="payload" && op=="payload" && i==1 {return Err(Error {class:"OSError",message:"injected".into()});} Ok(())
        });
        assert!(swapped,"{phase} hook absent");assert!(result.is_err(),"{phase} accepted changed home");assert!(fs::symlink_metadata(root.join("homes/0")).unwrap().is_symlink(),"{phase} removed foreign link");
        for (p,bytes) in before {assert_eq!(fs::read(outside.join(p)).unwrap(),bytes,"{phase} escaped root");}
    }
}

#[test]
fn rename_error_surrogate_destination() {
    use std::{ffi::OsString, os::unix::ffi::OsStringExt};
    // Derived from Python OSError.filename/filename2 representation at
    // 0754c36 scripts/install_user_runtime_agents.py:380 (os.replace).
    // Model ENOENT: macOS refuses surrogateescaped basenames on disk.
    for home in 0..2 {
        let source = PathBuf::from(format!("homes/{home}/agents/.temporary"));
        let target = PathBuf::from(OsString::from_vec(
            format!("homes/{home}/agents/")
                .into_bytes()
                .into_iter()
                .chain(b"\xff.md".iter().copied())
                .collect(),
        ));
        let error = rename_error(
            &source,
            &target,
            std::io::Error::from_raw_os_error(libc::ENOENT),
        );
        assert_eq!(error.class, "FileNotFoundError");
        assert_eq!(
            error.message,
            format!(
                "[Errno 2] No such file or directory: 'homes/{home}/agents/.temporary' -> 'homes/{home}/agents/\\udcff.md'"
            )
        );
    }
}
