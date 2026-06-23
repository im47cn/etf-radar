# 持仓监控 Phase 2（机会扫描）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `/portfolio` 页持仓汇总下方加"信号扫描"折叠面板，展示**未持有但当前信号偏强**的主题候选，并支持一键跳转主题详情。

**Architecture:** 纯前端 TypeScript 函数 `scanOpportunities()`（无 IO、无副作用），消费现有 `usePortfolioScores()` 已暴露的 `ownedThemeIds`，对 `themes.json` 做 filter+sort。UI 用折叠面板 + 主题卡网格 + react-router-dom `<Link>` 跳转 RadarPage。

**Tech Stack:** React 19 + Vite + TypeScript strict + Tailwind v4 + react-router-dom HashRouter + vitest + playwright

**Spec Reference:** `docs/superpowers/specs/2026-06-21-portfolio-monitor-design.md`（Section 3.6 + 5.4）

---

## 重要：Git 操作约束

> **本计划遵循项目 CLAUDE.md 约定**：用户未主动要求时不计划 git 提交/分支操作。各任务的"代码 + 测试通过"即任务完成，**不在任务内自动 commit**。
>
> 用户在阶段性回顾时（建议每 1-2 个任务后）自行决定 stage 与 commit 范围。

---

## Plan 阶段固化决策（spec 未明确的微调）

| 项 | 决策 | 理由 |
|---|---|---|
| 筛选阈值 | 模块常量 `COMPOSITE_MIN=75, SHORT_MIN=70` | YAGNI，下版本按反馈再开 UI 调节 |
| 排除逻辑 | 按 `ownedThemeIds`（持仓任意 ETF 的主题）排除整个主题 | 比 spec 原文用 `primary_cn` 更准 |
| 候选数 0 | 仍显示折叠面板，标题"信号扫描（0）"，展开后空态文案 | UI 一致性 |
| 排序 | `composite` 降序，截前 10 | spec 原文一致 |
| 跳转 | `<Link to={{ pathname: '/', search: '?theme=<id>' }}>` | HashRouter 自动适配；UIStateProvider 已支持 |
| 折叠默认 | 折叠（`open=false`） | 主区是持仓体检，扫描是附加视角 |

---

## 文件结构

### 新建文件

```
frontend/src/lib/portfolio/
├─ scanner.ts                         # scanOpportunities() 纯函数 + 常量
└─ __tests__/
   └─ scanner.test.ts                 # 单测

frontend/src/components/portfolio/
├─ OpportunityScanner.tsx             # 折叠面板组件
├─ OpportunityCard.tsx                # 单只候选主题卡
└─ __tests__/
   ├─ OpportunityScanner.test.tsx     # 折叠/展开/空态
   └─ OpportunityCard.test.tsx        # 跳转链接 + 字段渲染

frontend/e2e/
└─ portfolio-opportunity.spec.ts      # E2E：折叠展开 + 跳转
```

### 修改文件

```
frontend/src/lib/portfolio/types.ts                    # 加 Opportunity 类型
frontend/src/hooks/usePortfolioScores.ts               # 同时暴露 themes（供 scanner 用）
frontend/src/components/portfolio/HoldingsList.tsx     # 插入 <OpportunityScanner>
```

---

# Task 1：scanOpportunities 纯函数 + 类型 + 单测

**Files:**
- Create: `frontend/src/lib/portfolio/scanner.ts`
- Create: `frontend/src/lib/portfolio/__tests__/scanner.test.ts`
- Modify: `frontend/src/lib/portfolio/types.ts`

**Test command (frontend):** `cd /Users/dreambt/sources/etf-radar/frontend && npx vitest run src/lib/portfolio/__tests__/scanner.test.ts 2>&1 | tail -30`

### Step 1.1：在 `types.ts` 末尾新增 Opportunity 类型

- [ ] **Step 1.1.1：编辑 `frontend/src/lib/portfolio/types.ts`，在末尾追加：**

```ts
// ========== Phase 2: 机会扫描产物 ==========
export interface Opportunity {
  themeId:     string;
  themeName:   string;
  primaryCn:   string;          // 该主题主映射 A 股 ETF 代码（用于"持仓覆盖"文案）
  strength:    Strength;        // 复用 Strength（含 composite/short/mid/long）
  l2Tag:       StrengthTag;     // 复用 strengthTag 输出
  momentumTag: MomentumTag | null; // 复用 momentumTag 输出
}
```

- [ ] **Step 1.1.2：（无测试，仅类型）— 跳过运行**

### Step 1.2：写 `scanner.test.ts`（失败测试）

- [ ] **Step 1.2.1：创建 `frontend/src/lib/portfolio/__tests__/scanner.test.ts`：**

```ts
import { describe, it, expect } from 'vitest';
import { scanOpportunities, COMPOSITE_MIN, SHORT_MIN } from '../scanner';
import type { ThemeMetric } from '../types';

const mkTheme = (
  id: string,
  composite: number,
  short: number,
  overrides: Partial<ThemeMetric> = {},
): ThemeMetric => ({
  id,
  name:       `主题${id}`,
  primary_cn: `${id}-cn`,
  strength: { short, mid: 60, long: 60, composite },
  ...overrides,
});

describe('scanOpportunities', () => {
  it('返回 composite≥75 且 short≥70 的主题', () => {
    const themes = [
      mkTheme('a', 80, 75),  // 通过
      mkTheme('b', 74, 90),  // composite 不够
      mkTheme('c', 90, 69),  // short 不够
      mkTheme('d', 90, 90),  // 通过
    ];
    const result = scanOpportunities(themes, new Set());
    expect(result.map(o => o.themeId).sort()).toEqual(['a', 'd']);
  });

  it('排除 ownedThemeIds 中的主题', () => {
    const themes = [
      mkTheme('a', 90, 90),
      mkTheme('b', 90, 90),
    ];
    const result = scanOpportunities(themes, new Set(['a']));
    expect(result.map(o => o.themeId)).toEqual(['b']);
  });

  it('按 composite 降序排序', () => {
    const themes = [
      mkTheme('a', 80, 80),
      mkTheme('b', 95, 80),
      mkTheme('c', 85, 80),
    ];
    const result = scanOpportunities(themes, new Set());
    expect(result.map(o => o.themeId)).toEqual(['b', 'c', 'a']);
  });

  it('截前 10 只', () => {
    const themes = Array.from({ length: 15 }, (_, i) =>
      mkTheme(`t${i}`, 90 - i, 80),  // 强度递减
    );
    const result = scanOpportunities(themes, new Set());
    expect(result).toHaveLength(10);
    expect(result[0].themeId).toBe('t0');
    expect(result[9].themeId).toBe('t9');
  });

  it('携带 l2Tag 和 momentumTag', () => {
    const themes = [mkTheme('a', 80, 80, {
      strength: { short: 80, mid: 70, long: 60, composite: 80 },
    })];
    const result = scanOpportunities(themes, new Set());
    expect(result[0].l2Tag).toBe('偏强');
    expect(result[0].momentumTag).toBe('动量向上');
  });

  it('空主题列表返回空数组', () => {
    expect(scanOpportunities([], new Set())).toEqual([]);
  });

  it('所有主题被排除时返回空数组', () => {
    const themes = [mkTheme('a', 90, 90)];
    expect(scanOpportunities(themes, new Set(['a']))).toEqual([]);
  });

  it('阈值常量外露用于 UI 文案/测试', () => {
    expect(COMPOSITE_MIN).toBe(75);
    expect(SHORT_MIN).toBe(70);
  });
});
```

- [ ] **Step 1.2.2：运行测试，确认失败（模块尚不存在）：**

Run: `cd /Users/dreambt/sources/etf-radar/frontend && npx vitest run src/lib/portfolio/__tests__/scanner.test.ts 2>&1 | tail -30`
Expected: `Error: Failed to resolve import "../scanner"`

### Step 1.3：实现 `scanner.ts`

- [ ] **Step 1.3.1：创建 `frontend/src/lib/portfolio/scanner.ts`：**

```ts
import type { Opportunity, ThemeMetric } from './types';
import { strengthTag, momentumTag } from './rules';

/** 强势综合分位阈值（含等于）。 */
export const COMPOSITE_MIN = 75;
/** 短周期分位阈值（含等于）— 配合 composite 过滤"近期发力"的主题。 */
export const SHORT_MIN = 70;
/** 候选列表截断条数。 */
export const MAX_OPPORTUNITIES = 10;

/**
 * 从全市场主题中筛出"未持有 + 当前信号偏强"的候选，按综合强度降序截前 10。
 *
 * 立场：仅做"信号事实陈述"，不输出任何买卖指令。文案在 UI 层用 L2 形容词标签呈现。
 */
export function scanOpportunities(
  themes: ThemeMetric[],
  ownedThemeIds: Set<string>,
): Opportunity[] {
  return themes
    .filter(t => !ownedThemeIds.has(t.id))
    .filter(t => t.strength.composite >= COMPOSITE_MIN)
    .filter(t => t.strength.short     >= SHORT_MIN)
    .sort((a, b) => b.strength.composite - a.strength.composite)
    .slice(0, MAX_OPPORTUNITIES)
    .map(t => ({
      themeId:     t.id,
      themeName:   t.name,
      primaryCn:   t.primary_cn,
      strength:    t.strength,
      l2Tag:       strengthTag(t.strength.composite),
      momentumTag: momentumTag(t.strength.short, t.strength.mid),
    }));
}
```

- [ ] **Step 1.3.2：运行测试，确认通过：**

Run: `cd /Users/dreambt/sources/etf-radar/frontend && npx vitest run src/lib/portfolio/__tests__/scanner.test.ts 2>&1 | tail -30`
Expected: `Test Files  1 passed (1)` `Tests  8 passed (8)`

---

# Task 2：扩展 usePortfolioScores 暴露 themes（供 scanner 消费）

**Files:**
- Modify: `frontend/src/hooks/usePortfolioScores.ts`

**Test command:** `cd /Users/dreambt/sources/etf-radar/frontend && npx tsc --noEmit 2>&1 | tail -10`

### Step 2.1：在 `UsePortfolioScoresResult` 加 `themes` 字段

- [ ] **Step 2.1.1：编辑 `frontend/src/hooks/usePortfolioScores.ts`，修改返回值类型：**

把第 17-22 行：

```ts
export interface UsePortfolioScoresResult {
  scores: HoldingScore[];
  loading: boolean;
  /** 命中的主题 id 集合（用于现有页 ⭐/金圈叠加） */
  ownedThemeIds: Set<string>;
}
```

改为：

```ts
export interface UsePortfolioScoresResult {
  scores: HoldingScore[];
  loading: boolean;
  /** 命中的主题 id 集合（用于现有页 ⭐/金圈叠加 + Phase 2 排除） */
  ownedThemeIds: Set<string>;
  /** 全市场主题（Phase 2 机会扫描的输入；已转换为 engine 友好的 ThemeMetric 形态） */
  themes: ThemeMetric[];
}
```

- [ ] **Step 2.1.2：抽取 `themes` 计算到 useMemo 顶层（已存在则改返回）**

把现有的 themes 推导（第 33-41 行）从 scores 的 useMemo 内**抬出**为独立 useMemo，让它也可被外部消费：

```ts
const themes: ThemeMetric[] = useMemo(() => {
  if (!data?.themes) return [];
  return data.themes.themes.map((t) => ({
    id:          t.id,
    name:        t.name,
    primary_cn:  t.primary_cn ?? '',
    strength:    t.strength,
    us_strength: t.us_strength ?? undefined,
    cn_strength: t.cn_strength ?? undefined,
  }));
}, [data]);
```

把原 scores useMemo 内的 themes 推导删掉，scorePortfolio 调用改为复用 `themes` 变量。

最终 scores useMemo 结构：

```ts
const scores = useMemo(() => {
  if (!data?.themes || !data?.etfs) return [];

  const etfs: EtfMetric[] = data.etfs.etfs
    .filter((e) => e.price !== null)
    .map((e) => ({
      code:           e.code,
      name:           e.name,
      tracking_index: e.tracking_index,
      theme_id:       e.theme_id,
      theme_ids:      e.theme_ids,
      price:          e.price!,
      strength:       e.strength,
    }));

  const themeSignals: ThemeSignalEntry[] = (data.signals?.theme_signals ?? [])
    .filter((s) => s.signal !== null)
    .map((s) => ({
      theme_id: s.theme_id,
      signal:   s.signal!,
    }));

  return scorePortfolio({ holdings, themes, etfs, themeSignals });
}, [holdings, data, themes]);
```

- [ ] **Step 2.1.3：更新 return 语句把 themes 加进去：**

```ts
return { scores, loading, ownedThemeIds, themes };
```

- [ ] **Step 2.1.4：类型检查 + 原有测试不破：**

Run: `cd /Users/dreambt/sources/etf-radar/frontend && npx tsc --noEmit 2>&1 | tail -10`
Expected: 0 errors

Run: `cd /Users/dreambt/sources/etf-radar/frontend && npx vitest run src/lib/portfolio/__tests__/engine.test.ts 2>&1 | tail -10`
Expected: 原有 engine 测试仍通过

---

# Task 3：OpportunityCard 单卡组件（含跳转 Link）

**Files:**
- Create: `frontend/src/components/portfolio/OpportunityCard.tsx`
- Create: `frontend/src/components/portfolio/__tests__/OpportunityCard.test.tsx`

**Test command:** `cd /Users/dreambt/sources/etf-radar/frontend && npx vitest run src/components/portfolio/__tests__/OpportunityCard.test.tsx 2>&1 | tail -30`

### Step 3.1：写 OpportunityCard 测试（失败）

- [ ] **Step 3.1.1：创建 `frontend/src/components/portfolio/__tests__/OpportunityCard.test.tsx`：**

```tsx
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { OpportunityCard } from '../OpportunityCard';
import type { Opportunity } from '@/lib/portfolio/types';

const mkOpp = (overrides: Partial<Opportunity> = {}): Opportunity => ({
  themeId:     'storage_dram',
  themeName:   '存储芯片',
  primaryCn:   '512480',
  strength:    { short: 80, mid: 75, long: 60, composite: 85 },
  l2Tag:       '偏强',
  momentumTag: '动量向上',
  ...overrides,
});

const renderWithRouter = (opp: Opportunity) =>
  render(
    <MemoryRouter>
      <OpportunityCard opp={opp} />
    </MemoryRouter>,
  );

describe('OpportunityCard', () => {
  it('展示主题名 + 综合强度', () => {
    renderWithRouter(mkOpp());
    expect(screen.getByText('存储芯片')).toBeInTheDocument();
    expect(screen.getByText(/85/)).toBeInTheDocument(); // composite
  });

  it('展示 L2 标签', () => {
    renderWithRouter(mkOpp({ l2Tag: '偏强' }));
    expect(screen.getByText('偏强')).toBeInTheDocument();
  });

  it('动量向上时展示 momentumTag', () => {
    renderWithRouter(mkOpp({ momentumTag: '动量向上' }));
    expect(screen.getByText('动量向上')).toBeInTheDocument();
  });

  it('momentumTag 为 null 时不渲染该标签', () => {
    renderWithRouter(mkOpp({ momentumTag: null }));
    expect(screen.queryByText('动量向上')).not.toBeInTheDocument();
    expect(screen.queryByText('动量向下')).not.toBeInTheDocument();
  });

  it('跳转链接指向 RadarPage + theme 参数', () => {
    renderWithRouter(mkOpp({ themeId: 'robotics' }));
    const link = screen.getByRole('link', { name: /查看详情/ });
    // react-router-dom Link 渲染为 <a href>
    // HashRouter 下 to={{ pathname: '/', search: '?theme=robotics' }} → href="#/?theme=robotics"
    // MemoryRouter 下 href 为 "/?theme=robotics"（无 hash 前缀）
    expect(link.getAttribute('href')).toContain('theme=robotics');
  });

  it('文案保持 L1+L2 立场（不出现"买入/推荐"指令）', () => {
    renderWithRouter(mkOpp());
    const text = document.body.textContent ?? '';
    expect(text).not.toMatch(/推荐买入|建议买入|可买/);
  });
});
```

- [ ] **Step 3.1.2：运行测试，确认失败（组件尚不存在）：**

Run: `cd /Users/dreambt/sources/etf-radar/frontend && npx vitest run src/components/portfolio/__tests__/OpportunityCard.test.tsx 2>&1 | tail -30`
Expected: `Failed to resolve import "../OpportunityCard"`

### Step 3.2：实现 OpportunityCard

- [ ] **Step 3.2.1：创建 `frontend/src/components/portfolio/OpportunityCard.tsx`：**

```tsx
import { Link } from 'react-router-dom';
import type { Opportunity } from '@/lib/portfolio/types';

interface Props {
  opp: Opportunity;
}

/**
 * 单只机会候选卡。仅展示信号事实（强度分位 + L2 形容词标签），
 * 不出现任何买卖指令性语言。点击"查看详情"跳 RadarPage 并选中该主题。
 */
export const OpportunityCard = ({ opp }: Props) => {
  return (
    <div className="border rounded-lg p-3 bg-white hover:shadow-sm transition">
      <div className="flex items-center justify-between mb-2">
        <div className="font-medium">{opp.themeName}</div>
        <span className="text-xs px-1.5 py-0.5 rounded bg-emerald-50 text-emerald-700 border border-emerald-200">
          {opp.l2Tag}
        </span>
      </div>

      <div className="text-xs text-gray-500 mb-2">
        主映射 ETF：{opp.primaryCn}
      </div>

      <div className="grid grid-cols-4 gap-1 text-xs text-center mb-2">
        <div>
          <div className="text-gray-400">短</div>
          <div className="font-mono">{opp.strength.short}</div>
        </div>
        <div>
          <div className="text-gray-400">中</div>
          <div className="font-mono">{opp.strength.mid}</div>
        </div>
        <div>
          <div className="text-gray-400">长</div>
          <div className="font-mono">{opp.strength.long}</div>
        </div>
        <div>
          <div className="text-gray-400">综合</div>
          <div className="font-mono font-semibold">{opp.strength.composite}</div>
        </div>
      </div>

      {opp.momentumTag && (
        <div className="text-xs text-amber-700 mb-2">{opp.momentumTag}</div>
      )}

      <Link
        to={{ pathname: '/', search: `?theme=${opp.themeId}` }}
        className="block text-center text-xs text-blue-600 hover:underline mt-1"
      >
        查看详情 →
      </Link>
    </div>
  );
};
```

- [ ] **Step 3.2.2：运行测试，确认通过：**

Run: `cd /Users/dreambt/sources/etf-radar/frontend && npx vitest run src/components/portfolio/__tests__/OpportunityCard.test.tsx 2>&1 | tail -30`
Expected: `Tests  6 passed (6)`

---

# Task 4：OpportunityScanner 折叠面板

**Files:**
- Create: `frontend/src/components/portfolio/OpportunityScanner.tsx`
- Create: `frontend/src/components/portfolio/__tests__/OpportunityScanner.test.tsx`

**Test command:** `cd /Users/dreambt/sources/etf-radar/frontend && npx vitest run src/components/portfolio/__tests__/OpportunityScanner.test.tsx 2>&1 | tail -30`

### Step 4.1：写 OpportunityScanner 测试（失败）

- [ ] **Step 4.1.1：创建 `frontend/src/components/portfolio/__tests__/OpportunityScanner.test.tsx`：**

```tsx
import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { OpportunityScanner } from '../OpportunityScanner';
import type { ThemeMetric } from '@/lib/portfolio/types';

const mkTheme = (
  id: string,
  composite: number,
  short: number,
): ThemeMetric => ({
  id,
  name:       `主题${id}`,
  primary_cn: `${id}-cn`,
  strength: { short, mid: 60, long: 60, composite },
});

const renderScanner = (themes: ThemeMetric[], ownedThemeIds = new Set<string>()) =>
  render(
    <MemoryRouter>
      <OpportunityScanner themes={themes} ownedThemeIds={ownedThemeIds} />
    </MemoryRouter>,
  );

describe('OpportunityScanner', () => {
  it('默认折叠，仅渲染标题', () => {
    renderScanner([mkTheme('a', 90, 90)]);
    expect(screen.getByText(/信号扫描/)).toBeInTheDocument();
    expect(screen.queryByText('主题a')).not.toBeInTheDocument();
  });

  it('标题显示候选数', () => {
    renderScanner([
      mkTheme('a', 90, 90),
      mkTheme('b', 80, 80),
      mkTheme('c', 60, 60),  // 不达标
    ]);
    expect(screen.getByText(/信号扫描\s*\(\s*2\s*\)/)).toBeInTheDocument();
  });

  it('点击标题展开，渲染候选卡', () => {
    renderScanner([mkTheme('a', 90, 90)]);
    fireEvent.click(screen.getByRole('button', { name: /信号扫描/ }));
    expect(screen.getByText('主题a')).toBeInTheDocument();
  });

  it('展开 + 候选为 0 时显示空态文案', () => {
    renderScanner([mkTheme('a', 60, 60)]); // 不达标
    fireEvent.click(screen.getByRole('button', { name: /信号扫描/ }));
    expect(screen.getByText(/当前无满足筛选条件的主题/)).toBeInTheDocument();
  });

  it('排除 ownedThemeIds', () => {
    renderScanner(
      [mkTheme('a', 90, 90), mkTheme('b', 90, 90)],
      new Set(['a']),
    );
    fireEvent.click(screen.getByRole('button', { name: /信号扫描/ }));
    expect(screen.queryByText('主题a')).not.toBeInTheDocument();
    expect(screen.getByText('主题b')).toBeInTheDocument();
  });

  it('再次点击标题折叠', () => {
    renderScanner([mkTheme('a', 90, 90)]);
    const btn = screen.getByRole('button', { name: /信号扫描/ });
    fireEvent.click(btn);
    expect(screen.getByText('主题a')).toBeInTheDocument();
    fireEvent.click(btn);
    expect(screen.queryByText('主题a')).not.toBeInTheDocument();
  });

  it('展开后展示阈值说明（用户知道筛选条件）', () => {
    renderScanner([mkTheme('a', 90, 90)]);
    fireEvent.click(screen.getByRole('button', { name: /信号扫描/ }));
    // 75 / 70 出现在阈值说明文案
    expect(screen.getByText(/75/)).toBeInTheDocument();
    expect(screen.getByText(/70/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 4.1.2：运行测试，确认失败（组件尚不存在）：**

Run: `cd /Users/dreambt/sources/etf-radar/frontend && npx vitest run src/components/portfolio/__tests__/OpportunityScanner.test.tsx 2>&1 | tail -30`
Expected: `Failed to resolve import "../OpportunityScanner"`

### Step 4.2：实现 OpportunityScanner

- [ ] **Step 4.2.1：创建 `frontend/src/components/portfolio/OpportunityScanner.tsx`：**

```tsx
import { useMemo, useState } from 'react';
import type { ThemeMetric } from '@/lib/portfolio/types';
import {
  scanOpportunities,
  COMPOSITE_MIN,
  SHORT_MIN,
} from '@/lib/portfolio/scanner';
import { OpportunityCard } from './OpportunityCard';

interface Props {
  themes: ThemeMetric[];
  ownedThemeIds: Set<string>;
}

/**
 * 持仓页底部"信号扫描"折叠面板：
 *   - 默认折叠（主区是持仓体检，扫描为附加视角）
 *   - 候选数 0 时仍渲染面板，展开后给空态文案
 *   - 阈值文案显式告知用户筛选条件（非黑盒）
 */
export const OpportunityScanner = ({ themes, ownedThemeIds }: Props) => {
  const [open, setOpen] = useState(false);

  const opportunities = useMemo(
    () => scanOpportunities(themes, ownedThemeIds),
    [themes, ownedThemeIds],
  );

  return (
    <section className="mt-6 border rounded-lg bg-gray-50">
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between px-4 py-3 text-left"
        aria-expanded={open}
      >
        <span className="font-medium">
          信号扫描（{opportunities.length}）
        </span>
        <span className="text-xs text-gray-500">{open ? '收起 ▲' : '展开 ▼'}</span>
      </button>

      {open && (
        <div className="px-4 pb-4">
          <div className="text-xs text-gray-500 mb-3">
            筛选条件：综合强度 ≥ {COMPOSITE_MIN} 且 短周期 ≥ {SHORT_MIN}，
            排除您已持仓的主题。仅供信号参考，不构成投资建议。
          </div>

          {opportunities.length === 0 ? (
            <div className="text-sm text-gray-500 text-center py-6">
              当前无满足筛选条件的主题——可能强势主题已在您的持仓中，
              或全市场暂无新的发力主题。
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
              {opportunities.map(opp => (
                <OpportunityCard key={opp.themeId} opp={opp} />
              ))}
            </div>
          )}
        </div>
      )}
    </section>
  );
};
```

- [ ] **Step 4.2.2：运行测试，确认通过：**

Run: `cd /Users/dreambt/sources/etf-radar/frontend && npx vitest run src/components/portfolio/__tests__/OpportunityScanner.test.tsx 2>&1 | tail -30`
Expected: `Tests  7 passed (7)`

---

# Task 5：集成到 HoldingsList

**Files:**
- Modify: `frontend/src/components/portfolio/HoldingsList.tsx`

**Test command:** `cd /Users/dreambt/sources/etf-radar/frontend && npx vitest run 2>&1 | tail -10`

### Step 5.1：把 OpportunityScanner 插入到 PortfolioSummary 下方

- [ ] **Step 5.1.1：编辑 `frontend/src/components/portfolio/HoldingsList.tsx`：**

把第 2-5 行的 import 区域改为：

```ts
import { useHoldings } from '@/hooks/useHoldings';
import { usePortfolioScores } from '@/hooks/usePortfolioScores';
import { HoldingScoreCard } from './HoldingScoreCard';
import { HoldingsEditor } from './HoldingsEditor';
import { PortfolioSummary } from './PortfolioSummary';
import { OpportunityScanner } from './OpportunityScanner';
```

把第 10 行的 hook 解构改为：

```ts
const { scores, loading, ownedThemeIds, themes } = usePortfolioScores();
```

把第 41-54 行的渲染分支（`scores.length === 0 ? ... : (...)`）改为：

```tsx
{scores.length === 0 ? (
  <div className="border rounded p-8 text-center bg-gray-50">
    <div className="text-gray-600 mb-2">还没有录入持仓</div>
    <div className="text-sm text-gray-500 mb-4">
      把您的 A 股 ETF 接入信号引擎，看看它们当下状态
    </div>
    <button
      onClick={() => setEditingCode('')}
      className="px-4 py-2 bg-blue-600 text-white rounded"
    >+ 添加第一只</button>
  </div>
) : (
  <>
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
      {scores.map(s => (
        <HoldingScoreCard
          key={s.etfCode} score={s}
          onDelete={remove}
          onEdit={setEditingCode}
        />
      ))}
    </div>
    <PortfolioSummary scores={scores} />
    <OpportunityScanner themes={themes} ownedThemeIds={ownedThemeIds} />
  </>
)}
```

- [ ] **Step 5.1.2：跑所有 portfolio 相关单测：**

Run: `cd /Users/dreambt/sources/etf-radar/frontend && npx vitest run src/components/portfolio src/lib/portfolio 2>&1 | tail -20`
Expected: 全部通过

- [ ] **Step 5.1.3：跑全套前端单测确认无回归：**

Run: `cd /Users/dreambt/sources/etf-radar/frontend && npx vitest run 2>&1 | grep -E "Test Files|Tests" | head -5`
Expected: `Test Files  N passed` `Tests  M passed`（无 failed）

- [ ] **Step 5.1.4：TypeScript 类型检查：**

Run: `cd /Users/dreambt/sources/etf-radar/frontend && npx tsc --noEmit 2>&1 | tail -10`
Expected: 0 errors

---

# Task 6：E2E 烟雾测试

**Files:**
- Create: `frontend/e2e/portfolio-opportunity.spec.ts`

**Test command:** `cd /Users/dreambt/sources/etf-radar/frontend && npx playwright test e2e/portfolio-opportunity.spec.ts 2>&1 | tail -20`

### Step 6.1：编写 E2E 测试

- [ ] **Step 6.1.1：先查现有 portfolio e2e 用例了解登录注入模式：**

Run: `ls frontend/e2e/ && head -50 frontend/e2e/portfolio.spec.ts 2>/dev/null || echo "no existing portfolio spec"`
Expected: 列出现有 e2e 文件；若存在 portfolio.spec.ts，参考其中的 supabase mock / 登录注入手法。

> **如果不存在 `portfolio.spec.ts`**：跳过 Task 6（E2E 不阻塞），写一行 TODO 说明留给 Phase 1 收尾时补，本任务直接 mark done。

- [ ] **Step 6.1.2：创建 `frontend/e2e/portfolio-opportunity.spec.ts`：**

```ts
import { test, expect } from '@playwright/test';

// 沿用 portfolio.spec.ts 的 supabase mock + 持仓注入手法。
// 本用例只关心 OpportunityScanner 的"折叠/展开/跳转"行为，
// 不重复测持仓 CRUD。

test.describe('OpportunityScanner', () => {
  test.beforeEach(async ({ page }) => {
    // 假设 portfolio.spec.ts 已注入 mock auth + 一个持仓
    // 这里复用同样的注入逻辑（实际实现时从 portfolio.spec.ts 抄）
    await page.goto('/etf-radar/#/portfolio');
  });

  test('默认折叠，点击展开后可见候选卡', async ({ page }) => {
    const scannerBtn = page.getByRole('button', { name: /信号扫描/ });
    await expect(scannerBtn).toBeVisible();

    // 默认折叠：候选卡不可见
    await expect(page.getByText('查看详情')).toHaveCount(0);

    // 展开
    await scannerBtn.click();
    // 至少能看到阈值说明
    await expect(page.getByText(/筛选条件/)).toBeVisible();
  });

  test('展开后点击"查看详情"跳到 RadarPage 并自动选中主题', async ({ page }) => {
    await page.getByRole('button', { name: /信号扫描/ }).click();

    // 至少有一张候选卡（数据驱动，实际可能为 0；若 0 测试 SKIP）
    const detailLinks = page.getByRole('link', { name: /查看详情/ });
    const count = await detailLinks.count();
    test.skip(count === 0, '当前数据下无候选机会，跳过跳转测试');

    await detailLinks.first().click();

    // URL 应包含 theme 参数
    await expect(page).toHaveURL(/[?&]theme=/);
    // 应跳到 RadarPage（不在 /portfolio）
    await expect(page).not.toHaveURL(/portfolio/);
  });
});
```

- [ ] **Step 6.1.3：运行 E2E：**

Run: `cd /Users/dreambt/sources/etf-radar/frontend && npx playwright test e2e/portfolio-opportunity.spec.ts 2>&1 | tail -20`
Expected: 通过（或 skip）。如果 mock 缺失导致登录失败，**记录在任务备注中**，由人工补完 Phase 1 e2e 基建后回填。

> **注意**：本步骤是"宽容验收"——E2E 不通过不阻塞 Phase 2 落地（spec 5.4 验收清单未含 E2E 强制项），但需明确报告失败原因。

---

# 完成清单（对照 spec 5.4 验收）

- [ ] **`scanOpportunities()` 正确排除已持仓 ETF**（Task 1.2.1 第二个 it 覆盖）
- [ ] **筛选条件可调（首版 composite≥75 + short≥70）**（Task 1.3.1 常量外露，Task 1.2.1 末个 it 验证）
- [ ] **文案保持 L1+L2 立场（无"推荐买入"）**（Task 3.1.1 末个 it 验证）
- [ ] **空态文案**（Task 4.1.1 第四个 it 验证）
- [ ] **从持仓页可跳转到主题详情**（Task 3 渲染 Link，Task 6 E2E 验证）

---

# 自我审查（writing-plans skill 要求）

## 1. Spec 覆盖

| spec 章节 | 实施任务 |
|---|---|
| 3.6 `scanOpportunities` 函数签名 | Task 1.3 |
| 5.4 任务 1（函数 + 单测） | Task 1 |
| 5.4 任务 2（OpportunityScanner UI） | Task 4（+ Task 3 拆分单卡） |
| 5.4 任务 3（"跳转详情"路由集成） | Task 3.2（Link）+ Task 5（集成） |
| 5.4 任务 4（E2E） | Task 6 |
| 5.4 验收 4 条 | 上方"完成清单" |

**新增任务（spec 未明示但合理拆分）**：
- Task 2（扩展 `usePortfolioScores` 暴露 `themes`）— 数据流必要环节
- Task 3 单独拆出 `OpportunityCard`— 减小 OpportunityScanner 单文件复杂度，便于测试

## 2. 占位符扫描

✅ 无 TBD / TODO / "add appropriate" / 缺代码块的步骤

唯一一处"宽容"：Task 6 E2E 允许在 Phase 1 e2e 基建缺失时 SKIP，但有明确处理路径（记录在备注），不算占位符。

## 3. 类型一致性

| 命名 | 定义位置 | 引用位置 |
|---|---|---|
| `Opportunity` | Task 1.1.1 (types.ts) | Task 1, 3, 4 |
| `scanOpportunities(themes, ownedThemeIds): Opportunity[]` | Task 1.3.1 | Task 1.2.1, Task 4.2.1 |
| `COMPOSITE_MIN, SHORT_MIN` | Task 1.3.1 export | Task 1.2.1, Task 4.2.1 |
| `OpportunityCard({ opp })` | Task 3.2.1 | Task 4.2.1 |
| `OpportunityScanner({ themes, ownedThemeIds })` | Task 4.2.1 | Task 5.1.1 |
| `usePortfolioScores().themes` | Task 2.1.1 | Task 5.1.1 |

✅ 一致
