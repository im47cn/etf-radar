"""leader 龙头规则首次预测性回测 — 预注册判据版.

背景: holdings_indicators 的龙头标签 (⭐/⭐⭐/⭐⭐⭐ = classify_leader:
strength_60d 档 + RSI 未超买过滤) 自上线起从未做过预测性验证。
37 年个股归档 (data/stocks/history/) 允许点时重建标签: s60 与 RSI 都只依赖
收盘价序列, 无前视。

====================== 预注册判据(跑数前定死, 不做变体) ======================

样本: 2021-01 ~ 2026-08 (加载 2020 起分片留 60+14 日 burn-in);
  universe = 2026-08-15 归档边界 5542 只 (幸存者偏差声明: 退市股缺席)。
事件日: 每 21 个交易日采样一次 (降自相关)。
标签重建: s60 = batch_strength_per_dim(r_60d, k=2.0, days=60) (横截面,
  与生产同公式同参数); RSI14 = Wilder (pandas ewm alpha=1/14);
  档位 = classify_leader(s60_int, rsi) (直接调生产函数)。
前向: t+20 交易日收益; 超额 = 个股前向 − 当日 universe 前向中位数 (相对基准,
  剔除市场 beta)。
切分: 训练 <2024-01-01, 验证 ≥2024-01-01。

判据 (验证段为准, 训练段方向须一致否则直接判无效):
  1. 主检验: ⭐⭐⭐ 档平均超额 > 0 且 > 无星档, 差距 ≥ +0.5%/20日 (经济显著性下限)
  2. 单调性: ⭐⭐⭐ ≥ ⭐⭐ ≥ ⭐ 平均超额
  全部满足 → "龙头标签有验证的强势筛选力"; 否则 → "无预测力, 维持纯展示定位,
  帮助文案不得暗示预测性"。不试替代参数 (RSI 窗口/强度阈值都不调)。

============================================================================
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd  # type: ignore[import-untyped]

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # backend/
from src.scoring.leader_rule import classify_leader
from src.scoring.strength import batch_strength_per_dim

HIST = Path(__file__).resolve().parents[3] / 'data' / 'stocks' / 'history'
K_SIGMOID = 2.0
DIM_DAYS = 60
HORIZON = 20
STEP = 21
SPLIT = '2024-01-01'
MIN_EDGE = 0.005  # 主检验经济显著性下限: +0.5%/20日


def load_matrix(start_year: int) -> tuple[list[str], list[str], np.ndarray]:
    """读分片 -> (dates, codes, close 矩阵); dates 升序, 缺失 nan."""
    dates: list[str] = []
    per: dict[str, dict[str, float]] = {}
    for fp in sorted(HIST.glob('close_*.json')):
        if fp.stem.split('_')[1] < str(start_year):
            continue
        data = json.loads(fp.read_text(encoding='utf-8'))
        dates.extend(data['dates'])
        for code, row in data['stocks'].items():
            d = per.setdefault(code, {})
            for dt, c in zip(data['dates'], row):
                if c is not None:
                    d[dt] = float(c)
    dates = sorted(set(dates))
    codes = sorted(per)
    idx = {d: i for i, d in enumerate(dates)}
    m = np.full((len(dates), len(codes)), np.nan)
    for j, c in enumerate(codes):
        for dt, v in per[c].items():
            m[idx[dt], j] = v
    return dates, codes, m


def wilder_rsi(close: np.ndarray, period: int = 14) -> np.ndarray:
    """Wilder RSI 沿时间轴 (列=股票); 前 period 位 nan. pandas ewm alpha=1/period 等价."""
    out = np.full_like(close, np.nan)
    diff = np.diff(close, axis=0, prepend=close[:1])
    gain = np.where(np.isnan(diff), np.nan, np.clip(diff, 0, None))
    loss = np.where(np.isnan(diff), np.nan, np.clip(-diff, 0, None))
    df_g = pd.DataFrame(gain).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    df_l = pd.DataFrame(loss).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = df_g.values / df_l.values
    with np.errstate(invalid='ignore', divide='ignore'):
        rsi = 100 - 100 / (1 + rs)
    rsi[df_l.values == 0] = 100.0
    out[1:] = rsi[1:]
    return out


def main() -> None:
    dates, codes, close = load_matrix(2020)
    print(f'{dates[0]} ~ {dates[-1]}, {len(dates)} 日 × {len(codes)} 只')
    n, _ = close.shape

    r60 = np.full_like(close, np.nan)
    r60[DIM_DAYS:] = close[DIM_DAYS:] / close[:-DIM_DAYS] - 1
    fwd = np.full_like(close, np.nan)
    fwd[:-HORIZON] = close[HORIZON:] / close[:-HORIZON] - 1
    rsi = wilder_rsi(close)

    tiers = ['⭐⭐⭐', '⭐⭐', '⭐', '']
    buckets: dict[str, dict[str, list[float]]] = {t: {'train': [], 'valid': []} for t in tiers}

    burn = DIM_DAYS + 15
    for i in range(burn, n - HORIZON, STEP):
        r60_i = r60[i]
        s60 = batch_strength_per_dim(np.where(np.isfinite(r60_i), r60_i, np.nan),
                                     k=K_SIGMOID, days_in_dim=DIM_DAYS)
        fwd_i = fwd[i]
        med = float(np.nanmedian(fwd_i))
        per = 'train' if dates[i] < SPLIT else 'valid'
        rsi_i = rsi[i]
        for j in range(len(codes)):
            s = s60[j]
            if np.isnan(s):
                continue
            r = rsi_i[j] if np.isfinite(rsi_i[j]) else None
            tier = classify_leader(int(s), None if r is None else float(r))
            f = fwd_i[j]
            if np.isnan(f):
                continue
            buckets[tier][per].append(float(f) - med)

    print(f'\n[20日前向超额 vs 当日横截面中位数] (train <{SPLIT} / valid ≥{SPLIT})')
    means: dict[str, dict[str, float]] = {}
    for t in tiers:
        label = t if t else '(无星)'
        line = f'  {label:7s}'
        means[t] = {}
        for per in ('train', 'valid'):
            arr = np.array(buckets[t][per])
            means[t][per] = float(arr.mean())
            win = float((arr > 0).mean())
            line += f'  {per}: mean {arr.mean():+.3%} / 胜率 {win:.0%} (n={len(arr)})'
        print(line)

    print('\n[预注册判定]')
    star3, nostar = means['⭐⭐⭐'], means['']
    mono = means['⭐⭐⭐']['valid'] >= means['⭐⭐']['valid'] >= means['⭐']['valid']
    ok = (star3['train'] > 0 and star3['valid'] > 0 and star3['train'] > nostar['train']
          and star3['valid'] > nostar['valid'] + MIN_EDGE and mono)
    if ok:
        print('  通过 → 龙头标签有验证的强势筛选力 (⭐⭐⭐ 20日超额 > 无星档 ≥0.5pp 且层级单调)')
    else:
        print(f'  未通过 → 无预测力, 维持纯展示定位 (主检验差距 {star3["valid"] - nostar["valid"]:+.3%},'
              f' 单调性 {"成立" if mono else "不成立"})')


if __name__ == '__main__':
    main()
