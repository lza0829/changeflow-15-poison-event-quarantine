from app.engines.apply_rules import classify_event, next_expected_seq
from app.engines.poison_rules import (
    POISON_ILLEGAL_OP,
    POISON_MISSING_ENTITY_KEY,
    POISON_MISSING_REQUIRED_FIELD,
    POISON_POLICY_CONTINUE,
    POISON_POLICY_STOP,
    detect_poison,
)


def test_next_expected():
    assert next_expected_seq(0) == 1
    assert next_expected_seq(4) == 5


def test_classify_apply_and_gap():
    event = {"seq": 1, "op": "upsert", "entity_key": "A", "event_ts": "t", "payload": {}}
    assert classify_event(event=event, cursor=0, already_applied=False) == "apply"
    gap = {"seq": 3, "op": "upsert", "entity_key": "A", "event_ts": "t", "payload": {}}
    assert classify_event(event=gap, cursor=1, already_applied=False) == "quarantine_gap"
    assert (
        classify_event(event=event, cursor=0, already_applied=True) == "skipped_duplicate"
    )


def _poison(seq, **overrides):
    event = {
        "seq": seq,
        "op": "upsert",
        "entity_key": f"K{seq}",
        "event_ts": "t",
        "payload": {"x": 1},
        "poison_reasons": [POISON_ILLEGAL_OP],
    }
    event.update(overrides)
    return event


def test_poison_rules_are_reproducible():
    assert detect_poison(
        {"seq": 1, "op": "upsert", "event_ts": "t", "payload": {"x": 1}}
    ) == [POISON_MISSING_ENTITY_KEY]
    assert detect_poison({"seq": 1, "op": "merge", "entity_key": "k"}) == [POISON_ILLEGAL_OP]
    assert detect_poison(
        {"seq": 1, "op": "upsert", "entity_key": "k", "payload": {}}
    ) == [POISON_MISSING_REQUIRED_FIELD]
    assert detect_poison(
        {"seq": 1, "op": "delete", "entity_key": "k", "payload": {}}
    ) == []  # delete 的空 payload 合法
    legal = {"seq": 1, "op": "upsert", "entity_key": "k", "payload": {"x": 1}}
    assert detect_poison(legal) == []


def test_poison_classified_before_gap_and_policy_switches_decision():
    # 毒丸即使正好续序也不能应用
    poison = _poison(2)
    assert (
        classify_event(
            event=poison, cursor=1, already_applied=False,
            poison_policy=POISON_POLICY_STOP,
        )
        == "quarantine_poison_stop"
    )
    assert (
        classify_event(
            event=poison, cursor=1, already_applied=False,
            poison_policy=POISON_POLICY_CONTINUE,
        )
        == "quarantine_poison"
    )
    # 毒丸 + 缺口同时存在时，毒丸标签优先（结构坏掉优先于序问题）
    far_poison = _poison(9)
    assert classify_event(
        event=far_poison, cursor=1, already_applied=False,
        poison_policy=POISON_POLICY_STOP,
    ).startswith("quarantine_poison")
