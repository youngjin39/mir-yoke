use handoff_packet::mir_cli::context::{profile_context_lines, profile_search_scopes};
use handoff_packet::mir_core::context::profile_task_context::*;
use serde_json::{Value, json};
use std::{fs, path::Path, process::Command};
const PROFILE: &str = concat!(
    "[repo]\nslug = \"sample\"\nrepository_type = \"library\"\n",
    "purpose = \"  small   project  \"\ntechnology_stack = [\"Rust\", \"Python\", \"\"]\n",
    "[paths]\narchitecture_refs = [\"design.md\", \"design.md\", \"../escape\", \"/invalid\"]\n",
    "configuration_paths = [\"config.toml\"]\nverification_paths = [\"tests\"]\n",
    "workflow_refs = [\"workflow.md\"]\nexception_refs = [\"risk.md\"]\n",
    "code_paths = [\"src\", \"bad/../path\"]\nnon_code_paths = [\"docs\"]\n",
    "protected_paths = [\"src/private\"]\ngenerated_paths = [\"src/generated\"]\n[preserve]\n",
    "agent_memory_paths = [\"keep\"]\nextra_docs = [\"docs/keep.md\"]\nempty = []\n",
    "false = false\n[boundaries]\nlive_runtime = [\"runtime\"]\nsecrets = [\"secret\"]\n",
    "external = \"none\"\n[gates]\nz = true\na = true\nnumeric = 1\nno = false\n",
);
const FLOAT_PROFILE: &str = "[preserve]\nnan = nan\npinf = inf\nninf = -inf\nbig = 1e100\n\
tenth = 0.1\nnested = {x = nan, y = [-inf, 2.5]}\n";
const ORDER_PROFILE: &str = concat!(
    "[preserve]\nzeta = [\"z\"]\nalpha = [\"a\"]\nzero_float = 0.0\nflag = true\nmid = 1.5\n",
    "[boundaries]\nzz = \"first\"\nsecrets = [\"s\"]\naa = \"x\"\nlive_runtime = [\"r\"]\n",
    "nested = {b = 1, a = 2}\n[gates]\nzz = true\naa = true\n",
);
fn setup(root: &Path, body: &str) {
    fs::create_dir(root.join(".mir")).unwrap();
    fs::write(root.join(".mir/repo-profile.toml"), body).unwrap();
    for name in "design.md config.toml workflow.md risk.md src/a.py".split_whitespace() {
        let path = root.join(name);
        fs::create_dir_all(path.parent().unwrap()).unwrap();
        fs::write(path, "reference\n").unwrap();
    }
    for name in ["tests", "docs"] {
        fs::create_dir(root.join(name)).unwrap();
    }
}
fn git(root: &Path, args: &[&str]) -> String {
    let mut cmd = Command::new("git");
    for (key, _) in std::env::vars().filter(|(k, _)| k.starts_with("GIT_")) {
        cmd.env_remove(key);
    }
    let null = if cfg!(windows) { "NUL" } else { "/dev/null" };
    cmd.envs([
        ("GIT_CONFIG_NOSYSTEM", "1"),
        ("GIT_CONFIG_GLOBAL", null),
        ("GIT_AUTHOR_NAME", "Fixture"),
        ("GIT_COMMITTER_NAME", "Fixture"),
        ("GIT_AUTHOR_EMAIL", "fixture@example.invalid"),
        ("GIT_COMMITTER_EMAIL", "fixture@example.invalid"),
        ("GIT_AUTHOR_DATE", "2000-01-01T00:00:00+0000"),
        ("GIT_COMMITTER_DATE", "2000-01-01T00:00:00+0000"),
        ("LC_ALL", "C"),
    ]);
    let out = cmd.args(args).current_dir(root).output().unwrap();
    let stderr = String::from_utf8_lossy(&out.stderr);
    assert!(out.status.success(), "{args:?}: {stderr}");
    String::from_utf8(out.stdout).unwrap().trim().into()
}
fn bundle(c: ProfileTaskContext) -> Value {
    json!([
        c.to_value(),
        profile_context_lines(&c),
        profile_search_scopes(&c.to_value())
    ])
}
#[test]
fn git_text_uses_python_universal_newlines() {
    let dir = tempfile::tempdir().unwrap();
    git(dir.path(), &["init", "-b", "fixture"]);
    git(dir.path(), &["config", "fixture.text", "a\r\nb\rc"]);
    assert_eq!(
        git_output(dir.path(), &["config", "--get", "fixture.text"]).unwrap(),
        (0, "a\nb\nc".into())
    );
}
fn profile(root: &Path, body: Option<&str>, query: &str, targets: &[&str], risk: &str) -> Value {
    if let Some(body) = body {
        setup(root, body);
    }
    match build_profile_task_context(root, query, targets, risk) {
        Ok(c) => json!({"value":bundle(c)}),
        Err(e) => json!({"error":["ValueError",e.to_string()]}),
    }
}
fn snapshot(root: &Path, mode: &str) -> Value {
    setup(root, "");
    git(root, &["init", "-b", "fixture"]);
    if mode == "unborn" {
        return freshness(root, "", &["src"]).unwrap();
    }
    git(root, &["add", "."]);
    git(root, &["commit", "-m", "baseline"]);
    let mut base = git(root, &["rev-parse", "HEAD"]);
    if ["advanced", "selected_commit"].contains(&mode) {
        let next = if mode == "selected_commit" {
            "src/a.py"
        } else {
            "other"
        };
        fs::write(root.join(next), "next").unwrap();
        git(root, &["add", "."]);
        git(root, &["commit", "-m", "advance"]);
    }
    if mode == "dirty" {
        fs::write(root.join("src/a.py"), "unstaged").unwrap();
        fs::write(root.join("src/staged"), "staged").unwrap();
        git(root, &["add", "src/staged"]);
        for i in 0..55 {
            fs::write(root.join(format!("src/untracked-{i:02}")), "new").unwrap();
        }
    }
    if mode == "diverged" {
        let tree = git(root, &["write-tree"]);
        base = git(root, &["commit-tree", &tree, "-m", "unrelated"]);
    }
    let baseline = match mode {
        "invalid" => "BAD".into(),
        "missing" => "0".repeat(40),
        _ => base,
    };
    fs::write(
        root.join(".mir/repo-profile.toml"),
        format!("[repo]\nprofile_base_commit = \"{baseline}\"\n[paths]\ncode_paths = [\"src\"]\n"),
    )
    .unwrap();
    let targets = if mode == "container" {
        &[][..]
    } else {
        &["src"][..]
    };
    let c = build_profile_task_context(root, "code", targets, "normal").unwrap();
    json!([
        git_output(root, &["branch", "--show-current"]).unwrap(),
        git_output(root, &["status", "--porcelain"]).unwrap(),
        git_paths(root, &["ls-files", "-z"]).unwrap(),
        changed_paths(root, &baseline).unwrap(),
        freshness(root, &baseline, &["src", "src"]).unwrap(),
        c.to_value(),
        profile_context_lines(&c),
        profile_search_scopes(&c.to_value())
    ])
}
fn symlink(root: &Path) {
    #[cfg(unix)]
    std::os::unix::fs::symlink(root.parent().unwrap(), root.join("escape")).unwrap();
    #[cfg(windows)]
    let _ = root; // The two symlink records are explicitly exempt on Windows.
}
fn replay(name: &str, root: &Path) -> Value {
    if let Some(mode) = name.strip_prefix("snapshot.") {
        return json!({"value":snapshot(root, mode)});
    }
    if let Some(query) = name.strip_prefix("query.") {
        return profile(root, Some(PROFILE), query, &[], "normal");
    }
    if let Some(target) = name.strip_prefix("target.") {
        return profile(root, Some(PROFILE), "", &[target, target], "normal");
    }
    if let Some(section) = name.strip_prefix("profile.without_") {
        let (before, after) = PROFILE.split_once(&format!("[{section}]")).unwrap();
        let rest = after
            .split_once('[')
            .map_or(String::new(), |(_, s)| format!("[{s}"));
        return profile(root, Some(&format!("{before}{rest}")), "", &[], "normal");
    }
    let basic = |body| profile(root, Some(body), "", &[], "normal");
    match name {
        "profile.key_order" => basic(ORDER_PROFILE),
        "profile.float_text" => {
            setup(root, FLOAT_PROFILE);
            let context = build_profile_task_context(root, "", &[], "normal").unwrap();
            json!({"value": profile_context_lines(&context)})
        }
        "profile.absent" => profile(root, None, "", &[], "normal"),
        "profile.empty" => basic(""),
        "profile.malformed" => basic("[repo"),
        "profile.unknown" => basic("[unknown]\nx = 1"),
        "profile.wrong_sections" => {
            basic("repo=1\npaths=[]\npreserve=\"x\"\nboundaries=0\ngates=false")
        }
        "profile.default" => basic(PROFILE),
        "profile.high" => profile(root, Some(PROFILE), "", &[], "high"),
        "profile.low" => profile(root, Some(PROFILE), "", &[], "low"),
        "profile.bad_risk" => profile(root, Some(PROFILE), "", &[], "critical"),
        "profile.targets" => {
            let targets =
                "src/private/a src/generated/a keep docs/keep.md runtime secret ../bad /bad";
            let targets = targets.split_whitespace().collect::<Vec<_>>();
            profile(root, Some(PROFILE), "", &targets, "normal")
        }
        "profile.long" => basic(&PROFILE.replace("small   project", &"x".repeat(4000))),
        "profile.many_refs" => {
            let refs = json!((0..60).map(|i| format!("file-{i:02}")).collect::<Vec<_>>());
            basic(&format!("[paths]\narchitecture_refs={refs}"))
        }
        "profile.unsafe" => {
            setup(root, "[paths]\narchitecture_refs=[\"escape\"]");
            symlink(root);
            json!({"value":bundle(build_profile_task_context(root,"docs",&[],"normal").unwrap())})
        }
        "helpers.strings" => {
            let inputs = json!([null, "x", [], [" x ", "", " ", 2, false, "a"]]);
            let values: Vec<_> = inputs.as_array().unwrap().iter().map(string_list).collect();
            json!({"value": values})
        }
        "helpers.normalise" => {
            let paths = ["", " ", "././a\\b", "../x", "/a", "a/../b", ".", "a//b"];
            json!({"value": paths.map(normalise_repo_path)})
        }
        "helpers.matches" => {
            let pairs = json!([
                ["src", "src/a"],
                ["src/a", "src"],
                ["a", "ab"],
                ["src/*.py", "src/x.txt"],
                ["x?.py", "xa.py"],
                ["x[ab]", "xc"],
                ["../x", "x"],
                ["a", "/a"]
            ]);
            let results = pairs
                .as_array()
                .unwrap()
                .iter()
                .map(|pair| {
                    let (a, b) = (pair[0].as_str().unwrap(), pair[1].as_str().unwrap());
                    json!([a, b, path_matches(a, b).unwrap()])
                })
                .collect::<Vec<_>>();
            json!({"value": results})
        }
        "helpers.query" => json!({"value": query_terms("CODE a x_y test-42 \u{c9}cole").unwrap()}),
        "helpers.query_ref" => {
            let cases = [
                (&["ab"][..], "code", "ab"),
                (&["fig"][..], "configuration", "x"),
                (&[][..], "code", "src"),
                (&["src"][..], "code", "SRC/a"),
            ];
            let matches = cases.map(|(terms, kind, path)| {
                query_matches_ref(&terms.iter().map(|s| s.to_string()).collect(), kind, path)
            });
            json!({"value": matches})
        }
        "helpers.states" => {
            let root = root.join("root");
            fs::create_dir(&root).unwrap();
            setup(&root, "");
            symlink(&root);
            let mut states = json!({});
            for p in "design.md docs missing *.md nothing* escape escape/* ../".split_whitespace() {
                states[p] = json!(reference_state(&root, p).unwrap());
            }
            json!({"value":states})
        }
        "helpers.git_outside" => json!({"value": [
            git_output(root, &["rev-parse", "HEAD"]).unwrap(),
            git_paths(root, &["ls-files", "-z"]).unwrap(),
            changed_paths(root, "bad").unwrap(), freshness(root, "", &[]).unwrap()
        ]}),
        "helpers.invalid" => {
            json!({"value": empty_invalid_context("q", "high", "warning").to_value()})
        }
        "header.scopes" => {
            let context = json!({
                "task": {"target_paths": ["a", "a"]},
                "selected_refs": [
                    null, {}, {"path": 1}, {"path": ""},
                    {"path": "src", "kind": "code_scope"},
                    {"path": "doc", "kind": "non_code_scope"}, {"path": "a"}, {"path": "b"}
                ]
            });
            json!({"value": profile_search_scopes(&context)})
        }
        _ => panic!("unhandled record {name}"),
    }
}
#[test]
fn frozen_records() {
    let records: Value =
        serde_json::from_str(include_str!("fixtures/w2/b08-task-context.json")).unwrap();
    let (mut replayed, mut exempt) = (0, 0);
    for (name, expected) in records.as_object().unwrap() {
        if cfg!(windows) && ["helpers.states", "profile.unsafe"].contains(&name.as_str()) {
            exempt += 1;
            eprintln!("{name}: exempt: directory symlinks require Windows privileges");
            continue;
        }
        let tmp = tempfile::tempdir().unwrap();
        let root = tmp.path().canonicalize().unwrap();
        let actual = replay(name, &root);
        let encoded = json!(root.to_str().unwrap()).to_string();
        let text = actual
            .to_string()
            .replace(&encoded[1..encoded.len() - 1], "<tmp>");
        let actual: Value = serde_json::from_str(&text).unwrap();
        assert_eq!(actual, *expected, "{name}");
        replayed += 1;
        eprintln!("{name}: replayed");
    }
    assert_eq!(
        (replayed, exempt),
        if cfg!(windows) { (51, 2) } else { (53, 0) }
    );
    assert_eq!(replayed + exempt, 53);
}
