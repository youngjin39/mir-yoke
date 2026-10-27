import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_checkouts_keep_blob_bytes_on_every_os():
    # Reviewed handler and package digests hash raw bytes; Git for Windows
    # converts LF to CRLF on checkout unless the repository says otherwise.
    assert (ROOT / ".gitattributes").read_text(encoding="utf-8").splitlines()[-1] == "* -text"
    out = subprocess.run(
        ["git", "-C", str(ROOT), "check-attr", "text", "--",
         "plugins/mir-lifecycle-hooks/hooks/hooks.json", "plugins/mir-mcp/mir_mcp.py"],
        capture_output=True, text=True, encoding="utf-8", check=True,
    ).stdout.splitlines()
    assert out == [
        "plugins/mir-lifecycle-hooks/hooks/hooks.json: text: unset",
        "plugins/mir-mcp/mir_mcp.py: text: unset",
    ]
