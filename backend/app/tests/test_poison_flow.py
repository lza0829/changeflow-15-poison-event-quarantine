"""毒丸分流端到端：两种策略各跑一遍带毒丸夹具，核对隔离区/账本/Sink/游标/报告。"""

from app.db import DB_PATH, connect
from app.engines.poison_rules import (
    POISON_POLICY_CONTINUE,
    POISON_POLICY_STOP,
    is_poison_reason,
)
from app.repositories import cursors as cursor_repo
from app.repositories import ledger as ledger_repo
from app.repositories import quarantine as quarantine_repo
from app.repositories import settings as settings_repo
from app.repositories import sink as sink_repo
from app.repositories import streams as streams_repo
from app.seed import init_db
from app.services import apply_service

POISON_STREAM_ID = 3  # seed 中第三个流：Orders CDC（含毒丸）
POISON_SEQS = {3, 5, 7}
LEGAL_SEQS = [1, 2, 4, 6, 8, 9]


def _reset_db():
    if DB_PATH.exists():
        DB_PATH.unlink()
    init_db()


def _sink_keys(conn):
    return {r["entity_key"] for r in sink_repo.list_sink(conn)}


def _ledger_map(conn, run_id):
    return {r["seq"]: r["disposition"] for r in ledger_repo.list_ledger(conn, 1000)
            if r["run_id"] == run_id}


def test_stop_on_poison_blocks_cursor_and_keeps_poison_out_of_sink():
    _reset_db()
    conn = connect()
    settings_repo.put(conn, "poison_policy", POISON_POLICY_STOP)
    conn.commit()

    run = apply_service.run_apply(POISON_STREAM_ID)
    report = run["report"]

    # 报告：毒丸 3 个，只隔离到第一个（seq3）就停住
    assert run["status"] == "stopped_poison"
    assert report["poison_in_fixture"] == 3
    assert report["stopped_on_poison"] is True
    assert report["counts"]["applied"] == 2          # seq 1,2
    assert report["counts"]["quarantined_poison"] == 1
    assert report["counts"]["quarantined_gap"] == 0
    assert report["counts"]["quarantined_total"] == run["quarantined_count"] == 1
    assert report["cursor_before"] == 0
    assert report["cursor_after"] == run["cursor_after"] == 2  # 游标不越过 seq3

    # 隔离区：原因带 poison_ 前缀，kind=poison，与缺口分得开
    q = quarantine_repo.list_quarantine(conn)
    assert len(q) == 1 and q[0]["seq"] == 3 and q[0]["kind"] == "poison"
    assert is_poison_reason(q[0]["reason"])
    assert quarantine_repo.list_quarantine(conn, kind="gap") == []
    assert len(quarantine_repo.list_quarantine(conn, kind="poison")) == 1

    # 账本：seq3 是毒丸处置，其后 seq 本 run 根本没处理
    dispositions = _ledger_map(conn, run["id"])
    assert dispositions == {1: "applied", 2: "applied", 3: "quarantine_poison_stop"}

    # Sink / applied_seqs：毒丸绝不出现
    assert "applied" not in {v for k, v in dispositions.items() if k in POISON_SEQS}
    assert POISON_SEQS.isdisjoint(
        r["seq"] for r in conn.execute(
            "SELECT seq FROM applied_seqs WHERE stream_id=?", (POISON_STREAM_ID,)
        ).fetchall()
    )
    assert _sink_keys(conn) == {"ORD-1001"}  # ORD-1002 在 seq4，被堵在毒丸之后

    # 游标页与流游标一致
    view = {r["stream_id"]: r for r in cursor_repo.list_cursor_view(conn)}
    assert view[POISON_STREAM_ID]["apply_cursor"] == 2
    assert streams_repo.get_stream(conn, POISON_STREAM_ID)["apply_cursor"] == 2
    conn.close()


def test_quarantine_and_continue_skips_poison_but_applies_later_legal_seq():
    _reset_db()
    conn = connect()
    settings_repo.put(conn, "poison_policy", POISON_POLICY_CONTINUE)
    conn.commit()

    run = apply_service.run_apply(POISON_STREAM_ID)
    report = run["report"]

    assert run["status"] == "succeeded"
    assert report["stopped_on_poison"] is False
    assert report["counts"]["applied"] == 6          # 全部合法 seq
    assert report["counts"]["quarantined_poison"] == 3
    assert report["counts"]["quarantined_gap"] == 0
    assert report["counts"]["quarantined_total"] == run["quarantined_count"] == 3
    assert report["cursor_before"] == 0
    assert report["cursor_after"] == run["cursor_after"] == 9  # 游标越过毒丸到 9

    # 隔离区三条毒丸，原因各不相同，全部 kind=poison
    qrows = quarantine_repo.list_quarantine(conn, kind="poison")
    assert {r["seq"] for r in qrows} == POISON_SEQS
    assert all(is_poison_reason(r["reason"]) for r in qrows)
    reasons = {r["seq"]: r["reason"] for r in qrows}
    assert "poison_missing_entity_key" in reasons[3]
    assert "poison_illegal_op" in reasons[5]
    assert "poison_missing_required_field" in reasons[7]
    assert quarantine_repo.list_quarantine(conn, kind="gap") == []

    # 账本：合法全 applied，毒丸全是 quarantine_poison，绝无 applied
    dispositions = _ledger_map(conn, run["id"])
    assert {s for s, d in dispositions.items() if d == "applied"} == set(LEGAL_SEQS)
    assert all(
        dispositions[s] == "quarantine_poison" for s in POISON_SEQS
    )

    # Sink：只有合法事件对应的实体，毒丸的 ORD-1004（seq7 空 payload）不在；
    # seq8 delete 合法，ORD-1002 被删后也不在
    sink_keys = _sink_keys(conn)
    assert "ORD-1004" not in sink_keys
    assert sink_keys == {"ORD-1001", "ORD-1003", "ORD-1005"}
    applied_seqs = {
        r["seq"] for r in conn.execute(
            "SELECT seq FROM applied_seqs WHERE stream_id=?", (POISON_STREAM_ID,)
        ).fetchall()
    }
    assert applied_seqs == set(LEGAL_SEQS)  # 毒丸位点 3/5/7 绝不记 applied

    view = {r["stream_id"]: r for r in cursor_repo.list_cursor_view(conn)}
    assert view[POISON_STREAM_ID]["apply_cursor"] == 9
    # 越过毒丸的游标下 applied 集合存在空洞，属预期；max_applied_seq 与游标一致
    assert view[POISON_STREAM_ID]["max_applied_seq"] == 9
    conn.close()


def test_poison_and_gap_are_separated_in_quarantine_and_ledger():
    _reset_db()
    conn = connect()
    settings_repo.put(conn, "poison_policy", POISON_POLICY_CONTINUE)
    conn.commit()
    # 手工造一条缺口：删掉 seq4 所在行（通过临时夹具不可行，直接用服务层模拟：
    # 先跑毒丸流，再向隔离区写一条 gap 行验证分类）
    apply_service.run_apply(POISON_STREAM_ID)
    quarantine_repo.insert(
        conn, stream_id=POISON_STREAM_ID, run_id=999, seq=40,
        entity_key="GAP-1", reason="gap_before_seq", payload={},
    )
    conn.commit()

    poison_rows = quarantine_repo.list_quarantine(conn, kind="poison")
    gap_rows = quarantine_repo.list_quarantine(conn, kind="gap")
    assert {r["seq"] for r in poison_rows} == POISON_SEQS
    assert [r["seq"] for r in gap_rows] == [40]
    assert all(r["kind"] == "poison" for r in poison_rows)
    assert all(r["kind"] == "gap" for r in gap_rows)
    counts = quarantine_repo.count_by_kind(conn)
    assert counts == {"poison": 3, "gap": 1}
    conn.close()


def test_policy_persists_across_runs_and_reapply_is_idempotent():
    _reset_db()
    conn = connect()
    settings_repo.put(conn, "poison_policy", POISON_POLICY_CONTINUE)
    conn.commit()
    conn.close()

    # 重新打开连接模拟配置刷新：策略仍从 settings 读出
    conn = connect()
    assert settings_repo.get(conn, "poison_policy") == POISON_POLICY_CONTINUE
    first = apply_service.run_apply(POISON_STREAM_ID)
    sink_after_first = _sink_keys(conn)
    # 再跑一次：cursor=9 覆盖全部 seq，走 duplicate 分支不重复应用、不重复隔离
    second = apply_service.run_apply(POISON_STREAM_ID)
    assert second["report"]["counts"]["applied"] == 0
    assert second["report"]["counts"]["skipped"] == 9
    assert second["report"]["counts"]["quarantined_total"] == 0
    assert _sink_keys(conn) == sink_after_first
    assert quarantine_repo.count_by_kind(conn) == {"poison": 3, "gap": 0}
    assert second["cursor_after"] == 9
    conn.close()
