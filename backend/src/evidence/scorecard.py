"""信号计分卡: resonance/transmission 近端滚动胜率 vs 长期基线, 纯计算无 IO.

已验证长期基线 (5 年样本外回测, 见 memory/resonance):
- resonance 整体 55%, 高置信档 (|us_mom|≥1%) 57%, 弱档 (<0.3%) ≈48% ≈ 随机;
- transmission 长期 49% ≈ 基线, 无预测力 (仅展示"≈随机").
事件口径: 信号日 t 的 theme_signals 事件, 方向 = theme.returns.r_1d 符号 (美股动量代理),
结果 = 下一 snapshot 的 trigger_cn_etf 的 returns.r_1d 是否同向.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# 长期基线 (点估计, 5 年样本外): status 判定参照, 不是 rolling 重估
BASELINES: dict[tuple[str, str | None], float] = {
    ("resonance", None): 0.55,
    ("resonance", "high"): 0.57,
    ("transmission", None): 0.49,
}
HIGH_TIER_ABS_MOM = 0.01   # 高置信档: 事件日 |us_mom| ≥ 1%
MIN_N = 50                 # n<50 -> insufficient (与 IC 回测一致的最小样本量级)
Z_95 = 1.96                # 正态近似 95% CI

# 行输出顺序: resonance 整体 → resonance 高置信档 → transmission
ROW_SPECS: tuple[tuple[str, str | None], ...] = (
    ("resonance", None),
    ("resonance", "high"),
    ("transmission", None),
)


@dataclass(frozen=True)
class SignalEvent:
    """单个信号事件 (由 loader 从 snapshots 构建, 计算层不做 IO).

    day_index: 信号日在 snapshot 日期序列中的下标 (窗口归属用);
    us_mom: 信号日主题 r_1d (方向来源); next_ret: 下一交易日 trigger_cn_etf 的 r_1d.
    """

    day_index: int
    signal: str            # 'resonance' | 'transmission'
    theme_id: str
    us_mom: float
    next_ret: float


def _status(n: int, ci_high: float, baseline: float) -> str:
    """n<50 样本不足; CI 上界仍低于基线 -> 近期降效; 否则与长期一致 (CI 含/超基线)."""
    if n < MIN_N:
        return "insufficient"
    if ci_high < baseline:
        return "degraded"
    return "consistent"


def _row(events: list[SignalEvent], signal: str, tier: str | None, window: int,
         total_days: int) -> dict[str, object]:
    """单 (信号, 档位, 窗口) 的胜率行. 窗口 = 最近 window 个交易日 (按信号日归属)."""
    sel = [e for e in events
           if e.signal == signal
           and e.day_index >= total_days - window
           and (tier is None or abs(e.us_mom) >= HIGH_TIER_ABS_MOM)]
    n = len(sel)
    baseline = BASELINES[(signal, tier)]
    if n == 0:
        return {"signal": signal, "tier": tier, "window_days": window, "n": 0,
                "hit_rate": 0.0, "ci_low": 0.0, "ci_high": 0.0,
                "baseline": baseline, "status": "insufficient"}
    hits = sum(1 for e in sel if np.sign(e.next_ret) == np.sign(e.us_mom) and e.us_mom != 0.0)
    p = hits / n
    half = Z_95 * np.sqrt(p * (1.0 - p) / n)
    ci_low = max(0.0, p - half)
    ci_high = min(1.0, p + half)
    return {"signal": signal, "tier": tier, "window_days": window, "n": n,
            "hit_rate": round(p, 4), "ci_low": round(float(ci_low), 4),
            "ci_high": round(float(ci_high), 4), "baseline": baseline,
            "status": _status(n, float(ci_high), baseline)}


def scorecard_rows(events: list[SignalEvent], total_days: int,
                   windows: tuple[int, ...] = (60, 120)) -> list[dict[str, object]]:
    """事件序列 -> 计分卡行: 每信号档位 × 每窗口一行 (点时, 无前视)."""
    rows: list[dict[str, object]] = []
    for signal, tier in ROW_SPECS:
        for w in windows:
            rows.append(_row(events, signal, tier, w, total_days))
    return rows
