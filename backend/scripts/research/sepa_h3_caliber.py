"""H3 档位口径复核 (审查 #8): 生产 7 条 vs 回测 8 条 × 新漏斗分布.

口径漂移事实: 回测 index_template_pass_count 条件7 = 指数r60 > 000985 r60 (max 8);
生产 trend.py:90 指数 rs_pct=None → 条件7 恒 False (max 7)。classify_regime 阈值
(>=6 / <=3) 两边一致 → 生产档位分布系统性偏防守。本脚本只读复核, 不动预注册
sepa_backtest.py 本体。

四口径 (2×2):
  A. 8条 + 入场池 >=6     预注册原始 H3 (复现基线)
  B. 7条 + 入场池 >=6     生产口径, 旧漏斗 (b5471f98 前)
  C. 8条 + 入场池 = 全有效  回测口径, 新漏斗 (b5471f98 后 <6 保留进漏斗)
  D. 7条 + 入场池 = 全有效  当前生产实际配置

判定沿用预注册 H3: offense vs defense 两比例合并 z 单侧 p<0.05 且 offense 胜率
> defense → 可挂信号。本脚本属事后复核 (非预注册), 结论只用于裁决 defense gating
口径对齐与文案, 不新增挂信号依据。
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

import sepa_backtest as sb

VARIANTS = ("A_8cond_pass6", "B_7cond_pass6", "C_8cond_allpool", "D_7cond_allpool")


def index_pass_7cond(close: pd.Series, beats_bench_r60: pd.Series) -> pd.Series:
    """生产口径: 8 条减去条件7 (恒 False), 即 pass8 - cond7。"""
    pass8 = sb.index_template_pass_count(close, beats_bench_r60)
    return pass8 - beats_bench_r60.astype("float64")


def run(data_root: Path) -> None:
    bench = sb.load_index_cached(sb.RS_BENCHMARK)
    regime_idx = {
        code: sb.load_index_cached(code) for code in sb.REGIME_INDICES
    }
    close = sb.load_close_shards(data_root)
    print(
        f"个股矩阵 {close.shape[0]} 日 × {close.shape[1]} 只 "
        f"({close.index[0].date()}..{close.index[-1].date()})"
    )

    mats = sb.prepare_eval_matrices(close)
    bench_r = bench.reindex(close.index)
    bench_fwd20 = (bench_r / bench_r.shift(-sb.HORIZON) - 1.0).to_numpy()
    bench_r60 = bench_r / bench_r.shift(60) - 1.0

    idx8: dict[str, pd.Series] = {}
    idx7: dict[str, pd.Series] = {}
    for code, s in regime_idx.items():
        sr = s.reindex(close.index)
        beats = (sr / sr.shift(60) - 1.0) > bench_r60
        idx8[code] = sb.index_template_pass_count(sr, beats)
        idx7[code] = index_pass_7cond(sr, beats)

    buckets = {v: {r: {"win": 0, "all": 0} for r in ("offense", "defense", "neutral")}
               for v in VARIANTS}
    regime_days = {v: {r: 0 for r in ("offense", "defense", "neutral")} for v in VARIANTS}

    for t in sb.eval_positions(close):
        if not np.isfinite(bench_fwd20[t]) or not np.isfinite(bench_r60.iloc[t]):
            continue
        counts, fwd = sb.cross_section(close, mats, t, float(bench_r60.iloc[t]))
        excess = fwd - bench_fwd20[t]
        finite = np.isfinite(counts) & np.isfinite(excess)
        for v, idx, pool_pass6 in (
            ("A_8cond_pass6", idx8, True),
            ("B_7cond_pass6", idx7, True),
            ("C_8cond_allpool", idx8, False),
            ("D_7cond_allpool", idx7, False),
        ):
            regime = sb.classify_regime(
                [int(idx[c].iloc[t]) for c in sb.REGIME_INDICES
                 if np.isfinite(idx[c].iloc[t])]
            )
            regime_days[v][regime] += 1
            sel = (counts >= 6) & finite if pool_pass6 else finite
            e = excess[sel]
            buckets[v][regime]["all"] += len(e)
            buckets[v][regime]["win"] += int((e > 0).sum())

    for v in VARIANTS:
        days, b = regime_days[v], buckets[v]
        off, de = b["offense"], b["defense"]
        n_off, n_de = off["all"], de["all"]
        print(f"\n[{v}] 评估日 off/neu/def = {days['offense']}/{days['neutral']}/{days['defense']}")
        if n_off < sb.H3_MIN_ENTRIES or n_de < sb.H3_MIN_ENTRIES or \
                days["offense"] < sb.H3_MIN_DAYS or days["defense"] < sb.H3_MIN_DAYS:
            print(f"  ★ {sb.VERDICT_NO_EVIDENCE} — off {n_off}笔 / def {n_de}笔 不足")
            continue
        z, p = sb.two_proportion_ztest_one_sided(
            off["win"], n_off, de["win"], n_de
        )
        w_off, w_de = off["win"] / n_off, de["win"] / n_de
        verdict, detail = sb.judge(
            p, w_off > w_de, True,
            f"offense {off['win']}/{n_off}={w_off:.1%} vs defense {de['win']}/{n_de}={w_de:.1%}, z={z:.2f}",
        )
        print(f"  ★ {verdict} — {detail}")


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[3] / "data"
    if len(sys.argv) > 1:
        root = Path(sys.argv[1])
    run(root)
