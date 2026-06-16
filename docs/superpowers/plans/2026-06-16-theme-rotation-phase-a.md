# 主题轮动 Phase A 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `/etf-radar/#/rotation` 上线主题轮动散点象限图, 用 X=strength.long / Y=strength.short 直观展示 14 主题轮动格局, 复用现有 themes.json 不动 backend。

**Architecture:** 引入 HashRouter (react-router-dom@7), 将现有主页拆为 `<RadarPage>` 路由组件, 新增 `<RotationPage>` 路由。散点图基于 Recharts ScatterChart, 数据派生通过纯函数 `themesToRotationPoints`。

**Tech Stack:** React 19 + TypeScript strict + Vite + Recharts + react-router-dom@7 + zod + SWR + Tailwind v4 + vitest

**Spec:** `docs/superpowers/specs/2026-06-16-theme-rotation-design.md`

---

## File Structure

**Created:**
- `frontend/src/types/rotation.ts` — Quadrant / RotationPoint 类型
- `frontend/src/lib/rotation.ts` — 数据派生纯函数 + QUADRANT_COLORS 常量
- `frontend/src/lib/__tests__/rotation.test.ts` — 纯函数测试
- `frontend/src/components/rotation/QuadrantLegend.tsx` — 四象限图例
- `frontend/src/components/rotation/__tests__/QuadrantLegend.test.tsx`
- `frontend/src/components/rotation/ThemeBubbleTooltip.tsx` — hover 卡片
- `frontend/src/components/rotation/__tests__/ThemeBubbleTooltip.test.tsx`
- `frontend/src/components/rotation/RotationScatter.tsx` — 散点图主组件
- `frontend/src/components/rotation/__tests__/RotationScatter.test.tsx`
- `frontend/src/pages/RadarPage.tsx` — 现有主页内容拆出
- `frontend/src/pages/RotationPage.tsx` — 新页面
- `frontend/src/pages/__tests__/RotationPage.test.tsx`
- `frontend/src/__tests__/router.test.tsx` — 路由集成测试

**Modified:**
- `frontend/package.json` — 加 react-router-dom 依赖
- `frontend/src/App.tsx` — 引入 HashRouter + Routes
- `frontend/src/components/Header/RadarTabs.tsx` — 改成 Link

**Untouched (零 backend 改动):**
- backend/**, data/**, config/**, .github/workflows/**

---

## Task 1: 安装 react-router-dom

**Files:**
- Modify: `frontend/package.json`

- [ ] **Step 1: 安装依赖**

```bash
cd frontend && npm install react-router-dom@^7
```

- [ ] **Step 2: 验证 lock 文件更新**

```bash
cd frontend && grep 'react-router-dom' package.json
```

Expected: 显示 `"react-router-dom": "^7.x.x"`

- [ ] **Step 3: Commit**

```bash
git add frontend/package.json frontend/package-lock.json
git commit -m "chore(frontend): add react-router-dom@7 for rotation page routing"
```

---

## Task 2: 类型定义 + 数据派生纯函数 (TDD)

**Files:**
- Create: `frontend/src/types/rotation.ts`
- Create: `frontend/src/lib/rotation.ts`
- Test: `frontend/src/lib/__tests__/rotation.test.ts`

- [ ] **Step 1: 写失败测试**

Create `frontend/src/lib/__tests__/rotation.test.ts`:

```typescript
import { describe, it, expect } from 'vitest';
import { classifyQuadrant, themesToRotationPoints, QUADRANT_COLORS } from '../rotation';
import type { Theme } from '@/types/themes';

const mkTheme = (id: string, long: number, short: number, composite: number): Theme => ({
  id,
  name: id,
  us_etfs: ['X'],
  primary_us: 'X',
  tags: [],
  note: '',
  returns: { r_1d: null, r_5d: null, r_20d: null, r_60d: null, r_120d: null, r_ytd: null },
  strength: { short, mid: 50, long, composite },
  rank: { short: 1, mid: 1, long: 1, composite: 1 },
});

describe('classifyQuadrant', () => {
  it.each([
    [60, 60, 'leading'],
    [30, 60, 'rising'],
    [30, 30, 'lagging'],
    [60, 30, 'fading'],
    [50, 50, 'leading'],
    [49, 49, 'lagging'],
  ] as const)('long=%i short=%i → %s', (long, short, expected) => {
    expect(classifyQuadrant(long, short)).toBe(expected);
  });
});

describe('themesToRotationPoints', () => {
  it('maps strength fields correctly', () => {
    const points = themesToRotationPoints([mkTheme('t1', 75, 80, 95)]);
    expect(points).toHaveLength(1);
    expect(points[0]).toMatchObject({
      themeId: 't1',
      themeName: 't1',
      x: 75,
      y: 80,
      size: 95,
      quadrant: 'leading',
    });
  });

  it('preserves theme order', () => {
    const points = themesToRotationPoints([
      mkTheme('a', 10, 10, 10),
      mkTheme('b', 90, 90, 90),
    ]);
    expect(points.map(p => p.themeId)).toEqual(['a', 'b']);
  });

  it('handles empty array', () => {
    expect(themesToRotationPoints([])).toEqual([]);
  });
});

describe('QUADRANT_COLORS', () => {
  it('exposes 4 quadrant colors', () => {
    expect(Object.keys(QUADRANT_COLORS).sort()).toEqual(['fading', 'lagging', 'leading', 'rising']);
  });
});
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd frontend && npx vitest run src/lib/__tests__/rotation.test.ts
```

Expected: FAIL — "Cannot find module '../rotation'"

- [ ] **Step 3: 创建类型文件**

Create `frontend/src/types/rotation.ts`:

```typescript
export type Quadrant = 'leading' | 'rising' | 'lagging' | 'fading';

export interface RotationPoint {
  themeId: string;
  themeName: string;
  x: number;
  y: number;
  size: number;
  quadrant: Quadrant;
  tags: string[];
}
```

- [ ] **Step 4: 实现 lib/rotation.ts**

Create `frontend/src/lib/rotation.ts`:

```typescript
import type { Theme } from '@/types/themes';
import type { Quadrant, RotationPoint } from '@/types/rotation';

const QUADRANT_THRESHOLD = 50;

export const QUADRANT_COLORS: Record<Quadrant, string> = {
  leading: '#10b981',
  rising:  '#3b82f6',
  lagging: '#6b7280',
  fading:  '#ef4444',
};

export const QUADRANT_LABELS: Record<Quadrant, string> = {
  leading: '持续强势',
  rising:  '新崛起',
  lagging: '持续弱势',
  fading:  '退潮',
};

export function classifyQuadrant(x: number, y: number): Quadrant {
  if (x >= QUADRANT_THRESHOLD && y >= QUADRANT_THRESHOLD) return 'leading';
  if (x <  QUADRANT_THRESHOLD && y >= QUADRANT_THRESHOLD) return 'rising';
  if (x <  QUADRANT_THRESHOLD && y <  QUADRANT_THRESHOLD) return 'lagging';
  return 'fading';
}

export function themesToRotationPoints(themes: Theme[]): RotationPoint[] {
  return themes.map(t => ({
    themeId: t.id,
    themeName: t.name,
    x: t.strength.long,
    y: t.strength.short,
    size: t.strength.composite,
    quadrant: classifyQuadrant(t.strength.long, t.strength.short),
    tags: t.tags,
  }));
}
```

- [ ] **Step 5: 跑测试确认通过**

```bash
cd frontend && npx vitest run src/lib/__tests__/rotation.test.ts
```

Expected: 10 passed

- [ ] **Step 6: Commit**

```bash
git add frontend/src/types/rotation.ts frontend/src/lib/rotation.ts frontend/src/lib/__tests__/rotation.test.ts
git commit -m "feat(rotation): add types and pure quadrant classification fns"
```

---

## Task 3: QuadrantLegend 组件 (TDD)

**Files:**
- Create: `frontend/src/components/rotation/QuadrantLegend.tsx`
- Test: `frontend/src/components/rotation/__tests__/QuadrantLegend.test.tsx`

- [ ] **Step 1: 写失败测试**

Create `frontend/src/components/rotation/__tests__/QuadrantLegend.test.tsx`:

```tsx
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QuadrantLegend } from '../QuadrantLegend';

describe('QuadrantLegend', () => {
  it('renders 4 quadrant labels', () => {
    render(<QuadrantLegend />);
    expect(screen.getByText(/持续强势/)).toBeInTheDocument();
    expect(screen.getByText(/新崛起/)).toBeInTheDocument();
    expect(screen.getByText(/持续弱势/)).toBeInTheDocument();
    expect(screen.getByText(/退潮/)).toBeInTheDocument();
  });

  it('renders explanation text for each quadrant', () => {
    render(<QuadrantLegend />);
    expect(screen.getByText(/长期&短期都强/)).toBeInTheDocument();
    expect(screen.getByText(/长期弱但短期突涨/)).toBeInTheDocument();
    expect(screen.getByText(/长期强但短期跌/)).toBeInTheDocument();
    expect(screen.getByText(/长期&短期都弱/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd frontend && npx vitest run src/components/rotation/__tests__/QuadrantLegend.test.tsx
```

Expected: FAIL — "Cannot find module"

- [ ] **Step 3: 实现组件**

Create `frontend/src/components/rotation/QuadrantLegend.tsx`:

```tsx
import { QUADRANT_COLORS, QUADRANT_LABELS } from '@/lib/rotation';
import type { Quadrant } from '@/types/rotation';

const ROWS: { q: Quadrant; desc: string }[] = [
  { q: 'leading', desc: '长期&短期都强 — 趋势龙头, 续航空间需评估' },
  { q: 'rising',  desc: '长期弱但短期突涨 — 早期信号, 关注资金流入' },
  { q: 'fading',  desc: '长期强但短期跌 — 警惕高位回调' },
  { q: 'lagging', desc: '长期&短期都弱 — 暂观望' },
];

export const QuadrantLegend = () => (
  <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-xs mt-4">
    {ROWS.map(({ q, desc }) => (
      <div key={q} className="flex items-center gap-2">
        <span
          className="inline-block w-3 h-3 rounded-full shrink-0"
          style={{ backgroundColor: QUADRANT_COLORS[q] }}
          aria-hidden
        />
        <span className="font-medium">{QUADRANT_LABELS[q]}</span>
        <span className="text-gray-600">| {desc}</span>
      </div>
    ))}
  </div>
);
```

- [ ] **Step 4: 跑测试确认通过**

```bash
cd frontend && npx vitest run src/components/rotation/__tests__/QuadrantLegend.test.tsx
```

Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/rotation/QuadrantLegend.tsx frontend/src/components/rotation/__tests__/QuadrantLegend.test.tsx
git commit -m "feat(rotation): add QuadrantLegend with color swatches and explanations"
```

---

## Task 4: ThemeBubbleTooltip 组件 (TDD)

**Files:**
- Create: `frontend/src/components/rotation/ThemeBubbleTooltip.tsx`
- Test: `frontend/src/components/rotation/__tests__/ThemeBubbleTooltip.test.tsx`

- [ ] **Step 1: 写失败测试**

Create `frontend/src/components/rotation/__tests__/ThemeBubbleTooltip.test.tsx`:

```tsx
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ThemeBubbleTooltip } from '../ThemeBubbleTooltip';
import type { Theme } from '@/types/themes';

const mockTheme: Theme = {
  id: 'storage_dram',
  name: '存储芯片',
  us_etfs: ['DRAM', 'SOXX', 'SMH'],
  primary_us: 'DRAM',
  tags: ['DRAM', 'NAND', '半导体'],
  note: '',
  returns: { r_1d: -0.0017, r_5d: 0.1529, r_20d: 0.1895, r_60d: null, r_120d: null, r_ytd: 0.8509 },
  strength: { short: 99, mid: 93, long: 99, composite: 97 },
  rank: { short: 1, mid: 1, long: 1, composite: 1 },
};

describe('ThemeBubbleTooltip', () => {
  it('renders nothing when inactive', () => {
    const { container } = render(
      <ThemeBubbleTooltip active={false} payload={[]} theme={mockTheme} />
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders theme name and ranks when active', () => {
    render(
      <ThemeBubbleTooltip active payload={[{ payload: { themeId: 'storage_dram' } }]} theme={mockTheme} />
    );
    expect(screen.getByText('存储芯片')).toBeInTheDocument();
    expect(screen.getByText(/composite 97/)).toBeInTheDocument();
    expect(screen.getByText(/strength.short 99/)).toBeInTheDocument();
  });

  it('renders formatted returns', () => {
    render(
      <ThemeBubbleTooltip active payload={[{ payload: { themeId: 'storage_dram' } }]} theme={mockTheme} />
    );
    expect(screen.getByText(/-0.17%/)).toBeInTheDocument();
    expect(screen.getByText(/\+15.29%/)).toBeInTheDocument();
    expect(screen.getByText(/\+85.09%/)).toBeInTheDocument();
  });

  it('renders tags and primary ETF', () => {
    render(
      <ThemeBubbleTooltip active payload={[{ payload: { themeId: 'storage_dram' } }]} theme={mockTheme} />
    );
    expect(screen.getByText(/DRAM, NAND, 半导体/)).toBeInTheDocument();
    expect(screen.getByText(/DRAM \+ SOXX, SMH/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd frontend && npx vitest run src/components/rotation/__tests__/ThemeBubbleTooltip.test.tsx
```

Expected: FAIL — "Cannot find module"

- [ ] **Step 3: 实现组件**

Create `frontend/src/components/rotation/ThemeBubbleTooltip.tsx`:

```tsx
import type { Theme } from '@/types/themes';

const pct = (v: number | null): string => {
  if (v === null) return '-';
  const sign = v >= 0 ? '+' : '';
  return `${sign}${(v * 100).toFixed(2)}%`;
};

interface TooltipProps {
  active?: boolean;
  payload?: Array<{ payload?: { themeId?: string } }>;
  theme: Theme;
}

export const ThemeBubbleTooltip = ({ active, payload, theme }: TooltipProps) => {
  if (!active || !payload || payload.length === 0) return null;
  const { strength, rank, returns, tags, primary_us, us_etfs } = theme;
  const otherEtfs = us_etfs.filter(e => e !== primary_us).join(', ');

  return (
    <div className="bg-white border rounded shadow-lg p-3 text-xs space-y-2 max-w-xs">
      <div className="font-bold text-sm">{theme.name}</div>
      <div className="border-t pt-2 space-y-1">
        <div className="flex justify-between"><span>综合排名 #{rank.composite}</span><span>composite {strength.composite}</span></div>
        <div className="flex justify-between"><span>短期(1d) #{rank.short}</span><span>strength.short {strength.short}</span></div>
        <div className="flex justify-between"><span>中期(5d) #{rank.mid}</span><span>strength.mid {strength.mid}</span></div>
        <div className="flex justify-between"><span>长期(60d) #{rank.long}</span><span>strength.long {strength.long}</span></div>
      </div>
      <div className="border-t pt-2 grid grid-cols-2 gap-x-2 gap-y-0.5">
        <div>1d: {pct(returns.r_1d)}</div>
        <div>5d: {pct(returns.r_5d)}</div>
        <div>20d: {pct(returns.r_20d)}</div>
        <div>60d: {pct(returns.r_60d)}</div>
        <div className="col-span-2">YTD: {pct(returns.r_ytd)}</div>
      </div>
      <div className="border-t pt-2 space-y-0.5">
        <div>标签: {tags.join(', ')}</div>
        <div>主 ETF: {primary_us}{otherEtfs && ` + ${otherEtfs}`}</div>
      </div>
    </div>
  );
};
```

- [ ] **Step 4: 跑测试确认通过**

```bash
cd frontend && npx vitest run src/components/rotation/__tests__/ThemeBubbleTooltip.test.tsx
```

Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/rotation/ThemeBubbleTooltip.tsx frontend/src/components/rotation/__tests__/ThemeBubbleTooltip.test.tsx
git commit -m "feat(rotation): add ThemeBubbleTooltip with ranks/returns/tags"
```

---

## Task 5: RotationScatter 散点图组件 (TDD)

**Files:**
- Create: `frontend/src/components/rotation/RotationScatter.tsx`
- Test: `frontend/src/components/rotation/__tests__/RotationScatter.test.tsx`

- [ ] **Step 1: 写失败测试**

Create `frontend/src/components/rotation/__tests__/RotationScatter.test.tsx`:

```tsx
import { describe, it, expect, vi } from 'vitest';
import { render } from '@testing-library/react';
import { RotationScatter } from '../RotationScatter';
import type { Theme } from '@/types/themes';

const mkTheme = (id: string, long: number, short: number, composite: number): Theme => ({
  id,
  name: id,
  us_etfs: ['X'],
  primary_us: 'X',
  tags: [],
  note: '',
  returns: { r_1d: null, r_5d: null, r_20d: null, r_60d: null, r_120d: null, r_ytd: null },
  strength: { short, mid: 50, long, composite },
  rank: { short: 1, mid: 1, long: 1, composite: 1 },
});

// Recharts 在 jsdom 下 ResponsiveContainer 默认宽 0; stub 一个固定宽度
vi.mock('recharts', async () => {
  const actual = await vi.importActual<typeof import('recharts')>('recharts');
  return {
    ...actual,
    ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
      <div data-testid="rc-container" style={{ width: 800, height: 500 }}>{children}</div>
    ),
  };
});

describe('RotationScatter', () => {
  it('renders without crash given themes', () => {
    const themes = [
      mkTheme('a', 80, 80, 90),
      mkTheme('b', 30, 80, 60),
      mkTheme('c', 30, 30, 40),
      mkTheme('d', 80, 30, 50),
    ];
    const { container, getByTestId } = render(<RotationScatter themes={themes} />);
    expect(getByTestId('rc-container')).toBeInTheDocument();
    // Recharts 渲染出 SVG
    expect(container.querySelector('svg')).toBeInTheDocument();
  });

  it('renders empty without crash', () => {
    const { getByTestId } = render(<RotationScatter themes={[]} />);
    expect(getByTestId('rc-container')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd frontend && npx vitest run src/components/rotation/__tests__/RotationScatter.test.tsx
```

Expected: FAIL — "Cannot find module"

- [ ] **Step 3: 实现组件**

Create `frontend/src/components/rotation/RotationScatter.tsx`:

```tsx
import {
  ResponsiveContainer, ScatterChart, Scatter, XAxis, YAxis,
  CartesianGrid, ReferenceLine, ReferenceArea, Tooltip, Cell, LabelList,
} from 'recharts';
import { useNavigate } from 'react-router-dom';
import { themesToRotationPoints, QUADRANT_COLORS } from '@/lib/rotation';
import { ThemeBubbleTooltip } from './ThemeBubbleTooltip';
import type { Theme } from '@/types/themes';

interface Props {
  themes: Theme[];
  height?: number;
}

const computeBubbleSize = (composite: number): number => 8 + (composite / 99) * 12;

export const RotationScatter = ({ themes, height = 500 }: Props) => {
  const navigate = useNavigate();
  const points = themesToRotationPoints(themes).map(p => ({
    ...p,
    _bubbleSize: computeBubbleSize(p.size),
  }));
  const themeById = new Map(themes.map(t => [t.id, t]));

  return (
    <ResponsiveContainer width="100%" height={height}>
      <ScatterChart margin={{ top: 24, right: 24, bottom: 48, left: 24 }}>
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis
          type="number" dataKey="x" domain={[0, 100]}
          label={{ value: '长期强度 (60d)', position: 'insideBottom', offset: -10 }}
        />
        <YAxis
          type="number" dataKey="y" domain={[0, 100]}
          label={{ value: '短期强度 (1d)', angle: -90, position: 'insideLeft' }}
        />
        <ReferenceLine x={50} stroke="#94a3b8" strokeDasharray="3 3" />
        <ReferenceLine y={50} stroke="#94a3b8" strokeDasharray="3 3" />
        <ReferenceArea x1={50} x2={100} y1={50} y2={100} fill={QUADRANT_COLORS.leading} fillOpacity={0.05} />
        <ReferenceArea x1={0}  x2={50}  y1={50} y2={100} fill={QUADRANT_COLORS.rising}  fillOpacity={0.05} />
        <ReferenceArea x1={0}  x2={50}  y1={0}  y2={50}  fill={QUADRANT_COLORS.lagging} fillOpacity={0.05} />
        <ReferenceArea x1={50} x2={100} y1={0}  y2={50}  fill={QUADRANT_COLORS.fading}  fillOpacity={0.05} />
        <Tooltip
          cursor={{ strokeDasharray: '3 3' }}
          content={(props) => {
            const themeId = props.payload?.[0]?.payload?.themeId as string | undefined;
            const theme = themeId ? themeById.get(themeId) : undefined;
            if (!theme) return null;
            return <ThemeBubbleTooltip {...props} theme={theme} />;
          }}
        />
        <Scatter
          data={points}
          onClick={(p) => p?.themeId && navigate(`/?theme=${p.themeId}`)}
        >
          {points.map(p => (
            <Cell key={p.themeId} fill={QUADRANT_COLORS[p.quadrant]} />
          ))}
          <LabelList dataKey="themeName" position="top" style={{ fontSize: 11 }} />
        </Scatter>
      </ScatterChart>
    </ResponsiveContainer>
  );
};
```

- [ ] **Step 4: 跑测试确认通过**

```bash
cd frontend && npx vitest run src/components/rotation/__tests__/RotationScatter.test.tsx
```

Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/rotation/RotationScatter.tsx frontend/src/components/rotation/__tests__/RotationScatter.test.tsx
git commit -m "feat(rotation): add RotationScatter chart with quadrants and bubble sizing"
```

---

## Task 6: 拆出 RadarPage + 创建 RotationPage + App.tsx 引入 HashRouter

**Files:**
- Create: `frontend/src/pages/RadarPage.tsx`
- Create: `frontend/src/pages/RotationPage.tsx`
- Create: `frontend/src/pages/__tests__/RotationPage.test.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: 写 RotationPage 失败测试**

Create `frontend/src/pages/__tests__/RotationPage.test.tsx`:

```tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { RotationPage } from '../RotationPage';

vi.mock('recharts', async () => {
  const actual = await vi.importActual<typeof import('recharts')>('recharts');
  return {
    ...actual,
    ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
      <div data-testid="rc-container" style={{ width: 800, height: 500 }}>{children}</div>
    ),
  };
});

const mockUseDataContext = vi.fn();
vi.mock('@/providers/DataProvider', () => ({
  useDataContext: () => mockUseDataContext(),
}));

const renderPage = () =>
  render(
    <MemoryRouter>
      <RotationPage />
    </MemoryRouter>,
  );

describe('RotationPage', () => {
  it('renders skeleton when loading', () => {
    mockUseDataContext.mockReturnValue({ themes: undefined, isLoading: true, error: null });
    renderPage();
    expect(screen.getByTestId('rotation-skeleton')).toBeInTheDocument();
  });

  it('renders error alert when error', () => {
    mockUseDataContext.mockReturnValue({ themes: undefined, isLoading: false, error: new Error('boom') });
    renderPage();
    expect(screen.getByText(/数据加载失败/)).toBeInTheDocument();
  });

  it('renders empty alert when no themes', () => {
    mockUseDataContext.mockReturnValue({
      themes: { schema_version: '1.0', generated_at: '', themes: [] },
      isLoading: false, error: null,
    });
    renderPage();
    expect(screen.getByText(/暂无主题数据/)).toBeInTheDocument();
  });

  it('renders scatter and legend when data ready', () => {
    mockUseDataContext.mockReturnValue({
      themes: {
        schema_version: '1.0', generated_at: '',
        themes: [{
          id: 't1', name: 'T1', us_etfs: ['X'], primary_us: 'X', tags: [], note: '',
          returns: { r_1d: null, r_5d: null, r_20d: null, r_60d: null, r_120d: null, r_ytd: null },
          strength: { short: 80, mid: 50, long: 80, composite: 90 },
          rank: { short: 1, mid: 1, long: 1, composite: 1 },
        }],
      },
      isLoading: false, error: null,
    });
    renderPage();
    expect(screen.getByTestId('rc-container')).toBeInTheDocument();
    expect(screen.getByText(/持续强势/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd frontend && npx vitest run src/pages/__tests__/RotationPage.test.tsx
```

Expected: FAIL — "Cannot find module"

- [ ] **Step 3: 创建 RotationPage**

Create `frontend/src/pages/RotationPage.tsx`:

```tsx
import { useDataContext } from '@/providers/DataProvider';
import { RotationScatter } from '@/components/rotation/RotationScatter';
import { QuadrantLegend } from '@/components/rotation/QuadrantLegend';
import { Alert, AlertDescription } from '@/components/ui/alert';

export const RotationPage = () => {
  const { themes, isLoading, error } = useDataContext();

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
        <RotationScatter themes={themes.themes} />
        <QuadrantLegend />
      </div>
    </main>
  );
};
```

- [ ] **Step 4: 跑测试确认通过**

```bash
cd frontend && npx vitest run src/pages/__tests__/RotationPage.test.tsx
```

Expected: 4 passed

- [ ] **Step 5: 创建 RadarPage (拆出现有主页内容)**

Create `frontend/src/pages/RadarPage.tsx`:

```tsx
import { FilterBar } from '@/components/FilterBar';
import { ThemeList } from '@/components/ThemeList';
import { ThemeDetail } from '@/components/ThemeDetail';
import { CnEtfTable } from '@/components/CnEtfTable';

export const RadarPage = () => (
  <>
    <FilterBar />
    <main className="p-4 grid grid-cols-1 lg:grid-cols-2 gap-4">
      <ThemeList />
      <ThemeDetail />
    </main>
    <div className="px-4 pb-8">
      <CnEtfTable />
    </div>
  </>
);
```

- [ ] **Step 6: 改造 App.tsx 引入 HashRouter**

Replace `frontend/src/App.tsx` 内容:

```tsx
import { HashRouter, Routes, Route } from 'react-router-dom';
import { DataProvider } from '@/providers/DataProvider';
import { UIStateProvider } from '@/providers/UIStateProvider';
import { Header } from '@/components/Header';
import { RadarPage } from '@/pages/RadarPage';
import { RotationPage } from '@/pages/RotationPage';

export default function App() {
  return (
    <DataProvider>
      <UIStateProvider>
        <HashRouter>
          <div className="min-h-screen bg-gray-50">
            <Header />
            <Routes>
              <Route path="/" element={<RadarPage />} />
              <Route path="/rotation" element={<RotationPage />} />
            </Routes>
          </div>
        </HashRouter>
      </UIStateProvider>
    </DataProvider>
  );
}
```

- [ ] **Step 7: 跑全部测试**

```bash
cd frontend && npx vitest run
```

Expected: all tests pass (existing 27 + new ~16)

- [ ] **Step 8: Commit**

```bash
git add frontend/src/pages/ frontend/src/App.tsx
git commit -m "feat(routing): add HashRouter with RadarPage + RotationPage"
```

---

## Task 7: 改造 RadarTabs 使用 react-router Link

**Files:**
- Modify: `frontend/src/components/Header/RadarTabs.tsx`
- Test: `frontend/src/components/Header/__tests__/RadarTabs.test.tsx`

- [ ] **Step 1: 写失败测试**

Create `frontend/src/components/Header/__tests__/RadarTabs.test.tsx`:

```tsx
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { RadarTabs } from '../RadarTabs';

const renderAt = (path: string) =>
  render(
    <MemoryRouter initialEntries={[path]}>
      <RadarTabs />
    </MemoryRouter>,
  );

describe('RadarTabs', () => {
  it('renders 3 tab links', () => {
    renderAt('/');
    expect(screen.getByText('跨市雷达').closest('a')).toHaveAttribute('href', '/');
    expect(screen.getByText('主题轮动').closest('a')).toHaveAttribute('href', '/rotation');
    expect(screen.getByText(/持仓监控/)).toBeInTheDocument();
  });

  it('marks active tab when on root path', () => {
    renderAt('/');
    const radarLink = screen.getByText('跨市雷达').closest('a')!;
    expect(radarLink.className).toMatch(/bg-blue-600/);
  });

  it('marks rotation tab active on /rotation', () => {
    renderAt('/rotation');
    const rotationLink = screen.getByText('主题轮动').closest('a')!;
    expect(rotationLink.className).toMatch(/bg-blue-600/);
  });
});
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd frontend && npx vitest run src/components/Header/__tests__/RadarTabs.test.tsx
```

Expected: FAIL — getByText('跨市雷达').closest('a') 返回 null (现在还是 button)

- [ ] **Step 3: 改造 RadarTabs**

Replace `frontend/src/components/Header/RadarTabs.tsx` 内容:

```tsx
import { Link, useLocation } from 'react-router-dom';

const linkClass = (active: boolean): string =>
  active
    ? 'px-3 py-1 rounded bg-blue-600 text-white'
    : 'px-3 py-1 rounded text-gray-700 hover:bg-gray-100';

export const RadarTabs = () => {
  const { pathname } = useLocation();
  return (
    <div className="flex gap-1 text-sm">
      <Link to="/" className={linkClass(pathname === '/')}>跨市雷达</Link>
      <Link to="/rotation" className={linkClass(pathname === '/rotation')}>主题轮动</Link>
      <span
        className="px-3 py-1 rounded text-gray-400 cursor-not-allowed"
        aria-disabled
      >
        持仓监控 (v3)
      </span>
    </div>
  );
};
```

- [ ] **Step 4: 跑测试确认通过**

```bash
cd frontend && npx vitest run src/components/Header/__tests__/RadarTabs.test.tsx
```

Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/Header/RadarTabs.tsx frontend/src/components/Header/__tests__/RadarTabs.test.tsx
git commit -m "feat(header): replace placeholder RadarTabs buttons with router Links"
```

---

## Task 8: 路由集成测试

**Files:**
- Create: `frontend/src/__tests__/router.test.tsx`

- [ ] **Step 1: 写集成测试**

Create `frontend/src/__tests__/router.test.tsx`:

```tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { RadarPage } from '@/pages/RadarPage';
import { RotationPage } from '@/pages/RotationPage';

vi.mock('recharts', async () => {
  const actual = await vi.importActual<typeof import('recharts')>('recharts');
  return {
    ...actual,
    ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
      <div data-testid="rc-container" style={{ width: 800, height: 500 }}>{children}</div>
    ),
  };
});

vi.mock('@/providers/DataProvider', () => ({
  useDataContext: () => ({
    themes: {
      schema_version: '1.0', generated_at: '',
      themes: [{
        id: 't1', name: 'T1', us_etfs: ['X'], primary_us: 'X', tags: [], note: '',
        returns: { r_1d: null, r_5d: null, r_20d: null, r_60d: null, r_120d: null, r_ytd: null },
        strength: { short: 50, mid: 50, long: 50, composite: 50 },
        rank: { short: 1, mid: 1, long: 1, composite: 1 },
      }],
    },
    etfs: { schema_version: '1.0', generated_at: '', etfs: [] },
    signals: { schema_version: '1.0', generated_at: '', signals: [] },
    meta: { schema_version: '1.0', generated_at: '', as_of: '', stale_minutes: 0 },
    isLoading: false, error: null,
  }),
}));

vi.mock('@/providers/UIStateProvider', () => ({
  useUIState: () => ({
    selectedDim: 'composite', setSelectedDim: vi.fn(),
    selectedSignal: 'all', setSelectedSignal: vi.fn(),
    search: '', setSearch: vi.fn(),
    selectedThemeId: null, setSelectedThemeId: vi.fn(),
  }),
}));

const renderAt = (path: string) =>
  render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/" element={<RadarPage />} />
        <Route path="/rotation" element={<RotationPage />} />
      </Routes>
    </MemoryRouter>,
  );

describe('Router integration', () => {
  it('renders RadarPage on /', () => {
    renderAt('/');
    expect(screen.queryByTestId('rc-container')).toBeNull();
    // RadarPage 不应渲染散点图容器
  });

  it('renders RotationPage on /rotation', () => {
    renderAt('/rotation');
    expect(screen.getByTestId('rc-container')).toBeInTheDocument();
    expect(screen.getByText(/持续强势/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: 跑测试确认通过**

```bash
cd frontend && npx vitest run src/__tests__/router.test.tsx
```

Expected: 2 passed

如果失败 (常见: UIStateProvider mock 不全), 补齐 mock 字段后重跑。

- [ ] **Step 3: Commit**

```bash
git add frontend/src/__tests__/router.test.tsx
git commit -m "test(router): integration test for / and /rotation routes"
```

---

## Task 9: 移动端响应式 (RotationScatter)

**Files:**
- Modify: `frontend/src/components/rotation/RotationScatter.tsx`

- [ ] **Step 1: 加 useEffect 监听 media query**

修改 `frontend/src/components/rotation/RotationScatter.tsx`, 在 `RotationScatter` 组件顶部加 hook:

```tsx
import { useEffect, useState } from 'react';
// ...其余 imports 不变

const useIsMobile = (): boolean => {
  const [isMobile, setIsMobile] = useState(
    typeof window !== 'undefined' && window.matchMedia('(max-width: 768px)').matches,
  );
  useEffect(() => {
    if (typeof window === 'undefined') return;
    const mql = window.matchMedia('(max-width: 768px)');
    const handler = (e: MediaQueryListEvent) => setIsMobile(e.matches);
    mql.addEventListener('change', handler);
    return () => mql.removeEventListener('change', handler);
  }, []);
  return isMobile;
};
```

修改 `RotationScatter` 内部使用:

```tsx
export const RotationScatter = ({ themes, height }: Props) => {
  const navigate = useNavigate();
  const isMobile = useIsMobile();
  const effectiveHeight = height ?? (isMobile ? 360 : 500);
  const labelFontSize = isMobile ? 9 : 11;
  // ... 后续 JSX 中:
  // - <ResponsiveContainer width="100%" height={effectiveHeight}>
  // - <LabelList ... style={{ fontSize: labelFontSize }} />
```

- [ ] **Step 2: 跑测试确认现有测试仍通过**

```bash
cd frontend && npx vitest run src/components/rotation/
```

Expected: all rotation tests pass

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/rotation/RotationScatter.tsx
git commit -m "feat(rotation): mobile-responsive height and label font size"
```

---

## Task 10: 最终验证 (lint + typecheck + build + 全套测试)

**Files:** 无文件变更, 仅验证

- [ ] **Step 1: 跑全套测试**

```bash
cd frontend && npx vitest run
```

Expected: all passed (原 27 + 新增 ~20 = ~47 passed)

- [ ] **Step 2: lint + typecheck**

```bash
cd frontend && npm run lint
```

Expected: 0 errors. 如有报错, 修正后回到 Step 1。

- [ ] **Step 3: build**

```bash
cd frontend && npm run build
```

Expected: 成功生成 `dist/`, bundle size 接近 + 30KB (react-router-dom)

- [ ] **Step 4: 本地手动验证 (可选)**

```bash
cd frontend && npm run dev
```

浏览器打开 `http://localhost:5173/etf-radar/`:
- 点击 "主题轮动" tab → URL 变为 `#/rotation`, 散点图渲染
- F5 刷新当前页 → 仍在 `/rotation`, 不 404
- 点击气泡 → 跳回 `/?theme=<id>`

- [ ] **Step 5: 更新 README 增加 v0.2 入口说明**

修改 `README.md` 在 "在线访问" 之后加一节 "页面":

```markdown
## 页面 (v0.2+)

- `/` 跨市雷达 (默认) — 14 主题列表 + 信号详情 + A 股 ETF 映射
- `/rotation` 主题轮动 — 散点象限图, X=长期强度 Y=短期强度, 中线 50 切四象限
```

- [ ] **Step 6: Final commit**

```bash
git add README.md
git commit -m "docs(readme): document rotation page"
```

- [ ] **Step 7: Push**

```bash
git push
```

Expected: GitHub Actions 自动触发 deploy-frontend (因为 frontend/** 变更), 数分钟后 `https://im47.cn/etf-radar/#/rotation` 可访问。

---

## Self-Review Summary

**Spec coverage:**
- ✅ §1 目标 → Task 5-7 实现散点图 + 路由
- ✅ §2 架构 (HashRouter / 组件树) → Task 1, 6
- ✅ §3 Phase A (数据/Recharts/Tooltip/图例/响应式) → Task 2-5, 9
- ✅ §5 测试 (单元/组件/集成) → 每个 Task TDD 步骤
- ⏭️ §4 Phase B → 本 plan 不包含, 等数据累积后单独写 plan

**Placeholder scan:** 已扫描, 无 TBD/TODO/省略号。每个代码块完整。

**Type consistency:** RotationPoint 字段 (themeId/themeName/x/y/size/quadrant/tags) 在 Task 2 定义, Task 3-6 测试使用一致。

**关键风险已在 spec §6.1 记录, 实施时遵循:**
- R2 (标签重叠) 留待 Task 10 手动验证, 必要时单独 patch
- R5 (composite 极值集中) 同上
