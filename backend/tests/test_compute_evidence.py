"""compute_evidence 端到端: 合成 snapshots -> 校验 signal_evidence 字段齐全."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from scripts.compute_evidence import TREND_LIMIT_120, compute_evidence, grid_fitness_per_theme
from src.evidence.stats_utils import arch_per_theme


def _make_themes(rng: np.random.Generator, n_themes: int = 8) -> list[dict[str, object]]:
    return [
        {
            "id": f"t{i}",
            "name": f"主题{i}",
            "cn_strength": {"composite": int(rng.integers(0, 100))},
            "returns": {"r_1d": float(rng.normal(scale=0.01))},
        }
        for i in range(n_themes)
    ]


def test_compute_evidence_writes_all_fields(tmp_path):
    rng = np.random.default_rng(0)
    snap = tmp_path / "snapshots"
    n_days = 80
    for i in range(n_days):
        d = f"2021-01-{i + 1:02d}"  # 字符串日期 (load 只排序, 不校验真实日历)
        (snap / d).mkdir(parents=True, exist_ok=True)
        with open(snap / d / "themes.json", "w") as f:
            json.dump({"themes": _make_themes(rng)}, f)

    result = compute_evidence(tmp_path, horizon=20)

    # 顶层结构
    assert result["schema_version"] == "1.0"
    assert result["as_of_date"]
    assert set(result["sample"]) == {"start", "end", "n_days"}
    assert result["sample"]["n_days"] == n_days

    # IC: by_horizon 3 档 + rolling 非空 (80日 window60 horizon20 至少1点)
    ic = result["ic"]
    assert {e["horizon"] for e in ic["by_horizon"]} == {1, 5, 20}
    assert len(ic["rolling"]) > 0
    assert {"ic_5", "ic_20", "ic_60"} <= set(ic["rolling"][0])

    # ARCH: 8 主题 + summary + 代表 ACF
    arch = result["arch"]
    assert len(arch["themes"]) == 8
    for e in arch["themes"]:
        assert {"theme_id", "name", "n", "r2_lb_p", "is_arch", "ret_lb_p"} <= set(e)
    assert arch["summary"]["tested"] == 8
    assert arch["summary"]["arch_count"] <= 8
    assert len(arch["representative_acf"]) == 8  # 全主题 (8 个, 非 4 代表)
    for v in arch["representative_acf"].values():
        assert len(v) == 16  # acf lag 0..15

    # 滚动时序需 ≥120 日; 80 日样本不足 -> time_series 为空
    assert arch["time_series"] == []

    # 网格适配度: 80 日 < Hurst min_samples=100 -> 全跳过
    grid = result["grid_fitness"]
    assert grid["themes"] == []
    assert grid["summary"]["skipped"] == 8
    assert grid["summary"]["tested"] == 0
    assert {"vol", "mean_reversion", "arch"} <= set(grid["weights"])


def test_compute_evidence_arch_time_series_rolling_120d(tmp_path):
    """120 日滚动窗口按月步进: 5 月×30 日=150 日, 前 3 月凑不满 120 跳过, 04/05 产出."""
    rng = np.random.default_rng(2)
    snap = tmp_path / "snapshots"
    for month in range(1, 6):           # 2021-01 .. 2021-05, 各 30 日
        for day in range(1, 31):
            d = f"2021-{month:02d}-{day:02d}"
            (snap / d).mkdir(parents=True, exist_ok=True)
            with open(snap / d / "themes.json", "w") as f:
                json.dump({"themes": _make_themes(rng)}, f)

    ts = compute_evidence(tmp_path)["arch"]["time_series"]
    # 01/02/03 月末 idx (29/59/89) < 119 跳过; 04(idx119)/05(idx149) 产出
    assert [e["period"] for e in ts] == ["2021-04", "2021-05"]
    assert all(e["tested"] == 8 for e in ts)        # 120 日窗口, 每主题有效值 ≥40
    assert all("is_partial" not in e for e in ts)   # 滚动窗口无 partial 概念


def test_compute_evidence_arch_sorted_by_significance(tmp_path):
    rng = np.random.default_rng(1)
    snap = tmp_path / "snapshots"
    for i in range(80):
        (snap / f"2021-01-{i + 1:02d}").mkdir(parents=True, exist_ok=True)
        with open(snap / f"2021-01-{i + 1:02d}" / "themes.json", "w") as f:
            json.dump({"themes": _make_themes(rng)}, f)
    arch = compute_evidence(tmp_path)["arch"]
    ps = [float(e["r2_lb_p"]) for e in arch["themes"]]
    assert ps == sorted(ps)  # 按 r2_lb_p 升序 (最显著在前)


def test_grid_fitness_sorted_and_verdicts(tmp_path):
    """150日×8主题 (≥Hurst 下限 100): themes 非空, grid_score 降序, verdict 合法."""
    rng = np.random.default_rng(3)
    snap = tmp_path / "snapshots"
    for month in range(1, 6):           # 2021-01..05 各 30 日 = 150 日 (合法日期, ≥Hurst 下限 100)
        for day in range(1, 31):
            d = f"2021-{month:02d}-{day:02d}"
            (snap / d).mkdir(parents=True, exist_ok=True)
            with open(snap / d / "themes.json", "w") as f:
                json.dump({"themes": _make_themes(rng)}, f)
    grid = compute_evidence(tmp_path)["grid_fitness"]
    themes = grid["themes"]
    assert len(themes) == 8
    scores = [float(t["grid_score"]) for t in themes]
    assert scores == sorted(scores, reverse=True)  # 降序
    expected_fields = {"theme_id", "name", "n", "ann_vol", "hurst", "arch_neg_log10p",
                       "ret_60d", "ret_120d", "trend_regime",
                       "pct_vol", "pct_mean_reversion", "pct_arch", "grid_score", "verdict"}
    for t in themes:
        assert expected_fields <= set(t)
        assert t["verdict"] in {"suitable", "marginal", "unsuitable"}
    assert grid["summary"]["tested"] == 8
    assert grid["summary"]["suitable_count"] == sum(
        1 for t in themes if t["verdict"] == "suitable")


def test_trend_regime_detection():
    """趋势护栏阈值判定: 对称阈值, 60/120 双窗口, None 透传."""
    from scripts.compute_evidence import trend_regime
    assert trend_regime(None, None) is None            # 数据不足 -> 震荡
    assert trend_regime(0.05, -0.08) is None           # 双窗口均未超限
    assert trend_regime(-0.11, None) == "down"         # 60日超限
    assert trend_regime(0.10, None) == "up"            # 恰好达阈值 (>=)
    assert trend_regime(0.03, -0.15) == "down"         # 120日超限
    assert trend_regime(0.02, 0.20) == "up"


def test_recent_cum_return_windows():
    from scripts.compute_evidence import recent_cum_return
    col = np.full(150, 0.01)
    assert abs(recent_cum_return(col, 60) - (1.01 ** 60 - 1)) < 1e-9
    assert abs(recent_cum_return(col, 120) - (1.01 ** 120 - 1)) < 1e-9
    assert recent_cum_return(np.full(59, 0.01)) is None       # 有效值 <60 -> None
    assert recent_cum_return(np.array([np.nan] * 50)) is None  # 全 nan -> None


def test_grid_fitness_trend_guard_forces_marginal():
    """单边下跌主题: 即使复合分高 (高波动), 趋势护栏强制降 marginal (中概互联实证场景)."""
    rng = np.random.default_rng(7)
    n_days = 150
    # 7 个小波动震荡主题 (σ=0.5%, 120日随机漂移 std≈5.5%, 不触 15% 阈值)
    # + 1 个尾部单边下跌主题 (-0.25%/日, 120日累计约 -26%)
    cols = [rng.normal(scale=0.005, size=n_days) for _ in range(7)]
    decliner = rng.normal(scale=0.015, size=n_days)
    decliner[-120:] -= 0.0025
    cols.append(decliner)
    returns = np.column_stack(cols)
    names = [f"t{i}" for i in range(8)]
    display = {n: f"主题{i}" for i, n in enumerate(names)}
    arch = arch_per_theme(returns, names)
    grid = grid_fitness_per_theme(returns, names, display, arch)
    themed = {t["theme_id"]: t for t in grid["themes"]}
    d = themed["t7"]
    assert d["trend_regime"] == "down"
    assert d["ret_120d"] <= -TREND_LIMIT_120
    assert d["verdict"] == "marginal"  # 无论分数, 强制降级
    for i in range(7):  # 随机震荡主题不触发
        assert themed[f"t{i}"]["trend_regime"] is None


def test_grid_fitness_includes_garch_forecast():
    """grid_fitness 主题条目带 GARCH 前瞻年化波动 (正数; 合成正态波动下与历史 vol 同量级)."""
    rng = np.random.default_rng(11)
    n_days = 150
    returns = rng.normal(scale=0.02, size=(n_days, 3))
    names = ["t0", "t1", "t2"]
    arch = arch_per_theme(returns, names)
    grid = grid_fitness_per_theme(returns, names, {"t0": "甲", "t1": "乙", "t2": "丙"}, arch)
    for t in grid["themes"]:
        fv = t["vol_forecast_ann"]
        assert fv is not None and 0.1 < fv < 1.5  # σ=2%日 → 年化≈32%, 量级合理


def test_forecast_vol_annualized_short_sample_none():
    """样本 <100 -> GARCH 拟合返回 None (与 Hurst 同下限)."""
    from src.evidence.stats_utils import forecast_vol_annualized
    rng = np.random.default_rng(12)
    assert forecast_vol_annualized(rng.normal(scale=0.01, size=99)) is None
    v = forecast_vol_annualized(rng.normal(scale=0.01, size=150))
    assert v is not None and 0.05 < v < 0.5


def _write_signal_snapshot(snap: Path, d: str, themes: list[dict[str, object]],
                           etfs: list[dict[str, object]],
                           signals: list[dict[str, object]] | None = None) -> None:
    p = snap / d
    p.mkdir(parents=True, exist_ok=True)
    with open(p / "themes.json", "w") as f:
        json.dump({"themes": themes}, f)
    with open(p / "etfs.json", "w") as f:
        json.dump({"etfs": etfs}, f)
    if signals is not None:
        with open(p / "signals.json", "w") as f:
            json.dump({"theme_signals": signals}, f)


def test_scorecard_end_to_end_from_snapshots(tmp_path):
    """信号事件 loader + scorecard: 同向/反向事件 -> hit_rate/档位过滤/缺数据丢弃."""
    snap = tmp_path / "snapshots"
    n_days = 65
    for i in range(n_days):
        d = f"2021-03-{i + 1:02d}"
        # 主题 r_1d (方向): 偶日 +高动量 (≥1% 高置信档), 奇日 -弱动量
        mom = 0.02 if i % 2 == 0 else -0.002
        themes = [{"id": "t0", "name": "主题0", "cn_strength": {"composite": 50},
                   "returns": {"r_1d": mom}}]
        # 事件结果取下一日 etf r_1d: 恒为 +0.01 -> 偶日事件(动量+)同向, 奇日(动量-)反向
        etfs = [{"code": "159995", "returns": {"r_1d": 0.01}}]
        sigs = [{"theme_id": "t0", "signal": "resonance", "trigger_cn_etf": "159995"},
                {"theme_id": "t0", "signal": "divergence", "trigger_cn_etf": "159995"}]  # 非目标信号
        _write_signal_snapshot(snap, d, themes, etfs, sigs)
    # 最后一天: 无 signals.json (老 snapshot 兼容) + 下一日缺失不影响 (事件只到 n-2)
    _write_signal_snapshot(snap, "2021-05-06", [{"id": "t0", "returns": {"r_1d": 0.01}}],
                           [{"code": "159995", "returns": {"r_1d": 0.01}}])

    from scripts.compute_evidence import load_signal_events
    dates, events = load_signal_events(tmp_path)
    assert len(dates) == n_days + 1
    # 每日 1 条 resonance 事件 (divergence 丢弃); 信号日 idx0..64 全部有次日数据
    assert len(events) == n_days
    assert all(e.signal == "resonance" and e.theme_id == "t0" for e in events)
    # 高动量事件 = 偶数日 0..64
    high = [e for e in events if abs(e.us_mom) >= 0.01]
    assert len(high) == 33

    from src.evidence.scorecard import scorecard_rows
    rows = scorecard_rows(events, len(dates))
    by_key = {(r["signal"], r["tier"], r["window_days"]): r for r in rows}
    all60 = by_key[("resonance", None, 60)]
    # 最近 60 日窗口 (total 66 日, 事件日 idx 6..64): 偶日(同向)30 奇日(反向)29
    assert all60["n"] == 59
    assert all60["hit_rate"] == round(30 / 59, 4)
    high120 = by_key[("resonance", "high", 120)]
    assert high120["n"] == 33  # 仅高动量事件
    trans = by_key[("transmission", None, 60)]
    assert trans["n"] == 0 and trans["status"] == "insufficient"
