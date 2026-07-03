# 后端目录结构

Python 数据管线（**非 web 服务**）。入口是 CLI + GitHub Actions cron，不是 HTTP 路由。

## 布局（`backend/src/`）

| 目录/文件 | 职责 | 真实示例 |
|---|---|---|
| `pipeline.py` | 主管线：拉 OHLC → 算强度/主题/信号 → 写 `data/latest/*.json`。`--mode=full/intraday/archive` | `run_pipeline()`, `compute_outputs()` |
| `providers/` | 第三方数据源封装，**统一接口 + 统一异常** | `akshare_em_provider.py`, `akshare_sina_provider.py`, `yfinance_provider.py`, `dapanyuntu_provider.py` |
| `providers/base.py` | Provider 协议 + 异常基类 | `EtfDataProvider`(Protocol), `ProviderError`, `EmptyDataError` |
| `market_breadth/` | 独立子管线：个股 MA 宽度（自建 + dapanyuntu QC） | `self_breadth.py`, `stock_industry_pipeline.py`, `reconcile.py`, `industry_mapping.py` |
| `output/` | 快照写入 / 归档 / 索引 | `writer.py`(`atomic_write_json`), `archiver.py`, `snapshots_index.py` |
| `scoring/` | 强度等纯计算 | `strength.py` (`batch_strength_per_dim`) |
| `etl/` | 数据标准化 | `standardize.py` (`standardize_ohlc`) |
| `models.py` | dataclass 数据模型（`Returns`, `Strength`, `EtfOutput`, `ThemeConfig` …） |
| `stocks_*_pipeline.py` | 个股相关独立管线（history backfill / daily 增量 / spot） |
| `config_loader.py` | 读 `config/` 下 YAML |
| `tests/` | pytest（`tests/test_<module>.py`，与 `src/` 平级） |

## 原则

- **一个管线一个文件**：主 ETF 管线（`pipeline.py`）与个股/宽度子管线（`stocks_*_pipeline.py`, `market_breadth/`）解耦，各自 `run()` + `main()` CLI 入口，互不阻断（cron 里各 step `continue-on-error`）。
- **纯函数与 IO 分离**：计算逻辑（`compute_outputs`, `market_breadth/self_breadth.py::compute_self_breadth`）是无副作用纯函数，接 dict/DataFrame 返回 dict；`run()` 负责 读文件→算→`atomic_write_json`。便于测试。
- **无数据库**：状态即 `data/` 下 JSON 快照，见 `database-guidelines.md`。
- **新增 provider**：放 `providers/`，实现 `base.py` 协议，异常包装成 `ProviderError`/`EmptyDataError`，见 `error-handling.md`。
