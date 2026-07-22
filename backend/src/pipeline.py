"""主流水线 — 编排 providers / scoring / output 三层。

调用入口:
- `python -m src.pipeline --mode=full` 全量重算
- `python -m src.pipeline --mode=intraday` 仅刷新当前价格 (轻量)
- `python -m src.pipeline --mode=archive` 归档 latest/ 到 snapshots/<today>/
"""
from __future__ import annotations

import argparse
import json
import logging
import random
import time
from datetime import date, datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, NamedTuple, cast

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
    Strength,
    ThemeConfig,
    ThemeSignal,
)
from .output.descriptions import theme_dynamic_description
from .output.no_regress import should_write_latest
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
        if t.us_etfs:  # cn_only 主题 us_etfs 为空列表，跳过
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
    expected_cn_date: date | None = None,
) -> tuple[dict[str, pd.DataFrame], dict[str, str], list[str]]:
    """A 股 ETF 数据采集 (provider chain).

    单 symbol 内按 providers 顺序即时切换：首选失败立即试下一个。
    当 expected_cn_date 非空时, provider "成功但返回旧 bar" (最新 bar < 期望日)
    视同失败, 继续试下一个源 (根治 em 静默旧 bar 不触发 sina 回退的残根)。
    所有源都只有旧 bar 时, 保留其中**最新**的一份兜底返回 (不丢数据,
    交由下游 cn_stale/archiver 护栏拦截)。所有源都抛异常才进 failed。

    返回:
      out: 成功获取的 OHLC 数据
      fallback_map: {symbol: provider.name} 走了非首选 provider 的 symbol
      failed: 所有 provider 都失败(异常)的 symbol
    """
    out: dict[str, pd.DataFrame] = {}
    fallback_map: dict[str, str] = {}
    failed: list[str] = []
    codes: set[str] = set()
    for t in themes:
        for cn in t.cn_etfs:
            codes.add(cn.code)

    for code in sorted(codes):
        # 全源皆旧时保留最新的一份兜底
        best_df: pd.DataFrame | None = None
        best_provider: EtfDataProvider | None = None
        best_date: date | None = None
        for provider in providers:
            try:
                df = provider.fetch_ohlc(code, lookback_days=400)
            except (ProviderError, EmptyDataError) as e:
                log.warning(f'CN fetch failed [{provider.name}] {code}: {e}')
                continue

            bar_date = _df_latest_date(df)
            if expected_cn_date is None or (
                bar_date is not None and bar_date >= expected_cn_date
            ):
                # 无期望或够新 → 立即采纳
                best_df, best_provider, best_date = df, provider, bar_date
                break
            # 旧 bar: 视同失败, 记录最新候选后继续试下一个源
            if best_date is None or (bar_date is not None and bar_date > best_date):
                best_df, best_provider, best_date = df, provider, bar_date
            log.warning(
                f'CN stale bar [{provider.name}] {code}: '
                f'latest={bar_date} < expected={expected_cn_date}, 试下一源'
            )

        if best_provider is None:
            failed.append(code)
        else:
            out[code] = best_df
            if best_provider.name != providers[0].name:
                fallback_map[code] = best_provider.name

        time.sleep(random.uniform(0.3, 1.0))
    return out, fallback_map, failed


def _latest_bar_date(ohlc: dict[str, pd.DataFrame]) -> date | None:
    """一组 OHLC 中最新的 bar 日期 (跨 symbol 取 max), 空则 None."""
    dates = [df['date'].dt.date.max() for df in ohlc.values() if not df.empty]
    return max(dates) if dates else None


def _df_latest_date(df: pd.DataFrame | None) -> date | None:
    """单个 OHLC 的最新 bar 日期, 空则 None."""
    if df is None or df.empty:
        return None
    return cast('date | None', df['date'].dt.date.max())


# A 股厂商 (em/sina) EOD 结算发布时点: 收盘后当日 bar 通常 18:00 BJT 前后才 roll 出.
# 早于此时点即使已收盘, 缺当日 bar 也属正常, 不判陈旧 (避免 15:00-18:00 窗口误报回退).
CN_SETTLE_HOUR = 18


def _expected_cn_date(now_bjt: datetime) -> date | None:
    """本次采集**应当**拿到的最新 CN bar 日期; 无明确期望时返回 None.

    仅当"今天是 A 股交易日且已过厂商结算时点"才期望今日 bar; 盘中/结算前/
    非交易日一律 None (拿到啥用啥), 由 fetch 层据此决定是否把旧 bar 视同失败.
    """
    today = now_bjt.date()
    if is_cn_trading_day(today) and now_bjt.hour >= CN_SETTLE_HOUR:
        return today
    return None


def _theme_returns(t: ThemeConfig, us_ohlc: dict[str, pd.DataFrame]) -> Returns:
    # cn_only 主题没有美股锚点，直接返回空 Returns
    if not t.primary_us:
        return Returns()
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


# ---------------------------------------------------------------------------
# compute_outputs 拆分：4 个阶段子函数 + 编排层
# ---------------------------------------------------------------------------

class _ComputeContext(NamedTuple):
    """compute_outputs 内部阶段间传递的共享状态。"""
    theme_returns: dict[str, Returns]
    cn_returns: dict[str, Returns]
    theme_strengths: dict[str, Strength]
    cn_strengths: dict[str, Strength]
    cn_theme_strengths: dict[str, Strength]
    display_strengths: dict[str, Strength]
    theme_ranks: dict[str, int]
    cn_theme_primary: dict[str, str]


def _compute_all_strengths(
    themes: list[ThemeConfig],
    us_ohlc: dict[str, pd.DataFrame],
    cn_ohlc: dict[str, pd.DataFrame],
    algo: AlgoConfig,
) -> _ComputeContext:
    """阶段 1-6：从 OHLC 数据计算收益 → 池强度 → 排名。

    返回各强度字典和排名, 供后续信号计算和 JSON 构造使用。
    """
    # 1) 每个主题的收益
    theme_returns: dict[str, Returns] = {t.id: _theme_returns(t, us_ohlc) for t in themes}

    # 2) 每个 A 股 ETF 的收益
    cn_returns: dict[str, Returns] = {
        code: compute_returns(df) for code, df in cn_ohlc.items()
    }

    # 3) 池内 dim aggregate (过滤 None)
    theme_dim_rets: dict[DimName, list[float]] = {
        dim: [
            r for r in (
                dim_aggregate_return(theme_returns[t.id], dim)
                for t in themes if t.primary_us
            )
            if r is not None
        ] for dim in DIMS
    }
    cn_dim_rets_pool: dict[DimName, list[float]] = {
        dim: [
            r for r in (dim_aggregate_return(cn_returns[code], dim) for code in cn_returns)
            if r is not None
        ] for dim in DIMS
    }

    # 4) US 主题池强度（仅 mapped 主题参与）
    k = algo.strength.k_sigmoid
    days = algo.strength.days_in_dim
    cw = algo.strength.composite_weights
    theme_strengths: dict[str, Strength] = {}
    for t in themes:
        if not t.primary_us:
            continue
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

    # 5b) CN 主题池强度
    cn_theme_primary: dict[str, str] = {}
    cn_theme_returns: dict[str, Returns] = {}
    for t in themes:
        primary_code: str | None = t.primary_cn or (t.cn_etfs[0].code if t.cn_etfs else None)
        if primary_code is None:
            continue
        cn_theme_primary[t.id] = primary_code
        cn_theme_returns[t.id] = cn_returns.get(primary_code, Returns())

    cn_theme_dim_rets: dict[DimName, list[float]] = {
        dim: [
            r for r in (
                dim_aggregate_return(cn_theme_returns[tid], dim)
                for tid in cn_theme_returns
            )
            if r is not None
        ] for dim in DIMS
    }
    cn_theme_strengths: dict[str, Strength] = {}
    for tid, r in cn_theme_returns.items():
        s = _strength_for_pool(dim_aggregate_return(r, 'short'),
                               cn_theme_dim_rets['short'], k, days['short'])
        m = _strength_for_pool(dim_aggregate_return(r, 'mid'),
                               cn_theme_dim_rets['mid'], k, days['mid'])
        long_s = _strength_for_pool(dim_aggregate_return(r, 'long'),
                                    cn_theme_dim_rets['long'], k, days['long'])
        c = composite_strength(s, m, long_s, cw['short'], cw['mid'], cw['long'])
        cn_theme_strengths[tid] = Strength(short=s, mid=m, long=long_s, composite=c)

    # 6) 排名
    display_strengths: dict[str, Strength] = {
        t.id: (theme_strengths[t.id] if t.id in theme_strengths else cn_theme_strengths[t.id])
        for t in themes
        if t.id in theme_strengths or t.id in cn_theme_strengths
    }
    sorted_ids = sorted(display_strengths.keys(),
                        key=lambda i: display_strengths[i].composite, reverse=True)
    theme_ranks: dict[str, int] = {tid: i + 1 for i, tid in enumerate(sorted_ids)}

    return _ComputeContext(
        theme_returns=theme_returns,
        cn_returns=cn_returns,
        theme_strengths=theme_strengths,
        cn_strengths=cn_strengths,
        cn_theme_strengths=cn_theme_strengths,
        display_strengths=display_strengths,
        theme_ranks=theme_ranks,
        cn_theme_primary=cn_theme_primary,
    )


def _compute_signals(
    themes: list[ThemeConfig],
    ctx: _ComputeContext,
    us_ohlc: dict[str, pd.DataFrame],
    cn_ohlc: dict[str, pd.DataFrame],
    algo: AlgoConfig,
) -> tuple[list[ThemeSignal], list[PairSignal]]:
    """阶段 7：映射分 + 信号计算。

    返回 (theme_signals, pair_signals)。
    """
    pair_signals: list[PairSignal] = []
    theme_signals: list[ThemeSignal] = []
    for t in themes:
        if not t.primary_us:
            theme_signals.append(ThemeSignal(
                theme_id=t.id, signal=None, trigger_cn_etf=None,
                votes={'short': None, 'mid': None, 'long': None},
                description=f"{t.name}（A 股本土赛道）",
            ))
            continue

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

            cn_str_obj = ctx.cn_strengths.get(cn.code, Strength(short=0, mid=0, long=0, composite=0))
            r = ctx.cn_returns.get(cn.code, Returns())
            cn_dim_returns_dict: dict[str, float | None] = {
                dim: dim_aggregate_return(r, dim) for dim in DIMS
            }

            candidates.append({
                'code': cn.code, 'mapping_score': ms, 'confidence': conf,
                'cn_strength': cn_str_obj, 'cn_dim_returns': cn_dim_returns_dict,
            })

        us_str_obj = ctx.theme_strengths[t.id]
        us_r = ctx.theme_returns[t.id]
        us_dim_returns_dict: dict[str, float | None] = {
            dim: dim_aggregate_return(us_r, dim) for dim in DIMS
        }

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

    return theme_signals, pair_signals


def _build_output_jsons(
    themes: list[ThemeConfig],
    ctx: _ComputeContext,
    us_ohlc: dict[str, pd.DataFrame],
    cn_ohlc: dict[str, pd.DataFrame],
    us_failed: list[str],
    theme_signals: list[ThemeSignal],
    pair_signals: list[PairSignal],
    asof_bjt: datetime,
    mode: PipelineMode,
    backfilled: bool,
    cn_failed: list[str],
    cn_fallback_map: dict[str, str],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    """阶段 8：构造 4 个输出 JSON（themes/etfs/signals/meta）。"""
    def _strength_dump(s: Strength | None) -> dict[str, Any] | None:
        return s.model_dump() if s else None

    themes_json: dict[str, Any] = {
        'schema_version': '1.1',
        'generated_at': asof_bjt.isoformat(),
        'themes': [
            {
                'id': t.id, 'name': t.name, 'us_etfs': t.us_etfs,
                'primary_us': t.primary_us,
                'primary_cn': t.primary_cn or ctx.cn_theme_primary.get(t.id),
                'tags': t.tags, 'note': t.note,
                'returns': (
                    ctx.theme_returns[t.id].model_dump() if t.primary_us
                    else ctx.cn_returns.get(
                        ctx.cn_theme_primary.get(t.id, ''), Returns()
                    ).model_dump()
                ),
                'strength': ctx.display_strengths[t.id].model_dump(),
                'us_strength': _strength_dump(ctx.theme_strengths.get(t.id)),
                'cn_strength': _strength_dump(ctx.cn_theme_strengths.get(t.id)),
                'rank': Rank(
                    short=ctx.theme_ranks[t.id], mid=ctx.theme_ranks[t.id],
                    long=ctx.theme_ranks[t.id], composite=ctx.theme_ranks[t.id],
                ).model_dump(),
            } for t in themes if t.id in ctx.display_strengths
        ],
    }

    cn_code_to_theme_ids: dict[str, list[str]] = {}
    for t in themes:
        for cn in t.cn_etfs:
            cn_code_to_theme_ids.setdefault(cn.code, []).append(t.id)

    etfs_list: list[dict[str, Any]] = []
    cn_codes_seen: set[str] = set()
    for t in themes:
        for cn in t.cn_etfs:
            if cn.code in cn_codes_seen:
                continue
            cn_codes_seen.add(cn.code)
            r = ctx.cn_returns.get(cn.code, Returns())
            df = cn_ohlc.get(cn.code)
            price: float | None = None
            amount: float | None = None
            if df is not None and not df.empty:
                price = float(df['close'].iloc[-1])
                amount_raw = df['amount'].iloc[-1]
                if pd.notna(amount_raw):
                    amount = float(amount_raw) / 1e8
            theme_ids = cn_code_to_theme_ids[cn.code]
            etfs_list.append({
                'code': cn.code, 'name': cn.name, 'tracking_index': cn.tracking,
                'theme_id': theme_ids[0],
                'theme_ids': theme_ids,
                'returns': r.model_dump(),
                'amount_yi': amount, 'price': price,
                'strength': ctx.cn_strengths.get(
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
        'theme_signals': [ts.model_dump() for ts in theme_signals],
        'pair_signals': [ps.model_dump() for ps in pair_signals],
    }

    # meta
    today_bjt = asof_bjt.date()
    asof_utc = asof_bjt.astimezone(timezone.utc)
    cn_data_date = _latest_bar_date(cn_ohlc)
    us_data_date = _latest_bar_date(us_ohlc)

    cn_stale = (
        is_cn_trading_day(today_bjt)
        and not is_cn_session_active(asof_bjt)
        and cn_data_date is not None
        and cn_data_date < today_bjt
    )
    stale_minutes = (today_bjt - cn_data_date).days * 1440 if cn_stale and cn_data_date else 0

    if cn_stale:
        cn_status: ProviderStatus = 'stale'
    elif cn_failed:
        cn_status = 'degraded'
    elif cn_fallback_map:
        cn_status = 'fallback'
    else:
        cn_status = 'ok'

    meta = MetaInfo(
        last_full_refresh=FullRefreshTimes(us=asof_bjt.isoformat(), cn=asof_bjt.isoformat()),
        last_intraday_refresh=asof_bjt.isoformat() if mode == PipelineMode.INTRADAY else None,
        providers={
            'us': ProviderInfo(status='ok' if not us_failed else 'degraded', name='yfinance'),
            'cn': ProviderInfo(status=cn_status, name='akshare-em'),
        },
        failed_symbols=us_failed + cn_failed,
        fallback_symbols=cn_fallback_map,
        stale_minutes=stale_minutes,
        cn_data_date=cn_data_date.isoformat() if cn_data_date else None,
        us_data_date=us_data_date.isoformat() if us_data_date else None,
        calendar=CalendarInfo(
            us_trading_today=is_us_trading_day(today_bjt),
            cn_trading_today=is_cn_trading_day(today_bjt),
            us_session_active=is_us_session_active(asof_utc),
            cn_session_active=is_cn_session_active(asof_bjt),
        ),
        backfilled=backfilled,
    )
    meta_json: dict[str, Any] = meta.model_dump()
    meta_json['theme_kinds'] = {
        'mapped': sum(1 for t in themes if t.primary_us),
        'cn_only': sum(1 for t in themes if not t.primary_us),
    }

    return themes_json, etfs_json, signals_json, meta_json


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

    # 阶段 1-6：收益 → 池强度 → 排名
    ctx = _compute_all_strengths(themes, us_ohlc, cn_ohlc, algo)

    # 阶段 7：映射分 + 信号
    theme_signals, pair_signals = _compute_signals(
        themes, ctx, us_ohlc, cn_ohlc, algo,
    )

    # 阶段 8：构造输出 JSON
    return _build_output_jsons(
        themes, ctx, us_ohlc, cn_ohlc, us_failed,
        theme_signals, pair_signals,
        asof_bjt, mode, backfilled,
        cn_failed, cn_fallback_map,
    )


def _write_latest_guarded(
    data_root: Path,
    themes_json: dict[str, Any],
    etfs_json: dict[str, Any],
    signals_json: dict[str, Any],
    meta_json: dict[str, Any],
) -> bool:
    """写 data/latest 四文件, 前置 no-regress 护栏。

    若新数据相对现有 latest 回退(见 should_write_latest)则整体跳过写入,
    保留上一好版本并记 latest_write_skipped_regress 日志(供 C1 哨兵消费),
    返回 False; 正常写入返回 True。
    """
    latest = data_root / 'latest'
    meta_path = latest / 'meta.json'
    existing_meta: dict[str, Any] | None = None
    if meta_path.exists():
        try:
            existing_meta = json.loads(meta_path.read_text(encoding='utf-8'))
        except json.JSONDecodeError:
            log.warning(
                'latest/meta.json 损坏, no-regress 护栏按首次写入放行(行为不变, 仅告知)'
            )
            existing_meta = None
    ok, reason = should_write_latest(meta_json, existing_meta)
    if not ok:
        old = existing_meta or {}
        log.error(
            'latest_write_skipped_regress: %s new_cn=%s new_us=%s old_cn=%s old_us=%s',
            reason, meta_json.get('cn_data_date'), meta_json.get('us_data_date'),
            old.get('cn_data_date'), old.get('us_data_date'),
        )
        return False
    atomic_write_json(latest / 'themes.json', themes_json)
    atomic_write_json(latest / 'etfs.json', etfs_json)
    atomic_write_json(latest / 'signals.json', signals_json)
    atomic_write_json(latest / 'meta.json', meta_json)
    return True


def run_pipeline(
    mode: PipelineMode,
    data_root: Path,
    config_dir: Path,
) -> None:
    log.info(f'pipeline start mode={mode}')
    themes = load_themes(config_dir / 'themes.yml')
    algo = load_algo_config(config_dir / 'algo.yml')

    yf_provider = YfinanceProvider()
    cn_providers: list[EtfDataProvider] = [
        AkshareEmProvider(),
        AkshareSinaProvider(),
    ]

    now_utc = datetime.now(timezone.utc)
    now_bjt = now_utc.astimezone(BJT)

    us_ohlc, us_failed = _collect_us_ohlc(themes, yf_provider)
    cn_ohlc, cn_fallback_map, cn_failed = _collect_cn_ohlc(
        themes, cn_providers, expected_cn_date=_expected_cn_date(now_bjt),
    )
    themes_json, etfs_json, signals_json, meta_json = compute_outputs(
        themes, us_ohlc, cn_ohlc, us_failed, cn_failed, algo,
        asof_bjt=now_bjt, mode=mode, cn_fallback_map=cn_fallback_map,
    )

    written = _write_latest_guarded(
        data_root, themes_json, etfs_json, signals_json, meta_json,
    )

    # stocks_spot.json 由独立的 stocks_spot_pipeline 写入（解耦 spot 失败与主链路）
    log.info(
        f'pipeline done, failed={len(us_failed) + len(cn_failed)}, '
        f'latest_written={written}'
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', type=PipelineMode, default=PipelineMode.FULL)
    parser.add_argument('--data-root', type=Path, default=Path('data'))
    parser.add_argument('--config-dir', type=Path, default=Path('config'))
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s %(levelname)s %(name)s: %(message)s')

    if args.mode == PipelineMode.ARCHIVE:
        from .output.archiver import StaleDataError, archive_latest
        # 使用 BJT 日期作为归档目录, 与 A 股市场对齐
        # archive_latest 内部已自动重建 snapshots-index.json (见 archiver.py 不变量)
        today_bjt = datetime.now(tz=BJT).date()
        try:
            dst = archive_latest(args.data_root, today_bjt)
            log.info(f'archived to {dst} (snapshots-index rebuilt)')
        except StaleDataError as e:
            # 数据陈旧: 跳过归档 (当日留空缺口), 不写陈旧快照污染历史.
            log.error(f'archive skipped: {e}')
        return
    run_pipeline(args.mode, args.data_root, args.config_dir)


if __name__ == '__main__':
    main()
