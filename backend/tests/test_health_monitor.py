"""哨兵 health_monitor 单测——纯判定 evaluate + 编排计数上限。"""
from __future__ import annotations

import json
from datetime import datetime, timezone


from src import health_monitor as hm

# 固定"当前时刻"用于漏触发判据(2026-07-08 是周三,CN/US 交易日)。
TRADING_DAY = datetime(2026, 7, 8, tzinfo=timezone.utc)
SATURDAY = datetime(2026, 7, 11, tzinfo=timezone.utc)  # 非交易日


def _utc(y, m, d, hh=0, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=timezone.utc)


def _healthy_meta():
    return {
        "providers": {"cn": {"status": "ok"}, "us": {"status": "ok"}},
        "stale_minutes": 0,
        "cn_data_date": "2026-07-08",
    }


def _healthy_qc():
    return {
        "over_threshold": False,
        "self": {"date": "2026-07-08"},
        "dapanyuntu": {"date": "2026-07-07"},
    }


# ----------------------------- evaluate -----------------------------
def test_evaluate_healthy_no_findings():
    findings = hm.evaluate(_healthy_meta(), _healthy_qc(), ["2026-07-07", "2026-07-08"], runs={})
    assert findings == []


def test_evaluate_cn_provider_degraded():
    meta = _healthy_meta()
    meta["providers"]["cn"]["status"] = "degraded"
    kinds = {f["kind"] for f in hm.evaluate(meta, _healthy_qc(), [], runs={})}
    assert "cn_provider_degraded" in kinds


def test_evaluate_cn_provider_stale_status():
    meta = _healthy_meta()
    meta["providers"]["cn"]["status"] = "stale"
    kinds = {f["kind"] for f in hm.evaluate(meta, _healthy_qc(), [], runs={})}
    assert "cn_provider_degraded" in kinds


def test_evaluate_data_stale_minutes():
    meta = _healthy_meta()
    meta["stale_minutes"] = 200
    findings = hm.evaluate(meta, _healthy_qc(), [], runs={})
    f = next(f for f in findings if f["kind"] == "data_stale")
    assert f["remedy_workflow"] == "cn-refresh"


def test_evaluate_reconcile_over_when_self_behind():
    qc = _healthy_qc()
    qc["over_threshold"] = True
    qc["self"]["date"] = "2026-07-07"
    qc["dapanyuntu"]["date"] = "2026-07-08"
    kinds = {f["kind"] for f in hm.evaluate(_healthy_meta(), qc, [], runs={})}
    assert "reconcile_over" in kinds


def test_evaluate_reconcile_over_ignored_when_self_current():
    """over_threshold 但 self.date >= dpyt.date（自身不落后）→ 不判缺陷。"""
    qc = _healthy_qc()
    qc["over_threshold"] = True
    qc["self"]["date"] = "2026-07-08"
    qc["dapanyuntu"]["date"] = "2026-07-07"
    kinds = {f["kind"] for f in hm.evaluate(_healthy_meta(), qc, [], runs={})}
    assert "reconcile_over" not in kinds


def test_evaluate_close_series_gap():
    # 缺 2026-07-07（工作日交易日），复用 stocks_continuity
    dates = ["2026-07-06", "2026-07-08"]
    findings = hm.evaluate(_healthy_meta(), _healthy_qc(), dates, runs={})
    f = next(f for f in findings if f["kind"] == "close_series_gap")
    assert f["remedy_workflow"] == "stocks-history-backfill"


def test_evaluate_workflow_missed_or_failed():
    runs = {"cn-refresh": {"status": "completed", "conclusion": "failure"}}
    findings = hm.evaluate(_healthy_meta(), _healthy_qc(), [], runs=runs, now=TRADING_DAY)
    f = next(f for f in findings if f["kind"] == "workflow_missed_or_failed")
    assert f["remedy_workflow"] == "cn-refresh"
    assert "failed" in f["detail"]


def test_evaluate_workflow_missing_run():
    """关键 workflow 无任何成功 run（None）→ 交易日活跃窗口内判缺陷。"""
    runs = {"cn-refresh": None}
    kinds = {
        f["kind"]
        for f in hm.evaluate(_healthy_meta(), _healthy_qc(), [], runs=runs, now=_utc(2026, 7, 8, 5))
    }
    assert "workflow_missed_or_failed" in kinds


def test_evaluate_workflow_in_progress_not_flagged():
    """正在运行的 workflow（status!=completed, conclusion=None）不误判为失败。"""
    runs = {"cn-refresh": {"status": "in_progress", "conclusion": None}}
    kinds = {
        f["kind"]
        for f in hm.evaluate(_healthy_meta(), _healthy_qc(), [], runs=runs, now=TRADING_DAY)
    }
    assert "workflow_missed_or_failed" not in kinds


def test_evaluate_workflow_success_not_flagged():
    """最近 success 且 createdAt 在预期窗口内 → 不报。"""
    runs = {"cn-refresh": {"status": "completed", "conclusion": "success",
                           "createdAt": "2026-07-08T02:00:00Z"}}
    kinds = {
        f["kind"]
        for f in hm.evaluate(_healthy_meta(), _healthy_qc(), [], runs=runs, now=_utc(2026, 7, 8, 3))
    }
    assert "workflow_missed_or_failed" not in kinds


# ----------------------------- 漏触发判据（createdAt + 节奏） -----------------------------
def test_missed_cn_refresh_stale_last_success():
    """CN 交易日、now=05:00 UTC(活跃窗口内)、最近 success createdAt=昨天 → missed。"""
    runs = {"cn-refresh": {"status": "completed", "conclusion": "success",
                           "createdAt": "2026-07-07T02:00:00Z"}}
    findings = hm.evaluate(_healthy_meta(), _healthy_qc(), [], runs=runs, now=_utc(2026, 7, 8, 5))
    f = next(f for f in findings if f["kind"] == "workflow_missed_or_failed")
    assert "missed" in f["detail"]
    assert f["remedy_workflow"] == "cn-refresh"


def test_cn_refresh_recent_success_not_missed():
    """CN 交易日、now=03:00 UTC、最近 success=1h 前 → 不报。"""
    runs = {"cn-refresh": {"status": "completed", "conclusion": "success",
                           "createdAt": "2026-07-08T02:00:00Z"}}
    kinds = {
        f["kind"]
        for f in hm.evaluate(_healthy_meta(), _healthy_qc(), [], runs=runs, now=_utc(2026, 7, 8, 3))
    }
    assert "workflow_missed_or_failed" not in kinds


def test_cn_refresh_after_close_not_missed():
    """关键回归:CN 交易日 now=10:00 UTC(收盘后,超末班 07:45+grace)、
    最近 success=当日 07:40 UTC → 不报(当日工作已完成,防每晚误报)。"""
    runs = {"cn-refresh": {"status": "completed", "conclusion": "success",
                           "createdAt": "2026-07-08T07:40:00Z"}}
    kinds = {
        f["kind"]
        for f in hm.evaluate(_healthy_meta(), _healthy_qc(), [], runs=runs, now=_utc(2026, 7, 8, 10))
    }
    assert "workflow_missed_or_failed" not in kinds


def test_cn_refresh_before_open_not_missed():
    """CN 交易日 now=01:00 UTC(早于首班 01:15+grace1h=02:15,开盘前)、
    无当日 run → 不判 missed(当日工作尚未应开始)。"""
    runs = {"cn-refresh": None}
    kinds = {
        f["kind"]
        for f in hm.evaluate(_healthy_meta(), _healthy_qc(), [], runs=runs, now=_utc(2026, 7, 8, 1))
    }
    assert "workflow_missed_or_failed" not in kinds


def test_cn_refresh_at_deadline_boundary_not_missed():
    """边界:now 恰等于 earliest+grace(02:15 UTC)时 now < deadline 为假但
    max_age(3h)未超(success 01:20,55min 前)→ 不报,坐实 `now < deadline` 半开区间。"""
    runs = {"cn-refresh": {"status": "completed", "conclusion": "success",
                           "createdAt": "2026-07-08T01:20:00Z"}}
    kinds = {
        f["kind"]
        for f in hm.evaluate(_healthy_meta(), _healthy_qc(), [], runs=runs, now=_utc(2026, 7, 8, 2, 15))
    }
    assert "workflow_missed_or_failed" not in kinds


def test_cn_refresh_in_window_stale_missed():
    """CN 交易日 now=05:00 UTC(窗口内)、最近 success=01:20 UTC(>3h)→ missed。"""
    runs = {"cn-refresh": {"status": "completed", "conclusion": "success",
                           "createdAt": "2026-07-08T01:20:00Z"}}
    kinds = {
        f["kind"]
        for f in hm.evaluate(_healthy_meta(), _healthy_qc(), [], runs=runs, now=_utc(2026, 7, 8, 5))
    }
    assert "workflow_missed_or_failed" in kinds


def test_cn_refresh_success_missing_created_at_not_missed():
    """success run 存在但 createdAt 缺失 → 保守不判 missed(防 gh 格式微调误报)。"""
    runs = {"cn-refresh": {"status": "completed", "conclusion": "success"}}  # 无 createdAt
    kinds = {
        f["kind"]
        for f in hm.evaluate(_healthy_meta(), _healthy_qc(), [], runs=runs, now=_utc(2026, 7, 8, 5))
    }
    assert "workflow_missed_or_failed" not in kinds


def test_weekend_no_run_not_missed():
    """周末（非交易日）任何 workflow 无当日 run → gate 生效不报。"""
    runs = {wf: None for wf in ("cn-refresh", "stocks-daily", "cn-eod-archive")}
    kinds = {
        f["kind"]
        for f in hm.evaluate(_healthy_meta(), _healthy_qc(), [], runs=runs, now=_utc(2026, 7, 11, 12))
    }
    assert "workflow_missed_or_failed" not in kinds


def test_missed_stocks_daily_last_success_yesterday():
    """stocks-daily: now=10:00 交易日、最近 success=昨天 → missed。"""
    runs = {"stocks-daily": {"status": "completed", "conclusion": "success",
                             "createdAt": "2026-07-07T08:35:00Z"}}
    findings = hm.evaluate(_healthy_meta(), _healthy_qc(), [], runs=runs, now=_utc(2026, 7, 8, 10))
    assert any(f["kind"] == "workflow_missed_or_failed" for f in findings)


def test_stocks_daily_today_success_not_missed():
    """stocks-daily: 最近 success=今日 09:00 UTC（≥ deadline 08:30）→ 不报。"""
    runs = {"stocks-daily": {"status": "completed", "conclusion": "success",
                             "createdAt": "2026-07-08T09:00:00Z"}}
    kinds = {
        f["kind"]
        for f in hm.evaluate(_healthy_meta(), _healthy_qc(), [], runs=runs, now=_utc(2026, 7, 8, 10))
    }
    assert "workflow_missed_or_failed" not in kinds


def test_missed_us_refresh_over_26h():
    """us-refresh: 最近 success=30h 前 → missed。"""
    runs = {"us-refresh": {"status": "completed", "conclusion": "success",
                           "createdAt": "2026-07-07T06:00:00Z"}}  # ~30h before now
    findings = hm.evaluate(_healthy_meta(), _healthy_qc(), [], runs=runs, now=_utc(2026, 7, 8, 12))
    assert any(f["kind"] == "workflow_missed_or_failed" for f in findings)


def test_us_refresh_within_26h_not_missed():
    """us-refresh: 最近 success=10h 前 → 不报。"""
    runs = {"us-refresh": {"status": "completed", "conclusion": "success",
                           "createdAt": "2026-07-08T02:00:00Z"}}  # 10h before now
    kinds = {
        f["kind"]
        for f in hm.evaluate(_healthy_meta(), _healthy_qc(), [], runs=runs, now=_utc(2026, 7, 8, 12))
    }
    assert "workflow_missed_or_failed" not in kinds


# ----------------------------- 编排计数 -----------------------------
def _write_data_root(tmp_path, *, degraded=True):
    latest = tmp_path / "latest"
    latest.mkdir(parents=True)
    meta = _healthy_meta()
    if degraded:
        meta["providers"]["cn"]["status"] = "degraded"
    (latest / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    (latest / "market_breadth_qc.json").write_text(json.dumps(_healthy_qc()), encoding="utf-8")
    stocks = tmp_path / "stocks"
    stocks.mkdir()
    (stocks / "close_series.json").write_text(
        json.dumps({"dates": ["2026-07-07", "2026-07-08"]}), encoding="utf-8"
    )
    return tmp_path


def test_run_dispatch_then_alert_after_max(tmp_path, monkeypatch):
    root = _write_data_root(tmp_path, degraded=True)
    dispatched = []
    alerted = []
    monkeypatch.setattr(hm, "_query_runs", lambda: {})
    monkeypatch.setattr(hm, "_dispatch", lambda wf: dispatched.append(wf))
    monkeypatch.setattr(hm, "send_alert", lambda title, desp: alerted.append(title) or True)

    # 前 MAX_ATTEMPTS 轮 → dispatch；之后转 alert。
    for _ in range(hm.MAX_ATTEMPTS):
        hm.run(root, dry_run=False)
    assert len(dispatched) == hm.MAX_ATTEMPTS
    assert alerted == []

    hm.run(root, dry_run=False)  # 耗尽
    assert len(dispatched) == hm.MAX_ATTEMPTS  # 不再 dispatch
    assert len(alerted) == 1

    hm.run(root, dry_run=False)  # 已 alerted 不重复推
    assert len(alerted) == 1


def test_run_resets_count_when_finding_gone(tmp_path, monkeypatch):
    root = _write_data_root(tmp_path, degraded=True)
    dispatched = []
    monkeypatch.setattr(hm, "_query_runs", lambda: {})
    monkeypatch.setattr(hm, "_dispatch", lambda wf: dispatched.append(wf))
    monkeypatch.setattr(hm, "send_alert", lambda title, desp: True)

    hm.run(root, dry_run=False)
    assert len(dispatched) == 1

    # 异常消失 → 计数重置
    meta = _healthy_meta()
    (root / "latest" / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    hm.run(root, dry_run=False)
    state = json.loads((root / "health" / "heal_state.json").read_text(encoding="utf-8"))
    assert "cn_provider_degraded" not in state

    # 异常复现 → 重新从 attempt 1 开始
    (root / "latest" / "meta.json").write_text(
        json.dumps({**_healthy_meta(), "providers": {"cn": {"status": "degraded"}, "us": {"status": "ok"}}}),
        encoding="utf-8",
    )
    hm.run(root, dry_run=False)
    assert len(dispatched) == 2


def test_run_tolerates_corrupt_json(tmp_path, monkeypatch):
    """损坏的 meta/qc/close/heal_state 不该让哨兵崩溃, 按缺失处理继续。"""
    latest = tmp_path / "latest"
    latest.mkdir(parents=True)
    (latest / "meta.json").write_text("{ broken json", encoding="utf-8")
    (latest / "market_breadth_qc.json").write_text("not json at all", encoding="utf-8")
    stocks = tmp_path / "stocks"
    stocks.mkdir()
    (stocks / "close_series.json").write_text('{"dates": "oops-not-a-list"}', encoding="utf-8")
    health = tmp_path / "health"
    health.mkdir()
    (health / "heal_state.json").write_text("}{corrupt", encoding="utf-8")

    monkeypatch.setattr(hm, "_query_runs", lambda: {})
    monkeypatch.setattr(hm, "_dispatch", lambda wf: None)
    monkeypatch.setattr(hm, "send_alert", lambda title, desp: True)

    # 不应抛异常; 全损坏数据 → 无 findings。
    findings = hm.run(tmp_path, dry_run=False)
    assert findings == []


def test_run_dry_run_no_side_effects(tmp_path, monkeypatch):
    root = _write_data_root(tmp_path, degraded=True)
    dispatched = []
    alerted = []
    monkeypatch.setattr(hm, "_query_runs", lambda: {})
    monkeypatch.setattr(hm, "_dispatch", lambda wf: dispatched.append(wf))
    monkeypatch.setattr(hm, "send_alert", lambda title, desp: alerted.append(title))

    findings = hm.run(root, dry_run=True)
    assert any(f["kind"] == "cn_provider_degraded" for f in findings)
    assert dispatched == []
    assert alerted == []
    assert not (root / "health" / "heal_state.json").exists()
