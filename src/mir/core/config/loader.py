"""Portable, fail-loud loader for the public template memory contract.

The public template intentionally resolves only the memory section. Other
top-level sections may be consumed by private Mir builds, but unknown keys
inside ``[memory]`` are rejected so a typo cannot silently disable memory.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from . import defaults as D


class ConfigLoadError(RuntimeError):
    """The authored harness configuration is malformed or contradictory."""


_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


class EmbeddingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: bool = False
    required: bool = False
    backend: Literal["omlx_http"] = "omlx_http"
    base_url: str = D.DEFAULT_EMBEDDING_BASE_URL
    model: str = D.DEFAULT_EMBEDDING_MODEL
    fingerprint: str = ""
    dim: int = Field(default=D.DEFAULT_EMBEDDING_DIM, gt=0)
    timeout_sec: int = Field(default=D.DEFAULT_EMBEDDING_TIMEOUT_SEC, gt=0)
    norm_tolerance: float = Field(default=D.DEFAULT_EMBEDDING_NORM_TOLERANCE, gt=0)
    api_key_env: str = D.DEFAULT_EMBEDDING_API_KEY_ENV
    auth_scheme: str = "Bearer"

    @model_validator(mode="after")
    def _required_is_enabled(self) -> EmbeddingConfig:
        if self.required and not self.enabled:
            raise ValueError("memory.embedding.required=true requires enabled=true")
        if self.dim != D.DEFAULT_EMBEDDING_DIM:
            raise ValueError(
                "memory.embedding.dim must be 1024 until versioned vector tables exist"
            )
        if self.enabled and not self.fingerprint.strip():
            raise ValueError(
                "memory.embedding.fingerprint is required when embedding is enabled"
            )
        return self


class ExternalArchiveConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    slug: str
    root: str
    mode: Literal["indexed", "immutable"] = "indexed"
    glob_include: tuple[str, ...] = ("**/*.md",)
    glob_exclude: tuple[str, ...] = ()
    historical_glob: tuple[str, ...] = ()
    chunk_size: int = Field(default=800, ge=50, le=8192)
    chunk_overlap: int = Field(default=100, ge=0, lt=8192)

    @model_validator(mode="after")
    def _validate_archive(self) -> ExternalArchiveConfig:
        if not _SLUG_RE.fullmatch(self.slug):
            raise ValueError(f"archive slug {self.slug!r} must match {_SLUG_RE.pattern!r}")
        if not self.root.strip():
            raise ValueError(f"archive {self.slug!r} root must not be empty")
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError(f"archive {self.slug!r} chunk_overlap must be smaller than chunk_size")
        from mir.core.engine.memory.external_store import _compile_pattern_set

        for field_name, patterns in (
            ("glob_include", self.glob_include),
            ("glob_exclude", self.glob_exclude),
            ("historical_glob", self.historical_glob),
        ):
            try:
                _compile_pattern_set(patterns)
            except re.error as exc:
                raise ValueError(
                    f"archive {self.slug!r} {field_name} contains an invalid glob: {exc}"
                ) from exc
        return self


class MemoryConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: bool = True
    required: bool = True
    backend: Literal["sqlite_fts5"] = "sqlite_fts5"
    db_path: str = ".mir/memory.db"
    vector_mode: Literal["off", "optional", "required"] = "off"
    plugin_mode: Literal["auto", "disabled", "bridge_only"] = D.DEFAULT_CLAUDE_MEMORY_PLUGIN_MODE  # type: ignore[assignment]
    recall_policy: Literal["progressive", "full"] = D.DEFAULT_CLAUDE_MEMORY_RECALL_POLICY  # type: ignore[assignment]
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    external_archives: tuple[ExternalArchiveConfig, ...] = ()

    @model_validator(mode="after")
    def _validate_modes(self) -> MemoryConfig:
        if self.required and not self.enabled:
            raise ValueError("memory.required=true requires enabled=true")
        if not self.db_path.strip():
            raise ValueError("memory.db_path must not be empty")
        if self.vector_mode == "off" and self.embedding.enabled:
            raise ValueError("memory.embedding.enabled=true requires vector_mode optional|required")
        if self.vector_mode == "required":
            if not self.embedding.enabled or not self.embedding.required:
                raise ValueError(
                    "memory.vector_mode='required' requires embedding enabled=true "
                    "and required=true"
                )
        return self


class ResolvedConfig(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True)

    memory: MemoryConfig = Field(default_factory=MemoryConfig)


def _resolve_path(project_root: Path, authored_path: str) -> Path:
    candidate = Path(authored_path).expanduser()
    if not candidate.is_absolute():
        candidate = project_root / candidate
    return candidate.resolve(strict=False)


def resolve_memory_db(project_root: Path, cfg: ResolvedConfig) -> Path:
    """Return the configured DB location without creating it."""
    root = project_root.resolve()
    authored = Path(cfg.memory.db_path)
    if authored.is_absolute():
        raise ConfigLoadError("memory.db_path must be project-relative")
    resolved = _resolve_path(root, cfg.memory.db_path)
    mir_root = (root / ".mir").resolve(strict=False)
    try:
        resolved.relative_to(mir_root)
    except ValueError as exc:
        raise ConfigLoadError("memory.db_path must stay inside the project .mir directory") from exc
    return resolved


def resolve_archive_root(project_root: Path, archive: ExternalArchiveConfig) -> Path:
    """Return one configured archive root without requiring it to exist."""
    return _resolve_path(project_root.resolve(), archive.root)


def _paths_overlap(first: Path, second: Path) -> bool:
    try:
        first.relative_to(second)
        return True
    except ValueError:
        pass
    try:
        second.relative_to(first)
        return True
    except ValueError:
        return False


def _validate_archive_set(project_root: Path, cfg: ResolvedConfig) -> None:
    seen_slugs: set[str] = set()
    resolved: list[tuple[str, Path]] = []
    for archive in cfg.memory.external_archives:
        if archive.slug in seen_slugs:
            raise ConfigLoadError(f"duplicate external archive slug: {archive.slug!r}")
        seen_slugs.add(archive.slug)
        root = resolve_archive_root(project_root, archive)
        for prior_slug, prior_root in resolved:
            if _paths_overlap(root, prior_root):
                raise ConfigLoadError(
                    "external archives must not overlap: "
                    f"{prior_slug!r} ({prior_root}) and {archive.slug!r} ({root})"
                )
        resolved.append((archive.slug, root))


def load_config(project_root: Path | None = None) -> ResolvedConfig:
    """Load ``harness_a.toml`` and reject malformed memory configuration.

    A missing file resolves to explicit defaults for compatibility with
    read-only CLI calls. ``mir bootstrap`` is responsible for materializing
    and enforcing the active file before it declares a project ready.
    """
    root = (project_root or Path.cwd()).resolve()
    path = root / "harness_a.toml"
    raw: dict[str, Any] = {}
    if path.exists() and not path.is_file():
        raise ConfigLoadError(f"harness_a.toml is not a regular file: {path}")
    if path.is_file():
        try:
            with path.open("rb") as handle:
                raw = tomllib.load(handle)
        except (OSError, tomllib.TOMLDecodeError) as exc:
            raise ConfigLoadError(f"harness_a.toml: {exc}") from exc
    try:
        cfg = ResolvedConfig.model_validate(raw)
    except Exception as exc:
        raise ConfigLoadError(f"harness_a.toml memory configuration: {exc}") from exc
    _validate_archive_set(root, cfg)
    resolve_memory_db(root, cfg)
    return cfg
