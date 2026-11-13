"""解析器：字段级损坏打毒丸标签，文件级损坏（坏 JSON / 坏 seq）硬报错。"""

import json
from pathlib import Path

import pytest

from app.engines.parse_change import parse_change_fixture


def _write(tmp_path: Path, lines: list[str]) -> Path:
    p = tmp_path / "f.jsonl"
    p.write_text("\n".join(lines), encoding="utf-8")
    return p


def test_parse_flags_poison_without_raising(tmp_path):
    p = _write(
        tmp_path,
        [
            json.dumps({"seq": 1, "op": "upsert", "entity_key": "k",
                        "event_ts": "t", "payload": {"a": 1}}),
            json.dumps({"seq": 2, "op": "merge", "entity_key": "k2"}),
            json.dumps({"seq": 3, "op": "upsert", "payload": {}}),
        ],
    )
    events = parse_change_fixture(p)
    assert events[0]["poison_reasons"] == []
    assert events[1]["poison_reasons"] == ["poison_illegal_op"]
    # 毒丸字段给占位值，不抛异常
    assert events[2]["entity_key"] == ""
    assert "poison_missing_entity_key" in events[2]["poison_reasons"]
    assert "poison_missing_required_field" in events[2]["poison_reasons"]


def test_parse_hard_errors_for_file_level_corruption(tmp_path):
    bad_json = _write(tmp_path, ['{"seq": 1, broken'])
    with pytest.raises(ValueError, match="invalid jsonl"):
        parse_change_fixture(bad_json)

    missing_seq = _write(tmp_path, [json.dumps({"op": "upsert", "entity_key": "k"})])
    with pytest.raises(ValueError, match="missing seq"):
        parse_change_fixture(missing_seq)

    bad_seq = _write(tmp_path, [json.dumps({"seq": "x", "op": "upsert"})])
    with pytest.raises(ValueError, match="invalid seq"):
        parse_change_fixture(bad_seq)


def test_clean_fixtures_remain_poison_free(tmp_path):
    from app.config import FIXTURES_DIR

    for name in ("orders_cdc.jsonl", "inventory_cdc.jsonl"):
        events = parse_change_fixture(FIXTURES_DIR / name)
        assert events, name
        assert all(not e["poison_reasons"] for e in events), name


def test_poison_fixture_has_legal_events_after_each_poison():
    from app.config import FIXTURES_DIR

    events = parse_change_fixture(FIXTURES_DIR / "orders_cdc_poison.jsonl")
    poison_seqs = {e["seq"] for e in events if e["poison_reasons"]}
    legal_seqs = [e["seq"] for e in events if not e["poison_reasons"]]
    assert poison_seqs == {3, 5, 7}
    # 最后一个毒丸 seq7 之后仍有合法 seq 8、9
    assert legal_seqs[-2:] == [8, 9]
