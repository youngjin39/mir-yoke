"""Build deterministic core and capability-pack release artifacts."""

from __future__ import annotations

import gzip
import io
import os
import tarfile
import tempfile
from pathlib import Path

from .catalog import (
    DistributionError,
    atomic_write_json,
    expand_source_paths,
    load_pack_manifests,
    load_product_planes,
    sha256_file,
    source_is_clean,
    source_revision,
)


def _write_archive(path: Path, members: dict[str, Path]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, raw_temp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    os.close(descriptor)
    temp_path = Path(raw_temp)
    try:
        with temp_path.open("wb") as raw_stream:
            with gzip.GzipFile(filename="", mode="wb", fileobj=raw_stream, mtime=0) as zipped:
                with tarfile.open(fileobj=zipped, mode="w", format=tarfile.PAX_FORMAT) as archive:
                    for archive_name, source in sorted(members.items()):
                        payload = source.read_bytes()
                        info = tarfile.TarInfo(archive_name)
                        info.size = len(payload)
                        info.mode = 0o644
                        info.mtime = 0
                        info.uid = 0
                        info.gid = 0
                        info.uname = ""
                        info.gname = ""
                        archive.addfile(info, io.BytesIO(payload))
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def _pack_members(root: Path, pack_id: str, pack: dict[str, object]) -> dict[str, Path]:
    members = {
        "pack.json": root / "packs" / pack_id / "pack.json",
        "README.md": root / "packs" / pack_id / "README.md",
    }
    source_paths = pack.get("source_paths")
    if not isinstance(source_paths, list) or not all(
        isinstance(item, str) for item in source_paths
    ):
        raise DistributionError(f"pack {pack_id} has invalid source paths")
    for relative, path in expand_source_paths(root, source_paths).items():
        members[f"source/{relative}"] = path
    adoption_assets = pack.get("adoption_assets")
    if not isinstance(adoption_assets, list):
        raise DistributionError(f"pack {pack_id} has invalid adoption assets")
    for asset in adoption_assets:
        if not isinstance(asset, dict):
            raise DistributionError(f"pack {pack_id} has invalid adoption asset")
        source = asset.get("source")
        target = asset.get("target")
        if not isinstance(source, str) or not isinstance(target, str):
            raise DistributionError(f"pack {pack_id} has invalid adoption mapping")
        members[f"payload/{target}"] = root / source
    return members


def build_distribution(
    source_root: Path,
    output_dir: Path,
    *,
    version: str | None = None,
    require_clean: bool = False,
) -> dict[str, object]:
    source_root = source_root.resolve()
    output_dir = output_dir.resolve()
    load_product_planes(source_root)
    packs = load_pack_manifests(source_root)
    if require_clean and not source_is_clean(source_root):
        raise DistributionError("distribution source must be a clean Git worktree")
    release_version = version or (source_root / "VERSION").read_text(encoding="utf-8").strip()
    if not release_version:
        raise DistributionError("release version is empty")
    output_dir.mkdir(parents=True, exist_ok=True)

    core_members = {
        path.name: path
        for path in sorted((source_root / "starter").iterdir())
        if path.is_file()
    }
    core_path = output_dir / f"mir-yoke-core-{release_version}.tar.gz"
    _write_archive(core_path, core_members)
    artifact_paths: list[tuple[Path, str, str | None, str]] = [
        (core_path, "core", None, "stable")
    ]
    for pack_id, pack in sorted(packs.items()):
        archive_path = output_dir / f"mir-yoke-pack-{pack_id}-{release_version}.tar.gz"
        _write_archive(archive_path, _pack_members(source_root, pack_id, pack))
        artifact_paths.append(
            (archive_path, "pack", pack_id, str(pack["support_level"]))
        )

    artifacts = []
    for path, kind, pack_id, support_level in artifact_paths:
        row: dict[str, object] = {
            "file": path.name,
            "kind": kind,
            "support_level": support_level,
            "sha256": sha256_file(path),
            "size": path.stat().st_size,
        }
        if pack_id is not None:
            row["pack"] = pack_id
        artifacts.append(row)
    manifest = {
        "schema_version": 1,
        "version": release_version,
        "source_revision": source_revision(source_root),
        "artifacts": artifacts,
    }
    atomic_write_json(output_dir / "manifest.json", manifest)
    provenance = {
        "_type": "https://in-toto.io/Statement/v1",
        "subject": [
            {"name": item["file"], "digest": {"sha256": item["sha256"]}}
            for item in artifacts
        ],
        "predicateType": "https://slsa.dev/provenance/v1",
        "predicate": {
            "buildType": "https://mir-yoke.dev/distribution/v1",
            "externalParameters": {"version": release_version},
            "resolvedDependencies": [
                {
                    "uri": "git+https://github.com/youngjin39/mir-yoke",
                    "digest": {"gitCommit": manifest["source_revision"]},
                }
            ],
        },
    }
    atomic_write_json(output_dir / "provenance.json", provenance)
    checksum_paths = [
        *(path for path, *_ in artifact_paths),
        output_dir / "manifest.json",
        output_dir / "provenance.json",
    ]
    checksums = "".join(
        f"{sha256_file(path)}  {path.name}\n" for path in sorted(checksum_paths)
    )
    checksum_path = output_dir / "SHA256SUMS"
    checksum_path.write_text(checksums, encoding="utf-8", newline="\n")
    return {
        "status": "built",
        "version": release_version,
        "artifact_count": len(artifacts),
        "output_dir": str(output_dir),
        "manifest": manifest,
    }
