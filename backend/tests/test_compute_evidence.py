"""compute_evidence 端到端: 合成 snapshots -> 校验 signal_evidence 字段齐全."""
from __future__ import annotations

import json

import numpy as np

from scripts.compute_evidence import compute_evidence


def _make_themes(rng: np.random.Generator, n_themes: int = 8) -> list[dict[str, object]]:
    return [
        {
            "id": f"t{i}",
            "name": f"主题{i}",
            "cn_strength": {"composite": int(rng.integers(0, 100))},
            "returns": {"r_1d": float(rng.normal(scale=0.01))},
        }
        for i in range(n_themes)
    ]


def test_compute_evidence_writes_all_fields(tmp_path):
    rng = np.random.default_rng(0)
    snap = tmp_path / "snapshots"
    n_days = 80
    for i in range(n_days):
        d = f"2021-01-{i + 1:02d}"  # 字符串日期 (load 只排序, 不校验真实日历)
        (snap / d).mkdir(parents=True, exist_ok=True)
        with open(snap / d / "themes.json", "w") as f:
            json.dump({"themes": _make_themes(rng)}, f)

    result = compute_evidence(tmp_path, horizon=20)

    # 顶层结构
    assert result["schema_version"] == "1.0"
    assert result["as_of_date"]
    assert set(result["sample"]) == {"start", "end", "n_days"}
    assert result["sample"]["n_days"] == n_days

    # IC: by_horizon 3 档 + rolling 非空 (80日 window60 horizon20 至少1点)
    ic = result["ic"]
    assert {e["horizon"] for e in ic["by_horizon"]} == {1, 5, 20}
    assert len(ic["rolling"]) > 0
    assert {"ic_5", "ic_20", "ic_60"} <= set(ic["rolling"][0])

    # ARCH: 8 主题 + summary + 代表 ACF
    arch = result["arch"]
    assert len(arch["themes"]) == 8
    for e in arch["themes"]:
        assert {"theme_id", "name", "n", "r2_lb_p", "is_arch", "ret_lb_p"} <= set(e)
    assert arch["summary"]["tested"] == 8
    assert arch["summary"]["arch_count"] <= 8
    assert len(arch["representative_acf"]) == 8  # 全主题 (8 个, 非 4 代表)
    for v in arch["representative_acf"].values():
        assert len(v) == 16  # acf lag 0..15

    # 逐季 ARCH 显著比例: 80 日全在 2021-Q1 -> 1 个点, period 形如 YYYY-Qn
    ts = arch["time_series"]
    assert len(ts) == 1
    assert ts[0]["period"] == "2021-Q1"
    assert ts[0]["tested"] == 8
    assert {"period", "arch_ratio", "arch_count", "tested"} <= set(ts[0])


def test_compute_evidence_arch_time_series_quarterly_threshold(tmp_path):
    """逐季时序: Q1(80入选)/Q2(20非最新短季,跳过)/Q3(30最新季,不过滤+is_partial)."""
    rng = np.random.default_rng(2)
    snap = tmp_path / "snapshots"
    for span, month in [(80, 1), (20, 4), (30, 7)]:
        for i in range(span):
            d = f"2021-{month:02d}-{i + 1:02d}"
            (snap / d).mkdir(parents=True, exist_ok=True)
            with open(snap / d / "themes.json", "w") as f:
                json.dump({"themes": _make_themes(rng)}, f)

    ts = compute_evidence(tmp_path)["arch"]["time_series"]
    # Q2 非最新且 <40 -> 跳过; Q3 最新季 <40 不过滤 -> 入选且 is_partial
    assert [e["period"] for e in ts] == ["2021-Q1", "2021-Q3"]
    assert all(e["tested"] == 8 for e in ts)
    assert ts[-1]["is_partial"] is True
    assert all(not e.get("is_partial", False) for e in ts[:-1])


def test_compute_evidence_arch_sorted_by_significance(tmp_path):
    rng = np.random.default_rng(1)
    snap = tmp_path / "snapshots"
    for i in range(80):
        (snap / f"2021-01-{i + 1:02d}").mkdir(parents=True, exist_ok=True)
        with open(snap / f"2021-01-{i + 1:02d}" / "themes.json", "w") as f:
            json.dump({"themes": _make_themes(rng)}, f)
    arch = compute_evidence(tmp_path)["arch"]
    ps = [float(e["r2_lb_p"]) for e in arch["themes"]]
    assert ps == sorted(ps)  # 按 r2_lb_p 升序 (最显著在前)
