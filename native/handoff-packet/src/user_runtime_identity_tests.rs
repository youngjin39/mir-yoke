use super::*;
use serde_json::{Value as J, json};
use std::os::unix::fs::symlink;
#[test]
fn safe_home_double_anchor_failure_keeps_original_spelling() {
    let tmp = tempfile::tempdir().unwrap();
    let root = tmp.path().canonicalize().unwrap();
    let regular = root.join("regular-file");
    fs::write(&regular, b"file").unwrap();
    let input = PathBuf::from(format!("/{}/child", regular.display()));
    let error = require_safe_home(&input).unwrap_err();
    assert_eq!(error.class, "SyncError");
    assert_eq!(
        error.message,
        format!(
            "target path component is not a directory: /{}",
            regular.display()
        )
    );
}
#[test]
#[rustfmt::skip]
fn frozen_identity() {
    let corpus: J=serde_json::from_str(include_str!("../../../tests/fixtures/user_runtime_install/admission-receipts.json")).unwrap();
    let tmp=tempfile::tempdir().unwrap(); let canonical_root=tmp.path().canonicalize().unwrap(); let root=canonical_root.as_path(); let mut seen=BTreeSet::new();
    let mut check=|name:String,result:Result<J,Error>| {
        let actual=match result {
            Ok(value)=>json!({"value":value,"stdout":"","stderr":""}),
            Err(e)=>json!({"error":e.class,"message":e.message.replace(root.to_str().unwrap(),"{ROOT}"),"stdout":"","stderr":""}),
        };
        assert_eq!(actual,corpus["records"][&name],"{name}"); seen.insert(name);
    };
    let home=root.join("identity"); fs::create_dir_all(home.join("nested")).unwrap();
    fs::create_dir(root.join("identity-other")).unwrap(); fs::write(root.join("regular"),b"old").unwrap(); symlink(&home,root.join("identity-link")).unwrap();
    for name in ["identity","missing","regular","identity-link","identity-link/nested","null\0"] {
        check(format!("identity-capture-{}",name.replace('\0',"null")),capture_home_identity(&root.join(name)).map(|id| {
            let m=fs::symlink_metadata(&id.path).unwrap(); json!([id.path.to_str().unwrap().replace(root.to_str().unwrap(),"{ROOT}"),id.canonical_path.to_str().unwrap().replace(root.to_str().unwrap(),"{ROOT}"),id.object==adoption_fs::directory_identity(&id.path).unwrap(),m.is_dir()])
        }));
    }
    for (name,path) in [("double",PathBuf::from(format!("/{}",home.display()))),("relative",PathBuf::from("."))] {
        check(format!("identity-capture-{name}"),capture_home_identity(&path).map(|_|json!(null)));
    }
    use std::os::unix::ffi::OsStringExt;
    let bad=root.join(std::ffi::OsString::from_vec(b"bad-\xff".to_vec()));
    let wire=|result:Result<J,Error>| { let e=result.unwrap_err(); Ok(json!({"error":e.class,"message":e.message.replace(root.to_str().unwrap(),"{ROOT}")})) };
    check("identity-bytes-missing".into(),wire(capture_home_identity(&bad).map(|_|json!(null))));
    let bad_identity=HomeIdentity {path:bad.clone(),canonical_path:bad,object:adoption_fs::directory_identity(root).unwrap()};
    check("identity-bytes-changed".into(),wire(verified_target(&bad_identity,Path::new("new.md")).map(|p|json!(p))));
    let identity=capture_home_identity(&home).unwrap();
    for name in ["identity","identity/nested","identity-other"] {
        let other=capture_home_identity(&root.join(name)).unwrap();
        check(format!("identity-overlap-{name}"),Ok(json!(runtime_homes_overlap(&identity,&other))));
        check(format!("identity-overlap-reverse-{name}"),Ok(json!(runtime_homes_overlap(&other,&identity))));
    }
    for relative in ["agents/new.md",".","../regular"] {
        check(format!("identity-verified-{relative}"),verified_target(&identity,Path::new(relative)).map(|p|json!(p.to_str().unwrap().replace(root.to_str().unwrap(),"{ROOT}"))));
    }
    fs::rename(&home,root.join("identity-moved")).unwrap();
    check("identity-verified-missing".into(),verified_target(&identity,Path::new("new.md")).map(|p|json!(p)));
    fs::create_dir(&home).unwrap();
    check("identity-verified-replaced".into(),verified_target(&identity,Path::new("new.md")).map(|p|json!(p)));
    fs::remove_dir(&home).unwrap(); symlink(root.join("identity-moved"),&home).unwrap();
    check("identity-verified-symlink".into(),verified_target(&identity,Path::new("new.md")).map(|p|json!(p)));
    assert_eq!(seen.len(),corpus["records"].as_object().unwrap().keys().filter(|s|s.starts_with("identity-")).count());
}
