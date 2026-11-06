"""Verify once-extracted inputs against the untouched reference table.

Rows contain kind, earlier case name, prefix byte count, and base64/repeat suffix
spans. Prefix sharing and repetition preserve the large boundary inputs compactly.
"""
import base64
import json
from pathlib import Path

from test_w2_yaml_compose_frozen import CASES


def test_native_input_fixture_matches_cases():
    path = Path(__file__).parent / "../native/handoff-packet/tests/yaml-inputs.json"
    rows = json.loads(path.read_text(encoding="ascii"))
    decoded = {}
    for name, (kind, parent, prefix, spans) in rows.items():
        raw = decoded[parent][:prefix] if parent else b""
        raw += b"".join(base64.b64decode(text) * count for text, count in spans)
        decoded[name] = raw
        actual = raw if kind == "bytes" else raw.decode("utf-8", "surrogatepass")
        assert actual == CASES[name], name
    assert set(rows) == set(CASES)
    assert len(rows) == 252
