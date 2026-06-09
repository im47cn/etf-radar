"""信号判定 — 单周期判定 + 多周期投票

判定逻辑 (设计文档 §3.5):
- 共振: 双方都强 + 方向一致 + 强度差小
- 传导: 一方明显领先 (强度差大且领先方足够强)
- 背离: 方向相反且双方收益幅度都不可忽略
- 投票: 短/中/长三周期, 同标签 ≥ 2 才生效
"""
from collections import Counter
from collections.abc import Mapping
from typing import Any, Optional, Protocol
from ..models import SignalSubConfig, SignalType


class _StrengthLike(Protocol):
    """duck-typed for objects with short/mid/long int attributes."""
    short: int
    mid: int
    long: int


def _sign(x: float) -> int:
    """返回 -1/0/+1 (避免对 0 误判方向)。"""
    return (x > 0) - (x < 0)


def judge_per_period(
    us_str: int, cn_str: int,
    us_ret: float, cn_ret: float,
    cfg: SignalSubConfig,
) -> Optional[SignalType]:
    """单周期信号判定: 共振 / 传导 / 背离 / 中性 (None)。"""
    res_cfg = cfg.resonance
    trans_cfg = cfg.transmission
    div_cfg = cfg.divergence

    # 共振: 强度差小 + 方向一致非零 + 至少一方达到强势阈值
    if (abs(us_str - cn_str) <= res_cfg['max_strength_diff']
            and _sign(us_ret) == _sign(cn_ret)
            and _sign(us_ret) != 0
            and max(us_str, cn_str) >= res_cfg['min_max_strength']):
        return 'resonance'

    # 传导: 强度差大 + 领先方达到 leader 阈值 (双向均可)
    if us_str - cn_str >= trans_cfg['min_strength_diff'] and us_str >= trans_cfg['min_leader_strength']:
        return 'transmission'
    if cn_str - us_str >= trans_cfg['min_strength_diff'] and cn_str >= trans_cfg['min_leader_strength']:
        return 'transmission'

    # 背离: 方向相反 + 双方幅度都 >= 阈值
    if (_sign(us_ret) != _sign(cn_ret)
            and _sign(us_ret) != 0 and _sign(cn_ret) != 0
            and abs(us_ret) >= div_cfg['min_return_magnitude']
            and abs(cn_ret) >= div_cfg['min_return_magnitude']):
        return 'divergence'

    return None


def signal_for_pair(
    us_strength: _StrengthLike,
    cn_strength: _StrengthLike,
    us_dim_returns: Mapping[str, float | None],
    cn_dim_returns: Mapping[str, float | None],
    cfg: SignalSubConfig,
) -> tuple[Optional[SignalType], dict[str, Optional[SignalType]]]:
    """多周期一致性投票: 三周期中同标签 ≥ 2 才生效。"""
    votes: dict[str, Optional[SignalType]] = {}
    for dim in ['short', 'mid', 'long']:
        votes[dim] = judge_per_period(
            us_str=getattr(us_strength, dim),
            cn_str=getattr(cn_strength, dim),
            us_ret=us_dim_returns.get(dim) or 0.0,
            cn_ret=cn_dim_returns.get(dim) or 0.0,
            cfg=cfg,
        )
    valid = [v for v in votes.values() if v is not None]
    if not valid:
        return None, votes
    counter = Counter(valid)
    top_label, top_count = counter.most_common(1)[0]
    if top_count >= 2:
        return top_label, votes
    return None, votes


def signal_for_theme(
    us_strength: _StrengthLike,
    us_dim_returns: Mapping[str, float | None],
    cn_candidates: list[dict[str, Any]],
    cfg: SignalSubConfig,
) -> tuple[Optional[SignalType], Optional[str], dict[str, Optional[SignalType]]]:
    """主题级信号: 按 (confidence, mapping_score) 降序排候选 ETF, 取首个非中性信号。

    Args:
        cn_candidates: 每项含 keys {cn_strength, cn_dim_returns, confidence, mapping_score, code}

    Returns:
        (signal, trigger_cn_code, votes) — 全 None 表示无信号
    """
    sorted_candidates = sorted(
        cn_candidates,
        key=lambda x: (x['confidence'], x.get('mapping_score') or 0),
        reverse=True,
    )
    for cn in sorted_candidates:
        sig, votes = signal_for_pair(
            us_strength=us_strength,
            cn_strength=cn['cn_strength'],
            us_dim_returns=us_dim_returns,
            cn_dim_returns=cn['cn_dim_returns'],
            cfg=cfg,
        )
        if sig:
            return sig, cn['code'], votes
    return None, None, {}
