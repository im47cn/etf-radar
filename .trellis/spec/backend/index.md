# 后端开发规范

etf-radar 后端：Python 数据管线（CLI + GitHub Actions cron），产出 `data/` 下 JSON 快照供前端静态消费。**无 web 服务、无数据库、无 ORM。**（唯一例外：会员订阅子系统用 Supabase，见 `membership-supabase.md`。）

---

## 规范索引

| 规范 | 说明 | 状态 |
|-------|-------------|--------|
| [目录结构](./directory-structure.md) | src/ 布局：pipeline/providers/market_breadth/output/scoring/etl | ✅ 已填 |
| [数据存储](./database-guidelines.md) | 无 DB；JSON 快照 + 原子写入 + 归档不变量 | ✅ 已填 |
| [错误处理](./error-handling.md) | Provider Chain 铁律 + 统一异常 + 失败隔离 | ✅ 已填 |
| [质量约定](./quality-guidelines.md) | ruff/mypy strict + pytest + 团队铁律 | ✅ 已填 |
| [日志约定](./logging-guidelines.md) | stdlib logging + 降级必留痕 | ✅ 已填 |
| [会员/Supabase](./membership-supabase.md) | 会员订阅（唯一例外）：DB+RLS+Edge Function；afdian query-order 验真 + 门控铁律 | ✅ 已填 |
| [健康哨兵/告警](./health-monitoring.md) | 数据可用性自愈：health-monitor 每小时巡检→计数内自动补偿→Server酱 告警；漏触发判据 | ✅ 已填 |

---

## 最重要的三条（sub-agent 必读）

1. **外部 Provider 必走 Chain**（`[Primary, Fallback...]` 逐个兜底），禁止单 provider 直调 —— `error-handling.md`。
2. **写 `data/` 必走 `atomic_write_json`**，归档必同步 reindex —— `database-guidelines.md`。
3. **mypy `strict`**：泛型带类型参数、pandas 返回值 `cast`、多余 `# type: ignore` 会被拦 —— `quality-guidelines.md`。

团队级协作约定另见 `docs/CONVENTIONS.md`（Context 恢复纪律、双审顺序、枚举语义分离等）。
