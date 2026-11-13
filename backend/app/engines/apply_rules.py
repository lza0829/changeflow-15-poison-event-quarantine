from __future__ import annotations

from typing import Any

from app.engines.poison_rules import (
    POISON_POLICY_CONTINUE,
    POISON_POLICY_STOP,
)


def next_expected_seq(cursor: int) -> int:
    return int(cursor) + 1


def classify_event(
    *,
    event: dict[str, Any],
    cursor: int,
    already_applied: bool,
    gap_policy: str = "stop_quarantine",
    poison_policy: str = POISON_POLICY_STOP,
) -> str:
    """裁决单条事件的处置（纯标签，不含副作用）。

    返回值：
      skipped_duplicate       重复/已应用 seq
      apply                   合法且续序，可应用
      quarantine_gap          seq 缺口（事件本身合法），隔离
      quarantine_poison_stop  毒丸 + 停住策略：隔离并阻断后续
      quarantine_poison       毒丸 + 隔离继续策略：隔离，游标可越过

    毒丸判定优先于缺口判定：结构坏掉的事件即使正好续序也绝不能应用。
    """
    seq = int(event["seq"])
    if already_applied or seq <= cursor:
        return "skipped_duplicate"

    if event.get("poison_reasons"):
        if poison_policy == POISON_POLICY_CONTINUE:
            return "quarantine_poison"
        return "quarantine_poison_stop"

    expected = next_expected_seq(cursor)
    if seq > expected:
        if gap_policy == "skip_gap":
            return "apply"  # 预留给 gap_wait_or_skip；seed 默认 stop_quarantine
        return "quarantine_gap"
    if seq < expected:
        return "skipped_duplicate"
    return "apply"
