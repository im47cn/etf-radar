"""信号计分卡: 合成事件序列 -> hit_rate/CI/status 三分支 + tier 过滤 + 窗口截断."""
from __future__ import annotations

import numpy as np

from src.evidence.scorecard import (
    HIGH_TIER_ABS_MOM,
    SignalEvent,
    scorecard_rows,
)


def _events(
    rng: np.random.Generator, n_days: int, signals: tuple[str, ...] = ("resonance",),
    high_mom: bool = True,
) -> list[SignalEvent]:
    """合成事件: 每日每信号一条, |us_mom| 高于/低于高置信档阈值可切换."""
    events: list[SignalEvent] = []
    for i in range(n_days):
        for sig in signals:
            mom = (rng.uniform(0.011, 0.03) if high_mom else rng.uniform(0.001, 0.005)) \
                * (1 if i % 2 == 0 else -1)
            events.append(SignalEvent(i, sig, "t0", float(mom), 0.0))
    return events


def test_scorecard_rows_structure_and_order():
    rows = scorecard_rows(_events(np.random.default_rng(0), 200), 200)
    assert len(rows) == 6  # 3 (信号,档位) × 2 窗口
    assert [(r["signal"], r["tier"], r["window_days"]) for r in rows] == [
        ("resonance", None, 60), ("resonance", None, 120),
        ("resonance", "high", 60), ("resonance", "high", 120),
        ("transmission", None, 60), ("transmission", None, 120),
    ]
    for r in rows:
        assert 0.0 <= float(r["hit_rate"]) <= 1.0
        assert 0.0 <= float(r["ci_low"]) <= float(r["hit_rate"]) <= float(r["ci_high"]) <= 1.0
        assert r["status"] in {"consistent", "degraded", "insufficient"}


def test_scorecard_hit_rate_exact_and_ci():
    """全部同向 -> hit_rate=1, CI=1 -> consistent; 手工核对 n 与公式."""
    events = [SignalEvent(i, "resonance", "t0", 0.02 if i % 2 == 0 else -0.02,
                          0.01 if i % 2 == 0 else -0.01) for i in range(60)]
    rows = scorecard_rows(events, 60)
    r60 = rows[0]
    assert r60["n"] == 60
    assert r60["hit_rate"] == 1.0
    assert r60["ci_low"] == 1.0 and r60["ci_high"] == 1.0  # p=1 -> half=0, 截断到 [0,1]
    assert r60["status"] == "consistent"


def test_scorecard_consistent_ci_covers_baseline():
    """n=60 全中 40 (p≈0.667): CI 含基线 0.55 -> consistent."""
    events = [
        SignalEvent(i, "resonance", "t0", 0.02, 0.01 if i < 40 else -0.01)
        for i in range(60)
    ]
    rows = scorecard_rows(events, 60)
    r = rows[0]
    assert r["hit_rate"] == round(40 / 60, 4)
    assert float(r["ci_low"]) < 0.55 < float(r["ci_high"])
    assert r["status"] == "consistent"


def test_scorecard_degraded_ci_high_below_baseline():
    """n=60 仅中 20 (p≈0.333): CI 上界 < 基线 0.55 -> degraded."""
    events = [
        SignalEvent(i, "resonance", "t0", 0.02, 0.01 if i < 20 else -0.01)
        for i in range(60)
    ]
    rows = scorecard_rows(events, 60)
    r = rows[0]
    assert float(r["ci_high"]) < 0.55
    assert r["status"] == "degraded"


def test_scorecard_insufficient_small_n():
    """n<50 -> insufficient, 即使胜率极差也不断 degraded."""
    events = [SignalEvent(i, "resonance", "t0", 0.02, -0.01) for i in range(49)]
    rows = scorecard_rows(events, 49)
    r = rows[0]
    assert r["n"] == 49
    assert r["status"] == "insufficient"
    # n=0 (无事件) 也走 insufficient 而非除零
    rows0 = scorecard_rows([], 10)
    assert rows0[0]["n"] == 0 and rows0[0]["status"] == "insufficient"


def test_scorecard_high_tier_filtering():
    """高置信档仅计 |us_mom|≥1% 的事件; 弱动量事件只进整体行."""
    events = []
    for i in range(60):
        mom = 0.02 if i % 2 == 0 else 0.002  # 半数高动量
        events.append(SignalEvent(i, "resonance", "t0", mom, 0.01))
    rows = scorecard_rows(events, 60)
    by_tier = {(r["signal"], r["tier"]): r for r in rows}
    assert by_tier[("resonance", None)]["n"] == 60
    assert by_tier[("resonance", "high")]["n"] == 30
    # 高档行全部 us_mom≥阈值 (hit_rate=1 因全同向)
    assert by_tier[("resonance", "high")]["hit_rate"] == 1.0


def test_scorecard_window_truncation_by_signal_day():
    """窗口按信号日归属: 总 160 日, 60 窗口只含最近 60 日, 120 窗口含 day_index>=40."""
    old = [SignalEvent(i, "resonance", "t0", 0.02, 0.01) for i in range(100)]
    recent = [SignalEvent(100 + i, "resonance", "t0", 0.02, -0.01) for i in range(60)]
    rows = scorecard_rows(old + recent, 160)
    by_win = {(r["signal"], r["window_days"]): r for r in rows if r["tier"] is None}
    assert by_win[("resonance", 60)]["n"] == 60
    assert by_win[("resonance", 60)]["hit_rate"] == 0.0   # 最近 60 日全部反向
    assert by_win[("resonance", 120)]["n"] == 120         # day_index>=40: 旧事件后 60 条 + 新 60 条
    assert by_win[("resonance", 120)]["hit_rate"] == 0.5


def test_scorecard_transmission_baseline():
    """transmission 基线 0.49, 无 high 档行 (仅整体两行)."""
    events = [SignalEvent(i, "transmission", "t0", 0.02, 0.01) for i in range(60)]
    rows = scorecard_rows(events, 60)
    trans = [r for r in rows if r["signal"] == "transmission"]
    assert len(trans) == 2
    assert all(r["tier"] is None and r["baseline"] == 0.49 for r in trans)
    # 全同向 -> consistent (CI 上界 ≥ 0.49 显然成立)
    assert trans[0]["status"] == "consistent"


def test_high_tier_threshold_constant():
    assert HIGH_TIER_ABS_MOM == 0.01
