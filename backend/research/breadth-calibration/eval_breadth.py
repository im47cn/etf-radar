"""全市场温度阈值校准：MA20/60/120 站上率分布评估。

复用本地缓存 closes_full.json.gz（全量 5526 只 × ~1000 交易日前复权收盘）；
缓存缺失时才单线程重抓（mac arm64 必须 max_workers=1，否则 PyMiniRacer V8 崩溃，~24min）。
用法：cd backend && uv run python research/breadth-calibration/eval_breadth.py
"""
import gzip
import json
import time
import math
import statistics as st
from collections import defaultdict, Counter
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[1]
sys.path.insert(0, str(BACKEND))

CLOSES = HERE / 'closes_full.json.gz'   # 22M 原始缓存（gitignored，本机复用）
OUT = HERE / 'ma_breadth_multi.json.gz'  # 派生多周期序列（版本化）
PROD = BACKEND.parent / 'data' / 'stocks' / 'close_series.json'  # 复用生产代码表
DAYS = 1000
PERIODS = (20, 60, 120)
CLEAN_FROM = '2022-07-01'  # 剔除停牌股 tail 污染的早期碎片

if CLOSES.exists():
    with gzip.open(CLOSES, 'rt', encoding='utf-8') as f:
        per_code = json.load(f)
    print(f'复用缓存 {CLOSES.name}: {len(per_code)} 只', flush=True)
else:
    from src.providers.stock_history_provider import StockHistoryProvider
    codes = list(json.loads(PROD.read_text())['stocks'].keys())
    print(f'缓存缺失，重抓 universe={len(codes)}（单线程）', flush=True)
    provider = StockHistoryProvider()
    per_code = {}
    ok = fail = 0
    t0 = time.time()
    for i, code in enumerate(codes):
        try:
            bars = provider.fetch_history(code, days=DAYS)
            per_code[code] = {b.date.isoformat(): b.c for b in bars}
            ok += 1
        except Exception:
            fail += 1
        if (i + 1) % 500 == 0:
            el = time.time() - t0
            print(f'  {i+1}/{len(codes)} ok={ok} fail={fail} {el:.0f}s eta={el/(i+1)*(len(codes)-i-1):.0f}s', flush=True)
    print(f'抓取完成 ok={ok} fail={fail} {time.time()-t0:.0f}s', flush=True)
    with gzip.open(CLOSES, 'wt', encoding='utf-8') as f:
        json.dump(per_code, f, ensure_ascii=False)
    print(f'原始收盘已缓存 {CLOSES}', flush=True)

all_dates = sorted({d for m in per_code.values() for d in m})
print(f'日期 {all_dates[0]} -> {all_dates[-1]} n={len(all_dates)}', flush=True)


def breadth_series(period: int):
    above = defaultdict(int); valid = defaultdict(int)
    for m in per_code.values():
        ds = sorted(m); closes = [m[d] for d in ds]
        if len(closes) < period:
            continue
        pref = [0.0]
        for c in closes:
            pref.append(pref[-1] + c)
        for p in range(period - 1, len(closes)):
            sma = (pref[p + 1] - pref[p + 1 - period]) / period
            d = ds[p]; valid[d] += 1
            if closes[p] > sma:
                above[d] += 1
    return [{'date': d, 'rate': round(above[d] / valid[d] * 100, 1)}
            for d in all_dates if valid[d] > 0]


def pct(vs, p):
    i = (len(vs) - 1) * p / 100; lo, hi = math.floor(i), math.ceil(i)
    return round(vs[lo] + (vs[hi] - vs[lo]) * (i - lo), 1)


def tierdist(vals, lo_cold, mid, hot):
    def tier(r): return '过热' if r >= hot else '偏暖' if r >= mid else '偏冷' if r >= lo_cold else '冰点'
    c = Counter(tier(v) for v in vals)
    return {k: f'{c[k]/len(vals)*100:.0f}%' for k in ['冰点', '偏冷', '偏暖', '过热']}


result = {}
for period in PERIODS:
    s = breadth_series(period)
    s_clean = [x for x in s if x['date'] >= CLEAN_FROM]
    vals = sorted(x['rate'] for x in s_clean)
    result[f'ma{period}'] = s
    print(f'\n===== MA{period}  干净窗口 n={len(vals)} mean={st.mean(vals):.1f} median={pct(vals,50)} std={st.pstdev(vals):.1f} =====', flush=True)
    print('  分位 ' + '  '.join(f'P{p}={pct(vals,p)}' for p in [10, 20, 25, 50, 75, 80, 90]), flush=True)
    print('  当前25/50/70:', tierdist(vals, 25, 50, 70), flush=True)
    # 该周期"实证对称尾" = P20/P80 取整到 5
    p20 = pct(vals, 20); p80 = pct(vals, 80)
    print(f'  实证对称尾 P20={p20} P80={p80}', flush=True)

with gzip.open(OUT, 'wt', encoding='utf-8') as f:
    json.dump(result, f, ensure_ascii=False)
print(f'\n多周期宽度序列已存 {OUT}', flush=True)
