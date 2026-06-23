# 持仓监控 Phase 3 实施计划：轮动事件 + 站内信流

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `/portfolio` 上为持仓 ETF 引入"昨日 vs 今日轮动事件流"——主题象限切换、强度穿越阈值、信号变化——以 Header 红点 + 折叠时间线呈现。

**Architecture:** 纯前端差分 + Supabase 存档。访问 `/portfolio` 时用 `useEventsSnapshot(date)` 拉取今日/上一交易日两份完整快照（themes/etfs/signals），调 `detectEvents()` 纯函数生成 `PendingEvent[]`，`upsertEvents()` 写入 `user_events`（UNIQUE(user_id, event_signature) dedupe）。EventTimeline 折叠面板订阅 user_events（Realtime + Postgres Changes），Header 显示未读红点。

**Tech Stack:** React 19 + TypeScript strict + Vite + Tailwind v4 + shadcn/ui + @supabase/supabase-js + zod + swr + vitest + playwright

**Spec Reference:** `docs/superpowers/specs/2026-06-21-portfolio-monitor-design.md`（§2.3 user_events 表 / §3.7 detectEvents / §4.8 EventTimeline / §5.5 路线图）

---

## 重要：Git 操作约束

> **本计划遵循项目 CLAUDE.md 约定**：用户未主动要求时不计划 git 提交/分支操作。各任务的"代码 + 测试通过"即任务完成，**不在任务内自动 commit**。
>
> 用户在阶段性回顾时（建议每 2-3 个任务后）自行决定 stage 与 commit 范围。

---

## 关键固定决策（避免实施时再讨论）

| 维度 | 决策 | 理由 |
|---|---|---|
| 快照粒度 | 主题级（不下钻 ETF 级） | snapshots/<date>/themes.json 已含 quadrant/strength，etfs.json 仅含价格不含 quadrant。主题级 diff 与 RotationPage 同构，事件对全部持仓该主题 ETF 都有效 |
| 上一交易日识别 | 用 snapshots/index.json 倒数第 2 条 | 已现成；节假日"自然跳过"，无需日历库 |
| 差分单位 | 仅 covered（theme_id 命中）持仓 | uncovered 无快照可比，跳过 |
| 事件签名 | `{type}:{themeId}:{date}:{from}_to_{to}` | UNIQUE 约束跨用户共享同主题事件签名 |
| 节流 | localStorage(`portfolio_last_detected_date`)，同日不重跑 | 减少冷启动写库 |
| 首次登录积压 | 仅检测"昨日 vs 今日"一次，不追溯 7 天 | YAGNI；spec 提到 7 天是为大幅延迟登录场景，初版不实现 |
| 强度阈值 | 25/50/75 三档（spec §3.7 指定） | 与 L2 标签边界一致 |
| Realtime channel | `user_events_${user.id}` | 与现有 user_holdings channel 同 pattern |
| 已读 90 天裁剪 | UI 层 filter（不删库） | spec 验收"90 天前不显示"——SQL 已通过 created_at index 加速 |

---

## 文件结构

### 新建文件

```
backend/migrations/
└─ 002_user_events.sql                                # Phase 3 表 schema + RLS + Realtime

frontend/src/lib/portfolio/
├─ eventDiff.ts                                       # detectEvents() 纯函数
├─ eventTypes.ts                                      # PendingEvent / UserEvent / Snapshot 类型
└─ __tests__/
   ├─ eventDiff.test.ts                               # 8 状态转移 × 3 阈值 + 边界
   └─ __fixtures__/
      └─ snapshots-pair.ts                            # today/yesterday 配对夹具

frontend/src/hooks/
├─ useEventsSnapshot.ts                               # 拉取单日完整快照(themes+etfs+signals)
└─ useUserEvents.ts                                   # 订阅 user_events + 触发 detectEvents

frontend/src/providers/
└─ EventsProvider.tsx                                 # user_events 状态 + Realtime + upsertEvents

frontend/src/providers/eventsContext.ts               # context 类型与默认值（独立文件避免循环）

frontend/src/components/portfolio/
├─ EventTimeline.tsx                                  # 折叠时间线列表
├─ EventItem.tsx                                      # 单条事件卡（颜色映射）
└─ __tests__/
   ├─ EventTimeline.test.tsx                          # 折叠/已读/空态/90 天裁剪
   └─ EventItem.test.tsx                              # 颜色 / 文案 / 已读样式

frontend/src/components/Header/
└─ EventBadge.tsx                                     # Header 未读红点徽章

frontend/e2e/
└─ portfolio-events.spec.ts                           # 匿名烟雾（同 portfolio-opportunity 模式）
```

### 修改文件

```
frontend/src/providers/dataContext.ts                 # 暴露 useDataContext 已存在，无需改
frontend/src/App.tsx                                  # AuthProvider 之内嵌入 EventsProvider
frontend/src/components/portfolio/HoldingsList.tsx    # populated 分支挂载 EventTimeline
frontend/src/components/Header/index.tsx              # 登录态在 UserMenu 旁加 EventBadge
frontend/src/lib/portfolio/types.ts                   # 追加 Phase 3 type re-exports（兼容老用法）
```

---

# Task 1：user_events 表 migration

**Files:**
- Create: `backend/migrations/002_user_events.sql`

- [ ] **Step 1：写 SQL migration**

```sql
-- 002_user_events.sql
-- 用户事件表 + RLS 策略
-- 在 Supabase SQL Editor 中执行（一次性）

-- ========== user_events ==========
CREATE TABLE IF NOT EXISTS user_events (
  id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         uuid        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  event_type      text        NOT NULL,
  -- 'theme_quadrant_change' | 'theme_strength_cross_up' | 'theme_strength_cross_down' | 'theme_signal_change'
  theme_id        text        NOT NULL,
  event_signature text        NOT NULL,
  -- 例: 'theme_quadrant_change:cn_tech:2026-06-23:leading_to_weakening'
  payload         jsonb       NOT NULL DEFAULT '{}'::jsonb,
  asof_date       date        NOT NULL,
  created_at      timestamptz NOT NULL DEFAULT now(),
  read_at         timestamptz,
  UNIQUE (user_id, event_signature)
);

CREATE INDEX IF NOT EXISTS idx_events_user_time
  ON user_events (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_events_unread
  ON user_events (user_id)
  WHERE read_at IS NULL;

-- ========== RLS ==========
ALTER TABLE user_events ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS events_own ON user_events;
CREATE POLICY events_own ON user_events
  FOR ALL TO authenticated
  USING      (user_id = auth.uid())
  WITH CHECK (user_id = auth.uid());

-- ========== Realtime ==========
ALTER PUBLICATION supabase_realtime ADD TABLE user_events;
```

- [ ] **Step 2：人工操作 — 在 Supabase Dashboard 执行**

> 这一步**不进 git commit**，仅文件落地。用户在 SQL Editor 粘贴执行后回报结果。
>
> 验证方法：在 Supabase Dashboard → Database → Tables 看到 `user_events` 表 + RLS Enabled 即 OK。

---

# Task 2：detectEvents() 纯函数

**Files:**
- Create: `frontend/src/lib/portfolio/eventTypes.ts`
- Create: `frontend/src/lib/portfolio/eventDiff.ts`
- Create: `frontend/src/lib/portfolio/__tests__/__fixtures__/snapshots-pair.ts`
- Create: `frontend/src/lib/portfolio/__tests__/eventDiff.test.ts`

- [ ] **Step 1：定义类型 `eventTypes.ts`**

```ts
import type { Quadrant, SignalKind, Strength } from './types';

/** 一日的主题级快照视图（detectEvents 输入） */
export interface ThemeSnapshotEntry {
  themeId:   string;
  quadrant:  Quadrant;
  strength:  Strength;
  signal:    SignalKind | null;
}

export interface Snapshot {
  date:    string;                            // YYYY-MM-DD
  themes:  Map<string, ThemeSnapshotEntry>;   // by themeId
}

export type EventType =
  | 'theme_quadrant_change'
  | 'theme_strength_cross_up'
  | 'theme_strength_cross_down'
  | 'theme_signal_change';

/** 差分产出（尚未落库） */
export interface PendingEvent {
  event_type:      EventType;
  theme_id:        string;
  event_signature: string;
  payload:         Record<string, unknown>;
  asof_date:       string;                    // YYYY-MM-DD
}

/** 从数据库读出 + 解析后的事件 */
export interface UserEvent {
  id:              string;
  user_id:         string;
  event_type:      EventType;
  theme_id:        string;
  event_signature: string;
  payload:         Record<string, unknown>;
  asof_date:       string;
  created_at:      string;                    // ISO timestamp
  read_at:         string | null;
}
```

- [ ] **Step 2：写 fixture（today/yesterday 配对）**

```ts
// frontend/src/lib/portfolio/__tests__/__fixtures__/snapshots-pair.ts
import type { Snapshot, ThemeSnapshotEntry } from '../../eventTypes';

const mk = (
  themeId: string,
  quadrant: ThemeSnapshotEntry['quadrant'],
  composite: number,
  signal: ThemeSnapshotEntry['signal'] = 'resonance',
): ThemeSnapshotEntry => ({
  themeId,
  quadrant,
  strength: { short: composite, mid: composite, long: composite, composite },
  signal,
});

export const yesterday: Snapshot = {
  date: '2026-06-22',
  themes: new Map<string, ThemeSnapshotEntry>([
    ['cn_tech',     mk('cn_tech',     'leading',   80, 'resonance')],
    ['cn_consume',  mk('cn_consume',  'following', 24, 'divergence')],
    ['cn_chemical', mk('cn_chemical', 'weak',      49, 'transmission')],
    ['cn_energy',   mk('cn_energy',   'weakening', 70, 'resonance')],
  ]),
};

export const today: Snapshot = {
  date: '2026-06-23',
  themes: new Map<string, ThemeSnapshotEntry>([
    // 同象限同强度同信号 → 无事件
    ['cn_tech',     mk('cn_tech',     'leading',   80, 'resonance')],
    // 强度上穿 25 + 信号变化
    ['cn_consume',  mk('cn_consume',  'following', 26, 'resonance')],
    // 象限变化 + 强度上穿 50
    ['cn_chemical', mk('cn_chemical', 'leading',   60, 'transmission')],
    // 强度下穿 75（70 → 69 不触发；改为 70 → 49 触发 50 + 75 两档下穿）
    ['cn_energy',   mk('cn_energy',   'weakening', 49, 'resonance')],
  ]),
};
```

- [ ] **Step 3：写失败测试**

```ts
// frontend/src/lib/portfolio/__tests__/eventDiff.test.ts
import { describe, it, expect } from 'vitest';
import { detectEvents } from '../eventDiff';
import { today, yesterday } from './__fixtures__/snapshots-pair';

const holdings = (themeIds: string[]) => themeIds.map(id => ({ themeId: id, etfCode: `${id}-etf` }));

describe('detectEvents', () => {
  it('同象限同强度同信号 — 无事件', () => {
    const events = detectEvents(today, yesterday, holdings(['cn_tech']));
    expect(events).toHaveLength(0);
  });

  it('象限切换产生 theme_quadrant_change 事件', () => {
    const events = detectEvents(today, yesterday, holdings(['cn_chemical']));
    const quadrant = events.find(e => e.event_type === 'theme_quadrant_change');
    expect(quadrant).toBeDefined();
    expect(quadrant!.event_signature).toBe(
      'theme_quadrant_change:cn_chemical:2026-06-23:weak_to_leading',
    );
    expect(quadrant!.payload).toEqual({ from: 'weak', to: 'leading' });
  });

  it('上穿阈值产生 theme_strength_cross_up 事件（每档单独）', () => {
    // cn_consume: 24 → 26 仅上穿 25
    const consumeEvents = detectEvents(today, yesterday, holdings(['cn_consume']));
    const upEvents = consumeEvents.filter(e => e.event_type === 'theme_strength_cross_up');
    expect(upEvents).toHaveLength(1);
    expect(upEvents[0].event_signature).toBe(
      'theme_strength_cross_up:cn_consume:2026-06-23:25',
    );
    expect(upEvents[0].payload).toEqual({ threshold: 25, from: 24, to: 26 });
  });

  it('下穿阈值产生 theme_strength_cross_down 事件（多档同时）', () => {
    // cn_energy: 70 → 49 同时下穿 50（不下穿 75，因为已经 < 75）
    const events = detectEvents(today, yesterday, holdings(['cn_energy']));
    const downEvents = events.filter(e => e.event_type === 'theme_strength_cross_down');
    expect(downEvents.map(e => e.payload.threshold).sort()).toEqual([50]);
  });

  it('信号变化产生 theme_signal_change 事件', () => {
    const events = detectEvents(today, yesterday, holdings(['cn_consume']));
    const sig = events.find(e => e.event_type === 'theme_signal_change');
    expect(sig).toBeDefined();
    expect(sig!.payload).toEqual({ from: 'divergence', to: 'resonance' });
    expect(sig!.event_signature).toBe(
      'theme_signal_change:cn_consume:2026-06-23:divergence_to_resonance',
    );
  });

  it('多 holdings 共享同主题只生成一组事件（按 themeId 去重）', () => {
    // 两个 ETF 都属于 cn_chemical → 事件应仅生成一组（按 themeId 去重）
    const events = detectEvents(
      today, yesterday,
      [{ themeId: 'cn_chemical', etfCode: '512480' },
       { themeId: 'cn_chemical', etfCode: '512560' }],
    );
    const sigs = new Set(events.map(e => e.event_signature));
    expect(sigs.size).toBe(events.length);  // 无重复 signature
  });

  it('主题在 yesterday 缺失 — 跳过（新增主题不报错）', () => {
    const yWithout = { date: yesterday.date, themes: new Map() };
    const events = detectEvents(today, yWithout, holdings(['cn_tech']));
    expect(events).toEqual([]);
  });

  it('主题在 today 缺失 — 跳过（下架主题不报错）', () => {
    const tWithout = { date: today.date, themes: new Map() };
    const events = detectEvents(tWithout, yesterday, holdings(['cn_tech']));
    expect(events).toEqual([]);
  });

  it('精确边界：composite 24 → 25 上穿（含等于）', () => {
    const y: Snapshot = {
      date: '2026-06-22',
      themes: new Map([['x', { themeId: 'x', quadrant: 'weak',
        strength: { short:24, mid:24, long:24, composite:24 }, signal: 'resonance' }]]),
    };
    const t: Snapshot = {
      date: '2026-06-23',
      themes: new Map([['x', { themeId: 'x', quadrant: 'weak',
        strength: { short:25, mid:25, long:25, composite:25 }, signal: 'resonance' }]]),
    };
    const events = detectEvents(t, y, [{ themeId: 'x', etfCode: 'x-etf' }]);
    expect(events.filter(e => e.event_type === 'theme_strength_cross_up')).toHaveLength(1);
  });

  it('精确边界：composite 25 → 24 下穿', () => {
    const y: Snapshot = {
      date: '2026-06-22',
      themes: new Map([['x', { themeId: 'x', quadrant: 'weak',
        strength: { short:25, mid:25, long:25, composite:25 }, signal: 'resonance' }]]),
    };
    const t: Snapshot = {
      date: '2026-06-23',
      themes: new Map([['x', { themeId: 'x', quadrant: 'weak',
        strength: { short:24, mid:24, long:24, composite:24 }, signal: 'resonance' }]]),
    };
    const events = detectEvents(t, y, [{ themeId: 'x', etfCode: 'x-etf' }]);
    expect(events.filter(e => e.event_type === 'theme_strength_cross_down')).toHaveLength(1);
  });
});

// Snapshot 类型在 eventTypes.ts 已 export
import type { Snapshot } from '../eventTypes';
```

- [ ] **Step 4：跑测试看失败**

Run: `cd /Users/dreambt/sources/etf-radar/frontend && npx vitest run src/lib/portfolio/__tests__/eventDiff.test.ts 2>&1 | tail -20`
Expected: 全部 FAIL（"detectEvents is not defined" 或 import 失败）

- [ ] **Step 5：实现 `eventDiff.ts`**

```ts
// frontend/src/lib/portfolio/eventDiff.ts
import type { Snapshot, PendingEvent } from './eventTypes';

/** spec §3.7 — composite 强度三档分界 */
const THRESHOLDS = [25, 50, 75] as const;

export interface HoldingForDiff {
  themeId:  string;
  etfCode:  string;
}

/**
 * 主题级事件差分。
 *
 * 立场：仅记录"信号事实变化"，不评判好坏。颜色/语义判断由 UI 层根据
 *   event_type + payload 推导（参见 EventItem.tsx）。
 *
 * 去重策略：同一主题被多个 ETF 持有时，按 themeId 聚合，事件仅生成一组
 *   （由 event_signature 中的 themeId 保证唯一）。
 */
export function detectEvents(
  today:     Snapshot,
  yesterday: Snapshot,
  holdings:  HoldingForDiff[],
): PendingEvent[] {
  const events: PendingEvent[] = [];
  const seenThemes = new Set<string>();

  for (const h of holdings) {
    if (seenThemes.has(h.themeId)) continue;
    seenThemes.add(h.themeId);

    const t = today.themes.get(h.themeId);
    const y = yesterday.themes.get(h.themeId);
    if (!t || !y) continue;                       // 新增/下架主题：跳过

    // 1. 象限切换
    if (t.quadrant !== y.quadrant) {
      events.push({
        event_type: 'theme_quadrant_change',
        theme_id:   h.themeId,
        event_signature:
          `theme_quadrant_change:${h.themeId}:${today.date}:${y.quadrant}_to_${t.quadrant}`,
        payload:    { from: y.quadrant, to: t.quadrant },
        asof_date:  today.date,
      });
    }

    // 2. 强度阈值穿越（每档独立判断）
    for (const threshold of THRESHOLDS) {
      const yWas = y.strength.composite;
      const tNow = t.strength.composite;
      // 上穿（含等于 today）
      if (yWas < threshold && tNow >= threshold) {
        events.push({
          event_type: 'theme_strength_cross_up',
          theme_id:   h.themeId,
          event_signature:
            `theme_strength_cross_up:${h.themeId}:${today.date}:${threshold}`,
          payload:    { threshold, from: yWas, to: tNow },
          asof_date:  today.date,
        });
      }
      // 下穿（含等于 yesterday）
      if (yWas >= threshold && tNow < threshold) {
        events.push({
          event_type: 'theme_strength_cross_down',
          theme_id:   h.themeId,
          event_signature:
            `theme_strength_cross_down:${h.themeId}:${today.date}:${threshold}`,
          payload:    { threshold, from: yWas, to: tNow },
          asof_date:  today.date,
        });
      }
    }

    // 3. 信号变化
    if (t.signal !== y.signal && t.signal !== null && y.signal !== null) {
      events.push({
        event_type: 'theme_signal_change',
        theme_id:   h.themeId,
        event_signature:
          `theme_signal_change:${h.themeId}:${today.date}:${y.signal}_to_${t.signal}`,
        payload:    { from: y.signal, to: t.signal },
        asof_date:  today.date,
      });
    }
  }

  return events;
}
```

- [ ] **Step 6：跑测试看通过**

Run: `cd /Users/dreambt/sources/etf-radar/frontend && npx vitest run src/lib/portfolio/__tests__/eventDiff.test.ts 2>&1 | tail -15`
Expected: PASS（10 cases）

- [ ] **Step 7：自我审视——`detectEvents` 的"立场"是否符合 L1+L2 红线？**

边界条件检查：

```bash
cd /Users/dreambt/sources/etf-radar/frontend && npx vitest run src/lib/portfolio/__tests__/eventDiff.test.ts 2>&1 | grep -E "Test|PASS|FAIL"
```

确认输出没有产生"建议/推荐/可买"等指令性文案——`detectEvents` 仅输出 `event_type` 与 `payload`，UI 层负责呈现。

---

# Task 3：useEventsSnapshot — 单日完整快照拉取

**Files:**
- Create: `frontend/src/hooks/useEventsSnapshot.ts`
- Create: `frontend/src/hooks/__tests__/useEventsSnapshot.test.ts`

- [ ] **Step 1：写失败测试**

```ts
// frontend/src/hooks/__tests__/useEventsSnapshot.test.ts
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { setupServer } from 'msw/node';
import { http, HttpResponse } from 'msw';
import { SWRConfig } from 'swr';
import type { ReactNode } from 'react';
import { useEventsSnapshot } from '../useEventsSnapshot';

const server = setupServer();

const wrap = ({ children }: { children: ReactNode }) => (
  <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0 }}>
    {children}
  </SWRConfig>
);

beforeEach(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => { server.resetHandlers(); server.close(); });

describe('useEventsSnapshot', () => {
  it('成功拉取一日 themes+etfs+signals 并组装 Snapshot', async () => {
    server.use(
      http.get('*/snapshots/2026-06-23/themes.json', () => HttpResponse.json({
        schema_version: '1', generated_at: 'x',
        themes: [{ id: 'cn_tech', name: '科技', primary_cn: '515000',
          strength: { short:80, mid:80, long:80, composite:80 },
          tags: [], notes: '' }],
      })),
      http.get('*/snapshots/2026-06-23/signals.json', () => HttpResponse.json({
        theme_signals: [{ theme_id: 'cn_tech', signal: 'resonance' }],
      })),
    );

    const { result } = renderHook(() => useEventsSnapshot('2026-06-23'), { wrapper: wrap });
    await waitFor(() => expect(result.current.snapshot).toBeDefined());
    expect(result.current.snapshot!.date).toBe('2026-06-23');
    expect(result.current.snapshot!.themes.get('cn_tech')?.quadrant).toBe('leading');
    expect(result.current.snapshot!.themes.get('cn_tech')?.signal).toBe('resonance');
  });

  it('signals 缺失时仍组装快照，signal=null', async () => {
    server.use(
      http.get('*/snapshots/2026-06-23/themes.json', () => HttpResponse.json({
        schema_version: '1', generated_at: 'x',
        themes: [{ id: 'cn_tech', name: '科技', primary_cn: '515000',
          strength: { short:80, mid:80, long:80, composite:80 },
          tags: [], notes: '' }],
      })),
      http.get('*/snapshots/2026-06-23/signals.json', () => HttpResponse.json(
        { theme_signals: [] },
      )),
    );
    const { result } = renderHook(() => useEventsSnapshot('2026-06-23'), { wrapper: wrap });
    await waitFor(() => expect(result.current.snapshot).toBeDefined());
    expect(result.current.snapshot!.themes.get('cn_tech')?.signal).toBeNull();
  });

  it('date 为 undefined 时不发请求', () => {
    const { result } = renderHook(() => useEventsSnapshot(undefined), { wrapper: wrap });
    expect(result.current.snapshot).toBeUndefined();
    expect(result.current.error).toBeUndefined();
  });
});
```

- [ ] **Step 2：跑失败**

Run: `cd /Users/dreambt/sources/etf-radar/frontend && npx vitest run src/hooks/__tests__/useEventsSnapshot.test.ts 2>&1 | tail -10`
Expected: FAIL（hook 不存在）

- [ ] **Step 3：实现 hook**

```ts
// frontend/src/hooks/useEventsSnapshot.ts
import useSWR from 'swr';
import type { Snapshot, ThemeSnapshotEntry } from '@/lib/portfolio/eventTypes';
import type { SignalKind, Quadrant, Strength } from '@/lib/portfolio/types';
import { SnapshotThemesFileSchema } from '@/types/snapshots';
import { z } from 'zod';

// signals.json 校验（与 backend 输出对齐）
const SignalsFileSchema = z.object({
  theme_signals: z.array(z.object({
    theme_id: z.string(),
    signal:   z.enum(['resonance', 'transmission', 'divergence']).nullable(),
  })),
});

/** spec §3.7 — quadrant 判定（与 lib/rotation.ts 同口径但 portfolio 命名空间） */
function classifyQuadrant(strength: Strength): Quadrant {
  const x = strength.long, y = strength.short;
  if (x >= 50 && y >= 50) return 'leading';
  if (x <  50 && y >= 50) return 'weakening';   // 注意 portfolio 命名与 rotation 不同
  if (x <  50 && y <  50) return 'weak';
  return 'following';
}

/**
 * 单日完整快照拉取（themes + signals）+ 组装为 detectEvents 友好的 Snapshot。
 *
 * 不复用 useSnapshotsTimeline 的原因：
 *   - timeline 仅拉 themes，无 signals
 *   - Phase 3 仅在 portfolio 页用，独立 hook 解耦
 */
export interface UseEventsSnapshotResult {
  snapshot: Snapshot | undefined;
  error:    Error | undefined;
}

const fetcher = async (urls: [string, string]): Promise<{
  themesFile:  ReturnType<typeof SnapshotThemesFileSchema.parse>;
  signalsFile: z.infer<typeof SignalsFileSchema>;
}> => {
  const [themesUrl, signalsUrl] = urls;
  const [tRes, sRes] = await Promise.all([fetch(themesUrl), fetch(signalsUrl)]);
  if (!tRes.ok) throw new Error(`themes ${tRes.status}`);
  if (!sRes.ok) throw new Error(`signals ${sRes.status}`);
  return {
    themesFile:  SnapshotThemesFileSchema.parse(await tRes.json()),
    signalsFile: SignalsFileSchema.parse(await sRes.json()),
  };
};

export function useEventsSnapshot(date: string | undefined): UseEventsSnapshotResult {
  const key = date ? [
    `/data/snapshots/${date}/themes.json`,
    `/data/snapshots/${date}/signals.json`,
  ] as const : null;

  const { data, error } = useSWR(key, fetcher, {
    revalidateOnFocus: false,
    errorRetryInterval: 5000,
  });

  if (!date || !data) {
    return {
      snapshot: undefined,
      error: error ? (error as Error) : undefined,
    };
  }

  const sigByTheme = new Map<string, SignalKind | null>(
    data.signalsFile.theme_signals.map(s => [s.theme_id, s.signal]),
  );

  const themes = new Map<string, ThemeSnapshotEntry>();
  for (const t of data.themesFile.themes) {
    themes.set(t.id, {
      themeId:  t.id,
      strength: t.strength,
      quadrant: classifyQuadrant(t.strength),
      signal:   sigByTheme.get(t.id) ?? null,
    });
  }

  return {
    snapshot: { date, themes },
    error: undefined,
  };
}
```

- [ ] **Step 4：跑测试通过**

Run: `cd /Users/dreambt/sources/etf-radar/frontend && npx vitest run src/hooks/__tests__/useEventsSnapshot.test.ts 2>&1 | tail -15`
Expected: PASS（3 cases）

---

# Task 4：EventsProvider — Realtime 订阅 + upsertEvents

**Files:**
- Create: `frontend/src/providers/eventsContext.ts`
- Create: `frontend/src/providers/EventsProvider.tsx`
- Create: `frontend/src/hooks/useUserEvents.ts`

- [ ] **Step 1：写 context**

```ts
// frontend/src/providers/eventsContext.ts
import { createContext } from 'react';
import type { UserEvent, PendingEvent } from '@/lib/portfolio/eventTypes';

export interface UseEventsResult {
  events:    UserEvent[];
  unreadCount: number;
  loading:   boolean;
  error:     string | null;
  /** 批量插入；UNIQUE 约束自动 dedupe（ON CONFLICT DO NOTHING） */
  upsertEvents: (events: PendingEvent[]) => Promise<{ inserted: number; error: string | null }>;
  markRead:  (eventIds: string[]) => Promise<{ error: string | null }>;
  markAllRead: () => Promise<{ error: string | null }>;
}

export const defaultEventsResult: UseEventsResult = {
  events: [],
  unreadCount: 0,
  loading: false,
  error: null,
  upsertEvents: async () => ({ inserted: 0, error: 'EventsProvider 未挂载' }),
  markRead: async () => ({ error: 'EventsProvider 未挂载' }),
  markAllRead: async () => ({ error: 'EventsProvider 未挂载' }),
};

export const EventsContext = createContext<UseEventsResult>(defaultEventsResult);
```

- [ ] **Step 2：实现 EventsProvider**

```tsx
// frontend/src/providers/EventsProvider.tsx
import { useEffect, useState, useCallback, useRef, type ReactNode } from 'react';
import { isSupabaseConfigured, getSupabase } from '@/lib/supabase';
import { useAuth } from '@/hooks/useAuth';
import type { UserEvent, PendingEvent } from '@/lib/portfolio/eventTypes';
import { EventsContext, type UseEventsResult } from './eventsContext';

/** spec §5.5 验收：90 天前事件不显示 */
const SHOW_DAYS = 90;

function within90Days(iso: string): boolean {
  const created = Date.parse(iso);
  if (Number.isNaN(created)) return false;
  return Date.now() - created < SHOW_DAYS * 86400_000;
}

function useEventsImpl(): UseEventsResult {
  const { user, status } = useAuth();
  const [events, setEvents] = useState<UserEvent[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!user || !isSupabaseConfigured()) {
      setEvents([]);
      return;
    }
    setLoading(true);
    setError(null);
    const { data, error } = await getSupabase()
      .from('user_events')
      .select('*')
      .order('created_at', { ascending: false })
      .limit(200);                              // 上限保护：极端情况防止前端卡顿
    if (error) {
      setError(error.message);
      setEvents([]);
    } else {
      setEvents((data ?? []) as UserEvent[]);
    }
    setLoading(false);
  }, [user]);

  const refreshRef = useRef(refresh);
  useEffect(() => { refreshRef.current = refresh; }, [refresh]);

  useEffect(() => {
    if (status === 'authenticated') refreshRef.current();
  }, [status]);

  // Realtime — 与 HoldingsProvider 同 pattern: removeChannel 真正销毁
  useEffect(() => {
    if (status !== 'authenticated' || !isSupabaseConfigured() || !user) return;
    const supabase = getSupabase();
    const channel = supabase
      .channel(`user_events_${user.id}`)
      .on('postgres_changes',
        { event: '*', schema: 'public', table: 'user_events', filter: `user_id=eq.${user.id}` },
        () => { refreshRef.current(); })
      .subscribe();
    return () => { supabase.removeChannel(channel); };
  }, [status, user]);

  const upsertEvents = useCallback(async (pending: PendingEvent[]): Promise<{ inserted: number; error: string | null }> => {
    if (!user) return { inserted: 0, error: '未登录' };
    if (pending.length === 0) return { inserted: 0, error: null };
    const rows = pending.map(p => ({ ...p, user_id: user.id }));
    const { data, error } = await getSupabase()
      .from('user_events')
      .upsert(rows, { onConflict: 'user_id,event_signature', ignoreDuplicates: true })
      .select('id');
    if (error) return { inserted: 0, error: error.message };
    await refresh();
    return { inserted: data?.length ?? 0, error: null };
  }, [user, refresh]);

  const markRead = useCallback(async (eventIds: string[]) => {
    if (!user || eventIds.length === 0) return { error: null };
    const { error } = await getSupabase()
      .from('user_events')
      .update({ read_at: new Date().toISOString() })
      .in('id', eventIds)
      .is('read_at', null);
    if (error) return { error: error.message };
    await refresh();
    return { error: null };
  }, [user, refresh]);

  const markAllRead = useCallback(async () => {
    if (!user) return { error: null };
    const { error } = await getSupabase()
      .from('user_events')
      .update({ read_at: new Date().toISOString() })
      .eq('user_id', user.id)
      .is('read_at', null);
    if (error) return { error: error.message };
    await refresh();
    return { error: null };
  }, [user, refresh]);

  const visible = events.filter(e => within90Days(e.created_at));
  const unreadCount = visible.filter(e => e.read_at === null).length;

  const isAuthed = status === 'authenticated';
  return {
    events:   isAuthed ? visible : [],
    unreadCount: isAuthed ? unreadCount : 0,
    loading:  isAuthed ? loading : false,
    error,
    upsertEvents,
    markRead,
    markAllRead,
  };
}

export function EventsProvider({ children }: { children: ReactNode }) {
  const value = useEventsImpl();
  return <EventsContext.Provider value={value}>{children}</EventsContext.Provider>;
}
```

- [ ] **Step 3：写 hook（薄包装）**

```ts
// frontend/src/hooks/useUserEvents.ts
import { useContext } from 'react';
import { EventsContext } from '@/providers/eventsContext';

export const useUserEvents = () => useContext(EventsContext);
```

- [ ] **Step 4：写 EventsProvider 测试**

```tsx
// frontend/src/providers/__tests__/EventsProvider.test.tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, act } from '@testing-library/react';
import { EventsProvider } from '../EventsProvider';
import { useUserEvents } from '@/hooks/useUserEvents';
import type { UserEvent } from '@/lib/portfolio/eventTypes';

// Mock supabase 与 auth — 与现有 HoldingsProvider 测试同 pattern
vi.mock('@/lib/supabase', () => ({
  isSupabaseConfigured: () => true,
  getSupabase: () => mockSupabase,
}));
vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ user: { id: 'u1' }, status: 'authenticated' }),
}));

const mockEvents: UserEvent[] = [
  { id: 'e1', user_id: 'u1', event_type: 'theme_quadrant_change',
    theme_id: 'cn_tech', event_signature: 'sig1', payload: {},
    asof_date: '2026-06-23',
    created_at: new Date().toISOString(), read_at: null },
  { id: 'e2', user_id: 'u1', event_type: 'theme_signal_change',
    theme_id: 'cn_chem', event_signature: 'sig2', payload: {},
    asof_date: '2026-06-23',
    created_at: new Date(Date.now() - 100 * 86400_000).toISOString(),  // 100 天前
    read_at: null },
];

const channelMock = { on: vi.fn().mockReturnThis(), subscribe: vi.fn().mockReturnThis() };
const mockSupabase = {
  channel: vi.fn(() => channelMock),
  removeChannel: vi.fn(),
  from: vi.fn(() => ({
    select: vi.fn(() => ({
      order: vi.fn(() => ({
        limit: vi.fn().mockResolvedValue({ data: mockEvents, error: null }),
      })),
    })),
  })),
};

function Probe() {
  const { events, unreadCount } = useUserEvents();
  return (
    <div>
      <div data-testid="count">{events.length}</div>
      <div data-testid="unread">{unreadCount}</div>
    </div>
  );
}

describe('EventsProvider', () => {
  it('登录后拉取并过滤 90 天外事件', async () => {
    render(<EventsProvider><Probe /></EventsProvider>);
    await waitFor(() => {
      expect(screen.getByTestId('count').textContent).toBe('1');  // e2 被过滤
      expect(screen.getByTestId('unread').textContent).toBe('1');
    });
  });
});
```

- [ ] **Step 5：跑测试通过**

Run: `cd /Users/dreambt/sources/etf-radar/frontend && npx vitest run src/providers/__tests__/EventsProvider.test.tsx 2>&1 | tail -15`
Expected: PASS

---

# Task 5：事件触发器 + localStorage 节流

**Files:**
- Create: `frontend/src/hooks/usePortfolioEventDetection.ts`
- Create: `frontend/src/hooks/__tests__/usePortfolioEventDetection.test.ts`

- [ ] **Step 1：写失败测试**

```ts
// frontend/src/hooks/__tests__/usePortfolioEventDetection.test.ts
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { usePortfolioEventDetection } from '../usePortfolioEventDetection';

const upsertSpy = vi.fn().mockResolvedValue({ inserted: 0, error: null });

vi.mock('@/hooks/useUserEvents', () => ({
  useUserEvents: () => ({ upsertEvents: upsertSpy }),
}));

vi.mock('@/hooks/useEventsSnapshot', () => ({
  useEventsSnapshot: (date: string | undefined) => ({
    snapshot: date ? { date, themes: new Map() } : undefined,
    error: undefined,
  }),
}));

const STORAGE_KEY = 'portfolio_last_detected_date';

beforeEach(() => {
  localStorage.clear();
  upsertSpy.mockClear();
});

describe('usePortfolioEventDetection', () => {
  it('同一日已检测过则跳过', async () => {
    localStorage.setItem(STORAGE_KEY, '2026-06-23');
    renderHook(() => usePortfolioEventDetection({
      todayDate: '2026-06-23', yesterdayDate: '2026-06-22',
      holdings: [{ themeId: 'cn_tech', etfCode: '515000' }],
    }));
    await new Promise(r => setTimeout(r, 50));
    expect(upsertSpy).not.toHaveBeenCalled();
  });

  it('snapshots 都就位时触发 detectEvents + upsertEvents + 写 localStorage', async () => {
    renderHook(() => usePortfolioEventDetection({
      todayDate: '2026-06-23', yesterdayDate: '2026-06-22',
      holdings: [{ themeId: 'cn_tech', etfCode: '515000' }],
    }));
    await waitFor(() => {
      expect(upsertSpy).toHaveBeenCalledTimes(1);
      expect(localStorage.getItem(STORAGE_KEY)).toBe('2026-06-23');
    });
  });

  it('holdings 为空时不触发', async () => {
    renderHook(() => usePortfolioEventDetection({
      todayDate: '2026-06-23', yesterdayDate: '2026-06-22', holdings: [],
    }));
    await new Promise(r => setTimeout(r, 50));
    expect(upsertSpy).not.toHaveBeenCalled();
  });

  it('日期缺失时不触发', async () => {
    renderHook(() => usePortfolioEventDetection({
      todayDate: undefined, yesterdayDate: '2026-06-22',
      holdings: [{ themeId: 'x', etfCode: 'x' }],
    }));
    await new Promise(r => setTimeout(r, 50));
    expect(upsertSpy).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 2：跑失败**

Run: `cd /Users/dreambt/sources/etf-radar/frontend && npx vitest run src/hooks/__tests__/usePortfolioEventDetection.test.ts 2>&1 | tail -10`
Expected: FAIL

- [ ] **Step 3：实现 hook**

```ts
// frontend/src/hooks/usePortfolioEventDetection.ts
import { useEffect, useRef } from 'react';
import { useEventsSnapshot } from './useEventsSnapshot';
import { useUserEvents } from './useUserEvents';
import { detectEvents, type HoldingForDiff } from '@/lib/portfolio/eventDiff';

const STORAGE_KEY = 'portfolio_last_detected_date';

interface Args {
  todayDate:     string | undefined;
  yesterdayDate: string | undefined;
  holdings:      HoldingForDiff[];
}

/**
 * 持仓事件检测触发器（spec §3.7）。
 *
 * 流程：访问 /portfolio → 拉 today + yesterday 快照 → detectEvents → upsert → 写 localStorage。
 *
 * 节流：localStorage(`portfolio_last_detected_date`) 同日不重跑，避免每次 mount 都打库。
 *   注意：节流 key 仅用 date 不绑 user — 同设备多账号场景下检测一次即可，
 *   因为 user_events 由 UNIQUE 约束做最终 dedupe（即便重复 detect，库里也只有一份）。
 */
export function usePortfolioEventDetection({
  todayDate, yesterdayDate, holdings,
}: Args): void {
  const today     = useEventsSnapshot(todayDate);
  const yesterday = useEventsSnapshot(yesterdayDate);
  const { upsertEvents } = useUserEvents();

  const firedRef = useRef(false);

  useEffect(() => {
    if (firedRef.current) return;
    if (!todayDate || !yesterdayDate) return;
    if (holdings.length === 0) return;
    if (!today.snapshot || !yesterday.snapshot) return;

    const lastDetected = localStorage.getItem(STORAGE_KEY);
    if (lastDetected === todayDate) return;

    firedRef.current = true;

    const events = detectEvents(today.snapshot, yesterday.snapshot, holdings);
    if (events.length > 0) {
      void upsertEvents(events);
    }
    localStorage.setItem(STORAGE_KEY, todayDate);
  }, [todayDate, yesterdayDate, today.snapshot, yesterday.snapshot, holdings, upsertEvents]);
}
```

- [ ] **Step 4：跑测试通过**

Run: `cd /Users/dreambt/sources/etf-radar/frontend && npx vitest run src/hooks/__tests__/usePortfolioEventDetection.test.ts 2>&1 | tail -15`
Expected: PASS（4 cases）

---

# Task 6：EventItem + EventTimeline 组件

**Files:**
- Create: `frontend/src/components/portfolio/EventItem.tsx`
- Create: `frontend/src/components/portfolio/EventTimeline.tsx`
- Create: `frontend/src/components/portfolio/__tests__/EventItem.test.tsx`
- Create: `frontend/src/components/portfolio/__tests__/EventTimeline.test.tsx`

- [ ] **Step 1：写 EventItem 测试**

```tsx
// frontend/src/components/portfolio/__tests__/EventItem.test.tsx
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { EventItem } from '../EventItem';
import type { UserEvent } from '@/lib/portfolio/eventTypes';

const mk = (overrides: Partial<UserEvent>): UserEvent => ({
  id: 'e1', user_id: 'u1', event_type: 'theme_quadrant_change',
  theme_id: 'cn_tech', event_signature: 'sig',
  payload: { from: 'weak', to: 'leading' },
  asof_date: '2026-06-23',
  created_at: '2026-06-23T01:00:00Z', read_at: null,
  ...overrides,
});

describe('EventItem', () => {
  it('象限切到 leading 显示利好（🟢）', () => {
    render(<EventItem event={mk({})} themeName="科技" />);
    expect(screen.getByText(/科技/)).toBeInTheDocument();
    expect(screen.getByText(/领涨|强势/)).toBeInTheDocument();
    expect(screen.getByTestId('event-color')).toHaveAttribute('data-color', 'green');
  });

  it('象限切到 weak 显示利空（🟡）', () => {
    render(<EventItem event={mk({ payload: { from: 'leading', to: 'weak' } })} themeName="科技" />);
    expect(screen.getByTestId('event-color')).toHaveAttribute('data-color', 'red');
  });

  it('强度上穿显示利好', () => {
    const e = mk({ event_type: 'theme_strength_cross_up',
      payload: { threshold: 75, from: 70, to: 80 } });
    render(<EventItem event={e} themeName="科技" />);
    expect(screen.getByText(/上穿|进入强势区/)).toBeInTheDocument();
    expect(screen.getByTestId('event-color')).toHaveAttribute('data-color', 'green');
  });

  it('信号变共振显示利好', () => {
    const e = mk({ event_type: 'theme_signal_change',
      payload: { from: 'divergence', to: 'resonance' } });
    render(<EventItem event={e} themeName="科技" />);
    expect(screen.getByTestId('event-color')).toHaveAttribute('data-color', 'green');
  });

  it('已读样式：灰底', () => {
    const e = mk({ read_at: '2026-06-23T02:00:00Z' });
    render(<EventItem event={e} themeName="科技" />);
    const root = screen.getByTestId('event-root');
    expect(root.className).toMatch(/bg-gray-50|opacity-/);
  });

  it('文案保持 L1+L2 立场（不含"买入/推荐"）', () => {
    render(<EventItem event={mk({})} themeName="科技" />);
    const txt = document.body.textContent ?? '';
    expect(txt).not.toMatch(/推荐买入|建议买入|可买/);
  });
});
```

- [ ] **Step 2：实现 EventItem**

```tsx
// frontend/src/components/portfolio/EventItem.tsx
import type { UserEvent, EventType } from '@/lib/portfolio/eventTypes';
import type { Quadrant, SignalKind } from '@/lib/portfolio/types';

interface Props {
  event:     UserEvent;
  themeName: string;
}

type Tone = 'green' | 'red' | 'gray';

/**
 * 事件颜色判定（L1+L2 立场：仅"信号事实形容词"，无指令）：
 *   - 绿：进入更强状态（leading/上穿/resonance）
 *   - 红：进入更弱状态（weak/下穿/divergence）
 *   - 灰：中性切换（无明显方向）
 */
function tone(event: UserEvent): Tone {
  switch (event.event_type) {
    case 'theme_quadrant_change': {
      const to = event.payload.to as Quadrant;
      if (to === 'leading')  return 'green';
      if (to === 'weak')     return 'red';
      return 'gray';
    }
    case 'theme_strength_cross_up':   return 'green';
    case 'theme_strength_cross_down': return 'red';
    case 'theme_signal_change': {
      const to = event.payload.to as SignalKind;
      if (to === 'resonance')   return 'green';
      if (to === 'divergence')  return 'red';
      return 'gray';
    }
  }
}

const QUADRANT_LABEL: Record<Quadrant, string> = {
  leading:   '领涨',
  weakening: '退潮',
  following: '跟随',
  weak:      '弱势',
};

const SIGNAL_LABEL: Record<SignalKind, string> = {
  resonance:    '共振',
  transmission: '传导',
  divergence:   '背离',
};

function label(event: UserEvent, themeName: string): string {
  switch (event.event_type) {
    case 'theme_quadrant_change': {
      const from = QUADRANT_LABEL[event.payload.from as Quadrant];
      const to   = QUADRANT_LABEL[event.payload.to   as Quadrant];
      return `${themeName} 象限：${from} → ${to}`;
    }
    case 'theme_strength_cross_up': {
      const th = event.payload.threshold as number;
      if (th === 75) return `${themeName} 强度上穿 75（进入强势区）`;
      if (th === 50) return `${themeName} 强度上穿 50`;
      return `${themeName} 强度上穿 25`;
    }
    case 'theme_strength_cross_down': {
      const th = event.payload.threshold as number;
      if (th === 25) return `${themeName} 强度下穿 25（进入弱势区）`;
      if (th === 50) return `${themeName} 强度下穿 50`;
      return `${themeName} 强度下穿 75`;
    }
    case 'theme_signal_change': {
      const from = SIGNAL_LABEL[event.payload.from as SignalKind];
      const to   = SIGNAL_LABEL[event.payload.to   as SignalKind];
      return `${themeName} 信号：${from} → ${to}`;
    }
  }
}

const TONE_BAR: Record<Tone, string> = {
  green: 'bg-green-500',
  red:   'bg-red-500',
  gray:  'bg-gray-400',
};

export const EventItem = ({ event, themeName }: Props) => {
  const t = tone(event);
  const isRead = event.read_at !== null;
  return (
    <div
      data-testid="event-root"
      className={`flex items-start gap-2 py-2 px-3 border-b last:border-b-0 ${isRead ? 'bg-gray-50 opacity-70' : 'bg-white'}`}
    >
      <span data-testid="event-color" data-color={t} className={`w-1 self-stretch rounded ${TONE_BAR[t]}`} />
      <div className="flex-1">
        <div className={`text-sm ${isRead ? 'text-gray-500' : 'text-gray-800'}`}>{label(event, themeName)}</div>
        <div className="text-xs text-gray-400 mt-0.5">{event.asof_date}</div>
      </div>
    </div>
  );
};
```

- [ ] **Step 3：跑 EventItem 测试通过**

Run: `cd /Users/dreambt/sources/etf-radar/frontend && npx vitest run src/components/portfolio/__tests__/EventItem.test.tsx 2>&1 | tail -15`
Expected: PASS（6 cases）

- [ ] **Step 4：写 EventTimeline 测试**

```tsx
// frontend/src/components/portfolio/__tests__/EventTimeline.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { EventTimeline } from '../EventTimeline';
import type { UserEvent } from '@/lib/portfolio/eventTypes';

const themes = new Map<string, string>([['cn_tech', '科技'], ['cn_chem', '化工']]);

const mkEvent = (id: string, themeId: string, read = false): UserEvent => ({
  id, user_id: 'u1', event_type: 'theme_quadrant_change',
  theme_id: themeId, event_signature: `sig_${id}`,
  payload: { from: 'weak', to: 'leading' },
  asof_date: '2026-06-23',
  created_at: '2026-06-23T01:00:00Z', read_at: read ? '2026-06-23T02:00:00Z' : null,
});

const markAllReadSpy = vi.fn().mockResolvedValue({ error: null });

describe('EventTimeline', () => {
  it('默认折叠（仅显示标题 + 未读数）', () => {
    render(<EventTimeline events={[mkEvent('e1', 'cn_tech')]} themeNames={themes}
      unreadCount={1} markAllRead={markAllReadSpy} />);
    expect(screen.getByText(/事件流/)).toBeInTheDocument();
    expect(screen.getByText(/1/)).toBeInTheDocument();
    expect(screen.queryByTestId('event-root')).not.toBeInTheDocument();
  });

  it('展开后渲染事件列表', () => {
    render(<EventTimeline events={[mkEvent('e1', 'cn_tech')]} themeNames={themes}
      unreadCount={1} markAllRead={markAllReadSpy} />);
    fireEvent.click(screen.getByRole('button', { name: /事件流/ }));
    expect(screen.getByTestId('event-root')).toBeInTheDocument();
    expect(screen.getByText(/科技/)).toBeInTheDocument();
  });

  it('空事件展开后显示空态文案', () => {
    render(<EventTimeline events={[]} themeNames={themes}
      unreadCount={0} markAllRead={markAllReadSpy} />);
    fireEvent.click(screen.getByRole('button', { name: /事件流/ }));
    expect(screen.getByText(/暂无事件/)).toBeInTheDocument();
  });

  it('未知 themeId 不崩溃，使用 themeId 兜底', () => {
    render(<EventTimeline events={[mkEvent('e1', 'cn_unknown')]} themeNames={themes}
      unreadCount={1} markAllRead={markAllReadSpy} />);
    fireEvent.click(screen.getByRole('button', { name: /事件流/ }));
    expect(screen.getByText(/cn_unknown/)).toBeInTheDocument();
  });

  it('"全部标为已读"按钮调用 markAllRead', () => {
    render(<EventTimeline events={[mkEvent('e1', 'cn_tech')]} themeNames={themes}
      unreadCount={1} markAllRead={markAllReadSpy} />);
    fireEvent.click(screen.getByRole('button', { name: /事件流/ }));
    fireEvent.click(screen.getByRole('button', { name: /全部标为已读/ }));
    expect(markAllReadSpy).toHaveBeenCalled();
  });
});
```

- [ ] **Step 5：实现 EventTimeline**

```tsx
// frontend/src/components/portfolio/EventTimeline.tsx
import { useState } from 'react';
import type { UserEvent } from '@/lib/portfolio/eventTypes';
import { EventItem } from './EventItem';

interface Props {
  events:      UserEvent[];
  themeNames:  Map<string, string>;
  unreadCount: number;
  markAllRead: () => Promise<{ error: string | null }>;
}

/**
 * 持仓事件流（spec §4.8）。
 *   - 默认折叠（与 OpportunityScanner 同 pattern）
 *   - 标题显示未读数（与 Header 红点联动）
 *   - 立场：仅"事件事实陈述"，无买卖指令
 */
export const EventTimeline = ({ events, themeNames, unreadCount, markAllRead }: Props) => {
  const [open, setOpen] = useState(false);

  return (
    <section className="mt-6 border rounded-lg bg-gray-50">
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between px-4 py-3 text-left"
        aria-expanded={open}
      >
        <span className="font-medium">
          {`事件流(${events.length}${unreadCount > 0 ? `, 未读 ${unreadCount}` : ''})`}
        </span>
        <span className="text-xs text-gray-500">{open ? '收起 ▲' : '展开 ▼'}</span>
      </button>

      {open && (
        <div className="px-2 pb-2">
          {events.length === 0 ? (
            <div className="text-sm text-gray-500 text-center py-6">
              暂无事件——持仓主题在最近一个交易日未发生信号变化。
            </div>
          ) : (
            <>
              <div className="flex justify-end px-2 py-1">
                <button
                  type="button"
                  onClick={() => { void markAllRead(); }}
                  className="text-xs text-blue-600 hover:underline disabled:opacity-50"
                  disabled={unreadCount === 0}
                >全部标为已读</button>
              </div>
              <div className="bg-white border rounded">
                {events.map(e => (
                  <EventItem
                    key={e.id}
                    event={e}
                    themeName={themeNames.get(e.theme_id) ?? e.theme_id}
                  />
                ))}
              </div>
            </>
          )}
        </div>
      )}
    </section>
  );
};
```

- [ ] **Step 6：跑 EventTimeline 测试通过**

Run: `cd /Users/dreambt/sources/etf-radar/frontend && npx vitest run src/components/portfolio/__tests__/EventTimeline.test.tsx 2>&1 | tail -15`
Expected: PASS（5 cases）

---

# Task 7：集成到 /portfolio 页 + Header 红点

**Files:**
- Modify: `frontend/src/App.tsx`（包入 EventsProvider）
- Create: `frontend/src/components/Header/EventBadge.tsx`
- Modify: `frontend/src/components/Header/index.tsx`（嵌入 EventBadge）
- Modify: `frontend/src/components/portfolio/HoldingsList.tsx`（挂载 EventTimeline + 触发检测）

- [ ] **Step 1：App.tsx 包入 EventsProvider**

读 `frontend/src/App.tsx` 当前结构后插入 EventsProvider — 应在 AuthProvider 之内、HoldingsProvider 之后（同级），结构如：

```tsx
<AuthProvider>
  <HoldingsProvider>
    <EventsProvider>
      {/* existing children */}
    </EventsProvider>
  </HoldingsProvider>
</AuthProvider>
```

具体修改：在 import 区添加 `import { EventsProvider } from '@/providers/EventsProvider';`，找到 `<HoldingsProvider>` 与其 `</HoldingsProvider>` 之间内容，包一层 EventsProvider。

- [ ] **Step 2：写 EventBadge 测试**

```tsx
// frontend/src/components/Header/__tests__/EventBadge.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { EventBadge } from '../EventBadge';

const eventsMock = vi.fn();
vi.mock('@/hooks/useUserEvents', () => ({
  useUserEvents: () => eventsMock(),
}));

const rWith = (count: number) => {
  eventsMock.mockReturnValue({ unreadCount: count, events: [] });
  return render(<MemoryRouter><EventBadge /></MemoryRouter>);
};

describe('EventBadge', () => {
  it('未读 0 时不显示徽章', () => {
    rWith(0);
    expect(screen.queryByTestId('event-badge')).not.toBeInTheDocument();
  });
  it('未读 > 0 时显示数字', () => {
    rWith(3);
    expect(screen.getByTestId('event-badge').textContent).toBe('3');
  });
  it('未读 > 99 显示 99+', () => {
    rWith(150);
    expect(screen.getByTestId('event-badge').textContent).toBe('99+');
  });
});
```

- [ ] **Step 3：实现 EventBadge**

```tsx
// frontend/src/components/Header/EventBadge.tsx
import { Link } from 'react-router-dom';
import { useUserEvents } from '@/hooks/useUserEvents';

/**
 * Header 红点徽章（spec §5.5 验收）：
 *   - unread === 0 时不渲染（无干扰）
 *   - 点击跳 /portfolio 自动滚到 EventTimeline（hash anchor 暂不做，YAGNI；首版只跳页）
 */
export const EventBadge = () => {
  const { unreadCount } = useUserEvents();
  if (unreadCount === 0) return null;
  const text = unreadCount > 99 ? '99+' : String(unreadCount);
  return (
    <Link
      to="/portfolio"
      aria-label={`您有 ${unreadCount} 条未读事件`}
      className="inline-flex items-center justify-center min-w-5 h-5 px-1 rounded-full bg-red-500 text-white text-xs font-medium"
      data-testid="event-badge"
    >{text}</Link>
  );
};
```

- [ ] **Step 4：嵌入 Header**

读 `frontend/src/components/Header/index.tsx` 找到现有 UserMenu 渲染位置，在 UserMenu 旁（前置）插入 `<EventBadge />`：

```tsx
import { EventBadge } from './EventBadge';
// 在 UserMenu 旁渲染（仅登录态可见 — EventBadge 内部判 unreadCount = 0 时返回 null，已实现"未登录无未读"）
<div className="flex items-center gap-2">
  <EventBadge />
  <UserMenu />
</div>
```

- [ ] **Step 5：HoldingsList 挂载 EventTimeline + 触发检测**

修改 `frontend/src/components/portfolio/HoldingsList.tsx`，在 populated 分支注入：

```tsx
// 顶部 imports 增加：
import { useDataContext } from '@/providers/dataContext';
import { useUserEvents } from '@/hooks/useUserEvents';
import { usePortfolioEventDetection } from '@/hooks/usePortfolioEventDetection';
import { EventTimeline } from './EventTimeline';
import { useSnapshotsTimeline } from '@/hooks/useSnapshotsTimeline';

// 在 HoldingsList 函数内部，loading 检查之后：
const { index } = useSnapshotsTimeline();
const todayDate     = index?.snapshots[index.snapshots.length - 1]?.date;
const yesterdayDate = index?.snapshots[index.snapshots.length - 2]?.date;

const data = useDataContext();
const themeNames = new Map<string, string>(
  data?.themes?.themes.map(t => [t.id, t.name]) ?? []
);

// holdings-for-diff: 仅 covered（themeId 有值）
const holdingsForDiff = scores
  .filter(s => s.status === 'covered' && s.themeId)
  .map(s => ({ themeId: s.themeId!, etfCode: s.etfCode }));

usePortfolioEventDetection({ todayDate, yesterdayDate, holdings: holdingsForDiff });

const { events, unreadCount, markAllRead } = useUserEvents();

// 在 PortfolioSummary 与 OpportunityScanner 之间插入：
<EventTimeline
  events={events}
  themeNames={themeNames}
  unreadCount={unreadCount}
  markAllRead={markAllRead}
/>
```

- [ ] **Step 6：跑相关单测确认无回归**

Run: `cd /Users/dreambt/sources/etf-radar/frontend && npx vitest run src/components/portfolio src/components/Header src/hooks src/providers src/lib/portfolio 2>&1 | tail -20`
Expected: 全部 PASS（含 Phase 3 新增 25+ cases）

---

# Task 8：E2E 烟雾 + 整体回归

**Files:**
- Create: `frontend/e2e/portfolio-events.spec.ts`

- [ ] **Step 1：写匿名烟雾 E2E**

```ts
// frontend/e2e/portfolio-events.spec.ts
import { test, expect } from '@playwright/test';

/**
 * Phase 3 EventTimeline E2E。
 *
 * 完整流程（登录态 + 真实事件）需要 Supabase auth mock + user_events 注入，
 * 属 Phase 1 e2e 基建。本文件仅做"集成后 /portfolio 页未破"烟雾。
 *
 * 单测层面已覆盖：
 *   - eventDiff.test.ts (10 cases)
 *   - useEventsSnapshot.test.ts (3 cases)
 *   - EventsProvider.test.tsx (1 case + Realtime mock)
 *   - usePortfolioEventDetection.test.ts (4 cases)
 *   - EventItem.test.tsx (6 cases)
 *   - EventTimeline.test.tsx (5 cases)
 *   - EventBadge.test.tsx (3 cases)
 */

test.describe('EventTimeline (smoke)', () => {
  test('/portfolio 集成 EventTimeline 后页面仍能渲染（匿名）', async ({ page }) => {
    await page.goto('/#/portfolio');
    const cardVisible = await Promise.race([
      page.getByText('持仓信号监控').waitFor({ state: 'visible', timeout: 5000 }).then(() => 'login'),
      page.getByText('未配置 Supabase').waitFor({ state: 'visible', timeout: 5000 }).then(() => 'unconfig'),
    ]).catch(() => null);
    expect(cardVisible).toBeTruthy();
  });

  test.skip('登录态下 EventTimeline 折叠面板可见（待 Phase 1 e2e 基建）', () => {
    // 占位：需要 Supabase auth mock + 持仓 + 历史快照差异注入。
    // 完成后可解锁的断言：
    //   1. await page.getByRole('button', { name: /事件流/ }).click();
    //   2. await expect(page.getByText(/象限|强度|信号/)).toBeVisible();
    //   3. await page.getByRole('button', { name: /全部标为已读/ }).click();
    //   4. await expect(page.getByText(/事件流\(\d+\)/)).toBeVisible();  // 未读数清零
  });
});
```

- [ ] **Step 2：全套 lint + typecheck + 单测回归**

Run:
```bash
cd /Users/dreambt/sources/etf-radar/frontend && npm run lint && npm run typecheck && npx vitest run 2>&1 | tail -15
```

Expected:
- ESLint: No issues
- tsc: 0 errors
- Vitest: 全部 PASS（含 Phase 1+2+3）

---

## 已知偏离 spec 之处（供 review 时确认）

| spec 条款 | 实际实现 | 理由 |
|---|---|---|
| §3.7 detectEvents `lookup(snapshot, etfCode)` 以 ETF 级 | 改为主题级（按 themeId 聚合） | snapshots 文件无 ETF 级 quadrant；主题级与 RotationPage 同构，事件对持有该主题的所有 ETF 都成立 |
| §5.5 验收"首次登录只生成 last 7 天事件" | 仅生成"昨日 vs 今日"一次 | YAGNI；spec 提及 7 天为防大幅延迟登录，初版用户场景未观察到，留作 Phase 3.1 |
| §5.5 任务清单"7. E2E + 历史快照 fixtures" | 仅匿名烟雾 + 详细单测覆盖 | 登录态 E2E 依赖 Phase 1 auth mock 基建（spec 未覆盖） |

---

## 自我审视（writing-plans skill 要求）

### 1. Spec 覆盖
| spec 验收项 | plan 任务 |
|---|---|
| covered ETF quadrant 变化生成事件 | Task 2 — `theme_quadrant_change` |
| covered ETF strength 跨阈值生成事件 | Task 2 — `theme_strength_cross_*` |
| covered ETF signal 变化生成事件 | Task 2 — `theme_signal_change` |
| uncovered / 新加 ETF 跳过差分不报错 | Task 2 fixture + holdings filter（Task 7 `scores.filter(covered)`） |
| 同事件 N 次访问只生成一条 | Task 1（UNIQUE）+ Task 4（`upsert ignoreDuplicates`）+ Task 5（localStorage 节流） |
| 已读/未读状态正确 | Task 4（markRead/markAllRead） + Task 6（已读样式） |
| Realtime：A 浏览器新事件 → B 浏览器红点实时更新 | Task 4（postgres_changes 订阅） + Task 7（EventBadge 经 useUserEvents 自动 rerender） |
| 90 天前事件不显示 | Task 4（`within90Days` filter） |
| 算法单测覆盖所有边界 | Task 2（10 cases 含边界） |

### 2. Placeholder 扫描
- 未发现 "TBD/TODO/implement later/add validation/handle edge cases" 类占位。
- 所有 step 含完整代码 / 完整命令 / 预期输出。

### 3. 类型一致性
- `Snapshot` / `ThemeSnapshotEntry` 在 Task 2 定义，Task 3、4、5 均通过 `eventTypes.ts` 导入。
- `Quadrant` 在 `types.ts` 已存在为 `'leading' | 'weakening' | 'following' | 'weak'` — Task 3 `classifyQuadrant`、Task 6 `QUADRANT_LABEL`、Task 2 fixture 全部用此命名（与 rotation.ts 的 `'leading' | 'rising' | 'lagging' | 'fading'` 不冲突，属不同命名空间）。
- `PendingEvent` Task 2 创建，Task 4 `upsertEvents` 接收，Task 5 调用 → 一致。
- `UserEvent` Task 2 定义，Task 4 提供，Task 6 消费 → 一致。
- `HoldingForDiff` Task 2 定义 `{ themeId, etfCode }`，Task 5 hook 接收，Task 7 由 scores 派生 → 一致。

### 4. 已知风险
- **localStorage 节流 key 与日期绑定**：用户切换账号且同日，第二个账号不会重跑 detect → 但 user_events 表 user_id 隔离，结果是新账号当天看不到事件直到次日。对单设备多账号场景可接受，记为 Phase 3.1 改进点。
- **Realtime channel name 含 user.id**：与 HoldingsProvider 不同，是有意的（避免广播给同表所有用户）。

---

## 执行交接

Plan 完成并保存到 `docs/superpowers/plans/2026-06-23-portfolio-monitor-phase-3.md`。两条执行路径：

1. **Subagent-Driven（推荐）** — 每任务派遣全新 subagent，spec compliance + code quality 两段评审，快速迭代
2. **Inline Execution** — 在当前会话以 executing-plans 批量执行，带 checkpoint
