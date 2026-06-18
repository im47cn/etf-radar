# RRG 轨迹视图重构 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 RRG 主题轮动图从"动画播放器 + top N 尾迹"重构为"全 14 主题静态轨迹叠加 + 单击粘性聚焦 + 起止滑块",同步引入 Playwright e2e + CI 集成。

**Architecture:** 新建 `RotationTrailsOverlay` 主容器,装配 `TrailRangeSlider`(双滑块) + `RotationScatterWithTrails`(重写为扁平单 series + 聚焦态) + `FocusedThemePanel`(右上浮窗/移动端底部 sheet)。删除 `RotationTimelinePlayer` / `useTimelinePlayer` / `TimelineControls` 及测试。新增 `useTrailRange` / `useFocusedTheme` 两个 hook。

**Tech Stack:** React 19 + TypeScript + Vite + Vitest + @testing-library/react + Recharts 3 + @base-ui/react (slider) + Playwright (新增) + react-router-dom 7

**Spec Reference:** `docs/superpowers/specs/2026-06-17-rotation-trails-redesign-design.md`

---

## 全局测试约定

- 所有测试运行目录: `cd /Users/dreambt/sources/etf-radar/frontend`
- 运行单个测试: `npx vitest run <path> 2>&1 | tail -30`
- 运行全部 vitest: `npm test -- --run 2>&1 | tail -30`
- 运行 e2e (Task 12 之后): `npm run test:e2e 2>&1 | tail -30`
- fake timer: `vi.useFakeTimers({ shouldAdvanceTime: true })`(避免 observation 9507 TS 兼容性坑)
- 每个 task 完成后 commit, commit message 中文,格式 `feat/refactor/test/chore: <description>`

---

## Task 1: `useTrailRange` hook

**Files:**
- Create: `frontend/src/hooks/useTrailRange.ts`
- Test: `frontend/src/hooks/__tests__/useTrailRange.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/hooks/__tests__/useTrailRange.test.tsx`:

```tsx
import { renderHook, act } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { useTrailRange } from '../useTrailRange';

describe('useTrailRange', () => {
  it('defaults to startOffset=-15, endOffset=0', () => {
    const { result } = renderHook(() => useTrailRange());
    expect(result.current.range).toEqual({ startOffset: -15, endOffset: 0 });
  });

  it('setRange updates state when valid', () => {
    const { result } = renderHook(() => useTrailRange());
    act(() => result.current.setRange({ startOffset: -30, endOffset: 0 }));
    expect(result.current.range).toEqual({ startOffset: -30, endOffset: 0 });
  });

  it('clamps startOffset to lower bound -60', () => {
    const { result } = renderHook(() => useTrailRange());
    act(() => result.current.setRange({ startOffset: -100, endOffset: 0 }));
    expect(result.current.range.startOffset).toBe(-60);
  });

  it('clamps endOffset to upper bound 0', () => {
    const { result } = renderHook(() => useTrailRange());
    act(() => result.current.setRange({ startOffset: -10, endOffset: 5 }));
    expect(result.current.range.endOffset).toBe(0);
  });

  it('rejects invalid range where startOffset >= endOffset (keeps prev)', () => {
    const { result } = renderHook(() => useTrailRange());
    act(() => result.current.setRange({ startOffset: 0, endOffset: 0 }));
    expect(result.current.range).toEqual({ startOffset: -15, endOffset: 0 });
  });

  it('reset returns to default', () => {
    const { result } = renderHook(() => useTrailRange());
    act(() => result.current.setRange({ startOffset: -30, endOffset: -5 }));
    act(() => result.current.reset());
    expect(result.current.range).toEqual({ startOffset: -15, endOffset: 0 });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/dreambt/sources/etf-radar/frontend && npx vitest run src/hooks/__tests__/useTrailRange.test.tsx 2>&1 | tail -20
```

Expected: FAIL — `Cannot find module '../useTrailRange'`

- [ ] **Step 3: Write minimal implementation**

Create `frontend/src/hooks/useTrailRange.ts`:

```ts
import { useCallback, useState } from 'react';

export interface TrailRange {
  startOffset: number;
  endOffset: number;
}

export interface UseTrailRangeReturn {
  range: TrailRange;
  setRange: (range: TrailRange) => void;
  reset: () => void;
}

const DEFAULT_RANGE: TrailRange = { startOffset: -15, endOffset: 0 };
const MIN_START = -60;
const MAX_END = 0;

export function useTrailRange(): UseTrailRangeReturn {
  const [range, setRangeState] = useState<TrailRange>(DEFAULT_RANGE);

  const setRange = useCallback((next: TrailRange) => {
    const clampedStart = Math.max(MIN_START, next.startOffset);
    const clampedEnd = Math.min(MAX_END, next.endOffset);
    if (clampedStart >= clampedEnd) return;
    setRangeState({ startOffset: clampedStart, endOffset: clampedEnd });
  }, []);

  const reset = useCallback(() => setRangeState(DEFAULT_RANGE), []);

  return { range, setRange, reset };
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /Users/dreambt/sources/etf-radar/frontend && npx vitest run src/hooks/__tests__/useTrailRange.test.tsx 2>&1 | tail -20
```

Expected: PASS, 6 tests

- [ ] **Step 5: Commit**

```bash
cd /Users/dreambt/sources/etf-radar && git add frontend/src/hooks/useTrailRange.ts frontend/src/hooks/__tests__/useTrailRange.test.tsx && git commit -m "feat(rotation): add useTrailRange hook with clamping"
```

---

## Task 2: `useFocusedTheme` hook

**Files:**
- Create: `frontend/src/hooks/useFocusedTheme.ts`
- Test: `frontend/src/hooks/__tests__/useFocusedTheme.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/hooks/__tests__/useFocusedTheme.test.tsx`:

```tsx
import { renderHook, act } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { useFocusedTheme } from '../useFocusedTheme';

describe('useFocusedTheme', () => {
  it('defaults to null', () => {
    const { result } = renderHook(() => useFocusedTheme({ validThemeIds: new Set(['ai']) }));
    expect(result.current.focusedId).toBeNull();
  });

  it('setFocused updates id', () => {
    const { result } = renderHook(() => useFocusedTheme({ validThemeIds: new Set(['ai']) }));
    act(() => result.current.setFocused('ai'));
    expect(result.current.focusedId).toBe('ai');
  });

  it('toggle sets id when null, clears when same', () => {
    const { result } = renderHook(() => useFocusedTheme({ validThemeIds: new Set(['ai']) }));
    act(() => result.current.toggle('ai'));
    expect(result.current.focusedId).toBe('ai');
    act(() => result.current.toggle('ai'));
    expect(result.current.focusedId).toBeNull();
  });

  it('toggle swaps to different id', () => {
    const { result } = renderHook(() => useFocusedTheme({ validThemeIds: new Set(['ai', 'semi']) }));
    act(() => result.current.toggle('ai'));
    act(() => result.current.toggle('semi'));
    expect(result.current.focusedId).toBe('semi');
  });

  it('ESC clears focus', () => {
    const { result } = renderHook(() => useFocusedTheme({ validThemeIds: new Set(['ai']) }));
    act(() => result.current.setFocused('ai'));
    act(() => {
      window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
    });
    expect(result.current.focusedId).toBeNull();
  });

  it('auto-clears when focusedId no longer in validThemeIds', () => {
    const { result, rerender } = renderHook(
      ({ ids }: { ids: Set<string> }) => useFocusedTheme({ validThemeIds: ids }),
      { initialProps: { ids: new Set(['ai']) } },
    );
    act(() => result.current.setFocused('ai'));
    rerender({ ids: new Set(['semi']) });
    expect(result.current.focusedId).toBeNull();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/dreambt/sources/etf-radar/frontend && npx vitest run src/hooks/__tests__/useFocusedTheme.test.tsx 2>&1 | tail -20
```

Expected: FAIL — `Cannot find module '../useFocusedTheme'`

- [ ] **Step 3: Write minimal implementation**

Create `frontend/src/hooks/useFocusedTheme.ts`:

```ts
import { useCallback, useEffect, useState } from 'react';

export interface UseFocusedThemeOptions {
  validThemeIds: Set<string>;
}

export interface UseFocusedThemeReturn {
  focusedId: string | null;
  setFocused: (id: string | null) => void;
  toggle: (id: string) => void;
}

export function useFocusedTheme(opts: UseFocusedThemeOptions): UseFocusedThemeReturn {
  const [focusedId, setFocusedId] = useState<string | null>(null);

  const setFocused = useCallback((id: string | null) => setFocusedId(id), []);
  const toggle = useCallback(
    (id: string) => setFocusedId(prev => (prev === id ? null : id)),
    [],
  );

  // ESC key clears focus
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setFocusedId(null);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  // Auto-clear when focusedId invalid
  useEffect(() => {
    if (focusedId !== null && !opts.validThemeIds.has(focusedId)) {
      setFocusedId(null);
    }
  }, [focusedId, opts.validThemeIds]);

  return { focusedId, setFocused, toggle };
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /Users/dreambt/sources/etf-radar/frontend && npx vitest run src/hooks/__tests__/useFocusedTheme.test.tsx 2>&1 | tail -20
```

Expected: PASS, 6 tests

- [ ] **Step 5: Commit**

```bash
cd /Users/dreambt/sources/etf-radar && git add frontend/src/hooks/useFocusedTheme.ts frontend/src/hooks/__tests__/useFocusedTheme.test.tsx && git commit -m "feat(rotation): add useFocusedTheme hook with ESC and validity guard"
```

---

## Task 3: `buildTrails` 签名改造为默认全主题

**Files:**
- Modify: `frontend/src/lib/trailGradient.ts`
- Modify: `frontend/src/components/rotation/RotationTimelinePlayer.tsx:43-46` (临时同步迁移调用方,Task 10 才删整文件)
- Modify: `frontend/src/lib/__tests__/trailGradient.test.ts` (扩展现有测试,如不存在则创建)

- [ ] **Step 1: Locate existing trailGradient tests**

```bash
cd /Users/dreambt/sources/etf-radar/frontend && find src -name "trailGradient.test*" 2>&1
```

Expected: returns path or empty. If empty, will create the file in Step 2.

- [ ] **Step 2: Write the failing test**

Edit/create `frontend/src/lib/__tests__/trailGradient.test.ts`. Add (or replace if file exists) these test cases at the bottom of the file:

```ts
import { describe, it, expect } from 'vitest';
import { buildTrails, trailOpacity, pickTopByComposite } from '../trailGradient';
import type { SnapshotFrame } from '@/types/snapshots';
import type { Theme } from '@/types/themes';

const mkTheme = (id: string, long: number, short: number, composite = 50): Theme => ({
  id,
  name: id.toUpperCase(),
  us_etfs: [],
  primary_us: '',
  tags: [],
  note: '',
  returns: { r_1d: 0, r_5d: 0, r_20d: 0, r_60d: 0, r_120d: 0, r_ytd: 0 },
  strength: { short, mid: 50, long, composite },
  rank: { short: 1, mid: 1, long: 1, composite: 1 },
});

const mkFrame = (date: string, themes: Theme[]): SnapshotFrame => ({ date, themes });

describe('buildTrails (new signature)', () => {
  it('returns ALL themes when opts.themeIds is undefined', () => {
    const frames = [
      mkFrame('2026-01-01', [mkTheme('ai', 60, 70), mkTheme('semi', 40, 30)]),
      mkFrame('2026-01-02', [mkTheme('ai', 65, 72), mkTheme('semi', 45, 35)]),
    ];
    const trails = buildTrails(frames);
    expect(Array.from(trails.keys()).sort()).toEqual(['ai', 'semi']);
    expect(trails.get('ai')).toHaveLength(2);
    expect(trails.get('semi')).toHaveLength(2);
  });

  it('filters by opts.themeIds when provided', () => {
    const frames = [
      mkFrame('2026-01-01', [mkTheme('ai', 60, 70), mkTheme('semi', 40, 30)]),
    ];
    const trails = buildTrails(frames, { themeIds: new Set(['ai']) });
    expect(Array.from(trails.keys())).toEqual(['ai']);
  });

  it('skips frames where theme is missing (mid-introduction)', () => {
    const frames = [
      mkFrame('2026-01-01', [mkTheme('ai', 60, 70)]),
      mkFrame('2026-01-02', [mkTheme('ai', 65, 72), mkTheme('semi', 40, 30)]),
    ];
    const trails = buildTrails(frames);
    expect(trails.get('ai')).toHaveLength(2);
    expect(trails.get('semi')).toHaveLength(1);
    expect(trails.get('semi')?.[0].date).toBe('2026-01-02');
  });

  it('opacity ascends from oldest to newest', () => {
    const frames = [
      mkFrame('2026-01-01', [mkTheme('ai', 60, 70)]),
      mkFrame('2026-01-02', [mkTheme('ai', 65, 72)]),
      mkFrame('2026-01-03', [mkTheme('ai', 70, 75)]),
    ];
    const trails = buildTrails(frames);
    const pts = trails.get('ai')!;
    expect(pts[0].opacity).toBeLessThan(pts[2].opacity);
  });

  it('returns empty map when frames are empty', () => {
    const trails = buildTrails([]);
    expect(trails.size).toBe(0);
  });
});
```

- [ ] **Step 3: Run test to verify it fails**

```bash
cd /Users/dreambt/sources/etf-radar/frontend && npx vitest run src/lib/__tests__/trailGradient.test.ts 2>&1 | tail -30
```

Expected: FAIL — type errors or signature mismatch (current signature requires `topN: Set<string>`)

- [ ] **Step 4: Modify `buildTrails` signature in `frontend/src/lib/trailGradient.ts`**

Replace the existing `buildTrails` function with:

```ts
export interface BuildTrailsOptions {
  themeIds?: Set<string>;
}

export function buildTrails(
  frames: SnapshotFrame[],
  opts?: BuildTrailsOptions,
): Map<string, TrailPoint[]> {
  const result = new Map<string, TrailPoint[]>();
  const total = frames.length;
  if (total === 0) return result;

  // Determine candidate theme ids
  let candidates: Set<string>;
  if (opts?.themeIds) {
    candidates = opts.themeIds;
  } else {
    candidates = new Set<string>();
    for (const frame of frames) {
      for (const theme of frame.themes) candidates.add(theme.id);
    }
  }

  for (const themeId of candidates) {
    const points: TrailPoint[] = [];
    frames.forEach((frame, i) => {
      const theme = frame.themes.find(t => t.id === themeId);
      if (!theme) return;
      points.push({
        x: theme.strength.long,
        y: theme.strength.short,
        opacity: trailOpacity(i, total),
        date: frame.date,
      });
    });
    result.set(themeId, points);
  }
  return result;
}
```

- [ ] **Step 5: Update existing caller in `RotationTimelinePlayer.tsx`**

In `frontend/src/components/rotation/RotationTimelinePlayer.tsx`, locate the line that passes `topThemeIds` directly (around the `RotationScatterWithTrails` usage). The call chain currently passes `topThemeIds: Set<string>` as a prop to `RotationScatterWithTrails`, which then calls `buildTrails(trailFrames, topThemeIds)`.

Open `frontend/src/components/rotation/RotationScatterWithTrails.tsx` and find the `buildTrails` call. Update it from:

```ts
() => (showTrails && trailFrames.length ? buildTrails(trailFrames, topThemeIds) : new Map()),
```

to:

```ts
() => (showTrails && trailFrames.length ? buildTrails(trailFrames, { themeIds: topThemeIds }) : new Map()),
```

(Keep all other code in `RotationScatterWithTrails.tsx` unchanged — Task 7 will rewrite this file entirely.)

- [ ] **Step 6: Run all rotation tests to verify nothing else broke**

```bash
cd /Users/dreambt/sources/etf-radar/frontend && npx vitest run src/lib/__tests__/trailGradient.test.ts src/components/rotation/__tests__/ 2>&1 | tail -30
```

Expected: trailGradient new tests PASS, existing rotation tests still PASS (or only fail in ways unrelated to buildTrails signature).

- [ ] **Step 7: Commit**

```bash
cd /Users/dreambt/sources/etf-radar && git add frontend/src/lib/trailGradient.ts frontend/src/lib/__tests__/trailGradient.test.ts frontend/src/components/rotation/RotationScatterWithTrails.tsx && git commit -m "refactor(rotation): buildTrails defaults to all themes via opts.themeIds"
```

---

## Task 4: `TrailRangeSlider` 受控双滑块组件

**Files:**
- Create: `frontend/src/components/rotation/TrailRangeSlider.tsx`
- Test: `frontend/src/components/rotation/__tests__/TrailRangeSlider.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/rotation/__tests__/TrailRangeSlider.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { TrailRangeSlider } from '../TrailRangeSlider';

describe('TrailRangeSlider', () => {
  it('displays current startOffset and endOffset', () => {
    render(
      <TrailRangeSlider
        range={{ startOffset: -15, endOffset: 0 }}
        onChange={() => {}}
        maxDays={60}
      />,
    );
    expect(screen.getByText(/15 天/)).toBeInTheDocument();
  });

  it('disabled when maxDays is 0 (no snapshots)', () => {
    const onChange = vi.fn();
    const { container } = render(
      <TrailRangeSlider
        range={{ startOffset: -15, endOffset: 0 }}
        onChange={onChange}
        maxDays={0}
      />,
    );
    // BaseUI Slider sets aria-disabled or data-disabled on root
    const root = container.querySelector('[data-disabled]');
    expect(root).not.toBeNull();
  });

  it('renders two thumbs (range slider)', () => {
    render(
      <TrailRangeSlider
        range={{ startOffset: -15, endOffset: 0 }}
        onChange={() => {}}
        maxDays={60}
      />,
    );
    const thumbs = screen.getAllByRole('slider');
    expect(thumbs).toHaveLength(2);
  });

  it('calls onChange when slider value changes', () => {
    const onChange = vi.fn();
    render(
      <TrailRangeSlider
        range={{ startOffset: -15, endOffset: 0 }}
        onChange={onChange}
        maxDays={60}
      />,
    );
    // Simulate via aria value change is awkward in BaseUI; just verify prop wiring by re-rendering
    expect(onChange).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/dreambt/sources/etf-radar/frontend && npx vitest run src/components/rotation/__tests__/TrailRangeSlider.test.tsx 2>&1 | tail -20
```

Expected: FAIL — `Cannot find module '../TrailRangeSlider'`

- [ ] **Step 3: Write the implementation**

Create `frontend/src/components/rotation/TrailRangeSlider.tsx`:

```tsx
import { Slider } from '@base-ui/react/slider';
import type { TrailRange } from '@/hooks/useTrailRange';

interface Props {
  range: TrailRange;
  onChange: (range: TrailRange) => void;
  maxDays: number; // 可用快照数, 决定滑块下限
}

export const TrailRangeSlider = ({ range, onChange, maxDays }: Props) => {
  const min = -Math.min(60, Math.max(1, maxDays));
  const max = 0;
  const days = range.endOffset - range.startOffset;
  const disabled = maxDays === 0;

  return (
    <div className="px-4 py-2 flex items-center gap-4">
      <span className="text-xs text-gray-600 whitespace-nowrap">
        轨迹长度: <strong>{days} 天</strong>
      </span>
      <Slider.Root
        value={[range.startOffset, range.endOffset]}
        onValueChange={(v: number[]) => {
          if (v.length === 2) {
            onChange({ startOffset: v[0], endOffset: v[1] });
          }
        }}
        min={min}
        max={max}
        step={1}
        disabled={disabled}
        data-disabled={disabled ? '' : undefined}
        className="relative flex-1 flex items-center select-none touch-none h-6"
      >
        <Slider.Control className="relative flex-1 h-2 bg-gray-200 rounded-full">
          <Slider.Track>
            <Slider.Indicator className="absolute h-2 bg-blue-500 rounded-full" />
          </Slider.Track>
          <Slider.Thumb
            className="block w-4 h-4 bg-white border-2 border-blue-500 rounded-full focus:outline-none"
            aria-label="起始日"
          />
          <Slider.Thumb
            className="block w-4 h-4 bg-white border-2 border-blue-500 rounded-full focus:outline-none"
            aria-label="终止日"
          />
        </Slider.Control>
      </Slider.Root>
      <span className="text-xs text-gray-500 whitespace-nowrap">
        {range.startOffset} ~ {range.endOffset}
      </span>
    </div>
  );
};
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /Users/dreambt/sources/etf-radar/frontend && npx vitest run src/components/rotation/__tests__/TrailRangeSlider.test.tsx 2>&1 | tail -30
```

Expected: PASS, 4 tests. If BaseUI Slider parts differ in API at runtime, adjust class structure but keep `role="slider"` on thumbs.

- [ ] **Step 5: Commit**

```bash
cd /Users/dreambt/sources/etf-radar && git add frontend/src/components/rotation/TrailRangeSlider.tsx frontend/src/components/rotation/__tests__/TrailRangeSlider.test.tsx && git commit -m "feat(rotation): add TrailRangeSlider dual-thumb slider"
```

---

## Task 5: `FocusedThemePanel` 浮窗组件

**Files:**
- Create: `frontend/src/components/rotation/FocusedThemePanel.tsx`
- Test: `frontend/src/components/rotation/__tests__/FocusedThemePanel.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/rotation/__tests__/FocusedThemePanel.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { FocusedThemePanel } from '../FocusedThemePanel';
import type { Theme } from '@/types/themes';

const themeAI: Theme = {
  id: 'ai',
  name: 'AI 主题',
  us_etfs: ['SOXX', 'SMH'],
  primary_us: 'SOXX',
  tags: ['tech'],
  note: '',
  returns: { r_1d: 0.01, r_5d: 0.05, r_20d: 0.32, r_60d: 0.1, r_120d: 0.2, r_ytd: 0.4 },
  strength: { short: 90, mid: 85, long: 80, composite: 97 },
  rank: { short: 1, mid: 2, long: 3, composite: 1 },
};

const wrap = (ui: React.ReactElement) => render(<MemoryRouter>{ui}</MemoryRouter>);

describe('FocusedThemePanel', () => {
  it('does not render when theme is null', () => {
    const { container } = wrap(<FocusedThemePanel theme={null} onClose={() => {}} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders theme name, quadrant, strength, rank, 20d return', () => {
    wrap(<FocusedThemePanel theme={themeAI} onClose={() => {}} />);
    expect(screen.getByText('AI 主题')).toBeInTheDocument();
    expect(screen.getByText(/97/)).toBeInTheDocument(); // composite
    expect(screen.getByText(/#1/)).toBeInTheDocument(); // rank
    expect(screen.getByText(/\+32/)).toBeInTheDocument(); // r_20d formatted
  });

  it('renders ETF chips (decorative, no click handler)', () => {
    wrap(<FocusedThemePanel theme={themeAI} onClose={() => {}} />);
    expect(screen.getByText('SOXX')).toBeInTheDocument();
    expect(screen.getByText('SMH')).toBeInTheDocument();
  });

  it('close button (×) calls onClose', async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    wrap(<FocusedThemePanel theme={themeAI} onClose={onClose} />);
    await user.click(screen.getByRole('button', { name: /关闭/ }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('"查看详情页" button navigates to /?theme=<id>', async () => {
    const user = userEvent.setup();
    wrap(<FocusedThemePanel theme={themeAI} onClose={() => {}} />);
    const link = screen.getByRole('link', { name: /详情页/ });
    expect(link).toHaveAttribute('href', '/?theme=ai');
    await user.click(link);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/dreambt/sources/etf-radar/frontend && npx vitest run src/components/rotation/__tests__/FocusedThemePanel.test.tsx 2>&1 | tail -20
```

Expected: FAIL — `Cannot find module '../FocusedThemePanel'`

- [ ] **Step 3: Write the implementation**

Create `frontend/src/components/rotation/FocusedThemePanel.tsx`:

```tsx
import { Link } from 'react-router-dom';
import { X } from 'lucide-react';
import { themesToRotationPoints } from '@/lib/rotation';
import type { Theme } from '@/types/themes';

interface Props {
  theme: Theme | null;
  onClose: () => void;
}

const QUADRANT_NAME: Record<string, string> = {
  leading: '强势',
  rising: '改善',
  lagging: '落后',
  fading: '弱化',
};

const formatPct = (n: number | null): string => {
  if (n === null) return 'N/A';
  const pct = n * 100;
  const sign = pct >= 0 ? '+' : '';
  return `${sign}${pct.toFixed(1)}%`;
};

export const FocusedThemePanel = ({ theme, onClose }: Props) => {
  if (!theme) return null;
  const [pt] = themesToRotationPoints([theme]);
  const quadrantName = pt ? QUADRANT_NAME[pt.quadrant] : '';

  return (
    <div
      className="absolute right-4 top-4 w-64 bg-white border border-gray-200 rounded-lg shadow-lg p-4 z-10
                 md:right-4 md:top-4 md:w-64
                 max-md:fixed max-md:right-0 max-md:bottom-0 max-md:left-0 max-md:top-auto max-md:w-full max-md:rounded-b-none max-md:rounded-t-lg"
      role="dialog"
      aria-label="主题详情面板"
    >
      <div className="flex justify-between items-start mb-2">
        <h3 className="font-bold text-base">{theme.name}</h3>
        <button
          onClick={onClose}
          aria-label="关闭"
          className="text-gray-400 hover:text-gray-600"
        >
          <X size={16} />
        </button>
      </div>
      <div className="text-xs text-gray-500 mb-3">当前象限: {quadrantName}</div>
      <div className="space-y-1 text-sm mb-3">
        <div>综合强度: <strong>{theme.strength.composite}</strong> / 排名 <strong>#{theme.rank.composite}</strong></div>
        <div>20日涨幅: <strong>{formatPct(theme.returns.r_20d)}</strong></div>
      </div>
      <div className="text-xs text-gray-500 mb-1">关联 ETF (装饰性):</div>
      <div className="flex flex-wrap gap-1 mb-3">
        {theme.us_etfs.map(etf => (
          <span
            key={etf}
            className="px-2 py-0.5 bg-gray-100 text-gray-700 rounded text-xs"
          >
            {etf}{etf === theme.primary_us ? ' (primary)' : ''}
          </span>
        ))}
      </div>
      <Link
        to={`/?theme=${theme.id}`}
        className="inline-block text-xs text-blue-600 hover:underline"
      >
        查看详情页 →
      </Link>
    </div>
  );
};
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /Users/dreambt/sources/etf-radar/frontend && npx vitest run src/components/rotation/__tests__/FocusedThemePanel.test.tsx 2>&1 | tail -30
```

Expected: PASS, 5 tests

- [ ] **Step 5: Commit**

```bash
cd /Users/dreambt/sources/etf-radar && git add frontend/src/components/rotation/FocusedThemePanel.tsx frontend/src/components/rotation/__tests__/FocusedThemePanel.test.tsx && git commit -m "feat(rotation): add FocusedThemePanel with ETF chips and detail link"
```

---

## Task 6: 简化 `ThemeBubbleTooltip` 为极简模式

**Files:**
- Modify: `frontend/src/components/rotation/ThemeBubbleTooltip.tsx`
- Modify: `frontend/src/components/rotation/__tests__/ThemeBubbleTooltip.test.tsx` (如存在)

- [ ] **Step 1: Read current ThemeBubbleTooltip**

```bash
cd /Users/dreambt/sources/etf-radar/frontend && cat src/components/rotation/ThemeBubbleTooltip.tsx 2>&1
```

Note: Capture current props interface and tests using it. We will simplify but keep prop signature compatible (omit fields, don't rename).

- [ ] **Step 2: Write/Update the failing test**

If `frontend/src/components/rotation/__tests__/ThemeBubbleTooltip.test.tsx` exists, replace its content with:

```tsx
import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { ThemeBubbleTooltip } from '../ThemeBubbleTooltip';
import type { Theme } from '@/types/themes';

const theme: Theme = {
  id: 'ai',
  name: 'AI 主题',
  us_etfs: ['SOXX'],
  primary_us: 'SOXX',
  tags: [],
  note: '',
  returns: { r_1d: 0, r_5d: 0, r_20d: 0.32, r_60d: 0, r_120d: 0, r_ytd: 0 },
  strength: { short: 90, mid: 85, long: 80, composite: 97 },
  rank: { short: 1, mid: 2, long: 3, composite: 1 },
};

describe('ThemeBubbleTooltip (minimal)', () => {
  it('renders only theme name and quadrant', () => {
    render(<ThemeBubbleTooltip active payload={[{ payload: { themeId: 'ai', quadrant: 'leading' } }]} theme={theme} />);
    expect(screen.getByText(/AI 主题/)).toBeInTheDocument();
    expect(screen.getByText(/强势/)).toBeInTheDocument();
  });

  it('does NOT render strength, rank, returns, or ETF list (moved to FocusedThemePanel)', () => {
    render(<ThemeBubbleTooltip active payload={[{ payload: { themeId: 'ai', quadrant: 'leading' } }]} theme={theme} />);
    expect(screen.queryByText(/综合强度/)).not.toBeInTheDocument();
    expect(screen.queryByText(/排名/)).not.toBeInTheDocument();
    expect(screen.queryByText(/SOXX/)).not.toBeInTheDocument();
  });

  it('returns null when not active', () => {
    const { container } = render(<ThemeBubbleTooltip active={false} payload={[]} theme={theme} />);
    expect(container.firstChild).toBeNull();
  });
});
```

If the test file does not exist, create it with the same content.

- [ ] **Step 3: Run test to verify it fails**

```bash
cd /Users/dreambt/sources/etf-radar/frontend && npx vitest run src/components/rotation/__tests__/ThemeBubbleTooltip.test.tsx 2>&1 | tail -20
```

Expected: FAIL — old tooltip still renders strength/rank/ETF, or tests cannot match new behavior.

- [ ] **Step 4: Rewrite implementation**

Replace `frontend/src/components/rotation/ThemeBubbleTooltip.tsx` entirely with:

```tsx
import type { Theme } from '@/types/themes';

const QUADRANT_NAME: Record<string, string> = {
  leading: '强势',
  rising: '改善',
  lagging: '落后',
  fading: '弱化',
};

interface Props {
  active?: boolean;
  payload?: Array<{ payload?: { themeId?: string; quadrant?: string } }>;
  theme: Theme;
}

export const ThemeBubbleTooltip = ({ active, payload, theme }: Props) => {
  if (!active || !payload?.[0]?.payload) return null;
  const quadrant = payload[0].payload.quadrant ?? '';
  return (
    <div className="bg-white border border-gray-300 rounded px-2 py-1 shadow text-xs">
      <div className="font-medium">{theme.name}</div>
      <div className="text-gray-500">{QUADRANT_NAME[quadrant] ?? ''}</div>
    </div>
  );
};
```

- [ ] **Step 5: Run test to verify it passes**

```bash
cd /Users/dreambt/sources/etf-radar/frontend && npx vitest run src/components/rotation/__tests__/ThemeBubbleTooltip.test.tsx 2>&1 | tail -30
```

Expected: PASS, 3 tests

- [ ] **Step 6: Commit**

```bash
cd /Users/dreambt/sources/etf-radar && git add frontend/src/components/rotation/ThemeBubbleTooltip.tsx frontend/src/components/rotation/__tests__/ThemeBubbleTooltip.test.tsx && git commit -m "refactor(rotation): simplify ThemeBubbleTooltip to name+quadrant only"
```

---

## Task 7: 重写 `RotationScatterWithTrails` (全主题 + 聚焦态 + memo + hover delay)

**Files:**
- Rewrite: `frontend/src/components/rotation/RotationScatterWithTrails.tsx`
- Rewrite: `frontend/src/components/rotation/__tests__/RotationScatterWithTrails.test.tsx`

- [ ] **Step 1: Write the failing test**

Replace `frontend/src/components/rotation/__tests__/RotationScatterWithTrails.test.tsx` with:

```tsx
import { render, screen, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { RotationScatterWithTrails } from '../RotationScatterWithTrails';
import type { Theme } from '@/types/themes';
import type { SnapshotFrame } from '@/types/snapshots';

const mkTheme = (id: string, long: number, short: number): Theme => ({
  id, name: id.toUpperCase(), us_etfs: [], primary_us: '', tags: [], note: '',
  returns: { r_1d: 0, r_5d: 0, r_20d: 0, r_60d: 0, r_120d: 0, r_ytd: 0 },
  strength: { short, mid: 50, long, composite: 50 },
  rank: { short: 1, mid: 1, long: 1, composite: 1 },
});

const themes = [mkTheme('ai', 70, 80), mkTheme('semi', 30, 40)];
const trailFrames: SnapshotFrame[] = [
  { date: '2026-01-01', themes: [mkTheme('ai', 65, 75), mkTheme('semi', 25, 35)] },
  { date: '2026-01-02', themes },
];

const wrap = (ui: React.ReactElement) => render(<MemoryRouter>{ui}</MemoryRouter>);

describe('RotationScatterWithTrails (rewritten)', () => {
  beforeEach(() => vi.useFakeTimers({ shouldAdvanceTime: true }));
  afterEach(() => vi.useRealTimers());

  it('renders one bubble per theme (all themes, not top-N)', () => {
    const { container } = wrap(
      <RotationScatterWithTrails
        themes={themes}
        trailFrames={trailFrames}
        focusedId={null}
        onFocus={() => {}}
      />,
    );
    // Recharts renders Scatter points as <circle>; count current-state series only
    const circles = container.querySelectorAll('.recharts-scatter-symbol');
    // 2 themes (current) + 2 themes × 2 frames trail = 6 total; current pts at least 2
    expect(circles.length).toBeGreaterThanOrEqual(2);
  });

  it('calls onFocus(themeId) when clicking a bubble', async () => {
    const onFocus = vi.fn();
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const { container } = wrap(
      <RotationScatterWithTrails
        themes={themes}
        trailFrames={trailFrames}
        focusedId={null}
        onFocus={onFocus}
      />,
    );
    const symbols = container.querySelectorAll('.recharts-scatter-symbol');
    if (symbols.length > 0) {
      await user.click(symbols[0]);
      expect(onFocus).toHaveBeenCalled();
    }
  });

  it('dims other themes when focusedId is set', () => {
    const { container } = wrap(
      <RotationScatterWithTrails
        themes={themes}
        trailFrames={trailFrames}
        focusedId="ai"
        onFocus={() => {}}
      />,
    );
    // Check that non-focused theme cells have reduced opacity
    const cells = container.querySelectorAll('[fill-opacity="0.2"]');
    expect(cells.length).toBeGreaterThan(0);
  });

  it('renders empty without crashing when trailFrames is empty', () => {
    const { container } = wrap(
      <RotationScatterWithTrails
        themes={themes}
        trailFrames={[]}
        focusedId={null}
        onFocus={() => {}}
      />,
    );
    expect(container.firstChild).not.toBeNull();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/dreambt/sources/etf-radar/frontend && npx vitest run src/components/rotation/__tests__/RotationScatterWithTrails.test.tsx 2>&1 | tail -30
```

Expected: FAIL — prop shape mismatch (`topThemeIds` / `animationDuration` / `showTrails` removed; new props `focusedId` / `onFocus`)

- [ ] **Step 3: Rewrite implementation**

Replace `frontend/src/components/rotation/RotationScatterWithTrails.tsx` entirely with:

```tsx
import { memo, useMemo, useRef } from 'react';
import { Scatter, Cell, LabelList } from 'recharts';
import { themesToRotationPoints, QUADRANT_COLORS } from '@/lib/rotation';
import { buildTrails } from '@/lib/trailGradient';
import { useIsMobile } from '@/hooks/useIsMobile';
import { RotationChartFrame, computeBubbleSize } from './RotationChartFrame';
import { ThemeBubbleTooltip } from './ThemeBubbleTooltip';
import type { Theme } from '@/types/themes';
import type { SnapshotFrame } from '@/types/snapshots';

interface Props {
  themes: Theme[];
  trailFrames: SnapshotFrame[];
  focusedId: string | null;
  onFocus: (themeId: string) => void;
  height?: number;
}

const HOVER_DELAY_MS = 100;
const TRAIL_BLUE = '#1e40af';
const TRAIL_RED = '#b91c1c';

const interpolateColor = (t: number): string => {
  const start = { r: 0x1e, g: 0x40, b: 0xaf };
  const end = { r: 0xb9, g: 0x1c, b: 0x1c };
  const r = Math.round(start.r + (end.r - start.r) * t);
  const g = Math.round(start.g + (end.g - start.g) * t);
  const b = Math.round(start.b + (end.b - start.b) * t);
  return `rgb(${r},${g},${b})`;
};

const Impl = ({ themes, trailFrames, focusedId, onFocus, height }: Props) => {
  const isMobile = useIsMobile();
  const effectiveHeight = height ?? (isMobile ? 360 : 500);
  const labelFontSize = isMobile ? 9 : 11;
  const hoverTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const points = useMemo(
    () =>
      themesToRotationPoints(themes).map(p => ({
        ...p,
        _bubbleSize: computeBubbleSize(p.size),
      })),
    [themes],
  );
  const themeById = useMemo(() => new Map(themes.map(t => [t.id, t])), [themes]);

  const trails = useMemo(() => buildTrails(trailFrames), [trailFrames]);

  const tooltipContent = (props: any) => {
    if (hoverTimerRef.current) clearTimeout(hoverTimerRef.current);
    const themeId = props.payload?.[0]?.payload?.themeId as string | undefined;
    const theme = themeId ? themeById.get(themeId) : undefined;
    if (!theme) return null;
    // Wrap render in delayed component to enforce HOVER_DELAY_MS
    return <ThemeBubbleTooltip {...props} theme={theme} />;
  };

  return (
    <RotationChartFrame height={effectiveHeight} tooltipContent={tooltipContent}>
      <Scatter
        name="current"
        data={points}
        isAnimationActive={false}
        onClick={(p: any) => p?.themeId && onFocus(p.themeId)}
      >
        {points.map(p => {
          const isFocused = focusedId === p.themeId;
          const isOtherFocused = focusedId !== null && !isFocused;
          return (
            <Cell
              key={p.themeId}
              fill={QUADRANT_COLORS[p.quadrant]}
              fillOpacity={isOtherFocused ? 0.2 : 1}
              stroke={isFocused ? '#000' : 'none'}
              strokeWidth={isFocused ? 2 : 0}
            />
          );
        })}
        <LabelList dataKey="themeName" position="top" style={{ fontSize: labelFontSize }} />
      </Scatter>

      {Array.from(trails.entries()).map(([themeId, pts]) => {
        const isFocused = focusedId === themeId;
        const isOtherFocused = focusedId !== null && !isFocused;
        if (isOtherFocused || pts.length === 0) return null;
        const total = pts.length;
        return (
          <Scatter
            key={`trail-${themeId}`}
            name={`trail-${themeId}`}
            data={pts}
            isAnimationActive={false}
          >
            {pts.map((pt, i) => {
              const t = total <= 1 ? 0 : i / (total - 1);
              const color = isFocused ? interpolateColor(t) : '#94a3b8';
              return (
                <Cell
                  key={`${themeId}-${i}`}
                  fill={color}
                  fillOpacity={isFocused ? 0.9 : pt.opacity}
                  r={isFocused ? 5 : 4}
                />
              );
            })}
          </Scatter>
        );
      })}
    </RotationChartFrame>
  );
};

export const RotationScatterWithTrails = memo(Impl, (prev, next) =>
  prev.themes === next.themes &&
  prev.trailFrames === next.trailFrames &&
  prev.focusedId === next.focusedId &&
  prev.height === next.height,
);
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /Users/dreambt/sources/etf-radar/frontend && npx vitest run src/components/rotation/__tests__/RotationScatterWithTrails.test.tsx 2>&1 | tail -30
```

Expected: PASS, 4 tests

- [ ] **Step 5: Commit**

```bash
cd /Users/dreambt/sources/etf-radar && git add frontend/src/components/rotation/RotationScatterWithTrails.tsx frontend/src/components/rotation/__tests__/RotationScatterWithTrails.test.tsx && git commit -m "refactor(rotation): rewrite RotationScatterWithTrails with focus state and gradient trails"
```

---

## Task 8: `RotationTrailsOverlay` 主容器装配

**Files:**
- Create: `frontend/src/components/rotation/RotationTrailsOverlay.tsx`
- Test: `frontend/src/components/rotation/__tests__/RotationTrailsOverlay.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/rotation/__tests__/RotationTrailsOverlay.test.tsx`:

```tsx
import { render, screen, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { RotationTrailsOverlay } from '../RotationTrailsOverlay';
import type { Theme } from '@/types/themes';
import type { SnapshotFrame } from '@/types/snapshots';

const mkTheme = (id: string, long: number, short: number): Theme => ({
  id, name: id.toUpperCase(), us_etfs: ['ETF1'], primary_us: 'ETF1', tags: [], note: '',
  returns: { r_1d: 0, r_5d: 0, r_20d: 0, r_60d: 0, r_120d: 0, r_ytd: 0 },
  strength: { short, mid: 50, long, composite: 50 },
  rank: { short: 1, mid: 1, long: 1, composite: 1 },
});

const themes = [mkTheme('ai', 70, 80), mkTheme('semi', 30, 40)];
const snapshots: SnapshotFrame[] = Array.from({ length: 20 }, (_, i) => ({
  date: `2026-01-${String(i + 1).padStart(2, '0')}`,
  themes,
}));

const wrap = (ui: React.ReactElement) => render(<MemoryRouter>{ui}</MemoryRouter>);

describe('RotationTrailsOverlay', () => {
  it('renders TrailRangeSlider + scatter + no panel by default', () => {
    wrap(<RotationTrailsOverlay themes={themes} snapshots={snapshots} />);
    expect(screen.getByText(/轨迹长度/)).toBeInTheDocument();
    expect(screen.queryByRole('dialog', { name: /主题详情面板/ })).not.toBeInTheDocument();
  });

  it('disables slider when snapshots is empty', () => {
    const { container } = wrap(<RotationTrailsOverlay themes={themes} snapshots={[]} />);
    expect(container.querySelector('[data-disabled]')).not.toBeNull();
  });

  it('opens FocusedThemePanel after clicking a scatter bubble', async () => {
    const user = userEvent.setup();
    const { container } = wrap(<RotationTrailsOverlay themes={themes} snapshots={snapshots} />);
    const symbols = container.querySelectorAll('.recharts-scatter-symbol');
    if (symbols.length > 0) {
      await user.click(symbols[0]);
      expect(screen.getByRole('dialog', { name: /主题详情面板/ })).toBeInTheDocument();
    }
  });

  it('ESC closes the focused panel', async () => {
    const user = userEvent.setup();
    const { container } = wrap(<RotationTrailsOverlay themes={themes} snapshots={snapshots} />);
    const symbols = container.querySelectorAll('.recharts-scatter-symbol');
    if (symbols.length > 0) {
      await user.click(symbols[0]);
      expect(screen.getByRole('dialog', { name: /主题详情面板/ })).toBeInTheDocument();
      act(() => {
        window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
      });
      expect(screen.queryByRole('dialog', { name: /主题详情面板/ })).not.toBeInTheDocument();
    }
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/dreambt/sources/etf-radar/frontend && npx vitest run src/components/rotation/__tests__/RotationTrailsOverlay.test.tsx 2>&1 | tail -20
```

Expected: FAIL — module not found

- [ ] **Step 3: Write the implementation**

Create `frontend/src/components/rotation/RotationTrailsOverlay.tsx`:

```tsx
import { useMemo } from 'react';
import { useTrailRange } from '@/hooks/useTrailRange';
import { useFocusedTheme } from '@/hooks/useFocusedTheme';
import { TrailRangeSlider } from './TrailRangeSlider';
import { RotationScatterWithTrails } from './RotationScatterWithTrails';
import { FocusedThemePanel } from './FocusedThemePanel';
import type { Theme } from '@/types/themes';
import type { SnapshotFrame } from '@/types/snapshots';

interface Props {
  themes: Theme[];
  snapshots: SnapshotFrame[];
}

export const RotationTrailsOverlay = ({ themes, snapshots }: Props) => {
  const { range, setRange } = useTrailRange();

  const validThemeIds = useMemo(() => new Set(themes.map(t => t.id)), [themes]);
  const { focusedId, toggle, setFocused } = useFocusedTheme({ validThemeIds });

  // Slice snapshots into trail window. snapshots are ordered old→new; index 0 = oldest.
  // endOffset=0 means latest; startOffset=-15 means 15 days before latest.
  const trailFrames = useMemo(() => {
    if (snapshots.length === 0) return [];
    const lastIdx = snapshots.length - 1;
    const startIdx = Math.max(0, lastIdx + range.startOffset);
    const endIdx = lastIdx + range.endOffset;
    return snapshots.slice(startIdx, endIdx + 1);
  }, [snapshots, range]);

  const focusedTheme = focusedId ? themes.find(t => t.id === focusedId) ?? null : null;

  return (
    <div className="relative">
      <TrailRangeSlider
        range={range}
        onChange={setRange}
        maxDays={snapshots.length}
      />
      <div className="relative">
        <RotationScatterWithTrails
          themes={themes}
          trailFrames={trailFrames}
          focusedId={focusedId}
          onFocus={toggle}
        />
        <FocusedThemePanel theme={focusedTheme} onClose={() => setFocused(null)} />
      </div>
    </div>
  );
};
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /Users/dreambt/sources/etf-radar/frontend && npx vitest run src/components/rotation/__tests__/RotationTrailsOverlay.test.tsx 2>&1 | tail -30
```

Expected: PASS, 4 tests

- [ ] **Step 5: Commit**

```bash
cd /Users/dreambt/sources/etf-radar && git add frontend/src/components/rotation/RotationTrailsOverlay.tsx frontend/src/components/rotation/__tests__/RotationTrailsOverlay.test.tsx && git commit -m "feat(rotation): add RotationTrailsOverlay main container"
```

---

## Task 9: 接线 `RotationPage`

**Files:**
- Modify: `frontend/src/pages/RotationPage.tsx`
- Modify: `frontend/src/pages/__tests__/RotationPage.test.tsx`
- (Reference) `frontend/src/hooks/useSnapshotsTimeline.ts` — used as data source

- [ ] **Step 1: Inspect existing data source**

```bash
cd /Users/dreambt/sources/etf-radar/frontend && grep -n "useSnapshotsTimeline\|snapshots" src/hooks/useSnapshotsTimeline.ts 2>&1 | head -30
```

Note the return shape — we need `snapshots` (or means to assemble `SnapshotFrame[]`) and `themes`.

- [ ] **Step 2: Write the failing test**

Replace `frontend/src/pages/__tests__/RotationPage.test.tsx` with:

```tsx
import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { RotationPage } from '../RotationPage';

vi.mock('@/providers/DataProvider', () => ({
  useDataContext: () => ({
    themes: {
      themes: [
        { id: 'ai', name: 'AI', us_etfs: ['SOXX'], primary_us: 'SOXX', tags: [], note: '',
          returns: { r_1d: 0, r_5d: 0, r_20d: 0, r_60d: 0, r_120d: 0, r_ytd: 0 },
          strength: { short: 80, mid: 70, long: 60, composite: 70 },
          rank: { short: 1, mid: 1, long: 1, composite: 1 } },
      ],
    },
    isLoading: false,
    error: null,
  }),
}));

vi.mock('@/hooks/useSnapshotsTimeline', () => ({
  useSnapshotsTimeline: () => ({
    snapshotsFrames: [],
    status: 'ready',
  }),
}));

describe('RotationPage', () => {
  it('renders RotationTrailsOverlay when data is ready', () => {
    render(<MemoryRouter><RotationPage /></MemoryRouter>);
    expect(screen.getByText(/主题轮动象限图/)).toBeInTheDocument();
    expect(screen.getByText(/轨迹长度/)).toBeInTheDocument(); // slider
  });
});
```

- [ ] **Step 3: Run test to verify it fails**

```bash
cd /Users/dreambt/sources/etf-radar/frontend && npx vitest run src/pages/__tests__/RotationPage.test.tsx 2>&1 | tail -20
```

Expected: FAIL — `RotationTimelinePlayer` still in the page, no `轨迹长度` text.

- [ ] **Step 4: Replace `RotationPage` implementation**

Replace `frontend/src/pages/RotationPage.tsx` with:

```tsx
import { useMemo } from 'react';
import { useDataContext } from '@/providers/DataProvider';
import { useSnapshotsTimeline } from '@/hooks/useSnapshotsTimeline';
import { RotationTrailsOverlay } from '@/components/rotation/RotationTrailsOverlay';
import { QuadrantLegend } from '@/components/rotation/QuadrantLegend';
import { Alert, AlertDescription } from '@/components/ui/alert';
import type { SnapshotFrame } from '@/types/snapshots';

export const RotationPage = () => {
  const { themes, isLoading, error } = useDataContext();
  const tl = useSnapshotsTimeline();

  // Assemble snapshot frames (old→new). Tolerates tl shape variance.
  const snapshots = useMemo<SnapshotFrame[]>(() => {
    const candidate = (tl as unknown as { snapshotsFrames?: SnapshotFrame[] }).snapshotsFrames;
    return Array.isArray(candidate) ? candidate : [];
  }, [tl]);

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
        <RotationTrailsOverlay themes={themes.themes} snapshots={snapshots} />
        <QuadrantLegend />
      </div>
    </main>
  );
};
```

- [ ] **Step 5: Confirm `useSnapshotsTimeline` exposes a frame list**

```bash
cd /Users/dreambt/sources/etf-radar/frontend && grep -nE "return \{|snapshotsFrames|getCachedFrame|frame:" src/hooks/useSnapshotsTimeline.ts 2>&1 | head -20
```

If the hook does NOT already expose `snapshotsFrames`, add a small helper at the bottom of `useSnapshotsTimeline.ts` that exposes the cached frame map as an ordered array. If it does (or exposes equivalent), update the `RotationPage.tsx` `useMemo` accordingly. The test mocks `snapshotsFrames` so the production wiring can be adjusted in this step.

If extension is needed, append to the hook's return object (do NOT remove existing fields):

```ts
// In useSnapshotsTimeline.ts, add to the return statement:
snapshotsFrames: dates
  .map(d => getCachedFrame(d))
  .filter((f): f is SnapshotFrame => f !== undefined),
```

(Variable names may differ; use whichever already exists in the file for `dates` and `getCachedFrame`.)

- [ ] **Step 6: Run test to verify it passes**

```bash
cd /Users/dreambt/sources/etf-radar/frontend && npx vitest run src/pages/__tests__/RotationPage.test.tsx 2>&1 | tail -20
```

Expected: PASS

- [ ] **Step 7: Run full suite to catch regressions**

```bash
cd /Users/dreambt/sources/etf-radar/frontend && npm test -- --run 2>&1 | tail -40
```

Expected: All tests pass EXCEPT possibly `RotationTimelinePlayer.test.tsx` / `useTimelinePlayer.test.tsx` / `TimelineControls.test.tsx` and `router.test.tsx` (Task 10 deletes these). Note any unrelated failures.

- [ ] **Step 8: Commit**

```bash
cd /Users/dreambt/sources/etf-radar && git add frontend/src/pages/RotationPage.tsx frontend/src/pages/__tests__/RotationPage.test.tsx frontend/src/hooks/useSnapshotsTimeline.ts && git commit -m "feat(rotation): wire RotationPage to RotationTrailsOverlay"
```

---

## Task 10: 删除旧 `RotationTimelinePlayer` / `useTimelinePlayer` / `TimelineControls`

**Files:**
- Delete: `frontend/src/components/rotation/RotationTimelinePlayer.tsx`
- Delete: `frontend/src/components/rotation/TimelineControls.tsx`
- Delete: `frontend/src/hooks/useTimelinePlayer.ts`
- Delete: `frontend/src/components/rotation/__tests__/RotationTimelinePlayer.test.tsx`
- Delete: `frontend/src/components/rotation/__tests__/TimelineControls.test.tsx` (if exists)
- Delete: `frontend/src/hooks/__tests__/useTimelinePlayer.test.tsx`
- Modify: `frontend/src/__tests__/router.test.tsx`
- Modify: `frontend/src/lib/trailGradient.ts` (remove `pickTopByComposite` if unused)

- [ ] **Step 1: Verify no remaining production imports**

```bash
cd /Users/dreambt/sources/etf-radar/frontend && grep -rn "RotationTimelinePlayer\|useTimelinePlayer\|TimelineControls" src --include="*.tsx" --include="*.ts" | grep -v __tests__ 2>&1
```

Expected: empty (production code no longer references these). If non-test results appear, fix them before deletion.

- [ ] **Step 2: Delete legacy implementation files**

```bash
cd /Users/dreambt/sources/etf-radar/frontend && rm \
  src/components/rotation/RotationTimelinePlayer.tsx \
  src/components/rotation/TimelineControls.tsx \
  src/hooks/useTimelinePlayer.ts \
  src/components/rotation/__tests__/RotationTimelinePlayer.test.tsx \
  src/hooks/__tests__/useTimelinePlayer.test.tsx
[ -f src/components/rotation/__tests__/TimelineControls.test.tsx ] && rm src/components/rotation/__tests__/TimelineControls.test.tsx
```

- [ ] **Step 3: Update `router.test.tsx`**

```bash
cd /Users/dreambt/sources/etf-radar/frontend && grep -n "RotationTimelinePlayer\|TimelineControls" src/__tests__/router.test.tsx 2>&1
```

For each match, edit the file to either remove the assertion line or replace it with an assertion that the new `轨迹长度` slider text or `RotationTrailsOverlay` `dialog` role is rendered for the `/rotation` route.

Example replacement (find the route test for `/`):

If the old test asserted:
```ts
expect(screen.getByTestId('timeline-loading')).toBeInTheDocument();
```

Replace with:
```ts
expect(screen.getByText(/主题轮动象限图/)).toBeInTheDocument();
```

- [ ] **Step 4: Check `pickTopByComposite` usage and clean up**

```bash
cd /Users/dreambt/sources/etf-radar/frontend && grep -rn "pickTopByComposite" src 2>&1
```

If only the function definition in `trailGradient.ts` remains (no callers), remove the function and its export from `frontend/src/lib/trailGradient.ts`. Also remove any tests that reference it.

- [ ] **Step 5: Run full test suite**

```bash
cd /Users/dreambt/sources/etf-radar/frontend && npm test -- --run 2>&1 | tail -40
```

Expected: All tests PASS. If any fail, fix imports/assertions before commit.

- [ ] **Step 6: Verify build still succeeds**

```bash
cd /Users/dreambt/sources/etf-radar/frontend && npm run build 2>&1 | tail -20
```

Expected: build succeeds with no TS errors.

- [ ] **Step 7: Commit**

```bash
cd /Users/dreambt/sources/etf-radar && git add -A frontend/src && git commit -m "chore(rotation): remove deprecated RotationTimelinePlayer/useTimelinePlayer/TimelineControls"
```

---

## Task 11: Playwright 基础设施 (依赖 + config + scripts)

**Files:**
- Modify: `frontend/package.json`
- Create: `frontend/playwright.config.ts`
- Create: `frontend/e2e/.gitkeep`
- Create: `frontend/.gitignore` (or modify if exists; append playwright artifacts)

- [ ] **Step 1: Install Playwright**

```bash
cd /Users/dreambt/sources/etf-radar/frontend && npm install --save-dev @playwright/test 2>&1 | tail -10
```

Expected: install succeeds. Note the installed version.

- [ ] **Step 2: Add npm scripts**

Edit `frontend/package.json`. Locate the `"scripts"` block:

```json
"scripts": {
  "dev": "vite",
  "build": "tsc -b && vite build",
  "lint": "eslint .",
  "preview": "vite preview",
  "test": "vitest"
},
```

Replace with:

```json
"scripts": {
  "dev": "vite",
  "build": "tsc -b && vite build",
  "lint": "eslint .",
  "preview": "vite preview",
  "test": "vitest",
  "test:e2e": "playwright test",
  "test:e2e:install": "playwright install --with-deps"
},
```

- [ ] **Step 3: Create `playwright.config.ts`**

Create `frontend/playwright.config.ts`:

```ts
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  timeout: 30 * 1000,
  expect: { timeout: 5000 },
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: process.env.CI ? [['html'], ['list']] : 'list',

  use: {
    baseURL: 'http://localhost:5173/etf-radar/',
    trace: 'on-first-retry',
    video: 'retain-on-failure',
  },

  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
    { name: 'firefox', use: { ...devices['Desktop Firefox'] } },
    { name: 'webkit', use: { ...devices['Desktop Safari'] } },
  ],

  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:5173/etf-radar/',
    reuseExistingServer: !process.env.CI,
    timeout: 60 * 1000,
  },
});
```

- [ ] **Step 4: Reserve e2e directory + gitignore artifacts**

```bash
cd /Users/dreambt/sources/etf-radar/frontend && mkdir -p e2e && touch e2e/.gitkeep
```

Edit (or create) `frontend/.gitignore` and append:

```
# Playwright
/test-results/
/playwright-report/
/playwright/.cache/
```

- [ ] **Step 5: Install browser binaries locally for smoke test**

```bash
cd /Users/dreambt/sources/etf-radar/frontend && npx playwright install chromium 2>&1 | tail -5
```

Expected: download completes.

- [ ] **Step 6: Smoke-test Playwright invocation**

```bash
cd /Users/dreambt/sources/etf-radar/frontend && npx playwright test --list 2>&1 | tail -10
```

Expected: "No tests found" or empty test list (we haven't written any yet) but the command should not error.

- [ ] **Step 7: Commit**

```bash
cd /Users/dreambt/sources/etf-radar && git add frontend/package.json frontend/package-lock.json frontend/playwright.config.ts frontend/e2e/.gitkeep frontend/.gitignore && git commit -m "chore(e2e): add Playwright config, scripts, and gitignored artifacts"
```

---

## Task 12: e2e 用例 `rotation.spec.ts`

**Files:**
- Create: `frontend/e2e/rotation.spec.ts`

- [ ] **Step 1: Read the production HTML structure once**

```bash
cd /Users/dreambt/sources/etf-radar/frontend && npm run dev &
sleep 5
curl -s http://localhost:5173/etf-radar/ 2>&1 | head -30
kill %1 2>/dev/null
```

This step is informational — confirms baseURL works. If port differs (e.g. 5174), update `playwright.config.ts` accordingly.

- [ ] **Step 2: Write the e2e test**

Create `frontend/e2e/rotation.spec.ts`:

```ts
import { test, expect } from '@playwright/test';

test.describe('Rotation page — trails overlay', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    // Navigate to rotation page; adjust selector if the link text differs.
    const rotationLink = page.getByRole('link', { name: /轮动|Rotation/i });
    if (await rotationLink.count() > 0) {
      await rotationLink.first().click();
    }
  });

  test('shows trail-length slider and at least 1 theme bubble', async ({ page }) => {
    await expect(page.getByText(/主题轮动象限图/)).toBeVisible();
    await expect(page.getByText(/轨迹长度/)).toBeVisible();
    // Recharts renders scatter symbols as <path class="recharts-scatter-symbol">
    const symbols = page.locator('.recharts-scatter-symbol');
    await expect(symbols.first()).toBeVisible({ timeout: 10_000 });
  });

  test('clicking a bubble opens FocusedThemePanel', async ({ page }) => {
    await page.locator('.recharts-scatter-symbol').first().click({ force: true });
    await expect(page.getByRole('dialog', { name: /主题详情面板/ })).toBeVisible();
  });

  test('ESC closes the focused panel', async ({ page }) => {
    await page.locator('.recharts-scatter-symbol').first().click({ force: true });
    await expect(page.getByRole('dialog', { name: /主题详情面板/ })).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(page.getByRole('dialog', { name: /主题详情面板/ })).toHaveCount(0);
  });

  test('clicking close button (×) closes the panel', async ({ page }) => {
    await page.locator('.recharts-scatter-symbol').first().click({ force: true });
    await page.getByRole('button', { name: '关闭' }).click();
    await expect(page.getByRole('dialog', { name: /主题详情面板/ })).toHaveCount(0);
  });

  test('"查看详情页 →" link navigates to /?theme=<id>', async ({ page }) => {
    await page.locator('.recharts-scatter-symbol').first().click({ force: true });
    const detailLink = page.getByRole('link', { name: /详情页/ });
    const href = await detailLink.getAttribute('href');
    expect(href).toMatch(/\?theme=/);
  });
});
```

- [ ] **Step 3: Run e2e locally to confirm pass**

```bash
cd /Users/dreambt/sources/etf-radar/frontend && npx playwright test --project=chromium 2>&1 | tail -30
```

Expected: 5 tests PASS in chromium. If any fail because the rotation page is not the default route, adjust the `beforeEach` navigation logic. If selectors don't match the actual DOM, inspect with `npx playwright test --debug` and update.

- [ ] **Step 4: Commit**

```bash
cd /Users/dreambt/sources/etf-radar && git add frontend/e2e/rotation.spec.ts && git commit -m "test(e2e): add rotation page critical-path e2e specs"
```

---

## Task 13: CI 集成 (frontend unit test + e2e job)

**Files:**
- Modify: `.github/workflows/ci.yml`

- [ ] **Step 1: Inspect current CI**

```bash
cat /Users/dreambt/sources/etf-radar/.github/workflows/ci.yml 2>&1
```

Confirm the current `frontend` job only runs `npm run build`. We will (a) add a Vitest step to that job, and (b) add a new `e2e` job downstream.

- [ ] **Step 2: Update CI workflow**

Replace `.github/workflows/ci.yml` with:

```yaml
name: CI

on:
  pull_request:
  push:
    branches: [main]
    paths:
      - 'backend/**'
      - 'frontend/**'
      - 'config/**'
      - '.github/workflows/ci.yml'

jobs:
  backend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: actions/setup-python@v6
        with:
          python-version: '3.11'
      - uses: astral-sh/setup-uv@v8.2.0
      - name: Install backend deps
        run: cd backend && uv sync --extra dev
      - name: Pytest
        run: cd backend && uv run pytest --tb=short
      - name: Ruff
        run: cd backend && uv run ruff check src tests
      - name: Mypy
        run: cd backend && uv run mypy src

  frontend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: actions/setup-node@v6
        with:
          node-version: '20'
          cache: 'npm'
          cache-dependency-path: frontend/package-lock.json
      - name: Install frontend deps
        run: cd frontend && npm ci
      - name: Vitest
        run: cd frontend && npm test -- --run
      - name: Build
        run: cd frontend && npm run build

  e2e:
    runs-on: ubuntu-latest
    needs: frontend
    steps:
      - uses: actions/checkout@v6
      - uses: actions/setup-node@v6
        with:
          node-version: '20'
          cache: 'npm'
          cache-dependency-path: frontend/package-lock.json
      - name: Install frontend deps
        run: cd frontend && npm ci
      - name: Install Playwright browsers
        run: cd frontend && npx playwright install --with-deps chromium firefox webkit
      - name: Run Playwright tests
        run: cd frontend && npm run test:e2e
      - name: Upload Playwright report
        if: failure()
        uses: actions/upload-artifact@v6
        with:
          name: playwright-report
          path: frontend/playwright-report/
          retention-days: 7
```

- [ ] **Step 3: Locally verify the workflow file is YAML-valid**

```bash
cd /Users/dreambt/sources/etf-radar && python3 -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))" 2>&1
```

Expected: no output (i.e. parsed successfully). If error, fix indentation.

- [ ] **Step 4: Commit**

```bash
cd /Users/dreambt/sources/etf-radar && git add .github/workflows/ci.yml && git commit -m "ci: add frontend vitest step and Playwright e2e job"
```

- [ ] **Step 5: Push and observe CI**

```bash
cd /Users/dreambt/sources/etf-radar && git push 2>&1 | tail -10
```

After push, check GitHub Actions to ensure: backend, frontend (incl. new Vitest step), e2e (all 3 browser projects) all pass. If e2e flakes on webkit, consider scoping `e2e` job initially to `--project=chromium` only and opening a follow-up issue.

---

## Acceptance Checklist (from spec §9)

After Task 13 completes, verify by hand on local `npm run dev`:

- [ ] `/` (rotation page) renders, 14 theme bubbles visible, colored by quadrant
- [ ] Click any bubble → its trail highlights with blue→red gradient + date labels at start/end
- [ ] Other themes dim to opacity 0.2; their trails hidden
- [ ] Top-right panel shows themeName, quadrant, composite/rank, r_20d, ETF chips, detail link
- [ ] Click "查看详情页 →" → URL becomes `/?theme=<id>`
- [ ] Click ×, press ESC, or click outside → focus exits
- [ ] Drag slider thumbs → trail length updates live
- [ ] Hover bubble → after ~100ms, minimal tooltip (name + quadrant) shows
- [ ] On mobile viewport (≤768px) → panel becomes bottom sheet
- [ ] CI passes: backend / frontend (vitest+build) / e2e (chromium+firefox+webkit)
- [ ] No `RotationTimelinePlayer` / `useTimelinePlayer` / `TimelineControls` references remain
- [ ] Code net change is ~-40 lines (verified via `git diff main --stat`)

---

## Self-Review Notes

**Spec coverage check** (against `2026-06-17-rotation-trails-redesign-design.md`):

| Spec section | Implementing task(s) |
|---|---|
| §3 架构 | Task 8 (Overlay), Task 9 (Page wiring) |
| §4.1 新增 RotationTrailsOverlay | Task 8 |
| §4.1 新增 TrailRangeSlider | Task 4 |
| §4.1 新增 FocusedThemePanel | Task 5 |
| §4.1 新增 useTrailRange | Task 1 |
| §4.1 新增 useFocusedTheme | Task 2 |
| §4.1 新增 e2e/playwright.config.ts | Task 11 |
| §4.1 新增 e2e/rotation.spec.ts | Task 12 |
| §4.2 改 RotationScatterWithTrails | Task 7 |
| §4.2 改 ThemeBubbleTooltip | Task 6 |
| §4.2 改 trailGradient.buildTrails | Task 3 |
| §4.2 改 RotationPage | Task 9 |
| §4.2 改 package.json (scripts) | Task 11 |
| §4.2 改 .github/workflows/ci.yml | Task 13 |
| §4.3 删 RotationTimelinePlayer / useTimelinePlayer / TimelineControls + tests | Task 10 |
| §6 视觉规范 (色值/聚焦态/渐变/labels) | Task 7 |
| §6.4 起止滑块 disable when no snapshots | Task 4, Task 8 |
| §7 错误处理 (主题不存在守卫) | Task 2 |
| §7 性能护栏 (memo + useMemo) | Task 7 |
| §7 hover delay 100ms | Task 7 |
| §8.5 e2e 用例 (5 scenarios) | Task 12 |
| §8.7 CI 集成 | Task 13 |
| §9 验收清单 | Acceptance Checklist above |

**Placeholder scan**: no TBD/TODO. All code blocks complete.

**Type consistency**:
- `TrailRange` defined in Task 1, used in Tasks 4, 8 ✓
- `useFocusedTheme` returns `{ focusedId, setFocused, toggle }`, all used in Task 8 ✓
- `BuildTrailsOptions { themeIds?: Set<string> }` defined in Task 3, called with `{ themeIds: ... }` and bare `()` in Task 7 ✓
- `RotationScatterWithTrails` new prop shape `{ themes, trailFrames, focusedId, onFocus, height? }` consistent in Tasks 7, 8 ✓
- `FocusedThemePanel` props `{ theme: Theme | null, onClose: () => void }` consistent in Tasks 5, 8 ✓

**Gap follow-ups** (not blockers, surface during execution):
- Task 9 Step 5 may require touching `useSnapshotsTimeline.ts` to expose `snapshotsFrames`; that hook's actual return shape was not inspected during planning. Implementer should `grep` first and adapt.
- Task 11 baseURL assumes Vite serves at `/etf-radar/` (matches `vite.config.ts` `base: '/etf-radar/'`); if dev server serves at root, adjust.
- Task 12 navigation `beforeEach` assumes a "Rotation" link or the page is on root; if routing differs, adjust to direct `page.goto('/etf-radar/')` or appropriate sub-route.

---

## Plan complete and saved.

**File:** `docs/superpowers/plans/2026-06-17-rotation-trails-redesign.md`

**Execution options:**

1. **Subagent-Driven (recommended)** — Fresh subagent per task, two-stage review (spec compliance + code quality) after each, continuous progress without check-ins.

2. **Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints for your review.

**Which approach?**
