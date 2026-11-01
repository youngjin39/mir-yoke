"""Pin published lifecycle binaries, never a local rebuild, into an explicit lock.

Offline: --directory contains GitHub's release.json and all downloaded assets.
Online: --repo OWNER/REPO --tag native-<12-char SHA> uses read-only gh operations.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

from mir.core.capabilities.native import validate_artifacts

TARGETS = (
    "aarch64-apple-darwin", "x86_64-apple-darwin", "x86_64-unknown-linux-gnu",
    "aarch64-unknown-linux-gnu", "x86_64-pc-windows-msvc",
)
NAMES = ("handoff-packet", "runtime-continuity", "bootstrap-gate", "runtime-verify")
PLUGIN = "mir-lifecycle-hooks"


def filename(name: str, target: str) -> str:
    return f"{name}-{target}" + (".exe" if target.endswith("windows-msvc") else "")


def pin_release(directory: Path, lock_path: Path, source: str) -> None:
    """Validate the complete release before changing only the lock's native section."""
    release = json.loads((directory / "release.json").read_text(encoding="utf-8"))
    tag = release.get("tag_name", "")
    if re.fullmatch(r"native-[0-9a-f]{12}", tag) is None or release.get("prerelease") is not True:
        raise ValueError("expected a native-<12-char SHA> prerelease")
    # The source is the commit the bind pins; the lock's own source.commit still names the
    # previously recorded provider at bind time, so it cannot serve as the reference.
    if (
        re.fullmatch(r"[0-9a-f]{40}", source) is None
        or tag != f"native-{source[:12]}"
        or release.get("target_commitish") != source
    ):
        raise ValueError("release was not built from the given source commit")
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    expected = {filename(name, target) for name in NAMES for target in TARGETS}
    expected.update(f"SHA256-{target}.txt" for target in TARGETS)
    assets = {}
    bases = set()
    for asset in release["assets"]:
        name = asset["name"]
        if name not in expected or name in assets:
            raise ValueError("unexpected or duplicate release asset")
        url = asset["browser_download_url"]
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https" or parsed.netloc != "github.com"
            or parsed.query or parsed.fragment
            or re.fullmatch(
                rf"/[^/]+/[^/]+/releases/download/{re.escape(tag)}/{re.escape(name)}",
                parsed.path,
            ) is None
        ):
            raise ValueError("expected HTTPS GitHub release asset URL")
        bases.add(url.rsplit("/", 1)[0])
        path = directory / name
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"missing or linked asset: {name}")
        data = path.read_bytes()
        if type(asset["size"]) is not int or asset["size"] <= 0 or len(data) != asset["size"]:
            raise ValueError(f"asset size mismatch: {name}")
        assets[name] = (asset, data)
    if set(assets) != expected or len(bases) != 1:
        raise ValueError("incomplete release or mixed release URLs")
    records = {name: {"plugin": PLUGIN, "install_path": f"bin/{name}", "targets": {}}
               for name in NAMES}
    for target in TARGETS:
        lines = assets[f"SHA256-{target}.txt"][1].decode("ascii").splitlines()
        checksums = {}
        for line in lines:
            match = re.fullmatch(r"([0-9a-f]{64}) [ *](\S+)", line)
            if match is None or match[2] in checksums:
                raise ValueError("invalid or duplicate checksum line")
            checksums[match[2]] = match[1]
        if set(checksums) != {filename(name, target) for name in NAMES}:
            raise ValueError("checksum file must name exactly all target binaries")
        for name in NAMES:
            asset_name = filename(name, target)
            asset, data = assets[asset_name]
            digest = hashlib.sha256(data).hexdigest()
            if digest != checksums[asset_name]:
                raise ValueError(f"SHA256 mismatch: {asset_name}")
            records[name]["targets"][target] = {
                "url": asset["browser_download_url"], "sha256": digest, "size": len(data),
            }
    validate_artifacts(records, lock["plugins"], portable=True)
    lock["native_artifacts"] = records
    lock_path.write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--directory", type=Path)
    source.add_argument("--repo", help="GitHub OWNER/REPO")
    parser.add_argument("--tag")
    parser.add_argument("--lock", required=True, type=Path, help="explicit capability-lock.json")
    parser.add_argument("--source", required=True, help="40-char source commit of the prerelease")
    args = parser.parse_args(argv)
    try:
        if args.directory:
            if args.tag:
                parser.error("--tag is only used with --repo")
            pin_release(args.directory, args.lock, args.source)
        else:
            if not re.fullmatch(r"[\w.-]+/[\w.-]+", args.repo) or not re.fullmatch(
                r"native-[0-9a-f]{12}", args.tag or ""
            ):
                parser.error("--repo OWNER/REPO requires --tag native-<12-char SHA>")
            with tempfile.TemporaryDirectory(prefix="native-release-") as temporary:
                directory = Path(temporary)
                result = subprocess.run(
                    ["gh", "api", "--method", "GET",
                     f"repos/{args.repo}/releases/tags/{args.tag}"],
                    check=True, capture_output=True,
                )
                (directory / "release.json").write_bytes(result.stdout)
                subprocess.run(
                    ["gh", "release", "download", args.tag, "--repo", args.repo,
                     "--dir", str(directory), "--pattern", "handoff-packet-*",
                     "--pattern", "runtime-continuity-*", "--pattern", "bootstrap-gate-*",
                     "--pattern", "runtime-verify-*", "--pattern", "SHA256-*"],
                    check=True,
                )
                pin_release(directory, args.lock, args.source)
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"native release: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
