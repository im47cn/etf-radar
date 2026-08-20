"""触发推送内容组装 — 事实性文案 (spec §1.8/§2.5, 合规立场 B).

- 日报: 昨日 watch -> 今日 in_buy_zone 的候选列表
  ("XX 已进入买区 [a-b]，止损参考 c"; 一字涨停附注无法买入)
- 周报 (周日): 复盘聚合统计 + 当前持仓信号摘要
发送统一走 notify/alert.py ServerChan (失败不 raise); B1 仅 owner, 不区分会员。
"""
from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Any

from ..notify.alert import send_alert

if TYPE_CHECKING:  # 仅类型引用, 避免运行时循环依赖风险
    from .holding_signals import HoldingSignalResult
    from .review import AggregateStats

REGIME_LABELS = {'offense': '进攻', 'neutral': '中性', 'defense': '防守'}


def build_daily_message(
    trading_doc: dict[str, Any], prev_states: dict[str, str], as_of: date
) -> tuple[str, str] | None:
    """组装日报 (title, desp); 无 watch->in_buy_zone 迁移返回 None。

    严格口径: 仅昨日状态恰为 watch 且今日 in_buy_zone 才通知
    (昨日无记录/首跑不轰炸; defense 档下 state 全 watch, 天然无迁移)。
    """
    candidates = trading_doc.get('candidates', [])
    regime = str(trading_doc.get('environment', {}).get('regime', 'unknown'))
    moved = [
        c
        for c in candidates
        if c.get('state') == 'in_buy_zone' and prev_states.get(str(c.get('code'))) == 'watch'
    ]
    if not moved:
        return None

    lines = [f'当前环境档位：{REGIME_LABELS.get(regime, regime)}', '', '进入买区标的：']
    for c in moved:
        low, high, stop = c.get('buy_zone_low'), c.get('buy_zone_high'), c.get('stop')
        line = (
            f"- {c.get('code')} {c.get('name')} 已进入买区 "
            f"[{_fmt(low)} - {_fmt(high)}]，止损参考 {_fmt(stop)}"
        )
        if c.get('limit_up_unexecutable'):
            line += '（当日一字涨停，无法买入）'
        lines.append(line)
    title = f'交易信号 {as_of.strftime("%m-%d")}：{len(moved)} 只进入买区'
    return title, '\n'.join(lines)


def build_weekly_message(
    trading_doc: dict[str, Any],
    stats: AggregateStats,
    holdings: list[HoldingSignalResult],
    as_of: date,
) -> tuple[str, str]:
    """组装周报 (title, desp): 复盘聚合 + 持仓健康 + 环境档位。"""
    regime = str(trading_doc.get('environment', {}).get('regime', 'unknown'))
    lines = [f'## 交易周报 {as_of.isoformat()}', '', f'环境档位：{REGIME_LABELS.get(regime, regime)}', '']

    lines.append('### 本周复盘')
    if stats.n == 0:
        lines.append('本周无已完成交易')
    else:
        pf = '∞' if stats.profit_factor is None else f'{stats.profit_factor:.2f}'
        wr = '—' if stats.win_rate is None else f'{stats.win_rate * 100:.0f}%'
        lines.append(f'- 已完成 {stats.n} 笔，胜率 {wr}')
        avg_r = '—' if stats.avg_r is None else f'{stats.avg_r:+.2f}'
        lines.append(f'- 平均 R {avg_r}，盈亏比 {pf}，期望 {stats.expectancy:+.0f} 元')
        if stats.max_drawdown:
            lines.append(f'- 最大回撤 {stats.max_drawdown:.0f} 元')
        for regime_key, sub in sorted(stats.by_regime.items()):
            label = REGIME_LABELS.get(regime_key, regime_key)
            sub_wr = '—' if sub['win_rate'] is None else f"{sub['win_rate'] * 100:.0f}%"
            lines.append(f'- {label}期入场：{sub["n"]} 笔，胜率 {sub_wr}')

    lines.append('')
    lines.append('### 当前持仓')
    if not holdings:
        lines.append('无持仓')
    for h in holdings:
        profit = '—' if h.profit_pct is None else f'{h.profit_pct:+.1f}%'
        status = {'holding': '正常', 'warning': '有事件', 'frozen': '冻结'}[h.health]
        lines.append(f'- {h.code} {h.name}：浮盈 {profit}，{status}')
        for ev in h.events:
            lines.append(f'  - {ev.message}')
    title = f'交易周报 {as_of.strftime("%m-%d")}'
    return title, '\n'.join(lines)


def push_daily(trading_doc: dict[str, Any], prev_states: dict[str, str], as_of: date) -> bool:
    """日报推送; 无迁移不发。返回是否实际发送。"""
    msg = build_daily_message(trading_doc, prev_states, as_of)
    if msg is None:
        return False
    return send_alert(msg[0], msg[1])


def push_weekly(
    trading_doc: dict[str, Any],
    stats: AggregateStats,
    holdings: list[HoldingSignalResult],
    as_of: date,
) -> bool:
    """周报推送 (周日由 actions_main 触发)。"""
    title, desp = build_weekly_message(trading_doc, stats, holdings, as_of)
    return send_alert(title, desp)


def _fmt(v: Any) -> str:
    """价位显示: 数值两位小数, 缺省 '—'。"""
    return f'{float(v):.2f}' if isinstance(v, (int, float)) else '—'
