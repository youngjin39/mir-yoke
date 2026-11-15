"""Freeze P1 only from two identical, pinned Windows Python captures (no execution)."""

import argparse
import hashlib
import json
import zipfile
from pathlib import Path

PINS = {
    "provider": "1324a3cbf4f5eb5cbe5102efe555203895fbea65",
    "brief": "84b7b8a33cff26cd782170befa8621a1c65d9744",
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--captures", nargs=2, required=True, type=Path)
    parser.add_argument("--package", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    raw = [path.read_bytes() for path in args.captures]
    runs = [json.loads(body) for body in raw]
    frozen = {"capture_sha256": [hashlib.sha256(body).hexdigest() for body in raw]}
    for consumer, pin in PINS.items():
        probe = runs[0]["probes"][consumer]
        assert probe == runs[1]["probes"][consumer], consumer
        assert probe["platform"] == "win32" and probe["reference_pin"] == pin
        assert len(probe["records"]) == (44 if consumer == "provider" else 12)
        for record in probe["records"]:
            for field in [record["input"], record["stdout"], record["stderr"],
                          *record["files"].values()]:
                data = bytes.fromhex(field["tokenized_hex"])
                assert hashlib.sha256(data).hexdigest() == field["tokenized_sha256"]
                # P1 has no path-valued bytes: retain the {ROOT}/{DRIVE} convention
                # without translating any stream or inventing path replacements.
                assert not field["path_redacted"]
                assert len(data) == field["raw_length"]
                assert field["raw_sha256"] == field["tokenized_sha256"]
        with zipfile.ZipFile(args.package) as package:
            sources = [item for item in json.loads(package.read("source-manifest.json"))
                       if item["file"].startswith(f"references/{consumer}/")]
            assert sources and all(item["pin"] == pin for item in sources)
            for source in sources:
                assert hashlib.sha256(package.read(source["file"])).hexdigest() == source["sha256"]
            probe["sources"] = sources
            script = package.read("capture_windows.py")
            probe["capture_script_sha256"] = hashlib.sha256(script).hexdigest()
        frozen[consumer] = probe
    # One record per line keeps the byte-exact fixtures reviewable by route.
    lines = ["{", '"capture_sha256":' + json.dumps(frozen["capture_sha256"]) + ","]
    for index, consumer in enumerate(PINS):
        probe = dict(frozen[consumer])
        records = probe.pop("records")
        lines += [json.dumps(consumer) + ":{", json.dumps(probe)[1:-1] + ',"records":[']
        lines += [json.dumps(record, separators=(",", ":")) +
                  ("," if n + 1 < len(records) else "") for n, record in enumerate(records)]
        lines += ["]}" + ("," if index == 0 else "")]
    args.output.write_text("\n".join([*lines, "}", ""]), encoding="utf-8")


if __name__ == "__main__":
    main()
