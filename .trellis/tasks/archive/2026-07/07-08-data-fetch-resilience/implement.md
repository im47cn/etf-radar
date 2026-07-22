# 数据获取故障根治：执行计划

> parent task：数据获取故障根治(stale/degraded/gap)  
> 子任务执行分配：可 4 个并行实现 → 集成验收 → 灰度上线

## 总体流程

```
Phase 1: 子任务设计完成 + 审阅(当前)
  ↓
Phase 2: 并行实现 4 个子任务
  └─ C4(stocks-daily-resilience) + C2(latest-noregress) + C3(温度链) 可 3 并行
  └─ C1(alert-sentinel) 串行等前三者字段产出
  ↓
Phase 3: 集成验收
  ├─ 后端全量 pytest
  ├─ 模拟场景测试
  └─ 前端 typecheck/vite build
  ↓
Phase 4: 灰度 + 上线
  ├─ C4/C2/C3 直接 merge→main
  ├─ C1 灰度 2 阶段(dry-run→enable)
```

## 子任务分配(Phase 2 实现)

### 并行轨道 1：C4 · stocks-daily-resilience
**Owner: 分配 trellis-implement**  
**任务: ./07-08-stocks-daily-resilience**

- 依赖：无
- 关键：stocks_continuity 缺口检测、workflow timeout 升级、step-level retry
- 里程碑：
  1. TDD: tests/test_stocks_continuity.py (缺日检测、gap 边界、exit 3)
  2. 实现 src/stocks_continuity.py + 接入 pipeline.py
  3. 升级 .github/workflows/stocks-daily.yml (timeout 10→25min, 4 次 retry)
  4. pytest 全绿 + 手工验证 workflow 执行
- 交付物：close_series 连续 + stocks_continuity exit code
- 预计工期：1.5-2h

### 并行轨道 2：C2 · latest-noregress-guard
**Owner: 分配 trellis-implement**  
**任务: ./07-08-latest-noregress-guard**

- 依赖：无
- 关键：should_write_latest 判定、pipeline 接入、no-regress 日志
- 里程碑：
  1. TDD: tests/test_no_regress.py (首次/同日/回退/新增/缺字段各例)
  2. 实现 src/output/no_regress.py::should_write_latest
  3. 接入 pipeline.py:557-560 写入侧 + latest_write_skipped_regress 日志
  4. pytest 全绿
  5. (可选) 前端 AsOfBadge 组件（非阻断，可拆为收尾 PR）
- 交付物：latest 不回退 + skip 日志
- 预计工期：1-1.5h(核心) + 0.5h(前端可选)

### 并行轨道 3：C3 · temperature-freshness-guard
**Owner: 分配 trellis-implement**  
**任务: ./07-08-temperature-freshness-guard**

- 依赖：无
- 关键：_freshness 纯函数、market_temperature/qc 字段扩展、日志前缀
- 里程碑：
  1. TDD: tests/test_self_breadth.py (陈旧/正常/盘中各例)
  2. 实现 market_breadth/self_breadth.py::_freshness + run 陈旧 log
  3. 增强 market_breadth/reconcile.py::reconcile 的 self_stale 判定
  4. 前端 typecheck 验证（market_temperature.json zod schema 向后兼容）
  5. pytest 全绿
- 交付物：市场温度标记陈旧 + qc 判 self_stale
- 预计工期：1.5-2h

### 串行轨道 4：C1 · alert-sentinel
**Owner: 分配 trellis-implement**  
**任务: ./07-08-alert-sentinel**  
**前置：等 C2/C3 合并，消费其 meta 字段与日志**

- 依赖：C2/C3 字段产出、SERVERCHAN_SENDKEY 环境变量
- 关键：alert.py(Server酱 wrapper)、health_monitor.py(6 finding 类型 + heal_state 计数)、health-monitor.yml(hourly cron)
- 里程碑：
  1. TDD: tests/test_alert.py (sendkey parse、dry-run behavior)
  2. TDD: tests/test_health_monitor.py (6 finding 类型、计数逻辑、dispatch 限制)
  3. 实现 src/notify/alert.py + src/health_monitor.py
  4. 新增 .github/workflows/health-monitor.yml (hourly cron，env HEALTH_DRY_RUN=1 默认)
  5. pytest 全绿 + workflow 语法验证
  6. 配置 GitHub secrets SERVERCHAN_SENDKEY (用户手工)
- 交付物：heuristic 告警 + health-monitor cron + dry-run 灰度
- 预计工期：2-2.5h

## 集成验收(Phase 3)

### 3.1 后端全量回归
```bash
cd /Users/dreambt/sources/etf-radar/backend && uv run --all-extras pytest 2>&1 | tail -20
```
预期：354 passed (含新增子任务测试)

### 3.2 前端类型校验 & 构建
```bash
cd /Users/dreambt/sources/etf-radar/frontend && npm run typecheck
cd /Users/dreambt/sources/etf-radar/frontend && npm run build 2>&1 | tail -20
```
预期：无 TypeScript 错误、vite 构建成功

### 3.3 模拟场景测试

#### 场景 A：provider 降级 → 告警
1. 手工修改 tests/test_pipeline_compute_outputs.py：mock akshare-em 返回 `None` 触发 fallback
2. 运行 `uv run -m src.pipeline --mode=full` 产出 meta with `providers.akshare-em.status=degraded`
3. 检查 C1 health-monitor 日志搜索 `cn_provider_degraded` → 应触发补偿日志

#### 场景 B：close_series 缺日 → 补缺
1. 手工删除 data/stocks/close_series.json 中某日数据
2. 运行 C4 stocks_continuity(或触发 stocks-daily 后的 detect-gaps 步骤)
3. 检查 exit code=3 且日志含 `gap detected`
4. 验证补缺流程能被 C1 捕获

#### 场景 C：latest 回退 → 跳过写入
1. 初始 data/latest/meta.json cn_data_date=07-08
2. 产出陈旧数据 cn_data_date=07-07，再跑 pipeline --mode=intraday
3. 验证 C2 日志含 `latest_write_skipped_regress` + latest 四文件未变

#### 场景 D：温度陈旧 → 标记
1. 手工修改 close_series dates 末日为过期日期
2. 运行 market_breadth/self_breadth.py
3. 检查输出 market_temperature.json stale=true + 日志含 `temperature_stale`

### 3.4 git commit 与 git diff 审查
```bash
cd /Users/dreambt/sources/etf-radar
git status --short  # 确认修改范围
git diff --stat     # 统计变更
```

## 上线步骤(Phase 4)

### 4.1 后端护栏合并(C4 + C2 + C3)
```bash
# 各子任务合入 PR 或直接 commit
git add backend/src/stocks_continuity.py backend/src/output/no_regress.py backend/src/market_breadth/*.py backend/tests/test_*.py .github/workflows/stocks-daily.yml
git commit -m "data-fetch-resilience: stocks-daily retry + latest no-regress + temperature freshness guard"
git push origin main
```

### 4.2 前端可选 AsOfBadge(如完成)
```bash
git add frontend/src/components/Header/AsOfBadge.tsx frontend/src/components/Header/index.tsx
git commit -m "frontend: add AsOf data date badge (optional)"
git push origin main
```

### 4.3 C1 灰度部署(分阶段)

#### 第一阶段(1-2 天)：dry-run 模式
1. 用户配置 GitHub secrets `SERVERCHAN_SENDKEY` (或留空跳过微信通知)
2. 手工 merge C1 的 PR
3. health-monitor.yml 默认 `HEALTH_DRY_RUN=1`(仅检测+日志，不执行补偿)
4. 观察 health-monitor 日志，确认 6 finding 类型识别准确

#### 第二阶段：启用补偿
1. 在仓库 Variables 设 `SELF_HEAL_DISPATCH=1`(现有 stocks-daily 模式已用此开关)
2. health-monitor 开始真实触发 backfill/cn-refresh
3. 保持告警兜底(SERVERCHAN_SENDKEY 需配)
4. 运行 1 周观察无误后确认稳定

### 4.4 验证上线
```bash
# 观察 data/latest/meta.json 是否有以下迹象(72h 采样):
# 1. cn_data_date 单调不倒退
# 2. stale_minutes ≤ 60min(无长期陈旧)
# 3. providers.*.status 无过久 degraded
# 前端 StaleBanner 与温度页是否按预期展示陈旧警告
```

## 风险 & 回滚

### C4 回滚
```bash
git revert <C4-commit>  # 移除 stocks_continuity + retry 逻辑
# 恢复：无重试、无自动补缺、gap 需人肉补
```

### C2 回滚
```bash
git revert <C2-commit>  # 移除 no-regress 判定，恢复无条件写
# 恢复：latest 可被陈旧覆盖(原态)
```

### C3 回滚
```bash
git revert <C3-commit>  # 移除新增字段与陈旧日志
# 恢复：市场温度静默冻结
```

### C1 回滚
```bash
git revert <C1-commit>  # 删除 health-monitor.yml 与 alert.py
# 恢复：无定时巡检、无自动补偿、无微信告警
# 保留：C4/C2/C3 已生效，至少有静默护栏
```

## review 门

### 设计阶段(current)
- [ ] 用户审阅 parent prd/design/implement + 4 个 child prd/design/implement
- [ ] 确认 D1-D5 决策(自愈模式/告警渠道/latest 行为/任务结构)
- [ ] 确认 4 子任务交界与回滚可接受

### 实现完成后
- [ ] C4/C2/C3 各 trellis-check 通过
- [ ] C1 在 C2/C3 merge 后 trellis-check
- [ ] 集成场景 A-D 验收通过
- [ ] 后端全量 pytest + 前端 build 通过
- [ ] 由 repo 管理员最终 approve + merge

### 上线后(运维检查表)
- [ ] 3 天内未见因护栏新增的告警风暴
- [ ] close_series 连续无缺日
- [ ] latest 无陈旧覆盖现象(git diff 无逆向)
- [ ] 温度图/宽度正常更新

## 预计总工期

| 阶段 | 工时 | 备注 |
|------|------|------|
| Phase 2(并行实现) | 2h(C4) + 1.5h(C2) + 2h(C3) + 2.5h(C1) | 墙上时间 ~2.5h(3 并行 + 1 串行) |
| Phase 3(验收) | 1h | 场景测试 + pytest |
| Phase 4(上线) | 0.5h | 灰度推送需 2-3 天观察 |
| **总计** | **~10h** | **墙上时间 ~3-4h 并行** |

## 关键截止日期

- **2026-07-09 EOD**：设计评审 + 确认启动
- **2026-07-10 EOD**：4 子任务实现完成
- **2026-07-11**：集成验收
- **2026-07-12**：merge C4/C2/C3，C1 dry-run 上线
- **2026-07-19**：C1 启用补偿(若 dry-run 无异常)
