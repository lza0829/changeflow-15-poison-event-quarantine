"""毒丸（结构损坏事件）识别规则与分流策略常量。

毒丸 = 事件本身结构坏掉，无法安全应用。与“缺口”（seq 不连续，事件本身合法）
是两类问题，识别结果与隔离原因都必须能区分开。

可复现的毒丸规则（命中任意一条即判定为毒丸，可同时命中多条）：

1. poison_missing_entity_key —— 缺实体键
   entity_key 缺失、不是字符串，或为空白字符串。没有实体键的变更无法定位
   sink 行，应用即假账。
2. poison_illegal_op —— 非法 op
   op 缺失或不在允许集合 {"upsert", "delete"} 内（例如 "merge"）。
3. poison_missing_required_field —— 关键字段缺失
   upsert 事件的 payload 不是 JSON 对象，或是空对象（没有携带任何业务
   字段，等于没有可落库的变更内容）。delete 的空 payload 合法，不触发。

两种互斥分流策略（settings.poison_policy，可保存、刷新后仍生效）：

- stop_on_poison：毒丸处停住。毒丸进隔离区，其后事件本 run 不应用，
  apply_cursor 停在毒丸前一个合法 seq，绝不越过毒丸位点。
- quarantine_and_continue：隔离毒丸后继续。毒丸进隔离区且绝不记
  applied，游标可越过毒丸位点，后续合法 seq 正常应用。

注意：整行 JSON 无法解析、seq 缺失/非整数属于文件级损坏，解析器直接
报错终止本次 run，不进毒丸分流（毒丸至少要能定位到 seq）。
"""

from __future__ import annotations

from typing import Any

POISON_MISSING_ENTITY_KEY = "poison_missing_entity_key"
POISON_ILLEGAL_OP = "poison_illegal_op"
POISON_MISSING_REQUIRED_FIELD = "poison_missing_required_field"

POISON_REASON_PREFIX = "poison_"

ALLOWED_OPS = ("upsert", "delete")

POISON_POLICY_STOP = "stop_on_poison"
POISON_POLICY_CONTINUE = "quarantine_and_continue"
POISON_POLICIES = (POISON_POLICY_STOP, POISON_POLICY_CONTINUE)
DEFAULT_POISON_POLICY = POISON_POLICY_STOP


def detect_poison(raw: dict[str, Any]) -> list[str]:
    """对单条原始 JSON 对象跑毒丸规则，返回命中的原因 code 列表（空=合法事件）。"""
    reasons: list[str] = []

    entity_key = raw.get("entity_key")
    if not isinstance(entity_key, str) or not entity_key.strip():
        reasons.append(POISON_MISSING_ENTITY_KEY)

    op_raw = raw.get("op")
    op = op_raw.strip().lower() if isinstance(op_raw, str) else ""
    if op not in ALLOWED_OPS:
        reasons.append(POISON_ILLEGAL_OP)

    payload = raw.get("payload")
    if op == "upsert":
        if not isinstance(payload, dict) or len(payload) == 0:
            reasons.append(POISON_MISSING_REQUIRED_FIELD)

    return reasons


def is_poison_reason(reason: str) -> bool:
    return reason.startswith(POISON_REASON_PREFIX)
