# C2 · latest no-regress 护栏(+ 前端截至日,可选)

> parent: `07-08-data-fetch-resilience`（D4 no-regress 拒写 + 前端 banner）

## Goal
防止**陈旧 run 用旧数据覆盖较新的 `data/latest`**(数据回退)。保证前端读到的 latest 单调不倒退。

## 确认事实(代码勘察)
- latest 由 `run_pipeline`(`pipeline.py:557-560`)**无条件** `atomic_write_json` 四文件(themes/etfs/signals/meta),无新旧比较 → 陈旧 run 可覆盖新数据。
- meta 已含 `cn_data_date`/`us_data_date`/`stale_minutes`/`providers.*.status`(`pipeline.py:477-519`)。
- archiver `_assert_fresh` 只护 **dated 快照**,不护 latest(`archiver.py:17-40`)。
- **前端 StaleBanner 已完备**(`Header/StaleBanner.tsx`):按 `stale_minutes>60`/`failed_symbols`/`fallback_symbols` 三级展示"数据获取异常/Provider降级/备用源"。→ 用户最初在生产看到的"数据获取异常"正是它如实报警。
- `cn_data_date`/`us_data_date` 前端已定义但**未使用**(`types/meta.ts:33-34`)——可选做"数据截至X日"。

## Requirements
- R2.1 **后端 no-regress 护栏**:写 latest 前比对新 meta 的 data_date 与现有 latest/meta.json;若**严格更旧**(回退)则**跳过四文件写入**,保留上一好版本;记结构化日志 `latest_write_skipped_regress`(供 C1 告警)。同日(盘中价更新)与更新则正常写。
- R2.2 **测试**覆盖:回退→跳过;同日→写;更新→写;首次(无既有 latest)→写。
- R2.3 (可选)**前端"数据截至X日"**:Header 用 `cn_data_date` 展示 as-of 日期,补足 StaleBanner 未覆盖的"正常但非今日"提示。前端 banner 主体已存在,无须重做。

## Acceptance Criteria
- [x] 单测:`should_write_latest(new_meta, existing_meta)` —— 回退 False,同日/更新/首次 True;cn 或 us 任一回退即拦。(test_no_regress.py 7 例)
- [x] 单测:回退场景 `_write_latest_guarded` 不覆盖既有四文件。(test_pipeline_write_latest_guard.py 3 例)
- [x] 回归 `uv run --all-extras pytest` 全绿。(354 passed)
- [x] R2.3 前端 `AsOfBadge` + asOfLabel,tsc 无错、Header 19 测试全绿(含与 StaleBanner 去重)。

## Out of scope
- 前端 StaleBanner 重做(已存在且工作正常)。
- 陈旧数据的告警推送(属 C1)。
- dated 快照护栏(archiver 已有)。

## 设计细化(已确认采纳,2026-07-08)
- **回退时四文件全部跳过**(保持 meta 与数据一致,不写"数据是07-06但meta说stale"的自相矛盾态),陈旧暴露交给 C1 告警 + 前端 UpdateBadge 的"更新X分钟前"自然老化。此细化取代 D4 原述"写 stale meta"。用户已确认。
