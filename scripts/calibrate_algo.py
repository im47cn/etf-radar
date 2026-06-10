"""sigmoid K 参数校准 — 通过真实历史数据验证强度分布合理。

设计目标 (design.md §3.2.3):
- 前 20% 主题强度落在 75-99 (top)
- 中 60% 落在 30-75 (middle)
- 后 20% 落在 0-30 (bottom)

用法:
    cd backend && uv run python ../scripts/calibrate_algo.py

输出不同 K 值下的分布, 偏差 ≤15% 标记 ✓。
"""
import logging
import sys
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / 'backend'))

from src.config_loader import load_themes  # noqa: E402
from src.providers.yfinance_provider import YfinanceProvider  # noqa: E402
from src.scoring.returns import compute_returns  # noqa: E402
from src.scoring.strength import dim_aggregate_return, strength_per_dim  # noqa: E402


# (lo_inclusive, hi_exclusive, target_ratio)
TARGET_BINS: dict[str, tuple[int, int, float]] = {
    'top_20_pct':    (75, 100, 0.20),
    'middle_60_pct': (30,  75, 0.60),
    'bottom_20_pct': ( 0,  30, 0.20),
}


def evaluate_distribution(strengths: list[int]) -> dict[str, float]:
    n = len(strengths)
    if n == 0:
        return {bin_name: 0.0 for bin_name in TARGET_BINS}
    counts = dict.fromkeys(TARGET_BINS, 0)
    for s in strengths:
        for bin_name, (lo, hi, _target) in TARGET_BINS.items():
            if lo <= s < hi:
                counts[bin_name] += 1
                break
    return {bin_name: counts[bin_name] / n for bin_name in counts}


def main() -> None:
    logging.basicConfig(level=logging.WARNING)
    themes = load_themes(ROOT / 'config' / 'themes.yml')
    provider = YfinanceProvider()
    us_ohlc = {}
    for t in themes:
        try:
            us_ohlc[t.id] = provider.fetch_ohlc(t.primary_us, lookback_days=400)
            print(f'fetched {t.primary_us}')
        except Exception as e:
            print(f'FAIL {t.primary_us}: {e}')

    returns = {tid: compute_returns(df) for tid, df in us_ohlc.items()}
    pool_short = [r for r in (dim_aggregate_return(r, 'short') for r in returns.values()) if r is not None]

    if not pool_short:
        print('No US data fetched, abort.')
        return

    for k in [3.0, 5.0, 7.0]:
        strengths: list[int] = []
        for _tid, r in returns.items():
            ret = dim_aggregate_return(r, 'short')
            if ret is None:
                continue
            strengths.append(strength_per_dim(ret, pool_short, k=k, days_in_dim=3))
        if not strengths:
            continue
        dist = evaluate_distribution(strengths)
        print(f'\nK={k}: distribution={dist}, mean={mean(strengths):.1f}')
        for bin_name, ratio in dist.items():
            target = TARGET_BINS[bin_name][2]
            ok = '✓' if abs(ratio - target) <= 0.15 else '✗'
            print(f'  {bin_name}: {ratio:.2%} (target {target:.0%}) {ok}')


if __name__ == '__main__':
    main()
