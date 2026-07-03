# Implement · 温度页统一色阶与图例 primitive

## 执行清单（按序）

1. **色阶单一真源** `lib/breadthColor.ts`
   - [ ] 新增 `TIERS` 常量（key/label/min/max/mid/hatch）。
   - [ ] 新增 `breadthTier(rate): typeof TIERS[number] | null`（阈值 30/50/70，无数据→null）。
   - [ ] `breadthLabel` 改为 `breadthTier(rate)?.label ?? '无数据'`（去重阈值）。
   - [ ] `breadthLevelColor` 改为 `rate==null? NO_DATA : breadthColor(breadthTier(rate)!.mid)`（派生，去硬编码 hex）。
   - [ ] 新增 `breadthTextureCss(rate): { backgroundImage: string; backgroundSize?: string } | {}`（无数据→无纹理）。
   - [ ] 新增 `breadthTierPatternId(rate): string | null`（供 SVG）。

2. **图例 primitive** `components/temperature/BreadthLegend.tsx`（新建）
   - [ ] 按 design 契约实现，`role="list"` + `aria-label`，色块 `aria-hidden`。

3. **接入热力图** `BreadthHeatmap.tsx`
   - [ ] `<td>` 加 `...breadthTextureCss(v)` 到 style（保留现有 title 冗余）。

4. **接入排行条** `IndustryBreadthRanking.tsx`
   - [ ] 条形填充 div 加 `...breadthTextureCss(row.latest)`（保留现有数值冗余）。

5. **接入温度计** `BreadthThermometer.tsx`
   - [ ] 大圆背景加 `...breadthTextureCss(rate)`。
   - [ ] SVG 内加 `<defs>` 4 个半透明 hatch `<pattern>`；band 每格在 color rect 上叠一层 `fill="url(#...)"` 的 pattern rect。

6. **接入页面** `TemperaturePage.tsx`
   - [ ] 标题行下方渲染 `<BreadthLegend />`（三图之上、两栏之前）。

7. **测试**
   - [ ] `temperature.test.tsx`：新增 `breadthLevelColor(v) === breadthColor(tier.mid)` 一致性断言；`breadthTier` 边界（29/30/49/50/69/70/null）；`breadthTextureCss` 四档 backgroundImage 互异、无数据为空。
   - [ ] `BreadthLegend.test.tsx`（或并入）：渲染 4 档、含档名+区间文本、含 `role="list"`/`aria-label`。
   - [ ] 更新任何因 `breadthLevelColor` 由 hex→rgb 变化而失败的既有断言（预期无，先跑确认）。

## 验证命令
```bash
cd /Users/dreambt/sources/etf-radar/frontend && npx vitest run src/components/temperature src/lib/__tests__ 2>&1 | tail -20
cd /Users/dreambt/sources/etf-radar/frontend && npx tsc --noEmit 2>&1 | tail -20
cd /Users/dreambt/sources/etf-radar/frontend && npm run lint 2>&1 | tail -20
```
视觉核验（可选）：`npm run dev` 打开 /temperature，确认图例四档纹理方向可辨、热力图不卡、纹理"极轻"不喧宾夺主。

## 风险文件 / 回滚点
- `lib/breadthColor.ts`：契约中心，改错波及全部三图。改完立即跑 vitest 锁契约。
- `BreadthThermometer.tsx` SVG pattern 双层 rect：最易出错处（pattern id 唯一性、坐标对齐）；若 SVG 纹理成本过高或渲染异常，回退为趋势带仅色不叠纹理（HTML 面纹理照常），不阻塞主线。

## 提交前检查
- [ ] vitest / tsc / lint 三绿。
- [ ] 图例 4 档区间文字与 TIERS 阈值一致。
- [ ] 去色（浏览器灰度/DevTools）下四档纹理方向仍可区分。
