"""主流水线 — 编排 providers / scoring / output 三层。

调用入口:
- `python -m src.pipeline --mode=full` 全量重算
- `python -m src.pipeline --mode=intraday` 仅刷新当前价格 (轻量)
- `python -m src.pipeline --mode=archive` 归档 latest/ 到 snapshots/<today>/
"""
from __future__ import annotations

import argparse
import logging
import random
import time
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

import pandas as pd  # type: ignore[import-untyped]

from .config_loader import load_algo_config, load_themes
from .etl.calendar import (
    BJT,
    is_cn_session_active,
    is_cn_trading_day,
    is_us_session_active,
    is_us_trading_day,
)
from .models import (
    AlgoConfig,
    CalendarInfo,
    DimName,
    FullRefreshTimes,
    MetaInfo,
    PairSignal,
    ProviderInfo,
    ProviderStatus,
    Rank,
    Returns,
    SignalsSummary,
    Strength,
    ThemeConfig,
    ThemeSignal,
    TopTheme,
)
from .output.descriptions import theme_dynamic_description
from .output.writer import atomic_write_json
from .providers.akshare_em_provider import AkshareEmProvider
from .providers.akshare_sina_provider import AkshareSinaProvider
from .providers.base import EmptyDataError, EtfDataProvider, ProviderError
from .providers.yfinance_provider import YfinanceProvider
from .scoring.mapping import mapping_score
from .scoring.returns import compute_returns
from .scoring.signals import signal_for_pair, signal_for_theme
from .scoring.strength import (
    composite_strength,
    dim_aggregate_return,
    strength_per_dim,
)

log = logging.getLogger(__name__)


DIMS: list[DimName] = ['short', 'mid', 'long']


class PipelineMode(str, Enum):
    FULL = 'full'
    INTRADAY = 'intraday'
    ARCHIVE = 'archive'


def _collect_us_ohlc(
    themes: list[ThemeConfig], provider: EtfDataProvider,
) -> tuple[dict[str, pd.DataFrame], list[str]]:
    out: dict[str, pd.DataFrame] = {}
    failed: list[str] = []
    symbols: set[str] = set()
    for t in themes:
        symbols.update(t.us_etfs)
    for sym in sorted(symbols):
        try:
            out[sym] = provider.fetch_ohlc(sym, lookback_days=400)
        except (ProviderError, EmptyDataError) as e:
            log.warning(f'US fetch failed {sym}: {e}')
            failed.append(sym)
    return out, failed


def _collect_cn_ohlc(
    themes: list[ThemeConfig],
    providers: list[EtfDataProvider],
) -> tuple[dict[str, pd.DataFrame], dict[str, str], list[str]]:
    """A 股 ETF 数据采集 (provider chain).

    单 symbol 内按 providers 顺序即时切换：首选失败立即试下一个，
    第一个成功即停止。所有 provider 都失败的 symbol 进 failed 列表。

    返回:
      out: 成功获取的 OHLC 数据
      fallback_map: {symbol: provider.name} 走了非首选 provider 的 symbol
      failed: 所有 provider 都失败的 symbol
    """
    out: dict[str, pd.DataFrame] = {}
    fallback_map: dict[str, str] = {}
    failed: list[str] = []
    codes: set[str] = set()
    for t in themes:
        for cn in t.cn_etfs:
            codes.add(cn.code)

    for code in sorted(codes):
        success_provider: EtfDataProvider | None = None
        for provider in providers:
            try:
                out[code] = provider.fetch_ohlc(code, lookback_days=400)
                success_provider = provider
                break
            except (ProviderError, EmptyDataError) as e:
                log.warning(f'CN fetch failed [{provider.name}] {code}: {e}')
                continue

        if success_provider is None:
            failed.append(code)
        elif success_provider.name != providers[0].name:
            fallback_map[code] = success_provider.name

        time.sleep(random.uniform(0.3, 1.0))
    return out, fallback_map, failed


def _theme_returns(t: ThemeConfig, us_ohlc: dict[str, pd.DataFrame]) -> Returns:
    df = us_ohlc.get(t.primary_us)
    if df is None or df.empty:
        return Returns()
    return compute_returns(df)


def _strength_for_pool(
    own_dim_ret: float | None,
    pool_dim_rets: list[float],
    k: float, days: int,
) -> int:
    """空 pool 或缺数据时返回 0 (而非 raise), pipeline 层不应崩溃。"""
    if own_dim_ret is None or not pool_dim_rets:
        return 0
    return strength_per_dim(own_dim_ret, pool_dim_rets, k=k, days_in_dim=days)


def compute_outputs(
    themes: list[ThemeConfig],
    us_ohlc: dict[str, pd.DataFrame],
    cn_ohlc: dict[str, pd.DataFrame],
    us_failed: list[str],
    cn_failed: list[str],
    algo: AlgoConfig,
    asof_bjt: datetime,
    mode: PipelineMode,
    backfilled: bool = False,
    cn_fallback_map: dict[str, str] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    """从已采集的 OHLC 数据计算并构造 4 个输出 JSON（themes/etfs/signals/meta）。

    asof_bjt 是 as-of 锚定时间（BJT, 带时区）。所有 calendar 字段、generated_at
    均基于此时间。pipeline.run_pipeline 调用时传 datetime.now(tz=BJT)，
    backfill 脚本调用时传该 D 当晚 16:00 BJT。

    cn_fallback_map: {symbol: provider_name} 走了非首选 provider 的 symbol。
        当 cn_fallback_map 非空且 cn_failed 为空时，cn provider status = 'fallback'。

    返回顺序: (themes_json, etfs_json, signals_json, meta_json)
    """
    if cn_fallback_map is None:
        cn_fallback_map = {}
    today_bjt = asof_bjt.date()
    asof_utc = asof_bjt.astimezone(timezone.utc)

    # 1) 每个主题的收益
    theme_returns: dict[str, Returns] = {t.id: _theme_returns(t, us_ohlc) for t in themes}

    # 2) 每个 A 股 ETF 的收益
    cn_returns: dict[str, Returns] = {
        code: compute_returns(df) for code, df in cn_ohlc.items()
    }

    # 3) 池内 dim aggregate (过滤 None)
    theme_dim_rets: dict[DimName, list[float]] = {
        dim: [
            r for r in (dim_aggregate_return(theme_returns[t.id], dim) for t in themes)
            if r is not None
        ]
        for dim in DIMS
    }
    cn_dim_rets_pool: dict[DimName, list[float]] = {
        dim: [
            r for r in (dim_aggregate_return(cn_returns[code], dim) for code in cn_returns)
            if r is not None
        ]
        for dim in DIMS
    }

    # 4) 主题强度
    k = algo.strength.k_sigmoid
    days = algo.strength.days_in_dim
    cw = algo.strength.composite_weights
    theme_strengths: dict[str, Strength] = {}
    for t in themes:
        r = theme_returns[t.id]
        s = _strength_for_pool(dim_aggregate_return(r, 'short'),
                               theme_dim_rets['short'], k, days['short'])
        m = _strength_for_pool(dim_aggregate_return(r, 'mid'),
                               theme_dim_rets['mid'], k, days['mid'])
        long_s = _strength_for_pool(dim_aggregate_return(r, 'long'),
                                    theme_dim_rets['long'], k, days['long'])
        c = composite_strength(s, m, long_s, cw['short'], cw['mid'], cw['long'])
        theme_strengths[t.id] = Strength(short=s, mid=m, long=long_s, composite=c)

    # 5) A 股 ETF 强度
    cn_strengths: dict[str, Strength] = {}
    for code in cn_returns:
        r = cn_returns[code]
        s = _strength_for_pool(dim_aggregate_return(r, 'short'),
                               cn_dim_rets_pool['short'], k, days['short'])
        m = _strength_for_pool(dim_aggregate_return(r, 'mid'),
                               cn_dim_rets_pool['mid'], k, days['mid'])
        long_s = _strength_for_pool(dim_aggregate_return(r, 'long'),
                                    cn_dim_rets_pool['long'], k, days['long'])
        c = composite_strength(s, m, long_s, cw['short'], cw['mid'], cw['long'])
        cn_strengths[code] = Strength(short=s, mid=m, long=long_s, composite=c)

    # 6) 排名 (按综合)
    sorted_ids = sorted(theme_strengths.keys(),
                        key=lambda i: theme_strengths[i].composite, reverse=True)
    theme_ranks: dict[str, int] = {tid: i + 1 for i, tid in enumerate(sorted_ids)}

    # 7) 映射分 + 信号
    pair_signals: list[PairSignal] = []
    theme_signals: list[ThemeSignal] = []
    for t in themes:
        us_df = us_ohlc.get(t.primary_us)
        candidates: list[dict[str, Any]] = []
        for cn in t.cn_etfs:
            cn_df = cn_ohlc.get(cn.code)
            ms: int | None = None
            if us_df is not None and cn_df is not None:
                ms = mapping_score(us_df, cn_df,
                                   window=algo.mapping.corr_window_days,
                                   min_aligned=algo.mapping.min_aligned_days)
            conf = algo.confidence.exact if cn.match_type == 'exact' else algo.confidence.wide

            cn_str_obj = cn_strengths.get(cn.code, Strength(short=0, mid=0, long=0, composite=0))
            r = cn_returns.get(cn.code, Returns())
            cn_dim_returns_dict: dict[str, float | None] = {
                dim: dim_aggregate_return(r, dim) for dim in DIMS
            }

            candidates.append({
                'code': cn.code, 'mapping_score': ms, 'confidence': conf,
                'cn_strength': cn_str_obj, 'cn_dim_returns': cn_dim_returns_dict,
            })

        us_str_obj = theme_strengths[t.id]
        us_r = theme_returns[t.id]
        us_dim_returns_dict: dict[str, float | None] = {
            dim: dim_aggregate_return(us_r, dim) for dim in DIMS
        }

        # 主题级信号
        theme_sig, trigger_code, theme_votes = signal_for_theme(
            us_strength=us_str_obj, us_dim_returns=us_dim_returns_dict,
            cn_candidates=candidates, cfg=algo.signal,
        )
        theme_signals.append(ThemeSignal(
            theme_id=t.id,
            signal=theme_sig,
            trigger_cn_etf=trigger_code,
            votes=theme_votes if theme_votes else {'short': None, 'mid': None, 'long': None},
            description=theme_dynamic_description(t.name, theme_sig, us_str_obj.mid),
        ))

        # 配对级信号
        for cn_data in candidates:
            sig, votes = signal_for_pair(
                us_strength=us_str_obj, cn_strength=cn_data['cn_strength'],
                us_dim_returns=us_dim_returns_dict, cn_dim_returns=cn_data['cn_dim_returns'],
                cfg=algo.signal,
            )
            pair_signals.append(PairSignal(
                theme_id=t.id, cn_code=cn_data['code'],
                mapping_score=cn_data['mapping_score'], confidence=cn_data['confidence'],
                signal=sig, votes=votes,
            ))

    # 8) summary
    sig_counter: dict[str, int] = {'resonance': 0, 'transmission': 0, 'divergence': 0}
    for ts in theme_signals:
        if ts.signal:
            sig_counter[ts.signal] += 1
    top_id = sorted_ids[0] if sorted_ids else None
    top_theme: TopTheme | None = None
    if top_id:
        top_t = next(t for t in themes if t.id == top_id)
        top_theme = TopTheme(
            id=top_id, name=top_t.name, primary_us=top_t.primary_us,
            composite_strength=theme_strengths[top_id].composite,
        )

    cn_codes_unique: set[str] = set()
    for t in themes:
        for cn in t.cn_etfs:
            cn_codes_unique.add(cn.code)

    summary = SignalsSummary(
        themes_total=len(themes),
        etfs_total=len(cn_codes_unique),
        resonance_count=sig_counter['resonance'],
        transmission_count=sig_counter['transmission'],
        divergence_count=sig_counter['divergence'],
        top_theme=top_theme,
    )

    # 9) 构造 JSON
    themes_json: dict[str, Any] = {
        'schema_version': '1.0',
        'generated_at': asof_bjt.isoformat(),
        'themes': [
            {
                'id': t.id, 'name': t.name, 'us_etfs': t.us_etfs,
                'primary_us': t.primary_us, 'tags': t.tags, 'note': t.note,
                'returns': theme_returns[t.id].model_dump(),
                'strength': theme_strengths[t.id].model_dump(),
                'rank': Rank(
                    short=theme_ranks[t.id], mid=theme_ranks[t.id],
                    long=theme_ranks[t.id], composite=theme_ranks[t.id],
                ).model_dump(),
            } for t in themes
        ],
    }

    etfs_list: list[dict[str, Any]] = []
    cn_codes_seen: set[str] = set()
    for t in themes:
        for cn in t.cn_etfs:
            if cn.code in cn_codes_seen:
                continue
            cn_codes_seen.add(cn.code)
            r = cn_returns.get(cn.code, Returns())
            df = cn_ohlc.get(cn.code)
            price: float | None = None
            amount: float | None = None
            if df is not None and not df.empty:
                price = float(df['close'].iloc[-1])
                amount_raw = df['amount'].iloc[-1]
                if pd.notna(amount_raw):
                    amount = float(amount_raw) / 1e8
            etfs_list.append({
                'code': cn.code, 'name': cn.name, 'tracking_index': cn.tracking,
                'returns': r.model_dump(),
                'amount_yi': amount, 'price': price,
                'strength': cn_strengths.get(
                    cn.code, Strength(short=0, mid=0, long=0, composite=0),
                ).model_dump(),
            })
    etfs_json: dict[str, Any] = {
        'schema_version': '1.0',
        'generated_at': asof_bjt.isoformat(),
        'etfs': etfs_list,
    }

    signals_json: dict[str, Any] = {
        'schema_version': '1.0',
        'generated_at': asof_bjt.isoformat(),
        'summary': summary.model_dump(),
        'theme_signals': [ts.model_dump() for ts in theme_signals],
        'pair_signals': [ps.model_dump() for ps in pair_signals],
    }

    if cn_failed:
        cn_status: ProviderStatus = 'degraded'
    elif cn_fallback_map:
        cn_status = 'fallback'
    else:
        cn_status = 'ok'

    meta = MetaInfo(
        last_full_refresh=FullRefreshTimes(us=asof_bjt.isoformat(), cn=asof_bjt.isoformat()),
        last_intraday_refresh=asof_bjt.isoformat() if mode == PipelineMode.INTRADAY else None,
        providers={
            'us': ProviderInfo(status='ok' if not us_failed else 'degraded', name='yfinance'),
            'cn': ProviderInfo(status=cn_status, name='akshare-sina'),
        },
        failed_symbols=us_failed + cn_failed,
        fallback_symbols=cn_fallback_map,
        stale_minutes=0,
        calendar=CalendarInfo(
            us_trading_today=is_us_trading_day(today_bjt),
            cn_trading_today=is_cn_trading_day(today_bjt),
            us_session_active=is_us_session_active(asof_utc),
            cn_session_active=is_cn_session_active(asof_bjt),
        ),
        backfilled=backfilled,
    )
    meta_json: dict[str, Any] = meta.model_dump()

    return themes_json, etfs_json, signals_json, meta_json


def run_pipeline(
    mode: PipelineMode,
    data_root: Path,
    config_dir: Path,
) -> None:
    log.info(f'pipeline start mode={mode}')
    themes = load_themes(config_dir / 'themes.yml')
    algo = load_algo_config(config_dir / 'algo.yml')

    yf_provider = YfinanceProvider()
    # CN provider chain: sina 优先（稳定但不复权），em 兜底（前复权但东财对部分热门 ETF 间歇失败）
    # 决策见 06-19 fallback 调查：23 个核心主题 ETF 对 em 长期失败 → 牺牲复权一致性换稳定性
    cn_providers: list[EtfDataProvider] = [
        AkshareSinaProvider(),
        AkshareEmProvider(),
    ]

    us_ohlc, us_failed = _collect_us_ohlc(themes, yf_provider)
    cn_ohlc, cn_fallback_map, cn_failed = _collect_cn_ohlc(themes, cn_providers)

    now_utc = datetime.now(timezone.utc)
    now_bjt = now_utc.astimezone(BJT)
    themes_json, etfs_json, signals_json, meta_json = compute_outputs(
        themes, us_ohlc, cn_ohlc, us_failed, cn_failed, algo,
        asof_bjt=now_bjt, mode=mode, cn_fallback_map=cn_fallback_map,
    )

    atomic_write_json(data_root / 'latest' / 'themes.json', themes_json)
    atomic_write_json(data_root / 'latest' / 'etfs.json', etfs_json)
    atomic_write_json(data_root / 'latest' / 'signals.json', signals_json)
    atomic_write_json(data_root / 'latest' / 'meta.json', meta_json)
    log.info(f'pipeline done, failed={len(us_failed) + len(cn_failed)}')


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', type=PipelineMode, default=PipelineMode.FULL)
    parser.add_argument('--data-root', type=Path, default=Path('data'))
    parser.add_argument('--config-dir', type=Path, default=Path('config'))
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s %(levelname)s %(name)s: %(message)s')

    if args.mode == PipelineMode.ARCHIVE:
        from .output.archiver import archive_latest
        # 使用 BJT 日期作为归档目录, 与 A 股市场对齐
        today_bjt = datetime.now(tz=BJT).date()
        archive_latest(args.data_root, today_bjt)
        return
    run_pipeline(args.mode, args.data_root, args.config_dir)


if __name__ == '__main__':
    main()
