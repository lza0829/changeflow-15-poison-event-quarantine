from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.engines.poison_rules import detect_poison


def parse_change_fixture(path: Path) -> list[dict[str, Any]]:
    """解析 JSONL 夹具。

    整行 JSON 解析失败、seq 缺失/非整数属于文件级损坏：直接抛错终止 run，
    因为连 seq 都无法定位，无法做按序分流。

    字段级损坏（缺实体键、非法 op、关键字段缺失）不再抛错，而是打上
    poison_reasons 标签，由应用引擎按毒丸策略自动分流。
    """
    if not path.exists():
        raise FileNotFoundError(f"fixture missing: {path}")
    events: list[dict[str, Any]] = []
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid jsonl at line {line_no}: {exc}") from exc
        if not isinstance(obj, dict):
            raise ValueError(f"event at line {line_no} is not a json object")
        if "seq" not in obj:
            raise ValueError(f"missing seq at line {line_no}")
        try:
            seq = int(obj["seq"])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"invalid seq at line {line_no}: {obj.get('seq')!r}") from exc

        poison_reasons = detect_poison(obj)

        # 毒丸字段可能缺失或类型不对，统一给出可落库的占位值，不再抛错。
        op_raw = obj.get("op")
        op = op_raw.strip().lower() if isinstance(op_raw, str) and op_raw.strip() else "unknown"
        entity_key = obj.get("entity_key") if isinstance(obj.get("entity_key"), str) else ""
        event_ts = obj.get("event_ts") if isinstance(obj.get("event_ts"), str) else ""
        payload = obj.get("payload") if isinstance(obj.get("payload"), dict) else {}

        events.append(
            {
                "seq": seq,
                "op": op,
                "entity_key": entity_key,
                "event_ts": event_ts,
                "payload": payload,
                "poison_reasons": poison_reasons,
                "line_no": line_no,
            }
        )
    events.sort(key=lambda e: e["seq"])
    return events
