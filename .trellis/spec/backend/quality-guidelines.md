# 后端质量约定

## 工具链（`backend/pyproject.toml`）

- **ruff**：`line-length = 100`。提交前 `uv run ruff check src tests`（`--fix` 自动修）。
- **mypy `strict = true`**：pre-push 会跑，比本地默认更严。常踩的坑：
  - 裸 `list`/`dict` 泛型 → 必须带类型参数（`list[str]`, `dict[str, list[float | None]]`）。
  - 返回 pandas 值的函数会 `no-any-return` → 用 `cast(...)`。
  - 多类型两用（close float / volume int）→ 用受限 `TypeVar('_Num', float, int)`。
  - 多余 `# type: ignore` 会被 `unused-ignore` 拦。
- 测试命令：`cd backend && uv run --all-extras pytest`（单文件加 `tests/test_x.py`）。

## 测试

- **pytest**，`tests/test_<module>.py`，与 `src/` 平级。
- **纯函数优先测**：计算逻辑（`compute_*`, `compute_self_breadth`, `batch_strength_per_dim`）用小型构造数据覆盖边界（空值/停牌 null / 历史不足 / 聚合口径 / 排序）。
- **provider 用 mock**：`unittest.mock` 注入假 akshare/httpx 响应，测成功/403/空数据/重试；provider 支持 `_ak`/`fetch` 依赖注入便于测试。
- **测试防漂移**：不硬编码会变的常量（如主题数、`WINDOW_DAYS`）——从 config/常量派生（见近期 commit "derive ... from config to stop drift"）。

## 铁律（团队约定，来自 `docs/CONVENTIONS.md`）

- **Provider 必走 Chain**：见 `error-handling.md`。写/审任何 `*Provider().fetch_*` 时确认上游是 list 而非单实例。
- **原子写入**：写 `data/` 必走 `atomic_write_json`，见 `database-guidelines.md`。
- **Context 恢复纪律**：context 压缩/`/clear`/长空闲恢复后，第一动作 `git log --oneline -10` + `git status --short` 校准，不基于旧记忆做 staging/commit 决策。
- **枚举语义分离**：删/改 UI 状态枚举（如 MarketView `'us'|'cn-all'`）前 grep 全仓库并按语义分类——别误删同名的数据属性（如 Theme `isCnOnly()`）。

## 回归门（提交前）

`uv run --all-extras pytest` 全绿 + `ruff check` + `mypy src` 无错。pre-push hook 会强制这些，别用 `--no-verify`（纯数据提交例外）。
