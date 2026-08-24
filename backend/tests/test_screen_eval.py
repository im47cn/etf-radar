"""screen_eval 纯计算层: 固定输入 → 固定事件数/固定 R 值/固定分档命中率 (值全部手算硬编码)."""
from __future__ import annotations

from datetime import datetime, timedelta

from src.evidence.screen_eval import (
    MAX_WAIT_DAYS,
    Candidate,
    Outcome,
    bucket_rows,
    evaluate_candidate,
    hit_ci,
)


def _dates(start: str, n: int) -> list[str]:
    """从 start 起 n 个工作日日期串 (与真实交易日历无关, 只需互异且升序)."""
    d = datetime.strptime(start, '%Y-%m-%d').date()  # noqa: DTZ007  仅产日期串, 无时区语义
    out: list[str] = []
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def _bars(dates: list[str], closes: list[float]) -> list[dict[str, float | str | int]]:
    """合成 ohlcv bars: o=h=l=c=close, v/amt=1. 一字涨停由相邻 close 涨幅>=9.5% 天然构造."""
    return [{'d': d, 'o': c, 'h': c, 'l': c, 'c': c, 'v': 1, 'amt': 1}
            for d, c in zip(dates, closes)]


def _cand(pool_date: str, pivot: float = 10.0, stop: float = 9.0, state: str = 'watch',
          composite_score: float = 5.5, rs_pct: float = 79.6,
          vcp_quality: float = 0.7) -> Candidate:
    return Candidate(code='601001', pool_date=pool_date, pivot=pivot, stop=stop,
                     composite_score=composite_score, rs_pct=rs_pct,
                     vcp_quality=vcp_quality, state=state)


# --- case A: 常规突破 (入池日后第 5 根突破, T+20 exit) ---

def test_case_a_regular_breakout() -> None:
    dates = _dates('2026-01-05', 26)
    closes = [9.8, 9.7, 9.75, 9.8, 9.85, 10.6] + [round(10.6 + 0.12 * (k - 5), 2) for k in range(6, 26)]
    assert closes[10] == 11.2 and closes[25] == 13.0  # fixture 自检: ret_5d/exit 来源

    o = evaluate_candidate(_cand(dates[0]), _bars(dates, closes))

    assert o.status == 'broke_out'
    assert o.event_date == dates[5]
    assert o.entry == 10.6
    assert o.r_multiple == 1.5          # (13.0-10.6)/(10.6-9.0)
    assert o.ret_5d == 0.0566           # 11.2/10.6-1
    assert o.ret_20d == 0.2264          # 13.0/10.6-1


# --- case B: 窗口走满无突破 → never_broke_out ---

def test_case_b_never_broke_out() -> None:
    dates = _dates('2026-01-05', 21)  # 入池 + 20 根窗口
    closes = [9.8] + [9.7] * 20

    o = evaluate_candidate(_cand(dates[0]), _bars(dates, closes))

    assert o.status == 'never_broke_out'
    assert o.event_date is None and o.entry is None
    assert o.r_multiple is None and o.ret_5d is None and o.ret_20d is None


# --- case C: 一字涨停日消耗窗口但不记事件, 次日正常突破 ---

def test_case_c_limit_up_day_skipped() -> None:
    dates = _dates('2026-01-05', 25)
    # 第 3 根 (idx 3): o=h=l=c=10.5, prev=9.5 → 10.5 >= 9.5*1.095=10.4025 → 一字板, 跳过
    closes = [9.8, 9.6, 9.5, 10.5, 10.4] + [round(10.4 + 0.08 * (k - 4), 2) for k in range(5, 25)]
    assert closes[24] == 12.0

    o = evaluate_candidate(_cand(dates[0]), _bars(dates, closes))

    assert o.status == 'broke_out'
    assert o.event_date == dates[4]    # 涨停日 (dates[3]) 不记事件
    assert o.entry == 10.4
    assert o.r_multiple == 1.1429      # (12.0-10.4)/(10.4-9.0)


# --- case D: 入池即 in_buy_zone → 入池日即事件日 (豁免涨停复检) ---

def test_case_d_in_buy_zone_on_pool_day() -> None:
    dates = _dates('2026-01-05', 21)
    closes = [round(10.2 + 0.1 * k, 2) for k in range(21)]  # closes[0]=10.2 >= pivot=10.0
    assert closes[20] == 12.2

    o = evaluate_candidate(_cand(dates[0], state='in_buy_zone'), _bars(dates, closes))

    assert o.status == 'broke_out'
    assert o.event_date == dates[0]
    assert o.entry == 10.2
    assert o.r_multiple == 1.6667      # (12.2-10.2)/(10.2-9.0)

# --- case D2: 突破后不足 EXIT_HORIZON 根 → r=None (前瞻未到期), ret_5d 有值仍输出 ---

def test_breakout_exit_not_matured_r_none() -> None:
    dates = _dates('2026-01-05', 12)  # 入池 + 次根突破 + 后续仅 10 根
    closes = [9.8, 10.6, 10.7, 10.8, 10.9, 11.0, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7]

    o = evaluate_candidate(_cand(dates[0]), _bars(dates, closes))

    assert o.status == 'broke_out'
    assert o.event_date == dates[1] and o.entry == 10.6
    assert o.r_multiple is None   # 突破日后不足 20 根 → 前瞻未到期
    assert o.ret_5d == 0.0566     # 11.2/10.6-1
    assert o.ret_20d is None


# --- case D3: entry-stop <= 0 (风险定义失效) → r=None, 收益口径不受影响 ---

def test_r_none_when_stop_not_below_entry() -> None:
    dates = _dates('2026-01-05', 26)
    closes = [9.8, 9.7, 9.75, 9.8, 9.85, 10.6] + [round(10.6 + 0.12 * (k - 5), 2) for k in range(6, 26)]

    o = evaluate_candidate(_cand(dates[0], stop=10.6), _bars(dates, closes))

    assert o.status == 'broke_out'
    assert o.entry == 10.6
    assert o.r_multiple is None   # entry-stop == 0 → 分母 <=0
    assert o.ret_5d == 0.0566 and o.ret_20d == 0.2264


# --- case E: 窗口未走满 (可用 bar 不足) → pending ---

def test_case_e_pending_window_incomplete() -> None:
    dates = _dates('2026-01-05', 11)  # 入池 + 仅 10 根
    closes = [9.8] + [9.7] * 10

    o = evaluate_candidate(_cand(dates[0]), _bars(dates, closes))

    assert o.status == 'pending'
    assert o.event_date is None and o.r_multiple is None


# --- case F: 入池日无 bar → missing_quotes ---

def test_case_f_missing_quotes() -> None:
    dates = _dates('2026-02-02', 30)  # 序列不含入池日 2026-01-05
    closes = [10.5] * 30

    o = evaluate_candidate(_cand('2026-01-05'), _bars(dates, closes))

    assert o.status == 'missing_quotes'
    assert o.event_date is None


# --- case G: hit_ci 命中率/CI/中位 R ---

def test_case_g_hit_ci_insufficient_small_n() -> None:
    row = hit_ci([1.5, 0.5, -0.5])

    assert row['n'] == 3
    assert row['hit_rate'] == 0.6667
    # p=2/3, half=1.96*sqrt(p(1-p)/3)=0.53344 → ci_low=0.1332, ci_high 截断 1.0
    assert row['ci_low'] == 0.1332
    assert row['ci_high'] == 1.0
    assert row['median_r'] == 0.5
    assert row['status'] == 'insufficient'


def test_hit_ci_ok_at_min_n() -> None:
    rs = [1.0] * 30 + [-1.0] * 20  # p=0.6, n=50 → ok
    row = hit_ci(rs)

    assert row['status'] == 'ok'
    assert row['hit_rate'] == 0.6
    assert row['ci_low'] == 0.4642
    assert row['ci_high'] == 0.7358
    assert row['median_r'] == 1.0


def test_hit_ci_empty() -> None:
    row = hit_ci([])

    assert row == {'n': 0, 'hit_rate': 0.0, 'ci_low': 0.0, 'ci_high': 0.0,
                   'median_r': 0.0, 'status': 'insufficient'}


# --- bucket_rows: 三维度分档, 仅有效突破事件入档 ---

def _pair(code: str, score: float, rs_pct: float, quality: float, r: float
          ) -> tuple[Candidate, Outcome]:
    c = Candidate(code=code, pool_date='2026-01-05', pivot=10.0, stop=9.0,
                  composite_score=score, rs_pct=rs_pct, vcp_quality=quality, state='watch')
    return c, Outcome(status='broke_out', event_date='2026-01-06', entry=10.5,
                      r_multiple=r, ret_5d=0.01, ret_20d=0.02)


def _valid_pairs() -> list[tuple[Candidate, Outcome]]:
    # 四分位边 np.percentile([1,2,3,4],[25,50,75]) = [1.75, 2.5, 3.25] → q1..q4 各 1 事件
    return [
        _pair('c1', 1.0, 50.0, 0.3, -0.5),
        _pair('c2', 2.0, 70.0, 0.8, 1.0),
        _pair('c3', 3.0, 90.0, 0.3, 0.5),
        _pair('c4', 4.0, 70.0, 0.8, -1.0),
    ]


def test_bucket_rows_structure_and_counts() -> None:
    rows = bucket_rows(_valid_pairs())

    assert len(rows) == 9  # composite_score 4 档 + rs_pct 3 档 + vcp_quality 2 档
    keys = {'dimension', 'bucket', 'n', 'hit_rate', 'ci_low', 'ci_high', 'median_r', 'status'}
    assert all(keys <= set(r) for r in rows)
    assert [(r['dimension'], r['bucket']) for r in rows] == [
        ('composite_score', 'q1'), ('composite_score', 'q2'),
        ('composite_score', 'q3'), ('composite_score', 'q4'),
        ('rs_pct', 'low'), ('rs_pct', 'mid'), ('rs_pct', 'high'),
        ('vcp_quality', 'low'), ('vcp_quality', 'high'),
    ]
    by = {(r['dimension'], r['bucket']): r for r in rows}
    # rs_pct: low={c1} hit 0/1; mid={c2,c4} hit 1/2; high={c3} hit 1/1
    assert by[('rs_pct', 'low')]['n'] == 1 and by[('rs_pct', 'low')]['hit_rate'] == 0.0
    assert by[('rs_pct', 'mid')]['n'] == 2 and by[('rs_pct', 'mid')]['hit_rate'] == 0.5
    assert by[('rs_pct', 'high')]['n'] == 1 and by[('rs_pct', 'high')]['hit_rate'] == 1.0
    # vcp_quality: low={c1,c3} hit 1/2; high={c2,c4} hit 1/2
    assert by[('vcp_quality', 'low')]['n'] == 2 and by[('vcp_quality', 'low')]['hit_rate'] == 0.5
    assert by[('vcp_quality', 'high')]['n'] == 2
    # composite_score 四分位各 1
    for q in ('q1', 'q2', 'q3', 'q4'):
        assert by[('composite_score', q)]['n'] == 1


def test_bucket_rows_excludes_invalid_events() -> None:
    """never_broke_out / r_multiple=None (前瞻未到期) 不入任何分档."""
    c_never = Candidate(code='c5', pool_date='2026-01-05', pivot=10.0, stop=9.0,
                        composite_score=5.0, rs_pct=95.0, vcp_quality=0.9, state='watch')
    c_unmatured = Candidate(code='c6', pool_date='2026-01-05', pivot=10.0, stop=9.0,
                            composite_score=6.0, rs_pct=96.0, vcp_quality=0.95, state='watch')
    pairs = _valid_pairs() + [
        (c_never, Outcome(status='never_broke_out')),
        (c_unmatured, Outcome(status='broke_out', event_date='2026-01-06',
                              entry=10.5, r_multiple=None)),
    ]

    rows = bucket_rows(pairs)

    by = {(r['dimension'], r['bucket']): r for r in rows}
    assert by[('rs_pct', 'high')]['n'] == 1  # c5(rs 95)/c6(96) 未计入
    assert by[('composite_score', 'q4')]['n'] == 1


def test_bucket_rows_empty_events() -> None:
    rows = bucket_rows([])

    assert len(rows) == 9
    assert all(r['n'] == 0 and r['status'] == 'insufficient' for r in rows)


def test_constants() -> None:
    assert MAX_WAIT_DAYS == 20
