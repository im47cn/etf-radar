# Design · 温度页统一色阶与图例 primitive

## 架构与边界
纯前端。核心是把"色阶+档位+纹理"收敛为 `lib/breadthColor.ts` 单一真源，UI 层（1 个新组件 + 4 处接入）只消费，不再各自持有色值/阈值。

改动文件：
- `frontend/src/lib/breadthColor.ts` — 扩展为色阶单一真源（新增 TIERS/tier/texture）。
- `frontend/src/components/temperature/BreadthLegend.tsx` — 新建图例 primitive。
- `frontend/src/pages/TemperaturePage.tsx` — 接入共享图例。
- `frontend/src/components/temperature/BreadthHeatmap.tsx` — 格子叠纹理。
- `frontend/src/components/temperature/IndustryBreadthRanking.tsx` — 条形叠纹理。
- `frontend/src/components/temperature/BreadthThermometer.tsx` — 趋势带 + 大圆叠纹理。
- 测试：`components/temperature/__tests__/temperature.test.tsx`（更新）+ `BreadthLegend.test.tsx`（新增，可并入 temperature.test）。

## 单一真源契约（breadthColor.ts）
```ts
// 4 档定义: 单一来源, 图例/tier/纹理/文案全部由此派生
export const TIERS = [
  { key: 'cold', label: '冰点', min: 0,  max: 30,  mid: 15, hatch: 45  },  // '/'
  { key: 'cool', label: '偏冷', min: 30, max: 50,  mid: 40, hatch: 0   },  // '—'
  { key: 'warm', label: '偏暖', min: 50, max: 70,  mid: 60, hatch: 90  },  // '|'
  { key: 'hot',  label: '过热', min: 70, max: 100, mid: 85, hatch: 135 },  // '\'
] as const;

breadthColor(rate)       // 连续 rgb, 现状不变(仍是唯一 STOPS 渐变)
breadthTier(rate)        // -> TIERS 项 | null(无数据); 阈值 30/50/70, 与 breadthLabel 完全对齐
breadthLabel(rate)       // 改为 breadthTier(rate)?.label ?? '无数据' (消除重复阈值)
breadthLevelColor(rate)  // 改为 breadthColor(breadthTier(rate).mid) 派生(消除硬编码 hex 双真源) → R1
breadthTextureCss(rate)  // -> { backgroundImage, backgroundSize } CSS 纹理(HTML 面用)
breadthTierPatternId(rate) // -> 'breadth-tex-<key>' | null (SVG 面引用 <defs> pattern)
```

### R1 色阶收敛
- `breadthLevelColor` 不再返回硬编码 hex，而是 `breadthColor(tier.mid)`。连续与离散共用同一 STOPS，永不漂移。
- 低端一致性天然成立：离散冰点色 = 连续在 15 处采样，落在 `#e0e7ff→#bae6fd` 之间，与热力图低端同系。
- 注意：`breadthLevelColor` 返回值从 hex 变为 `rgb(...)` 字符串 → 温度计趋势带色值有细微变化（预期，属收敛目标）。

## 纹理方案（R4，性能优先）
纹理编码 **tier（4 档离散）**，非连续值——即使热力图连续着色，纹理按档呈现，反而强化"冷暖分带"读感。

- **HTML 面**（图例色块 / 热力图 `<td>` / 排行条 `<div>` / 温度计大圆）：
  `style={{ backgroundColor: breadthColor(v), ...breadthTextureCss(v) }}`
  纹理 = `repeating-linear-gradient(<hatch>deg, transparent 0 4px, rgba(0,0,0,.07) 4px 5px)`。
  纯 CSS、GPU 合成，数百格子零 SVG 开销 → 解决热力图性能顾虑。透明度 .06–.08 保证"极轻"。
- **SVG 面**（温度计趋势带 rect）：`<defs>` 内 4 个 `<pattern>`（同 hatch 角度、同透明度），band rect `fill={color}` 上再叠一层 `fill="url(#breadth-tex-<key>)"` 的同尺寸 rect；pattern 只画半透明斜线不含底色，故色仍由下层 rect 决定，与 CSS 面视觉一致。

四档角度 45/0/90/135 → 去色后纯靠方向即可区分，经典 pattern-fill 可达性做法。

## 图例 primitive 契约（R2）
```tsx
// BreadthLegend.tsx — 无 props, 数据全部来自 TIERS
export const BreadthLegend = () => (
  <ul role="list" aria-label="市场温度色阶图例" className="flex flex-wrap gap-3 ...">
    {TIERS.map(t => (
      <li key={t.key} className="flex items-center gap-1.5 text-xs text-gray-600">
        <span aria-hidden className="h-3 w-4 rounded-sm border"
              style={{ backgroundColor: breadthColor(t.mid), ...breadthTextureCss(t.mid) }} />
        <span>{t.label} <span className="text-gray-400">{t.min}–{t.max}%</span></span>
      </li>
    ))}
  </ul>
);
```
- 色块 `aria-hidden`（装饰），语义靠文字 → 屏幕阅读器读到"冰点 0–30% / 偏冷 30–50% …"，满足"不只靠颜色"。
- 无 props、纯派生 → 可复用、易测。

## 数据流与兼容
- 无后端/数据契约变化；`MarketPoint`/`BreadthRow` 类型不动。
- 既有 `temperature.test.tsx` 断言 `breadthColor` 端点（不变，仍绿）与 `breadthLabel` 阈值（重构后行为等价，仍绿）。无断言 `breadthLevelColor` 硬编码 hex → 改派生不破测试；但需**新增**派生一致性断言锁住契约。

## 取舍
- 纹理用 CSS gradient 而非 SVG pattern（HTML 面）：牺牲图案精细度，换数百格子零额外 DOM。合理，纹理只需"可区分方向"。
- 图例无 toggle 常显：接受少量视觉噪点换默认可达（Q3 已决）。
- 温度计趋势带走 SVG pattern 双层 rect：局部复杂度上升，但为跨面纹理一致所必需。

## 回滚
改动集中在 1 个 lib + 5 个组件，无迁移/无状态。回滚 = revert commit。`breadthColor.ts` 保持向后兼容导出名（`breadthColor/breadthLabel/breadthLevelColor` 签名不变），即便只回滚组件、保留 lib 也不炸。
