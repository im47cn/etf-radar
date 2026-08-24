"""SEPA candidates 池复盘: 入池→突破→T+N 事件口径 (issue #60, 口径 B 突破事件), 纯计算无 IO.

事件定义:
- 触发: candidate 入池后, 首次收盘 close>=pivot 且当日非一字涨停 → 突破事件;
  入池日已 state=in_buy_zone 则入池日即事件日 (豁免涨停复检, entry=入池日收盘).
- 失败: 入池后 MAX_WAIT_DAYS 个交易日内无有效突破 → never_broke_out (门槛缺陷探测器).
- pending: 等待窗口未走满 (可用 bar 不足) → 不入分母, 防"未到期误判失败".
- missing_quotes: 入池日 bar 缺失 (ohlcv 文件缺失或入池日已滚出数据窗) → 不入分母.
收益: R 倍数 = (exit−entry)/(entry−stop_at_pool), exit = 突破日后第 EXIT_HORIZON 根收盘;
T+N 口径同步输出 close[t+N]/entry−1, N ∈ {5, 20}.
CI 约定: 沿用 scorecard 的 MIN_N=50 / Z_95 / 正态 95% CI / n<MIN_N → insufficient.
纯计算无 IO, loader 见 backend/scripts/compute_screen_eval.py.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..trading.vcp import is_one_word_limit_up

MAX_WAIT_DAYS = 20  # 入池后突破判定窗口 (交易日), 涨停跳过日消耗窗口不重置
EXIT_HORIZON = 20   # R 口径 exit = 突破日后第 20 根收盘 (不足 20 根 → r=None 前瞻未到期)
T_HORIZONS = (5, 20)  # T+N 口径 horizons
MIN_N = 50           # n<50 -> insufficient (与 IC 回测一致的最小样本量级)
Z_95 = 1.96          # 正态近似 95% CI

RS_LOW_PCT, RS_HIGH_PCT = 60.0, 80.0  # rs_pct 固定分档阈值: low(<60) / mid([60,80)) / high(>=80)
VCP_LOW_QUALITY = 0.5                 # vcp_quality 分档阈值: low(<0.5) / high(>=0.5)

# 分档规格 (写死): composite_score 按事件池四分位动态分档, 其余两维固定阈值
BUCKET_SPECS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ('composite_score', ('q1', 'q2', 'q3', 'q4')),
    ('rs_pct', ('low', 'mid', 'high')),
    ('vcp_quality', ('low', 'high')),
)


@dataclass(frozen=True)
class Candidate:
    """入池候选 (由 loader 从 snapshots/*/trading.json 构建, 计算层不做 IO).

    stop 即 issue 术语 stop_at_pool (trading.json 的 'stop' 键);
    vcp_quality 为 trading.json 嵌套键 vcp.quality (loader 摊平).
    """

    code: str
    pool_date: str
    pivot: float
    stop: float
    composite_score: float
    rs_pct: float
    vcp_quality: float
    state: str  # 'in_buy_zone' | 'near_buy_zone' | 'watch'


@dataclass(frozen=True)
class Outcome:
    """单候选复盘结果.

    status: 'broke_out' | 'never_broke_out' | 'pending' | 'missing_quotes';
    event_date/entry 仅 broke_out 有值; r_multiple 在 exit 未到期时为 None.
    """

    status: str
    event_date: str | None = None
    entry: float | None = None
    r_multiple: float | None = None
    ret_5d: float | None = None
    ret_20d: float | None = None


def _ret(bars: list[dict[str, float | str | int]], event_i: int, n: int, entry: float) -> float | None:
    """事件后第 n 根收盘的 T+N 收益; 越界 (前瞻未到期) 返回 None."""
    j = event_i + n
    if j >= len(bars):
        return None
    return round(float(bars[j]['c']) / entry - 1.0, 4)


def evaluate_candidate(cand: Candidate, bars: list[dict[str, float | str | int]]) -> Outcome:
    """单候选入池→突破→T+N 复盘. bars 为 ohlcv 文件 bars 原样 (已按日期升序)."""
    idx = {str(b['d']): i for i, b in enumerate(bars)}
    i = idx.get(cand.pool_date)
    if i is None:
        return Outcome(status='missing_quotes')

    event_i: int | None = None
    if cand.state == 'in_buy_zone':
        event_i = i  # 入池即事件日, 豁免涨停复检
    else:
        # 扫入池日之后第 1..MAX_WAIT_DAYS 根: 一字涨停日消耗窗口但不记事件
        for j in range(i + 1, i + MAX_WAIT_DAYS + 1):
            if j >= len(bars):
                break
            c = float(bars[j]['c'])
            if c < cand.pivot:
                continue
            if is_one_word_limit_up(float(bars[j]['o']), float(bars[j]['h']),
                                    float(bars[j]['l']), c, float(bars[j - 1]['c'])):
                continue
            event_i = j
            break
        if event_i is None:
            if i + MAX_WAIT_DAYS >= len(bars):
                return Outcome(status='pending')
            return Outcome(status='never_broke_out')

    entry = round(float(bars[event_i]['c']), 4)
    exit_i = event_i + EXIT_HORIZON
    r: float | None = None
    if exit_i < len(bars) and entry - cand.stop > 0:
        r = round((float(bars[exit_i]['c']) - entry) / (entry - cand.stop), 4)
    return Outcome(
        status='broke_out',
        event_date=str(bars[event_i]['d']),
        entry=entry,
        r_multiple=r,
        ret_5d=_ret(bars, event_i, 5, entry),
        ret_20d=_ret(bars, event_i, 20, entry),
    )


def hit_ci(r_values: list[float]) -> dict[str, object]:
    """R 命中率行: hit = r>0; 95% 正态 CI 截断 [0,1]; n<MIN_N → insufficient."""
    n = len(r_values)
    if n == 0:
        return {'n': 0, 'hit_rate': 0.0, 'ci_low': 0.0, 'ci_high': 0.0,
                'median_r': 0.0, 'status': 'insufficient'}
    p = sum(1 for r in r_values if r > 0) / n
    half = Z_95 * np.sqrt(p * (1.0 - p) / n)
    ci_low = max(0.0, p - half)
    ci_high = min(1.0, p + half)
    return {'n': n, 'hit_rate': round(p, 4), 'ci_low': round(float(ci_low), 4),
            'ci_high': round(float(ci_high), 4),
            'median_r': round(float(np.median(r_values)), 4),
            'status': 'insufficient' if n < MIN_N else 'ok'}


def _bucket_of(dim: str, cand: Candidate, q_edges: tuple[float, float, float]) -> str:
    """维度 → 档位: composite_score 按事件池四分位, rs_pct / vcp_quality 固定阈值."""
    if dim == 'composite_score':
        v = cand.composite_score
        if v < q_edges[0]:
            return 'q1'
        if v < q_edges[1]:
            return 'q2'
        if v < q_edges[2]:
            return 'q3'
        return 'q4'
    if dim == 'rs_pct':
        return 'low' if cand.rs_pct < RS_LOW_PCT else (
            'mid' if cand.rs_pct < RS_HIGH_PCT else 'high')
    return 'low' if cand.vcp_quality < VCP_LOW_QUALITY else 'high'


def bucket_rows(pairs: list[tuple[Candidate, Outcome]]) -> list[dict[str, object]]:
    """分档命中率行: 仅 status='broke_out' 且 r_multiple 非 None 的事件入档.

    每档一行 (档内无事件 → n=0 insufficient 行仍输出), 行数 = 各维度档数和 (4+3+2=9).
    """
    events = [(c, o) for c, o in pairs if o.status == 'broke_out' and o.r_multiple is not None]
    if events:
        e1, e2, e3 = (float(e) for e in np.percentile(
            [c.composite_score for c, _ in events], [25, 50, 75]))
        edges = (e1, e2, e3)
    else:
        edges = (0.0, 0.0, 0.0)
    rows: list[dict[str, object]] = []
    for dim, buckets in BUCKET_SPECS:
        for bucket in buckets:
            rs = [float(o.r_multiple) for c, o in events
                  if o.r_multiple is not None and _bucket_of(dim, c, edges) == bucket]
            rows.append({'dimension': dim, 'bucket': bucket, **hit_ci(rs)})
    return rows
