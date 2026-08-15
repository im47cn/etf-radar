"""个股 5 年 ARCH 重验 — 读 data/stocks/history/close_YYYY.json 分片.

背景: 旧结论"个股 ARCH 40%"仅基于 150 日样本 (2026-08, power 不足疑似);
按项目方法论铁律须多年大样本重验。数据源: stocks-archive workflow 全量灌入的
按年分片 (全市场 ~5500 只, 2021-2026, 幸存者边界=灌数日 universe).

口径 (跑数前声明, 与主题层 arch_per_theme 同法):
- 日收益 = 简单收益 close[t]/close[t-1]-1, 跨年按日期拼接, None 剔除
- ARCH 判定 = r² 的 Ljung-Box m=10, p<0.05 (McLeod-Li), 期望假阳性 5%
- 主样本: 有效交易日 ≥1000 (≈4.2 年) 的个股; 副口径 n∈[250,1000) 报稳定性
- 附: 分年度 ARCH 比例 (每年窗口独立检验, n≥200), 看时间稳定性
- 不做: GARCH 拟合/预测 (那是下一步, 先确认 ARCH 存在性)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # backend/
from src.evidence.stats_utils import ljung_box
from src.scoring.stock_indicators import simple_returns

HIST = Path(__file__).resolve().parents[3] / 'data' / 'stocks' / 'history'
M_LAGS = 10
MIN_DAYS_MAIN = 1000
MIN_DAYS_PARTIAL = 250
MIN_DAYS_YEARLY = 200


def load_returns() -> dict[str, list[float]]:
    """按日期拼接全部分片 -> 每股日收益序列 (按日升序)."""
    shards = sorted(HIST.glob('close_*.json'))
    if not shards:
        raise SystemExit(f'无分片: {HIST} (先跑 stocks-archive workflow)')
    dates: list[str] = []
    stocks_close: dict[str, dict[str, float]] = {}
    for fp in shards:
        data = json.loads(fp.read_text(encoding='utf-8'))
        dates.extend(data['dates'])
        for code, row in data['stocks'].items():
            per = stocks_close.setdefault(code, {})
            for d, c in zip(data['dates'], row):
                if c is not None:
                    per[d] = float(c)
    dates = sorted(set(dates))
    out: dict[str, list[float]] = {}
    for code, per in stocks_close.items():
        out[code] = simple_returns([per.get(d) for d in dates])
    return out


def arch_test(r: list[float]) -> tuple[float, float] | None:
    """返回 (arch_p, ret_white_p); 样本不足 None."""
    arr = np.array(r, dtype=float)
    if len(arr) < MIN_DAYS_YEARLY:
        return None
    _, p_arch = ljung_box(arr ** 2, M_LAGS)
    _, p_ret = ljung_box(arr, M_LAGS)
    return float(p_arch), float(p_ret)


def main() -> None:
    returns = load_returns()
    print(f'股票数: {len(returns)} (幸存者边界 = 灌数日 universe)')

    # ---- 主口径: n≥1000 ----
    main_ps = {c: arch_test(r) for c, r in returns.items() if len(r) >= MIN_DAYS_MAIN}
    partial = {c: len(r) for c, r in returns.items()
               if MIN_DAYS_PARTIAL <= len(r) < MIN_DAYS_MAIN}
    print(f'主样本 n≥{MIN_DAYS_MAIN}: {len(main_ps)} 只; 部分 {MIN_DAYS_PARTIAL}~1000: {len(partial)} 只')

    arch_flags = {c: ps[0] < 0.05 for c, ps in main_ps.items() if ps}
    n_arch = sum(arch_flags.values())
    n = len(arch_flags)
    print(f'\n[主口径] ARCH (r² Ljung-Box m={M_LAGS}, p<0.05): {n_arch}/{n} = {n_arch / n:.1%}'
          f'  (期望假阳性 5%={0.05 * n:.0f} 只)')
    print(f'  旧结论 (150日): 40%  ->  5年重验: {n_arch / n:.1%}')
    med_p = float(np.median([ps[0] for ps in main_ps.values() if ps]))
    print(f'  arch p 中位数: {med_p:.2e}')
    # 收益白噪比例 (ARCH 不依赖收益自相关, 但值得对照)
    white = sum(1 for ps in main_ps.values() if ps and ps[1] < 0.05)
    print(f'  收益非白噪比例 (对照): {white}/{n} = {white / n:.1%}')

    # ---- 副口径: 250~1000 日 (次新股等) ----
    partial_flags = []
    for c in partial:
        ps = arch_test(returns[c])
        if ps:
            partial_flags.append(ps[0] < 0.05)
    if partial_flags:
        print(f'[副口径 250~1000日] ARCH: {sum(partial_flags)}/{len(partial_flags)}'
              f' = {sum(partial_flags) / len(partial_flags):.1%}')

    # ---- 分年度稳定性 ----
    print('\n[分年度] (每年窗口独立, n≥200)')
    shards = sorted(HIST.glob('close_*.json'))
    for fp in shards:
        data = json.loads(fp.read_text(encoding='utf-8'))
        flags = []
        for row in data['stocks'].values():
            rets = simple_returns(row)
            if len(rets) < MIN_DAYS_YEARLY:
                continue
            ps = arch_test(rets)
            if ps:
                flags.append(ps[0] < 0.05)
        if flags:
            print(f'  {fp.stem.replace("close_", "")}: {sum(flags)}/{len(flags)}'
                  f' = {sum(flags) / len(flags):.1%}')


if __name__ == '__main__':
    main()
