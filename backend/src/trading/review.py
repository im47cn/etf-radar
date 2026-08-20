"""复盘评分 — 纪律分四维 + 结果分 + 聚合统计 (spec 2026-08-20 §2.5, 纯函数无 IO).

口径:
- 纪律分 0-100, 四维各 25 (证据不足按未达成计, 不折算):
  1) entry_in_buy_zone   首笔入场价在入场日买区 [pivot, pivot x1.05] 内
  2) stop_discipline     首笔带初始止损, 且止损触发 (收盘 < 当日有效止损位) 后
                         EXIT_RESPONSE_DAYS 个交易日内退出; 从未触发视为遵守
  3) exit_responsiveness 持仓期间最后一次信号事件 (跌破50MA/转Stage3/4) 后
                         EXIT_RESPONSE_DAYS 个交易日内退出; 无事件视为遵守
  4) position_compliance equity 未配置视为合规; 配置后查 单票市值上限 +
                         单笔风险预算 (含 5% 容差)
- 结果分: result_r (实现盈亏/初始风险额, 无初始止损则 None)、
  holding_days (入场..退出交易日数)、mae_pct ((持仓期最低价-入场价)/入场价)
- 聚合: 胜率/平均R/盈亏比/期望/最大回撤, 按入场日环境档位切片
    (regime 历史由 actions_main 的 state 文件累积, 缺失归 unknown)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

EXIT_RESPONSE_DAYS = 2  # 止损/信号事件后的响应窗口 (交易日)
RISK_TOLERANCE = 1.05  # 单笔风险预算容差 5%


@dataclass(frozen=True)
class RoundTrip:
    """一笔完整交易 (事件流按 M3 derivePositions 规则回放切出)。

    open/add/reduce/close 语义与前端一致; reduce 扣到 <=0 视同清仓。
    """

    code: str
    name: str
    events: list[dict[str, Any]]  # 该笔全部原始事件 (按时间升序)
    open_date: str
    open_price: float
    open_shares: int
    stop_at_open: float | None  # 首笔后的 stop_after (初始风险锚点)
    close_date: str
    close_price: float
    realized_pnl: float  # Σ卖出收入 - Σ买入支出


@dataclass(frozen=True)
class ReviewContext:
    """复盘一笔所需的行情/设置上下文 (由 actions_main 组装)。"""

    buy_zone: tuple[float, float] | None  # 入场日买区 (low, high); 无 VCP 结构为 None
    holding_days: list[str]  # 入场日..退出日交易日序列 (ISO, 含两端)
    closes: list[float]  # 对齐 holding_days 的收盘价
    lows: list[float]  # 对齐 holding_days 的最低价 (MAE)
    stop_levels: list[float | None]  # 对齐每日的有效止损位 (事件回放)
    signal_event_dates: list[str]  # 持仓期间信号事件日 (跌破50MA / 转Stage3/4)
    equity: float | None
    risk_per_trade_pct: float  # 默认 0.75
    max_position_pct: float  # 默认 20


@dataclass(frozen=True)
class TradeReviewResult:
    """单笔复盘结果 (对应 trade_reviews 一行, events 为细节快照)。"""

    code: str
    name: str
    open_date: str
    close_date: str
    realized_pnl: float
    discipline_score: int  # 0-100
    dimensions: dict[str, bool]  # 四维达成与否 (顺序稳定)
    result_r: float | None
    holding_days: int  # 交易日数
    mae_pct: float | None
    events: dict[str, Any] = field(default_factory=dict)


def split_round_trips(trades: list[dict[str, Any]]) -> list[RoundTrip]:
    """事件流 -> 完成的一笔笔交易 (进行中的持仓尾部丢弃)。

    回放规则与 M3 derivePositions 一致: (trade_date, created_at) 升序;
    open/add 累加、reduce 扣减 (<=0 视同清仓)、close 清仓。
    无持仓时的 add 视作 open; 无持仓的 reduce/close 忽略。
    """
    def sort_key(t: dict[str, Any]) -> tuple[str, str]:
        return (str(t['trade_date']), str(t['created_at']))

    by_code: dict[str, list[dict[str, Any]]] = {}
    for t in sorted(trades, key=sort_key):
        by_code.setdefault(str(t['code']), []).append(t)

    trips: list[RoundTrip] = []
    for code, events in by_code.items():
        shares = 0
        cost = 0.0  # Σ买入支出
        proceeds = 0.0  # Σ卖出收入
        cur: list[dict[str, Any]] = []
        first: dict[str, Any] | None = None
        for t in events:
            side = str(t['side'])
            price, qty = float(t['price']), int(t['shares'])
            if side in ('open', 'add'):
                if shares == 0:  # open 开新笔; 无持仓 add 容错视作 open
                    first, cur = t, [t]
                else:
                    cur.append(t)
                shares += qty
                cost += price * qty
            elif side == 'reduce':
                if shares <= 0:
                    continue  # 无持仓 reduce: 忽略 (脏数据)
                proceeds += price * qty
                shares -= qty
                cur.append(t)
                if shares <= 0:  # 超额减仓视同清仓
                    trips.append(_make_trip(code, first, cur, price, cost, proceeds))
                    shares, first, cur = 0, None, []
            elif side == 'close':
                if shares > 0:
                    proceeds += price * qty
                    cur.append(t)
                    trips.append(_make_trip(code, first, cur, price, cost, proceeds))
                shares, first, cur = 0, None, []
        # 尾部 shares>0 为进行中持仓, 不入复盘
    return trips


def _make_trip(
    code: str,
    first: dict[str, Any] | None,
    events: list[dict[str, Any]],
    close_price: float,
    cost: float,
    proceeds: float,
) -> RoundTrip:
    close_event = events[-1]
    assert first is not None, 'round trip 必有首笔'
    stop_after_raw = first.get('stop_after')
    return RoundTrip(
        code=code,
        name=str(first['name']),
        events=events,
        open_date=str(first['trade_date']),
        open_price=float(first['price']),
        open_shares=int(first['shares']),
        stop_at_open=float(stop_after_raw) if stop_after_raw is not None else None,
        close_date=str(close_event['trade_date']),
        close_price=close_price,
        realized_pnl=round(proceeds - cost, 2),
    )


def _stop_trigger_idx(ctx: ReviewContext) -> int | None:
    """首个收盘 < 当日有效止损位的交易日下标 (止损位 None 的日子跳过)。"""
    for i, (c, stop) in enumerate(zip(ctx.closes, ctx.stop_levels)):
        if stop is not None and c < stop:
            return i
    return None


def _within_days(from_idx: int, to_idx: int, window: int) -> bool:
    """from_idx 到 to_idx 的交易日距离 <= window (含当日)。"""
    return 0 <= to_idx - from_idx <= window


def _dimension_scores(rt: RoundTrip, ctx: ReviewContext) -> dict[str, bool]:
    # 1) 入场在买区 (无买区结构 = 不在任何已识别买区, 按未达成计)
    d1 = ctx.buy_zone is not None and ctx.buy_zone[0] <= rt.open_price <= ctx.buy_zone[1]
    # 2) 止损纪律: 有初始止损 + 触发后 2 交易日内退出 (或从未触发)
    if rt.stop_at_open is None:
        d2 = False
    else:
        trig = _stop_trigger_idx(ctx)
        d2 = trig is None or _within_days(trig, len(ctx.holding_days) - 1, EXIT_RESPONSE_DAYS)
    # 3) 退出响应: 最后一次信号事件后 2 交易日内退出 (或无事件)
    idx_of = {d: i for i, d in enumerate(ctx.holding_days)}
    ev_idxs = [idx_of[d] for d in ctx.signal_event_dates if d in idx_of]
    if not ev_idxs:
        d3 = True
    else:
        d3 = _within_days(max(ev_idxs), len(ctx.holding_days) - 1, EXIT_RESPONSE_DAYS)
    # 4) 仓位合规: equity 未配置视为合规 (无法判定不惩罚)
    if ctx.equity is None or ctx.equity <= 0:
        d4 = True
    else:
        market_value = rt.open_shares * rt.open_price
        cap_ok = market_value <= ctx.equity * ctx.max_position_pct / 100
        if rt.stop_at_open is None:
            d4 = cap_ok  # 无止损无法核风险额, 仅查市值
        else:
            risk_amt = rt.open_shares * abs(rt.open_price - float(rt.stop_at_open))
            risk_ok = risk_amt <= ctx.equity * ctx.risk_per_trade_pct / 100 * RISK_TOLERANCE
            d4 = cap_ok and risk_ok
    return {'entry_in_buy_zone': d1, 'stop_discipline': d2, 'exit_responsiveness': d3, 'position_compliance': d4}


def review_round_trip(rt: RoundTrip, ctx: ReviewContext) -> TradeReviewResult:
    """单笔复盘: 纪律四维 + 结果分 (R/持仓天数/MAE)。"""
    dims = _dimension_scores(rt, ctx)
    score = 25 * sum(dims.values())

    initial_risk: float | None = None
    if rt.stop_at_open is not None:
        initial_risk = rt.open_shares * abs(rt.open_price - float(rt.stop_at_open))
    result_r = round(rt.realized_pnl / initial_risk, 3) if initial_risk and initial_risk > 0 else None

    mae: float | None = None
    if ctx.lows:
        mae = round((min(ctx.lows) - rt.open_price) / rt.open_price * 100, 2)

    return TradeReviewResult(
        code=rt.code,
        name=rt.name,
        open_date=rt.open_date,
        close_date=rt.close_date,
        realized_pnl=rt.realized_pnl,
        discipline_score=score,
        dimensions=dims,
        result_r=result_r,
        holding_days=len(ctx.holding_days),
        mae_pct=mae,
        events={'dimensions': dims, 'open_stop': rt.stop_at_open, 'pnl': rt.realized_pnl},
    )


@dataclass(frozen=True)
class AggregateStats:
    """聚合统计 (按整体与按入场日环境档位切片同构)。"""

    n: int
    win_rate: float | None  # 实现盈亏 > 0 占比
    avg_r: float | None  # 平均可得 R
    profit_factor: float | None  # 盈亏比 Σ盈利/|Σ亏损| (无亏损 None)
    expectancy: float | None  # 期望 = 平均实现盈亏
    max_drawdown: float | None  # 累计盈亏峰谷回撤 (金额)
    by_regime: dict[str, dict[str, Any]] = field(default_factory=dict)


def _stats_of(results: list[TradeReviewResult]) -> dict[str, Any]:
    n = len(results)
    if n == 0:
        return {'n': 0, 'win_rate': None, 'avg_r': None, 'profit_factor': None, 'expectancy': None, 'max_drawdown': None}
    wins = [r for r in results if r.realized_pnl > 0]
    losses = [r for r in results if r.realized_pnl < 0]
    rs = [r.result_r for r in results if r.result_r is not None]
    gross_win = sum(r.realized_pnl for r in wins)
    gross_loss = sum(r.realized_pnl for r in losses)
    # 最大回撤: 按 close_date 排序的累计盈亏峰谷
    cum, peak, mdd = 0.0, 0.0, 0.0
    for r in sorted(results, key=lambda x: x.close_date):
        cum += r.realized_pnl
        peak = max(peak, cum)
        mdd = max(mdd, peak - cum)
    return {
        'n': n,
        'win_rate': round(len(wins) / n, 4),
        'avg_r': round(sum(rs) / len(rs), 3) if rs else None,
        'profit_factor': round(gross_win / abs(gross_loss), 3) if gross_loss < 0 else None,
        'expectancy': round(sum(r.realized_pnl for r in results) / n, 2),
        'max_drawdown': round(mdd, 2) if mdd > 0 else 0.0,
    }


def aggregate_stats(
    results: list[TradeReviewResult], regime_by_date: dict[str, str] | None
) -> AggregateStats:
    """整体统计 + 按入场日环境档位切片 (缺失归 unknown)。"""
    overall = _stats_of(results)
    by_regime: dict[str, dict[str, Any]] = {}
    buckets: dict[str, list[TradeReviewResult]] = {}
    for r in results:
        regime = (regime_by_date or {}).get(r.open_date, 'unknown')
        buckets.setdefault(regime, []).append(r)
    for regime, rs in buckets.items():
        by_regime[regime] = _stats_of(rs)
    return AggregateStats(
        n=overall['n'],
        win_rate=overall['win_rate'],
        avg_r=overall['avg_r'],
        profit_factor=overall['profit_factor'],
        expectancy=overall['expectancy'],
        max_drawdown=overall['max_drawdown'],
        by_regime=by_regime,
    )
