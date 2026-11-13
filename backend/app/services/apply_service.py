from __future__ import annotations

from typing import Any

from app.config import FIXTURES_DIR
from app.db import connect
from app.engines.apply_rules import classify_event
from app.engines.parse_change import parse_change_fixture
from app.engines.poison_rules import (
    DEFAULT_POISON_POLICY,
    POISON_POLICY_CONTINUE,
    POISON_POLICY_STOP,
    POISON_POLICIES,
)
from app.repositories import cursors as cursor_repo
from app.repositories import ledger as ledger_repo
from app.repositories import quarantine as quarantine_repo
from app.repositories import runs as runs_repo
from app.repositories import settings as settings_repo
from app.repositories import sink as sink_repo
from app.repositories import streams as streams_repo


def preview_stream(stream_id: int) -> dict[str, Any]:
    conn = connect()
    try:
        stream = streams_repo.get_stream(conn, stream_id)
        if not stream:
            raise ValueError("stream not found")
        path = FIXTURES_DIR / stream["fixture_path"]
        events = parse_change_fixture(path)
        return {"stream": stream, "count": len(events), "events": events[:50]}
    finally:
        conn.close()


def run_apply(stream_id: int) -> dict[str, Any]:
    conn = connect()
    try:
        stream = streams_repo.get_stream(conn, stream_id)
        if not stream:
            raise ValueError("stream not found")
        if not stream["enabled"]:
            raise ValueError("stream disabled")

        cursor_before = int(stream["apply_cursor"] or 0)
        gap_policy = settings_repo.get(conn, "gap_policy", "stop_quarantine") or "stop_quarantine"
        poison_policy = (
            settings_repo.get(conn, "poison_policy", DEFAULT_POISON_POLICY)
            or DEFAULT_POISON_POLICY
        )
        if poison_policy not in POISON_POLICIES:
            poison_policy = DEFAULT_POISON_POLICY
        run_id = runs_repo.create_run(conn, stream_id, cursor_before)
        path = FIXTURES_DIR / stream["fixture_path"]

        try:
            events = parse_change_fixture(path)
        except Exception as exc:  # noqa: BLE001
            runs_repo.finish_run(
                conn,
                run_id,
                status="failed",
                loaded=0,
                applied=0,
                quarantined=0,
                skipped=0,
                cursor_after=cursor_before,
                report={"error": str(exc)},
            )
            conn.commit()
            raise

        loaded = len(events)
        poison_in_fixture = sum(1 for e in events if e.get("poison_reasons"))
        applied = 0
        quarantined = 0
        poison_quarantined = 0
        gap_quarantined = 0
        skipped = 0
        cursor = cursor_before
        dispositions: list[str] = []
        poison_seen: list[dict[str, Any]] = []
        stop_reason: str | None = None  # "gap" | "poison"

        for event in events:
            already = cursor_repo.is_applied(conn, stream_id, int(event["seq"]))
            decision = classify_event(
                event=event,
                cursor=cursor,
                already_applied=already,
                gap_policy=gap_policy,
                poison_policy=poison_policy,
            )

            if decision == "skipped_duplicate":
                ledger_repo.insert_ledger(
                    conn, stream_id=stream_id, run_id=run_id, event=event, disposition=decision
                )
                skipped += 1
                dispositions.append(decision)
                continue

            if decision in ("quarantine_gap", "quarantine_poison_stop", "quarantine_poison"):
                is_poison = decision != "quarantine_gap"
                if is_poison:
                    # 毒丸原因必须能看出是毒丸：reason 带 poison_ 前缀，多规则用 | 连接。
                    reason = "|".join(event["poison_reasons"])
                else:
                    reason = "gap_before_seq"
                ledger_repo.insert_ledger(
                    conn, stream_id=stream_id, run_id=run_id, event=event, disposition=decision
                )
                quarantine_repo.insert(
                    conn,
                    stream_id=stream_id,
                    run_id=run_id,
                    seq=int(event["seq"]),
                    entity_key=event["entity_key"],
                    reason=reason,
                    payload=event.get("payload") or {},
                )
                quarantined += 1
                dispositions.append(decision)
                if is_poison:
                    poison_quarantined += 1
                    poison_seen.append(
                        {"seq": int(event["seq"]), "reasons": list(event["poison_reasons"])}
                    )
                else:
                    gap_quarantined += 1

                if decision == "quarantine_poison_stop":
                    # 停住策略：毒丸自身不 applied、不进 sink，游标不越过，其后事件不处理。
                    stop_reason = "poison"
                    break
                if decision == "quarantine_gap":
                    stop_reason = "gap"
                    break
                # quarantine_poison：隔离后继续。游标是“消费位点”，越过毒丸位点
                # （后续合法 seq 才能续序应用），但毒丸不写 applied_seqs、不进 Sink。
                cursor = int(event["seq"])
                streams_repo.set_cursor(conn, stream_id, cursor)
                continue

            # apply —— 走到这里的一定是结构合法且续序的事件
            if event["op"] == "upsert":
                sink_repo.upsert(
                    conn,
                    stream_id=stream_id,
                    entity_key=event["entity_key"],
                    payload=event.get("payload") or {},
                    seq=int(event["seq"]),
                    event_ts=event["event_ts"],
                )
            else:
                sink_repo.delete(conn, stream_id=stream_id, entity_key=event["entity_key"])

            cursor_repo.mark_applied(conn, stream_id, int(event["seq"]), run_id)
            cursor = int(event["seq"])
            streams_repo.set_cursor(conn, stream_id, cursor)
            ledger_repo.insert_ledger(
                conn, stream_id=stream_id, run_id=run_id, event=event, disposition="applied"
            )
            applied += 1
            dispositions.append("applied")

        if stop_reason == "poison":
            status = "stopped_poison"
        elif stop_reason == "gap":
            status = "partial"
        else:
            status = "succeeded"

        report = {
            "stream_id": stream_id,
            "gap_policy": gap_policy,
            "poison_policy": poison_policy,
            "poison_policy_label": (
                "毒丸处停住" if poison_policy == POISON_POLICY_STOP else "隔离毒丸后继续"
            ),
            "dispositions": dispositions,
            "stop_reason": stop_reason,
            "stopped_on_gap": stop_reason == "gap",
            "stopped_on_poison": stop_reason == "poison",
            "poison_in_fixture": poison_in_fixture,
            "counts": {
                "loaded": loaded,
                "applied": applied,
                "quarantined_total": quarantined,
                "quarantined_poison": poison_quarantined,
                "quarantined_gap": gap_quarantined,
                "skipped": skipped,
            },
            "poison_events": poison_seen,
            "cursor_before": cursor_before,
            "cursor_after": cursor,
            "sink_count_after": sink_repo.count_sink(conn),
            "quarantine_count_after": quarantine_repo.count_quarantine(conn),
            "quarantine_kinds_after": quarantine_repo.count_by_kind(conn),
        }
        runs_repo.finish_run(
            conn,
            run_id,
            status=status,
            loaded=loaded,
            applied=applied,
            quarantined=quarantined,
            skipped=skipped,
            cursor_after=cursor,
            report=report,
        )
        conn.commit()
        return runs_repo.get_run(conn, run_id) or {}
    finally:
        conn.close()
