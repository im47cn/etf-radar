"""actions_main 单测 — 编排/降级/幂等/状态文件 (Supabase REST 用桩, 不出网)."""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest

import src.trading.actions_main as am
from src.trading.actions_main import (
    DEFAULT_SETTINGS,
    Holding,
    TradingRest,
    _parse_trades,
    _settings_of,
    derive_positions,
    run,
)

AS_OF = date(2026, 8, 20)  # 周四; 08-23 为周日 (周报)


def trade_row(
    side: str,
    day: str,
    price: float,
    shares: int,
    stop: float | None = None,
    code: str = '600519',
    user: str = 'u1',
    seq: int = 0,
) -> dict[str, Any]:
    """REST 原始行 (numeric 序列化为字符串, PostgREST 默认行为)。"""
    return {
        'id': f'00000000-0000-0000-0000-{seq:012d}',
        'user_id': user,
        'code': code,
        'name': '测试股',
        'side': side,
        'trade_date': day,
        'price': str(price),
        'shares': shares,
        'stop_after': str(stop) if stop is not None else None,
        'reason': None,
        'created_at': f'2026-01-01T00:00:{seq:02d}Z',
    }


class FakeRest:
    """TradingRest 桩: 记录写调用, select 可注入异常。"""

    def __init__(self, trades: list[dict[str, Any]], settings: list[dict[str, Any]]) -> None:
        self.trades, self.settings = trades, settings
        self.inserts: list[tuple[str, list[dict[str, Any]]]] = []
        self.deletes: list[tuple[str, str]] = []
        self.fail = False

    def select(self, table: str, query: str = '') -> list[dict[str, Any]]:
        if self.fail:
            raise RuntimeError('Supabase 不可达')
        return self.trades if table == 'trades' else self.settings

    def insert(self, table: str, rows: list[dict[str, Any]]) -> None:
        self.inserts.append((table, rows))

    def delete(self, table: str, query: str) -> None:
        self.deletes.append((table, query))


def mk_bars(n: int = 60, end: date = AS_OF, start_price: float = 10.0) -> list[dict[str, Any]]:
    closes = [start_price * 1.002**i for i in range(n)]
    return [
        {
            'd': (end - timedelta(days=n - 1 - i)).isoformat(),
            'o': c, 'h': c * 1.001, 'l': c * 0.999, 'c': c, 'v': 1e6, 'amt': 2e8,
        }
        for i, c in enumerate(closes)
    ]


@pytest.fixture()
def data_root(tmp_path: Path) -> Path:
    """最小 data 树: latest/trading.json + stocks/ohlcv/600519.json。"""
    (tmp_path / 'latest').mkdir(parents=True)
    (tmp_path / 'stocks' / 'ohlcv').mkdir(parents=True)
    (tmp_path / 'latest' / 'trading.json').write_text(
        json.dumps(
            {
                'environment': {'regime': 'neutral'},
                'candidates': [
                    {
                        'code': '600519', 'name': '测试股', 'state': 'in_buy_zone',
                        'buy_zone_low': 11.0, 'buy_zone_high': 11.5, 'stop': 10.2,
                    }
                ],
            }
        ),
        encoding='utf-8',
    )
    (tmp_path / 'stocks' / 'ohlcv' / '600519.json').write_text(
        json.dumps({'schema_version': '1.0', 'code': '600519', 'bars': mk_bars()}),
        encoding='utf-8',
    )
    return tmp_path


DEFAULT_TRADES = [
    trade_row('open', (AS_OF - timedelta(days=30)).isoformat(), 10.5, 100, stop=9.8, seq=1),
    trade_row('close', (AS_OF - timedelta(days=10)).isoformat(), 11.2, 100, seq=2),
]


# ---------- 纯函数 ----------

def test_parse_trades_numeric_strings() -> None:
    rows = _parse_trades(DEFAULT_TRADES)
    assert rows[0]['price'] == 10.5 and isinstance(rows[0]['price'], float)
    assert rows[0]['stop_after'] == 9.8
    assert rows[1]['stop_after'] is None
    assert rows[0]['shares'] == 100 and isinstance(rows[0]['shares'], int)


def test_derive_positions_matches_m3_rules() -> None:
    trades = _parse_trades(
        [
            trade_row('open', '2026-08-01', 10.0, 100, stop=9.0, seq=1),
            trade_row('add', '2026-08-02', 12.0, 100, stop=11.0, seq=2),
            trade_row('reduce', '2026-08-03', 11.0, 60, stop=10.5, seq=3),
            trade_row('close', '2026-08-05', 9.0, 140, seq=4),
            trade_row('open', '2026-08-10', 8.0, 50, stop=7.5, seq=5),
        ]
    )
    pos = derive_positions(trades)
    assert pos == [Holding(code='600519', name='测试股', shares=50, avg_cost=8.0, stop_current=7.5)]


def test_derive_positions_reduce_updates_stop_keeps_cost() -> None:
    trades = _parse_trades(
        [
            trade_row('open', '2026-08-01', 10.0, 100, stop=9.0, seq=1),
            trade_row('reduce', '2026-08-02', 11.0, 40, seq=2),
        ]
    )
    pos = derive_positions(trades)
    assert pos[0].shares == 60 and pos[0].avg_cost == 10.0
    assert pos[0].stop_current == 9.0  # reduce 未带新止损 -> 保留


def test_settings_of_defaults_and_parsing() -> None:
    assert _settings_of([], 'u1') == DEFAULT_SETTINGS
    s = _settings_of(
        [{'user_id': 'u1', 'equity_cny': '100000', 'risk_per_trade_pct': '1.0', 'max_position_pct': '30'}],
        'u1',
    )
    assert s == {'equity_cny': 100000.0, 'risk_per_trade_pct': 1.0, 'max_position_pct': 30.0}


def test_trading_rest_from_env_requires(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv('SUPABASE_URL', raising=False)
    monkeypatch.delenv('SUPABASE_SERVICE_ROLE_KEY', raising=False)
    with pytest.raises(RuntimeError, match='SUPABASE'):
        TradingRest.from_env()


# ---------- run(): dry-run ----------

def test_run_dry_run_no_side_effects(data_root: Path, capsys: pytest.CaptureSelector) -> None:
    rest = FakeRest(DEFAULT_TRADES, [])
    code = run(data_root, dry_run=True, as_of=AS_OF, rest=rest)
    out = capsys.readouterr().out
    assert code == 0
    assert '[dry-run] as_of=2026-08-20 degraded=False reviews=1' in out
    assert rest.inserts == [] and rest.deletes == []  # 不写 Supabase
    assert not (data_root / 'latest' / am.STATE_FILENAME).exists()  # 不落状态
    # 日报: prev states 空 -> 无迁移
    assert '日报: 无迁移' in out


def test_run_dry_run_daily_on_transition(data_root: Path, capsys: pytest.CaptureSelector) -> None:
    (data_root / 'latest' / am.STATE_FILENAME).write_text(
        json.dumps({'states': {'600519': 'watch'}, 'regime_history': {}}), encoding='utf-8'
    )
    run(data_root, dry_run=True, as_of=AS_OF, rest=FakeRest([], []))
    out = capsys.readouterr().out
    assert '已进入买区 [11.00 - 11.50]，止损参考 10.20' in out


def test_run_dry_run_sunday_weekly(data_root: Path, capsys: pytest.CaptureSelector) -> None:
    sunday = date(2026, 8, 23)
    run(data_root, dry_run=True, as_of=sunday, rest=FakeRest(DEFAULT_TRADES, []))
    out = capsys.readouterr().out
    assert '交易周报' in out and '本周复盘' in out


# ---------- run(): 正常写路径 ----------

def test_run_writes_reviews_idempotently_and_state(data_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pushed: list[tuple[str, str]] = []
    monkeypatch.setattr(am, 'send_alert', lambda t, d: pushed.append((t, d)) or True)
    rest = FakeRest(DEFAULT_TRADES, [])
    code = run(data_root, dry_run=False, as_of=AS_OF, rest=rest)
    assert code == 0
    # 幂等: 先删当日旧行再插
    assert rest.deletes == [('trade_reviews', 'user_id=eq.u1&review_date=eq.2026-08-20')]
    assert len(rest.inserts) == 1
    table, rows = rest.inserts[0]
    assert table == 'trade_reviews' and len(rows) == 1
    row = rows[0]
    assert row['user_id'] == 'u1' and row['review_date'] == '2026-08-20'
    assert row['trade_id'] == DEFAULT_TRADES[0]['id']
    # 夹具为缓涨序列, 入场日无 VCP 结构 -> entry_in_buy_zone=False (口径: 无结构=不在买区);
    # 其余三维合规 (有止损未触发/无信号事件/equity 未配) -> 75
    assert row['discipline_score'] == 75
    assert row['events']['dimensions']['entry_in_buy_zone'] is False
    assert row['result_r'] == round(70.0 / 70.0, 3)  # pnl (11.2-10.5)*100 / (10.5-9.8)*100
    # 无迁移 -> 无日报推送; 状态文件落盘
    assert pushed == []
    state = json.loads((data_root / 'latest' / am.STATE_FILENAME).read_text(encoding='utf-8'))
    assert state['states'] == {'600519': 'in_buy_zone'}
    assert state['regime_history'] == {'2026-08-20': 'neutral'}


def test_run_regime_history_accumulates(data_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(am, 'send_alert', lambda t, d: True)
    (data_root / 'latest' / am.STATE_FILENAME).write_text(
        json.dumps({'states': {}, 'regime_history': {'2026-08-19': 'offense'}}), encoding='utf-8'
    )
    run(data_root, dry_run=False, as_of=AS_OF, rest=FakeRest([], []))
    state = json.loads((data_root / 'latest' / am.STATE_FILENAME).read_text(encoding='utf-8'))
    assert state['regime_history'] == {'2026-08-19': 'offense', '2026-08-20': 'neutral'}


def test_run_holding_signals_for_open_position(data_root: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureSelector) -> None:
    monkeypatch.setattr(am, 'send_alert', lambda t, d: True)
    trades = [trade_row('open', (AS_OF - timedelta(days=5)).isoformat(), '10.0', 100, stop=9.0, seq=1)]
    trades[0]['price'] = '10.0'
    run(data_root, dry_run=True, as_of=AS_OF, rest=FakeRest(trades, []))
    out = capsys.readouterr().out
    assert 'reviews=0' in out  # 进行中持仓无复盘行


# ---------- run(): 降级 ----------

def test_run_degrades_when_supabase_down(data_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pushed: list[tuple[str, str]] = []
    monkeypatch.setattr(am, 'send_alert', lambda t, d: pushed.append((t, d)) or True)
    rest = FakeRest(DEFAULT_TRADES, [])
    rest.fail = True
    code = run(data_root, dry_run=False, as_of=AS_OF, rest=rest)
    assert code == 0  # 降级不算失败
    assert rest.inserts == []
    assert any('交易复盘降级' in t for t, _ in pushed)
    # 降级只影响复盘; 迁移通知只依赖 trading.json -> 状态照常前进 (否则重复推送)
    state = json.loads((data_root / 'latest' / am.STATE_FILENAME).read_text(encoding='utf-8'))
    assert state['states'] == {'600519': 'in_buy_zone'}


def test_run_env_missing_degrades(data_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pushed: list[tuple[str, str]] = []
    monkeypatch.setattr(am, 'send_alert', lambda t, d: pushed.append((t, d)) or True)
    monkeypatch.delenv('SUPABASE_URL', raising=False)
    monkeypatch.delenv('SUPABASE_SERVICE_ROLE_KEY', raising=False)
    code = run(data_root, dry_run=False, as_of=AS_OF, rest=None)
    assert code == 0
    assert any('交易复盘降级' in t for t, _ in pushed)


def test_run_missing_trading_json_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        run(tmp_path, dry_run=True, as_of=AS_OF, rest=FakeRest([], []))


# ---------- TradingRest HTTP 层 (mock urlopen, 验证请求形状) ----------

def test_trading_rest_request_shapes(monkeypatch: pytest.MonkeyPatch) -> None:
    import io
    import urllib.request

    calls: list[tuple[str, str, dict[str, str] | None, Any]] = []

    def fake_urlopen(req: Any, timeout: int = 0) -> io.BytesIO:
        calls.append((req.method, req.full_url, dict(req.headers), req.data))
        return io.BytesIO(b'[]')

    monkeypatch.setattr(urllib.request, 'urlopen', fake_urlopen)
    rest = TradingRest('https://x.supabase.co/', 'key-1')
    assert rest.select('trades', 'select=*&order=trade_date.asc') == []
    method, url, headers, _ = calls[-1]
    assert method == 'GET' and url == 'https://x.supabase.co/rest/v1/trades?select=*&order=trade_date.asc'
    assert headers['Apikey'] == 'key-1' and headers['Authorization'] == 'Bearer key-1'
    rest.insert('trade_reviews', [{'a': 1}])
    assert calls[-1][0] == 'POST' and b'{"a": 1}' in calls[-1][3]
    rest.delete('trade_reviews', 'user_id=eq.u1')
    assert calls[-1][0] == 'DELETE' and 'user_id=eq.u1' in calls[-1][1]


def test_trading_rest_http_error_wrapped(monkeypatch: pytest.MonkeyPatch) -> None:
    import io
    import urllib.error
    import urllib.request

    def fake_urlopen(req: Any, timeout: int = 0) -> io.BytesIO:
        raise urllib.error.HTTPError('u', 500, 'boom', None, io.BytesIO(b'detail'))  # type: ignore[arg-type]

    monkeypatch.setattr(urllib.request, 'urlopen', fake_urlopen)
    rest = TradingRest('https://x.supabase.co/', 'key-1')
    with pytest.raises(RuntimeError, match='500'):
        rest.select('trades')


def test_trading_rest_from_env_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('SUPABASE_URL', 'https://x.supabase.co')
    monkeypatch.setenv('SUPABASE_SERVICE_ROLE_KEY', 'k')
    rest = TradingRest.from_env()
    assert rest._base == 'https://x.supabase.co' and rest._key == 'k'


# ---------- 边界与降级补充 ----------

def test_derive_positions_orphan_reduce_and_reduce_to_zero() -> None:
    trades = _parse_trades(
        [
            trade_row('reduce', '2026-08-01', 10.0, 50, seq=1),  # 无持仓: 忽略
            trade_row('open', '2026-08-02', 10.0, 100, stop=9.0, seq=2),
            trade_row('reduce', '2026-08-03', 10.5, 100, seq=3),  # 扣到 0: 清仓
        ]
    )
    assert derive_positions(trades) == []


def test_load_bars_corrupt_file(tmp_path: Path) -> None:
    (tmp_path / '600519.json').write_text('{bad json', encoding='utf-8')
    from src.trading.actions_main import _load_bars

    assert _load_bars(tmp_path, '600519') == []
    assert _load_bars(tmp_path, 'notexist') == []


def test_read_state_corrupt(tmp_path: Path) -> None:
    f = tmp_path / 'trading_notify_state.json'
    f.write_text('not-json{', encoding='utf-8')
    import src.trading.actions_main as m

    assert m._read_state(tmp_path) == {}


def test_run_review_skipped_when_open_date_not_in_bars(
    data_root: Path, capsys: pytest.CaptureSelector
) -> None:
    # open 日期早于 ohlcv 窗口 -> ctx None -> 跳过该笔 (warning), 不写 reviews
    trades = [
        trade_row('open', '2026-01-05', 10.0, 100, stop=9.0, seq=1),
        trade_row('close', '2026-01-10', 11.0, 100, seq=2),
    ]
    run(data_root, dry_run=True, as_of=AS_OF, rest=FakeRest(trades, []))
    assert 'reviews=0' in capsys.readouterr().out


def test_run_buy_zone_from_vcp_structure(data_root: Path) -> None:
    # VCP 形态入场: 买区可识别 -> entry_in_buy_zone 达成
    from tests.test_trading_fixtures import as_bars, legs_series, volumes

    closes = legs_series([(12.0, 11.2), (11.9, 11.4), (11.85, 11.5)], tail_to=12.1)  # 尾部爬回买区
    vols = volumes(len(closes))
    arr = as_bars(closes, vols)
    n = len(closes)
    bars = [
        {
            'd': (AS_OF - timedelta(days=n - 1 - i)).isoformat(),
            'o': float(arr['open'][i]), 'h': float(arr['high'][i]), 'l': float(arr['low'][i]),
            'c': float(arr['close'][i]), 'v': float(arr['volume'][i]), 'amt': 2e8,
        }
        for i in range(n)
    ]
    (data_root / 'stocks' / 'ohlcv' / '600519.json').write_text(
        json.dumps({'schema_version': '1.0', 'code': '600519', 'bars': bars}), encoding='utf-8'
    )
    last = closes[-1]
    trades = [
        # 入场日取 bars[-2]: VCP 结构在该截断面已成型 (bars[-3] 截断时第二段收缩未确认)
        trade_row('open', bars[-2]['d'], round(last, 2), 100, stop=round(last * 0.92, 2), seq=1),
        trade_row('close', bars[-1]['d'], round(last, 2), 100, seq=2),
    ]
    rest = FakeRest(trades, [])
    run(data_root, dry_run=True, as_of=AS_OF, rest=rest)
    # 从 FakeRest 捕获不到 dry-run 行; 直接复算断言维度
    parsed = _parse_trades(trades)
    from src.trading.review import review_round_trip, split_round_trips

    rt = split_round_trips(parsed)[0]
    ctx = am._build_review_context(rt.events, rt.open_date, rt.close_date, bars, DEFAULT_SETTINGS)
    assert ctx is not None and ctx.buy_zone is not None
    res = review_round_trip(rt, ctx)
    assert res.dimensions['entry_in_buy_zone'] is True


def test_run_signal_events_replayed(data_root: Path) -> None:
    # 持仓窗内跌破 50MA 穿越被回放为信号事件日 (缓涨末段大跌)
    # 涨段须 >=60 根: sma(close,50) 从 idx49 起才有效, 持仓窗 (idx60+) 内才可判穿越
    closes = [10.0 * 1.005**i for i in range(60)]
    peak = closes[-1]
    closes += [peak * 0.75] * 5 + [peak * 0.74] * 5  # 跌穿 50MA 后低位横盘
    bars = [
        {
            'd': (AS_OF - timedelta(days=len(closes) - 1 - i)).isoformat(),
            'o': c, 'h': c * 1.001, 'l': c * 0.999, 'c': c, 'v': 1e6, 'amt': 2e8,
        }
        for i, c in enumerate(closes)
    ]
    (data_root / 'stocks' / 'ohlcv' / '600519.json').write_text(
        json.dumps({'schema_version': '1.0', 'code': '600519', 'bars': bars}), encoding='utf-8'
    )
    trades = [
        trade_row('open', bars[60]['d'], round(closes[60], 2), 100, stop=9.0, seq=1),
        trade_row('close', bars[-1]['d'], round(closes[-1], 2), 100, seq=2),
    ]
    parsed = _parse_trades(trades)
    from src.trading.review import split_round_trips

    rt = split_round_trips(parsed)[0]
    ctx = am._build_review_context(rt.events, rt.open_date, rt.close_date, bars, DEFAULT_SETTINGS)
    assert ctx is not None
    assert ctx.signal_event_dates, '持仓窗内应回放出跌破 50MA 事件日'


def test_replay_stage_change_event() -> None:
    # 两根连续大跌分离两类事件日: 倒数第2根破50MA (穿越日), 末根 52周高条件挂 -> 转 Stage 3 (非穿越日)
    import numpy as np

    closes = [10.0 * 1.004**i for i in range(260)]
    closes[-2] = closes[-3] * 0.85  # -15%: 跌破 50MA -> break_ma50 事件
    closes[-1] = closes[-2] * 0.826  # -17%: 现价 < 52周高x0.75 -> 模板掉到 5/8 -> Stage 3
    n = len(closes)
    dates = [(AS_OF - timedelta(days=n - 1 - i)).isoformat() for i in range(n)]
    arr = np.array(closes, dtype=np.float64)
    events = am._replay_signal_event_dates(dates, arr * 1.001, arr * 0.999, arr, n - 3, n - 1)
    assert dates[-2] in events and dates[-1] in events  # 两个不同来源的事件日都被回放


def test_run_bars_cache_reused_for_position_and_trip(data_root: Path) -> None:
    # 同股既有进行中持仓又有已完成一笔 -> bars_of 缓存命中
    trades = [
        trade_row('open', (AS_OF - timedelta(days=30)).isoformat(), 10.5, 100, stop=9.8, seq=1),
        trade_row('close', (AS_OF - timedelta(days=10)).isoformat(), 11.2, 100, seq=2),
        trade_row('open', (AS_OF - timedelta(days=3)).isoformat(), 11.0, 100, stop=10.2, seq=3),
    ]
    run(data_root, dry_run=True, as_of=AS_OF, rest=FakeRest(trades, []))


def test_run_dry_run_degraded_no_alert(data_root: Path, capsys: pytest.CaptureSelector) -> None:
    # dry-run + Supabase 挂: 不发降级告警 (dry-run 无副作用), 打印 degraded=True
    rest = FakeRest(DEFAULT_TRADES, [])
    rest.fail = True
    run(data_root, dry_run=True, as_of=AS_OF, rest=rest)
    assert 'degraded=True' in capsys.readouterr().out


def test_run_non_dry_sends_daily_and_weekly(data_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # 周日 + 昨日 watch 迁移 -> 日报与周报都发
    pushed: list[tuple[str, str]] = []
    monkeypatch.setattr(am, 'send_alert', lambda t, d: pushed.append((t, d)) or True)
    (data_root / 'latest' / am.STATE_FILENAME).write_text(
        json.dumps({'states': {'600519': 'watch'}, 'regime_history': {}}), encoding='utf-8'
    )
    sunday = date(2026, 8, 23)
    run(data_root, dry_run=False, as_of=sunday, rest=FakeRest(DEFAULT_TRADES, []))
    titles = [t for t, _ in pushed]
    assert any('进入买区' in t for t in titles)
    assert any('交易周报' in t for t in titles)


def test_main_cli(monkeypatch: pytest.MonkeyPatch, data_root: Path, capsys: pytest.CaptureSelector) -> None:
    monkeypatch.setattr('sys.argv', ['actions_main', '--data-root', str(data_root), '--dry-run', '--as-of', '2026-08-20'])
    monkeypatch.delenv('SUPABASE_URL', raising=False)
    monkeypatch.delenv('SUPABASE_SERVICE_ROLE_KEY', raising=False)
    with pytest.raises(SystemExit) as exc:
        am.main()
    assert exc.value.code == 0
    assert '[dry-run]' in capsys.readouterr().out
