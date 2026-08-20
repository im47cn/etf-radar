"""SEPA 预注册回测夹具单测 — 统计函数/模板/VCP/判定逻辑, 全离线无网络."""

import itertools
import json
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from scripts.research.sepa_backtest import (
    VERDICT_DESCRIPTIVE,
    VERDICT_NO_EVIDENCE,
    VERDICT_SIGNAL,
    classify_regime,
    cross_section,
    detect_vcp,
    eval_positions,
    find_vcp_breakout_entries,
    index_template_pass_count,
    judge,
    load_close_shards,
    load_index_cached,
    load_ohlcv_universe,
    mann_whitney_u_greater,
    prepare_eval_matrices,
    run_h1,
    run_h2_h3,
    template_pass_count,
    two_proportion_ztest_one_sided,
    welch_t_greater,
)

# ---------------------------------------------------------------------------
# 模板 8 条
# ---------------------------------------------------------------------------


def _m(**over: float) -> dict[str, np.ndarray]:
    """全 8 条通过的基准输入, 覆盖单字段可破坏指定条件 (其余条件不受牵连)."""
    base = {
        "close": 110.0,
        "ma50": 105.0,
        "ma150": 100.0,
        "ma200": 95.0,
        "ma200_lag20": 94.0,
        "hi250": 120.0,
        "lo250": 80.0,
    }
    base.update(over)
    return {k: np.array([v]) for k, v in base.items()}


def test_template_all_eight_pass():
    assert template_pass_count(_m(), np.array([85.0]))[0] == 8


@pytest.mark.parametrize(
    "over",
    [
        {"close": 104.0},  # c1 破坏: close < ma50
        {"ma150": 94.0},  # c2 破坏: ma150 < ma200
        {"ma200_lag20": 96.0},  # c3 破坏: 200MA 未上行
        {"ma50": 98.0},  # c4 破坏: ma50 < ma150
        {"lo250": 92.0},  # c5 破坏: close < lo250*1.30
        {"hi250": 150.0},  # c6 破坏: close < hi250*0.75
        {"ma200": 104.0, "ma150": 104.5, "ma200_lag20": 94.0},  # c8 破坏: 均线距离 <1%
    ],
)
def test_template_single_condition_break(over):
    """破坏单条 → 通过数恰好 8→7, 其余条件不被牵连."""
    assert template_pass_count(_m(**over), np.array([85.0]))[0] == 7


def test_template_rs_condition_seventy_cutoff():
    """c7 阈值 70: 69.9 不通过, 70.0 通过."""
    n69 = template_pass_count(_m(), np.array([69.9]))[0]
    n70 = template_pass_count(_m(), np.array([70.0]))[0]
    assert (n69, n70) == (7, 8)


def test_template_nan_input_invalid():
    out = template_pass_count(_m(ma200=np.nan), np.array([85.0]))
    assert np.isnan(out[0])


def test_index_template_and_regime():
    """指数版: c7=跑赢基准; 强上行指数应 ≥7; regime 三档映射."""
    idx = pd.Series(np.linspace(100, 300, 300), index=pd.date_range("2024-01-01", periods=300))
    beats = (idx / idx.shift(60) - 1.0) > 0.0  # 基准恒为平盘 → r60>0 即跑赢
    cnt = index_template_pass_count(idx, beats)
    assert cnt.iloc[-1] >= 7
    assert classify_regime([7, 6, 2]) == "offense"
    assert classify_regime([2, 3, 8]) == "defense"
    assert classify_regime([6, 5, 3]) == "neutral"
    assert classify_regime([5, 5, 5]) == "neutral"


# ---------------------------------------------------------------------------
# 统计函数 (已知值锚点)
# ---------------------------------------------------------------------------


def test_two_proportion_ztest_known_value():
    """60/100 vs 40/100: 合并 p=0.5, z=2.8284, 单侧 p≈0.00234."""
    z, p = two_proportion_ztest_one_sided(60, 100, 40, 100)
    assert z == pytest.approx(2.8284, abs=1e-3)
    assert p == pytest.approx(0.002338, abs=1e-5)


def test_two_proportion_ztest_zero_denominator():
    z, p = two_proportion_ztest_one_sided(1, 0, 0, 10)
    assert np.isnan(z) and np.isnan(p)


def test_mann_whitney_direction():
    rng = np.random.default_rng(7)
    x = rng.normal(0.02, 0.05, 500)
    y = rng.normal(0.0, 0.05, 500)
    _, p_greater = mann_whitney_u_greater(x, y)
    _, p_reverse = mann_whitney_u_greater(y, x)
    assert p_greater < 0.05
    assert p_reverse > 0.5


def test_welch_t_greater_direction():
    rng = np.random.default_rng(9)
    x = rng.normal(0.03, 0.05, 300)
    y = rng.normal(0.0, 0.05, 300)
    t, p = welch_t_greater(x, y)
    assert t > 0 and p < 0.05
    _, p_same = welch_t_greater(y, y.copy())
    assert p_same > 0.4


def test_judge_three_branches():
    assert judge(0.01, True, True, "x")[0] == VERDICT_SIGNAL
    # 方向对但欠显著 → 维持描述性 (金银比先例)
    assert judge(0.168, True, True, "x")[0] == VERDICT_DESCRIPTIVE
    assert judge(0.01, False, True, "x")[0] == VERDICT_DESCRIPTIVE
    assert judge(float("nan"), False, False, "x")[0] == VERDICT_NO_EVIDENCE


# ---------------------------------------------------------------------------
# VCP 识别 + pivot 上穿
# ---------------------------------------------------------------------------


def _vcp_base(scale: float = 1.0) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """教科书 VCP 基部(60 bar): 100→91(9%) 与 97→92.5(4.64% ≤ 9%×0.8), 末端缩量."""
    seg = (
        [95.0 + i * 0.5 for i in range(11)]  # 0..10 上行 95→100
        + [100.0 - i * 0.9 for i in range(1, 11)]  # 11..20 回落 →91.0
        + [91.0 + i * 0.6 for i in range(1, 11)]  # 21..30 反弹 →97.0
        + [97.0 - i * 0.45 for i in range(1, 11)]  # 31..40 二次回撤 →92.5
        + [92.5 + i * 0.05 for i in range(19)]  # 41..59 漂移 92.5→93.4
    )
    p = np.array(seg) * scale
    assert len(p) == 60
    vol = np.array([1000.0] * 55 + [500.0] * 5)
    return p, p, vol  # 摆动点即极值, high==low 不影响 zigzag


def test_detect_vcp_textbook_true():
    high, low, vol = _vcp_base()
    ok, quality = detect_vcp(high, low, vol)
    assert ok is True
    assert 0.0 <= quality <= 1.0


def test_detect_vcp_expanding_depths_false():
    """二次收缩比一次深 (9%→13.2% > 9%×0.8) → 单调递减破坏 → 非 VCP."""
    seg = (
        [95.0 + i * 0.5 for i in range(11)]
        + [100.0 - i * 0.9 for i in range(1, 11)]  # →91 (9%)
        + [91.0 + i * 0.6 for i in range(1, 11)]  # →97
        + [97.0 - i * 1.0 for i in range(1, 6)]  # →92
        + [92.0 - i * 0.8 for i in range(1, 11)]  # →84.2 (13.2%)
        + [84.2 + i * 0.1 for i in range(12)]
    )
    p = np.array(seg)
    vol = np.concatenate([np.full(len(p) - 5, 1000.0), np.full(5, 500.0)])
    ok, _ = detect_vcp(p, p, vol)
    assert ok is False


def test_detect_vcp_volume_not_dry_false():
    high, low, _ = _vcp_base()
    ok, _ = detect_vcp(high, low, np.full(60, 1000.0))  # 无缩量
    assert ok is False


def test_find_vcp_breakout_entries_cross_and_no_cross():
    high, low, vol = _vcp_base()
    close = (high + low) / 2.0
    # 上穿: close[59]=93.4 < pivot(100) ≤ close[60]=101
    h2 = np.append(high, 101.0)
    l2 = np.append(low, 100.5)
    v2 = np.append(vol, 600.0)
    assert find_vcp_breakout_entries(h2, l2, np.append(close, 101.0), v2) == [60]
    # 未上穿 (收盘未及 pivot) → 无信号
    assert find_vcp_breakout_entries(h2, l2, np.append(close, 99.0), v2) == []
    # 窗口不足 → 空
    assert find_vcp_breakout_entries(h2[:30], l2[:30], close[:30], v2[:30]) == []


# ---------------------------------------------------------------------------
# 数据加载 (tmp 夹具)
# ---------------------------------------------------------------------------


def test_load_close_shards(tmp_path: Path):
    for year, dates, stocks in (
        ("2024", ["2024-01-02", "2024-01-03"], {"600519": [1700.0, None], "000001": [10.0, 10.2]}),
        ("2025", ["2025-01-02", "2025-01-03"], {"600519": [1750.0, 1760.0]}),
    ):
        (tmp_path / "stocks" / "history").mkdir(parents=True, exist_ok=True)
        (tmp_path / "stocks" / "history" / f"close_{year}.json").write_text(
            json.dumps({"schema_version": "1.0", "year": year, "dates": dates, "stocks": stocks})
        )
    df = load_close_shards(tmp_path, years=[2024, 2025])
    assert df.shape == (4, 2)
    assert df.index[0] == pd.Timestamp("2024-01-02")
    assert np.isnan(df.loc[pd.Timestamp("2024-01-03"), "600519"])  # null → NaN
    assert np.isnan(df.loc[pd.Timestamp("2025-01-02"), "000001"])  # 该年缺席 → NaN


def test_load_index_cached_roundtrip(tmp_path: Path):
    fake = [("2025-01-02", 5000.0), ("2025-01-03", 5010.0)]
    with patch("scripts.research.sepa_backtest._fetch_index_chain", return_value=fake) as m:
        s1 = load_index_cached("000985", cache_dir=tmp_path)
        s2 = load_index_cached("000985", cache_dir=tmp_path)
    assert m.call_count == 1  # 第二次命中本地缓存
    assert list(s1.items()) == [
        (pd.Timestamp("2025-01-02"), 5000.0),
        (pd.Timestamp("2025-01-03"), 5010.0),
    ]
    assert s2.equals(s1)
    assert (tmp_path / "index_000985.json").exists()


def test_eval_positions_start_and_step():
    idx = pd.date_range("2020-12-20", periods=60)
    close = pd.DataFrame({"a": np.arange(60, dtype="float64")}, index=idx)
    pos = eval_positions(close)
    assert pos[0] == idx.searchsorted(pd.Timestamp("2021-01-01"))
    assert all(b - a == 21 for a, b in itertools.pairwise(pos))
    assert all(p + 20 < 60 for p in pos)


# ---------------------------------------------------------------------------
# 截面与端到端 (合成宇宙)
# ---------------------------------------------------------------------------


def _uptrend_df(n_days: int, n_stocks: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2020-06-01", periods=n_days)
    base = np.cumprod(1.0 + 0.002 + rng.normal(0, 0.005, (n_days, n_stocks)), axis=0)
    return pd.DataFrame(base * 100.0, index=idx, columns=[f"u{i}" for i in range(n_stocks)])


def _flat_df(n_days: int, n_stocks: int, seed: int, idx: pd.Index) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    return pd.DataFrame(
        100.0 + rng.normal(0, 0.2, (n_days, n_stocks)),
        index=idx,
        columns=[f"f{i}" for i in range(n_stocks)],
    )


def test_cross_section_counts_and_excess():
    """上行股应入 pass 池(≥6); 平盘股大量条件不过(≤3)."""
    up = _uptrend_df(400, 30, seed=11)
    flat = _flat_df(400, 30, seed=5, idx=up.index)
    close = pd.concat([up, flat], axis=1)
    mats = prepare_eval_matrices(close)
    counts, fwd = cross_section(close, mats, 350, bench_r60_t=0.0)
    assert np.isfinite(counts).sum() == 60
    assert (counts[:30] >= 6).sum() >= 10
    assert (counts[30:] <= 3).sum() >= 10
    assert np.isfinite(fwd[:30]).all()


def test_run_h2_h3_synthetic(capsys):
    """端到端: 100 上行 + 100 平盘, 三指数强上行 → H2 走统计分支, H3 defense=0 → 样本不足."""
    up = _uptrend_df(500, 100, seed=21)
    flat = _flat_df(500, 100, seed=6, idx=up.index)
    close = pd.concat([up, flat], axis=1)
    bench = pd.Series(100.0, index=up.index)
    regime = {
        c: pd.Series(np.linspace(100, 400, 500), index=up.index)
        for c in ("000300", "000905", "399006")
    }
    run_h2_h3(close, bench, regime)
    out = capsys.readouterr().out
    assert "MW U=" in out  # H2 两组均超门槛 → 统计分支
    assert VERDICT_NO_EVIDENCE in out  # H3 defense 无评估日 → 样本不足


def _cycle_bars(offset: int, n: int = 400) -> list[dict]:
    """循环 VCP+上穿序列: 每 71 bar 一周期(60 基部+1 突破+10 漂移), 逐周期抬升 10%.

    offset 为前置低价铺垫 bar 数 → 各股突破日错开, 同日信号数 ≤ 池容量。
    """
    bars: list[dict] = [{"h": 50.0, "l": 49.9, "c": 50.0, "v": 900.0} for _ in range(offset)]
    level = 1.0
    pos = offset
    while pos + 71 <= n:
        h, l, v = _vcp_base(scale=level)
        c = (h + l) / 2.0
        brk = float(h.max()) * 1.01
        drift = np.linspace(brk, brk * 1.035, 10)
        seq = (
            [{"h": hh, "l": ll, "c": cc, "v": float(vv)} for hh, ll, cc, vv in zip(h, l, c, v)]
            + [{"h": brk, "l": brk * 0.995, "c": brk, "v": 600.0}]
            + [
                {"h": float(d) * 1.001, "l": float(d) * 0.998, "c": float(d), "v": 900.0}
                for d in drift
            ]
        )
        bars += seq
        level *= 1.1
        pos += 71
    tail = bars[-1]["c"] * 1.002
    bars += [{"h": tail, "l": tail * 0.998, "c": tail, "v": 900.0} for _ in range(n - len(bars))]
    assert len(bars) == n
    return bars


def test_run_h1_synthetic_universe(tmp_path: Path, capsys):
    """12 循环 VCP 股(错相) + 8 上行池股 → 信号 n≥20, Welch 分支可执行."""
    ohlcv = tmp_path / "ohlcv"
    ohlcv.mkdir()
    dates = pd.date_range("2024-06-03", periods=400, freq="B")
    for i in range(12):
        bars = _cycle_bars(offset=i * 3)
        (ohlcv / f"6000{i:02d}.json").write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "code": f"6000{i:02d}",
                    "bars": [{"d": d.strftime("%Y-%m-%d"), **b} for d, b in zip(dates, bars)],
                }
            )
        )
    up = _uptrend_df(400, 8, seed=31)
    for i, col in enumerate(up.columns):
        (ohlcv / f"00000{i}.json").write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "code": f"00000{i}",
                    "bars": [
                        {
                            "d": d.strftime("%Y-%m-%d"),
                            "o": float(c),
                            "h": float(c) * 1.001,
                            "l": float(c) * 0.999,
                            "c": float(c),
                            "v": 1000.0,
                        }
                        for d, c in zip(dates, up[col].to_numpy())
                    ],
                }
            )
        )
    bench = pd.Series(100.0, index=dates)
    verdict = run_h1(ohlcv, bench)
    out = capsys.readouterr().out
    assert "Welch t=" in out  # 信号 n≥20 → 统计分支
    assert verdict


def test_run_h1_missing_dir(tmp_path: Path):
    assert "跳过" in run_h1(tmp_path / "nope", pd.Series(dtype="float64"))


def test_load_ohlcv_universe_alignment(tmp_path: Path):
    ohlcv = tmp_path / "ohlcv"
    ohlcv.mkdir()
    (ohlcv / "600001.json").write_text(
        json.dumps(
            {
                "code": "600001",
                "bars": [
                    {"d": "2025-01-02", "o": 10, "h": 10.5, "l": 9.8, "c": 10.2, "v": 100},
                    {"d": "2025-01-03", "o": 10, "h": 10.4, "l": 9.9, "c": 10.1, "v": 90},
                ],
            }
        )
    )
    (ohlcv / "600002.json").write_text(
        json.dumps(
            {
                "code": "600002",
                "bars": [
                    {"d": "2025-01-03", "o": 20, "h": 20.5, "l": 19.8, "c": 20.2, "v": 100},
                ],
            }
        )
    )
    close, extra = load_ohlcv_universe(ohlcv)
    assert close.shape == (2, 2)
    assert np.isnan(close.loc[pd.Timestamp("2025-01-02"), "600002"])  # 日期并集对齐
    assert set(extra) == {"high", "low", "vol"}
    assert extra["high"].shape == close.shape


# ---------------------------------------------------------------------------
# 补充分支: chain 兜底 / 守卫 / 样本不足 / main 冒烟
# ---------------------------------------------------------------------------


def test_fetch_index_chain_falls_back(monkeypatch):
    """首源失败 → chain 落到兜底源; 两源全失败 → 响亮报错."""
    import sys
    import types
    from datetime import date

    today = date.today()  # noqa: DTZ011  日期标签,时区无关
    today_iso = today.isoformat()

    mod = types.ModuleType("src.providers.index_provider")

    class Boom:
        def fetch_close(self, code):
            raise RuntimeError("sina down")

    class Ok:
        def fetch_close(self, code):
            return [(today, 1234.5)]

    mod.IndexProvider, mod.EmIndexProvider = Boom, Ok
    monkeypatch.setitem(sys.modules, "src.providers.index_provider", mod)
    from scripts.research import sepa_backtest as sb

    assert sb._fetch_index_chain("000300") == [(today_iso, 1234.5)]

    class Boom2:
        def fetch_close(self, code):
            raise RuntimeError("em down")

    mod.EmIndexProvider = Boom2
    with pytest.raises(RuntimeError, match="chain 全部失败"):
        sb._fetch_index_chain("000300")


def test_two_proportion_ztest_degenerate_all_wins():
    """两侧全胜 (p_pool=1 → se=0) → nan 不判定."""
    z, p = two_proportion_ztest_one_sided(10, 10, 10, 10)
    assert np.isnan(z) and np.isnan(p)


def test_zigzag_empty_input():
    from scripts.research.sepa_backtest import zigzag_pivots

    assert zigzag_pivots(np.array([]), np.array([])) == []


def test_detect_vcp_tail_shallow_not_counted():
    """末端下探 <4% 不构成收缩段 → 仅 1 次收缩 → 非 VCP."""
    seg = (
        [95.0 + i * 0.5 for i in range(11)]
        + [100.0 - i * 0.9 for i in range(1, 11)]  # →91 (9%)
        + [91.0 + i * 0.6 for i in range(1, 11)]  # →97 (H)
        + [96.5] * 28  # 末端浅回撤 0.5% 后走平 (<4% 不计段)
    )
    p = np.array(seg)
    vol = np.concatenate([np.full(len(p) - 5, 1000.0), np.full(5, 500.0)])
    ok, _ = detect_vcp(p, p, vol)
    assert ok is False


def test_find_vcp_breakout_nan_close_skipped():
    high, low, vol = _vcp_base()
    close = (high + low) / 2.0
    close = close.copy()
    close[59] = np.nan  # 突破前夜停牌 → 无信号
    assert find_vcp_breakout_entries(high, low, close, vol) == []


def test_run_h2_h3_bench_all_nan_insufficient(capsys):
    """基准全 NaN → 无有效评估日 → H2/H3 均样本不足."""
    up = _uptrend_df(500, 100, seed=41)
    bench_nan = pd.Series(np.nan, index=up.index)
    regime = {
        c: pd.Series(np.linspace(100, 400, 500), index=up.index)
        for c in ("000300", "000905", "399006")
    }
    run_h2_h3(up, bench_nan, regime)
    out = capsys.readouterr().out
    assert VERDICT_NO_EVIDENCE in out


def test_run_h1_empty_dir(tmp_path: Path):
    ohlcv = tmp_path / "ohlcv"
    ohlcv.mkdir()
    assert "目录为空" in run_h1(ohlcv, pd.Series(dtype="float64"))


def test_run_h1_guard_branches(tmp_path: Path, capsys):
    """末段信号 t+20 越界 / fwd NaN 两类守卫路径 + 信号不足分支."""
    ohlcv = tmp_path / "ohlcv"
    ohlcv.mkdir()
    dates400 = pd.date_range("2024-06-03", periods=400, freq="B")
    # offset=40: 末周期突破 t=384, t+20>400 → 越界弃
    bars_a = _cycle_bars(offset=40, n=400)
    (ohlcv / "600100.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "code": "600100",
                "bars": [{"d": d.strftime("%Y-%m-%d"), **b} for d, b in zip(dates400, bars_a)],
            }
        )
    )
    # n=364: 末周期突破 t=344 落矩阵但该股 fwd 处 NaN → isfinite 守卫弃
    bars_b = _cycle_bars(offset=0, n=364)
    dates364 = pd.date_range("2024-06-03", periods=364, freq="B")
    (ohlcv / "600200.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "code": "600200",
                "bars": [{"d": d.strftime("%Y-%m-%d"), **b} for d, b in zip(dates364, bars_b)],
            }
        )
    )
    bench = pd.Series(100.0, index=dates400)
    verdict = run_h1(ohlcv, bench)
    out = capsys.readouterr().out
    assert VERDICT_NO_EVIDENCE in out  # 有效信号 < 20 → 无证据分支
    assert verdict


def test_main_smoke(capsys, monkeypatch):
    """main 全流程 (指数缓存与分片加载打桩, 无网络无磁盘依赖)."""
    import sys

    from scripts.research import sepa_backtest as sb

    up = _uptrend_df(500, 100, seed=51)
    flat = _flat_df(500, 100, seed=8, idx=up.index)
    close = pd.concat([up, flat], axis=1)
    idx_series = {
        "000985": pd.Series(100.0, index=up.index),
        **{
            c: pd.Series(np.linspace(100, 400, 500), index=up.index)
            for c in ("000300", "000905", "399006")
        },
    }
    monkeypatch.setattr(sb, "load_index_cached", lambda code, refresh=False: idx_series[code])
    monkeypatch.setattr(sb, "load_close_shards", lambda root, years=sb.SHARD_YEARS: close)
    monkeypatch.setattr(sys, "argv", ["sepa_backtest.py"])
    sb.main()
    out = capsys.readouterr().out
    assert "H2" in out and "H3" in out and "H1" in out
    assert "跳过" in out  # 未启用 --use-ohlcv


def test_run_h2_h3_both_regimes_stat_branch(capsys):
    """指数前强后弱 → offense/defense 均有评估日 → H3 走 z 检验统计分支."""
    up = _uptrend_df(500, 100, seed=61)
    flat = _flat_df(500, 100, seed=9, idx=up.index)
    close = pd.concat([up, flat], axis=1)
    bench = pd.Series(100.0, index=up.index)
    shape = np.concatenate([np.linspace(100, 300, 300), np.linspace(300, 50, 200)])
    regime = {c: pd.Series(shape, index=up.index) for c in ("000300", "000905", "399006")}
    run_h2_h3(close, bench, regime)
    out = capsys.readouterr().out
    assert "vs defense" in out  # H3 进入了比例检验分支
    assert "z=" in out


def test_run_h1_bench_r60_nan_day_skipped(tmp_path: Path, capsys):
    """信号日基准 r60 无值 (序列头部) → 该日整体跳过."""
    ohlcv = tmp_path / "ohlcv"
    ohlcv.mkdir()
    dates = pd.date_range("2024-06-03", periods=400, freq="B")
    bars = _cycle_bars(offset=0, n=400)
    (ohlcv / "600300.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "code": "600300",
                "bars": [{"d": d.strftime("%Y-%m-%d"), **b} for d, b in zip(dates, bars)],
            }
        )
    )
    bench = pd.Series([np.nan] * 60 + [100.0] * 340, index=dates)
    run_h1(ohlcv, bench)
    out = capsys.readouterr().out
    assert "H1" in out


def test_main_smoke_use_ohlcv(capsys, monkeypatch, tmp_path: Path):
    """main --use-ohlcv 分支 (H1 打桩, 验证接线)."""
    import sys

    from scripts.research import sepa_backtest as sb

    up = _uptrend_df(500, 100, seed=71)
    idx_series = {"000985": pd.Series(100.0, index=up.index)}
    monkeypatch.setattr(
        sb,
        "load_index_cached",
        lambda code, refresh=False: idx_series.setdefault(
            code, pd.Series(np.linspace(100, 400, 500), index=up.index)
        ),
    )
    monkeypatch.setattr(sb, "load_close_shards", lambda root, years=sb.SHARD_YEARS: up)
    called = {}
    monkeypatch.setattr(sb, "run_h1", lambda d, b: called.setdefault("t", d) and "OK")
    monkeypatch.setattr(sb, "run_h2_h3", lambda *a, **k: None)
    monkeypatch.setattr(sys, "argv", ["sepa_backtest.py", "--use-ohlcv"])
    sb.main()
    assert called.get("t") is not None and str(called["t"]).endswith("stocks/ohlcv")


def test_fetch_index_chain_stale_data_falls_back(monkeypatch):
    """首源返回陈旧截断数据 (如新浪 000985 止于 2016) → 视为坏数据落到兜底源."""
    import sys
    import types
    from datetime import date

    mod = types.ModuleType("src.providers.index_provider")

    class Stale:
        name = "stale-src"

        def fetch_close(self, code):
            return [(date(2016, 6, 13), 4401.3)]  # 末端距今 >45 天

    class Fresh:
        name = "fresh-src"

        def fetch_close(self, code):
            return [(date.today(), 5868.99)]  # noqa: DTZ011  日期标签,时区无关

    mod.IndexProvider, mod.EmIndexProvider = Stale, Fresh
    monkeypatch.setitem(sys.modules, "src.providers.index_provider", mod)
    from scripts.research import sepa_backtest as sb

    assert sb._fetch_index_chain("000985") == [(date.today().isoformat(), 5868.99)]  # noqa: DTZ011  日期标签,时区无关
