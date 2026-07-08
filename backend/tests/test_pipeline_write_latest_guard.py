"""pipeline._write_latest_guarded 集成测试: 回退跳过 / 更新写入。"""
import json

from src.pipeline import _write_latest_guarded


def _bootstrap(latest, cn, us):
    latest.mkdir(parents=True, exist_ok=True)
    (latest / 'themes.json').write_text('{"marker": "old"}', encoding='utf-8')
    (latest / 'etfs.json').write_text('{"marker": "old"}', encoding='utf-8')
    (latest / 'signals.json').write_text('{"marker": "old"}', encoding='utf-8')
    (latest / 'meta.json').write_text(
        json.dumps({'cn_data_date': cn, 'us_data_date': us}), encoding='utf-8'
    )


def _new(cn, us):
    m = {'marker': 'new'}
    meta = {'marker': 'new', 'cn_data_date': cn, 'us_data_date': us}
    return m, m, m, meta


def test_regress_skips_all_files(tmp_path):
    latest = tmp_path / 'latest'
    _bootstrap(latest, '2026-07-08', '2026-07-08')
    themes, etfs, signals, meta = _new('2026-07-06', '2026-07-08')  # cn 回退

    written = _write_latest_guarded(tmp_path, themes, etfs, signals, meta)

    assert written is False
    # 四文件保持旧值, 未被覆盖
    for name in ('themes.json', 'etfs.json', 'signals.json'):
        assert json.loads((latest / name).read_text())['marker'] == 'old'
    assert json.loads((latest / 'meta.json').read_text())['cn_data_date'] == '2026-07-08'


def test_advance_writes_all_files(tmp_path):
    latest = tmp_path / 'latest'
    _bootstrap(latest, '2026-07-07', '2026-07-07')
    themes, etfs, signals, meta = _new('2026-07-08', '2026-07-08')

    written = _write_latest_guarded(tmp_path, themes, etfs, signals, meta)

    assert written is True
    for name in ('themes.json', 'etfs.json', 'signals.json'):
        assert json.loads((latest / name).read_text())['marker'] == 'new'
    assert json.loads((latest / 'meta.json').read_text())['cn_data_date'] == '2026-07-08'


def test_first_write_no_existing(tmp_path):
    themes, etfs, signals, meta = _new('2026-07-08', '2026-07-08')

    written = _write_latest_guarded(tmp_path, themes, etfs, signals, meta)

    assert written is True
    assert (tmp_path / 'latest' / 'meta.json').exists()
