"""变化计算核心单测：A/C/D 触发、聚合降噪、温度边界钉死、prev-day 回溯。"""
from __future__ import annotations

import pytest

from src.notify.changes import (
    ItemChange,
    TemperatureChange,
    build_watchlist_changes,
    diff_item,
    diff_temperature,
    find_prev_snapshot_dir,
    index_strength_by_key,
    latest_market_rate,
    temperature_tier,
)


def _s(short: int, long: int, composite: int) -> dict[str, int | None]:
    return {"short": short, "mid": 50, "long": long, "composite": composite}


# ========== C：温度边界钉死（防与前端 breadthColor.ts 的 30/50/70 漂移） ==========
@pytest.mark.parametrize(
    "rate,expected",
    [
        (0, "冰点"),
        (29.9, "冰点"),
        (30, "偏冷"),
        (49.9, "偏冷"),
        (50, "偏暖"),
        (69.9, "偏暖"),
        (70, "过热"),
        (100, "过热"),
    ],
)
def test_temperature_tier_boundaries(rate: float, expected: str) -> None:
    assert temperature_tier(rate) == expected


def test_temperature_tier_none() -> None:
    assert temperature_tier(None) is None


# ========== C：温度档切换 / 未切 / 缺失跳过 ==========
def test_diff_temperature_switch_up() -> None:
    ch = diff_temperature(29.0, 55.0)
    assert isinstance(ch, TemperatureChange)
    assert ch.tier_prev == "冰点" and ch.tier_now == "偏暖"
    assert ch.direction == "up"


def test_diff_temperature_switch_down() -> None:
    ch = diff_temperature(72.0, 40.0)
    assert ch is not None and ch.direction == "down"
    assert ch.tier_prev == "过热" and ch.tier_now == "偏冷"


def test_diff_temperature_same_tier_no_change() -> None:
    # 33 与 40 同处「偏冷」→ 不触发
    assert diff_temperature(33.0, 40.0) is None


def test_diff_temperature_missing_skips() -> None:
    assert diff_temperature(None, 55.0) is None
    assert diff_temperature(40.0, None) is None
    assert diff_temperature(None, None) is None


# ========== A：象限迁移 / 未迁移 ==========
def test_diff_item_quadrant_moved() -> None:
    # long 从 <50 到 ≥50 → 象限变；composite 也升
    ch = diff_item("theme", "t1", "半导体", _s(60, 40, 45), _s(60, 55, 61))
    assert ch is not None
    assert ch.kind == "A"
    assert ch.direction == "up"
    assert ch.composite_prev == 45 and ch.composite_now == 61


def test_diff_item_quadrant_not_moved_no_cross() -> None:
    # 同象限（都 long≥50 short≥50）、composite 都在强侧 → 无变化
    assert diff_item("theme", "t1", "x", _s(80, 80, 70), _s(75, 78, 66)) is None


# ========== D：composite 上穿 / 下穿 / 未跨 ==========
def test_diff_item_composite_cross_up_only() -> None:
    # 象限不变（short/long 都保持强侧），仅 composite 从 <50 上穿
    ch = diff_item("etf", "512480", "半导体ETF", _s(60, 60, 48), _s(60, 60, 52))
    assert ch is not None
    assert ch.kind == "D"
    assert ch.direction == "up"


def test_diff_item_composite_cross_down_only() -> None:
    ch = diff_item("theme", "t2", "y", _s(60, 60, 55), _s(55, 55, 45))
    assert ch is not None and ch.kind == "D" and ch.direction == "down"


def test_diff_item_composite_no_cross() -> None:
    # 都在强侧、象限不变 → 无变化
    assert diff_item("theme", "t3", "z", _s(60, 60, 55), _s(62, 62, 58)) is None


# ========== 聚合降噪：同标的 A+D 合并为一行，优先级 A>D ==========
def test_diff_item_a_and_d_merge_prefers_a() -> None:
    # long 从 40→55（象限变，A）且 composite 从 48→52（跨 50，D）→ 合并一行，kind=A
    ch = diff_item("theme", "t4", "存储", _s(60, 40, 48), _s(60, 55, 52))
    assert ch is not None
    assert ch.kind == "A"  # A 优先
    assert ch.composite_prev == 48 and ch.composite_now == 52


# ========== 缺失降级 ==========
def test_diff_item_missing_now_strength() -> None:
    assert diff_item("theme", "t", "n", _s(60, 40, 45), None) is None


def test_diff_item_missing_prev_strength_no_a_but_d_uses_now() -> None:
    # prev 缺失 → A 不触发、D 也无 prev composite → 无变化
    assert diff_item("theme", "t", "n", None, _s(60, 60, 61)) is None


# ========== latest_market_rate：取全市场 ma20 最新值 ==========
def test_latest_market_rate_ok() -> None:
    temp = {"periods": {"ma20": {"market": [
        {"date": "2026-07-02", "rate": 33.5},
        {"date": "2026-07-03", "rate": 40.3},
    ]}}}
    assert latest_market_rate(temp) == 40.3


def test_latest_market_rate_missing() -> None:
    assert latest_market_rate(None) is None
    assert latest_market_rate({}) is None
    assert latest_market_rate({"periods": {"ma20": {"market": []}}}) is None


# ========== prev-day 目录回溯（非目录名减一天） ==========
def test_find_prev_snapshot_dir() -> None:
    dirs = ["2026-07-02", "2026-07-03", "2026-07-06", "2026-07-07"]
    # 07-07 的上一交易日是 07-06（跳过周末，目录名减一天=07-06 恰好对，但换 07-06 验证跨周末）
    assert find_prev_snapshot_dir(dirs, "2026-07-06") == "2026-07-03"
    assert find_prev_snapshot_dir(dirs, "2026-07-07") == "2026-07-06"


def test_find_prev_snapshot_dir_none() -> None:
    assert find_prev_snapshot_dir(["2026-07-07"], "2026-07-07") is None
    assert find_prev_snapshot_dir([], "2026-07-07") is None


# ========== build_watchlist_changes：整合 + 空自选 ==========
def test_build_watchlist_changes_empty() -> None:
    assert build_watchlist_changes([], {}, {}) == []


def test_build_watchlist_changes_filters_unchanged() -> None:
    prev_index = {
        "theme": {"t1": _s(60, 40, 45), "t2": _s(60, 60, 55)},
        "etf": {},
    }
    now_index = {
        "theme": {"t1": _s(60, 55, 61), "t2": _s(62, 62, 58)},  # t1 变、t2 不变
        "etf": {},
    }
    watchlist: list = [("theme", "t1", "半导体"), ("theme", "t2", "白酒")]
    changes = build_watchlist_changes(watchlist, prev_index, now_index)
    assert len(changes) == 1
    assert isinstance(changes[0], ItemChange)
    assert changes[0].item_key == "t1" and changes[0].kind == "A"


# ========== index_strength_by_key ==========
def test_index_strength_by_key() -> None:
    themes = [
        {"id": "a", "strength": _s(1, 2, 3)},
        {"id": "b"},  # 无 strength → 空 dict
        {"name": "no-id"},  # 无 key → 跳过
    ]
    idx = index_strength_by_key(themes, "id")
    assert idx["a"]["composite"] == 3
    assert idx["b"] == {}
    assert "no-id" not in idx
