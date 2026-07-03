# PRD · 温度页统一色阶与图例 primitive

## 目标与用户价值
温度页三张图（温度计趋势带 / 行业排行条 / 历史热力图）都用站上率冷暖色编码，但：
1. 存在两套并存色阶（连续 `breadthColor` 5-stop vs 离散 `breadthLevelColor` 4 档），低端色不一致（淡紫 vs 浅蓝），视觉割裂；
2. 全站无图例，用户无法把颜色对应到"冰点/偏冷/偏暖/过热"语义；
3. 纯颜色编码，色觉障碍用户无法区分冷暖（a11y 缺口）。

价值：单一色阶真源 + 可复用图例 primitive，让温度语义可读、视觉统一、满足"不只靠颜色"的可达性基线。

## 已确认事实（代码勘察）
- 色阶源已集中在 `frontend/src/lib/breadthColor.ts`，导出 `breadthColor`(连续)/`breadthLabel`(4 档文案)/`breadthLevelColor`(4 档离散色)。
- 阈值：冰点 <30 / 偏冷 30–50 / 偏暖 50–70 / 过热 ≥70（`breadthLabel` 与 `breadthLevelColor` 一致）。
- 消费方：
  - `BreadthHeatmap.tsx` 用 `breadthColor`（连续，格子背景）
  - `IndustryBreadthRanking.tsx` 用 `breadthColor`（连续，条形填充）
  - `BreadthThermometer.tsx` 用 `breadthColor`（大圆背景）+ `breadthLevelColor`（趋势背景带）+ `breadthLabel`（文案）
- 页面 `TemperaturePage.tsx`：标题区 → 温度计 → (行业排行 | 热力图) 两栏。
- 测试在 `components/temperature/__tests__/temperature.test.tsx`，断言了 `breadthColor` 端点与 `breadthLabel` 阈值 → 改色值需同步更新。

## 需求
- R1 色阶收敛：`breadthLevelColor` 改为在各档中点对连续 `STOPS` 采样派生，消除双真源漂移；连续与离散低端色一致。
- R2 图例 primitive：新建 `<BreadthLegend>` 复用组件，展示 4 档色块 + 中文档名 + 数值区间。
- R3 接入：温度页在标题行下方展示**页面级单一共享图例**（Q1 定）。
- R4 可达性：4 档各用一种纹理方向（`/` 冰点 / `—` 偏冷 / `|` 偏暖 / `\` 过热），**常显 + CSS 极轻半透明纹理**（Q3 定），叠加到图例 + 热力图 + 排行条 + 温度计趋势带/圆（Q2 定）；去色/色觉障碍下靠纹理方向即可区分档位；补 ARIA 使图例可被屏幕阅读器朗读。
- R5 测试：图例组件单测 + 色阶派生一致性断言 + 纹理按档区分断言；更新既有 temperature 测试。

## 验收标准
- [ ] `breadthLevelColor(v)` 与 `breadthColor` 在同档中点色值一致（单测断言）。
- [ ] `<BreadthLegend>` 渲染 4 档，每档含色块+档名+区间文字，含 `role`/`aria-label`。
- [ ] 温度页可见统一图例。
- [ ] 色觉障碍下（或去色查看）仍可通过文字/纹理区分档位。
- [ ] `npx vitest run` 全绿（含更新后的 temperature 测试）。

## 已决问题
- Q1 图例放置 → 页面级单一共享（标题行下）。
- Q2 纹理范围 → 图例 + 热力图 + 排行条 + 温度计趋势带/圆 全加。
- Q3 常显 vs 切换 → 常显 + CSS 极轻纹理，无 toggle。

## 暂不在范围
- 后端数据/口径变更；温度计以外其他页面配色；新增交互（如点击图例筛选）。
