# 数据获取故障根治:陈旧护栏告警 + 个股日更韧性

## 背景 / 触发事件
2026-07-08 生产两条数据链同时陈旧,靠人工手动重跑 3 个 workflow(cn-refresh ×2、stocks-daily、stocks-history-backfill)才恢复:
- **eastmoney(akshare-em)断连风暴** → CN provider 降级 `fallback`(34 只),但 `data/latest` 仍被写入,前端显示降级/陈旧。
- **stocks-daily 07-07 被 CANCELLED**(schedule 触发、`Run daily pipeline` 步骤超时,`timeout-minutes: 10` 撞网络抖动)→ close_series 缺 07-07 → 自建宽度(市场温度)冻结在 07-06 → MA20 对账偏差 14.2 超阈,但仅打 WARNING 日志。
- **09:15 cn-refresh 定时未触发**,无人知晓。

## 确认事实(来自代码勘察,非记忆)
- `ProviderStatus` 已含 `'stale'`;`pipeline.py:482-488` 计算 `cn_stale` + `stale_minutes`;状态优先级 stale>degraded>fallback>ok(`pipeline.py:490-498`)。
- provider 链(`pipeline.py:120-140`)回退时已按 `bar_date >= expected_cn_date` 拒收旧 bar,全源皆旧时保留最新兜底。
- `archiver._assert_fresh()`(`archiver.py:17-40`)在 ARCHIVE 模式抛 `StaleDataError`,拒绝陈旧数据污染 dated 快照;pipeline 捕获后仅记 ERROR(`pipeline.py:584-586`)。
- **告警设施**:已有 Resend 发信(`notify/digest.py:441-467`,会员摘要复用)、Supabase 幂等审计(`digest_log`)。GitHub Actions 无失败通知,cn-refresh 多步 `continue-on-error: true`(静默失败根源)。
- `stocks_daily_pipeline` 为**追加模式**(`:71-105`),漏一天=永久空洞;spot 失败不抛异常、不更新 indicators(`:132-136`)。timeout 10min,仅 git push 重试 5 次,pipeline 步骤本身无重试。
- 交易日历 `etl/calendar.py:15-20`(chinese_calendar);期望日 `_expected_cn_date`(交易日 & ≥18:00 结算时)。

## 问题定性
根因不是"没有护栏",而是 **护栏只保护 dated 快照、且全部静默**:
1. **无人被告警** —— 降级/陈旧/对账超阈/漏触发全部只进日志,无主动通知。
2. **`data/latest` 无新鲜度护栏** —— 前端读的 latest 即使陈旧/降级也照写。
3. **self_breadth/市场温度无新鲜度校验** —— 盲读 close_series,静默冻结。
4. **stocks-daily 韧性弱** —— 超时紧、无步骤级重试、漏天成永久空洞、失败无告警无补偿。
5. **cron 漏触发无监控**。

## 目标 / 用户价值
让数据陈旧/获取失败**在发生时立即被发现**(告警)并尽量**自愈**,消除"靠人肉巡检 + 手动重跑三连"的运维负担。

## 需求(草案,待逐条确认)
- R1 告警:降级/陈旧/对账超阈/关键 workflow 失败时,通过既有渠道主动通知管理员。
- R2 latest 护栏:`data/latest` 写入前做新鲜度判定,陈旧时的行为需定义(拒写/标记/降级展示)。
- R3 温度链护栏:self_breadth 消费 close_series 前校验新鲜度,陈旧则告警而非静默出图。
- R4 stocks-daily 韧性:放宽/分级超时、步骤级重试、检测并自动补抓缺失交易日。
- R5 cron 漏触发监控。

## 验收标准(待细化)
- 模拟 eastmoney 全断 → 触发告警,且 latest 不被陈旧数据静默覆盖。
- 模拟 stocks-daily 漏一天 → 下次运行自动补齐或至少告警,不留永久空洞。

## Out of scope(草案)
- 更换数据源 / 引入付费行情。
- 前端告警 UI 重做。

## 已决策
- **D1 响应模式 = 全自动自愈**:失败/陈旧应自动检测→自动补偿(重跑/补抓/重算),尽量无人值守。约束:必须带重试上限、与 backfill 的并发锁,自愈耗尽后仍**响亮告警**兜底(不得回到静默盲区)。
- **D2 自愈架构 = 独立哨兵 health-monitor workflow 定时巡检**:每小时巡检 meta.json/close_series 新鲜度 + 各关键 workflow 最近 run 状态;发现陈旧/失败/漏触发 → `gh workflow run` 对应补偿并计数;集中管重试与告警。天然覆盖“cron 漏触发”。

- **D3 告警渠道 = Server酱/微信 webhook**:自愈耗尽后推微信。需新增渠道封装 + `SERVERCHAN_SENDKEY`(GitHub secret,实现时由用户配置)。哨兵 workflow 自身失败保留 GitHub 原生红叉作二级兜底。

- **D4 latest 陈旧行为 = no-regress 拒写 + 前端 banner**:后端若新数据日期 ≤ 现有 latest 则不覆盖核心行情,仅写 meta.status=stale + as_of;前端读 meta 显示“数据更新中/截至X日”提示。数据不回退,用户知情。
- **D5 任务结构 = parent + children**:本 task 作 parent(拥有需求集、子任务地图、跨子验收、集成回归);拆 4 个可独立验收的子任务。

## 子任务地图(children)
- **C1 告警渠道 + 哨兵骨架**:Server酱 webhook 渠道封装(`SERVERCHAN_SENDKEY`)+ 新增 health-monitor workflow(每小时巡检 meta/close_series 新鲜度、关键 workflow 最近 run 状态、cron 漏触发;发现异常 → `gh workflow run` 补偿 + 计数上限 + 耗尽告警)。自愈 hub。
- **C2 latest no-regress 护栏 + 前端 banner**:后端 writer 侧新鲜度/no-regress 判定(旧数据不覆盖新 latest,写 meta.status/as_of)+ 前端读 meta 展示陈旧提示。
- **C3 温度链新鲜度护栏**:`self_breadth` 消费 close_series 前校验末日是否达期望交易日,陈旧则告警/标记而非静默出图;reconcile 超阈接入告警。
- **C4 stocks-daily 韧性**:分级/放宽 timeout、pipeline 步骤级重试、检测缺失交易日并自动补抓(与 backfill 并发锁,避免 reset 冲突)。

## 需求(定稿,映射子任务)
- R1(C1)关键异常(降级/陈旧/对账超阈/workflow 失败/cron 漏触发)自动检测,自愈补偿,耗尽后 Server酱 告警。
- R2(C2)`data/latest` no-regress:旧数据不覆盖新数据,meta 准确标记陈旧,前端提示。
- R3(C3)温度/自建宽度链消费上游前校验新鲜度,陈旧不静默。
- R4(C4)stocks-daily 抗网络抖动:重试 + 不留永久空洞(自动补缺)。
- R5(C1)cron 漏触发被哨兵发现并补触发。

## 验收标准(跨子,parent 集成)
- 模拟 eastmoney 全断:provider 降级被检测 → 哨兵触发补偿;补偿耗尽 → 收到 Server酱 告警;latest 不被陈旧覆盖,前端显示陈旧 banner。
- 模拟 stocks-daily 漏一天:下次运行(或哨兵触发)自动补齐该交易日,close_series 无空洞;补失败则告警。
- 模拟 cron 未触发:哨兵在下个巡检周期发现并补触发。
- 全量后端测试通过;新增护栏/渠道/补缺均有单测。
