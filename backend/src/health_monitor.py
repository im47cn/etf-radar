"""哨兵自愈 hub——巡检数据新鲜度 + 关键 workflow 运行状态,发现异常自动补偿,
计数上限内自愈,耗尽后经 Server酱 告警。

分层:
  - `evaluate()` 纯函数:输入 meta/qc/close_series_dates/runs → 产出 findings(便于单测)。
  - `run()` 编排:读数据 + 查 runs + 按 heal_state 计数决定 dispatch / alert。
  - `_query_runs()` / `_dispatch()` 封装 gh CLI(单测 monkeypatch)。

设计详见 .trellis/tasks/07-08-alert-sentinel/design.md。
"""
from __future__ import annotations

import argparse
import json
import logging
import subprocess
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from .etl.calendar import is_cn_trading_day, is_us_trading_day
from .notify.alert import send_alert
from .stocks_continuity import missing_trading_days

log = logging.getLogger(__name__)

STALE_ALERT_MIN = 120  # stale_minutes 超此值判 data_stale
MAX_ATTEMPTS = 2  # 同一 kind 补偿上限,超过转告警

# 巡检的关键 workflow → 补偿 workflow（此处补偿即重跑自身）。
KEY_WORKFLOWS = ["cn-refresh", "us-refresh", "stocks-daily", "cn-eod-archive"]


@dataclass(frozen=True)
class WorkflowSchedule:
    """关键 workflow 预期节奏（UTC）,用于判"超期未触发/漏触发"。

    - trading_gate: 'cn'|'us'|'none' —— 非对应交易日不判 missed(避免周末误报)。
    - earliest_utc: 当日最早应触发时刻(UTC time);now < earliest+grace 前不判。
    - grace_hours: 宽限,吸收 cron 触发延迟。
    - mode:
        'intraday' —— 盘中多班(如 cn-refresh):活跃窗口内最近 success createdAt 应在
                       max_age_hours 内,否则 missed。窗口外(收盘后/开盘前)不判。
        'daily'    —— 日频单班:最近 success createdAt 应 ≥ 当日 daily_deadline_utc,
                       否则 missed。
    - latest_utc:(intraday)当日末班时刻;now 超过 latest_utc+grace(收盘后)或早于
                  earliest_utc+grace(开盘前)→ 不判 missed(当日工作已完成/未开始)。
                  None 表示无上界(如 us-refresh 日频跨日,仅靠 max_age_hours)。
    """

    trading_gate: str
    earliest_utc: time
    grace_hours: float
    mode: str
    max_age_hours: Optional[float] = None  # intraday
    daily_deadline_utc: Optional[time] = None  # daily
    latest_utc: Optional[time] = None  # intraday 末班上界


# 真实 cron 节奏(见 design.md「漏触发判据」)。
WORKFLOW_SCHEDULES: dict[str, WorkflowSchedule] = {
    "cn-refresh": WorkflowSchedule(
        trading_gate="cn",
        earliest_utc=time(1, 15),  # 09:15 BJT 首班
        grace_hours=1.0,
        mode="intraday",
        max_age_hours=3.0,
        latest_utc=time(7, 45),  # 15:45 BJT 末班;收盘后不再判 missed
    ),
    "us-refresh": WorkflowSchedule(
        # us-refresh 日频、跨 UTC 日边界(22:30),故不设同日 earliest 门:
        # 仅靠 max_age_hours=26h(日频+grace)判"距最近 success 过久"。
        trading_gate="us",
        earliest_utc=time(0, 0),
        grace_hours=0.0,
        mode="intraday",
        max_age_hours=26.0,
    ),
    "stocks-daily": WorkflowSchedule(
        trading_gate="cn",
        earliest_utc=time(8, 30),  # 16:30 BJT
        grace_hours=1.0,
        mode="daily",
        daily_deadline_utc=time(8, 30),
    ),
    "cn-eod-archive": WorkflowSchedule(
        trading_gate="cn",
        earliest_utc=time(10, 0),  # 18:00 BJT
        grace_hours=1.0,
        mode="daily",
        daily_deadline_utc=time(10, 0),
    ),
}

Finding = dict[str, Any]  # {kind, severity, detail, remedy_workflow}


def _finding(kind: str, severity: str, detail: str, remedy: str) -> Finding:
    return {"kind": kind, "severity": severity, "detail": detail, "remedy_workflow": remedy}


def _trading_gate_open(gate: str, d: date) -> bool:
    """gate 对应交易日才判 missed;'none' 恒开。"""
    if gate == "cn":
        return is_cn_trading_day(d)
    if gate == "us":
        return is_us_trading_day(d)
    return True


def _parse_created_at(run: dict[str, Any]) -> Optional[datetime]:
    raw = run.get("createdAt")
    if not raw:
        return None
    try:
        # gh 返回 RFC3339 带 Z;统一为带 tz 的 UTC。
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _is_missed(
    sched: WorkflowSchedule, run: dict[str, Any], now: datetime, run_present: bool = True
) -> bool:
    """最近一条 success run 是否"超期/漏触发"(createdAt + 预期节奏)。

    仅在 gate 交易日、且已过当日 earliest+grace 后才判(避免过早/周末误报)。
    intraday 另设活跃窗口上界 latest_utc+grace:收盘后当日工作已完成 → 不判。
    run_present=False(无任何 qualifying success run)时,窗口内一律判 missed。
    run_present=True 但 createdAt 缺失/异常 → 保守不判(避免 gh 格式微调触发无谓补偿)。
    """
    today = now.date()
    if not _trading_gate_open(sched.trading_gate, today):
        return False
    earliest_dt = datetime.combine(today, sched.earliest_utc, tzinfo=timezone.utc)
    deadline = earliest_dt + timedelta(hours=sched.grace_hours)
    if now < deadline:
        return False  # 尚未到应触发时点,不判 missed

    # intraday 活跃窗口上界:超过末班+grace(收盘后)→ 当日工作已完成,不再判 missed。
    if sched.mode == "intraday" and sched.latest_utc is not None:
        latest_dt = datetime.combine(today, sched.latest_utc, tzinfo=timezone.utc) + timedelta(
            hours=sched.grace_hours
        )
        if now > latest_dt:
            return False

    if not run_present:
        return True  # 窗口内无任何 qualifying success run → missed

    created = _parse_created_at(run)
    if created is None:
        # success run 存在但 createdAt 缺失/格式异常 → 保守不判 missed,避免 gh
        # 输出格式微调触发无谓补偿。
        log.warning("_is_missed: run 缺有效 createdAt, 保守不判 missed: %r", run)
        return False

    if sched.mode == "intraday":
        assert sched.max_age_hours is not None
        return (now - created) > timedelta(hours=sched.max_age_hours)
    # daily:最近 success 应 ≥ 当日 deadline
    assert sched.daily_deadline_utc is not None
    day_deadline = datetime.combine(today, sched.daily_deadline_utc, tzinfo=timezone.utc)
    return created < day_deadline


def evaluate(
    meta: dict[str, Any],
    qc: dict[str, Any],
    close_series_dates: list[str],
    runs: dict[str, Optional[dict[str, Any]]],
    now: Optional[datetime] = None,
) -> list[Finding]:
    """纯判定:根据只读数据产出结构化 findings(无副作用)。

    now(UTC,默认当前时间)注入用于漏触发判据,便于单测固定时间。
    """
    if now is None:
        now = datetime.now(timezone.utc)
    findings: list[Finding] = []

    # 1. CN provider degraded / stale
    cn_status = (meta.get("providers", {}).get("cn", {}) or {}).get("status")
    if cn_status in ("degraded", "stale"):
        findings.append(
            _finding(
                "cn_provider_degraded",
                "warning",
                f"cn provider status={cn_status}",
                "cn-refresh",
            )
        )

    # 2. 数据陈旧
    stale = meta.get("stale_minutes")
    if isinstance(stale, (int, float)) and stale > STALE_ALERT_MIN:
        findings.append(
            _finding("data_stale", "warning", f"stale_minutes={stale}", "cn-refresh")
        )

    # 3. 对账超阈且自身落后 dapanyuntu → 温度链陈旧
    if qc.get("over_threshold"):
        self_date = (qc.get("self") or {}).get("date")
        dpyt_date = (qc.get("dapanyuntu") or {}).get("date")
        if self_date and dpyt_date and self_date < dpyt_date:
            findings.append(
                _finding(
                    "reconcile_over",
                    "warning",
                    f"reconcile over_threshold, self={self_date} < dpyt={dpyt_date}",
                    "stocks-daily",
                )
            )

    # 4. close_series 内部缺口（复用 C4 stocks_continuity）
    if close_series_dates:
        gaps = missing_trading_days(close_series_dates)
        if gaps:
            findings.append(
                _finding(
                    "close_series_gap",
                    "critical",
                    f"missing trading days: {[d.isoformat() for d in gaps]}",
                    "stocks-history-backfill",
                )
            )

    # 5. 关键 workflow 漏触发 / 失败
    # - run 已 completed 且非 success → failed。
    # - 正在运行（status!=completed, conclusion=None）不误判为失败,避免哨兵每小时
    #   撞上正常执行中的 workflow 触发补偿风暴。
    # - 最近一条为 success（或无 run）时,再按预期节奏(createdAt+now)判 missed:
    #   覆盖"昨天成功、今天该跑没跑,最近 run 仍是 success"的漏触发场景。
    for wf, run in runs.items():
        if run is not None and run.get("status") == "completed" and run.get("conclusion") != "success":
            findings.append(
                _finding(
                    "workflow_missed_or_failed",
                    "warning",
                    f"{wf}: failed conclusion={run.get('conclusion')}",
                    wf,
                )
            )
            continue

        # in_progress（未 completed 且 conclusion 未定）不判 missed——正在跑。
        if run is not None and run.get("status") != "completed" and run.get("conclusion") is None:
            continue

        sched = WORKFLOW_SCHEDULES.get(wf)
        if sched is None:
            # 无节奏配置的 workflow:仅保留"无 run"的旧判据。
            if run is None:
                findings.append(
                    _finding("workflow_missed_or_failed", "warning", f"{wf}: no recent success run", wf)
                )
            continue

        # 有节奏配置:无 run 或最近 success → 用 createdAt+now 判是否超期/漏触发。
        run_for_check = run if run is not None else {}
        if _is_missed(sched, run_for_check, now, run_present=run is not None):
            detail = f"{wf}: missed (no run in expected window)" if run is None \
                else f"{wf}: missed (last success createdAt={run.get('createdAt')} overdue)"
            findings.append(
                _finding("workflow_missed_or_failed", "warning", detail, wf)
            )

    return findings


# ----------------------------- gh 封装（单测 monkeypatch） -----------------------------
def _query_runs() -> dict[str, Optional[dict[str, Any]]]:
    """查关键 workflow 最近一次 run 的状态。gh 不可用/异常 → 该 wf 记 None。"""
    result: dict[str, Optional[dict[str, Any]]] = {}
    for wf in KEY_WORKFLOWS:
        try:
            out = subprocess.run(
                [
                    "gh", "run", "list", f"--workflow={wf}.yml", "-L", "1",
                    "--json", "status,conclusion,createdAt",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if out.returncode != 0:
                result[wf] = None
                continue
            data = json.loads(out.stdout or "[]")
            result[wf] = data[0] if data else None
        except Exception as exc:  # gh 缺失/超时——记 None，evaluate 会判缺陷
            log.warning("_query_runs(%s) 失败: %s", wf, exc)
            result[wf] = None
    return result


def _dispatch(workflow: str) -> None:
    """触发补偿 workflow（gh workflow run）。异常仅 log，不中断巡检。"""
    try:
        subprocess.run(
            ["gh", "workflow", "run", f"{workflow}.yml"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except Exception as exc:
        log.error("_dispatch(%s) 失败: %s", workflow, exc)


# ----------------------------- heal_state 持久化 -----------------------------
def _load_state(state_path: Path) -> dict[str, dict[str, Any]]:
    if state_path.exists():
        try:
            data = json.loads(state_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
            log.warning("heal_state 非 dict, 重置")
        except (ValueError, OSError) as exc:
            # 坏 heal_state 不该让哨兵永久瘫痪——重置为空态继续。
            log.warning("heal_state 损坏, 重置: %s", exc)
    return {}


def _save_state(state_path: Path, state: dict[str, dict[str, Any]]) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (ValueError, OSError) as exc:
            # 损坏/不可读的数据文件不该让整轮巡检崩溃——按缺失处理。
            log.warning("读取 %s 失败, 按缺失处理: %s", path, exc)
    return {}


# ----------------------------- 编排 -----------------------------
def run(data_root: Path, dry_run: bool) -> list[Finding]:
    """一轮巡检:读数据 → evaluate → 计数决定 dispatch/alert → 写 heal_state。

    dry_run 只打印 findings 与拟触发动作,不 dispatch/告警/写状态。返回 findings。
    """
    data_root = Path(data_root)
    meta = _read_json(data_root / "latest" / "meta.json")
    qc = _read_json(data_root / "latest" / "market_breadth_qc.json")
    close_data = _read_json(data_root / "stocks" / "close_series.json")
    raw_dates = close_data.get("dates", [])
    close_dates: list[str] = raw_dates if isinstance(raw_dates, list) else []
    runs = _query_runs()

    findings = evaluate(meta, qc, close_dates, runs)

    if dry_run:
        for f in findings:
            log.info(
                "[dry-run] finding=%s severity=%s remedy=%s detail=%s",
                f["kind"], f["severity"], f["remedy_workflow"], f["detail"],
            )
        return findings

    state_path = data_root / "health" / "heal_state.json"
    state = _load_state(state_path)
    active_kinds = {f["kind"] for f in findings}

    # 异常消失 → 重置该 kind 计数
    for kind in list(state.keys()):
        if kind not in active_kinds:
            del state[kind]

    now_iso = datetime.now(timezone.utc).isoformat()
    for f in findings:
        kind = f["kind"]
        entry = state.setdefault(kind, {"attempts": 0, "last_iso": None, "alerted": False})
        if entry["attempts"] < MAX_ATTEMPTS:
            _dispatch(f["remedy_workflow"])
            entry["attempts"] += 1
            entry["last_iso"] = now_iso
        elif not entry.get("alerted"):
            title = f"[etf-radar] 自愈耗尽: {kind}"
            desp = (
                f"**{kind}** (severity={f['severity']}) 补偿 {MAX_ATTEMPTS} 次仍未恢复。\n\n"
                f"- detail: {f['detail']}\n- remedy: {f['remedy_workflow']}\n- last: {entry['last_iso']}"
            )
            send_alert(title, desp)
            entry["alerted"] = True
        # else: 已 alerted，不重复推

    _save_state(state_path, state)
    return findings


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    findings = run(args.data_root, dry_run=args.dry_run)
    log.info("health_monitor 完成: %d finding(s)", len(findings))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
