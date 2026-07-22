# 数据获取故障根治：系统设计

## 核心架构：四层防御

```
1. C4 [stocks-daily-resilience] — 防止新缺陷
   └─ 加强 pipeline 韧性：retry/timeout 分级/自动补缺 → 确保 close_series 每日连续

2. C2 [latest-noregress-guard] — 防止既有数据回退
   └─ 后端写入侧护栏：no-regress 判定 → latest 不被陈旧数据覆盖

3. C3 [温度链护栏] — 防止上游陈旧静默传导
   └─ 消费侧新鲜度校验：self_breadth/reconcile 标记陈旧 → 不静默出图

4. C1 [告警哨兵] — 发现 + 自愈
   └─ 独立 health-monitor 定时巡检：检测异常 → 自动补偿(回填/重算/重跑) → 耗尽告警
```

## 依赖与交界

### C4 ↔ C1：最上游
- **C4 产出**：close_series 连续（via 重试 + 自动补缺）、指标更新及时
- **C1 消费**：monitoring close_series 连续性、stocks-daily 任务执行状态
- **交界**：stocks_continuity 的"缺口检测" exit code=3，C1 据此触发 stocks-history-backfill

### C2 ↔ C1：latest 新鲜度防线
- **C2 产出**：latest 无陈旧覆盖、meta 准确标记 `latest_write_skipped_regress` 日志
- **C1 消费**：读 latest/meta.json 的 stale_minutes/providers.*.status、搜 `latest_write_skipped_regress` 日志 → 触发 cn-refresh 补偿
- **交界**：meta 字段与 C1 触发条件同步（stale_minutes/cn_data_date/providers.*.{status,fallback_symbols}）

### C3 ↔ C1：温度链新鲜度
- **C3 产出**：market_temperature.json 含 {stale, as_of, expected_date}、qc.json 含 {self_stale}、log 含 `temperature_stale` / `reconcile_self_stale` 前缀
- **C1 消费**：读 market_temperature.stale、qc.self_stale、搜日志前缀 → 触发 cn-refresh 重算温度与 self_breadth
- **交界**：温度陈旧的"期望交易日"定义与 C4 stocks_continuity 同源（calendar + stale_threshold）

### C1 自身：并发与上限
- health-monitor 与其它 workflow 的**并发冲突管控**：
  - backfill 中 lock 文件 → health-monitor 触发 backfill 时检查 lock，若已运行则跳过
  - cn-refresh 多次触发 → health-monitor 维护 heal_state.json 计数，同市场故障单位时间内触发数上限，避免风暴
  - stocks-daily 并发 → 无竞争（独占 slots-daily.yml 调度，不会同时 2x）

## 协议与字段

### meta.json 扩展字段（C2 + C3 依赖）
```json
{
  "cn_data_date": "2026-07-08",
  "us_data_date": "2026-07-09",
  "stale_minutes": 0,
  "providers": {
    "akshare-em": {"status": "ok|stale|degraded|fallback", "fallback_symbols": []},
    "akshare-sina": {...}
  }
}
```
- C2 用 `cn_data_date < existing` 判回退
- C3 用 `cn_data_date < expected_date` 判温度陈旧
- C1 用 stale_minutes > 60 判 **data-fetch 异常**

### market_temperature.json 扩展字段（C3 产出）
```json
{
  "dates": [...],
  "periods": {...},
  "as_of": "2026-07-08",
  "stale": false,
  "expected_date": "2026-07-08"
}
```
- 前端可忽略新字段（后向兼容）
- C1 读 stale=true 时触发 cn-refresh

### qc.json 扩展字段（C3 产出）
```json
{
  "self_stale": false,
  "over_threshold": false
}
```
- self_stale 单独标记"as-of 真陈旧" vs "方法学微差"

### 结构化日志前缀（C1 消费）
| 前缀 | 来源 | 含义 | 触发补偿 |
|------|------|------|---------|
| `latest_write_skipped_regress` | C2 | latest 无新数据（拒写） | cn-refresh 重算全部 |
| `temperature_stale` | C3 | close_series 陈旧 | stocks-daily retry + backfill |
| `reconcile_self_stale` | C3 | MA20 as-of 落后 dapanyuntu | cn-refresh 重算温度 |
| `stocks_continuity_gap` | C4 | close_series 缺日 | 自动补抓或告警 |

## 可选优化：前端 AsOfBadge（C2 + C3 协作）
- 若 C2 与 C3 都完成，前端 Header 可展示 `cn_data_date` 与 as_of，提示用户数据最新程度
- **非必需**（C1 告警已够机制），但改善 UX
- 独立于后端护栏，可拆为单独收尾 PR

## 回滚点 & 独立性

| 子任务 | 依赖 | 回滚成本 | 备注 |
|--------|------|--------|------|
| C4 | 无 | 低 | workflow yml 改动 + stocks_continuity.py 新增；revert 即恢复无重试 |
| C2 | 无 | 低 | no_regress.py 新增 + pipeline 接入；revert 接入即恢复无条件写 |
| C3 | 无 | 低 | self_breadth + reconcile 改动；新增字段向后兼容，前端可忽略 |
| C1 | C2/C3 消费字段 | 中 | health-monitor.yml 新增 + alert.py 新增；依赖 C2/C3 的 meta/日志，若后者未合入则告警不准 |

**并行度**：C4 + C2 + C3 可完全并行（改不同文件）；C1 需等 C2/C3 完成字段产出（代码可并行，测试需字段），建议最后集成。

## 风险评估

### 高危
- **C4 自动补缺逻辑错误** → close_series 反复补填同一天 → git history 污染、数据多算 → 规避：stocks_continuity 严格检查 gap 边界，补缺前验证新数据日期 >= gap 末日 + 1
- **C1 并发风暴** → health-monitor 反复触发 backfill/cn-refresh，相互冲突 → 规避：heal_state.json 计数上限，单市场故障 6h 内最多 3 次触发

### 中危
- **C2 保守拦截** → 单市场回退但另市场新数据时也跳过 → 接受风险（宁可保留上一好版本）
- **C3 陈旧信号误报** → 盘中/非交易日被误判为陈旧 → 规避：expected_date 放宽为上一交易日

### 低危
- **新增 JSON 字段前端不兼容** → 前端 zod strict 报错 → 规避：C3 实现时验证，字段必须可选
- **日志前缀格式变动** → C1 正则搜索失效 → 规避：约定固定前缀，写一次文档

## 推送策略 & 灰度

1. **C4 + C2 + C3**（后端护栏）**→ uv run pytest 全绿 → merge main**
2. **C1 部署**（告警哨兵）→ **灰度**：
   - 第一阶段（1-2 天）：health-monitor 定时巡检，告警 dry-run（仅 log，不真触发补偿）
   - 第二阶段：启用自动补偿（dispatch），但保留上限 + 告警兜底
   - 配置环节：`SERVERCHAN_SENDKEY` 由用户手动写入 GitHub secrets，C1 里 default=空字符串（dry-run 模式）
3. **前端 AsOfBadge**（可选）→ 单独 PR，依赖 C2 已合

## 交界合同（跨子任务通信）
- **meta 字段**：C2/C3 产出 → C1 消费，schema 变更需通知 C1
- **日志前缀**：固定格式，C1 搜索模式需在 health_monitor.py 写死
- **时间口径**：calendar.is_cn_trading_day 为单一真源，C3/C4 都用它判期望日
- **git push 顺序**：C4/C2/C3 无依赖可并行；C1 需等前三者合并后再推（以消费其输出）
