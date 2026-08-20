"""SEPA 环节预注册回测 — 判据先定死, 跑数后不变体.

对应规格 docs/superpowers/specs/2026-08-20-sepa-trading-loop-spec.md §3。
目标: 判定三个环节(模板过滤/环境档位/VCP突破入场)是否含 alpha → 可挂"信号"文案, 还是维持描述性。

====================== 预注册判据(跑数前定死, 不做变体) ======================

数据范围:
  - 个股: data/stocks/history/close_2020..2026.json 年度分片(qfq 收盘矩阵)。
    2020 分片仅作 burn-in(200MA/52周窗), 有效评估自 2021-01 起, 末评估日=倒数第 21 交易日。
  - 指数: 000985(中证全指, 超额基准+RS基准) + 000300/000905/399006(环境档位)。
    经 IndexProvider→EmIndexProvider chain 拉取, 本地缓存 scripts/research/cache/。
  - H1 需 high/low: M0 data/stocks/ohlcv/ 未就绪 → 真数据判定跳过(管线由合成夹具单测
    验证), 数据可用后 --use-ohlcv 补跑, 口径不变。

评估设计:
  - 每 21 交易日取截面(步长=HORIZON+1 → 前向窗互不重叠); H=20 日前向。
  - 基础有效池: 当日与 t+20 收盘非 NaN, 且截至当日 ≥250 个有效收盘(200MA/52周可算)。
    不做 ST/流动性剔除(close 分片无名称/成交额字段; 两组同口径, 不引入不对称)。
  - close-only 口径: 52 周高/低用收盘价近似; 模板 8 条按规格 §2.1, 其中条件 7
    RS_raw = 个股 60 日收益 − 000985 60 日收益, 当日有效池内横截面百分位 ≥70。
  - 20 日超额 = 个股 20 日收益 − 000985 20 日收益。

H1(唯一成功判据): VCP+pivot 上穿入场有 alpha。
  信号: 基部(前 60 交易日)满足 VCP(≥2 次收缩、深度逐段 ≤ 前段×0.8、基部总深 ≤35%、
  近 5 日均量 ≤ 50 日均量×0.6, 即规格 §1.4), pivot=基部最高 high,
  收盘上穿 = close[t-1] < pivot ≤ close[t]。
  对照: 同日 Stage 2 池(模板 ≥6/8)内不放回随机抽同数量(RNG seed=42, 按日排序采样;
  池余量不足时该日信号与对照整体弃, 两侧同弃不引入偏)。
  判定: 两样本单侧 Welch t 检验 p<0.05 且信号组超额均值>0
  → "环节可挂'信号'文案"; 否则维持描述性。信号 n<20 → 无证据(样本不足)。

H2(唯一成功判据): 模板 ≥6/8 过滤有区分力。
  组间: pass 池(≥6/8) vs fail 池(<6/8), 同日有效池互斥二分, 各评估日样本合并。
  判定: Mann-Whitney U 单侧 greater p<0.05 且 pass 池超额中位数 > fail 池中位数
  (方向条件用中位数, 与 MW 秩口径一致)
  → 模板过滤有信息含量, 可挂"信号"; 否则维持描述性。任一组 n<50 → 无证据(样本不足)。

H3(唯一成功判据): 环境档位有区分力。
  档位: 000300/000905/399006 各跑 8 条模板(指数版条件 7 = 指数 60 日收益 > 000985
  同期收益, 其余同个股口径; 仅回测用, 生产口径以 M1 为准)
  → offense(≥2 只 pass≥6) / defense(≥2 只 pass≤3) / neutral(其余)。
  入场: 各评估日模板 ≥6/8 池; 胜率 = 20 日超额 > 0 占比。
  判定: offense 入场 vs defense 入场, 两比例合并 z 检验单侧 p<0.05 且 offense 胜率>defense
  → 档位有信息含量, 可挂"信号"; 否则维持描述性。
  任一档评估日 <5 或该档合计入场 <30 → 无证据(样本不足)。

失败处置: 方向对但 p≥0.05 → 按无证据处理(金银比先例 gsr_timing_backtest), 对应环节
维持描述性; 判定后不改口径、不补变体、不挑子区间。

已知局限(不参与判定, 仅随结果报告):
  ① 幸存者偏差: 年度分片含当年在市股票, 退市后消失, 前向收益被高估;
  ② 同日横截面相关使 p 值偏乐观(月度步长消除时间重叠, 截面维未校正);
  ③ close-only 近似(H2/H3 的 52 周高低用收盘价; H1 的 pivot 用真实 high);
  ④ 无 ST/流动性过滤。
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import (  # type: ignore[import-untyped]
    mannwhitneyu,  # type: ignore[import-untyped]
    norm,
    ttest_ind,
)

# backend/ 入 path → 可 import src.* (provider chain); scripts/research/ 本身无包依赖
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

RS_BENCHMARK = "000985"
REGIME_INDICES = ("000300", "000905", "399006")
SHARD_YEARS = range(2020, 2027)  # 2020 仅 burn-in
EVAL_STEP = 21  # = HORIZON+1 → 前向窗不重叠
HORIZON = 20
HISTORY_MIN = 250  # 200MA + 20日斜率 + 52周窗
EVAL_START = "2021-01-01"
SEED = 42
CACHE_DIR = Path(__file__).resolve().parent / "cache"

VCP_BASE = 60  # VCP 基部回看窗(交易日)
VCP_ZIGZAG_THRESH = 0.04
VCP_DECAY = 0.8
VCP_MAX_TOTAL_DEPTH = 0.35
VCP_DRYUP = 0.6

# 判定文案(定死)
VERDICT_SIGNAL = "可挂信号"
VERDICT_DESCRIPTIVE = "维持描述性"
VERDICT_NO_EVIDENCE = "无证据(样本不足)"

# 样本充足性门槛(预注册, 任一不满足 → 无证据(样本不足))
H1_MIN_SIGNALS = 20
H2_MIN_GROUP_N = 50
H3_MIN_DAYS = 5
H3_MIN_ENTRIES = 30


def fmt_pct(x: float) -> str:
    return f"{x * 100:+.2f}%"


# ---------------------------------------------------------------------------
# 数据加载
# ---------------------------------------------------------------------------


def load_close_shards(data_root: Path, years: Sequence[int] = SHARD_YEARS) -> pd.DataFrame:
    """年度收盘分片 → dates×code 矩阵 (null→NaN, 年度间按日期 concat)."""
    frames: list[pd.DataFrame] = []
    for y in years:
        p = data_root / "stocks" / "history" / f"close_{y}.json"
        d = json.loads(p.read_text())
        idx = pd.Index(pd.to_datetime(d["dates"]))
        cols = {
            code: pd.Series(vals, index=idx, dtype="float64") for code, vals in d["stocks"].items()
        }
        frames.append(pd.DataFrame(cols))
    out = pd.concat(frames, axis=0).sort_index()
    out.index.name = "date"
    return out


def _fetch_index_chain(code: str) -> list[tuple[str, float]]:
    """provider chain 逐级兜底拉指数日线 (CLAUDE.md 硬约束: 禁单实例直调).

    新鲜度护栏: 末端日期距今 >45 天视为坏数据 (如新浪 sh000985 只维护到 2016),
    同样落入 chain 兜底。EM push2his 间歇性掐断 (见 data-fetch-resilience), 给两轮机会。
    懒加载 src.*: 测试导入本模块时不触发 akshare。
    """
    from datetime import date as _date
    from datetime import timedelta

    from src.providers.index_provider import EmIndexProvider, IndexProvider

    last_err: Exception | None = None
    for provider in (IndexProvider(), EmIndexProvider(), EmIndexProvider()):
        try:
            rows = provider.fetch_close(code)
        except Exception as e:  # noqa: BLE001  chain 兜底, 单源失败试下一源
            last_err = e
            continue
        pts = [(d.isoformat(), float(c)) for d, c in rows]
        if _date.fromisoformat(pts[-1][0]) >= _date.today() - timedelta(days=45):  # noqa: DTZ011  日期标签,时区无关
            return pts
        last_err = RuntimeError(f"{provider.name}: 数据陈旧 (末值 {pts[-1][0]})")
    raise RuntimeError(f"指数 {code}: chain 全部失败, last={last_err}")


def load_index_cached(code: str, cache_dir: Path = CACHE_DIR, refresh: bool = False) -> pd.Series:
    """指数日线收盘, 本地缓存优先; 无缓存/refresh 时经 chain 拉取后写缓存."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache = cache_dir / f"index_{code}.json"
    pts: list[list] = []
    if cache.exists() and not refresh:
        d = json.loads(cache.read_text())
        pts = d["points"]
    if not pts:
        fetched = _fetch_index_chain(code)
        pts = [[dt, c] for dt, c in fetched]
        cache.write_text(json.dumps({"code": code, "points": pts}, ensure_ascii=False))
    s = pd.Series({pd.Timestamp(p[0]): float(p[1]) for p in pts}, dtype="float64")
    return s.sort_index()


# ---------------------------------------------------------------------------
# 模板 8 条 (规格 §2.1, close-only)
# ---------------------------------------------------------------------------


def prepare_eval_matrices(close: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """模板与收益所需的全部滚动矩阵 (一次性预计算, 截面评估只做行索引)."""
    return {
        "ma50": close.rolling(50, min_periods=50).mean(),
        "ma150": close.rolling(150, min_periods=150).mean(),
        "ma200": close.rolling(200, min_periods=200).mean(),
        "ma200_lag20": close.rolling(200, min_periods=200).mean().shift(20),
        "hi250": close.rolling(250, min_periods=250).max(),
        "lo250": close.rolling(250, min_periods=250).min(),
        "r60": close / close.shift(60) - 1.0,
        "fwd20": close.shift(-HORIZON) / close - 1.0,
    }


def template_pass_count(m: dict[str, np.ndarray], rs_rank_pct: np.ndarray) -> np.ndarray:
    """单日截面模板通过数 (0..8 float; 任一输入 NaN → NaN 即无效).

    m 键: close, ma50, ma150, ma200, ma200_lag20, hi250, lo250 (等长数组)。
    rs_rank_pct: RS_raw=个股r60−基准r60 的池内百分位 (0..100, NaN 无效)。
    """
    c, ma50, ma150, ma200 = m["close"], m["ma50"], m["ma150"], m["ma200"]
    valid = np.ones(len(c), dtype=bool)
    for arr in (c, ma50, ma150, ma200, m["ma200_lag20"], m["hi250"], m["lo250"], rs_rank_pct):
        valid &= np.isfinite(arr)
    flags = (
        (c > ma50) & (c > ma150) & (c > ma200),  # 1
        (ma150 > ma200),  # 2
        (m["ma200"] > m["ma200_lag20"]),  # 3
        (ma50 > ma150) & (ma50 > ma200),  # 4
        (c >= m["lo250"] * 1.30),  # 5
        (c >= m["hi250"] * 0.75),  # 6
        (rs_rank_pct >= 70.0),  # 7
        (np.abs(ma50 - ma200) / ma200 >= 0.01),  # 8
    )
    count = np.zeros(len(c), dtype="float64")
    for f in flags:
        count += f.astype("float64")
    count[~valid] = np.nan
    return count


def index_template_pass_count(close: pd.Series, beats_bench_r60: pd.Series) -> pd.Series:
    """指数版模板通过数 (H3 档位用; 条件7=指数r60>基准r60, 其余同个股)."""
    ma50 = close.rolling(50, min_periods=50).mean()
    ma150 = close.rolling(150, min_periods=150).mean()
    ma200 = close.rolling(200, min_periods=200).mean()
    lag20 = ma200.shift(20)
    hi250 = close.rolling(250, min_periods=250).max()
    lo250 = close.rolling(250, min_periods=250).min()
    flags = (
        (close > ma50) & (close > ma150) & (close > ma200),
        (ma150 > ma200),
        (ma200 > lag20),
        (ma50 > ma150) & (ma50 > ma200),
        (close >= lo250 * 1.30),
        (close >= hi250 * 0.75),
        beats_bench_r60,
        ((ma50 - ma200).abs() / ma200 >= 0.01),
    )
    total = sum(f.astype("float64") for f in flags)
    valid = np.ones(len(close), dtype=bool)
    for s in (close, ma50, ma150, ma200, lag20, hi250, lo250, beats_bench_r60):
        valid &= s.notna().to_numpy()
    total[~valid] = np.nan
    return pd.Series(total, index=close.index)


def classify_regime(pass_counts: Sequence[int]) -> str:
    """offense: ≥2 只 pass≥6; defense: ≥2 只 pass≤3; 否则 neutral (规格 §1.1)."""
    n_off = sum(1 for p in pass_counts if p >= 6)
    n_def = sum(1 for p in pass_counts if p <= 3)
    if n_off >= 2:
        return "offense"
    if n_def >= 2:
        return "defense"
    return "neutral"


# ---------------------------------------------------------------------------
# 统计检验 (纯函数, 单测锚点)
# ---------------------------------------------------------------------------


def mann_whitney_u_greater(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    """MW U 单侧 (x 的分布位于 y 之上). 返回 (U, p_one_sided)."""
    res = mannwhitneyu(x, y, alternative="greater")
    return float(res.statistic), float(res.pvalue)


def welch_t_greater(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    """两样本单侧 Welch t (x 均值 > y 均值). 返回 (t, p_one_sided)."""
    res = ttest_ind(x, y, alternative="greater", equal_var=False)
    return float(res.statistic), float(res.pvalue)


def two_proportion_ztest_one_sided(wins1: int, n1: int, wins2: int, n2: int) -> tuple[float, float]:
    """合并比例两样本 z 检验单侧 (p1 > p2). 返回 (z, p_one_sided)."""
    if n1 <= 0 or n2 <= 0:
        return float("nan"), float("nan")
    p1, p2 = wins1 / n1, wins2 / n2
    p_pool = (wins1 + wins2) / (n1 + n2)
    se = np.sqrt(p_pool * (1.0 - p_pool) * (1.0 / n1 + 1.0 / n2))
    if se == 0.0:
        return float("nan"), float("nan")
    z = (p1 - p2) / se
    return float(z), float(norm.sf(z))


def judge(p: float, direction_ok: bool, sufficient: bool, what: str) -> tuple[str, str]:
    """统一判定: 样本不足 → 无证据; p<0.05 且方向对 → 可挂信号; 否则维持描述性."""
    if not sufficient:
        return VERDICT_NO_EVIDENCE, f"{what}: 样本不足, 不做判定"
    verdict = VERDICT_SIGNAL if (p < 0.05 and direction_ok) else VERDICT_DESCRIPTIVE
    return verdict, f"{what}: p={p:.4f}, 方向{'对' if direction_ok else '错/无差异'}"


# ---------------------------------------------------------------------------
# VCP 识别 + pivot 突破 (H1; 规格规格 §1.4/§1.5)
# ---------------------------------------------------------------------------


def zigzag_pivots(
    high: np.ndarray, low: np.ndarray, thresh: float = VCP_ZIGZAG_THRESH
) -> list[tuple[str, int, float]]:
    """4% 阈值 zigzag: 返回交替 ('H'|'L', idx, price) 摆动点列表."""
    n = len(high)
    piv: list[tuple[str, int, float]] = []
    if n == 0:
        return piv
    mode = "up"
    ext_i, ext_v = 0, float(high[0])
    for i in range(1, n):
        if mode == "up":
            if high[i] >= ext_v:
                ext_i, ext_v = i, float(high[i])
            if ext_v - low[i] >= ext_v * thresh:
                piv.append(("H", ext_i, ext_v))
                mode, ext_i, ext_v = "down", i, float(low[i])
        else:
            if low[i] <= ext_v:
                ext_i, ext_v = i, float(low[i])
            if high[i] - ext_v >= ext_v * thresh:
                piv.append(("L", ext_i, ext_v))
                mode, ext_i, ext_v = "up", i, float(high[i])
    return piv


def detect_vcp(high: np.ndarray, low: np.ndarray, vol: np.ndarray) -> tuple[bool, float]:
    """基部窗口是否构成 VCP + 质量分(0..1, 收缩次数30%+递减陡峭度40%+量能萎缩30%)."""
    piv = zigzag_pivots(high, low)
    # 连续 H→L 段为一次收缩, 深度 = (H−L)/H
    depths: list[float] = []
    for k in range(len(piv) - 1):
        if piv[k][0] == "H" and piv[k + 1][0] == "L":
            h, l = piv[k][2], piv[k + 1][2]
            depths.append((h - l) / h)
    # zigzag 只记已反转确认的摆动点; 基部末端的未反转下探段 (VCP 常态收尾) 按
    # 现窗最小 low 直接补记为最后一次收缩, 深度仍须 ≥ 阈值 (否则不计段)
    if piv and piv[-1][0] == "H":
        tail_low = float(low[piv[-1][1] :].min())
        d_tail = (piv[-1][2] - tail_low) / piv[-1][2]
        if d_tail >= VCP_ZIGZAG_THRESH:
            depths.append(d_tail)
    total_depth = (float(high.max()) - float(low.min())) / float(high.max())
    v5 = float(np.mean(vol[-5:]))
    v50 = float(np.mean(vol[-50:])) if len(vol) >= 50 else float(np.mean(vol))
    dryup_ratio = v5 / v50 if v50 > 0 else np.inf
    monotone = all(depths[i + 1] <= depths[i] * VCP_DECAY for i in range(len(depths) - 1))
    ok = (
        len(depths) >= 2
        and monotone
        and total_depth <= VCP_MAX_TOTAL_DEPTH
        and dryup_ratio <= VCP_DRYUP
    )
    # 质量分 (仅描述, 不参与 H1 判定)
    q_cnt = min(len(depths), 4) / 4.0
    ratios = (
        [depths[i + 1] / depths[i] for i in range(len(depths) - 1)] if len(depths) >= 2 else [1.0]
    )
    q_decay = float(np.clip(np.mean([1.0 - r / VCP_DECAY for r in ratios]), 0.0, 1.0))
    q_dry = float(np.clip(1.0 - dryup_ratio / VCP_DRYUP, 0.0, 1.0))
    quality = 0.3 * q_cnt + 0.4 * q_decay + 0.3 * q_dry
    return ok, round(quality, 4)


def find_vcp_breakout_entries(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    vol: np.ndarray,
    base: int = VCP_BASE,
) -> list[int]:
    """VCP+上穿入场日索引: 基部[ t-base, t ) 满足 VCP 且 close[t-1]<pivot≤close[t]."""
    n = len(close)
    if n < base + 1:
        return []
    piv_roll = pd.Series(high).rolling(base).max().shift(1).to_numpy()
    out: list[int] = []
    for t in range(base, n):
        p = piv_roll[t]
        if not np.isfinite(p) or not np.isfinite(close[t]) or not np.isfinite(close[t - 1]):
            continue
        if close[t] >= p and close[t - 1] < p:
            ok, _ = detect_vcp(high[t - base : t], low[t - base : t], vol[t - base : t])
            if ok:
                out.append(t)
    return out


# ---------------------------------------------------------------------------
# H2/H3: close 分片截面回测
# ---------------------------------------------------------------------------


def eval_positions(close: pd.DataFrame) -> list[int]:
    """评估日位置: 自 2021 年首个交易日起每 21 交易日, 需留足 20 日前向."""
    idx = close.index
    start = int(np.searchsorted(idx, pd.Timestamp(EVAL_START)))
    return list(range(start, len(idx) - HORIZON, EVAL_STEP))


def cross_section(
    close: pd.DataFrame, mats: dict[str, pd.DataFrame], t: int, bench_r60_t: float
) -> tuple[np.ndarray, np.ndarray]:
    """单日截面 → (模板通过数, 20日超额), 均在有效池内 (NaN=无效)."""
    c = close.iloc[t].to_numpy(dtype="float64")
    fwd = mats["fwd20"].iloc[t].to_numpy(dtype="float64")
    finite_close = np.isfinite(c)
    valid = (
        finite_close
        & np.isfinite(fwd)
        & np.isfinite(mats["r60"].iloc[t].to_numpy(dtype="float64"))
        & np.isfinite(mats["ma200"].iloc[t].to_numpy(dtype="float64"))
        & np.isfinite(mats["hi250"].iloc[t].to_numpy(dtype="float64"))
    )
    # 有效池内 RS_raw 横截面百分位
    rs_raw = mats["r60"].iloc[t].to_numpy(dtype="float64") - bench_r60_t
    rank = np.full(len(c), np.nan)
    if valid.sum() > 1:
        r = pd.Series(rs_raw[valid]).rank(pct=True).to_numpy() * 100.0
        rank[valid] = r
    m = {
        k: mats[k].iloc[t].to_numpy(dtype="float64")
        for k in ("ma50", "ma150", "ma200", "ma200_lag20", "hi250", "lo250")
    }
    m["close"] = c
    counts = template_pass_count(m, rank)
    counts[~valid] = np.nan
    return counts, fwd


def run_h2_h3(close: pd.DataFrame, bench: pd.Series, regime_indices: dict[str, pd.Series]) -> None:
    """H2: 模板过滤区分力; H3: 环境档位区分力 (预注册判据见 docstring)."""
    mats = prepare_eval_matrices(close)
    bench_r = bench.reindex(close.index)
    bench_fwd20 = (bench_r / bench_r.shift(-HORIZON) - 1.0).to_numpy()
    bench_r60 = bench_r / bench_r.shift(60) - 1.0

    idx_pass: dict[str, pd.Series] = {}
    for code, s in regime_indices.items():
        sr = s.reindex(close.index)
        beats = (sr / sr.shift(60) - 1.0) > bench_r60
        idx_pass[code] = index_template_pass_count(sr, beats)

    positions = eval_positions(close)
    pass_excess: list[float] = []
    fail_excess: list[float] = []
    buckets: dict[str, dict[str, list[float]]] = {
        "offense": {"win": [], "all": []},
        "defense": {"win": [], "all": []},
        "neutral": {"win": [], "all": []},
    }
    regime_days: dict[str, int] = {"offense": 0, "defense": 0, "neutral": 0}

    for t in positions:
        if not np.isfinite(bench_fwd20[t]) or not np.isfinite(bench_r60.iloc[t]):
            continue
        counts, fwd = cross_section(close, mats, t, float(bench_r60.iloc[t]))
        excess = fwd - bench_fwd20[t]
        is_pass = counts >= 6
        valid_excess = np.isfinite(excess)
        pass_excess += excess[is_pass & valid_excess].tolist()
        fail_excess += excess[(~is_pass) & valid_excess & np.isfinite(counts)].tolist()
        regime = classify_regime(
            [int(idx_pass[c].iloc[t]) for c in REGIME_INDICES if np.isfinite(idx_pass[c].iloc[t])]
        )
        regime_days[regime] += 1
        e = excess[is_pass & valid_excess]
        buckets[regime]["win"] += (e > 0).tolist()
        buckets[regime]["all"] += np.isfinite(e).tolist()

    # ---- H2 ----
    x, y = np.array(pass_excess), np.array(fail_excess)
    print(f"\n[H2] 模板≥6/8 vs <6/8, 20日超额 (vs {RS_BENCHMARK})")
    print(
        f"  pass 池 n={len(x)} 均值={fmt_pct(float(x.mean()) if len(x) else float('nan'))}"
        f" 中位数={fmt_pct(float(np.median(x)) if len(x) else float('nan'))} | "
        f"fail 池 n={len(y)} 均值={fmt_pct(float(y.mean()) if len(y) else float('nan'))}"
        f" 中位数={fmt_pct(float(np.median(y)) if len(y) else float('nan'))}"
    )
    if len(x) < H2_MIN_GROUP_N or len(y) < H2_MIN_GROUP_N:
        v2, d2 = VERDICT_NO_EVIDENCE, "H2 样本不足"
    else:
        u, p2 = mann_whitney_u_greater(x, y)
        dir_ok2 = float(np.median(x)) > float(np.median(y))
        v2, d2 = judge(p2, dir_ok2, True, f"MW U={u:.0f}")
    print(f"★ H2: {v2} — {d2}")

    # ---- H3 ----
    print(
        f"\n[H3] 环境档位 × 模板池入场胜率 (评估日 offense/neutral/defense = "
        f"{regime_days['offense']}/{regime_days['neutral']}/{regime_days['defense']})"
    )
    off, de = buckets["offense"], buckets["defense"]
    n_off, n_de = len(off["all"]), len(de["all"])
    w_off, w_de = int(np.sum(off["win"])), int(np.sum(de["win"]))
    sufficient = (
        regime_days["offense"] >= H3_MIN_DAYS
        and regime_days["defense"] >= H3_MIN_DAYS
        and n_off >= H3_MIN_ENTRIES
        and n_de >= H3_MIN_ENTRIES
    )
    if not sufficient:
        v3, d3 = (
            VERDICT_NO_EVIDENCE,
            (
                f"offense {regime_days['offense']}日/{n_off}笔, defense {regime_days['defense']}日/{n_de}笔 不足"
            ),
        )
    else:
        z, p3 = two_proportion_ztest_one_sided(w_off, n_off, w_de, n_de)
        dir_ok3 = w_off / n_off > w_de / n_de
        v3, d3 = judge(
            p3,
            dir_ok3,
            True,
            f"offense {w_off}/{n_off}={w_off / n_off:.1%} vs defense {w_de}/{n_de}={w_de / n_de:.1%}, z={z:.2f}",
        )
    print(f"★ H3: {v3} — {d3}")


# ---------------------------------------------------------------------------
# H1: VCP+pivot 上穿 (需 OHLCV; --use-ohlcv)
# ---------------------------------------------------------------------------


def load_ohlcv_universe(ohlcv_dir: Path) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    """M0 OHLCV 归档 → (close 矩阵, {high/low/vol: 矩阵}), 日期取并集对齐."""
    closes: dict[str, pd.Series] = {}
    highs: dict[str, pd.Series] = {}
    lows: dict[str, pd.Series] = {}
    vols: dict[str, pd.Series] = {}
    for fp in sorted(ohlcv_dir.glob("*.json")):
        d = json.loads(fp.read_text())
        bars = d["bars"]
        idx = pd.Index(pd.to_datetime([b["d"] for b in bars]))
        code = d["code"]
        closes[code] = pd.Series([b["c"] for b in bars], index=idx, dtype="float64")
        highs[code] = pd.Series([b["h"] for b in bars], index=idx, dtype="float64")
        lows[code] = pd.Series([b["l"] for b in bars], index=idx, dtype="float64")
        vols[code] = pd.Series([b["v"] for b in bars], index=idx, dtype="float64")
    if not closes:
        return pd.DataFrame(), {
            "high": pd.DataFrame(),
            "low": pd.DataFrame(),
            "vol": pd.DataFrame(),
        }
    close = pd.concat(closes, axis=1).sort_index()
    close.index.name = "date"
    return close, {
        "high": pd.concat(highs, axis=1).sort_index().reindex(close.index),
        "low": pd.concat(lows, axis=1).sort_index().reindex(close.index),
        "vol": pd.concat(vols, axis=1).sort_index().reindex(close.index),
    }


def run_h1(ohlcv_dir: Path, bench: pd.Series, seed: int = SEED) -> str:
    """H1 预注册判定; 返回判定文案 (数据未就绪时返回提示, 不做判定)."""
    if not ohlcv_dir.exists():
        return "跳过: OHLCV 数据未就绪 (M0 backfill 后 --use-ohlcv 补跑, 口径不变)"
    close, extra = load_ohlcv_universe(ohlcv_dir)
    if close.empty:
        return "跳过: OHLCV 目录为空"
    mats = prepare_eval_matrices(close)
    bench_r = bench.reindex(close.index)
    bench_fwd20 = (bench_r / bench_r.shift(-HORIZON) - 1.0).to_numpy()
    bench_r60 = bench_r / bench_r.shift(60) - 1.0

    # 每股 VCP+上穿信号日
    signals: dict[str, list[int]] = {}
    for code in close.columns:
        ts = find_vcp_breakout_entries(
            extra["high"][code].to_numpy(),
            extra["low"][code].to_numpy(),
            close[code].to_numpy(),
            extra["vol"][code].to_numpy(),
        )
        if ts:
            signals[code] = ts
    # 按日聚合信号 → (日位置, 超额); 对照 = 同日 Stage2 池不放回同数量随机
    by_day: dict[int, list[tuple[str, float]]] = {}
    for code, ts in signals.items():
        fwd = mats["fwd20"][code].to_numpy()
        for t in ts:
            if t + HORIZON < len(close) and np.isfinite(bench_fwd20[t]):
                ex = fwd[t] - bench_fwd20[t]
                if np.isfinite(ex):
                    by_day.setdefault(t, []).append((code, float(ex)))
    rng = np.random.default_rng(seed)
    sig_excess: list[float] = []
    ctl_excess: list[float] = []
    for t in sorted(by_day):
        if not np.isfinite(bench_r60.iloc[t]):
            continue
        day = by_day[t]
        counts, fwd = cross_section(close, mats, t, float(bench_r60.iloc[t]))
        excess = fwd - bench_fwd20[t]
        pool_mask = (counts >= 6) & np.isfinite(excess)
        sig_codes = {c for c, _ in day}
        pool = [i for i in np.where(pool_mask)[0] if close.columns[i] not in sig_codes]
        if len(pool) < len(day):
            continue  # 池不够抽同数量 → 该日整体弃 (信号与对照两侧同弃, 不引入偏)
        sig_excess += [e for _, e in day]
        picks = rng.choice(pool, size=len(day), replace=False)
        ctl_excess += [float(excess[i]) for i in picks]
    x, y = np.array(sig_excess), np.array(ctl_excess)
    print("\n[H1] VCP+pivot上穿 vs 同日Stage2随机对照 (20日超额)")
    print(
        f"  信号 n={len(x)} 均值={fmt_pct(float(x.mean()) if len(x) else float('nan'))} | "
        f"对照 n={len(y)} 均值={fmt_pct(float(y.mean()) if len(y) else float('nan'))}"
    )
    if len(x) < H1_MIN_SIGNALS:
        v1, d1 = VERDICT_NO_EVIDENCE, f"信号 n={len(x)} < {H1_MIN_SIGNALS}"
    else:
        t_stat, p1 = welch_t_greater(x, y)
        dir_ok1 = float(x.mean()) > 0.0
        v1, d1 = judge(p1, dir_ok1, True, f"Welch t={t_stat:.2f}")
    print(f"★ H1: {v1} — {d1}")
    return f"{v1} — {d1}"


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def main() -> None:
    ap = argparse.ArgumentParser(description="SEPA 预注册回测 (判据见模块 docstring)")
    ap.add_argument(
        "--data-root", type=Path, default=Path(__file__).resolve().parents[3] / "data"
    )
    ap.add_argument("--use-ohlcv", action="store_true", help="H1 用 M0 OHLCV 真数据补跑")
    ap.add_argument("--refresh-index-cache", action="store_true")
    args = ap.parse_args()

    print("=" * 72)
    print("SEPA 预注册回测 — 判据与口径见 sepa_backtest.py docstring (跑数前定死)")
    print("=" * 72)

    bench = load_index_cached(RS_BENCHMARK, refresh=args.refresh_index_cache)
    regime_idx = {
        code: load_index_cached(code, refresh=args.refresh_index_cache) for code in REGIME_INDICES
    }
    close = load_close_shards(args.data_root)
    print(
        f"个股矩阵: {close.shape[0]} 交易日 × {close.shape[1]} 只 "
        f"({close.index[0].date()}..{close.index[-1].date()}); 基准 {RS_BENCHMARK} "
        f"{len(bench)} 点"
    )
    run_h2_h3(close, bench, regime_idx)

    ohlcv_dir = args.data_root / "stocks" / "ohlcv"
    if args.use_ohlcv:
        run_h1(ohlcv_dir, bench)
    else:
        print(
            "\n[H1] 未启用 --use-ohlcv: 真数据判定跳过 "
            "(管线已由 tests/test_sepa_backtest.py 合成夹具验证)"
        )


if __name__ == "__main__":
    main()
