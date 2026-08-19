"""贵金属指标管线: yfinance 美股侧宏观指标 -> data/latest/metals.json.

/mets 页(/metals)后端。四个宏观组件 + A股端引用, 任一组件数据源失败
仅降级该组件 (source_status='missing', 值为 null), 不阻塞整文件;
核心金银比组件失败则整跑失败 (CI 可见)。

口径: 金银比 = GLD/SLV 收盘价比, 5y(1260日) trailing 分位含自身 —
与 scripts/research/gsr_timing_backtest.py 预注册回测一致。
回测结论 (2026-08-19): 择时无 alpha (Q5 超额 +4.94%, p=0.168),
本文件产出仅作描述性展示, 不生成任何信号。
"""
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
from numpy.typing import NDArray

from ..output.writer import atomic_write_json
from ..providers.base import EtfDataProvider, ProviderError
from .indicators import (
    GSR_WINDOW,
    change_over,
    gold_silver_ratio,
    rolling_corr,
    rolling_percentile,
    simple_return,
)

log = logging.getLogger(__name__)
BJT = ZoneInfo('Asia/Shanghai')

SCHEMA_VERSION = '1.0'
SYMBOLS = ('GLD', 'SLV', 'GDX', 'TIP', 'DX-Y.NYB')
LOOKBACK_DAYS = 2600  # 自然日, 覆盖 1260 交易日分位窗 + 1y 展示序列
SERIES_LEN = 252  # 金银比趋势序列长度 (1y)
MINER_WINDOW = 252  # 金矿杠杆比 1y 分位窗口
CORR_WINDOW = 20  # 金价-实际利率 20 日滚动相关
CN_GOLD, CN_SILVER = '518880', '161226'

Array = NDArray[np.float64]


def _closes(df: Any) -> tuple[list[str], Array]:
    """standardize 后的 OHLC -> (日期字符串列表, 收盘价数组)."""
    dates = [d.strftime('%Y-%m-%d') for d in df['date']]
    return dates, df['close'].to_numpy(dtype=np.float64)


def _fetch(provider: EtfDataProvider) -> dict[str, tuple[list[str], Array]]:
    """拉取全部 symbol; 单 symbol 失败不阻断, 由调用方按组件判缺失."""
    out: dict[str, tuple[list[str], Array]] = {}
    for sym in SYMBOLS:
        try:
            out[sym] = _closes(provider.fetch_ohlc(sym, LOOKBACK_DAYS))
        except Exception as e:  # noqa: BLE001  组件级降级
            log.warning('metals fetch %s failed: %s', sym, e)
    return out


def _tail(dates: list[str], values: Array, n: int) -> list[list[Any]]:
    """末尾 n 个 (date, value) 对, 供前端趋势序列; 不足 n 取全部."""
    start = max(0, len(values) - n)
    return [[dates[i], float(values[i])] for i in range(start, len(values))]


def _or_none(x: float) -> float | None:
    """nan -> None, 防 NaN 混入 JSON (JSON.parse 不认)."""
    return None if np.isnan(x) else float(x)


def compute_metals(closes: dict[str, tuple[list[str], Array]]) -> dict[str, Any]:
    """组装 metals.json dict; 缺失组件降级为 null + status='missing'."""
    def have(*syms: str) -> bool:
        return all(s in closes for s in syms)

    out: dict[str, Any] = {
        'schema_version': SCHEMA_VERSION,
        'generated_at': datetime.now(UTC).astimezone(BJT).isoformat(),
        'as_of': None,
        'gold_silver_ratio': {'value': None, 'percentile_5y': None, 'series': []},
        'real_rate': {'tip_price': None, 'change_60d': None, 'corr_gold_20d': None},
        'dxy': {'value': None, 'r_20d': None, 'r_60d': None},
        'miner_leverage': {'ratio': None, 'percentile_1y': None},
        'cn_side': {'gold_etf': None, 'silver_lof': None},
        'source_status': {},
    }
    status = out['source_status']
    for key in ('gold_silver', 'real_rate', 'dxy', 'miner_leverage'):
        status[key] = 'missing'

    # 核心组件: 金银比 (GLD/SLV 对齐到共同日期)
    if have('GLD', 'SLV'):
        gd, gp = closes['GLD']
        sd, sp = closes['SLV']
        common = sorted(set(gd) & set(sd))
        gi = {d: i for i, d in enumerate(gd)}
        si = {d: i for i, d in enumerate(sd)}
        g = np.array([gp[gi[d]] for d in common])
        s = np.array([sp[si[d]] for d in common])
        ratio = gold_silver_ratio(g, s)
        pct = rolling_percentile(ratio, GSR_WINDOW)
        out['gold_silver_ratio'] = {
            'value': float(ratio[-1]),
            'percentile_5y': _or_none(pct[-1]),
            'series': _tail(common, ratio, SERIES_LEN),
        }
        out['as_of'] = common[-1]
        status['gold_silver'] = 'ok'

        # 金矿杠杆比 (GDX/GLD) 复用同一对齐
        if 'GDX' in closes:
            xd, xp = closes['GDX']
            xi = {d: i for i, d in enumerate(xd)}
            shared = [d for d in common if d in xi]
            if shared:
                lev = xp[[xi[d] for d in shared]] / g[[gi[d] for d in shared]]
                lp = rolling_percentile(lev, MINER_WINDOW)
                out['miner_leverage'] = {
                    'ratio': float(lev[-1]),
                    'percentile_1y': _or_none(lp[-1]),
                }
                status['miner_leverage'] = 'ok'

        # 实际利率方向代理: TIP (iShares TIPS ETF) 价格, Yahoo 已下线 DFII10.
        # TIP 价格与实际利率反向; 与金价 20 日滚动相关 (金价用对齐后 g).
        if 'TIP' in closes:
            fd, fp = closes['TIP']
            fi = {d: i for i, d in enumerate(fd)}
            shared = [d for d in common if d in fi]
            if len(shared) > CORR_WINDOW + 1:
                f = fp[[fi[d] for d in shared]]
                gg = g[[gi[d] for d in shared]]
                out['real_rate'] = {
                    'tip_price': float(f[-1]),
                    'change_60d': change_over(f, 60) if len(f) > 60 else None,
                    'corr_gold_20d': _or_none(rolling_corr(gg, f, CORR_WINDOW)[-1]),
                }
                status['real_rate'] = 'ok'
    else:
        status['gold_silver'] = 'missing'

    if 'DX-Y.NYB' in closes:
        _, dp = closes['DX-Y.NYB']
        out['dxy'] = {
            'value': float(dp[-1]),
            'r_20d': simple_return(dp, 20) if len(dp) > 20 else None,
            'r_60d': simple_return(dp, 60) if len(dp) > 60 else None,
        }
        status['dxy'] = 'ok'
    else:
        status['dxy'] = 'missing'

    if out['gold_silver_ratio']['value'] is None:
        raise ProviderError('metals: core gold_silver component missing (GLD/SLV)')
    return out


def _cn_side(data_root: Path) -> dict[str, Any]:
    """从已落盘的 latest/etfs.json 提取 A 股端行情; 缺失返回占位."""
    out: dict[str, Any] = {'gold_etf': None, 'silver_lof': None}
    try:
        etfs = json.loads((Path(data_root) / 'latest' / 'etfs.json').read_text(encoding='utf-8'))['etfs']
        by_code = {e['code']: e for e in etfs}
        for key, code in (('gold_etf', CN_GOLD), ('silver_lof', CN_SILVER)):
            e = by_code.get(code)
            if e is not None:
                out[key] = {
                    'code': code,
                    'name': e.get('name'),
                    'price': e.get('price'),
                    'r_1d': (e.get('returns') or {}).get('r_1d'),
                    'amount_yi': e.get('amount_yi'),
                    'premium_pct': None,  # LOF 溢价数据源未接, 预留
                }
    except (OSError, KeyError, json.JSONDecodeError) as e:
        log.warning('metals cn_side degraded: %s', e)
    return out


def run(data_root: Path, provider: EtfDataProvider | None = None) -> Path:
    """拉取 -> 计算 -> 写 data_root/latest/metals.json."""
    from ..providers.yfinance_provider import YfinanceProvider

    provider = provider or YfinanceProvider()
    closes = _fetch(provider)
    snapshot = compute_metals(closes)
    snapshot['cn_side'] = _cn_side(data_root)
    snapshot['source_status']['cn_side'] = 'ok' if snapshot['cn_side']['gold_etf'] else 'missing'
    out = Path(data_root) / 'latest' / 'metals.json'
    atomic_write_json(out, snapshot)
    log.info('metals written: as_of=%s, status=%s', snapshot['as_of'], snapshot['source_status'])
    return out


def main() -> None:
    import argparse

    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s %(message)s')
    parser = argparse.ArgumentParser(description='贵金属指标管线')
    parser.add_argument('--data-root', type=Path, default=Path('data'))
    args = parser.parse_args()
    run(args.data_root)


if __name__ == '__main__':
    main()
