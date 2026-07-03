# Component Guidelines

> How components are built in this project.

---

## Overview

<!--
Document your project's component conventions here.

Questions to answer:
- What component patterns do you use?
- How are props defined?
- How do you handle composition?
- What accessibility standards apply?
-->

(To be filled by the team)

---

## Component Structure

<!-- Standard structure of a component file -->

(To be filled by the team)

---

## Props Conventions

<!-- How props should be defined and typed -->

(To be filled by the team)

---

## Styling Patterns

Tailwind utility classes for layout; a shared color-scale module for any value→color mapping.

### Convention: Single-Source Color Scale (breadthColor.ts)

**What**: Data-driven color/label/level/texture for a metric must all derive from ONE source module. No component may hardcode hex/threshold for that metric.

**Why**: Multiple components colored the same "站上率" metric. Previously a continuous scale (`breadthColor`) and a discrete scale (`breadthLevelColor`) drifted apart (mismatched low-end hues), and thresholds were duplicated. Single source removes drift and makes visual convergence a one-line change.

**Contract** (`frontend/src/lib/breadthColor.ts`):
```ts
export const TIERS = [ // 4 档单一定义: label/min/max/mid/hatch 全部由此派生
  { key: 'cold', label: '冰点', min: 0,  max: 30,  mid: 15, hatch: 45  },
  { key: 'cool', label: '偏冷', min: 30, max: 50,  mid: 40, hatch: 0   },
  { key: 'warm', label: '偏暖', min: 50, max: 70,  mid: 60, hatch: 90  },
  { key: 'hot',  label: '过热', min: 70, max: 100, mid: 85, hatch: 135 },
] as const;

breadthColor(rate)      // 连续 rgb — 唯一 STOPS 渐变真源
breadthTier(rate)       // -> TIERS 项 | null; 阈值单点定义
breadthLabel(rate)      // = breadthTier(rate)?.label ?? '无数据' (不重复阈值)
breadthLevelColor(rate) // = breadthColor(breadthTier(rate).mid) (派生, 禁硬编码 hex)
```

**Rule**: A discrete level color MUST be `breadthColor(tier.mid)`, never a separate hex constant. Test with a non-midpoint value to lock tier assignment: `breadthLevelColor(42) === breadthColor(TIERS.cool.mid)` AND `!== breadthColor(42)`.

**Related**: Accessibility → texture encoding below reuses the same `TIERS.hatch` angles.

---

## Accessibility

### Convention: Never Encode Meaning by Color Alone (Texture + Text Redundancy)

**What**: When a value is communicated via color (heatmap cells, bars, bands), it MUST also be distinguishable without color — via (a) a per-tier texture direction and (b) redundant text/number.

**Why**: Color-blind users cannot read a pure冷暖 gradient. This project reinforces每档 with a distinct hatch direction so grayscale/CVD viewers still tell tiers apart.

**Pattern**:
- 4 tiers → 4 distinct hatch angles (`TIERS.hatch`: 45/0/90/135 → `/ — | \`). Direction, not just color.
- HTML surfaces (td / bar / swatch): apply `breadthTextureCss(rate)` → `repeating-linear-gradient(<hatch>deg, transparent 0 4px, rgba(0,0,0,.07) 4px 5px)`. Pure CSS, GPU-composited — scales to hundreds of cells with zero SVG overhead. Keep opacity ~.07 ("极轻") so it doesn't overwhelm.
- SVG surfaces (thermometer band): 4 `<pattern>` in `<defs>` (id `breadth-tex-<key>`); layer a pattern rect over a solid color rect (color stays on the lower rect).
- Texture encodes TIER (discrete), even on a continuous-colored surface — reinforces banding.

**Legend primitive**: a shared page-level `<BreadthLegend>` (no props, data from `TIERS`) renders swatch + label + range. Swatch is `aria-hidden`; screen-reader meaning comes from the text (`role="list"` + `aria-label`).

**Gotcha**: On light palettes the coldest tier has the lowest contrast; if `rgba(0,0,0,.07)` hatch is too faint, raise opacity to ~.09–.10 in the lib (single point), do NOT change angle/width per component.

### Common a11y checklist
- Any `backgroundColor` carrying data → also add texture + text/number/`title`.
- Decorative swatch → `aria-hidden`; meaning in adjacent text.
- Verify in grayscale (DevTools rendering emulation) that all tiers stay distinguishable.

---

## Common Mistakes

<!-- Component-related mistakes your team has made -->

(To be filled by the team)
