"""Freeze TDD compatibility records from the pinned Python script, never native code."""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def main():
    scratch = Path(sys.argv[1])
    scratch.mkdir(parents=True, exist_ok=True)
    source = subprocess.check_output(
        ["git", "show", "abb0dd82:.claude/hooks/tdd-matrix-guard.py"]
    )
    oracle = scratch / "tdd-matrix-guard.py"
    oracle.write_bytes(source)
    records = []

    def capture(
        name, mode, ledger, target="src/a.py", changed="src/a.py\n", git_body=None,
        git_mode=0o755, args=None, missing_changed=False,
    ):
        with tempfile.TemporaryDirectory(dir=scratch) as temp:
            root = Path(temp).resolve()
            (root / "tasks").mkdir()
            setup = {}
            if ledger is not None:
                setup["tasks/tdd.json"] = ledger
            if not missing_changed:
                setup["changed"] = changed
            for name_in_root, body in setup.items():
                (root / name_in_root).write_text(body, encoding="utf-8")
            tools = root / "bin"
            tools.mkdir()
            git = tools / "git"
            git.write_text(git_body or "#!/bin/sh\nprintf '%s' '" + changed + "'\n")
            git.chmod(git_mode)
            env = dict(os.environ, HOME=str(scratch / "home"), TMPDIR=str(scratch),
                       PYTHONDONTWRITEBYTECODE="1", PATH=str(tools))
            arguments = args if args is not None else [
                mode, "@PROJECT@", "@PROJECT@/changed" if mode == "precommit" else target,
            ]
            before = {str(p.relative_to(root)): p.read_bytes()
                      for p in root.rglob("*") if p.is_file()}
            result = subprocess.run(
                [sys.executable, str(oracle),
                 *(a.replace("@PROJECT@", str(root)) for a in arguments)],
                cwd=root, env=env, capture_output=True,
                timeout=55,
            )
            error = result.stderr.decode("utf-8")
            oracle_stderr = error.replace(str(root), "@PROJECT@").replace(str(oracle), "@ORACLE@")
            # The native exception contract preserves the traceback's final line.
            if error.startswith("Traceback (most recent call last):"):
                error = error.splitlines()[-1] + "\n"
            after = {str(p.relative_to(root)): p.read_bytes()
                     for p in root.rglob("*") if p.is_file()}
            assert before == after, name
            records.append(dict(id=name, mode=mode, target=target, changed=changed,
                                args=arguments, oracle_stderr=oracle_stderr,
                                git_body=git_body, git_mode=git_mode,
                                setup=setup,
                                expected=dict(exit=result.returncode,
                                              stdout=result.stdout.decode("utf-8"),
                                              stderr=error.replace(str(root), "@PROJECT@"),
                                              delta={}, deleted=[])))

    def entry(**updates):
        result = dict(id="a", targets=["src/a.py"], categories={})
        result.update(updates)
        return result

    def document(change, **extra):
        return json.dumps(dict(changes=[change], **extra))

    for mode in ["prewrite", "precommit", "precommit-merge"]:
        capture(f"{mode}-missing-ledger", mode, None)
        capture(f"{mode}-valid", mode, document(entry()))
    capture("precommit-missing-input", "precommit", document(entry()), missing_changed=True)
    for label, args in [("no-args", []), ("only-mode", ["prewrite"]),
                        ("missing-target", ["prewrite", "@PROJECT@"]),
                        ("unknown-mode", ["unknown", "@PROJECT@", "src/a.py"])]:
        capture(label, "prewrite", document(entry()), args=args)

    for mode in ["prewrite", "precommit", "precommit-merge"]:
        for code in range(0x1c, 0x20):
            sep = chr(code)
            for field, status in [("reason", "not_applicable"), ("command", "pass")]:
                capture(f"{mode}-{field}-{code}", mode,
                        document(entry(categories={"unit": {"status": status, field: sep}})))
            capture(f"{mode}-target-strip-{code}", mode,
                    document(entry(targets=[sep + "src/a.py" + sep])))
        for label, value in [("nan", "NaN"), ("inf", "Infinity"), ("negative-inf", "-Infinity"),
                             ("overflow", "1e400"), ("surrogate", '"\\ud800"'),
                             ("deep", "[" * 140 + "0" + "]" * 140),
                             ("huge-int", "1" * 300)]:
            capture(f"{mode}-metadata-{label}", mode,
                    '{"changes":[],"metadata":' + value + "}")
        for label, value in [("null", None), ("list", []), ("object", {})]:
            capture(f"{mode}-status-{label}", mode,
                    document(entry(categories={"unit": {"status": value}})))
        for label, change in [("scalar-null", None), ("scalar-int", 4),
                              ("scalar-bool", True), ("scalar-string", "x"),
                              ("scalar-list", []),
                              ("targets-int", entry(targets=4)),
                              ("targets-null", entry(targets=None)),
                              ("target-element-int", entry(targets=[4])),
                              ("target-element-list", entry(targets=[[]])),
                              ("target-element-object", entry(targets=[{}])),
                              ("categories-null", entry(categories=None)),
                              ("categories-list", entry(categories=[])),
                              ("categories-int", entry(categories=4))]:
            capture(f"{mode}-{label}", mode, document(change))
        for label, text in [("malformed", '{"changes":[}'),
                            ("bom", '\ufeff{"changes":[]}'),
                            ("trailing", '{"changes":[]}x'),
                            ("invalid-escape", '{"changes":[],"metadata":"\\x"}')]:
            capture(f"{mode}-json-{label}", mode, text)
    for code in range(0x1c, 0x20):
        sep = chr(code)
        capture(f"prewrite-argument-strip-{code}", "prewrite", document(entry()),
                target=sep + "src/a.py" + sep)
        capture(f"precommit-command-strip-{code}", "precommit",
                document(entry(categories={
                    "unit": {"status": "pass", "command": sep + "test" + sep}
                })))
    for sep in ["\r", "\v", "\f", "\x1c", "\x1d", "\x1e", "\x85", "\u2028", "\u2029"]:
        capture(f"precommit-splitlines-{ord(sep)}", "precommit", document(entry()),
                changed="ignored.txt" + sep + "src/missing.py" + sep)
    for mode in ["prewrite", "precommit", "precommit-merge"]:
        for field, status in [("reason", "not_applicable"), ("command", "pass")]:
            capture(f"{mode}-{field}-surrogate", mode,
                    document(entry(categories={"unit": {"status": status, field: "\ud800"}})))
        for label, value in [("nan", float("nan")), ("inf", float("inf")),
                             ("huge-int", 10**299), ("surrogate", "\ud800")]:
            capture(f"{mode}-status-{label}", mode,
                    document(entry(categories={"unit": {"status": value}})))
        for label, targets in [("dict", {"src/a.py": 1}), ("string", "src/a.py")]:
            capture(f"{mode}-targets-{label}", mode, document(entry(targets=targets)))
        capture(f"{mode}-targets-surrogate", mode, document(entry(targets=["\ud800"])))
        for label, value in [("list", []), ("dict", {})]:
            capture(f"{mode}-top-status-{label}", mode,
                    document(entry(), legacy={"status": value}))
        for depth in [9995, 9996, 9997]:
            capture(f"{mode}-metadata-depth-{depth}", mode,
                    '{"changes":[],"metadata":' + '[' * depth + '0' + ']' * depth + '}')
    capture("precommit-merge-git-permission", "precommit-merge", document(entry()), git_mode=0o644)
    capture("precommit-merge-git-invalid-stdout", "precommit-merge", document(entry()),
            git_body="#!/bin/sh\nprintf '\\377'\n")
    capture("precommit-merge-git-invalid-stderr", "precommit-merge", document(entry()),
            git_body="#!/bin/sh\nprintf '\\377' >&2\n")
    capture("precommit-merge-git-timeout", "precommit-merge", document(entry()),
            git_body='#!/bin/sh\nif [ "$3" = "@{upstream}..HEAD" ]; then exec /bin/sleep 11; fi\n'
                     'printf "src/a.py\\n"\n')
    for label, status in [("format", "\u200b"), ("soft-hyphen", "\u00ad"),
                          ("private", "\ue000"), ("unassigned", "\u0378"),
                          ("mixed-surrogate", "\ud800\u200b\ue000")]:
        capture(f"precommit-merge-repr-{label}", "precommit-merge",
                document(entry(categories={"unit": {"status": status}})))
    assert len({r["id"] for r in records}) == len(records)
    witnesses = [(r["mode"], r["args"], r["setup"], r["git_body"], r["git_mode"])
                 for r in records]
    assert len({json.dumps(w, sort_keys=True) for w in witnesses}) == len(witnesses)
    output = dict(schema="mir.tdd-compat@1", oracle="abb0dd82:.claude/hooks/tdd-matrix-guard.py",
                  sha256=hashlib.sha256(source).hexdigest(), records=records)
    # Emit into scratch; the maintainer admits the JSON with the editing tool.
    (scratch / "w5-tdd.json").write_text(json.dumps(output, ensure_ascii=True, indent=2) + "\n",
                                        encoding="utf-8")
    print(f"captured {len(records)} reference records")


if __name__ == "__main__":
    main()
