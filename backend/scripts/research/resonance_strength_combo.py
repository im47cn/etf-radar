"""strength×resonance 组合检验 — 预注册判据 + 样本外验证.

基础事实(已验证, 见 memory resonance-alpha-vs-transmission-null): resonance 状态下
美股动量方向(theme.returns.r_1d) → 次日 A 股 trigger_cn_etf 同向 56.8% 全样本 /
验证段(≥2024) 54.6% 整体。本脚本检验: 该同向率是否随信号日主题的美股强度
(us_strength.composite, 0-100) 分层 — 即 strength 是否对 resonance alpha 有组合增益。

====================== 预注册判据(跑数前定死, 不做变体) ======================

事件口径(与 resonance_conditions.py 完全一致): date t 的 theme_signals 中
signal=='resonance' 且 trigger_cn_etf 非空; 美股动量 = theme.returns.r_1d
(跳过 None/0); 结果 = 下一 snapshot 的 trigger_cn_etf 的 returns.r_1d 符号与
动量符号是否同向; 缺次日数据剔除该事件。分档条件取同日 us_strength.composite
(缺省剔除该事件)。

固定分档(非数据驱动):
  high_str: composite ≥ 60;  mid_str: 40 ≤ composite < 60;  low_str: composite < 40

样本切分: 训练段 < 2024-01-01 (估计), 验证段 ≥ 2024-01-01 (确认)。

成功判据(验证段): high_str 同向率 > low_str 同向率 且 high_str ≥ 58%
(比无条件 56.8% 有实质抬升, 非噪声级差异)。

判定规则: 训练段无分层(high_str 未高于 low_str) → 直接判"组合无增益";
验证段不达标 → "组合无增益, resonance 保持独立使用"。
不试替代分档/阈值(防多重检验)。

附输出: 整体同向率、各档 n、单调性检查(high_str ≥ mid_str ≥ low_str)。

============================================================================
"""
from __future__ import annotations

import json
import os
from pathlib import Path

DATA = Path(__file__).resolve().parents[3] / "data" / "snapshots"
SPLIT = "2024-01-01"          # 训练/验证切分日
STR_HIGH, STR_LOW = 60, 40    # 固定分档阈值(composite)


def load_all() -> tuple[list[str], dict[str, dict], dict[str, dict],
                        dict[str, dict], dict[str, dict]]:
    """→ (dates, signals: date→{theme:cn_code}, us_mom: date→{theme:r1d},
    strength: date→{theme:composite}, etf_r1: date→{code:r1d})"""
    dates = sorted(d for d in os.listdir(DATA) if len(d) == 10 and d[4] == "-")
    signals: dict[str, dict] = {}
    us_mom: dict[str, dict] = {}
    strength: dict[str, dict] = {}
    etf_r1: dict[str, dict] = {}
    for d in dates:
        with open(DATA / d / "signals.json") as f:
            ts = json.load(f)["theme_signals"]
        with open(DATA / d / "themes.json") as f:
            th = json.load(f)["themes"]
        with open(DATA / d / "etfs.json") as f:
            etfs = json.load(f)["etfs"]
        us_mom[d] = {t["id"]: t.get("returns", {}).get("r_1d") for t in th}
        strength[d] = {t["id"]: (t.get("us_strength") or {}).get("composite") for t in th}
        signals[d] = {s["theme_id"]: s["trigger_cn_etf"]
                      for s in ts if s.get("signal") == "resonance"
                      and s.get("trigger_cn_etf") and s["theme_id"] in us_mom[d]}
        etf_r1[d] = {e["code"]: (e.get("returns") or {}).get("r_1d") for e in etfs}
    return dates, signals, us_mom, strength, etf_r1


def period_of(date: str) -> str:
    return "train" if date < SPLIT else "valid"


def bucket_of(c: int) -> str:
    if c >= STR_HIGH:
        return "high_str"
    if c >= STR_LOW:
        return "mid_str"
    return "low_str"


def rate(hits: list[int]) -> tuple[float, int]:
    return (sum(hits) / len(hits), len(hits)) if hits else (float("nan"), 0)


def main() -> None:
    dates, signals, us_mom, strength, etf_r1 = load_all()
    di_map = {d: i for i, d in enumerate(dates)}

    events: list[dict[str, object]] = []
    n_no_next = n_no_str = 0
    for d in dates:
        for theme, code in signals[d].items():
            m = us_mom[d].get(theme)
            if m is None or m == 0:
                continue
            s = strength[d].get(theme)
            if s is None:
                n_no_str += 1
                continue
            if di_map[d] + 1 >= len(dates):
                n_no_next += 1
                continue
            nd = dates[di_map[d] + 1]
            r = etf_r1[nd].get(code)
            if r is None:
                n_no_next += 1
                continue
            hit = 1 if (r > 0) == (m > 0) else 0
            events.append({"date": d, "bucket": bucket_of(int(s)), "hit": hit})

    print(f"resonance 事件(含强度分档): {len(events)}  "
          f"(剔除: 缺 composite={n_no_str}, 缺次日数据={n_no_next})")
    n_train = sum(1 for e in events if period_of(str(e["date"])) == "train")
    print(f"  训练段(<{SPLIT}): {n_train}   验证段(≥{SPLIT}): {len(events) - n_train}")

    buckets = ["high_str", "mid_str", "low_str"]
    overall: dict[str, float] = {}
    stratified: dict[str, dict[str, float]] = {}
    ns: dict[str, dict[str, int]] = {}
    for per in ("train", "valid"):
        print(f"  [{per}]")
        for name in buckets:
            hits = [e["hit"] for e in events
                    if period_of(str(e["date"])) == per and e["bucket"] == name]
            r, n = rate(hits)
            shown = f"{r:6.1%}" if hits else "   n/a"
            print(f"    {name:8s}: 同向率 {shown}  (n={n})")
            stratified.setdefault(per, {})[name] = r
            ns.setdefault(per, {})[name] = n
        hits = [e["hit"] for e in events if period_of(str(e["date"])) == per]
        r, n = rate(hits)
        print(f"    {'整体':8s}: 同向率 {r:6.1%}  (n={n})")
        overall[per] = r

    print("\n[预注册判定]")
    train_hi, train_lo = stratified["train"]["high_str"], stratified["train"]["low_str"]
    if ns["train"]["low_str"] == 0:
        print("  训练段 low_str 档结构性空集 (resonance 事件几乎不发生在"
              " composite<40 主题上) → 分层不可检验, 组合无增益")
        return
    if not train_hi > train_lo:
        print(f"  训练段无分层 (high_str {train_hi:.1%} ≤ low_str {train_lo:.1%})"
              " → 组合无增益")
        return
    valid_hi, valid_lo = stratified["valid"]["high_str"], stratified["valid"]["low_str"]
    mono = (stratified["valid"]["high_str"] >= stratified["valid"]["mid_str"]
            >= stratified["valid"]["low_str"])
    print(f"  训练段有分层: high_str {train_hi:.1%} > low_str {train_lo:.1%}")
    passed = valid_hi > valid_lo and valid_hi >= 0.58
    print(f"  验证段: high_str {valid_hi:.1%} vs low_str {valid_lo:.1%}, "
          f"整体 {overall['valid']:.1%}; 单调性(high≥mid≥low): "
          f"{'是' if mono else '否'}")
    if passed:
        print("  判定: 通过 → strength×resonance 有组合增益, "
              "产品可按 composite≥60 标注高置信")
    else:
        print("  判定: 不达标 → 组合无增益, resonance 保持独立使用")


if __name__ == "__main__":
    main()
