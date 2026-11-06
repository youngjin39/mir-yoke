"""Frozen unmodified Python config/registry oracle; never recapture from a port."""
from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

from mir.core.config import defaults as D
from mir.core.config import loader as L
from mir.core.registry import (
    AgentRegistry,
    EmbeddingBackendRegistry,
    EntryPointRegistry,
    ProviderRegistry,
    SkillRegistry,
    base,
)

FIXTURE = Path(__file__).parent / "../native/handoff-packet/tests/fixtures/w2/b02-config.json"


def _plain(value):
    if isinstance(value, (set, frozenset)):
        return sorted(_plain(item) for item in value)
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    return value


def _model(cls, data):
    return lambda tmp: cls.model_validate(data).model_dump(mode="json")


def _load(body=None, env=None, fault=None):
    def run(tmp):
        path = tmp / "harness_a.toml"
        if body is not None:
            path.write_text(body, encoding="ascii")
        if fault == "directory":
            path.mkdir()
        with mock.patch.dict(os.environ, env or {}, clear=True), \
                mock.patch.object(Path, "home", return_value=tmp), \
                mock.patch.object(Path, "cwd", return_value=tmp), \
                mock.patch.object(os, "getenv", wraps=os.getenv) as getenv, \
                mock.patch.object(os._Environ, "__getitem__", autospec=True,
                                  side_effect=lambda _, key: (env or {})[key]) as reads:
            try:
                if fault == "read":
                    with mock.patch.object(Path, "open", side_effect=PermissionError("denied")):
                        L.load_config(tmp)
                cfg = L.load_config().model_dump(mode="json")
                return [cfg, getenv.call_args_list, [c.args[1] for c in reads.call_args_list]]
            except Exception as exc:
                raise type(exc)(str(exc).replace(str(tmp), "<tmp>")) from None
    return run


def _path(tmp, mode):
    with mock.patch.dict(os.environ, {"HOME": str(tmp)}, clear=True):
        if mode.startswith("db:"):
            value = L.resolve_memory_db(tmp, L.ResolvedConfig(
                memory=L.MemoryConfig(db_path=mode[3:].replace("ABS", str(tmp)))))
        else:
            authored = mode[3:].replace("ABS", str(tmp))
            value = (L._resolve_path(tmp, authored) if mode.startswith("raw") else
                     L.resolve_archive_root(tmp, L.ExternalArchiveConfig(slug="a", root=authored)))
        return str(value).replace(str(tmp), "<tmp>")


def _registry(cls, mode):
    def run(tmp):
        events = []
        def ep(name, value):
            def load():
                events.append(["load", name, value])
                if mode == "broken":
                    raise RuntimeError("plugin failed")
                return value
            return SimpleNamespace(name=name, load=load)
        def discover(**kwargs):
            events.append(kwargs)
            return [] if mode == "empty" else [ep("z", "first"), ep("a", "a"), ep("z", "last")]
        with mock.patch.object(base, "entry_points", side_effect=discover):
            reg = cls()
            if mode == "unknown":
                return reg.get("missing")
            if mode.startswith("create"):
                cfg = (L.ResolvedConfig() if mode == "create-default" else
                       SimpleNamespace(providers=SimpleNamespace(
                           allowlist={"z": False} if mode == "create-allowed" else {})))
                return reg.create("z", cfg)
            values = [reg._discover(), reg.get("z")] if mode != "empty" else []
            values += [reg.all_names(), reg.has("a"), reg.has("missing")]
            reg.reset()
            return [values, reg.all_names(), events, hasattr(reg, "register")]
    return run


CASES = {"defaults.all": lambda tmp: {k: _plain(v) for k, v in vars(D).items()
                                    if k.isupper()},
         "registry.base": _registry(EntryPointRegistry, "normal")}
for name, cls, data in (
    ("embedding", L.EmbeddingConfig, {}), ("archive", L.ExternalArchiveConfig,
                                          {"slug": "a", "root": "archive"}),
    ("memory", L.MemoryConfig, {}), ("resolved", L.ResolvedConfig, {}),
):
    CASES[f"model.{name}.default"] = _model(cls, data)
    CASES[f"model.{name}.unknown"] = _model(cls, {**data, "unknown": 1})
for key, value in {"required": True, "backend": "bad", "dim": 0, "timeout_sec": -1,
                   "norm_tolerance": 0, "enabled": True, "base_url": [], "model": 3}.items():
    CASES[f"embedding.{key}"] = _model(L.EmbeddingConfig, {key: value})
for name, data in {"dim_policy": {"dim": 8}, "valid": {"enabled": True, "required": True,
                  "fingerprint": " fp "}, "coerce": {"dim": "1024", "enabled": "false"}}.items():
    CASES[f"embedding.{name}"] = _model(L.EmbeddingConfig, data)
for key, value in {"slug": "Bad", "root": " ", "mode": "bad", "chunk_size": 49,
                   "chunk_overlap": 800, "glob_include": 3}.items():
    CASES[f"archive.{key}"] = _model(L.ExternalArchiveConfig,
                                    {"slug": "a", "root": "archive", key: value})
for key, value in {"enabled": False, "db_path": " ", "vector_mode": "required",
                   "plugin_mode": "bad", "recall_policy": "bad", "backend": "bad",
                   "embedding": {"enabled": True, "fingerprint": "fp"}}.items():
    CASES[f"memory.{key}"] = _model(L.MemoryConfig, {key: value})
for name, body in {"missing": None, "empty": "", "memory": "[memory]\n",
                   "other": "[other]\nx=1", "unknown": "[memory]\nx=1",
                   "wrong": 'memory="bad"', "toml": "[", "invalid": "[memory]\nenabled=false",
                   "embedding": "[memory.embedding]\n",
                   "archives": "[memory]\nexternal_archives=[]",
                   "disabled": "[memory]\nenabled=false\nrequired=false"}.items():
    CASES[f"load.{name}"] = _load(body)
CASES["load.env"] = _load('[memory]\nplugin_mode="auto"',
                          {"MIR_MEMORY_ENABLED": "false", "MIR_CONFIG": "absent", "HOME": "unused"})
for fault in ("directory", "read"):
    CASES[f"load.{fault}"] = _load("" if fault == "read" else None, fault=fault)
for mode in ("db:.mir/memory.db", "db:ABS/db", "db:../escape", "db:.mir/../escape",
             "db:~/.mir/db", "raw:~/archive", "raw:ABS/archive", "arc:archive/../notes"):
    CASES[f"path.{mode}"] = lambda tmp, mode=mode: _path(tmp, mode)
for first, second in (("a", "a"), ("a", "a/b"), ("a/b", "a"), ("a", "ab")):
    CASES[f"overlap.{first}.{second}"] = lambda tmp, a=first, b=second: L._paths_overlap(
        tmp/a, tmp/b)
for name, archives in {"empty": [], "distinct": [("a", "a"), ("b", "b")],
                       "duplicate": [("a", "a"), ("a", "b")],
                       "overlap": [("a", "a"), ("b", "a/b")]}.items():
    CASES[f"archive_set.{name}"] = _load("".join(
        f'[[memory.external_archives]]\nslug="{slug}"\nroot="{root}"\n' for slug, root in archives))
for cls in (AgentRegistry, EmbeddingBackendRegistry, ProviderRegistry, SkillRegistry):
    for mode in ("normal", "empty", "unknown", "broken"):
        CASES[f"registry.{cls.__name__}.{mode}"] = _registry(cls, mode)
for mode in ("create-default", "create-denied", "create-allowed"):
    CASES[f"provider.{mode}"] = _registry(ProviderRegistry, mode)


def _archive_root(authored):
    """Distinct project, home and cwd: a relative archive root resolves against the project."""
    def run(tmp):
        for name in ("project", "home", "cwd"):
            (tmp / name).mkdir()
        archive = L.ExternalArchiveConfig.model_validate({"slug": "a", "root": authored})
        with mock.patch.dict(os.environ, {"HOME": str(tmp / "home")}), \
                mock.patch.object(Path, "home", return_value=tmp / "home"), \
                mock.patch.object(Path, "cwd", return_value=tmp / "cwd"):
            return str(L.resolve_archive_root(tmp / "project", archive)).replace(str(tmp), "<tmp>")
    return run


for _name, _authored in (("relative", "notes"), ("home", "~/notes"), ("parent", "../shared"),
                         ("dot", "./a/./b")):
    CASES[f"archive_root.{_name}"] = _archive_root(_authored)


def observe(case, tmp):
    try:
        return {"value": case(tmp)}
    except Exception as exc:  # noqa: BLE001 - freeze reference error class and message
        return {"error": [type(exc).__name__, str(exc)]}


RECORDS = json.loads(FIXTURE.read_text(encoding="ascii")) if FIXTURE.exists() else {}


def test_every_case_has_a_frozen_record():
    assert sorted(RECORDS) == sorted(CASES)


@pytest.mark.parametrize("name", sorted(CASES))
def test_reference_matches_frozen_record(name, tmp_path):
    assert observe(CASES[name], tmp_path) == RECORDS[name]
