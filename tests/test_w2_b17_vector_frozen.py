"""W2-B17-F01: records captured from the unmodified Python reference, never a port."""
from __future__ import annotations

import json
import math
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import httpx
import pytest

from mir.core.engine.memory import store
from mir.core.engine.memory import vector_index as vi
from mir.core.engine.memory.backends import omlx_http as oh

FIXTURE = Path(__file__).parent / "../native/handoff-packet/tests/fixtures/w2/b17-vector.json"


def observe(case, tmp):
    try:
        return {"value": json.loads(json.dumps(case(tmp)), parse_constant=str)}
    except Exception as exc:  # noqa: BLE001 - freeze exception class and message
        return {"error": [type(exc).__name__, str(exc).replace(str(tmp), "<tmp>")]}


def _validate(vector, dim=2):
    return lambda tmp: vi.validate_embedding(vector, expected_dim=dim)


def _database(mode):
    def run(tmp):
        loader = store._load_sqlite_vec
        def load(raw):
            return (False, "synthetic unavailable") if mode == "missing" else loader(raw)
        with mock.patch.object(store, "_load_sqlite_vec", side_effect=load):
            connection = store.connect(tmp / "synthetic.db")
        conn = connection.conn
        try:
            if mode != "missing" and not connection.vec_available:
                raise RuntimeError(connection.vec_reason)
            state = {"available": connection.vec_available, "reason": connection.vec_reason}
            state["create"] = observe(lambda _: vi.ensure_vec_table(conn, dim=2), tmp)
            if mode != "missing":
                vi.ensure_vec_table(conn, dim=2)
                for rowid, vector in [(1, [1., 0.]), (2, [0., 1.]), (3, [-1., 0.])]:
                    vi.upsert_vector(conn, rowid, vector, expected_dim=2)
                state["replace"] = observe(
                    lambda _: vi.upsert_vector(conn, 1, [0., -1.], expected_dim=2), tmp)
                state["rows"] = conn.execute(
                    "SELECT rowid, hex(embedding) FROM facts_vec ORDER BY rowid").fetchall()
                for label, query, k in [("order", [0., 1.], 3), ("ties", [0., 0.], 3),
                                        ("zero_k", [0., 0.], 0), ("shape", [1.], 2)]:
                    state[label] = observe(lambda _, q=query, n=k: vi.knn(conn, q, n), tmp)
            state["pragmas"] = {key: conn.execute(f"PRAGMA {key}").fetchone()[0]
                                for key in ("journal_mode", "synchronous", "foreign_keys")}
            state["schema"] = conn.execute(
                "SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name").fetchall()
            state["migrations"] = (conn.execute(
                "SELECT version,name FROM schema_migrations ORDER BY version").fetchall()
                if conn.execute("SELECT 1 FROM sqlite_master WHERE name='schema_migrations'")
                .fetchone() else [])
            return state
        finally:
            conn.close()
    return run


def _http(mode="ok", vectors=None, factory="init", key="synthetic-key"):
    def run(tmp):
        requests = []
        def transport(request):
            requests.append({"url": str(request.url), "method": request.method,
                             "headers": dict(request.headers), "body": json.loads(request.content),
                             "timeout": request.extensions["timeout"]})
            if mode == "timeout":
                raise httpx.TimeoutException("synthetic timeout")
            if mode == "json":
                return httpx.Response(200, content=b"{")
            body = {"data": [{"embedding": v} for v in
                             ([[1., 0.]] if vectors is None else vectors)]}
            return httpx.Response(503 if mode == "status" else 200,
                                  content=json.dumps(body).encode())
        client_type = httpx.Client
        def client(**kwargs):
            return client_type(**kwargs, transport=httpx.MockTransport(transport))
        cfg = oh._BackendCfg("https://embedding.invalid/v1/", "synthetic-model", 2,
                             7, 0.001, "SYNTHETIC_KEY", "Token")
        with mock.patch.dict(oh.os.environ, {"SYNTHETIC_KEY": key,
                                            "OMLX_API_KEY": key}, clear=True), \
                mock.patch.object(oh.httpx, "Client", side_effect=client):
            backend = (oh.build_default() if factory == "default" else
                       oh.from_config(SimpleNamespace(**vars(cfg))) if factory == "config" else
                       oh.OmlxHttpBackend(cfg))
        try:
            result = {"dim": backend.dimensions, "cfg": vars(backend._cfg),
                      "before": backend._client.is_closed}
            texts = [] if mode == "empty" else ["alpha", "\u00e9"]
            result["first"] = observe(lambda _: backend.encode(texts), tmp)
            result["after_encode"] = backend._client.is_closed
            result["second"] = observe(lambda _: backend.encode(texts), tmp)
            backend.close()
            backend.close()
            result["closed"] = backend._client.is_closed
            result["after_close"] = observe(lambda _: backend.encode(texts), tmp)
            result["requests"] = requests
            return result
        finally:
            backend.close()
    return run


CASES = {
    "validate.finite": _validate([0.6, 0.8]),
    "validate.zero": _validate([0., 0.]),
    "validate.dimension": _validate([1.]),
    "validate.empty": _validate([], 0),
    "validate.nan": _validate([math.nan, 0.]),
    "validate.inf": _validate([0., math.inf]),
    "validate.negative_inf": _validate([-math.inf, 0.]),
    "validate.bound": _validate([-10., 10.]),
    "validate.over_bound": _validate([10.001, 0.]),
    "pack.finite": lambda tmp: vi._pack_vector([0., -0., 1., -2.5, 0.1]).hex(),
    "pack.nonfinite": lambda tmp: vi._pack_vector([math.nan, math.inf, -math.inf]).hex(),
    "pack.empty": lambda tmp: vi._pack_vector([]).hex(),
    "vector.available": _database("available"),
    "vector.missing": _database("missing"),
    "http.ok": _http(),
    "http.no_key": _http(key=""),
    "http.config": _http(factory="config"),
    "http.default": _http(factory="default"),
    "http.status": _http("status"),
    "http.json": _http("json"),
    "http.timeout": _http("timeout"),
    "http.wrong_dim": _http(vectors=[[1.]]),
    "http.zero": _http(vectors=[[0., 0.]]),
    "http.norm": _http(vectors=[[2., 0.]]),
    "http.tolerance_inside": _http(vectors=[[1.0005, 0.]]),
    "http.tolerance_outside": _http(vectors=[[1.002, 0.]]),
    "http.nan": _http(vectors=[[math.nan, 0.]]),
    "http.inf": _http(vectors=[[math.inf, 0.]]),
    "http.count_empty": _http(vectors=[]),
    "http.count_excess": _http(vectors=[[1., 0.]] * 3),
    "http.empty_input": _http("empty", vectors=[]),
}
RECORDS = json.loads(FIXTURE.read_text(encoding="ascii")) if FIXTURE.exists() else {}


def test_every_case_has_a_frozen_record():
    assert sorted(RECORDS) == sorted(CASES)


@pytest.mark.parametrize("name", sorted(CASES))
def test_reference_matches_frozen_record(name, tmp_path):
    assert observe(CASES[name], tmp_path) == RECORDS[name]
