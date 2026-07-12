# 数据存储约定（无数据库）

**本项目没有数据库、没有 ORM。** 所有状态是 `data/` 下的 JSON 快照，随 git 提交、由 GitHub Pages 静态托管、前端直接 fetch。写实：把"数据库约定"理解为"快照文件约定"。

## 数据布局（`data/`）

| 路径 | 内容 |
|---|---|
| `data/latest/*.json` | 最新快照（`themes.json`, `etfs.json`, `signals.json`, `meta.json`, `market_temperature.json`, `snapshots-index.json` …）。前端主读这里。 |
| `data/snapshots/<YYYY-MM-DD>/` | 每日 EOD 归档（`archiver.py` 从 latest 复制）。前端"时光机"读这里。 |
| `data/stocks/` | 个股矩阵（`close_series.json` 全市场收盘、`volume_series.json`、`stock_industry_map.json`、`ohlc/<code>.json`）。大文件。 |
| `config/*.yaml` | 主题/ETF 配置输入（非产出）。 |

## 铁律

- **原子写入**：所有快照写入必须走 `output/writer.py::atomic_write_json`（先写 `.tmp` 再 `os.replace`），失败不污染原文件。禁止直接 `open(...,'w')+json.dump` 写 `data/`。
- **归档白名单**：`output/archiver.py` 的 `FILES` 列表控制哪些 latest 文件被归档进 snapshots。新增需归档的快照要加进该列表。
- **归档不变量**：任何对 `data/snapshots/` 的修改必须同步重建 `latest/snapshots-index.json`（`archive_latest` 内部已内化 `write_snapshots_index`，别在外面手动组合，历史 bug 就出在漏 reindex）。
- **schema 演进**：快照 JSON 有 `schema_version` 字段。加字段时前端 zod 必须兼容旧数据，见 `.trellis/spec/frontend/type-safety.md`。
- **数据新鲜度（个股矩阵）**：backfill 整体重算 vs daily 增量 append 会互相覆盖，`stocks_history_pipeline.py::_guard_no_regress` 是写入护栏，防 backfill 回退掉 daily 已写的最新 bar。
- **latest 单调不倒退**：写 `data/latest` 主快照必走 `pipeline.py::_write_latest_guarded`，它前置 `output/no_regress.py::should_write_latest(new_meta, existing_meta)` 判定——任一市场 `{cn,us}_data_date` 严格更旧即判回退，**四文件(themes/etfs/signals/meta)整体跳过写入**，保留上一好版本（不写"半新半旧"或自相矛盾的 stale meta）。同日（盘中价更新）/更新/首次放行；某侧日期缺失该侧不参与判定（向后兼容）。
  - **跨层契约**：回退时记结构化日志 `latest_write_skipped_regress: <reason> new_cn=.. new_us=.. old_cn=.. old_us=..`，供健康哨兵消费（见 `health-monitoring.md`）。陈旧暴露交给哨兵告警 + 前端 `UpdateBadge`/`AsOfBadge` 老化，护栏本身只保证 latest 不倒退。
  - 与归档护栏互补：`should_write_latest` 护 latest（源），`archiver._assert_fresh` 护 snapshot（下游）。
- **提交 `data/` 回 main 必走 composite action**：所有把 `data/` 提交到 `main` 的 data workflow，提交步骤统一 `uses: ./.github/actions/commit-and-push`，禁止在 workflow 里内联手写 `git commit/pull --rebase/push`。见下「commit-and-push 契约」。**唯一例外**：`stocks-history-backfill`——它是「reset-hard 覆盖取胜」策略（整体重算覆盖 `data/stocks/`，不能用 rebase 合并语义），保留内联逻辑，仅带 `GIT_TERMINAL_PROMPT=0` 护栏。

## commit-and-push 契约（`.github/actions/commit-and-push`）

**为什么存在**：8 个 data workflow 曾各自复制粘贴 git 提交逻辑，多数是裸 `git pull --rebase` 无重试无 timeout。2026-07-11 `cn-eod-archive` 因 `pull --rebase` 遇冲突静默挂起 22 分钟被取消（数据已生成却未落库）。抽成统一 action 根治重复 + 加防 hang 护栏。

- **inputs**：`paths`(必填，git add 路径，空格分隔多路径)、`message`(必填，commit 文案)、`max-retry`(默认 5)、`user-name`/`user-email`(默认 `github-actions[bot]`；`stocks-daily`/`stock-industry-map` 传 `data-bot`)。
- **output**：`changed`（`true`=产生提交 / `false`=无变更跳过）。下游 `Trigger deploy` 靠它判 `if`，勿丢。
- **防 hang 三要素**（缺一即可能复现挂起）：① `export GIT_TERMINAL_PROMPT=0` 防认证交互等待；② `git pull --rebase --autostash origin main && git push` 有界重试（≤`max-retry`，退避 `sleep i*5`），失败轮 `git rebase --abort` 清理半成品 rebase 态；③ 每个调用 job 必配 `timeout-minutes`（兜底上限）。
- **失败语义**：遇无法自动解决的冲突时，重试耗尽即 `::error::` + `exit 1`（~60s 内快速失败），**绝不无限 hang**——这是本 action 存在的根本目的。
- **`with.message` 陷阱**：`with:` 输入不经 shell，`$(date ...)` 会原样传入变死字符串。需日期/时间戳时，前置 `run` step 写 `$GITHUB_OUTPUT` 再用 `${{ steps.*.outputs.* }}` 引用（`${{ }}` 表达式在 `with:` 里由 GitHub 展开，`$()` 不会）。
- **`git add $CP_PATHS` 有意不加引号**（依赖 word-split 支持多路径，如 archive 的 `data/snapshots/ data/latest/`）；shellcheck SC2086 属预期误报。
