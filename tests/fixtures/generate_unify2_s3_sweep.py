"""Freeze P2 pinned Windows Python rows; never use native rows as expectations."""

import argparse
import hashlib
import json
import zipfile
from pathlib import Path

PIN = "f10edf21f5a94db1254eacabfdb06b517f9daeca"
SOURCE_SHA = "81a58812087992733c5dc0b0549319c9e7663a1d4cf005591882bc103da52c0b"


def project(probe):
    records = []
    for record in probe["records"]:
        if not record["variant"].endswith("/python"):
            continue
        assert record["exit"] == 0 and record["exception"] is None
        for field in [record["stdout"], record["stderr"], *record["files"].values()]:
            data = bytes.fromhex(field["tokenized_hex"])
            assert hashlib.sha256(data).hexdigest() == field["tokenized_sha256"]
        paths = record["receipt_paths"] + [record["input"]["stored_receipt"]]
        paths += [item["path"] for item in record["lookup_arguments"]]
        for path in paths:
            assert path["text"] == "".join(map(chr, path["codepoints"]))
            assert path["repr"] == repr(path["text"])
        records.append({key: record[key] for key in (
            "name", "variant", "input", "before_sql", "after_sql", "result",
            "lookup_arguments", "receipt_paths", "refs",
        )})
    assert len(records) == 12
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--captures", nargs=2, required=True, type=Path)
    parser.add_argument("--package", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    raw = [path.read_bytes() for path in args.captures]
    probes = [json.loads(body)["probes"]["sweep"] for body in raw]
    assert all(p["platform"] == "win32" and p["reference_pin"] == PIN for p in probes)
    records = project(probes[0])
    assert records == project(probes[1]), "P2 Python records differ"
    with zipfile.ZipFile(args.package) as package:
        sources = [s for s in json.loads(package.read("source-manifest.json"))
                   if s["file"].startswith("references/sweep/")]
        assert sources and all(s["pin"] == PIN for s in sources)
        for source in sources:
            assert hashlib.sha256(package.read(source["file"])).hexdigest() == source["sha256"]
        assert hashlib.sha256(package.read("references/sweep/tools/mir_executor/sweep.py")) \
            .hexdigest() == SOURCE_SHA
    provenance = {key: value for key, value in probes[0].items() if key != "records"}
    provenance.update(sources=sources, capture_sha256=[hashlib.sha256(b).hexdigest() for b in raw])
    lines = ["{", '"provenance":' + json.dumps(provenance) + ',"records":[']
    lines += [json.dumps(r, separators=(",", ":")) + ("," if i < 11 else "")
              for i, r in enumerate(records)]
    args.output.write_text("\n".join([*lines, "]}", ""]), encoding="utf-8")


if __name__ == "__main__":
    main()
