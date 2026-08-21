"""Actions 每晚流程 — 持仓信号 + 复盘评分 + 推送 (spec 2026-08-20 §1.8/§2.5 M4).

编排 (在 M1 trading.json 产出之后运行):
1. 读 data/latest/trading.json + 通知状态文件 (上次 states + regime 历史)
2. Supabase (service_role REST, 仿 notify/digest.py): 拉 trades/trading_settings
3. 持仓推导 (规则与 M3 derivePositions 一致) -> holding_signals 每日信号
4. round trip 切分 -> review 复盘评分 -> 幂等写 trade_reviews
   (无 UNIQUE, 按 user_id+review_date 先删后插)
5. ServerChan 推送: watch->in_buy_zone 日报; 周日加周报 (B1 仅 owner)

降级: Supabase 不可达 (env 缺失/网络失败) -> 复盘跳过 + 告警推送, 日报照常。
本地验证: uv run python -m src.trading.actions_main --data-root ../data --dry-run
(不写 Supabase 不推送不落状态文件, 打印全部内容)。
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import urllib.error
import urllib.request
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import numpy as np

from ..notify.alert import send_alert
from ..output.writer import atomic_write_json
from .holding_signals import Holding, HoldingSignalResult, compute_holding_signals
from .notify_digest import build_daily_message, build_weekly_message
from .review import (
    ReviewContext,
    aggregate_stats,
    review_round_trip,
    split_round_trips,
)
from .trend import compute_trend, sma
from .vcp import find_vcp

log = logging.getLogger(__name__)

STATE_FILENAME = 'trading_notify_state.json'
DEFAULT_SETTINGS = {'equity_cny': None, 'risk_per_trade_pct': 0.75, 'max_position_pct': 20.0}


# ============================================================
# Supabase REST (service_role, stdlib urllib — 仿 notify/digest.py)
# ============================================================
class TradingRest:
    """极简 PostgREST 封装, 仅覆盖本任务读写; 失败抛异常 (供整体降级)。"""

    def __init__(self, base_url: str, service_role_key: str) -> None:
        self._base = base_url.rstrip('/')
        self._key = service_role_key

    @classmethod
    def from_env(cls) -> TradingRest:
        url, key = os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_SERVICE_ROLE_KEY')
        if not url or not key:
            raise RuntimeError('缺少环境变量: SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY')
        return cls(url, key)

    def _request(
        self, method: str, path: str, *, headers: dict[str, str] | None = None, body: Any = None
    ) -> Any:
        req = urllib.request.Request(
            f'{self._base}{path}',
            data=json.dumps(body).encode('utf-8') if body is not None else None,
            method=method,
            headers={
                'apikey': self._key,
                'Authorization': f'Bearer {self._key}',
                'Content-Type': 'application/json',
                **(headers or {}),
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode('utf-8')
        except urllib.error.HTTPError as e:
            detail = e.read().decode('utf-8', 'replace')
            raise RuntimeError(f'Supabase {method} {path} 失败 {e.code}: {detail}') from e
        return json.loads(raw) if raw else None

    def select(self, table: str, query: str = '') -> list[dict[str, Any]]:
        sep = '?' if query and not query.startswith('?') else ''
        result = self._request('GET', f'/rest/v1/{table}{sep}{query}')
        return result if isinstance(result, list) else []

    def insert(self, table: str, rows: list[dict[str, Any]]) -> None:
        self._request(
            'POST', f'/rest/v1/{table}', headers={'Prefer': 'return=minimal'}, body=rows
        )

    def delete(self, table: str, query: str) -> None:
        self._request('DELETE', f'/rest/v1/{table}?{query}', headers={'Prefer': 'return=minimal'})


# ============================================================
# 持仓推导 (规则与 M3 frontend derivePositions 一致)
# ============================================================
def _parse_trades(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """REST 行标准化: numeric 序列化为字符串 -> float/int。"""
    out: list[dict[str, Any]] = []
    for r in rows:
        stop = r.get('stop_after')
        out.append(
            {
                'id': str(r['id']),
                'user_id': str(r['user_id']),
                'code': str(r['code']),
                'name': str(r['name']),
                'side': str(r['side']),
                'trade_date': str(r['trade_date']),
                'price': float(r['price']),
                'shares': int(r['shares']),
                'stop_after': float(stop) if stop is not None else None,
                'reason': r.get('reason'),
                'created_at': str(r.get('created_at', '')),
            }
        )
    return out


def derive_positions(trades: list[dict[str, Any]]) -> list[Holding]:
    """事件流 -> 当前持仓 (open/add 累加、reduce 扣减、close 清仓; M3 规则)。"""
    by_code: dict[str, Holding] = {}
    for t in sorted(trades, key=lambda x: (x['trade_date'], x['created_at'])):
        cur = by_code.get(t['code'])
        if t['side'] in ('open', 'add'):
            prev_shares = cur.shares if cur else 0
            prev_cost = cur.avg_cost if cur else 0.0
            shares = prev_shares + t['shares']
            avg_cost = t['price'] if prev_shares == 0 else (prev_cost * prev_shares + t['price'] * t['shares']) / shares
            stop = t['stop_after'] if t['stop_after'] is not None else (cur.stop_current if cur else None)
            by_code[t['code']] = Holding(
                code=t['code'], name=t['name'], shares=shares,
                avg_cost=round(avg_cost, 4), stop_current=stop,
            )
        elif t['side'] == 'reduce':
            if cur is None:
                continue
            shares = cur.shares - t['shares']
            if shares <= 0:
                del by_code[t['code']]
                continue
            by_code[t['code']] = Holding(
                code=cur.code, name=cur.name, shares=shares, avg_cost=cur.avg_cost,
                stop_current=t['stop_after'] if t['stop_after'] is not None else cur.stop_current,
            )
        elif t['side'] == 'close':
            by_code.pop(t['code'], None)
    return list(by_code.values())


# ============================================================
# 复盘上下文组装 (ohlcv 历史回放)
# ============================================================
def _load_bars(ohlcv_dir: Path, code: str) -> list[dict[str, Any]]:
    """读 ohlcv/{code}.json (M0 §2.2); 缺失/损坏返回空。"""
    try:
        doc = json.loads((ohlcv_dir / f'{code}.json').read_text(encoding='utf-8'))
        bars = doc['bars']
        return list(bars) if isinstance(bars, list) else []
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as e:
        log.warning('actions_main bars skip %s: %s', code, e)
        return []


def _replay_stop_levels(events: list[dict[str, Any]], days: list[str]) -> list[float | None]:
    """持仓窗每日有效止损位: 截至该日最后一个 stop_after (M3 规则: 每笔后更新)。"""
    by_day: dict[str, float] = {}
    for e in sorted(events, key=lambda x: (x['trade_date'], x.get('created_at', ''))):
        if e.get('stop_after') is not None:
            by_day[str(e['trade_date'])] = float(e['stop_after'])
    levels: list[float | None] = []
    cur: float | None = None
    for d in days:
        if d in by_day:
            cur = by_day[d]
        levels.append(cur)
    return levels


def _replay_signal_event_dates(
    dates: list[str], high: np.ndarray, low: np.ndarray, close: np.ndarray, i0: int, i1: int
) -> list[str]:
    """持仓窗内信号事件日回放: 跌破50MA 穿越日 + 转 Stage 3/4 日 (rs_pct 历史不可得, 恒 None)。"""
    events: list[str] = []
    ma50 = sma(close, 50)
    prev_stage: int | None = None
    for i in range(i0, i1 + 1):
        if (
            i >= 1
            and not np.isnan(ma50[i])
            and not np.isnan(ma50[i - 1])
            and close[i - 1] >= ma50[i - 1]
            and close[i] < ma50[i]
        ):
            events.append(dates[i])
        t = compute_trend(high[: i + 1], low[: i + 1], close[: i + 1], None)
        stage = t.stage if t else None
        if stage in (3, 4) and prev_stage is not None and prev_stage != stage and dates[i] not in events:
            events.append(dates[i])
        prev_stage = stage
    return events


def _build_review_context(
    rt_events: list[dict[str, Any]],
    open_date: str,
    close_date: str,
    bars: list[dict[str, Any]],
    settings: dict[str, Any],
) -> ReviewContext | None:
    """round trip 行情上下文; bars 缺失或日期不在序列内返回 None (跳过该笔)。"""
    dates = [str(b['d']) for b in bars]
    if open_date not in dates or close_date not in dates:
        return None
    i0, i1 = dates.index(open_date), dates.index(close_date)
    high = np.array([float(b['h']) for b in bars], dtype=np.float64)
    low = np.array([float(b['l']) for b in bars], dtype=np.float64)
    close = np.array([float(b['c']) for b in bars], dtype=np.float64)
    volume = np.array([float(b.get('v', 0.0)) for b in bars], dtype=np.float64)
    days = dates[i0 : i1 + 1]

    # 入场日买区: 截断到入场日的 VCP 结构 (当日视角, 无前视)
    buy_zone: tuple[float, float] | None = None
    vcp = find_vcp(close[: i0 + 1], volume[: i0 + 1])
    if vcp is not None:
        buy_zone = (vcp.buy_zone_low, vcp.buy_zone_high)

    return ReviewContext(
        buy_zone=buy_zone,
        holding_days=days,
        closes=[float(x) for x in close[i0 : i1 + 1]],
        lows=[float(x) for x in low[i0 : i1 + 1]],
        stop_levels=_replay_stop_levels(rt_events, days),
        signal_event_dates=_replay_signal_event_dates(dates, high, low, close, i0, i1),
        equity=settings.get('equity_cny'),
        risk_per_trade_pct=float(settings.get('risk_per_trade_pct', 0.75)),
        max_position_pct=float(settings.get('max_position_pct', 20.0)),
    )


def _settings_of(rows: list[dict[str, Any]], user_id: str) -> dict[str, Any]:
    """该用户 trading_settings (无行用默认值; numeric 字符串转 float)。"""
    row = next((r for r in rows if str(r.get('user_id')) == user_id), None)
    if row is None:
        return dict(DEFAULT_SETTINGS)
    equity = row.get('equity_cny')
    return {
        'equity_cny': float(equity) if equity is not None else None,
        'risk_per_trade_pct': float(row.get('risk_per_trade_pct', 0.75)),
        'max_position_pct': float(row.get('max_position_pct', 20.0)),
    }


# ============================================================
# 状态文件 (推送迁移对比 + regime 历史累积)
# ============================================================
def _read_state(data_root: Path) -> dict[str, Any]:
    try:
        doc = json.loads(
            (data_root / 'latest' / STATE_FILENAME).read_text(encoding='utf-8')
        )
        return doc if isinstance(doc, dict) else {}
    except (OSError, ValueError, json.JSONDecodeError):
        return {}


def _write_state(data_root: Path, trading_doc: dict[str, Any], as_of: date, prev: dict[str, Any]) -> None:
    regime_history = dict(prev.get('regime_history', {}))
    regime = trading_doc.get('environment', {}).get('regime')
    if regime:
        regime_history[as_of.isoformat()] = str(regime)
    states = {str(c.get('code')): str(c.get('state')) for c in trading_doc.get('candidates', [])}
    atomic_write_json(
        data_root / 'latest' / STATE_FILENAME,
        {
            'updated_at': datetime.now(UTC).isoformat(),
            'states': states,
            'regime_history': regime_history,
        },
    )


# ============================================================
# 主编排
# ============================================================
def run(
    data_root: Path,
    dry_run: bool = False,
    as_of: date | None = None,
    rest: TradingRest | None = None,
) -> int:
    """每晚 EOD 主流程; 返回 0 (降级不算失败, 已通过告警渠道暴露)。"""
    data_root = Path(data_root)
    as_of = as_of or datetime.now(UTC).astimezone().date()  # 本地时区当日 (同 pipeline 语义)

    trading_doc = json.loads((data_root / 'latest' / 'trading.json').read_text(encoding='utf-8'))
    prev_state = _read_state(data_root)
    prev_states = dict(prev_state.get('states', {}))
    regime_history = dict(prev_state.get('regime_history', {}))
    if trading_doc.get('environment', {}).get('regime'):
        regime_history[as_of.isoformat()] = str(trading_doc['environment']['regime'])

    holdings: list[HoldingSignalResult] = []
    reviews: list[dict[str, Any]] = []  # trade_reviews 行 (全用户)
    results_by_user: dict[str, list[Any]] = {}  # 按用户收集, 聚合统计按用户物化
    stats = aggregate_stats([], None)
    degraded = False

    try:
        rest = rest or TradingRest.from_env()
        trade_rows = rest.select('trades', 'select=*&order=trade_date.asc,created_at.asc')
        setting_rows = rest.select('trading_settings', 'select=*')
        ohlcv_dir = data_root / 'stocks' / 'ohlcv'
        bars_cache: dict[str, list[dict[str, Any]]] = {}

        def bars_of(code: str) -> list[dict[str, Any]]:
            if code not in bars_cache:
                bars_cache[code] = _load_bars(ohlcv_dir, code)
            return bars_cache[code]

        for user_id in sorted({str(r['user_id']) for r in trade_rows}):
            user_trades = _parse_trades([r for r in trade_rows if str(r['user_id']) == user_id])
            settings = _settings_of(setting_rows, user_id)

            for pos in derive_positions(user_trades):
                holdings.append(compute_holding_signals(pos, bars_of(pos.code), trading_doc, as_of))

            for rt in split_round_trips(user_trades):
                ctx = _build_review_context(rt.events, rt.open_date, rt.close_date, bars_of(rt.code), settings)
                if ctx is None:
                    log.warning('actions_main review skip %s %s: bars 缺失', rt.code, rt.open_date)
                    continue
                result = review_round_trip(rt, ctx)
                results_by_user.setdefault(user_id, []).append(result)
                reviews.append(
                    {
                        'user_id': user_id,
                        'trade_id': rt.events[0]['id'],
                        'review_date': as_of.isoformat(),
                        'discipline_score': result.discipline_score,
                        'result_r': result.result_r,
                        'mae_pct': result.mae_pct,
                        'events': {
                            'dimensions': result.dimensions,
                            'open_date': result.open_date,
                            'close_date': result.close_date,
                            'realized_pnl': result.realized_pnl,
                            'holding_days': result.holding_days,
                        },
                    }
                )

        # 幂等写: 无 UNIQUE, 按 user+review_date 先删后插
        if not dry_run and reviews:
            for user_id in sorted({r['user_id'] for r in reviews}):
                rest.delete(
                    'trade_reviews', f'user_id=eq.{user_id}&review_date=eq.{as_of.isoformat()}'
                )
                rest.insert('trade_reviews', [r for r in reviews if r['user_id'] == user_id])
        # 聚合统计物化: 按用户覆写 review_aggregates (PK=user_id), 前端只读此快照,
        # 消除前后端双实现口径漂移。有交易的用户才写; 无交易用户保留旧快照 (口径历史)。
        if not dry_run:
            for user_id, results in sorted(results_by_user.items()):
                user_stats = aggregate_stats(results, regime_history)
                rest.delete('review_aggregates', f'user_id=eq.{user_id}')
                rest.insert(
                    'review_aggregates',
                    [
                        {
                            'user_id': user_id,
                            'as_of': as_of.isoformat(),
                            'stats': {
                                'n': user_stats.n,
                                'win_rate': user_stats.win_rate,
                                'avg_r': user_stats.avg_r,
                                'profit_factor': user_stats.profit_factor,
                                'expectancy': user_stats.expectancy,
                                'max_drawdown': user_stats.max_drawdown,
                                'by_regime': user_stats.by_regime,
                            },
                        }
                    ],
                )
        stats = aggregate_stats(
            [r for rs in results_by_user.values() for r in rs], regime_history
        )
    except Exception as e:  # noqa: BLE001  整体降级: 复盘跳过 + 告警
        degraded = True
        log.warning('actions_main Supabase 降级: %s', e)
        if not dry_run:
            send_alert('[etf-radar] 交易复盘降级', f'Supabase 不可达，复盘评分跳过：\n{e}')

    daily = build_daily_message(trading_doc, prev_states, as_of)
    weekly = (
        build_weekly_message(trading_doc, stats, holdings, as_of)
        if as_of.isoweekday() == 7
        else None
    )

    if dry_run:
        print(f'[dry-run] as_of={as_of} degraded={degraded} reviews={len(reviews)}')
        if daily:
            print(f'[dry-run] 日报:\n{daily[0]}\n{daily[1]}')
        else:
            print('[dry-run] 日报: 无迁移, 不发送')
        if weekly:
            print(f'[dry-run] 周报:\n{weekly[0]}\n{weekly[1]}')
        return 0

    if daily:
        send_alert(daily[0], daily[1])
    if weekly:
        send_alert(weekly[0], weekly[1])
    _write_state(data_root, trading_doc, as_of, prev_state)
    log.info('actions_main done: degraded=%s, holdings=%d, reviews=%d', degraded, len(holdings), len(reviews))
    return 0


def main() -> None:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s %(message)s')
    parser = argparse.ArgumentParser(description='SEPA 交易 Actions 每晚流程 (复盘+推送)')
    parser.add_argument('--data-root', type=Path, default=Path('../data'))
    parser.add_argument('--dry-run', action='store_true', help='不写 Supabase 不推送不落状态文件')
    parser.add_argument('--as-of', type=date.fromisoformat, default=None, help='基准日 (默认今天)')
    args = parser.parse_args()
    raise SystemExit(run(args.data_root, dry_run=args.dry_run, as_of=args.as_of))


if __name__ == '__main__':  # pragma: no cover
    main()
