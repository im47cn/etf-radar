# Journal - im47cn (Part 1)

> AI development session journal
> Started: 2026-06-30

---



## Session 1: 温度页统一色阶+图例primitive+a11y纹理

**Date**: 2026-07-03
**Task**: 温度页统一色阶+图例primitive+a11y纹理
**Branch**: `main`

### Summary

温度页色阶收敛为 TIERS 单一真源(消除连续/离散双真源漂移); 新建页面级共享 BreadthLegend primitive; 三图+温度计叠四方向(/—|\)per-tier纹理满足去色/色觉障碍可辨; 测试121->126; spec 沉淀色阶单一真源+不只靠颜色两条前端约定. 遗留: 冰点档纹理对比度未做人眼核验(spec 已记 gotcha).

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `53be8d5` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 2: 市场温度: 自建个股多周期(MA20/60/120)宽度 + 全套UI迭代

**Date**: 2026-07-03
**Task**: 市场温度: 自建个股多周期(MA20/60/120)宽度 + 全套UI迭代
**Branch**: `main`

### Summary

市场温度从 dapanyuntu 单MA20升级为自建个股级多周期(MA20/60/120)宽度: 巨潮门类(11)/大类(86)分类, 全市场真个股占比, dapanyuntu降为QC对账. 本地8-worker backfill补150天历史使MA120落地. 前端: 全局周期切换+行业排行折叠树(子行业min-max区间须)+热力图(折叠/正方格/竖排日期)+温度计逐日4档色带. 附带CN旧bar根治(旧bar视同失败试下一源)+CI加固. 全部上线生产 im47.cn/etf-radar.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `e308f85` | (see git log) |
| `5e54eea` | (see git log) |
| `b9782bd` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 3: 会员订阅 MVP(爱发电订阅闭环+自选盯盘)

**Date**: 2026-07-04
**Task**: 07-03-membership-subscription-mvp
**Branch**: `main`

### Summary

真实变现方向: 定位「活跃散户 × 效率/全景/沉淀」,合规上只卖工具与信息不荐股(全站文案禁操作动词+免责声明). 收款用爱发电(afdian)做 MVP(免营业执照/免备案),跑通后再迁微信官方支付. 纯 serverless: 复用现有 Supabase OAuth, 新增 subscriptions/bind_codes/watchlist/webhook_events 四表+RLS+两个 SECURITY DEFINER RPC(issue_bind_code/add_watchlist). 阶段 1/2/4(数据层+前端hook+UI)一次实现,阶段 3(afdian-webhook Edge Function)后补. 定价 ¥6/月·¥58/年.

### 关键技术决策 / 踩坑

- **afdian webhook 无 sign 字段**: 首版误做「对 payload 验签」,查证官方规范后重写为「拿 out_trade_no 反向调 query-order API 核实订单真实且 status=2,以返回订单为权威源防伪造」. sign 规则 md5(token+"params"{params}"ts"{ts}"user_id"{uid}) 小写. 用官方已知答案向量断言避免自证.
- **会员门控铁律**: subscriptions 无 authenticated 写策略(状态不可前端伪造); 「仅会员可写」由 add_watchlist RPC 服务端硬校验; webhook_events 对 authenticated 完全不可见; 到期回落零后台(useSubscription 前端判 periodEnd>now).
- **SUPABASE_URL/SERVICE_ROLE_KEY** Edge Function 自动注入,禁手动 secrets set.
- 绑定码方案(留言填码打通 afdian↔supabase)有 UX 摩擦,是 MVP 已知权衡; 二期迁官方支付消除.

### Git Commits

| Hash | Message |
|------|---------|
| `ea82c66` | feat(membership): 数据层+前端hook+UI(阶段1/2/4) |
| `218e43e` | feat(membership): afdian-webhook Edge Function(阶段3) |

### Testing

- [OK] 前端 445 passed, 后端 262 passed, Edge Function deno test 16 passed, tsc/lint 干净

### Status

[OK] **代码完成并推送 main**; 部署待人工(SQL Editor 执行 003 迁移 + supabase secrets/deploy + afdian 回调 URL + 真实订单端到端联调 + 轮换泄漏 token)

### Next Steps

- 部署上线(见 spec/backend/membership-supabase.md Runbook)
- 二期: 邮件变化摘要推送(Resend+pg_cron)、全量历史回看+导出、微信官方支付迁移、年费独立方案


## Session 3: 数据获取故障根治: 止血三连 + C1哨兵/C4韧性落地

**Date**: 2026-07-08
**Task**: 数据获取故障根治: 止血三连 + C1哨兵/C4韧性落地
**Branch**: `feat/data-fetch-resilience`

### Summary

生产数据链陈旧排查: eastmoney断连+stocks-daily被CANCELLED+09:15cron漏触发三者叠加, 手动重跑cn-refresh/stocks-daily/backfill止血并补齐07-07空洞。根治规划为parent(data-fetch-resilience)+4子任务; C4(个股日更韧性+自动补缺)已完成, C1(health-monitor哨兵+Server酱告警+自愈编排,含漏触发判据)本会话实现+双审(344 passed)+update-spec(health-monitoring.md)并提交。C2/C3仍待实现。分支feat/data-fetch-resilience未推送。

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `b656d8f` | (see git log) |
| `60513fe` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 4: C2 latest no-regress 护栏 + 前端数据截至日

**Date**: 2026-07-08
**Task**: C2 latest no-regress 护栏 + 前端数据截至日
**Branch**: `feat/data-fetch-resilience`

### Summary

实现 latest no-regress 护栏(should_write_latest + _write_latest_guarded 回退整体跳过 + latest_write_skipped_regress 日志供C1消费)与前端 AsOfBadge(数据截至X日,与StaleBanner去重)。10后端+3前端新测,全量354 passed;trellis-check通过(自修去重);spec 增latest单调不倒退不变量。已提交推送并归档。根治进度 C1/C2/C4 完成,C3待做。

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `7135bdc` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 5: 修前端 e2e portfolio.spec 陈旧断言 + 连带修 C2 AsOfBadge lint

**Date**: 2026-07-08
**Task**: 修前端 e2e portfolio.spec 陈旧断言 + 连带修 C2 AsOfBadge lint
**Branch**: `feat/data-fetch-resilience`

### Summary

e2e portfolio.spec 两用例长期 red: 根因是导航标签早前缩短(我的持仓→持仓/主题轮动→轮动, 修移动端换行)但 e2e 未跟上, systematic-debugging 本地复现定位后更新断言+exact:true。推送时发现并行会话在同分支提交的 C2 AsOfBadge.tsx 触发 react-refresh/only-export-components 打挂 frontend job, 拆 asOfLabel 到独立文件修复。PR#25 五项 CI 全 SUCCESS(含 C1/C4/C2/e2e)。

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `37d89f9` | (see git log) |
| `5bb353e` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 6: C3 温度链新鲜度护栏实现+审查修正

**Date**: 2026-07-09
**Task**: C3 温度链新鲜度护栏实现+审查修正
**Branch**: `main`

### Summary

实现 C3: self_breadth 输出 as_of/stale/expected_date + reconcile self_stale, 供 health-monitor(C1) 消费; 独立审查修正 M1(run 补 now_bjt)/M2(回溯21天+兜底防长假误报)/M3(date 解析比较); 后端369+前端448 passed; 新增 spec market-breadth.md。附: 排查生产数据获取异常(eastmoney断连+stocks-daily漏07-07), 手动重跑 cn-refresh/stocks-daily/backfill 止血恢复。

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `0f89d00` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 7: 会员变化摘要邮件推送(二期) + MVP上线联调

**Date**: 2026-07-07
**Task**: 07-07-membership-change-digest（+ 07-03-membership-subscription-mvp 联调）
**Branch**: `main`

### Summary

先完成会员订阅 MVP 上线联调: afdian-webhook 部署踩坑连环(占位函数非本函数→重部署; 域名 afdian.net→afdian.com 边缘DNS; ping须loadEnv前放行; token轮换须同步secret否则ec=400005; 测试推送用文档假单号). 加支付失败告警(Server酱)+富文本+一键重试(HMAC签名GET端点,仍走完整核实)+Supabase跳转; 用Management API清理测试数据. 然后头脑风暴二期定为「自选+每日变化摘要邮件」留存引擎,建Trellis任务全流程(research→6阶段实现→双审)完成。

### 关键技术决策 / 踩坑

- **二期触发集 A+C+D**: B(宽度跨档)经research剔除——theme/ETF无宽度维度、无theme→行业映射(tags与巨潮门类对齐<10%)。
- **温度4档30/50/70**: 前端breadthColor.ts真源, Python changes.py同值移植+单测钉死边界防漂移。
- **幂等铁律**: 发信前必须先查digest_log(run_date,user_id), UNIQUE只挡审计重复挡不住重发→会破prd「每天最多1封」。
- **latest_market_rate按最大date取值**(非series[-1]), 防乱序误报C(全员广播)。
- **零新依赖**: urllib自封SupabaseRest; 邮箱走Supabase Auth Admin REST(service_role可读,无需profiles)。
- afdian webhook 无sign→反向调query-order核实(见Session3); 域名必须afdian.com。

### Git Commits

| Hash | Message |
|------|---------|
| `c0e56a9` | feat(notify): 数据层+变化计算(阶段2/3) |
| `423ecc8` | feat(notify): 发信编排+退订Function(阶段4/5) |
| `ac13176` | feat(notify): EOD workflow编排(阶段6) |

### Testing

- [OK] 后端 304 passed, notify-unsub deno 7 passed, ruff/mypy strict 干净; MVP afdian-webhook 23 passed

### Status

[OK] **二期代码6阶段全完成推送main + 双trellis-check通过**; 联调待人工(Resend域名+迁移004+secrets, 见 docs/membership-digest-deployment.md); MVP已部署,待首笔真实订单验证

### Next Steps

- 二期联调: 见 docs/membership-digest-deployment.md 准备清单
- MVP: 下第一笔真实¥6订单验证activated


## Session 7: data workflow 提交步骤防hang护栏

**Date**: 2026-07-12
**Task**: data workflow 提交步骤防hang护栏
**Branch**: `main`

### Summary

排查 07-11 cn-eod-archive 提交步骤 pull --rebase 遇冲突静默挂起 22min 被取消的故障。抽 .github/actions/commit-and-push composite action(GIT_TERMINAL_PROMPT=0 + pull --rebase --autostash origin main + 有界重试含 rebase --abort 清理 + changed 输出),7 个 data workflow 归并复用+补 timeout-minutes;backfill 保留 reset-hard 覆盖策略仅加护栏。冲突从'无限 hang'变为'~60s 有界失败'。trellis-check 8/8 + actionlint/shellcheck 通过;holdings-refresh 分支冒烟实证护栏行为。spec 补 commit-and-push 契约。

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `1284a0c` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 8: health-monitor 提交步骤归并 commit-and-push

**Date**: 2026-07-12
**Task**: health-monitor 提交步骤归并 commit-and-push
**Branch**: `main`

### Summary

收口最后一个未归并的 data-commit workflow: health-monitor.yml 的 Commit heal_state 删内联 5 次 pull --rebase 重试循环, 改用 commit-and-push action(带 GIT_TERMINAL_PROMPT=0 防hang护栏)。token 注入(persist-credentials:false 需 git remote set-url DATA_BOT_PAT)保留为前置 step, dry-run 门控/timeout:15 不变, user 传 data-bot。全仓已无裸 pull --rebase(除 backfill reset-hard)。YAML+actionlint 通过。

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `e89ed8e` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete
