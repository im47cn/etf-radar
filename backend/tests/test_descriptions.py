from src.output.descriptions import signal_description, theme_dynamic_description


def test_resonance_text() -> None:
    assert '同向' in signal_description('resonance')


def test_transmission_text() -> None:
    assert '美股' in signal_description('transmission')


def test_divergence_text() -> None:
    assert '不同步' in signal_description('divergence')


def test_none_returns_empty() -> None:
    assert signal_description(None) == ''


def test_dynamic_resonance_strong_mid() -> None:
    txt = theme_dynamic_description(theme_name='存储芯片', signal='resonance', us_strength_mid=99)
    assert '存储芯片' in txt
    assert '走强' in txt


def test_dynamic_transmission_uses_template() -> None:
    txt = theme_dynamic_description(theme_name='网络安全', signal='transmission', us_strength_mid=70)
    assert '领先' in txt or '跟随' in txt


def test_dynamic_divergence() -> None:
    txt = theme_dynamic_description(theme_name='黄金', signal='divergence', us_strength_mid=50)
    assert '不一致' in txt or '不同步' in txt


def test_dynamic_fallback() -> None:
    """无信号 / 共振但 mid < 80 → fallback 模板"""
    txt = theme_dynamic_description(theme_name='半导体', signal=None, us_strength_mid=50)
    assert '半导体' in txt
