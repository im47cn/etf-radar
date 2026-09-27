# regression/ — 自挖掘日回归

借鉴 dark-factory comprehensive-test 模式：机器自己每周把全仓三层检查跑一遍，
红了自动开 issue 走工厂 triage 链，绿了记账。人类只看 issue / 合并 PR。

## 用法

```bash
bash .factory/regression/daily-regression.sh            # 真跑：失败开 issue / 全绿记 metrics
bash .factory/regression/daily-regression.sh --dry-run  # 真跑三层，只打印将开的 issue 标题与正文预览
```

定时触发：`~/Library/LaunchAgents/com.im47cn.factory.daily.plist`
（`StartCalendarInterval` Hour=3, Minute=0，每日；**加载由人类决定**：
`launchctl load ~/Library/LaunchAgents/com.im47cn.factory.daily.plist`）。
2026-08-25 周频提至日频：停摆/断档类故障（slug 回归实测 4h 静默、LaunchAgent
断档实测 13h）在周频下的发现延迟最坏 7d+，日频收至 ≤1d。

## 三层语义

| # | 层名 | 命令 | 日志 |
|---|---|---|---|
| 1 | `badcase-strict` | `python3 scripts/badcase_runner.py --strict-exact` | `artifacts/regression/<date>/<time>/badcase-strict.log` |
| 2 | `gauntlet` | `sh tools/gauntlet.sh` | `artifacts/regression/<date>/<time>/gauntlet.log` |
| 3 | `doc-freshness` | `python3 tools/check_doc_freshness.py` | `artifacts/regression/<date>/<time>/doc-freshness.log` |
| 4 | `dispatch-liveness` | `python3 .factory/regression/dispatch_liveness.py` | `artifacts/regression/<date>/<time>/dispatch-liveness.log` |

日志目录 `.factory/artifacts/regression/<YYYY-MM-DD>/<HHMMSS>/` 由脚本自建，
**每次运行独立目录、不覆盖**；`regression/latest` 符号链接始终指向最近一次
（`tail .factory/artifacts/regression/latest/gauntlet.log`）。launchd 自身
stdout/stderr 落 `.factory/artifacts/regression/launchd.log`。

## 行为契约

- **三层全部顺序执行，不短路**：任一层失败后其余层照跑——三层结果表
  完整是 triage 节点的输入，也避免"修好第一层才发现第二层也红"的两段式。
- **失败 → issue**：标题 `[factory-regression] <date> 日回归失败：<首失败层>`；
  正文 = 三层结果表 + 全部日志路径 + 首失败层日志尾部 30 行 + 复跑命令。
- **零标签（有意）**：`triage-batch.sh` 只拾取零 `factory:*` 标签的 open issue，
  `dispatch.sh` 消费 `factory:accepted`。不打标签 = 走设计的
  「写 issue → 工厂自动看见」路径：下一轮 hub kick（600s）triage 批次拾取
  → 裁决落标 → dispatch 派链修复。打 `factory:accepted` 会绕过 triage 裁决，
  打其他 `factory:*` 标签会永远不被拾取。
- **幂等路由**：已有 open 的标题含 `[factory-regression]` 的 issue 时按
  标签态路由（`factory_lib.py regression-routing`，ADR-013）：挂
  `factory:in-progress`（零改动轮留守）→ 移除该标签唤醒重派；挂
  `factory:rejected`（人工判噪音）→ 另开新 issue；其余 → 评论追加，
  不重复开；该 issue 被关闭后，下次失败重开。
- **全绿 → 记账**：追加一行
  `{"ts":…,"result":"pass","layers":{…}}` 到 `.factory/metrics/daily-regression.jsonl`。
- **`--dry-run`**：三层真实执行、日志照落，但不执行任何 gh 写操作、
  不追加 metrics（预演不产生台账）。
- **退出码**：`0` 全绿（或另一实例持锁静默退出）；`1` 有层失败（issue 已开/已评）；
  `2` 基础设施错误（无 gh / 无 slug / gh 写失败）。
- **单实例锁**：`.factory/locks/daily-regression`（mkdir 原子 + PID 活性检测，
  形态对齐 `dispatch.sh`）——防手动跑与 launchd 定时跑并发执行 gauntlet
  互踩 `.coverage` 清理。

## 设计说明

- **为什么这三层**：badcase `--strict-exact` 是发版回归级双向精确比对
  （捕获"夹具多出未声明规则"）；gauntlet 是全仓门禁唯一入口；
  doc-freshness 是陈述↔事实漂移门。三层分别覆盖「技能行为、工具链健康、
  文档诚实」三个正交面。
- **doc-freshness 与 gauntlet 的重复是有意的**：gauntlet 内已有同名子层，
  独立成第三层是为了独立日志（失败归因到单层）与独立退出码汇总。
- **日志按次保留（不覆盖）**：同日重跑各自成目录，分析收益有三——
  ① 失败证据不朽：issue 正文只带首失败层尾部 30 行，同日修复后重跑，
  失败那次的完整日志（如 gauntlet 全量 165 行）仍可追溯；
  ② issue 引用的日志路径永不失效（路径含运行戳，无人会再写它）；
  ③ 相邻两次同日运行 `diff -r` 即 flake 检测（同代码两次结果不同
  = 非确定性，比"红了又绿"的印象可靠）。磁盘成本可忽略：
  每次运行三个纯文本日志（百行级），周频 ≈ 52 目录/年，无需清理策略。
- **调度点**：`StartCalendarInterval` `Hour=3, Minute=0` = **每日凌晨
  03:00**（历史：曾为周日凌晨 Weekday=0，2026-08-25 提频；launchd 语义
  0/7=周日、1=周一，曾按规格字面取 1=周一，
  已修正为 0）。
- **launchd 环境自足**：脚本内显式注入 PATH（对齐 `cron-dispatch.sh`），
  不依赖登录 shell 环境；plist 用 `/bin/bash <绝对路径>` 调起，规避
  shebang 查找歧义。日志目录若被清空，首跑会自建，但 launchd 打开
  `launchd.log` 需目录先存在——加载前确保
  `.factory/artifacts/regression/` 存在（任何一次手动/dry-run 运行都会建好）。
