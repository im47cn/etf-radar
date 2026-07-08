"""latest no-regress 护栏纯函数测试。"""
from src.output.no_regress import should_write_latest


def _meta(cn=None, us=None):
    return {'cn_data_date': cn, 'us_data_date': us}


def test_first_time_no_existing_writes():
    ok, reason = should_write_latest(_meta('2026-07-08'), None)
    assert ok is True
    assert reason == 'first'


def test_cn_regress_blocks():
    ok, reason = should_write_latest(
        _meta('2026-07-06', '2026-07-08'), _meta('2026-07-07', '2026-07-08')
    )
    assert ok is False
    assert 'regress' in reason and 'cn' in reason


def test_us_regress_blocks_even_if_cn_equal():
    ok, reason = should_write_latest(
        _meta('2026-07-08', '2026-07-06'), _meta('2026-07-08', '2026-07-07')
    )
    assert ok is False
    assert 'us' in reason


def test_same_day_intraday_allows():
    ok, reason = should_write_latest(
        _meta('2026-07-08', '2026-07-08'), _meta('2026-07-08', '2026-07-08')
    )
    assert ok is True
    assert reason == 'ok'


def test_advance_allows():
    ok, reason = should_write_latest(
        _meta('2026-07-08', '2026-07-08'), _meta('2026-07-07', '2026-07-07')
    )
    assert ok is True
    assert reason == 'ok'


def test_missing_existing_date_passes():
    # 既有 meta 缺 data_date(冷启动/旧 schema)→ 不拦, 保守放行。
    ok, _ = should_write_latest(_meta('2026-07-08', '2026-07-08'), _meta(None, None))
    assert ok is True


def test_missing_new_date_side_ignored():
    # 新 meta 某侧缺失 → 该侧不参与判定, 另一侧回退仍拦。
    ok, reason = should_write_latest(
        _meta(None, '2026-07-06'), _meta('2026-07-08', '2026-07-07')
    )
    assert ok is False and 'us' in reason
