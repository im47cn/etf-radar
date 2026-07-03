# 日志约定

标准库 `logging`，无第三方日志框架。

## 模式

- 每个模块顶部：`log = logging.getLogger(__name__)`。
- CLI `main()` 里配置 handler：`logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s %(message)s')`。
- 用 `log.info/warning/error`，**不要 `print`**（管线日志进 GitHub Actions 输出）。

## 记什么（写实，本项目实际习惯）

| 级别 | 场景 | 真实示例 |
|---|---|---|
| `info` | 管线产出摘要 | `market_temperature written: %d dates, %d L1, %d L2`；`backfill done: success=%d failed=%d` |
| `warning` | 兜底/降级/数据异常，**不阻断** | provider 旧 bar 试下一源；巨潮映射覆盖率 <95%；未知二级行业归入"其他"；provider 单次 fetch 失败重试 |
| `error` | 步骤失败但主流程继续 | spot fetch 失败保留旧 indicators |

## 原则

- **降级必留痕**：任何"失败但兜底继续"的分支必须 `log.warning`，否则静默降级会被误当正常（教训：数据陈旧无护栏被静默归档）。
- 关键数值入日志：覆盖率、成功/失败计数、日期范围、偏差值——便于从 CI 日志回溯。
- 中文 message 可接受（项目习惯），但保持简洁。
