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
