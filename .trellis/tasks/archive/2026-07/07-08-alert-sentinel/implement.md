# C1 执行计划 · 告警渠道 + 哨兵自愈骨架

## 前置
- `task.py start 07-08-alert-sentinel`(review 后)。建议在 C4 合入后再做(复用 `stocks_continuity`);若先做,`close_series_gap` 判定留 TODO。
- 需用户在 GitHub secrets 配 `SERVERCHAN_SENDKEY`(Server酱 SendKey)。`DATA_BOT_PAT` 已有。

## 有序清单

### 步骤 1 — Server酱 渠道(TDD)
1. 测试 `backend/tests/test_notify_alert.py`:dry-run 不触网返回 False;patch `requests.post` 断言 URL 含 sendkey、data 有 title/desp;post 抛异常时 `send_alert` 返回 False 不 raise。
2. 实现 `backend/src/notify/alert.py`(AlertConfig.from_env + send_alert)。
3. 验证:`cd backend && uv run --all-extras pytest tests/test_notify_alert.py -v 2>&1 | tail -20`

### 步骤 2 — 哨兵判定(纯函数 TDD)
1. 测试 `backend/tests/test_health_monitor.py`:
   - 健康 meta → findings 空。
   - `providers.cn.status=degraded` → `cn_provider_degraded`。
   - `stale_minutes=200` → `data_stale`。
   - `qc.over_threshold=true` 且 self.date<dpyt.date → `reconcile_over`。
   - close_series 缺口 → `close_series_gap`(用 C4 的 continuity;未合入则跳过/xfail)。
2. 实现 `health_monitor.py` 判定函数 `evaluate(meta, qc, close_series, runs) -> list[Finding]`(纯函数,便于测)。
3. 验证 pytest。

### 步骤 3 — 补偿编排 + 计数
1. 测试:同一 kind 连续巡检——attempts 递增,达 MAX 后不再 dispatch、转 alert;异常消失后计数重置。monkeypatch `_dispatch`、`send_alert`、`_query_runs`。
2. 实现 heal_state 读写 + 编排 `run(data_root, dry_run)`;`--dry-run` 只打印。
3. 验证 pytest。

### 步骤 4 — workflow
1. 新增 `.github/workflows/health-monitor.yml`(见 design);首版 `--dry-run` 默认开(env 开关)。
2. YAML 自检:`python -c "import yaml; yaml.safe_load(open('.github/workflows/health-monitor.yml'))"`

### 步骤 5 — 全量回归
- `cd backend && uv run --all-extras pytest 2>&1 | tail -15`

### 步骤 6 — 灰度
- 合入后先 dry-run 跑 1-2 天,人工核对 findings 与拟触发动作正确 → 再关 dry-run 开真自愈。

## 验证命令
```shell
cd backend && uv run --all-extras pytest tests/test_notify_alert.py tests/test_health_monitor.py -v 2>&1 | tail -25
cd backend && uv run --all-extras pytest 2>&1 | tail -15
```

## 风险 / 回滚
- 三组件独立可单独 revert;dry-run 开关是主保险。
- 误告警/风暴:MAX_ATTEMPTS + 消失重置 + 并发组;先 dry-run 灰度。
- Server酱 免费限频:仅耗尽后告警、已 alerted 不重复。

## review 门
- 每步 `trellis-check`;workflow 与 dispatch 逻辑人工 review;完成后 parent 集成。

## 交界契约
- `evaluate()` 消费 C4 `stocks_continuity.missing_trading_days`;签名变更需同步。
- heal_state.json schema 属本任务私有,置于 `data/health/`。
