# MarketView 全局市场视角 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 RotationPage 局部的 `RotationMode` 升级为全局 `MarketView` 三态 (`us` / `cn-all` / `cn-only`),让 ThemeList、RotationScatter、ThemeRow 强度、头部文案统一联动,同时解掉 Final reviewer 标记的 Blocker (ThemeList 头部硬编码 "美股主题强弱") 与 3 项 deferred (trailGradient mode-aware、isCnOnly helper、ThemeList 集成测试)。

**Architecture:**
- `UIState` 新增 `marketView: 'us' | 'cn-all' | 'cn-only'`,走 URL params `mv` (与 dim/sig 一致,默认 `us` 不写入)。同时**移除** `onlyCnOnly` 与 `SET_ONLY_CN_ONLY` action (语义被 `cn-only` 包含)。
- 新增 `MarketViewSelector` (3 段按钮,FilterBar 内替换 `OnlyCnOnlyToggle`),**删除** `OnlyCnOnlyToggle.tsx` 与 RotationPage 内的 `ModeToggle` 引用 (但保留 `ModeToggle.tsx` 文件供旧测试,Task 4 一并删)。
- `MarketView → RotationMode` 派生: `us → 'us'`,`cn-all/cn-only → 'cn'`。
- ThemeList / ThemeRow 按 marketView 选 strength 字段、过滤主题集、改变头部文案。
- `trailGradient.buildTrails` 新增 `mode` 参数,从对应 `us_strength`/`cn_strength` 取值 (旧 schema 1.0 fallback 到 `strength`)。
- 新增 `lib/marketView.ts` 集中 helper: `isCnOnly(t)`、`pickStrength(t, mv)`、`themeMatchesView(t, mv)`、`marketViewToRotationMode(mv)`。

**Tech Stack:** React 19 + TypeScript + Vitest + React Testing Library + Zod + React Router HashRouter useSearchParams。

---

## 文件结构

**新增:**
- `frontend/src/lib/marketView.ts` — 集中所有 marketView 派生逻辑 (DRY,避免散落判断)
- `frontend/src/lib/__tests__/marketView.test.ts` — helper 单元测试
- `frontend/src/components/FilterBar/MarketViewSelector.tsx` — 3 段按钮控件,替代 OnlyCnOnlyToggle
- `frontend/src/components/FilterBar/__tests__/MarketViewSelector.test.tsx` — 控件交互测试
- `frontend/src/components/ThemeList/__tests__/ThemeList.test.tsx` — 集成测试 (顺手清掉 deferred #3)

**修改:**
- `frontend/src/providers/uiStateContext.ts` — UIState 加 `marketView`,Action 加 `SET_MARKET_VIEW`,**移除** `onlyCnOnly` + `SET_ONLY_CN_ONLY` (语义被 cn-only 包含)
- `frontend/src/providers/UIStateProvider.tsx` — URL params `mv` 解析/写回,**删** `onlyCnOnly` useState
- `frontend/src/types/uiState.ts` (若不存在则在 uiStateContext 内) — 新增 `MarketView` 类型
- `frontend/src/components/FilterBar/index.tsx` — 渲染顺序 `MarketViewSelector` 替换 `OnlyCnOnlyToggle`
- `frontend/src/components/ThemeList/index.tsx` — `visible` 改为 `themeMatchesView`,排序改为 `pickStrength(...)[dim]`,头部文案 mode-aware
- `frontend/src/components/ThemeList/ThemeRow.tsx` — 强度数字与"近1日/近1周"对应主题集判定改为 mode-aware (强度数;returns 仍取 theme.returns,所有 returns 都从主 ETF 来,与市场无关)
- `frontend/src/lib/trailGradient.ts` — `buildTrails` 加 `mode: RotationMode` 参数,从 `us_strength`/`cn_strength` 取值,旧快照回退 `theme.strength`
- `frontend/src/lib/__tests__/trailGradient.test.ts` — 加 mode 维度测试 (顺手清掉 deferred #1)
- `frontend/src/components/rotation/RotationScatterWithTrails.tsx` — `buildTrails(trailFrames, effectiveMode)` (mode 传透)
- `frontend/src/components/rotation/RotationTrailsOverlay.tsx` — mode 从 Context 派生 (不再走 prop)
- `frontend/src/pages/RotationPage.tsx` — 删 `useState<RotationMode>`,删 ModeToggle 渲染,marketView 从 Context 取并 derive RotationMode 传子组件
- `frontend/src/components/MappingPanel.tsx` (Task 12 留下,路径以实际为准) — 不改逻辑,但用 `isCnOnly` 替换 `theme.primary_us === null` (顺手清掉 deferred #2)

**删除:**
- `frontend/src/components/FilterBar/OnlyCnOnlyToggle.tsx` (功能并入 MarketViewSelector)
- `frontend/src/components/FilterBar/__tests__/OnlyCnOnlyToggle.test.tsx` (若存在)
- `frontend/src/components/rotation/ModeToggle.tsx` 与其测试 (功能并入 MarketViewSelector)

---

## Task 1: MarketView 类型 + UIState + helper 库

**Files:**
- Create: `frontend/src/lib/marketView.ts`
- Create: `frontend/src/lib/__tests__/marketView.test.ts`
- Modify: `frontend/src/providers/uiStateContext.ts`

- [ ] **Step 1.1: 写 marketView helper 失败测试**

`frontend/src/lib/__tests__/marketView.test.ts`:
```ts
import { describe, it, expect } from 'vitest';
import {
  isCnOnly,
  pickStrength,
  themeMatchesView,
  marketViewToRotationMode,
} from '@/lib/marketView';
import type { Theme } from '@/types/themes';

const mkStrength = (n: number) => ({ short: n, mid: n, long: n, composite: n });

const mapped: Theme = {
  id: 'ai', name: 'AI', us_etfs: ['BOTZ'],
  primary_us: 'BOTZ', primary_cn: '159819',
  tags: [], note: '',
  returns: { r_1d: 0, r_5d: 0, r_20d: 0, r_60d: 0, r_120d: 0, r_ytd: 0 },
  strength: mkStrength(50),
  us_strength: mkStrength(60),
  cn_strength: mkStrength(40),
  rank: { short: 1, mid: 1, long: 1, composite: 1 },
};

const cnOnly: Theme = {
  ...mapped, id: 'cn_liquor', name: '白酒',
  us_etfs: [], primary_us: null, primary_cn: '512690',
  us_strength: null,
  cn_strength: mkStrength(70),
};

describe('isCnOnly', () => {
  it('mapped theme returns false', () => expect(isCnOnly(mapped)).toBe(false));
  it('cn-only theme returns true', () => expect(isCnOnly(cnOnly)).toBe(true));
});

describe('pickStrength', () => {
  it('us view picks us_strength', () =>
    expect(pickStrength(mapped, 'us')).toEqual(mkStrength(60)));
  it('cn-all view picks cn_strength', () =>
    expect(pickStrength(mapped, 'cn-all')).toEqual(mkStrength(40)));
  it('cn-only view picks cn_strength', () =>
    expect(pickStrength(cnOnly, 'cn-only')).toEqual(mkStrength(70)));
  it('us view on cn-only returns null', () =>
    expect(pickStrength(cnOnly, 'us')).toBeNull());
});

describe('themeMatchesView', () => {
  it('us hides cn-only', () => {
    expect(themeMatchesView(mapped, 'us')).toBe(true);
    expect(themeMatchesView(cnOnly, 'us')).toBe(false);
  });
  it('cn-all keeps both', () => {
    expect(themeMatchesView(mapped, 'cn-all')).toBe(true);
    expect(themeMatchesView(cnOnly, 'cn-all')).toBe(true);
  });
  it('cn-only keeps only cn-only', () => {
    expect(themeMatchesView(mapped, 'cn-only')).toBe(false);
    expect(themeMatchesView(cnOnly, 'cn-only')).toBe(true);
  });
});

describe('marketViewToRotationMode', () => {
  it('us → us', () => expect(marketViewToRotationMode('us')).toBe('us'));
  it('cn-all → cn', () => expect(marketViewToRotationMode('cn-all')).toBe('cn'));
  it('cn-only → cn', () => expect(marketViewToRotationMode('cn-only')).toBe('cn'));
});
```

- [ ] **Step 1.2: 跑测试确认失败**

```
cd /Users/dreambt/sources/etf-radar/frontend && npx vitest run src/lib/__tests__/marketView.test.ts 2>&1 | tail -15
```
预期: 全失败,模块未定义。

- [ ] **Step 1.3: 实现 marketView.ts**

`frontend/src/lib/marketView.ts`:
```ts
import type { Theme, Strength } from '@/types/themes';
import type { RotationMode } from '@/lib/rotation';

export type MarketView = 'us' | 'cn-all' | 'cn-only';

// 单一事实来源: A 股专属主题判定.
// 旧散落判断 (`theme.primary_us === null`) 全部用此 helper 替换.
export function isCnOnly(t: Theme): boolean {
  return t.primary_us === null;
}

// us → us_strength; cn-all/cn-only → cn_strength.
// cn-only 主题在 us 视角下回 null (与 RotationPoint 已有过滤一致).
export function pickStrength(t: Theme, mv: MarketView): Strength | null {
  return mv === 'us' ? t.us_strength : t.cn_strength;
}

// us 隐藏 cn-only; cn-all 全保留; cn-only 只保留 cn-only.
export function themeMatchesView(t: Theme, mv: MarketView): boolean {
  if (mv === 'us') return !isCnOnly(t);
  if (mv === 'cn-only') return isCnOnly(t);
  return true; // cn-all
}

export function marketViewToRotationMode(mv: MarketView): RotationMode {
  return mv === 'us' ? 'us' : 'cn';
}
```

- [ ] **Step 1.4: 跑测试确认通过**

```
cd /Users/dreambt/sources/etf-radar/frontend && npx vitest run src/lib/__tests__/marketView.test.ts 2>&1 | tail -10
```
预期: 全 PASS。

- [ ] **Step 1.5: 修改 uiStateContext.ts (加 marketView,删 onlyCnOnly)**

`frontend/src/providers/uiStateContext.ts`:
```ts
import { createContext, useContext } from 'react';
import type { DimName } from '@/types/themes';
import type { SignalType } from '@/types/signals';
import type { MarketView } from '@/lib/marketView';

export type SignalFilter = 'all' | SignalType;

export interface UIState {
  selectedThemeId: string | null;
  dimension: DimName;
  signalFilter: SignalFilter;
  searchQuery: string;
  marketView: MarketView;
}

export type UIStateAction =
  | { type: 'SELECT_THEME'; id: string | null }
  | { type: 'SET_DIM'; dim: DimName }
  | { type: 'SET_SIGNAL_FILTER'; v: SignalFilter }
  | { type: 'SET_SEARCH'; q: string }
  | { type: 'SET_MARKET_VIEW'; v: MarketView };

export const UIContext = createContext<{
  state: UIState;
  dispatch: React.Dispatch<UIStateAction>;
} | null>(null);

export const useUIState = (): {
  state: UIState;
  dispatch: React.Dispatch<UIStateAction>;
} => {
  const c = useContext(UIContext);
  if (!c) throw new Error('useUIState must be inside UIStateProvider');
  return c;
};
```

- [ ] **Step 1.6: Commit**

```bash
git add frontend/src/lib/marketView.ts \
        frontend/src/lib/__tests__/marketView.test.ts \
        frontend/src/providers/uiStateContext.ts
git commit -m "feat(ui-state): introduce MarketView type and marketView helpers"
```

---

## Task 2: UIStateProvider URL params + SET_MARKET_VIEW reducer

**Files:**
- Modify: `frontend/src/providers/UIStateProvider.tsx`

- [ ] **Step 2.1: 实现 UIStateProvider 改造**

完整重写 `frontend/src/providers/UIStateProvider.tsx`:
```tsx
import React, { useCallback, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { DimNameSchema, type DimName } from '@/types/themes';
import { SignalTypeSchema } from '@/types/signals';
import type { MarketView } from '@/lib/marketView';
import {
  UIContext,
  type SignalFilter,
  type UIState,
  type UIStateAction,
} from './uiStateContext';

const DEFAULT_DIM: DimName = 'short';
const DEFAULT_SIG: SignalFilter = 'all';
const DEFAULT_MV: MarketView = 'us';

function parseDim(s: string | null): DimName {
  const r = DimNameSchema.safeParse(s);
  return r.success ? r.data : DEFAULT_DIM;
}

function parseSig(s: string | null): SignalFilter {
  if (s === 'all') return 'all';
  const r = SignalTypeSchema.safeParse(s);
  return r.success ? r.data : DEFAULT_SIG;
}

function parseMv(s: string | null): MarketView {
  if (s === 'cn-all' || s === 'cn-only' || s === 'us') return s;
  return DEFAULT_MV;
}

/**
 * URL params 作为 selectedTheme / dim / sig / mv 的单一事实来源.
 * searchQuery 仍仅内存态.
 * 默认值 (`dim=short`, `sig=all`, `mv=us`) 不写入 URL.
 */
export const UIStateProvider: React.FC<{ children: React.ReactNode }> = ({
  children,
}) => {
  const [params, setParams] = useSearchParams();
  const [searchQuery, setSearchQuery] = useState('');

  const themeParam = params.get('theme');
  const dimParam = params.get('dim');
  const sigParam = params.get('sig');
  const mvParam = params.get('mv');

  const state = useMemo<UIState>(
    () => ({
      selectedThemeId: themeParam || null,
      dimension: parseDim(dimParam),
      signalFilter: parseSig(sigParam),
      searchQuery,
      marketView: parseMv(mvParam),
    }),
    [themeParam, dimParam, sigParam, mvParam, searchQuery],
  );

  const dispatch = useCallback<React.Dispatch<UIStateAction>>(
    (a) => {
      if (a.type === 'SET_SEARCH') {
        setSearchQuery(a.q);
        return;
      }
      setParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          switch (a.type) {
            case 'SELECT_THEME':
              if (a.id) next.set('theme', a.id);
              else next.delete('theme');
              break;
            case 'SET_DIM':
              if (a.dim === DEFAULT_DIM) next.delete('dim');
              else next.set('dim', a.dim);
              break;
            case 'SET_SIGNAL_FILTER':
              if (a.v === DEFAULT_SIG) next.delete('sig');
              else next.set('sig', a.v);
              break;
            case 'SET_MARKET_VIEW':
              if (a.v === DEFAULT_MV) next.delete('mv');
              else next.set('mv', a.v);
              break;
          }
          return next;
        },
        { replace: true },
      );
    },
    [setParams],
  );

  const contextValue = useMemo(() => ({ state, dispatch }), [state, dispatch]);

  return (
    <UIContext.Provider value={contextValue}>{children}</UIContext.Provider>
  );
};
```

- [ ] **Step 2.2: 跑全前端测试看回归**

```
cd /Users/dreambt/sources/etf-radar/frontend && npx vitest run 2>&1 | tail -30
```
预期: 因 `OnlyCnOnlyToggle` / `ThemeList` 还引用旧字段会失败 (后续 task 修)。**只允许** OnlyCnOnly/ThemeList/RotationPage 相关测试失败,其他必须 PASS。如有其他文件失败,先停下排查。

- [ ] **Step 2.3: Commit**

```bash
git add frontend/src/providers/UIStateProvider.tsx
git commit -m "feat(ui-state): wire marketView URL param (mv=us|cn-all|cn-only)"
```

---

## Task 3: MarketViewSelector + 删除 OnlyCnOnlyToggle

**Files:**
- Create: `frontend/src/components/FilterBar/MarketViewSelector.tsx`
- Create: `frontend/src/components/FilterBar/__tests__/MarketViewSelector.test.tsx`
- Modify: `frontend/src/components/FilterBar/index.tsx`
- Delete: `frontend/src/components/FilterBar/OnlyCnOnlyToggle.tsx`
- Delete: `frontend/src/components/FilterBar/__tests__/OnlyCnOnlyToggle.test.tsx` (若存在)

- [ ] **Step 3.1: 写 MarketViewSelector 失败测试**

`frontend/src/components/FilterBar/__tests__/MarketViewSelector.test.tsx`:
```tsx
import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { UIStateProvider } from '@/providers/UIStateProvider';
import { useUIState } from '@/providers/uiStateContext';
import { MarketViewSelector } from '../MarketViewSelector';

const Spy = () => {
  const { state } = useUIState();
  return <span data-testid="mv-val">{state.marketView}</span>;
};

const renderWith = () =>
  render(
    <MemoryRouter>
      <UIStateProvider>
        <MarketViewSelector />
        <Spy />
      </UIStateProvider>
    </MemoryRouter>,
  );

describe('MarketViewSelector', () => {
  it('默认渲染 us 高亮', () => {
    renderWith();
    expect(screen.getByTestId('mv-val').textContent).toBe('us');
    expect(screen.getByRole('button', { name: /美股/i })).toHaveAttribute(
      'aria-pressed', 'true',
    );
  });

  it('点击 A 股全部 切到 cn-all', () => {
    renderWith();
    fireEvent.click(screen.getByRole('button', { name: /A股全部/i }));
    expect(screen.getByTestId('mv-val').textContent).toBe('cn-all');
  });

  it('点击 A 股专属 切到 cn-only', () => {
    renderWith();
    fireEvent.click(screen.getByRole('button', { name: /A股专属/i }));
    expect(screen.getByTestId('mv-val').textContent).toBe('cn-only');
  });

  it('role=group + 三个 aria-pressed 按钮', () => {
    renderWith();
    const group = screen.getByRole('group', { name: /市场视角/i });
    expect(group).toBeInTheDocument();
    const btns = screen.getAllByRole('button');
    expect(btns).toHaveLength(3);
    btns.forEach(b => expect(b).toHaveAttribute('aria-pressed'));
  });
});
```

- [ ] **Step 3.2: 跑测试确认失败**

```
cd /Users/dreambt/sources/etf-radar/frontend && npx vitest run src/components/FilterBar/__tests__/MarketViewSelector.test.tsx 2>&1 | tail -15
```
预期: FAIL,组件未定义。

- [ ] **Step 3.3: 实现 MarketViewSelector**

`frontend/src/components/FilterBar/MarketViewSelector.tsx`:
```tsx
import { useUIState } from '@/providers/uiStateContext';
import type { MarketView } from '@/lib/marketView';

const OPTIONS: Array<{ v: MarketView; label: string }> = [
  { v: 'us',      label: '美股'     },
  { v: 'cn-all',  label: 'A股全部' },
  { v: 'cn-only', label: 'A股专属' },
];

export const MarketViewSelector = () => {
  const { state, dispatch } = useUIState();
  return (
    <div
      role="group"
      aria-label="市场视角"
      className="inline-flex rounded border border-slate-300 overflow-hidden text-sm"
    >
      {OPTIONS.map(({ v, label }) => {
        const active = state.marketView === v;
        return (
          <button
            key={v}
            type="button"
            aria-pressed={active}
            onClick={() => dispatch({ type: 'SET_MARKET_VIEW', v })}
            className={
              active
                ? 'px-3 py-1 bg-slate-800 text-white'
                : 'px-3 py-1 bg-white text-slate-700 hover:bg-slate-100'
            }
          >
            {label}
          </button>
        );
      })}
    </div>
  );
};
```

- [ ] **Step 3.4: FilterBar 替换 + 删除 OnlyCnOnlyToggle**

`frontend/src/components/FilterBar/index.tsx`:
```tsx
import { DimensionTabs } from './DimensionTabs';
import { SignalTabs } from './SignalTabs';
import { SearchInput } from './SearchInput';
import { Legend } from './Legend';
import { MarketViewSelector } from './MarketViewSelector';

export const FilterBar = () => (
  <div className="bg-white border-b p-3 flex flex-wrap items-center gap-4">
    <DimensionTabs />
    <SignalTabs />
    <MarketViewSelector />
    <Legend />
    <div className="ml-auto">
      <SearchInput />
    </div>
  </div>
);
```

删 文件:
```bash
rm frontend/src/components/FilterBar/OnlyCnOnlyToggle.tsx
[ -f frontend/src/components/FilterBar/__tests__/OnlyCnOnlyToggle.test.tsx ] && \
  rm frontend/src/components/FilterBar/__tests__/OnlyCnOnlyToggle.test.tsx
```

- [ ] **Step 3.5: 跑测试**

```
cd /Users/dreambt/sources/etf-radar/frontend && npx vitest run src/components/FilterBar 2>&1 | tail -15
```
预期: MarketViewSelector PASS。FilterBar 旧测试若引用 OnlyCnOnlyToggle,本步顺手修。

- [ ] **Step 3.6: Commit**

```bash
git add frontend/src/components/FilterBar/MarketViewSelector.tsx \
        frontend/src/components/FilterBar/__tests__/MarketViewSelector.test.tsx \
        frontend/src/components/FilterBar/index.tsx
git add -u frontend/src/components/FilterBar/  # 删除项
git commit -m "feat(filter-bar): MarketViewSelector replaces OnlyCnOnlyToggle (3-state)"
```

---

## Task 4: trailGradient mode-aware + 删 ModeToggle

**Files:**
- Modify: `frontend/src/lib/trailGradient.ts`
- Modify: `frontend/src/lib/__tests__/trailGradient.test.ts`
- Modify: `frontend/src/components/rotation/RotationScatterWithTrails.tsx`
- Modify: `frontend/src/components/rotation/RotationTrailsOverlay.tsx`
- Delete: `frontend/src/components/rotation/ModeToggle.tsx` + 测试

- [ ] **Step 4.1: 写 trailGradient mode 维度失败测试**

在 `frontend/src/lib/__tests__/trailGradient.test.ts` (若不存在则创建) 内加测试:
```ts
import { describe, it, expect } from 'vitest';
import { buildTrails } from '@/lib/trailGradient';
import type { SnapshotFrame } from '@/types/snapshots';
import type { Theme } from '@/types/themes';

const mkS = (long: number, short: number) => ({
  short, mid: 0, long, composite: 0,
});

const mapped = (long: number, short: number): Theme => ({
  id: 'ai', name: 'AI', us_etfs: [], primary_us: 'BOTZ', primary_cn: '159819',
  tags: [], note: '',
  returns: { r_1d: 0, r_5d: 0, r_20d: 0, r_60d: 0, r_120d: 0, r_ytd: 0 },
  strength: mkS(long, short),
  us_strength: mkS(long + 10, short + 10),
  cn_strength: mkS(long - 10, short - 10),
  rank: { short: 1, mid: 1, long: 1, composite: 1 },
});

const f = (date: string, themes: Theme[]): SnapshotFrame => ({ date, themes });

describe('buildTrails mode-aware', () => {
  it('mode=us 取 us_strength 坐标', () => {
    const frames = [f('d1', [mapped(50, 50)])];
    const m = buildTrails(frames, 'us');
    expect(m.get('ai')?.[0]).toMatchObject({ x: 60, y: 60 });
  });

  it('mode=cn 取 cn_strength 坐标', () => {
    const frames = [f('d1', [mapped(50, 50)])];
    const m = buildTrails(frames, 'cn');
    expect(m.get('ai')?.[0]).toMatchObject({ x: 40, y: 40 });
  });

  it('us_strength=null (旧 schema 1.0 frame) 回退到 strength', () => {
    const legacy: Theme = { ...mapped(50, 50), us_strength: null, cn_strength: null };
    const frames = [f('d1', [legacy])];
    const m = buildTrails(frames, 'us');
    expect(m.get('ai')?.[0]).toMatchObject({ x: 50, y: 50 });
  });

  it('cn-only 主题在 mode=us 时跳过', () => {
    const cnOnly: Theme = {
      ...mapped(50, 50), primary_us: null, us_strength: null,
      cn_strength: mkS(70, 70),
    };
    const frames = [f('d1', [cnOnly])];
    const m = buildTrails(frames, 'us');
    expect(m.get('ai')).toBeUndefined();
  });
});
```

- [ ] **Step 4.2: 跑测试确认失败**

```
cd /Users/dreambt/sources/etf-radar/frontend && npx vitest run src/lib/__tests__/trailGradient.test.ts 2>&1 | tail -15
```
预期: 新增 4 用例全失败 (buildTrails 不接 mode)。

- [ ] **Step 4.3: 改 trailGradient.ts**

`frontend/src/lib/trailGradient.ts`:
```ts
import type { SnapshotFrame } from '@/types/snapshots';
import type { RotationMode } from '@/lib/rotation';

const OPACITY_MIN = 0.05;
const OPACITY_MAX = 0.4;

export function trailOpacity(i: number, total: number): number {
  if (total <= 1) return OPACITY_MAX;
  const t = i / (total - 1);
  return OPACITY_MIN + (OPACITY_MAX - OPACITY_MIN) * t;
}

export interface TrailPoint {
  x: number;
  y: number;
  opacity: number;
  date: string;
}

export interface BuildTrailsOptions {
  themeIds?: Set<string>;
}

export function buildTrails(
  frames: SnapshotFrame[],
  mode: RotationMode,
  opts?: BuildTrailsOptions,
): Map<string, TrailPoint[]> {
  const result = new Map<string, TrailPoint[]>();
  const total = frames.length;
  if (total === 0) return result;

  let candidates: Set<string>;
  if (opts?.themeIds) {
    candidates = opts.themeIds;
  } else {
    candidates = new Set<string>();
    for (const frame of frames) {
      for (const theme of frame.themes) candidates.add(theme.id);
    }
  }

  const pickField = mode === 'us' ? 'us_strength' : 'cn_strength';

  for (const themeId of candidates) {
    const points: TrailPoint[] = [];
    frames.forEach((frame, i) => {
      const theme = frame.themes.find(t => t.id === themeId);
      if (!theme) return;
      // 优先取 mode-aware 字段; null 时 (旧 schema 1.0 快照) 回退到 strength;
      // 仍 null 则跳过此帧 (cn-only 主题 + mode=us).
      const s = theme[pickField] ?? theme.strength;
      if (!s) return;
      points.push({
        x: s.long,
        y: s.short,
        opacity: trailOpacity(i, total),
        date: frame.date,
      });
    });
    // 全帧都被跳过(cn-only + us)时不写入 candidate, 与现有 candidate 过滤一致.
    if (points.length > 0) result.set(themeId, points);
  }
  return result;
}
```

- [ ] **Step 4.4: 跑 trailGradient 测试**

```
cd /Users/dreambt/sources/etf-radar/frontend && npx vitest run src/lib/__tests__/trailGradient.test.ts 2>&1 | tail -15
```
预期: 全 PASS。

- [ ] **Step 4.5: RotationScatterWithTrails 传 mode 给 buildTrails**

修改 `frontend/src/components/rotation/RotationScatterWithTrails.tsx`,Line 92:
```ts
const trails = useMemo(
  () => buildTrails(trailFrames, effectiveMode),
  [trailFrames, effectiveMode],
);
```

- [ ] **Step 4.6: 删 ModeToggle**

```bash
rm frontend/src/components/rotation/ModeToggle.tsx
[ -f frontend/src/components/rotation/__tests__/ModeToggle.test.tsx ] && \
  rm frontend/src/components/rotation/__tests__/ModeToggle.test.tsx
```

- [ ] **Step 4.7: 跑 rotation 目录测试**

```
cd /Users/dreambt/sources/etf-radar/frontend && npx vitest run src/components/rotation src/lib/__tests__/trailGradient.test.ts 2>&1 | tail -20
```
预期: rotation/trailGradient 全 PASS。

- [ ] **Step 4.8: Commit**

```bash
git add frontend/src/lib/trailGradient.ts \
        frontend/src/lib/__tests__/trailGradient.test.ts \
        frontend/src/components/rotation/RotationScatterWithTrails.tsx
git add -u frontend/src/components/rotation/
git commit -m "feat(rotation): trailGradient mode-aware, drop ModeToggle (folded into MarketViewSelector)"
```

---

## Task 5: RotationPage / RotationTrailsOverlay 走 Context 派生 mode

**Files:**
- Modify: `frontend/src/pages/RotationPage.tsx`
- Modify: `frontend/src/components/rotation/RotationTrailsOverlay.tsx`

- [ ] **Step 5.1: 改 RotationTrailsOverlay 从 Context 派生 mode**

`frontend/src/components/rotation/RotationTrailsOverlay.tsx` 头部加 import + 替换 mode prop:
```tsx
import { useMemo, useRef } from 'react';
import { useTrailRange } from '@/hooks/useTrailRange';
import { useFocusedTheme } from '@/hooks/useFocusedTheme';
import { TrailRangeSlider } from './TrailRangeSlider';
import { RotationScatterWithTrails } from './RotationScatterWithTrails';
import { FocusedThemePanel } from './FocusedThemePanel';
import { useUIState } from '@/providers/uiStateContext';
import { marketViewToRotationMode } from '@/lib/marketView';
import type { Theme } from '@/types/themes';
import type { SnapshotFrame } from '@/types/snapshots';

interface Props {
  themes: Theme[];
  snapshots: SnapshotFrame[];
}

export const RotationTrailsOverlay = ({ themes, snapshots }: Props) => {
  const { state } = useUIState();
  const mode = marketViewToRotationMode(state.marketView);
  // ... 其余保持 (range / validThemeIds / focusedId / trailFrames 不变),
  //     RotationScatterWithTrails 调用处把 mode={mode} 传下去
```

- [ ] **Step 5.2: 改 RotationPage (删 useState, 计算 counts 用 marketView)**

`frontend/src/pages/RotationPage.tsx` 改动点 (示意 diff):
```diff
-import { useState } from 'react';
-import type { RotationMode } from '@/lib/rotation';
-import { ModeToggle } from '@/components/rotation/ModeToggle';
 ...
-  const [mode, setMode] = useState<RotationMode>('us');
 ...
-  const usCount = themes.themes.filter(t => t.us_strength !== null).length;
-  const cnCount = themes.themes.filter(t => t.cn_strength !== null).length;
 ...
-  <ModeToggle mode={mode} onChange={setMode} usCount={usCount} cnCount={cnCount} />
 ...
-  <RotationTrailsOverlay themes={themes.themes} snapshots={snapshotsFrames} mode={mode} />
+  <RotationTrailsOverlay themes={themes.themes} snapshots={snapshotsFrames} />
```

> ⚠️ 注: 完整文件内容由 implementer 依据现状改写; 此处仅声明删除/修改点,实现时**逐行确认**是否还有遗漏的 mode/usCount/cnCount/ModeToggle 引用。

- [ ] **Step 5.3: 跑 rotation 相关测试**

```
cd /Users/dreambt/sources/etf-radar/frontend && npx vitest run src/components/rotation src/pages 2>&1 | tail -20
```
预期: 全 PASS (如果 RotationPage 没有测试,只看 rotation 目录绿)。

- [ ] **Step 5.4: Commit**

```bash
git add frontend/src/pages/RotationPage.tsx \
        frontend/src/components/rotation/RotationTrailsOverlay.tsx
git commit -m "feat(rotation): RotationPage/Overlay consume marketView from Context"
```

---

## Task 6: ThemeList mode-aware 过滤 + 排序 + 头部文案 (Blocker 修复)

**Files:**
- Modify: `frontend/src/components/ThemeList/index.tsx`
- Modify: `frontend/src/components/ThemeList/ThemeRow.tsx`

- [ ] **Step 6.1: 改 ThemeList/index.tsx**

完整重写:
```tsx
import { useMemo } from 'react';
import { useDataContext } from '@/providers/dataContext';
import { useUIState } from '@/providers/uiStateContext';
import { useThemeSignalsMap } from '@/hooks/useData';
import { filterThemes } from '@/lib/filters';
import { pickStrength, themeMatchesView } from '@/lib/marketView';
import { ThemeRow } from './ThemeRow';

const DIM_LABELS = {
  short: '短期',
  mid: '中期',
  long: '长期',
  composite: '综合',
} as const;

const VIEW_TITLES = {
  us:        '美股主题强弱',
  'cn-all':  'A 股主题强弱',
  'cn-only': 'A 股专属主题',
} as const;

export const ThemeList = () => {
  const { themes } = useDataContext();
  const { state, dispatch } = useUIState();
  const sigMap = useThemeSignalsMap();
  const { dimension, marketView } = state;

  // 1) 过滤到当前视角的主题集
  const inView = useMemo(() => {
    if (!themes) return [];
    return themes.themes.filter(t => themeMatchesView(t, marketView));
  }, [themes, marketView]);

  // 2) 按 mode-aware strength[dim] 排序; pickStrength=null 排到最后 (理论上 inView 已过滤掉)
  const sorted = useMemo(() => {
    return [...inView].sort((a, b) => {
      const sa = pickStrength(a, marketView)?.[dimension] ?? -1;
      const sb = pickStrength(b, marketView)?.[dimension] ?? -1;
      return sb - sa;
    });
  }, [inView, marketView, dimension]);

  // 3) signal + search 过滤 (sigMap 仅对 mapped 主题有值; cn-only 视图全是 cn-only,
  //    signalFilter='all' 时不影响; filterThemes 内部已对 sigMap 缺失安全处理)
  const filtered = useMemo(
    () => filterThemes(sorted, sigMap, state.signalFilter, state.searchQuery),
    [sorted, sigMap, state.signalFilter, state.searchQuery],
  );

  return (
    <div className="bg-white border rounded">
      <div className="p-3 border-b">
        <div className="font-medium">{VIEW_TITLES[marketView]}</div>
        <div className="text-xs text-gray-500">
          按{DIM_LABELS[dimension]}强弱排序 · {filtered.length}/{inView.length} 个主题
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-xs text-gray-600">
            <tr>
              <th className="px-2 py-2 text-center">#</th>
              <th className="px-2 py-2 text-left">主题</th>
              <th className="px-2 py-2 text-left">主ETF</th>
              <th className="px-2 py-2 text-left">强度</th>
              <th className="px-2 py-2 text-right">近1日</th>
              <th className="px-2 py-2 text-right">近1周</th>
              <th className="px-2 py-2 text-center">信号</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((t, i) => (
              <ThemeRow
                key={t.id}
                index={i}
                theme={t}
                signal={sigMap.get(t.id)}
                dimension={dimension}
                marketView={marketView}
                selected={state.selectedThemeId === t.id}
                onClick={() => dispatch({ type: 'SELECT_THEME', id: t.id })}
              />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};
```

- [ ] **Step 6.2: 改 ThemeRow.tsx 接收 marketView 并取 mode-aware 强度**

读取当前 ThemeRow 文件,精准定位强度数显示位置,改造点:
- Props 增加 `marketView: MarketView`
- 强度数从 `theme.strength[dimension]` 改为 `pickStrength(theme, marketView)?.[dimension] ?? '-'`
- 保留现有 `isCnOnly` "A股专属" pill 显示 (但内部判定改用 `isCnOnly(theme)` helper, deferred #2)
- 主 ETF 列: us 视角显示 `primary_us`, cn-* 视角显示 `primary_cn` (cn-only 视角 primary_us 为 null,显示 primary_cn 更自然)
- returns 列 (近1日/近1周) 维持原样: returns 都从 theme.returns (取主 ETF) 来,与 marketView 无关,但 us 视角下 returns 反映美 ETF, cn-* 视角下 reflects... 这里要 implementer 调研 theme.returns 是从 primary_us 还是 primary_cn 算的,**若两个都依赖单一主 ETF 则需要新增 returns_us/returns_cn 字段 -- 超出本 plan 范围, 标 follow-up**。本任务暂不动 returns 列,仅在 ThemeRow 顶部加一行注释说明这个已知不一致。

具体改写由 implementer 读取 ThemeRow.tsx 现状后做。

- [ ] **Step 6.3: 跑 ThemeList + ThemeRow 既有测试**

```
cd /Users/dreambt/sources/etf-radar/frontend && npx vitest run src/components/ThemeList 2>&1 | tail -30
```
预期: 若有 props 类型错误先修。期望全部 PASS。

- [ ] **Step 6.4: Commit**

```bash
git add frontend/src/components/ThemeList/index.tsx \
        frontend/src/components/ThemeList/ThemeRow.tsx
git commit -m "feat(theme-list): mode-aware filter+sort+header (Blocker fix)"
```

---

## Task 7: 集中化 isCnOnly + ThemeList 集成测试 (deferred #2 + #3)

**Files:**
- Modify: `frontend/src/components/ThemeList/ThemeRow.tsx`
- Modify: `frontend/src/components/MappingPanel.tsx` (实际路径以现状为准)
- Create: `frontend/src/components/ThemeList/__tests__/ThemeList.test.tsx`

- [ ] **Step 7.1: 替换所有 `theme.primary_us === null` 为 `isCnOnly(theme)`**

用 grep 定位:
```
cd /Users/dreambt/sources/etf-radar/frontend && \
  grep -rn "primary_us === null" src/
```
预期出现 ThemeRow / MappingPanel / 可能还有 1-2 处。逐一替换为 `import { isCnOnly } from '@/lib/marketView'` 并调用 `isCnOnly(theme)`。

- [ ] **Step 7.2: 跑全前端测试,确认无回归**

```
cd /Users/dreambt/sources/etf-radar/frontend && npx vitest run 2>&1 | tail -20
```
预期: 全 PASS。

- [ ] **Step 7.3: 写 ThemeList 集成测试**

`frontend/src/components/ThemeList/__tests__/ThemeList.test.tsx`:
```tsx
import { describe, it, expect } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { UIStateProvider } from '@/providers/UIStateProvider';
import { DataContext } from '@/providers/dataContext';
import { ThemeList } from '../index';
import type { ThemesFile } from '@/types/themes';

// 最小 fixtures: 1 mapped + 1 cn-only
const mkS = (n: number) => ({ short: n, mid: n, long: n, composite: n });
const themesFile: ThemesFile = {
  schema_version: '1.1', generated_at: '2026-06-20T00:00:00Z',
  themes: [
    {
      id: 'ai', name: 'AI', us_etfs: ['BOTZ'],
      primary_us: 'BOTZ', primary_cn: '159819',
      tags: [], note: '',
      returns: { r_1d: 1, r_5d: 2, r_20d: 3, r_60d: 4, r_120d: 5, r_ytd: 6 },
      strength: mkS(80), us_strength: mkS(90), cn_strength: mkS(50),
      rank: { short: 1, mid: 1, long: 1, composite: 1 },
    },
    {
      id: 'cn_liquor', name: '白酒', us_etfs: [],
      primary_us: null, primary_cn: '512690',
      tags: [], note: '',
      returns: { r_1d: 0, r_5d: 0, r_20d: 0, r_60d: 0, r_120d: 0, r_ytd: 0 },
      strength: mkS(60), us_strength: null, cn_strength: mkS(60),
      rank: { short: 2, mit: 2, long: 2, composite: 2 } as never,
    },
  ],
};

const renderAt = (path: string) =>
  render(
    <MemoryRouter initialEntries={[path]}>
      <DataContext.Provider value={{
        themes: themesFile, etfs: null, signals: null,
        meta: null, snapshots: null,
        loading: false, error: null,
      } as never}>
        <UIStateProvider>
          <ThemeList />
        </UIStateProvider>
      </DataContext.Provider>
    </MemoryRouter>,
  );

describe('ThemeList × MarketView 集成', () => {
  it('mv=us 隐藏 cn-only,头部 "美股主题强弱"', () => {
    renderAt('/?mv=us');
    expect(screen.getByText('美股主题强弱')).toBeInTheDocument();
    expect(screen.getByText('AI')).toBeInTheDocument();
    expect(screen.queryByText('白酒')).not.toBeInTheDocument();
  });

  it('mv=cn-all 同时展示 mapped 与 cn-only,头部 "A 股主题强弱"', () => {
    renderAt('/?mv=cn-all');
    expect(screen.getByText('A 股主题强弱')).toBeInTheDocument();
    expect(screen.getByText('AI')).toBeInTheDocument();
    expect(screen.getByText('白酒')).toBeInTheDocument();
  });

  it('mv=cn-only 只展示 cn-only,头部 "A 股专属主题"', () => {
    renderAt('/?mv=cn-only');
    expect(screen.getByText('A 股专属主题')).toBeInTheDocument();
    expect(screen.queryByText('AI')).not.toBeInTheDocument();
    expect(screen.getByText('白酒')).toBeInTheDocument();
  });

  it('mv=cn-all 排序按 cn_strength,mapped(50) 落后于 cn-only(60)', () => {
    renderAt('/?mv=cn-all');
    const rows = screen.getAllByRole('row');
    // 第一数据行 (rows[0] 是 thead) 应是白酒
    const first = within(rows[1]);
    expect(first.getByText('白酒')).toBeInTheDocument();
  });
});
```

> ⚠️ DataContext shape 以代码实际形态为准; 若 DataContext 不能直接 mock,改用 vi.mock('@/providers/dataContext') 形式。

- [ ] **Step 7.4: 跑集成测试**

```
cd /Users/dreambt/sources/etf-radar/frontend && \
  npx vitest run src/components/ThemeList/__tests__/ThemeList.test.tsx 2>&1 | tail -20
```
预期: 全 PASS。

- [ ] **Step 7.5: Commit**

```bash
git add frontend/src/components/ThemeList/__tests__/ThemeList.test.tsx
git add -u frontend/src/components/ThemeList/ frontend/src/components/MappingPanel.tsx
git commit -m "refactor: isCnOnly helper + ThemeList integration tests (clears deferred #2 + #3)"
```

---

## Task 8: 端到端验收 + tsc/lint/build

**Files:** (无新建,只跑命令)

- [ ] **Step 8.1: 全前端测试**

```
cd /Users/dreambt/sources/etf-radar/frontend && npx vitest run 2>&1 | tail -30
```
预期: 全 PASS,无 skipped 增加。

- [ ] **Step 8.2: TypeScript 类型检查**

```
cd /Users/dreambt/sources/etf-radar/frontend && npx tsc --noEmit 2>&1 | tail -20
```
预期: 无错误。

- [ ] **Step 8.3: ESLint**

```
cd /Users/dreambt/sources/etf-radar/frontend && npx eslint src --max-warnings=0 2>&1 | tail -20
```
预期: 无 error/warn。

- [ ] **Step 8.4: 后端测试 (确认不受影响)**

```
cd /Users/dreambt/sources/etf-radar/backend && uv run --all-extras pytest 2>&1 | tail -10
```
预期: 全 PASS。

- [ ] **Step 8.5: 手工验收 checklist (dev server)**

```
cd /Users/dreambt/sources/etf-radar/frontend && npm run dev
```
打开浏览器逐项过:
- [ ] FilterBar 显示 [美股/A股全部/A股专属] 3 段按钮
- [ ] 默认 mv=us, URL 不带 mv 参数
- [ ] 点 "A股全部",URL 变为 `?mv=cn-all`, ThemeList 头部变 "A 股主题强弱", 21 主题全显
- [ ] 点 "A股专属",URL 变为 `?mv=cn-only`, ThemeList 头部变 "A 股专属主题", 7 cn-only 显
- [ ] 切到 "美股", cn-only 隐藏, ThemeList 头部变 "美股主题强弱", 14 mapped 显
- [ ] RotationScatter 在 mv=us 显 14 散点(cn-only 不渲染), mv=cn-* 显 21 散点
- [ ] mv=cn-* 时, RotationScatter trail 末点对齐当前 bubble (mode=cn 一致)
- [ ] 刷新页面, mv 状态保留
- [ ] 排序: mv=us 按 us_strength, mv=cn-* 按 cn_strength (数字大的在上)
- [ ] 点主题 bubble: 详情面板 OK, primary_us=null 主题展示 "A股专属" fallback

- [ ] **Step 8.6: Commit (若手工修补)**

```bash
git status
# 如手工 step 5 暴露遗留问题已修,这里 commit
```

- [ ] **Step 8.7: 总结写入 plan 末尾 (在该 plan 文档后追加 "Execution Log" 章节)**

记录每个 task 的 commit SHA,便于后续 Final reviewer 追溯。

---

## 自我审查 (writing-plans Self-Review)

**1. Spec coverage**

| Spec 决策 | 落在 Task |
|---|---|
| MarketView 三态 ('us'/'cn-all'/'cn-only') | Task 1 (类型) + Task 2 (URL) |
| 1a: us 视角隐藏 cn-only, onlyCnOnly 与 mode=us 互斥 | Task 1 themeMatchesView + Task 6 inView |
| onlyCnOnly 概念被吸收进 cn-only | Task 1 删 OnlyCnOnly + Task 3 删 toggle |
| iii: 三选一控件 | Task 3 MarketViewSelector |
| 2a: cn_strength 主导, us_strength 退到详情 | Task 6 pickStrength |
| 3a: Signal 不动 | Task 6 sigMap 保留, signalFilter 不改 |
| ModeToggle 全局化 (不在 RotationPage 内) | Task 3 (FilterBar) + Task 4 (删 ModeToggle) + Task 5 (RotationPage 走 Context) |
| Blocker: ThemeList 头部硬编码文案 | Task 6 VIEW_TITLES |
| Deferred #1: trailGradient mode-aware | Task 4 |
| Deferred #2: isCnOnly helper 提取 | Task 1 + Task 7 替换 |
| Deferred #3: ThemeList 集成测试 | Task 7 |

✅ 全部覆盖。

**2. Placeholder scan**

- ❌ "TBD"/"TODO": 无
- ❌ "类似 Task N": 无 (每 task 完整代码)
- ⚠️ Task 6 ThemeRow / Task 5 RotationPage 部分写"由 implementer 读取现状改写": 这是因为这两处文件未在 plan 前读取(避免一次性塞过多代码)。implementer 必须先 Read 当前内容再改,**不能** 凭空想象。这是有意为之的最小化原则,但 implementer 需要明白这两点。
- ⚠️ Task 7 ThemeList 集成测试中 `DataContext.Provider` 直接传 fake value: 若实际 DataContext 不导出或 shape 不同,implementer 改用 `vi.mock('@/providers/dataContext', () => ...)`。

**3. Type consistency**

- `MarketView` 在 marketView.ts 定义,uiStateContext.ts、MarketViewSelector、ThemeList、ThemeRow 全部 import from `@/lib/marketView` ✅
- `RotationMode` 仍源自 `@/lib/rotation`,trailGradient/Overlay/Scatter 一致 ✅
- `UIStateAction.SET_MARKET_VIEW` payload `v: MarketView` 与 dispatch 调用方一致 ✅
- ThemeList 与 ThemeRow 之间 props `marketView: MarketView` 一致 ✅

**4. 已知风险**

- ThemeRow returns 列 (r_1d/r_5d) 在 cn-* 视角下显示的仍是 theme.returns (理论上从 primary_us 算出),这是 schema 1.1 的已知遗留 -- backend 未拆分 us_returns/cn_returns。本 plan **不修复**,在 Task 6 Step 6.2 标 follow-up,由独立 PR 处理。
- 旧 schema 1.0 snapshot 在 trailGradient 中 fallback 到 `theme.strength` -- 这与 mode-aware 语义不严格一致 (1.0 frame 不区分美/中),但能避免老历史 trail 断片。可接受。

---

## 执行交接

Plan 已完成,保存到 `docs/superpowers/plans/2026-06-20-market-view-global.md`。

两种执行方式:
1. **Subagent-Driven (推荐)** — 每 task 派 fresh implementer + 双阶段评审,适合本 plan (8 task 相互独立性高)。
2. **Inline Execution** — 同会话批量执行,需要在每 checkpoint review。

---

## Execution Log

执行日期: 2026-06-20
执行方式: Subagent-Driven Development
分支: feat/cn-sector-themes

| Task | Commit SHA | 说明 |
|---|---|---|
| 1 | 14cbd8d | MarketView 基础设施 (marketView.ts + uiStateContext) |
| 2 | 20a786d | UIStateProvider 接 mv URL 参数 |
| 3 | 33a5b90 | MarketViewSelector 替换 OnlyCnOnlyToggle |
| 4 | 53f8ed1 | trailGradient buildTrails 接 mode 参数 + 删 ModeToggle |
| 5 | a405515 | RotationPage/Overlay 从 Context 派生 mode |
| 6a | b805ea4 | ThemeList mode-aware 过滤+排序+头部 (Blocker fix) |
| 6b | e9ca083 | fix: 闭合 cn_strength invariant + Progress null state |
| 7 | 8985fa1 | isCnOnly helper + ThemeList 集成测试 |
| 8 | (本 commit) | 自动化验收 + Execution Log |

### 自动化验收结果 (Step 8.1-8.4)

- **前端测试**: 207/207 PASS, 0 FAIL, 0 SKIPPED (vitest)
- **TypeScript**: 仅预存 `tsconfig.json(8,5): TS5101 baseUrl deprecated` 警告,无新增 error
- **ESLint**: `npm run lint` (= `eslint .`) 输出 `ESLint: No issues found`;直接调 `node_modules/.bin/eslint src --max-warnings=0` 也 exit 0 无输出。注:`npx eslint src ...` 形式因 npx wrapper 解析问题输出诡异 `Lint: 2 errors, 0 warnings`,非真实 lint 错误 (项目规范命令为 `npm run lint`)
- **后端测试**: 135/135 PASSED, 0 FAILED (uv run --all-extras pytest, 120.79s)

### 手工验收 (Step 8.5)

由人类用户在 dev server 上完成,checklist 见 plan 原文 Step 8.5。

### Deferred / 已知遗留

- ThemeRow returns 列在 cn-* 视角仍取 `theme.returns` (主 ETF 数据),需要后端拆分 `returns_us` / `returns_cn` 才能彻底修复 → 跟踪在 ThemeRow.tsx 顶部 FIXME。
- `us_etfs.join(' / ')` 子标题在 cn-* 视角仍显示美股 ETF 代码列表 (Task 6 reviewer concern,YAGNI 范围外)。
- `pickPrimary` helper 未抽取 (只 1 处用,YAGNI)。
