"""Freeze pass-1 isolated PC captures; inputs come from capture_windows.py's pinned bundle."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def freeze(value):
    """Exclude hashes of pre-tokenisation bytes, preserving every captured value."""
    if isinstance(value, dict):
        result = {key: freeze(item) for key, item in value.items()
                  if key not in {"raw_record_sha256", "raw_sha256"}}
        # The old cleaner missed the JSON-escaped root: this unlabelled hash is raw too.
        if "legacy_cleaned_observation" in result:
            result["legacy_cleaned_observation"][1].pop("sha256")
        return result
    if isinstance(value, list):
        return [freeze(item) for item in value]
    return value


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument("repeat", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    first, second = [json.loads(path.read_text(encoding="utf-8"))
                     for path in (args.capture, args.repeat)]
    assert first["platform"] == "win32" and first["python"].startswith("3.12.13 ")
    assert len(first["records"]) == 11
    first, second = freeze(first), freeze(second)
    assert first == second, "tokenised captures differ"
    for record in first["records"]:
        for stream in ("stdout", "stderr"):
            text = record[stream].encode("utf-8")
            witness = record[stream + "_bytes"]
            assert text.hex() == witness["tokenized_hex"], record.get("route", record.get("case"))
            assert hashlib.sha256(text).hexdigest() == witness["tokenized_sha256"]
    first["bytes_contract"] = ("Tokenized UTF-8 application text; pre-tokenisation raw hashes "
                               "omitted. Original lengths retained, not process CRLF framing.")
    args.output.write_text(json.dumps(first, ensure_ascii=True) + "\n", encoding="ascii")


if __name__ == "__main__":
    main()
