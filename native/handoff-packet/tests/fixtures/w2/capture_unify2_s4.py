"""Freeze P3 Windows Python observations, never native digests. Run from repo root."""

import argparse
import hashlib
import json
from pathlib import Path

PIN = "d7bf5cc90052e12898748b613e55e7856e7debc5"
MODES = ("argv_none", "pass", "native_arg", "install_none")


def freeze(path):
    capture = json.loads(path.read_text(encoding="utf-8"))
    probe = capture["probes"]["adoption"]
    assert probe["reference_pin"] == PIN and probe["platform"] == "win32"
    records = {}
    for mode in MODES:
        name = f"adoption_main.scripted_validators.{mode}.apply_True.windows."
        rows = [next(r for r in probe["records"] if r["name"] == name + suffix)
                for suffix in ("raw", "digest", "effects")]
        row = rows[0]
        assert all({k: v for k, v in r.items() if k != "name"}
                   == {k: v for k, v in row.items() if k != "name"} for r in rows)
        value = row["raw_result"]
        assert value == json.loads(bytes.fromhex(row["deterministic_json"]["tokenized_hex"]))
        assert row["exit"] == value["result"]["value"] and row["exception"] is None
        for stream in ("stdout", "stderr"):
            assert bytes.fromhex(row[stream]["tokenized_hex"]) == value[stream].encode()
        # CAP retains escaped path spellings. Only these declared Path-valued mock
        # arguments are canonicalized; suffixes and all other strings stay exact.
        root = value["calls"][0][1][0]
        assert root.replace("\\", "/").replace("//", "/") == f"{{ROOT}}/adoption-{mode}"
        for call in value["calls"]:
            if call[1] and call[1][0] == root:
                call[1][0] = "<tmp>"
        install = value["installs"][0]
        assert install[0] == [root]
        install[0] = ["<tmp>"]
        for key, suffix in (("source_root", "source"), ("local_source", "local-evaluator")):
            path_value = install[1][key]
            if path_value is not None:
                assert path_value in (root + "\\" + suffix, root + "\\\\" + suffix)
                install[1][key] = "<tmp>/" + suffix
        files = {k: v["tokenized_hex"] for k, v in row["files"].items()}
        receipt = bytes.fromhex(row["receipt_raw"]["tokenized_hex"])
        assert receipt.hex() == files[".mir/bootstrap-receipt.json"]
        assert receipt.count(b"\r\n") == receipt.count(b"\n") > 0
        assert receipt.decode().replace("\r\n", "\n") == row["receipt_read_text"]
        assert value["receipts"][".mir/bootstrap-receipt.json"] == row["receipt_read_text"]
        records[mode] = {"value": value, "files": files}
    assert "{ROOT}" not in json.dumps(records), "unhandled run-scoped path"
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_a", type=Path)
    parser.add_argument("run_b", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    records = freeze(args.run_a)
    assert records == freeze(args.run_b), "run-scoped bytes remain"
    provenance = {"reference_pin": PIN, "capture_sha256": [
        hashlib.sha256(p.read_bytes()).hexdigest() for p in (args.run_a, args.run_b)
    ]}
    rows = [json.dumps(k) + ": " + json.dumps(v, sort_keys=True)
            for k, v in sorted(records.items())]
    text = json.dumps(provenance, sort_keys=True)[:-1] + ', "records": {\n'
    args.output.write_text(text + ",\n".join(rows) + "\n}}\n", encoding="ascii")
    print("P3: four Python-only records; two captures agree including raw file bytes")


if __name__ == "__main__":
    main()
