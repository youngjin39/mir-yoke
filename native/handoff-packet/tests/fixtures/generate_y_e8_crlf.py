"""Generate splitlines and real pull-console oracles using the worktree .venv.

Run from the repository root with scratch HOME/MIR_HUB_DB_PATH:
  .venv/bin/python -B native/handoff-packet/tests/fixtures/generate_y_e8_crlf.py
No network, existing databases, or frozen E8 fixtures are used.
"""

import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO / "src"))

from mir.cli.__main__ import main
from mir.core.engine.memory import store
from mir.core.engine.memory.external_store import ExternalStore


def main_fixture():
    cases = [
        ("empty", ""),
        ("lf", "alpha\nbeta\n"),
        ("crlf", "alpha\r\nbeta\r\n"),
        ("cr", "alpha\rbeta\r"),
        ("mixed", "a\r\nb\rc\nd\vE\fF\x1cG\x1dH\x1eI\x85J\u2028K\u2029"),
        ("blank-lines", "\r\nalpha\r\n\r\nbeta\n\n"),
        ("trailing-break", "alpha\r\n"),
        ("no-trailing-break", "alpha\r\nbeta"),
        ("nel", "alpha\x85beta\x85"),
        ("line-separator", "alpha\u2028beta\u2028"),
    ]
    # Exhaustive short sequences exercise consecutive and terminal delimiters.
    import itertools

    for n in range(1, 4):
        for chars in itertools.product(("x", "\r", "\n", "\x85", "\u2028"), repeat=n):
            text = "".join(chars)
            cases.append((f"sequence-{len(cases)}", text))
    rows = []
    for name, text in cases:
        lines = text.splitlines()
        rendered = "\n".join(f"  {line}" for line in (lines or [""]))
        rows.append(dict(name=name, input=text, lines=lines,
                         indented_len=len(rendered.encode("utf-8"))))

    with tempfile.TemporaryDirectory(dir=os.environ["HOME"]) as tmp:
        root = Path(tmp)
        (root / "notes").mkdir()
        body = "alpha apple orchard.\r\n\r\nbeta apple harbor.\r\n"
        (root / "notes/0.md").write_bytes(body.encode("utf-8"))
        config = "[memory]\nvector_mode='optional'\n[memory.embedding]\nenabled=false\n"
        (root / "harness_a.toml").write_text(config, encoding="utf-8")
        c = store.connect(root / "memory.db")
        store.apply_migrations(c.conn)
        es = ExternalStore(c)
        aid = es.register(slug="notes", root_path=str(root / "notes"),
                          mode="indexed", owner="synthetic")
        es.scan(aid)
        c.conn.commit()
        c.conn.close()
        argv = ["context", "pull", "apple", "--db", str(root / "memory.db"),
                "--project-root", str(root), "--k", "1"]
        captures = {}
        for name, newline in (("stdout", "\n"), ("stdout_windows", "\r\n")):
            buf = io.BytesIO()
            out = io.TextIOWrapper(buf, encoding="utf-8", newline=newline)
            err = io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = main(argv)
            out.flush()
            assert code == 0, err.getvalue()
            captures[name] = buf.getvalue().decode("utf-8")
        pull = dict(body=body, config=config, **captures)
    fixture = dict(cases=rows, pull=pull)
    Path(__file__).with_name("y-e8-crlf.json").write_text(
        json.dumps(fixture, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(dict(cases=len(rows), pull=pull), ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main_fixture()
