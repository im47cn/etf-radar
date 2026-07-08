# C4 设计 · stocks-daily 韧性 + 自动补缺

## 边界与总体思路
两层防御:
1. **防新洞(robustness)**:让 daily 抗抖动、失败响亮 —— 改 `stocks_daily_pipeline.py` + `stocks-daily.yml`。
2. **补旧洞(self-heal)**:检测已有缺口 → dispatch backfill —— 新增连续性检测模块 + workflow 步骤。

补缺**不**由 daily 自身完成(spot 实时接口无历史能力),而是委托 `stocks-history-backfill`(整体重算窗口,天然填洞)。

## 变更清单

### 1. `backend/src/stocks_daily_pipeline.py`
- 新增异常 `class SpotFetchError(Exception)`。
- 新增 `_fetch_today_spot_with_retry(attempts=3, base_delay=2.0)`:循环调用 `_fetch_today_spot()`,指数退避;全部失败抛 `SpotFetchError`。
  - 退避用 `time.sleep`;不引入新依赖。测试通过 monkeypatch `_fetch_today_spot` + patch `time.sleep` 为 no-op。
- `run_daily_pipeline`:把 `try/except → return`(line 132-136)改为调用带重试版;终失败 **raise SpotFetchError**(不再静默 return)。调用方 main() 让异常冒泡 → 进程非 0 → workflow 步骤红。

### 2. 新增 `backend/src/stocks_continuity.py`
纯函数 + CLI,供 workflow 与 C1 哨兵复用。
```
def missing_trading_days(dates: list[str], today: date | None = None) -> list[date]:
    """close_series.dates 相邻项之间、按 chinese_calendar 应存在却缺失的交易日。
    只检测已有序列内部空洞(dates[0]..dates[-1] 区间),不含未来。"""
```
- 逻辑:遍历 `dates` 排序后相邻对 (d_i, d_{i+1}),枚举 (d_i, d_{i+1}) 之间的日历日,`is_cn_trading_day` 为真者若不在 dates 中 → 缺失。
- CLI:`python -m src.stocks_continuity --data-root ../data` 读 `stocks/close_series.json`,打印缺失日;有缺失 exit 3(区分于普通错误),无缺失 exit 0。stdout 输出机器可读(逗号分隔日期)+ 人读摘要。
- 复用 `etl/calendar.is_cn_trading_day`。

### 3. `.github/workflows/stocks-daily.yml`
- `timeout-minutes: 10 → 25`。
- 新增步骤(在 Commit & push 之后,`if: is_trading == 'true'`):
  **Detect gaps & self-heal**
  ```
  set +e
  cd backend && uv run python -m src.stocks_continuity --data-root ../data
  code=$?
  set -e
  if [ "$code" = "3" ]; then
    echo "gap detected → dispatch backfill"
    gh workflow run stocks-history-backfill.yml -f days=150 -f max_workers=8
  elif [ "$code" != "0" ]; then
    exit $code   # 非预期错误,响亮失败
  fi
  ```
  - 需 `env: GH_TOKEN: ${{ secrets.DATA_BOT_PAT }}`(gh CLI 触发 workflow 需 actions:write 的 token)。
  - fire-and-forget:不等待 backfill;backfill 并发组 `stocks-history-backfill` 防止叠加。
  - 顺序保证:先 Commit & push(daily 自身增量落库)再 detect,backfill 后续 `reset --hard origin/main` 会包含该 commit,再以重算结果覆盖 data/stocks(既有"backfill 对 data/stocks 获胜"策略)→ 无冲突、无回归。

## 数据流
```
daily run → spot(retry) → append → commit/push
                                      ↓
                          stocks_continuity 检测
                          ├─ 无缺口 → 结束
                          └─ 有缺口(exit 3) → gh workflow run backfill
                                                   ↓
                                     backfill 整体重算窗口(填洞) → 覆盖 data/stocks
```

## 失败可见性(呼应 D1:自愈耗尽仍告警)
- spot 终失败 → 步骤红 → GitHub 原生 + (C1 落地后)哨兵捕获 workflow failure → Server酱 告警。
- 本子任务**不**直接接 Server酱(渠道属 C1)。C4 只保证"失败非静默(红)"与"缺口自动补",告警由 C1 统一。若 C1 尚未落地,红叉 + GitHub 通知即临时兜底。

## 兼容性 / 回归风险
- `SpotFetchError` 改变了 spot 失败语义(绿→红):这是**期望**的行为修正(静默是 bug)。需确认无调用方依赖旧的"静默 return"。经勘察仅 `main()` 调用,无。
- 连续性检测只读、幂等,零副作用。
- backfill 自触发可能增加 CI 用量:仅在**确有缺口**时触发,正常日不触发;缺口罕见,可控。

## 回滚点
- 三处改动相互独立:pipeline 重试/异常、continuity 模块、workflow 步骤。任一出问题可单独 revert。workflow 的 self-heal 步骤可先加 `--dry-run`(仅打印不 dispatch)灰度。

## 开放项(实现时定,不阻塞)
- backfill dispatch 的 `days`:缺口通常 1-2 天,150 天全量重算偏重但最稳(复用现成参数);若担心用量可按缺口跨度动态传较小值。默认 150。
