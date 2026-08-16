from src.models import Strength
from src.output.descriptions import signal_description, theme_dynamic_description


def _str(n: int) -> Strength:
    """测试用: 四维同值 Strength。"""
    return Strength(short=n, mid=n, long=n, composite=n)


def test_resonance_text() -> None:
    assert '同向' in signal_description('resonance')


def test_transmission_text() -> None:
    assert '美股' in signal_description('transmission')


def test_divergence_text() -> None:
    assert '不同步' in signal_description('divergence')


def test_none_returns_empty() -> None:
    assert signal_description(None) == ''


def test_dynamic_resonance_strong_mid() -> None:
    txt = theme_dynamic_description(theme_name='存储芯片', signal='resonance', us_strength=_str(99))
    assert '存储芯片' in txt
    assert '走强' in txt


def test_dynamic_transmission_uses_template() -> None:
    txt = theme_dynamic_description(theme_name='网络安全', signal='transmission', us_strength=_str(70))
    assert '领先' in txt
    assert '同步' in txt  # P1: 去"跟随"方向暗示, 改"尚未同步"


def test_dynamic_divergence() -> None:
    txt = theme_dynamic_description(theme_name='黄金', signal='divergence', us_strength=_str(50))
    assert '不一致' in txt or '不同步' in txt


def test_dynamic_fallback() -> None:
    """无信号 / 共振但 mid < 80 → fallback 模板"""
    txt = theme_dynamic_description(theme_name='半导体', signal=None, us_strength=_str(50))
    assert '半导体' in txt


def test_dynamic_resonance_direction_up() -> None:
    txt = theme_dynamic_description(
        theme_name='半导体', signal='resonance', us_strength=_str(99), direction='up',
    )
    assert '走强' in txt
    assert '偏多' in txt


def test_dynamic_resonance_direction_down() -> None:
    txt = theme_dynamic_description(
        theme_name='半导体', signal='resonance', us_strength=_str(70), direction='down',
    )
    assert '偏空' in txt


def test_dynamic_resonance_no_direction() -> None:
    """direction=None 时不应出现方向词"""
    txt = theme_dynamic_description(
        theme_name='半导体', signal='resonance', us_strength=_str(70),
    )
    assert '偏多' not in txt
    assert '偏空' not in txt


def test_dynamic_description_includes_composite_value() -> None:
    """P2: description 带 composite 强度具体值 (量化, 替代空泛'动量观察中')"""
    txt = theme_dynamic_description(theme_name='半导体', signal=None, us_strength=_str(42))
    assert 'composite' in txt
    assert '42' in txt


def test_theme_description_direction_tier_markers() -> None:
    """共振方向 + 幅度置信档: high/low 加标注, 中间档不加 (主列表一眼可辨)."""
    up = theme_dynamic_description(theme_name='半导体', signal='resonance',
                                   us_strength=_str(85), direction='up')
    assert up.endswith('共振偏多') and '高置信' not in up and '弱信号' not in up
    hi = theme_dynamic_description(theme_name='半导体', signal='resonance',
                                   us_strength=_str(85), direction='up',
                                   direction_tier='high')
    assert hi.endswith('共振偏多（高置信）')
    lo = theme_dynamic_description(theme_name='半导体', signal='resonance',
                                   us_strength=_str(85), direction='down',
                                   direction_tier='low')
    assert lo.endswith('共振偏空（弱信号）')
