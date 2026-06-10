"""信号说明文字与动态描述生成 (REQ-013)."""
from typing import Optional
from ..models import SignalType

SIGNAL_NOTES: dict[str, str] = {
    'resonance': '美股主题ETF与A股ETF在多个周期同向走强或走弱, 说明跨市场映射更顺畅, 适合优先观察。',
    'transmission': '美股主题ETF已经先动, A股ETF尚未完全跟上, 适合观察隔夜到A股开盘后的补涨或补跌传导。',
    'divergence': '美股与A股走势不同步, 需二次确认, 警惕假信号。',
}


def signal_description(signal: Optional[SignalType]) -> str:
    """信号类型 → 标准说明文字 (REQ-013)。None 返回空串。"""
    if signal is None:
        return ''
    return SIGNAL_NOTES[signal]


def theme_dynamic_description(
    theme_name: str, signal: Optional[SignalType], us_strength_mid: int,
) -> str:
    """根据主题名 + 信号 + 中期强度生成简短动态描述 (UI 主题行副标题用)。"""
    if signal == 'transmission':
        return '美股领先, A股尚未完全跟随'
    if signal == 'resonance' and us_strength_mid >= 80:
        return f'美股{theme_name}中长期走强'
    if signal == 'divergence':
        return '美股A股短期方向不一致'
    return f'美股{theme_name}动量观察中'
