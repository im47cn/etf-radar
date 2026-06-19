# 主题轮动象限图分布健康度指标 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在主题轮动象限图上方新增一行"覆盖度 + 鲁棒度"双指标信息条，让用户一眼判断当前快照的分类信号质量。

**Architecture:** 纯前端实时计算。三个新文件（类型扩展 + 纯函数 + 展示组件）+ 一个修改文件（RotationPage 接线）+ 一个测试扩展（RotationPage 测试）。指标公式与档位阈值见 spec §3。所有计算 O(N)，N≈10-20，<1ms。

**Tech Stack:** React 18 + TypeScript + Tailwind + Vitest + React Testing Library。沿用现有 `frontend/src/lib/__tests__/` 与 `frontend/src/components/rotation/__tests__/` 测试目录约定。

**Spec:** [docs/superpowers/specs/2026-06-18-rotation-health-indicator-design.md](../specs/2026-06-18-rotation-health-indicator-design.md)

**File Structure:**

```
frontend/src/
├── types/rotation.ts                                  ← 修改: 追加类型导出
├── lib/
│   ├── rotationHealth.ts                              ← 新增: 纯函数模块
│   └── __tests__/rotationHealth.test.ts               ← 新增: 18 个单元测试
├── components/rotation/
│   ├── RotationHealthBar.tsx                          ← 新增: 展示组件
│   └── __tests__/RotationHealthBar.test.tsx           ← 新增: 8 个组件测试
└── pages/
    ├── RotationPage.tsx                               ← 修改: 接线
    └── __tests__/RotationPage.test.tsx                ← 修改: 4 个新增 case
```

**关键决策（与 spec 一致）：**
- 数据源：用 `useDataContext()` 提供的 `themes.themes`，与 chart 显示的数据保持一致。当前 RotationPage 无时间轴 slider，用 dataContext 即可；未来若加 slider，改为 `useSnapshotsTimeline().frame.themes` 是 1 行变更。
- Tooltip：v1 用 HTML 原生 `title` 属性。spec §5.3 已注明此为可选项之一，避免引入 base-ui Tooltip 的 Provider 包装复杂度。

---

## Task 1: 扩展 rotation 类型定义

**Files:**
- Modify: `frontend/src/types/rotation.ts`

- [ ] **Step 1: 追加 HealthGrade 和 HealthScore 类型**

在 `frontend/src/types/rotation.ts` 末尾追加：

```ts
export type HealthGrade = 'healthy' | 'caution' | 'imbalanced' | 'insufficient';

export interface HealthMetric {
  score: number;
  grade: HealthGrade;
}

export interface HealthScore {
  coverage: HealthMetric;
  robustness: HealthMetric;
}
```

- [ ] **Step 2: 验证 TypeScript 编译通过**

Run:
```bash
cd /Users/dreambt/sources/etf-radar/frontend && npx tsc --noEmit 2>&1 | tail -10
```
Expected: 无新报错（可能有既有的 `tsconfig.json` deprecation 警告，忽略）

- [ ] **Step 3: 提交**

```bash
cd /Users/dreambt/sources/etf-radar
git add frontend/src/types/rotation.ts
git commit -m "feat(rotation): add HealthGrade and HealthScore types"
```

---

## Task 2: 实现 computeCoverage 函数（TDD）

**Files:**
- Create: `frontend/src/lib/rotationHealth.ts`
- Create: `frontend/src/lib/__tests__/rotationHealth.test.ts`

- [ ] **Step 1: 写失败测试**

创建 `frontend/src/lib/__tests__/rotationHealth.test.ts`：

```ts
import { describe, it, expect } from 'vitest';
import type { RotationPoint } from '@/types/rotation';
import { computeCoverage } from '../rotationHealth';

const mkPoint = (x: number, y: number, id = 't'): RotationPoint => ({
  themeId: id,
  themeName: id,
  x,
  y,
  size: 50,
  quadrant:
    x >= 50 && y >= 50 ? 'leading'
    : x < 50 && y >= 50 ? 'rising'
    : x < 50 && y < 50 ? 'lagging'
    : 'fading',
  tags: [],
});

describe('computeCoverage', () => {
  it('returns ~100 when all four quadrants are evenly populated', () => {
    const points = [
      mkPoint(80, 80, 'a1'), mkPoint(80, 80, 'a2'), mkPoint(80, 80, 'a3'),  // leading
      mkPoint(20, 80, 'b1'), mkPoint(20, 80, 'b2'), mkPoint(20, 80, 'b3'),  // rising
      mkPoint(20, 20, 'c1'), mkPoint(20, 20, 'c2'), mkPoint(20, 20, 'c3'),  // lagging
      mkPoint(80, 20, 'd1'), mkPoint(80, 20, 'd2'), mkPoint(80, 20, 'd3'),  // fading
    ];
    expect(computeCoverage(points)).toBeCloseTo(100, 0);
  });

  it('returns 0 when all points are in one quadrant', () => {
    const points = [
      mkPoint(80, 80, 'a1'), mkPoint(80, 80, 'a2'),
      mkPoint(80, 80, 'a3'), mkPoint(80, 80, 'a4'),
    ];
    expect(computeCoverage(points)).toBe(0);
  });

  it('returns 50 for bipolar distribution (2 quadrants equally)', () => {
    const points = [
      mkPoint(80, 80, 'a1'), mkPoint(80, 80, 'a2'), mkPoint(80, 80, 'a3'),
      mkPoint(20, 20, 'b1'), mkPoint(20, 20, 'b2'), mkPoint(20, 20, 'b3'),
    ];
    expect(computeCoverage(points)).toBeCloseTo(50, 1);
  });

  it('returns 0 for empty array', () => {
    expect(computeCoverage([])).toBe(0);
  });

  it('returns 0 for single point', () => {
    expect(computeCoverage([mkPoint(80, 80)])).toBe(0);
  });
});
```

- [ ] **Step 2: 运行测试确认失败**

Run:
```bash
cd /Users/dreambt/sources/etf-radar/frontend && npx vitest run src/lib/__tests__/rotationHealth.test.ts 2>&1 | tail -20
```
Expected: FAIL，错误信息类似 "Cannot find module '../rotationHealth'"

- [ ] **Step 3: 写最小实现**

创建 `frontend/src/lib/rotationHealth.ts`：

```ts
import type { RotationPoint, Quadrant } from '@/types/rotation';

/**
 * 覆盖度: 四象限主题数的香农熵, 归一到 0-100.
 * 100 = 四象限完全均匀, 0 = 全部挤在一个象限.
 * N < 2 时无意义, 返回 0 (调用方应配合 gradeCoverage 判定为 insufficient).
 */
export function computeCoverage(points: RotationPoint[]): number {
  if (points.length < 2) return 0;

  const counts: Record<Quadrant, number> = {
    leading: 0,
    rising: 0,
    lagging: 0,
    fading: 0,
  };
  for (const p of points) counts[p.quadrant]++;

  const total = points.length;
  let H = 0;
  for (const c of Object.values(counts)) {
    if (c === 0) continue; // 数学约定: 0 * log(0) := 0
    const p = c / total;
    H -= p * Math.log2(p);
  }
  return (H / Math.log2(4)) * 100;
}
```

- [ ] **Step 4: 运行测试确认通过**

Run:
```bash
cd /Users/dreambt/sources/etf-radar/frontend && npx vitest run src/lib/__tests__/rotationHealth.test.ts 2>&1 | tail -20
```
Expected: 5 tests passed

- [ ] **Step 5: 提交**

```bash
cd /Users/dreambt/sources/etf-radar
git add frontend/src/lib/rotationHealth.ts frontend/src/lib/__tests__/rotationHealth.test.ts
git commit -m "feat(rotation): add computeCoverage with shannon entropy"
```

---

## Task 3: 实现 computeRobustness 函数（TDD）

**Files:**
- Modify: `frontend/src/lib/rotationHealth.ts`
- Modify: `frontend/src/lib/__tests__/rotationHealth.test.ts`

- [ ] **Step 1: 写失败测试**

在 `rotationHealth.test.ts` 末尾、`mkPoint` 之后追加新 describe 块：

```ts
import { computeRobustness, EDGE_THRESHOLD } from '../rotationHealth';

describe('computeRobustness', () => {
  it('returns 100 when all points are far from boundaries', () => {
    const points = [mkPoint(10, 10), mkPoint(10, 10), mkPoint(10, 10)];
    expect(computeRobustness(points)).toBe(100);
  });

  it('returns 0 when all points are on boundaries', () => {
    const points = [mkPoint(50, 50), mkPoint(50, 50), mkPoint(50, 50)];
    expect(computeRobustness(points)).toBe(0);
  });

  it('returns 50 when half points are fragile', () => {
    const points = [
      mkPoint(10, 10), mkPoint(10, 10), mkPoint(10, 10), mkPoint(10, 10), mkPoint(10, 10),
      mkPoint(50, 50), mkPoint(50, 50), mkPoint(50, 50), mkPoint(50, 50), mkPoint(50, 50),
    ];
    expect(computeRobustness(points)).toBe(50);
  });

  it('treats x-near-boundary as fragile even if y is far', () => {
    const points = [mkPoint(50, 80)];
    expect(computeRobustness(points)).toBe(0);
  });

  it('uses strict < at threshold boundary', () => {
    // 距边界恰好 = EDGE_THRESHOLD: 不算脆弱 (开区间)
    const pSafe = mkPoint(50 + EDGE_THRESHOLD, 80);
    expect(computeRobustness([pSafe])).toBe(100);
    // 距边界 < EDGE_THRESHOLD: 算脆弱
    const pFragile = mkPoint(50 + EDGE_THRESHOLD - 0.01, 80);
    expect(computeRobustness([pFragile])).toBe(0);
  });

  it('returns 0 for empty array', () => {
    expect(computeRobustness([])).toBe(0);
  });

  it('exports EDGE_THRESHOLD = 10', () => {
    expect(EDGE_THRESHOLD).toBe(10);
  });
});
```

- [ ] **Step 2: 运行测试确认失败**

Run:
```bash
cd /Users/dreambt/sources/etf-radar/frontend && npx vitest run src/lib/__tests__/rotationHealth.test.ts 2>&1 | tail -20
```
Expected: 7 new tests FAIL with "Cannot find name 'computeRobustness'" or similar

- [ ] **Step 3: 写实现**

在 `frontend/src/lib/rotationHealth.ts` 中追加：

```ts
/**
 * 距边界 < EDGE_THRESHOLD 即视为脆弱: 小幅波动就会跨象限.
 * 设为 10 是首版默认 (strength 是 0-99 整数, ±10 约对应一日 ±1% 收益的强度抖动).
 */
export const EDGE_THRESHOLD = 10;

/**
 * 鲁棒度: 远离边界线 (x=50 或 y=50) 超过 EDGE_THRESHOLD 单位的主题占比 * 100.
 * 100 = 没有脆弱主题, 0 = 全部脆弱.
 * N = 0 时返回 0.
 */
export function computeRobustness(points: RotationPoint[]): number {
  if (points.length === 0) return 0;

  let fragileCount = 0;
  for (const p of points) {
    const xNearEdge = Math.abs(p.x - 50) < EDGE_THRESHOLD;
    const yNearEdge = Math.abs(p.y - 50) < EDGE_THRESHOLD;
    if (xNearEdge || yNearEdge) fragileCount++;
  }
  return (1 - fragileCount / points.length) * 100;
}
```

- [ ] **Step 4: 运行测试确认通过**

Run:
```bash
cd /Users/dreambt/sources/etf-radar/frontend && npx vitest run src/lib/__tests__/rotationHealth.test.ts 2>&1 | tail -20
```
Expected: 12 tests passed (5 from Task 2 + 7 new)

- [ ] **Step 5: 提交**

```bash
cd /Users/dreambt/sources/etf-radar
git add frontend/src/lib/rotationHealth.ts frontend/src/lib/__tests__/rotationHealth.test.ts
git commit -m "feat(rotation): add computeRobustness with edge-distance fragility"
```

---

## Task 4: 实现 gradeCoverage 和 gradeRobustness（TDD）

**Files:**
- Modify: `frontend/src/lib/rotationHealth.ts`
- Modify: `frontend/src/lib/__tests__/rotationHealth.test.ts`

- [ ] **Step 1: 写失败测试**

在 `rotationHealth.test.ts` 末尾追加：

```ts
import { gradeCoverage, gradeRobustness } from '../rotationHealth';

describe('gradeCoverage', () => {
  it('returns insufficient when n < 2', () => {
    expect(gradeCoverage(50, 0)).toBe('insufficient');
    expect(gradeCoverage(50, 1)).toBe('insufficient');
  });

  it('returns healthy when score >= 80', () => {
    expect(gradeCoverage(80, 10)).toBe('healthy');
    expect(gradeCoverage(95, 10)).toBe('healthy');
  });

  it('returns caution when 74 <= score < 80', () => {
    expect(gradeCoverage(74, 10)).toBe('caution');
    expect(gradeCoverage(79.9, 10)).toBe('caution');
  });

  it('returns imbalanced when score < 74', () => {
    expect(gradeCoverage(73.9, 10)).toBe('imbalanced');
    expect(gradeCoverage(0, 10)).toBe('imbalanced');
  });
});

describe('gradeRobustness', () => {
  it('returns insufficient when n < 1', () => {
    expect(gradeRobustness(50, 0)).toBe('insufficient');
  });

  it('returns healthy when score >= 77', () => {
    expect(gradeRobustness(77, 10)).toBe('healthy');
    expect(gradeRobustness(100, 10)).toBe('healthy');
  });

  it('returns caution when 69 <= score < 77', () => {
    expect(gradeRobustness(69, 10)).toBe('caution');
    expect(gradeRobustness(76.9, 10)).toBe('caution');
  });

  it('returns imbalanced when score < 69', () => {
    expect(gradeRobustness(68.9, 10)).toBe('imbalanced');
    expect(gradeRobustness(0, 10)).toBe('imbalanced');
  });
});
```

- [ ] **Step 2: 运行测试确认失败**

Run:
```bash
cd /Users/dreambt/sources/etf-radar/frontend && npx vitest run src/lib/__tests__/rotationHealth.test.ts 2>&1 | tail -20
```
Expected: 8 new tests FAIL

- [ ] **Step 3: 写实现**

在 `frontend/src/lib/rotationHealth.ts` 中追加：

```ts
import type { HealthGrade } from '@/types/rotation';

/**
 * 覆盖度档位: 基于 123 个历史快照 (2026-01 ~ 2026-06) 的实测分位数.
 * P50=80, P25=74. 详见 spec §10.
 */
export function gradeCoverage(score: number, n: number): HealthGrade {
  if (n < 2) return 'insufficient';
  if (score >= 80) return 'healthy';
  if (score >= 74) return 'caution';
  return 'imbalanced';
}

/**
 * 鲁棒度档位: 基于 123 个历史快照的实测分位数. P50=77, P25=69.
 */
export function gradeRobustness(score: number, n: number): HealthGrade {
  if (n < 1) return 'insufficient';
  if (score >= 77) return 'healthy';
  if (score >= 69) return 'caution';
  return 'imbalanced';
}
```

注意：把 `import type { HealthGrade }` 加到文件顶部已有的 import 行（与现有 `RotationPoint` import 合并）。最终顶部 import 形如：

```ts
import type { RotationPoint, Quadrant, HealthGrade } from '@/types/rotation';
```

- [ ] **Step 4: 运行测试确认通过**

Run:
```bash
cd /Users/dreambt/sources/etf-radar/frontend && npx vitest run src/lib/__tests__/rotationHealth.test.ts 2>&1 | tail -20
```
Expected: 20 tests passed

- [ ] **Step 5: 提交**

```bash
cd /Users/dreambt/sources/etf-radar
git add frontend/src/lib/rotationHealth.ts frontend/src/lib/__tests__/rotationHealth.test.ts
git commit -m "feat(rotation): add gradeCoverage and gradeRobustness with P25/P50 thresholds"
```

---

## Task 5: 实现 computeRotationHealth 集成入口（TDD）

**Files:**
- Modify: `frontend/src/lib/rotationHealth.ts`
- Modify: `frontend/src/lib/__tests__/rotationHealth.test.ts`

- [ ] **Step 1: 写失败测试**

在 `rotationHealth.test.ts` 末尾追加：

```ts
import { computeRotationHealth } from '../rotationHealth';
import type { Theme } from '@/types/themes';

const mkTheme = (id: string, longStr: number, shortStr: number): Theme => ({
  id,
  name: id.toUpperCase(),
  us_etfs: ['SOXX'],
  primary_us: 'SOXX',
  tags: [],
  note: '',
  returns: { r_1d: 0, r_5d: 0, r_20d: 0, r_60d: 0, r_120d: 0, r_ytd: 0 },
  strength: { short: shortStr, mid: 50, long: longStr, composite: 50 },
  rank: { short: 1, mid: 1, long: 1, composite: 1 },
});

describe('computeRotationHealth', () => {
  it('returns complete structure with both metrics', () => {
    const themes: Theme[] = [
      mkTheme('a', 80, 80), mkTheme('b', 80, 80), mkTheme('c', 80, 80),
      mkTheme('d', 20, 80), mkTheme('e', 20, 80), mkTheme('f', 20, 80),
      mkTheme('g', 20, 20), mkTheme('h', 20, 20), mkTheme('i', 20, 20),
      mkTheme('j', 80, 20), mkTheme('k', 80, 20), mkTheme('l', 80, 20),
    ];
    const h = computeRotationHealth(themes);
    expect(h.coverage.score).toBeCloseTo(100, 0);
    expect(h.coverage.grade).toBe('healthy');
    expect(h.robustness.score).toBe(100);
    expect(h.robustness.grade).toBe('healthy');
  });

  it('handles empty themes array', () => {
    const h = computeRotationHealth([]);
    expect(h.coverage.score).toBe(0);
    expect(h.coverage.grade).toBe('insufficient');
    expect(h.robustness.score).toBe(0);
    expect(h.robustness.grade).toBe('insufficient');
  });

  it('handles single-theme array (coverage insufficient, robustness computed)', () => {
    const h = computeRotationHealth([mkTheme('a', 10, 10)]);
    expect(h.coverage.grade).toBe('insufficient');
    expect(h.robustness.score).toBe(100); // (10,10) 远离边界
    expect(h.robustness.grade).toBe('healthy');
  });

  it('rounds scores to integers in returned structure', () => {
    const themes: Theme[] = [
      mkTheme('a', 80, 80), mkTheme('b', 80, 80), mkTheme('c', 80, 80),
      mkTheme('d', 20, 20), mkTheme('e', 20, 20), mkTheme('f', 20, 20),
    ];
    const h = computeRotationHealth(themes);
    expect(Number.isInteger(h.coverage.score)).toBe(true);
    expect(Number.isInteger(h.robustness.score)).toBe(true);
  });
});
```

- [ ] **Step 2: 运行测试确认失败**

Run:
```bash
cd /Users/dreambt/sources/etf-radar/frontend && npx vitest run src/lib/__tests__/rotationHealth.test.ts 2>&1 | tail -20
```
Expected: 4 new tests FAIL

- [ ] **Step 3: 写实现**

在 `frontend/src/lib/rotationHealth.ts` 中追加。同时**修改顶部 import**：

```ts
import type { RotationPoint, Quadrant, HealthGrade, HealthScore } from '@/types/rotation';
import type { Theme } from '@/types/themes';
import { themesToRotationPoints } from './rotation';
```

然后追加：

```ts
/**
 * 一站式入口: 主题数组 → 完整 HealthScore. 分数取整, 档位由 grade* 函数判定.
 */
export function computeRotationHealth(themes: Theme[]): HealthScore {
  const points = themesToRotationPoints(themes);
  const n = points.length;

  const coverageScore = Math.round(computeCoverage(points));
  const robustnessScore = Math.round(computeRobustness(points));

  return {
    coverage: {
      score: coverageScore,
      grade: gradeCoverage(coverageScore, n),
    },
    robustness: {
      score: robustnessScore,
      grade: gradeRobustness(robustnessScore, n),
    },
  };
}
```

- [ ] **Step 4: 检查 `themesToRotationPoints` 是否已导出**

Run:
```bash
cd /Users/dreambt/sources/etf-radar/frontend && grep -n "export.*themesToRotationPoints" src/lib/rotation.ts
```
Expected: 匹配到 `export function themesToRotationPoints` 或 `export const themesToRotationPoints`。如未导出，需要修改 `src/lib/rotation.ts` 增加 `export` 关键字。

- [ ] **Step 5: 运行测试确认通过**

Run:
```bash
cd /Users/dreambt/sources/etf-radar/frontend && npx vitest run src/lib/__tests__/rotationHealth.test.ts 2>&1 | tail -20
```
Expected: 24 tests passed

- [ ] **Step 6: 提交**

```bash
cd /Users/dreambt/sources/etf-radar
git add frontend/src/lib/rotationHealth.ts frontend/src/lib/__tests__/rotationHealth.test.ts frontend/src/lib/rotation.ts
git commit -m "feat(rotation): add computeRotationHealth integration entrypoint"
```

---

## Task 6: 实现 RotationHealthBar 组件（TDD）

**Files:**
- Create: `frontend/src/components/rotation/RotationHealthBar.tsx`
- Create: `frontend/src/components/rotation/__tests__/RotationHealthBar.test.tsx`

- [ ] **Step 1: 写失败测试**

创建 `frontend/src/components/rotation/__tests__/RotationHealthBar.test.tsx`：

```tsx
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { HealthScore } from '@/types/rotation';
import { RotationHealthBar } from '../RotationHealthBar';

const mkHealth = (
  coverageScore: number,
  coverageGrade: HealthScore['coverage']['grade'],
  robustnessScore: number,
  robustnessGrade: HealthScore['robustness']['grade'],
): HealthScore => ({
  coverage: { score: coverageScore, grade: coverageGrade },
  robustness: { score: robustnessScore, grade: robustnessGrade },
});

describe('RotationHealthBar', () => {
  it('renders score numbers for both metrics', () => {
    render(<RotationHealthBar health={mkHealth(72, 'caution', 85, 'healthy')} />);
    expect(screen.getByText('72')).toBeInTheDocument();
    expect(screen.getByText('85')).toBeInTheDocument();
  });

  it('renders both labels', () => {
    render(<RotationHealthBar health={mkHealth(72, 'caution', 85, 'healthy')} />);
    expect(screen.getByText('覆盖度')).toBeInTheDocument();
    expect(screen.getByText('鲁棒度')).toBeInTheDocument();
  });

  it('renders both grade labels', () => {
    render(<RotationHealthBar health={mkHealth(72, 'caution', 85, 'healthy')} />);
    expect(screen.getByText('警示')).toBeInTheDocument();
    expect(screen.getByText('健康')).toBeInTheDocument();
  });

  it('applies green class for healthy grade', () => {
    const { container } = render(
      <RotationHealthBar health={mkHealth(90, 'healthy', 90, 'healthy')} />,
    );
    expect(container.querySelectorAll('.bg-green-100').length).toBe(2);
  });

  it('applies amber class for caution grade', () => {
    const { container } = render(
      <RotationHealthBar health={mkHealth(75, 'caution', 75, 'caution')} />,
    );
    expect(container.querySelectorAll('.bg-amber-100').length).toBe(2);
  });

  it('applies red class for imbalanced grade', () => {
    const { container } = render(
      <RotationHealthBar health={mkHealth(50, 'imbalanced', 50, 'imbalanced')} />,
    );
    expect(container.querySelectorAll('.bg-red-100').length).toBe(2);
  });

  it('shows em-dash placeholder when grade is insufficient', () => {
    render(<RotationHealthBar health={mkHealth(0, 'insufficient', 85, 'healthy')} />);
    // coverage cell uses '—', robustness cell still shows '85'
    expect(screen.getByText('—')).toBeInTheDocument();
    expect(screen.getByText('85')).toBeInTheDocument();
  });

  it('exposes status role and aria-label on each cell', () => {
    render(<RotationHealthBar health={mkHealth(72, 'caution', 85, 'healthy')} />);
    const cells = screen.getAllByRole('status');
    expect(cells).toHaveLength(2);
    expect(cells[0].getAttribute('aria-label')).toContain('覆盖度');
    expect(cells[0].getAttribute('aria-label')).toContain('72');
    expect(cells[0].getAttribute('aria-label')).toContain('警示');
  });
});
```

- [ ] **Step 2: 运行测试确认失败**

Run:
```bash
cd /Users/dreambt/sources/etf-radar/frontend && npx vitest run src/components/rotation/__tests__/RotationHealthBar.test.tsx 2>&1 | tail -20
```
Expected: 8 tests FAIL with "Cannot find module '../RotationHealthBar'"

- [ ] **Step 3: 写实现**

创建 `frontend/src/components/rotation/RotationHealthBar.tsx`：

```tsx
import type { HealthGrade, HealthScore } from '@/types/rotation';

const GRADE_LABEL: Record<HealthGrade, string> = {
  healthy: '健康',
  caution: '警示',
  imbalanced: '失衡',
  insufficient: '数据不足',
};

const GRADE_BADGE_CLASS: Record<HealthGrade, string> = {
  healthy: 'bg-green-100 text-green-700 px-2 py-0.5 rounded text-xs',
  caution: 'bg-amber-100 text-amber-700 px-2 py-0.5 rounded text-xs',
  imbalanced: 'bg-red-100 text-red-700 px-2 py-0.5 rounded text-xs',
  insufficient: 'bg-gray-100 text-gray-600 px-2 py-0.5 rounded text-xs',
};

const TOOLTIP: Record<'coverage' | 'robustness', string> = {
  coverage:
    '四象限主题数的香农熵。100=四象限均匀，0=全部挤在一个象限。低分意味分类信号集中，需结合大盘环境理解。',
  robustness:
    '远离边界线 (x=50 或 y=50) 超过 10 单位的主题占比。低分意味多数主题贴近边界，小幅波动就会跨象限，分类信号脆弱；高分意味分类对噪声有抗扰动能力。',
};

interface HealthCellProps {
  label: string;
  score: number;
  grade: HealthGrade;
  tooltip: string;
}

const HealthCell = ({ label, score, grade, tooltip }: HealthCellProps) => {
  const display = grade === 'insufficient' ? '—' : score.toString();
  const ariaLabel = `${label} ${display}${grade === 'insufficient' ? '' : ' 分'} ${GRADE_LABEL[grade]}`;
  return (
    <div
      className="bg-white px-4 py-2 flex items-center justify-between"
      role="status"
      aria-label={ariaLabel}
      title={tooltip}
    >
      <span className="text-xs text-gray-600">{label}</span>
      <div className="flex items-center gap-2">
        <span className="text-lg font-semibold tabular-nums">{display}</span>
        <span className={GRADE_BADGE_CLASS[grade]}>{GRADE_LABEL[grade]}</span>
      </div>
    </div>
  );
};

export interface RotationHealthBarProps {
  health: HealthScore;
}

export const RotationHealthBar = ({ health }: RotationHealthBarProps) => (
  <div
    className="grid grid-cols-1 sm:grid-cols-2 gap-px bg-gray-200 border rounded overflow-hidden mb-4"
    role="region"
    aria-label="分布健康度"
  >
    <HealthCell
      label="覆盖度"
      score={health.coverage.score}
      grade={health.coverage.grade}
      tooltip={TOOLTIP.coverage}
    />
    <HealthCell
      label="鲁棒度"
      score={health.robustness.score}
      grade={health.robustness.grade}
      tooltip={TOOLTIP.robustness}
    />
  </div>
);
```

- [ ] **Step 4: 运行测试确认通过**

Run:
```bash
cd /Users/dreambt/sources/etf-radar/frontend && npx vitest run src/components/rotation/__tests__/RotationHealthBar.test.tsx 2>&1 | tail -20
```
Expected: 8 tests passed

- [ ] **Step 5: 提交**

```bash
cd /Users/dreambt/sources/etf-radar
git add frontend/src/components/rotation/RotationHealthBar.tsx frontend/src/components/rotation/__tests__/RotationHealthBar.test.tsx
git commit -m "feat(rotation): add RotationHealthBar display component"
```

---

## Task 7: 接入 RotationPage 并扩展集成测试

**Files:**
- Modify: `frontend/src/pages/RotationPage.tsx`
- Modify: `frontend/src/pages/__tests__/RotationPage.test.tsx`

- [ ] **Step 1: 先扩展页面集成测试（TDD）**

在 `frontend/src/pages/__tests__/RotationPage.test.tsx` 的 `describe('RotationPage', () => {` 块末尾追加 4 个新 case：

```tsx
  it('renders health bar when themes are ready', () => {
    mockUseDataContext.mockReturnValue({
      themes: {
        schema_version: '1.0',
        generated_at: '',
        themes: [mkTheme('ai'), mkTheme('semi')],
      },
      isLoading: false,
      error: null,
    });
    renderPage();
    expect(screen.getByText('覆盖度')).toBeInTheDocument();
    expect(screen.getByText('鲁棒度')).toBeInTheDocument();
  });

  it('does not render health bar when loading', () => {
    mockUseDataContext.mockReturnValue({ themes: undefined, isLoading: true, error: null });
    renderPage();
    expect(screen.queryByText('覆盖度')).not.toBeInTheDocument();
  });

  it('does not render health bar on error', () => {
    mockUseDataContext.mockReturnValue({
      themes: undefined,
      isLoading: false,
      error: new Error('boom'),
    });
    renderPage();
    expect(screen.queryByText('覆盖度')).not.toBeInTheDocument();
  });

  it('does not render health bar when themes empty', () => {
    mockUseDataContext.mockReturnValue({
      themes: { schema_version: '1.0', generated_at: '', themes: [] },
      isLoading: false,
      error: null,
    });
    renderPage();
    expect(screen.queryByText('覆盖度')).not.toBeInTheDocument();
  });
```

- [ ] **Step 2: 运行测试确认失败**

Run:
```bash
cd /Users/dreambt/sources/etf-radar/frontend && npx vitest run src/pages/__tests__/RotationPage.test.tsx 2>&1 | tail -20
```
Expected: 至少 1 个新 case FAIL (renders health bar when themes are ready 找不到 "覆盖度")

- [ ] **Step 3: 修改 RotationPage 接入 HealthBar**

将 `frontend/src/pages/RotationPage.tsx` 完整替换为：

```tsx
import { useMemo } from 'react';
import { useDataContext } from '@/providers/dataContext';
import { useSnapshotsTimeline } from '@/hooks/useSnapshotsTimeline';
import { RotationTrailsOverlay } from '@/components/rotation/RotationTrailsOverlay';
import { QuadrantLegend } from '@/components/rotation/QuadrantLegend';
import { RotationHealthBar } from '@/components/rotation/RotationHealthBar';
import { computeRotationHealth } from '@/lib/rotationHealth';
import { Alert, AlertDescription } from '@/components/ui/alert';

export const RotationPage = () => {
  const { themes, isLoading, error } = useDataContext();
  const { snapshotsFrames } = useSnapshotsTimeline();

  // Health 必须在所有 hooks 调用完成后计算 (即便提前 return). 用 useMemo 缓存,
  // themes.themes 变化时自动重算 (滑动时间轴 / 数据刷新).
  // 注: 当前 RotationPage 无时间轴 slider, 数据源为 dataContext (=最新快照).
  // 未来加 slider 时改用 useSnapshotsTimeline().frame?.themes 即可.
  const health = useMemo(
    () => (themes?.themes ? computeRotationHealth(themes.themes) : null),
    [themes?.themes],
  );

  if (isLoading) {
    return <div data-testid="rotation-skeleton" className="h-[500px] animate-pulse bg-gray-100 rounded m-4" />;
  }
  if (error) {
    return (
      <Alert variant="destructive" className="m-4">
        <AlertDescription>数据加载失败, 已显示上次成功快照</AlertDescription>
      </Alert>
    );
  }
  if (!themes || themes.themes.length === 0) {
    return (
      <Alert className="m-4">
        <AlertDescription>暂无主题数据</AlertDescription>
      </Alert>
    );
  }

  return (
    <main className="p-4 space-y-4">
      <div className="bg-white border rounded p-4">
        <h2 className="text-lg font-bold mb-2">主题轮动象限图</h2>
        <p className="text-xs text-gray-600 mb-4">
          X 轴为长期强度 (60d), Y 轴为短期强度 (1d), 中线 50 切四象限。气泡大小反映综合排名。
        </p>
        {health && <RotationHealthBar health={health} />}
        <RotationTrailsOverlay themes={themes.themes} snapshots={snapshotsFrames} />
        <QuadrantLegend />
      </div>
    </main>
  );
};
```

- [ ] **Step 4: 运行页面测试确认全部通过**

Run:
```bash
cd /Users/dreambt/sources/etf-radar/frontend && npx vitest run src/pages/__tests__/RotationPage.test.tsx 2>&1 | tail -25
```
Expected: 8 tests passed (4 既有 + 4 新增)

- [ ] **Step 5: 提交**

```bash
cd /Users/dreambt/sources/etf-radar
git add frontend/src/pages/RotationPage.tsx frontend/src/pages/__tests__/RotationPage.test.tsx
git commit -m "feat(rotation): wire RotationHealthBar into RotationPage"
```

---

## Task 8: 最终验证（全套测试 + lint + 手动检视）

**Files:** 无修改，仅运行验证

- [ ] **Step 1: 跑全部 vitest 单元测试**

Run:
```bash
cd /Users/dreambt/sources/etf-radar/frontend && npx vitest run 2>&1 | tail -20
```
Expected: 所有测试通过，无新增失败。重点关注 `rotationHealth.test.ts`、`RotationHealthBar.test.tsx`、`RotationPage.test.tsx`。

- [ ] **Step 2: 跑 ESLint 0 警告（与 CI gate 对齐）**

Run:
```bash
cd /Users/dreambt/sources/etf-radar/frontend && npx eslint src --max-warnings=0 2>&1 | tail -10
```
Expected: 无错误也无警告输出，命令以 exit 0 结束。

如出现警告，常见原因：
- 未使用的导入 → 删除
- 命名冲突 → 重命名
- React Hook 依赖缺失 → 补全或加注释（参考既有 `useSnapshotsTimeline.ts` 注释风格）

- [ ] **Step 3: 启动 dev server 手动检视（可选但推荐）**

Run:
```bash
cd /Users/dreambt/sources/etf-radar/frontend && npm run dev
```
然后浏览器打开 http://localhost:5173/rotation，目视确认：

1. 信息条出现在标题/描述之下、chart 之上
2. 两个 cell 横向并排（桌面），上下堆叠（移动端，可缩窄浏览器宽度验证）
3. 分数数值显示正确，徽章颜色匹配档位
4. 鼠标悬停 cell 显示 tooltip 文字
5. 切换 tab（主题轮动 ↔ ETF 列表）后回来仍正常

- [ ] **Step 4: 跑 e2e（兜底）**

Run:
```bash
cd /Users/dreambt/sources/etf-radar/frontend && npx playwright test rotation.spec.ts 2>&1 | tail -10
```
Expected: 既有 e2e 通过。HealthBar 不在 e2e 选择器范围内，应无回归。

如果 e2e 失败、且失败原因是 HealthBar 影响了既有 selector（如 chart 容器尺寸变化导致点击位置漂移），需要回到 Task 7 调整页面布局或在 e2e 中适配新元素。

- [ ] **Step 5: 最终提交（无修改时跳过）**

如果上述验证没有产生新改动，跳过此步。如果在 Step 3 或 Step 4 中做了小修，先 `git status` 检查，再：

```bash
cd /Users/dreambt/sources/etf-radar
git add -p   # 选择性 stage
git commit -m "fix(rotation): <具体修改说明>"
```

---

## 完成标准

- [ ] 8 个 Task 全部 check 完成
- [ ] `npx vitest run` 全部通过
- [ ] `npx eslint src --max-warnings=0` 0 警告
- [ ] 手动检视：信息条显示正确，颜色与档位一致，tooltip 可读
- [ ] 7 次主体 commit 完成（Task 1, 2, 3, 4, 5, 6, 7 各一次）；Task 8 视情况最多 1 次修复 commit

**预计耗时**：1.5-2 小时（含手动检视）

**风险**：
- ⚠️ `themesToRotationPoints` 当前可能未导出。Task 5 Step 4 已包含检查与修复指引。
- ⚠️ tooltip 用原生 `title` 属性而非 base-ui Tooltip 组件，在移动端 long-press 行为依赖浏览器实现。如需更好移动体验，可在后续迭代中迁移到 Tooltip 组件。
- ⚠️ 阈值 (74/80, 69/77) 是基于 2026 上半年回测的快照。若后续季度市场结构变化（如出现长时间单边趋势），可能需要重新校准 — 这属于运营调参，不属于本次实施范围。
