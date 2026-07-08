# C1 设计 · 告警渠道 + 哨兵自愈骨架

## 组件
1. `backend/src/notify/alert.py` — Server酱 渠道(薄封装)。
2. `backend/src/health_monitor.py` — 巡检 + 判定 + 补偿编排 + 告警。
3. `.github/workflows/health-monitor.yml` — cron 每小时驱动。
4. 补偿计数持久化(见下)。

## 1. Server酱 渠道 `notify/alert.py`
```
@dataclass
class AlertConfig:
    sendkey: str | None
    dry_run: bool
    @classmethod
    def from_env(cls): ...   # SERVERCHAN_SENDKEY, ALERT_DRY_RUN

def send_alert(title: str, desp: str, cfg: AlertConfig | None = None) -> bool:
    """POST https://sctapi.ftqq.com/<sendkey>.send  (data: title, desp[markdown]).
    dry_run 或无 sendkey → 打印并返回 False(不视为致命)。
    网络异常 catch 后 log.error 返回 False —— 告警失败绝不 raise。"""
```
- 复用 `requests`(digest.py 已用)。风格对齐 digest.py 的 dataclass+from_env。
- 单测:patch `requests.post` 断言 URL/payload;dry-run 不触网。

## 2. 哨兵 `health_monitor.py`
### 判定(read-only,产出 findings)
输入:`data/latest/meta.json`、`market_breadth_qc.json`、`stocks/close_series.json`,可选 `gh run list` 结果(经 CLI 传入或 env)。
```
Finding = {kind, severity, detail, remedy_workflow}
```
kind 枚举与判据:
- `cn_provider_degraded`：`meta.providers.cn.status in (degraded, stale)` → remedy=cn-refresh
- `data_stale`：`meta.stale_minutes > STALE_ALERT_MIN`(默认 120) → remedy=cn-refresh
- `reconcile_over`：`market_breadth_qc.over_threshold` 且 self.date < dapanyuntu.date → remedy=stocks-daily(补个股)+ cn-refresh(重算温度)
- `close_series_gap`：`stocks_continuity.missing_trading_days` 非空 → remedy=stocks-history-backfill
- `workflow_missed_or_failed`：关键 workflow 最近 run 超期未成功 → remedy=该 workflow

### run 状态巡检
- 用 `gh run list --workflow=<f> -L 1 --json status,conclusion,createdAt`(在 workflow 步骤里预取,或 health_monitor 内 subprocess 调 gh)。
- 判据:交易日预期时间点后仍无 success run(超 EXPECT_GRACE)→ missed/failed。
- **设计取舍**:把 gh 查询放在 **workflow 的 shell 步骤**里更简单(gh 原生可用),health_monitor.py 专注纯判定(便于单测)。故 workflow 先 `gh run list` 生成 runs.json 传给 health_monitor,或 health_monitor 内封装 `_query_runs()` 并在测试中 monkeypatch。**选后者**:内聚,单测可控。

### 漏触发判据(R1.3 补齐 — createdAt + 预期节奏)
仅"最近一条 run 成败"不够:workflow 昨天成功、今天该跑没跑时,最近 run 仍是 success → 漏检(正是"09:15 cn-refresh 没触发无人知"场景)。补 createdAt 超期判据。
- 每 workflow 配预期节奏(UTC),`evaluate` 注入 `now`(UTC,便于单测固定时间):
  - `cn-refresh`:CN 交易日 intraday(首班 01:15 UTC / 09:15 BJT,末班 07:45 UTC / 15:45 BJT)。判据 = CN 交易日且 now ≥ 01:15+grace 时,最近 success 的 createdAt 应在 `max_age_hours`(默认 3h)内,否则 missed。
  - `us-refresh`:每日 22:30 UTC(BJT 06:30)。判据 = now 距最近 success > 26h(日频+grace)→ missed。
  - `stocks-daily`:每日 08:30 UTC(16:30 BJT)。判据 = CN 交易日且 now ≥ 08:30+grace(默认 1h)时,最近 success createdAt 应 ≥ 当日 08:30 UTC,否则 missed。
  - `cn-eod-archive`:每日 10:00 UTC(18:00 BJT)。判据同 stocks-daily,deadline 10:00 UTC。
- 统一抽象:每 workflow 配 `{trading_gate: cn|us|none, earliest_utc, grace_hours, mode: intraday|daily, max_age_hours(intraday) / daily_deadline_utc(daily)}`。
- 交易日 gate 用 `is_cn_trading_day`/`is_us_trading_day`;非交易日不判 missed(避免周末误报)。
- finding kind 复用 `workflow_missed_or_failed`,detail 区分 `missed`(超期未触发)与 `failed`(最近 run 失败);remedy 均为重跑该 workflow。
- **误报防护**:漏触发补偿=重跑,首版仍走全局 dry-run 灰度;开真自愈前在真实 runs 上验不误报。

### 补偿编排 + 计数上限(防风暴)
- 状态文件 `data/health/heal_state.json`:`{kind: {attempts, last_iso}}`,随 workflow commit 持久化(轻量,复用 data-bot push)。
- 逻辑:对每个 finding,若 `attempts < MAX_ATTEMPTS`(默认 2)→ `gh workflow run remedy` + attempts++;否则 → `send_alert` 并标记 `alerted`。
- 异常消失(下轮巡检无该 finding)→ 重置该 kind 计数。
- 幂等/并发:health-monitor 自身 `concurrency: health-monitor` 防叠加;补偿目标各有并发组。

## 3. `health-monitor.yml`
```
on:
  schedule: [ cron: '5 * * * *' ]   # 每小时(可后续按交易时段加密)
  workflow_dispatch:
concurrency: { group: health-monitor }
permissions: { contents: write, actions: write }
env: { SERVERCHAN_SENDKEY, GH_TOKEN: DATA_BOT_PAT }
steps:
  - checkout / setup / uv sync
  - run: uv run python -m src.health_monitor --data-root ../data
  - commit heal_state.json(有变更才提交,带 rebase 重试)
```
- `gh workflow run` 需 GH_TOKEN=DATA_BOT_PAT(actions:write)。
- 巡检只读数据 + 写 heal_state,不碰行情文件 → 与其他 workflow 无写冲突(仅 data/health/)。

## 数据流
```
health-monitor(hourly)
  → 读 meta/qc/close_series + 查 workflow runs
  → findings
  → 每 finding: attempts<max ? gh workflow run remedy : send_alert(Server酱)
  → 写 heal_state.json
```

## 兼容 / 风险
- 误触发风暴:MAX_ATTEMPTS + 异常消失重置 + 各 remedy 并发组三重防护。
- 巡检窗口延迟:每小时粒度;可接受(数据 T+0 EOD,盘中容忍小时级)。若需更快后续加密 cron。
- Server酱 限频:每日免费额度有限 → 仅"耗尽后"告警,非每轮;同 kind 已 alerted 不重复推。
- gh 依赖:health_monitor 单测 monkeypatch `_query_runs`/`_dispatch`,不真调 gh。

## 回滚点
- alert.py / health_monitor.py / health-monitor.yml 三者独立。首版可让补偿编排走 `--dry-run`(只打印 findings 与拟触发动作,不真 dispatch/告警)灰度观察 1-2 天,再开真触发。

## 交界
- 消费 C4 的 `stocks_continuity`(缺口检测契约:exit3/missing 列表)。C4 未合入前 `close_series_gap` 判定留 TODO。
- 与 C2 共享 meta 字段语义(status/stale_minutes/cn_data_date)。
