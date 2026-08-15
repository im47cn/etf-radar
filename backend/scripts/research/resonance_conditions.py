"""resonance 信号条件增强探索 — 预注册判据 + 样本外验证.

基础事实(已验证, 见 memory resonance-alpha-vs-transmission-null): resonance 状态下
美股动量方向(theme.returns.r_1d) → 次日 A 股 trigger_cn_etf 同向 56.8%
(基线 48.6%, n=3647)。本脚本探索该 alpha 的**分布**: 是否集中在可过滤的条件下。

====================== 预注册判据(跑数前定死, 不做变体) ======================

样本与口径: 与基础回测一致 — 全部 snapshot 中 signal=='resonance' 的
(日期, 主题) 事件; 美股动量 = theme.returns.r_1d; 次日收益 = 下一 snapshot 的
trigger_cn_etf 的 returns.r_1d。分解 t+k 需要连续 k 个 snapshot, 缺日则该事件
在 t+k 口径剔除(各 horizon 样本数可不同)。

样本切分: 训练段 < 2024-01-01 (估计), 验证段 ≥ 2024-01-01 (确认)。
只有验证段通过的过滤器才允许进产品。

Q1 动量幅度分档 (固定阈值, 非数据驱动):
  large: |us_mom| ≥ 1%;  mid: 0.3% ~ 1%;  small: < 0.3%
  假设: 幅度越大信息含量越高。
  成功判据(验证段): large 同向率 > small 同向率 且 large ≥ 55%。

Q2 alpha 衰减 (t+1/t+2/t+3/t+5 累计同向率):
  成功判据(验证段): t+2..t+5 任一 ≥ 53% → alpha 可延展持有期;
  全部 < 52% → 结论"信号严格次日", 产品必须强调当日了结。

Q3 主题条件波动调节 (触发 ETF trailing 30 日已实现年化波动, 按信号日点时计算):
  high: vol ≥ 30%;  low: < 30%
  成功判据(验证段): high 同向率 > low 同向率 且 high ≥ 55%。

判定规则: 三问各自独立判定; 任何一问训练段模式在验证段消失 → 该过滤器弃用,
不试替代分档/阈值(防多重检验)。全部失败 → resonance 保持无条件展示。

============================================================================
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np

DATA = Path(__file__).resolve().parents[3] / "data" / "snapshots"
SPLIT = "2024-01-01"          # 训练/验证切分日
HORIZONS = (1, 2, 3, 5)
VOL_WINDOW = 30               # Q3 trailing 波动窗口(日)
VOL_SPLIT = 0.30              # Q3 年化波动分界
MAG_LARGE, MAG_SMALL = 0.01, 0.003  # Q1 固定分档阈值


def load_all() -> tuple[list[str], dict[str, dict], dict[str, dict], dict[str, dict]]:
    """→ (dates, signals: date→{theme:cn_code}, us_mom: date→{theme:r1d}, etf_r1: date→{code:r1d})"""
    dates = sorted(d for d in os.listdir(DATA) if len(d) == 10 and d[4] == "-")
    signals: dict[str, dict] = {}
    us_mom: dict[str, dict] = {}
    etf_r1: dict[str, dict] = {}
    for d in dates:
        with open(DATA / d / "signals.json") as f:
            ts = json.load(f)["theme_signals"]
        with open(DATA / d / "themes.json") as f:
            th = json.load(f)["themes"]
        with open(DATA / d / "etfs.json") as f:
            etfs = json.load(f)["etfs"]
        us_mom[d] = {t["id"]: t.get("returns", {}).get("r_1d") for t in th}
        signals[d] = {s["theme_id"]: s["trigger_cn_etf"]
                      for s in ts if s.get("signal") == "resonance"
                      and s.get("trigger_cn_etf") and s["theme_id"] in us_mom[d]}
        etf_r1[d] = {e["code"]: (e.get("returns") or {}).get("r_1d") for e in etfs}
    return dates, signals, us_mom, etf_r1


def period_of(date: str) -> str:
    return "train" if date < SPLIT else "valid"


def cum_ret(dates: list[str], etf_r1: dict[str, dict], di: int, code: str, k: int) -> float | None:
    """第 di 个 snapshot 后 k 日的 etf 累计收益; 任一日缺失返回 None。"""
    if di + k >= len(dates):
        return None
    total = 1.0
    for dd in dates[di + 1:di + 1 + k]:
        r = etf_r1[dd].get(code)
        if r is None:
            return None
        total *= 1.0 + r
    return total - 1.0


def rate(hits: list[int]) -> tuple[float, int]:
    return (sum(hits) / len(hits), len(hits)) if hits else (float("nan"), 0)


def main() -> None:
    dates, signals, us_mom, etf_r1 = load_all()
    di_map = {d: i for i, d in enumerate(dates)}
    # trailing 30 日已实现波动 (点时): 随时间轴累积每 code 的 r_1d 历史
    hist: dict[str, list[tuple[str, str, float]]] = {}  # code -> [(date, r)]

    events: list[dict[str, object]] = []
    for d in dates:
        for code, r in etf_r1[d].items():
            if r is not None:
                hist.setdefault(code, []).append((d, r))
        for theme, code in signals[d].items():
            m = us_mom[d].get(theme)
            if m is None or m == 0:
                continue
            h = [r for _, r in hist.get(code, [])][-VOL_WINDOW:]
            vol = float(np.std(h, ddof=1) * np.sqrt(252)) if len(h) >= 15 else float("nan")
            events.append({"date": d, "theme": theme, "code": code,
                           "mom": float(m), "vol": vol})
        # 记录本日各 code 波动供后续(此循环内 vol 已即时算好, 无需后存)

    print(f"resonance 事件: {len(events)} (口径: 全时段)")
    n_train = sum(1 for e in events if period_of(str(e["date"])) == "train")
    print(f"  训练段(<{SPLIT}): {n_train}   验证段(≥{SPLIT}): {len(events) - n_train}")

    # 逐事件各 horizon 的方向命中 (1=同向)
    for e in events:
        d, code = str(e["date"]), str(e["code"])
        s = np.sign(float(e["mom"]))
        for k in HORIZONS:
            cr = cum_ret(dates, etf_r1, di_map[d], code, k)
            e[f"hit_{k}"] = (1 if np.sign(cr) == s else 0) if cr is not None else None

    def bucket_report(title: str, key: callable, buckets: list[tuple[str, callable]]) -> None:  # type: ignore[valid-type]
        print(f"\n===== {title} =====")
        valid_pass: dict[str, bool] = {}
        for per in ("train", "valid"):
            print(f"  [{per}]")
            for name, cond in buckets:
                hits = [e["hit_1"] for e in events
                        if period_of(str(e["date"])) == per and e["hit_1"] is not None
                        and cond(e)]
                r, n = rate(hits)
                print(f"    {name:8s}: 同向率 {r:6.1%}  (n={n})")
                if per == "valid":
                    valid_pass[name] = r
        return valid_pass  # type: ignore[return-value]

    # ---- Q1 动量幅度 ----
    v = bucket_report(
        "Q1 美股动量幅度分档 (判据: 验证段 large>small 且 large≥55%)", None,
        [("large", lambda e: abs(e["mom"]) >= MAG_LARGE),
         ("mid", lambda e: MAG_SMALL <= abs(e["mom"]) < MAG_LARGE),
         ("small", lambda e: abs(e["mom"]) < MAG_SMALL)])
    q1 = bool(v and v.get("large", 0) > v.get("small", 0) and v.get("large", 0) >= 0.55)

    # ---- Q2 衰减 ----
    print("\n===== Q2 alpha 衰减 (判据: 验证段 t+2..t+5 任一≥53% → 可延展; 全<52% → 严格次日) =====")
    extend = False
    for per in ("train", "valid"):
        line = f"  [{per}] "
        for k in HORIZONS:
            hits = [e[f"hit_{k}"] for e in events
                    if period_of(str(e["date"])) == per and e[f"hit_{k}"] is not None]
            r, n = rate(hits)
            line += f" t+{k}={r:5.1%}(n={n})"
            if per == "valid" and k > 1 and r >= 0.53:
                extend = True
        print(line)
    q2 = extend

    # ---- Q3 条件波动 ----
    v = bucket_report(
        "Q3 触发ETF trailing30日年化波动 (判据: 验证段 high>low 且 high≥55%; vol<15样本记 nan 剔除)", None,
        [("high", lambda e: np.isfinite(e["vol"]) and e["vol"] >= VOL_SPLIT),
         ("low", lambda e: np.isfinite(e["vol"]) and e["vol"] < VOL_SPLIT),
         ("nan", lambda e: not np.isfinite(e["vol"]))])
    q3 = bool(v and v.get("high", 0) > v.get("low", 0) and v.get("high", 0) >= 0.55)

    print("\n[预注册判定]")
    print(f"  Q1 幅度过滤:   {'通过 → 产品可按 |us_mom|≥1% 标注高置信' if q1 else '未通过 → 弃用幅度过滤'}")
    print(f"  Q2 延展持有期: {'通过 → alpha 可延展至 t+2+' if q2 else '未通过 → 信号严格次日, 产品强调当日属性'}")
    print(f"  Q3 波动过滤:   {'通过 → 产品可按高波动主题标注高置信' if q3 else '未通过 → 弃用波动过滤'}")


if __name__ == "__main__":
    main()
