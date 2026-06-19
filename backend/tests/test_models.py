import pytest
from pydantic import ValidationError
from src.models import (
    ThemeConfig, CnEtfConfig, Returns, Strength, PairSignal,
)


def test_theme_config_loads_minimal() -> None:
    cn = CnEtfConfig(code='512480', name='半导体ETF', tracking='中证全指半导体', match_type='exact')
    t = ThemeConfig(
        id='storage_dram', name='存储芯片',
        us_etfs=['DRAM', 'SOXX'], primary_us='DRAM',
        tags=['DRAM'], note='',
        cn_etfs=[cn],
    )
    assert t.primary_us == 'DRAM'
    assert t.cn_etfs[0].match_type == 'exact'


def test_match_type_rejects_invalid() -> None:
    import pytest
    with pytest.raises(ValueError):
        CnEtfConfig(code='000', name='x', tracking='y', match_type='loose')  # type: ignore[arg-type]


def test_returns_all_optional() -> None:
    r = Returns(r_1d=0.01, r_5d=0.05)
    assert r.r_20d is None


def test_strength_rejects_out_of_range() -> None:
    import pytest
    with pytest.raises(ValueError):
        Strength(short=101, mid=60, long=70, composite=60)
    with pytest.raises(ValueError):
        Strength(short=50, mid=-1, long=70, composite=60)


def test_pair_signal_minimal() -> None:
    p = PairSignal(
        theme_id='x', cn_code='000001', mapping_score=88, confidence=90,
        signal='resonance', votes={'short': 'resonance', 'mid': 'resonance', 'long': None},
    )
    assert p.signal == 'resonance'


# ── Task 1: ThemeConfig 扩展 —— cn_only 主题支持 ──────────────────────────
def _cn(code='000001'):
    return CnEtfConfig(code=code, name='测试ETF', tracking='测试指数', match_type='exact')


def test_theme_config_cn_only_minimal():
    """纯 A 股主题：无 us_etfs/primary_us，只需 primary_cn。"""
    t = ThemeConfig(id='cn_x', name='测试', tags=[], primary_cn='000001', cn_etfs=[_cn()])
    assert t.primary_us is None
    assert t.us_etfs == []
    assert t.primary_cn == '000001'


def test_theme_config_requires_at_least_one_primary():
    with pytest.raises(ValidationError, match='primary_us or primary_cn required'):
        ThemeConfig(id='cn_x', name='测试', tags=[], cn_etfs=[_cn()])


def test_theme_config_primary_us_must_be_in_us_etfs():
    with pytest.raises(ValidationError, match='primary_us must be in us_etfs'):
        ThemeConfig(id='m', name='M', us_etfs=['A'], primary_us='B', tags=[], cn_etfs=[_cn()])


def test_theme_config_mapped_backward_compat():
    """现有映射主题加载仍正常。"""
    t = ThemeConfig(id='m', name='M', us_etfs=['SOXX'], primary_us='SOXX',
                    tags=['半导体'], cn_etfs=[_cn()])
    assert t.primary_us == 'SOXX'
    assert t.primary_cn is None
