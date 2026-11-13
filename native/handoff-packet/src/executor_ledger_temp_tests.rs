use super::*;

fn names(values: &[&str]) {
    LEDGER_TEMP_NAMES.with(|names| {
        *names.borrow_mut() = values.iter().rev().map(OsString::from).collect();
    });
}

fn reference() -> Value {
    serde_json::from_str(include_str!(
        "../tests/fixtures/executor_ledger_temp_reference.json"
    ))
    .unwrap()
}

#[test]
fn ledger_temp_collision_retries_without_removing_existing_file() {
    let root = tempfile::tempdir().unwrap();
    let ledger = root.path().join("tdd.json");
    fs::write(&ledger, "original").unwrap();
    let collision = root.path().join(".mir-executor-reviewcollision.tmp");
    fs::write(&collision, "collision-owner").unwrap();
    names(&[
        ".mir-executor-reviewcollision.tmp",
        ".mir-executor-aftercollision.tmp",
    ]);
    let result = write_ledger(&ledger, "updated");
    assert_eq!(fs::read_to_string(&collision).unwrap(), "collision-owner");
    result.unwrap();
    assert_eq!(fs::read_to_string(&ledger).unwrap(), "updated");
    assert_eq!(fs::read_dir(root.path()).unwrap().count(), 2);
    assert!(reference()["records"]["collision"]["error"].is_null());
}

#[test]
fn ledger_temp_exhaustion_preserves_every_candidate() {
    let root = tempfile::tempdir().unwrap();
    let ledger = root.path().join("tdd.json");
    fs::write(&ledger, "original").unwrap();
    let candidates = ["one.tmp", "two.tmp", "three.tmp"];
    for name in candidates {
        fs::write(root.path().join(name), name).unwrap();
    }
    names(&candidates);
    let reference = reference();
    assert_eq!(reference["test_retry_bound"], candidates.len());
    LEDGER_TEMP_LIMIT.with(|limit| limit.set(Some(candidates.len())));
    let result = write_ledger(&ledger, "updated");
    LEDGER_TEMP_LIMIT.with(|limit| limit.set(None));
    for name in candidates {
        assert_eq!(fs::read_to_string(root.path().join(name)).unwrap(), name);
    }
    assert_eq!(
        result.unwrap_err(),
        reference["records"]["exhaustion"]["error"]
            .as_str()
            .unwrap()
    );
    assert!(LEDGER_TEMP_NAMES.with(|names| names.borrow().is_empty()));
    assert_eq!(fs::read_to_string(&ledger).unwrap(), "original");
}

#[test]
fn ledger_temp_cleanup_preserves_substituted_file() {
    let root = tempfile::tempdir().unwrap();
    let ledger = root.path().join("tdd.json");
    fs::write(&ledger, "original").unwrap();
    names(&["candidate.tmp"]);
    let parent = root.path().to_owned();
    BEFORE_LEDGER_REPLACE.with(|hook| {
        *hook.borrow_mut() = Some(Box::new(move || {
            fs::rename(parent.join("candidate.tmp"), parent.join("retained.tmp")).unwrap();
            fs::write(parent.join("candidate.tmp"), "other-owner").unwrap();
            fs::remove_file(parent.join("tdd.json")).unwrap();
            fs::create_dir(parent.join("tdd.json")).unwrap();
        }))
    });
    assert!(write_ledger(&ledger, "updated").is_err());
    assert_eq!(
        fs::read_to_string(root.path().join("candidate.tmp")).unwrap(),
        "other-owner"
    );
    assert_eq!(
        fs::read_to_string(root.path().join("retained.tmp")).unwrap(),
        "updated"
    );
}

#[test]
fn ledger_temp_failure_cleans_its_own_file() {
    let root = tempfile::tempdir().unwrap();
    let ledger = root.path().join("tdd.json");
    fs::create_dir(&ledger).unwrap();
    names(&["candidate.tmp"]);
    assert!(write_ledger(&ledger, "updated").is_err());
    assert!(!root.path().join("candidate.tmp").exists());
    assert!(ledger.is_dir());
}
