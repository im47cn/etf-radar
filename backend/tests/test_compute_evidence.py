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

    result = compute_evidence(tmp_path, window=60, horizon=20)

    # 顶层结构
    assert result["schema_version"] == "1.0"
    assert result["as_of_date"]
    assert set(result["sample"]) == {"start", "end", "n_days"}
    assert result["sample"]["n_days"] == n_days

    # IC: by_horizon 3 档 + rolling 非空 (80日 window60 horizon20 至少1点)
    ic = result["ic"]
    assert {e["horizon"] for e in ic["by_horizon"]} == {1, 5, 20}
    assert len(ic["rolling"]) > 0

    # ARCH: 8 主题 + summary + 代表 ACF
    arch = result["arch"]
    assert len(arch["themes"]) == 8
    for e in arch["themes"]:
        assert {"theme_id", "name", "n", "r2_lb_p", "is_arch", "ret_lb_p"} <= set(e)
    assert arch["summary"]["tested"] == 8
    assert arch["summary"]["arch_count"] <= 8
    assert len(arch["representative_acf"]) == 4  # 强 ARCH 2 + 无 ARCH 2
    for v in arch["representative_acf"].values():
        assert len(v) == 16  # acf lag 0..15


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
