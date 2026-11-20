"""Pin published native binaries, never a local rebuild, into an explicit lock.

Offline: --directory contains GitHub's release.json and all downloaded assets.
Online: --repo OWNER/REPO --tag native-<12-char SHA> uses read-only gh operations.
Use --cli-pin config/cli-native-artifacts.json for a release that includes mir.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

from mir.core.capabilities.native import validate_artifacts

MAC_TARGETS = ("aarch64-apple-darwin", "x86_64-apple-darwin")
TARGETS = (
    *MAC_TARGETS, "x86_64-unknown-linux-gnu",
    "aarch64-unknown-linux-gnu", "x86_64-pc-windows-msvc",
)
BINARIES = {
    "handoff-packet": "mir-lifecycle-hooks",
    "runtime-continuity": "mir-lifecycle-hooks",
    "bootstrap-gate": "mir-lifecycle-hooks",
    "runtime-verify": "mir-lifecycle-hooks",
    "executor-query": "mir-lifecycle-hooks",
    "delegation-gate": "mir-lifecycle-hooks",
    "project-hooks": "mir-lifecycle-hooks",
    "mir-mcp": "mir-mcp",
}


def filename(name: str, target: str) -> str:
    return f"{name}-{target}" + (".exe" if target.endswith("windows-msvc") else "")


def pin_release(
    directory: Path, lock_path: Path, source: str, cli_pin: Path | None = None,
    mac_only: bool = False,
) -> None:
    """Validate the full release or Mac cohort before writing native pins."""
    if mac_only and cli_pin is None:
        raise ValueError("--mac-only requires --cli-pin")
    lock_path = lock_path.resolve()
    if cli_pin is not None:
        cli_pin = cli_pin.resolve()
        if (
            cli_pin.name == "capability-lock.json" or cli_pin == lock_path
            or (cli_pin.exists() and lock_path.exists() and cli_pin.samefile(lock_path))
        ):
            raise ValueError("--cli-pin must be separate from the capability lock")
    # A rerun needs the same release input, so no output may land inside it.
    release_dir = directory.resolve()
    for output in (lock_path, cli_pin):
        if output is not None and (
            output.is_relative_to(release_dir)
            or (output.exists() and output.samefile(directory / "release.json"))
        ):
            raise ValueError(f"output must be outside the release directory: {output}")
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
    targets = MAC_TARGETS if mac_only else TARGETS
    names_by_target = {
        target: (*BINARIES, "mir") if cli_pin and target in MAC_TARGETS else tuple(BINARIES)
        for target in targets
    }
    expected = {filename(name, target) for target in targets for name in names_by_target[target]}
    expected.update(f"SHA256-{target}.txt" for target in targets)
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
    records = {name: {"plugin": BINARIES[name], "install_path": f"bin/{name}", "targets": {}}
               for name in BINARIES}
    console_targets = {}
    for target, names in names_by_target.items():
        lines = assets[f"SHA256-{target}.txt"][1].decode("ascii").splitlines()
        checksums = {}
        for line in lines:
            match = re.fullmatch(r"([0-9a-f]{64}) [ *](\S+)", line)
            if match is None or match[2] in checksums:
                raise ValueError("invalid or duplicate checksum line")
            checksums[match[2]] = match[1]
        if set(checksums) != {filename(name, target) for name in names}:
            raise ValueError("checksum file must name exactly all target binaries")
        for name in names:
            asset_name = filename(name, target)
            asset, data = assets[asset_name]
            digest = hashlib.sha256(data).hexdigest()
            if digest != checksums[asset_name]:
                raise ValueError(f"SHA256 mismatch: {asset_name}")
            pins = console_targets if name == "mir" else records[name]["targets"]
            pins[target] = {
                "url": asset["browser_download_url"], "sha256": digest, "size": len(data),
            }
    existing = lock.get("native_artifacts", {})
    if mac_only:
        for name, record in records.items():
            record["targets"] = {**existing.get(name, {}).get("targets", {}), **record["targets"]}
    merged = {**existing, **records}
    validate_artifacts(merged, lock["plugins"], portable=True)
    outputs = {}
    if cli_pin is not None:
        console = {"source_commit": source, "targets": console_targets}
        outputs[cli_pin] = json.dumps(console, indent=2) + "\n"
    lock["native_artifacts"] = merged
    outputs[lock_path] = json.dumps(lock, indent=2) + "\n"
    publish_outputs(outputs, lock_path, cli_pin)


def publish_outputs(outputs: dict[Path, str], lock_path: Path, cli_pin: Path | None) -> None:
    modes = {}
    for path in outputs:
        parent = path.parent
        if not parent.is_dir() or not parent.stat().st_mode & 0o222 or not os.access(
            parent, os.W_OK | os.X_OK,
        ):
            raise PermissionError(f"destination directory is not writable: {parent}")
        if path.exists():
            mode = path.stat().st_mode
            if not stat.S_ISREG(mode) or not mode & 0o222 or not os.access(path, os.W_OK):
                raise PermissionError(f"destination file is not writable: {path}")
            modes[path] = stat.S_IMODE(mode)

    staged = {}
    try:
        for path, payload in outputs.items():
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=path.parent, delete=False,
            ) as handle:
                temporary = Path(handle.name)
                staged[path] = temporary
                handle.write(payload)
                handle.flush()
                if path in modes:
                    temporary.chmod(modes[path])
                os.fsync(handle.fileno())
        if cli_pin is not None:
            os.replace(staged[cli_pin], cli_pin)
        try:
            os.replace(staged[lock_path], lock_path)
        except OSError as exc:
            if cli_pin is None:
                raise
            raise OSError(
                f"updated {cli_pin} but could not replace {lock_path}: {exc}; "
                "rerun the same command to converge"
            ) from exc
    finally:
        leftovers = []
        for temporary in staged.values():
            # Preserve the publish error; only name what cleanup could not remove.
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                if temporary.exists():
                    leftovers.append(str(temporary))
        if leftovers:
            print("could not remove temporary file(s): " + ", ".join(leftovers), file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--directory", type=Path)
    source.add_argument("--repo", help="GitHub OWNER/REPO")
    parser.add_argument("--tag")
    parser.add_argument("--lock", required=True, type=Path, help="explicit capability-lock.json")
    parser.add_argument("--cli-pin", type=Path, help="write config/cli-native-artifacts.json")
    parser.add_argument("--mac-only", action="store_true", help="validate only the Darwin cohort")
    parser.add_argument("--source", required=True, help="40-char source commit of the prerelease")
    args = parser.parse_args(argv)
    try:
        if args.directory:
            if args.tag:
                parser.error("--tag is only used with --repo")
            pin_release(args.directory, args.lock, args.source, args.cli_pin, args.mac_only)
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
                names = (*BINARIES, "mir") if args.cli_pin else BINARIES
                subprocess.run(
                    ["gh", "release", "download", args.tag, "--repo", args.repo,
                     "--dir", str(directory),
                     *(part for name in names for part in ("--pattern", f"{name}-*")),
                     "--pattern", "SHA256-*"],
                    check=True,
                )
                pin_release(directory, args.lock, args.source, args.cli_pin, args.mac_only)
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"native release: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
