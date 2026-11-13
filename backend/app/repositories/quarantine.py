from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from app.engines.poison_rules import POISON_REASON_PREFIX


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def insert(
    conn: sqlite3.Connection,
    *,
    stream_id: int,
    run_id: int,
    seq: int,
    entity_key: str,
    reason: str,
    payload: dict[str, Any],
) -> None:
    conn.execute(
        """
        INSERT INTO quarantine(stream_id, run_id, seq, entity_key, reason, payload_json, created_at)
        VALUES (?,?,?,?,?,?,?)
        """,
        (
            stream_id,
            run_id,
            seq,
            entity_key,
            reason,
            json.dumps(payload, ensure_ascii=False),
            _now(),
        ),
    )


def list_quarantine(
    conn: sqlite3.Connection, kind: str | None = None
) -> list[dict[str, Any]]:
    # kind 由 reason 前缀派生：poison_* 为毒丸，其余为缺口，不加表结构迁移。
    if kind == "poison":
        where = "WHERE reason LIKE ?"
        params: tuple[Any, ...] = (POISON_REASON_PREFIX + "%",)
    elif kind == "gap":
        where = "WHERE reason NOT LIKE ?"
        params = (POISON_REASON_PREFIX + "%",)
    else:
        where = ""
        params = ()
    rows = conn.execute(
        f"""
        SELECT id, stream_id, run_id, seq, entity_key, reason, payload_json, created_at,
               CASE WHEN reason LIKE '{POISON_REASON_PREFIX}%' THEN 'poison' ELSE 'gap' END AS kind
        FROM quarantine {where}
        ORDER BY id DESC
        """,
        params,
    ).fetchall()
    out = []
    for r in rows:
        item = dict(r)
        item["payload"] = json.loads(item.pop("payload_json") or "{}")
        out.append(item)
    return out


def count_quarantine(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT COUNT(*) c FROM quarantine").fetchone()["c"])


def count_by_kind(conn: sqlite3.Connection) -> dict[str, int]:
    row = conn.execute(
        f"""
        SELECT
            SUM(CASE WHEN reason LIKE '{POISON_REASON_PREFIX}%' THEN 1 ELSE 0 END) AS poison,
            SUM(CASE WHEN reason NOT LIKE '{POISON_REASON_PREFIX}%' THEN 1 ELSE 0 END) AS gap
        FROM quarantine
        """
    ).fetchone()
    return {"poison": int(row["poison"] or 0), "gap": int(row["gap"] or 0)}
