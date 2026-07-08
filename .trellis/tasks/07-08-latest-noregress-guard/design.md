# C2 设计 · latest no-regress 护栏

## 核心:回退判定 + 条件写入

### 判定纯函数(易测)
`backend/src/output/no_regress.py`(或并入 writer.py):
```
def should_write_latest(new_meta: dict, existing_meta: dict | None) -> tuple[bool, str]:
    """existing_meta=None(首次)→ (True, 'first')。
    比对 cn_data_date / us_data_date:任一市场 new < existing(严格更旧)→ (False, 'regress:<market>')。
    否则(同日或更新)→ (True, 'ok')。
    某侧 date 缺失(None)→ 该侧不参与判定(向后兼容,保守放行)。"""
```
- 日期为 ISO `YYYY-MM-DD` 字符串,可直接字典序比较(等价日期序)。

### 接入点 `pipeline.py:557-560`
把四个 `atomic_write_json` 包进一个 `write_latest(data_root, themes, etfs, signals, meta)`:
```
existing = _read_existing_meta(data_root/'latest'/'meta.json')  # 容错 None
ok, reason = should_write_latest(meta_json, existing)
if not ok:
    log.error('latest_write_skipped_regress: %s new_cn=%s new_us=%s old_cn=%s old_us=%s',
              reason, new_cn, new_us, old_cn, old_us)
    return   # 保留上一好版本, 四文件都不写
# 正常原子写四文件
```
- 结构化前缀 `latest_write_skipped_regress` 便于 C1 哨兵/日志检索(与 provider degraded 一样是 findings 来源;C1 也可直接读 meta 判定,不强依赖日志)。

### 为什么"回退全跳过"而非"写 stale meta"(D4 细化)
- 若写新(更旧)meta 但保留旧数据 → meta 说 07-06、数据是 07-07,自相矛盾,前端/归档下游会被误导。
- 全跳过保持 latest 四文件**整体一致**(仍是上一好版本,含其 meta)。陈旧暴露由两条既有机制兜底:
  - 前端 `UpdateBadge` "更新 X 分钟前" 随时间自然老化 → 用户可感知。
  - C1 哨兵读 meta/run 状态发现停滞 → 告警。
- 因此**无需**为 no-regress 改前端;StaleBanner/UpdateBadge 已够。

## 可选 R2.3:前端"数据截至X日"
- `Header/index.tsx` 新增小字/badge,读 `meta.cn_data_date` 显示"数据截至 07-08"。
- 仅当 `cn_data_date` 存在且非今日、且未触发 StaleBanner(即正常但滞后)时展示,避免与 StaleBanner 重复。
- 轻量,与后端护栏解耦,可作为收尾增强或单独 PR。

## 兼容 / 风险
- **盘中 intraday**:同日多次刷新 cn_data_date 相等 → 放行(价更新),正确。
- **us/cn 独立**:任一回退即整体跳过,偏保守。真实故障多为单市场降级;跳过保留上一好版本比写入半新半旧更安全。可接受。
- **首次/缺 meta**:放行,不阻断冷启动。
- 幂等只读判定,零副作用。

## 回滚点
- `no_regress.py` + pipeline 接入独立;revert 接入即恢复无条件写。
- R2.3 前端独立。

## 交界
- 与 C1 共享 meta 字段与 `latest_write_skipped_regress` 语义。
- 与 archiver `_assert_fresh` 互补:C2 护 latest(源),archiver 护 snapshot(下游)。
