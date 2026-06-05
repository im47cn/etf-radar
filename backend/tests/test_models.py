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
