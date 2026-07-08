# 数据健康哨兵 + 告警(health-monitor)

数据可用性自愈子系统:独立 workflow 每小时巡检数据新鲜度与关键 workflow 运行状态,发现异常→计数上限内自动触发补偿→耗尽后经 Server酱 推微信告警。解决"上游抽风/cron 漏触发导致数据陈旧、靠人肉巡检重跑"的运维负担。

> 背景:2026-07-08 eastmoney 断连 + stocks-daily 被 CANCELLED + 09:15 cron 漏触发,三者叠加致生产陈旧,全靠人工重跑三个 workflow 才恢复。本子系统把该恢复流程自动化。

---

## 1. Scope / Trigger
- 触发 code-spec 深度:新后端子系统 + 新 env 接线(`SERVERCHAN_SENDKEY`)+ 新 workflow(`health-monitor.yml`)+ 跨 workflow 编排(`gh workflow run`)。
- 组成:`src/health_monitor.py`(巡检+判定+编排)、`src/notify/alert.py`(Server酱渠道)、`.github/workflows/health-monitor.yml`(每小时驱动)。

## 2. Signatures
```python
# src/notify/alert.py
@dataclass
class AlertConfig:
    sendkey: str | None
    dry_run: bool
    @classmethod
    def from_env(cls) -> AlertConfig: ...        # SERVERCHAN_SENDKEY, ALERT_DRY_RUN
def send_alert(title: str, desp: str, cfg: AlertConfig | None = None) -> bool
    # POST https://sctapi.ftqq.com/<sendkey>.send (data: title, desp)
    # dry-run/无 key/网络异常/非 200 → 返回 False, 绝不 raise

# src/health_monitor.py
def evaluate(meta: dict, qc: dict, close_series_dates: list[str],
             runs: dict[str, dict | None], now: datetime | None = None) -> list[Finding]
def run(data_root: Path, dry_run: bool) -> None      # 读数据+查runs → 编排补偿/告警
# CLI: python -m src.health_monitor --data-root ../data [--dry-run]
```
- `Finding = {kind, severity, detail, remedy_workflow}`。
- `now` 可注入(UTC),用于漏触发时间判定单测固定时钟。

## 3. Contracts

### Finding 判据(kind → 触发条件 → remedy)
| kind | 触发条件 | remedy_workflow |
|---|---|---|
| `cn_provider_degraded` | `meta.providers.cn.status ∈ {degraded, stale}` | cn-refresh |
| `data_stale` | `meta.stale_minutes > 120` | cn-refresh |
| `reconcile_over` | `qc.over_threshold` **且** `qc.self.date < qc.dapanyuntu.date` | stocks-daily |
| `close_series_gap` | `stocks_continuity.missing_trading_days(dates)` 非空 | stocks-history-backfill |
| `workflow_missed_or_failed` | 见「漏触发判据」 | 该 workflow 自身 |

### 漏触发判据(createdAt + 预期节奏)
每 workflow 配 `WorkflowSchedule{trading_gate, earliest_utc, grace_hours, mode, max_age_hours|daily_deadline_utc, latest_utc?}`:
| workflow | gate | 判据 |
|---|---|---|
| cn-refresh | cn | intraday;活跃窗口 `[earliest+grace, latest_utc(07:45)+grace]` 内、最近 success 距 now > 3h → missed;窗口外(收盘后/开盘前)**不判** |
| us-refresh | us | 距最近 success > 26h → missed |
| stocks-daily | cn | daily;now ≥ 08:30+grace 且最近 success < 当日 08:30 → missed |
| cn-eod-archive | cn | daily;deadline 10:00 UTC,同上 |
- 交易日 gate(`is_cn/us_trading_day`)为假 → 不判(周末/假期不误报)。
- 存在 success run 但 createdAt 无法解析 → 保守**不判 missed**(仅 log);无任何 qualifying run → 判 missed。
- detail 区分 `missed`(超期/漏触发)/`failed`(最近 run 完成但非 success);`in_progress`(未完成、conclusion=None)→ 跳过不误判。

### 补偿编排 + 防风暴
- 状态 `data/health/heal_state.json`:`{kind: {attempts, last_iso, alerted?}}`,随 workflow commit 持久化。
- `attempts < MAX_ATTEMPTS(2)` → `gh workflow run remedy` + attempts++;达上限 → `send_alert` 并置 `alerted`(不重复推);异常消失(不在本轮 findings)→ 删除该 kind 计数重置。
- 目标 workflow 各有并发组(backfill=stocks-history-backfill 等)防叠加。

### 环境 / 权限
| key | 必需 | 用途 |
|---|---|---|
| `SERVERCHAN_SENDKEY` | 是(真告警) | Server酱 SendKey;缺则 send_alert 返回 False |
| `ALERT_DRY_RUN` / `HEALTH_DRY_RUN` | 否 | 灰度:只打印不 dispatch/告警;首版默认开 |
| `GH_TOKEN`(=`DATA_BOT_PAT`) | 是 | `gh workflow run` 需 actions:write |
- workflow permissions:`contents: write`(提交 heal_state)+ `actions: write`。concurrency group `health-monitor`。

## 4. Validation & Error Matrix
| 条件 | 行为 |
|---|---|
| meta/qc/heal_state JSON 损坏或缺字段 | 容错:按缺失/空态处理 + log.warning,不崩溃 |
| Server酱 网络异常 / 非 200 / 无 key | send_alert 返回 False,不 raise(告警失败不得拖垮巡检) |
| workflow 正在运行(conclusion=None 未完成) | 跳过,不判 missed(防每小时撞正常执行) |
| createdAt 缺失/格式异常但有 success run | 保守不判 missed |
| 非交易日 | 不判 workflow missed |

## 5. Good/Base/Bad Cases
- Good:健康 meta + 各 workflow 当日已成功 → findings 空,不动作。
- Base:cn provider degraded 首现 → dispatch cn-refresh,attempts=1;下轮仍在 → attempts=2;第三轮仍在 → 告警。
- Bad(防回归):CN 交易日收盘后 now=10:00 UTC、cn-refresh 最近 success=当日 07:40 → **不判 missed**(否则每晚误报重跑)。

## 6. Tests Required(assertion points)
- `test_notify_alert.py`:dry-run 不触网返回 False;monkeypatch `requests.post` 断言 URL 含 sendkey + payload{title,desp};post 抛异常 → 返回 False 不 raise。
- `test_health_monitor.py`:各 kind 命中/健康不命中;计数达上限转告警 + 异常消失重置(monkeypatch `_dispatch`/`send_alert`/`_query_runs`);漏触发窗口内/收盘后/开盘前/周末/createdAt 缺失/in_progress/损坏 JSON 边界。

## 7. Wrong vs Correct
### Wrong
```python
# 只看最近 run 成败 → 漏检"今天该跑没跑"(09:15 cron 没触发,最近 run 仍是昨天 success)
if run and run["conclusion"] != "success":
    findings.append(missed)
# 且:intraday 无末班上界 → 收盘后最近 success 必 >3h → 每晚误报
```
### Correct
```python
# 交易日 gate + earliest/latest 活跃窗口 + createdAt 时效, 注入 now 可测
if _trading_gate_open(sched.trading_gate, now.date()) and _in_active_window(sched, now):
    if _is_missed(sched, run, now, run_present=run is not None):
        findings.append(Finding("workflow_missed_or_failed", ..., detail, remedy=wf))
```

---

## 部署 / 灰度
1. GitHub secrets 配 `SERVERCHAN_SENDKEY`(`DATA_BOT_PAT` 已有)。
2. 首版 `HEALTH_DRY_RUN=1`:定时只打印 findings 与拟触发动作。灰度 1-2 天核对无误报后,改默认 `0` 开真自愈。

## 交界
- 复用 `src/stocks_continuity.py::missing_trading_days`(C4)判缺口。
- 消费字段语义(`meta.providers/stale_minutes/cn_data_date`、`qc.over_threshold/self_stale`)与 C2/C3 共享。
