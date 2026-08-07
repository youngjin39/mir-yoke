"""'mir migrate' CLI — SQL schema migrations only.

This is the public template version. Only 'up' and 'status' are supported.
The full migrate surface (apply/rollback/preserve/dry-run) lives in the Mir
private harness and requires additional heavy deps.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from mir.core.engine.memory import store

from ._common import default_db_path


def _parse(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="mir migrate")
    sub = p.add_subparsers(dest="action", required=True)

    up = sub.add_parser("up", help="apply pending SQL migrations")
    up.add_argument("--db", type=Path, default=None)

    status = sub.add_parser("status", help="show current schema version")
    status.add_argument("--db", type=Path, default=None)

    return p.parse_args(argv)


def _cmd_up(ns) -> int:
    db_path = ns.db or default_db_path()
    conn = store.connect(db_path)
    try:
        applied = store.apply_migrations(conn.conn)
        version = store.schema_version(conn.conn)
        if applied:
            print("applied {}: {}".format(len(applied), ", ".join(applied)))
        else:
            print("already up to date")
        print(f"schema_version: {version}")
        vec_status = "ok" if conn.vec_available else "unavailable"
        print(f"sqlite-vec: {vec_status}")
    finally:
        conn.conn.close()
    return 0


def _cmd_status(ns) -> int:
    db_path = ns.db or default_db_path()
    conn = store.connect(db_path)
    try:
        version = store.schema_version(conn.conn)
        print("schema_version: {}".format(version or "(none)"))
    finally:
        conn.conn.close()
    return 0


def main(argv: list[str]) -> int:
    ns = _parse(argv)
    if ns.action == "up":
        return _cmd_up(ns)
    if ns.action == "status":
        return _cmd_status(ns)
    return 2
