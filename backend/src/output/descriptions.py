"""信号说明文字与动态描述生成 (REQ-013)."""

from typing import Literal

from ..models import SignalType

SIGNAL_NOTES: dict[str, str] = {
    'resonance': '美股主题ETF与A股ETF在多个周期同向走强或走弱, 说明跨市场映射更顺畅, 适合优先观察。',
    'transmission': '美股主题ETF已经先动, A股ETF尚未完全跟上, 适合观察隔夜到A股开盘后的补涨或补跌传导。',
    'divergence': '美股与A股走势不同步, 需二次确认, 警惕假信号。',
}


def signal_description(signal: SignalType | None) -> str:
    """信号类型 → 标准说明文字 (REQ-013)。None 返回空串。"""
    if signal is None:
        return ''
    return SIGNAL_NOTES[signal]


def theme_dynamic_description(
    theme_name: str, signal: SignalType | None, us_strength_mid: int,
    direction: Literal['up', 'down'] | None = None,
) -> str:
    """根据主题名 + 信号 + 中期强度 + 方向生成简短动态描述 (UI 主题行副标题用)。

    direction 仅对 resonance 有统计意义 (5年回测美股动量→次日A股同向≈56%)。
    """
    if signal == 'transmission':
        return '美股领先, A股尚未完全跟随'
    if signal == 'resonance':
        base = (
            f'美股{theme_name}中长期走强'
            if us_strength_mid >= 80
            else f'美股{theme_name}动量观察中'
        )
        if direction == 'up':
            return f'{base}, 共振偏多'
        if direction == 'down':
            return f'{base}, 共振偏空'
        return base
    if signal == 'divergence':
        return '美股A股短期方向不一致'
    return f'美股{theme_name}动量观察中'
