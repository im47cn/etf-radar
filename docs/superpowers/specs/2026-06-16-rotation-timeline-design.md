# Phase B: 主题轮动时间轴回放设计

> **文档元信息**
> - 创建日期: 2026-06-16
> - 上游设计: [`2026-06-16-theme-rotation-design.md`](2026-06-16-theme-rotation-design.md) §4 (Phase B 骨架)
> - 数据基础: [`2026-06-16-snapshots-backfill.md`](../plans/2026-06-16-snapshots-backfill.md) (已完成, 119 天 backfilled snapshots)
> - 范围: `/rotation` 页面增强 — 静态散点 → 时间轴动画播放器

---

## 1. 目标与非目标

### 目标
在 `/rotation` 页面叠加时间轴功能, 让用户可拖动滑块查看历史象限分布, 或点击 ▶ 自动播放 119 天轮动过程, 配合 Top-5 主题尾迹增强方向感, 帮助用户识别"持续强势 / 新崛起 / 退潮"的演化路径。

### 非目标 (YAGNI)
- ❌ URL 状态同步 (每次进入默认最新)
- ❌ 数据积累中占位逻辑 (索引必然 ≥ 119 天)
- ❌ 14 主题全尾迹 (视觉密度太高, 仅 Top-5)
- ❌ 循环播放 (到末尾停止)
- ❌ 移动端单独路由 (响应式 matchMedia 即可)
- ❌ Storybook / 视觉回归 (项目当前未引入)

---

## 2. 数据契约

### 2.1 索引: `data/latest/snapshots-index.json`

已由 Phase B 数据基础生成, 当前 120 entries (119 backfilled + 1 实时):

```json
{
  "schema_version": "1.0",
  "generated_at": "2026-06-16T14:50:50.802039+08:00",
  "snapshots": [
    {"date": "2026-01-02", "themes_path": "snapshots/2026-01-02/themes.json"},
    ...
    {"date": "2026-06-15", "themes_path": "snapshots/2026-06-15/themes.json"}
  ]
}
```

**前端契约 (zod schema, `frontend/src/types/snapshots.ts`)**:

```typescript
import { z } from 'zod';

export const SnapshotEntrySchema = z.object({
  date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
  themes_path: z.string(),
});

export const SnapshotsIndexSchema = z.object({
  schema_version: z.string(),
  generated_at: z.string(),
  snapshots: z.array(SnapshotEntrySchema).min(1),
});

export type SnapshotsIndex = z.infer<typeof SnapshotsIndexSchema>;
export type SnapshotEntry = z.infer<typeof SnapshotEntrySchema>;
```

### 2.2 单帧: `data/snapshots/<date>/themes.json`

格式与 `data/latest/themes.json` 完全一致 (复用现有 `ThemesSchema`)。前端 `SnapshotFrame` 类型:

```typescript
export interface SnapshotFrame {
  date: string;        // YYYY-MM-DD
  themes: Theme[];     // 复用 frontend/src/types/themes.ts
}
```

---

## 3. UI 设计

### 3.1 桌面布局 (≥768px)

```
┌──────────────────────────────────────────────────────────────────────────┐
│ /rotation                                                                │
├──────────────────────────────────────────────────────────────────────────┤
│ [可选: 黄色横幅 — 时间轴/帧错误时]                                          │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   [QuadrantLegend 复用 Phase A]                                          │
│                                                                          │
│   [ScatterChart - 散点图]                                                │
│     · 14 主气泡 (当前帧)                                                  │
│     · Top-5 尾迹 (showTrails=true 时, 渐变 opacity 0.05→0.4)              │
│     · 中线 50 切四象限                                                     │
│                                                                          │
├──────────────────────────────────────────────────────────────────────────┤
│ [⏹][▶/⏸] ━━●━━━━━━━━━━━━━━━ 2026-06-12   [1x|2x|4x] [☐显示尾迹]      │
└──────────────────────────────────────────────────────────────────────────┘
```

### 3.2 移动端布局 (<768px) — 双层堆叠

```
┌──────────────────────────────────────┐
│ [⏹][▶/⏸] ━━━━━●━━━━━━ 2026-06-12  │
│ [1x|2x|4x]            [☐显示尾迹]   │
└──────────────────────────────────────┘
```

### 3.3 交互细节

| 控件 | 行为 |
|------|------|
| 滑块 (native range input) | 拖动 → 立即切换帧; 步进 = 1 天 (dates 数组索引) |
| ▶ | 播放 (若当前=末尾, 先 reset 到第一帧); 切换为 ⏸ |
| ⏸ | 暂停; 切换为 ▶, 保持 currentDate |
| ⏹ | 停止并重置到最新帧 (snapshots[last]) |
| 速度 segmented control | 1x=300ms / 2x=150ms / 4x=80ms (per frame) |
| 尾迹勾选框 | 默认 OFF; ON 时显示 Top-5 主题过去 10 帧尾迹 |
| 末尾自动停止 | 到 dates[last] 时 → pause, 不循环 |

---

## 4. 架构: 分层 hooks + 组件 (Approach B)

### 4.1 文件结构

```
frontend/src/
├── hooks/
│   ├── useSnapshotsTimeline.ts       # fetch index + LRU 缓存 + currentDate
│   └── useTimelinePlayer.ts          # 播放状态机 + setInterval
├── components/rotation/
│   ├── TimelineControls.tsx          # 纯 UI 受控: 滑块 + ▶⏸⏹ + 速度 + 尾迹
│   ├── RotationTimelinePlayer.tsx    # 顶层装配 + 容灾 (~50 行)
│   └── RotationScatterWithTrails.tsx # 包装 ScatterChart, 叠加 Top-5 尾迹
├── lib/
│   ├── snapshotsCache.ts             # 纯函数: createLRU<V>(max)
│   └── trailGradient.ts              # 纯函数: trailOpacity / pickTopByComposite / buildTrails
└── types/
    └── snapshots.ts                  # zod schema + TS types
```

### 4.2 数据流

```
DataProvider (existing)
   │ latest themes (容灾 fallback)
   ↓
RotationPage
   │ <RotationTimelinePlayer fallbackThemes={themes} />
   ↓
RotationTimelinePlayer
   ├─ useSnapshotsTimeline()
   │      → { index, currentDate, frame, setDate, prefetch, status, error }
   │      ├─ SWR fetch snapshots-index.json (auto-retry ∞)
   │      ├─ SWR fetch snapshots/<date>/themes.json (auto-retry 3)
   │      ├─ snapshotsCache (LRU, max=20)
   │      └─ 启动预取最近 10 帧
   │
   ├─ useTimelinePlayer({ dates, currentDate, onAdvance, onPrefetchNeeded })
   │      → { playing, speed, animationDuration, play, pause, stop, setSpeed }
   │      ├─ setInterval ({1:300, 2:150, 4:80}[speed])
   │      ├─ play() 时预取未来 5 帧
   │      └─ 末尾自动 pause
   │
   ├─ TimelineControls (纯 UI 受控)
   │
   └─ RotationScatterWithTrails
          ├─ 当前帧 14 主气泡 (Recharts Scatter, animationDuration 动态)
          └─ Top-5 尾迹 (showTrails=true): 5 个 Scatter 序列, opacity 0.05→0.4
```

### 4.3 Hooks 接口

#### `useSnapshotsTimeline`

```typescript
export type TimelineStatus = 'loading' | 'ready' | 'index-error' | 'frame-error';

export interface UseSnapshotsTimelineResult {
  index: SnapshotsIndex | undefined;
  currentDate: string | undefined;
  frame: SnapshotFrame | undefined;   // frame-error 时保留上一次成功值
  setDate: (date: string) => void;
  prefetch: (dates: string[]) => void; // play() 时调用
  status: TimelineStatus;
  error: string | undefined;           // 失败的 date 串
}

export function useSnapshotsTimeline(): UseSnapshotsTimelineResult;
```

**内部行为**:
- 启动: SWR fetch index → zod parse; 失败终态 `index-error`
- 初始化: `currentDate = snapshots[last].date`
- 预取最近 10 帧 (fire-and-forget)
- `setDate(d)`: cache 优先, miss 则 SWR fetch (3 次自动重试) → zod parse → cache.put
- 帧失败: `frame` 保留上一次值, status='frame-error', error=date

#### `useTimelinePlayer`

```typescript
export type PlaySpeed = 1 | 2 | 4;

const DURATIONS: Record<PlaySpeed, number> = { 1: 300, 2: 150, 4: 80 };

export interface UseTimelinePlayerOptions {
  dates: string[];                              // 升序
  currentDate: string | undefined;
  onAdvance: (next: string) => void;
  onPrefetchNeeded?: (dates: string[]) => void; // 仅 play 时调用
}

export interface UseTimelinePlayerResult {
  playing: boolean;
  speed: PlaySpeed;
  animationDuration: number;                    // DURATIONS[speed]
  play: () => void;                             // 末尾 → reset 到 dates[0]
  pause: () => void;
  stop: () => void;                             // → dates[last] + pause
  setSpeed: (s: PlaySpeed) => void;
}
```

**关键不变量**:
- empty dates → 所有方法 no-op (容灾防御)
- speed 切换 → 重启 setInterval
- 末尾自动 pause (无循环)
- play() 触发时 `onPrefetchNeeded(未来 5 帧)`

### 4.4 纯函数

```typescript
// lib/snapshotsCache.ts
export function createLRU<V>(max: number): {
  get(key: string): V | undefined;
  put(key: string, value: V): void;
  has(key: string): boolean;
  size(): number;
};

// lib/trailGradient.ts
export function trailOpacity(i: number, total: number): number;
// i=0 (最旧) → 0.05; i=total-1 (最近) → 0.4

export function pickTopByComposite(themes: Theme[], n: number): Set<string>;
// 按 composite 降序, null 排末尾, 返回 themeId set

export function buildTrails(
  frames: SnapshotFrame[],
  topN: Set<string>,
): Map<string, Array<{x: number; y: number; opacity: number; date: string}>>;
// 仅返回 topN 主题的尾迹路径
```

### 4.5 组件接口

#### `TimelineControls`

```typescript
export interface TimelineControlsProps {
  dates: string[];
  currentDate: string;
  onDateChange: (date: string) => void;

  playing: boolean;
  speed: PlaySpeed;
  onPlay: () => void;
  onPause: () => void;
  onStop: () => void;
  onSpeedChange: (s: PlaySpeed) => void;

  showTrails: boolean;
  onToggleTrails: (v: boolean) => void;

  disabled?: boolean;  // status !== 'ready' 时为 true
}
```

实现要点:
- 滑块: `<input type="range">` (a11y + 移动端原生体验)
- icons: lucide-react (`Play`, `Pause`, `Square`)
- 移动端布局: `useMediaQuery('(max-width: 768px)')` 切换

#### `RotationScatterWithTrails`

```typescript
export interface RotationScatterWithTrailsProps {
  themes: Theme[];                  // 当前帧 14 主题
  trailFrames: SnapshotFrame[];     // 升序, 含当前帧, ≤11 帧
  topThemeIds: Set<string>;         // Top-5 by composite
  animationDuration: number;        // 透传给 Recharts
  showTrails: boolean;
}
```

实现要点:
- 主气泡层: `<Scatter data={themes}>` 复用 Phase A 渲染逻辑
- 尾迹层 (showTrails=true): 对 topThemeIds 中的每个主题, 1 个独立 `<Scatter>` (10 个历史点, opacity 渐变, isAnimationActive=false, tooltipType="none")
- `useMemo` 缓存 buildTrails 结果

#### `RotationTimelinePlayer` (顶层装配, ~50 行)

```typescript
export interface RotationTimelinePlayerProps {
  fallbackThemes: Theme[];          // 来自 DataProvider, 用于 index-error
}
```

容灾分支:
- `status === 'index-error'`: 黄横幅 "时间轴数据不可用, 正在重试..." + `<RotationScatter themes={fallbackThemes} />`
- `status === 'loading'`: Tailwind animate-pulse placeholder (`<div className="animate-pulse h-96 bg-muted rounded">`)
- `status === 'frame-error'`: 黄横幅 "帧 {error} 不可用, 显示上一帧" + 正常渲染上一帧
- `status === 'ready'`: 正常装配

---

## 5. 容灾设计

### 5.1 失败矩阵

| 失败点 | 触发 | UI 响应 | 数据响应 | 状态 |
|--------|------|---------|---------|------|
| 索引加载 | snapshots-index.json 404/parse/网络 | 黄横幅 "时间轴数据不可用, 正在重试..." + 控件 disabled | Fall back `fallbackThemes` (DataProvider) | `index-error` |
| 当前帧 | snapshots/<date>/themes.json 404/parse | 黄横幅 "帧 YYYY-MM-DD 不可用, 显示上一帧" | 保留上一次成功 `frame`, 不写 cache | `frame-error` |
| 预取 | play() 时预取请求失败 | 无 UI 提示 (静默) | 不写 cache, console.warn (dev) | `ready` 不变 |

### 5.2 SWR 自动重试策略

| 资源 | 重试次数 | 间隔 | 行为 |
|------|---------|------|------|
| `snapshots-index.json` | ∞ (SWR 默认) | 5s | 后台静默重试, 成功后横幅自动消失 |
| `snapshots/<date>/themes.json` | 3 | 5s/10s/20s | 3 次失败后 frame-error; 用户切换其他 date 不阻塞 |
| 预取帧 | 3 (同上) | - | 失败静默 |

### 5.3 状态机

```
loading → [index OK?] → ready ⟷ frame-error (按 date 切换)
                ↓
           index-error (终态, SWR 后台 retry)
```

不变量:
- `frame-error` 时 `frame` 保留上一次值 (不清空)
- `index-error` 只发生一次 (SWR 后台 retry 成功后转 ready)

---

## 6. 测试策略

### 6.1 测试分布 (~26 测试)

| 层级 | 数量 | 工具 | 范围 |
|------|------|------|------|
| 纯函数单测 | ~8 | vitest | `snapshotsCache`, `trailGradient` (LRU 边界, opacity 边界, pickTopByComposite null 处理, buildTrails 结构) |
| Hooks 单测 | ~10 | renderHook + MSW + vi.useFakeTimers | `useSnapshotsTimeline` (索引 OK/404/帧 500/cache 命中/预取), `useTimelinePlayer` (推进/末尾/速度切换/empty no-op) |
| 组件单测 | ~5 | RTL | `TimelineControls` (滑块/▶⏸⏹/速度/尾迹/disabled), `RotationScatterWithTrails` (尾迹 series 数/showTrails 切换) |
| 集成 | ~3 | RTL + MSW | banner (index-error / frame-error), trails toggle 视觉效果, happy path smoke (点 ▶ 看滑块变化) |

### 6.2 测试粒度原则

- **去重**: hook 测试已覆盖"play 推进/末尾 pause/速度切换", 集成不再重复
- **集成只测 hook 无法测的**: 容灾 banner、Top-5 尾迹渲染、端到端用户路径
- **不测**: Recharts 内部 (mock 沿用 Phase A), 真实网络, 视觉回归

### 6.3 测试基础设施

- `tests/mocks/handlers.ts` 添加 2 个 MSW route (index + frame)
- `__fixtures__/snapshots.ts` 工厂函数: `mkIndex(n)`, `mkFrame(date, n=14)`
- `vitest.setup.ts` 添加 `matchMedia` polyfill (10 行)
- Recharts mock 沿用 Phase A `RotationScatter.test.tsx` 风格

### 6.4 不测试 (YAGNI)

- Recharts 内部 SVG 渲染
- `matchMedia` 实际媒体查询
- 真实 snapshots 文件 (用 MSW)
- 视觉回归

---

## 7. 文件清单与代码量

### 7.1 新建 (11 个)

| 路径 | 类型 | 源码 | 测试 |
|------|------|------|------|
| `types/snapshots.ts` | types + zod | 30 | - |
| `lib/snapshotsCache.ts` | 纯函数 LRU | 40 | 50 |
| `lib/trailGradient.ts` | 纯函数 (opacity/topN/buildTrails) | 60 | 80 |
| `hooks/useSnapshotsTimeline.ts` | hook | 120 | 150 |
| `hooks/useTimelinePlayer.ts` | hook | 80 | 120 |
| `components/rotation/TimelineControls.tsx` | UI | 120 | 100 |
| `components/rotation/RotationScatterWithTrails.tsx` | UI | 80 | 80 |
| `components/rotation/RotationTimelinePlayer.tsx` | 装配 | 50 | 120 |
| `tests/mocks/handlers.ts` | MSW (扩展) | +20 | - |
| `__fixtures__/snapshots.ts` | 测试工厂 | 40 | - |

**合计**: 源码 ~620 行, 测试 ~700 行 (~26 测试), 测试源码比 1.13

### 7.2 修改 (2 个)

| 路径 | 改动 |
|------|------|
| `pages/RotationPage.tsx` | `<RotationScatter>` → `<RotationTimelinePlayer fallbackThemes={themes}/>` (1 行替换) |
| `package.json` | 若 `msw` 未安装则新增 (devDependency) |

### 7.3 依赖检查

- `zod`, `swr`, `recharts`, `lucide-react`: 已有
- `msw@^2`: 需检查 (项目已用 vitest 7+ 与之兼容)

---

## 8. 实施计划 (9 个 TDD 任务)

```
Task 1: 类型 + zod schema + fixture
        Files: types/snapshots.ts, __fixtures__/snapshots.ts
Task 2: snapshotsCache (LRU 纯函数 + 3 单测)
Task 3: trailGradient (opacity/pickTopByComposite/buildTrails + 5 单测)
Task 4: useSnapshotsTimeline + MSW handler + 6 hook 测试
Task 5: useTimelinePlayer + fake timer 6 测试
Task 6: TimelineControls + 5 RTL 测试 (含 matchMedia polyfill)
Task 7: RotationScatterWithTrails + 3 测试 (复用 recharts mock)
Task 8: RotationTimelinePlayer 装配 + 3 集成测试 (banner/trails/smoke)
Task 9: RotationPage 接入 + 端到端 smoke + npm test 全绿
```

每任务 1 commit, 适合 subagent-driven-development 同会话调度。

---

## 9. 风险与已知未知

| 风险 | 缓解 |
|------|------|
| MSW v2 集成 | 项目使用 vitest 7+ 兼容; 若未安装 Task 1 中先 `npm i -D msw` |
| Recharts 5 主题 × 10 历史点 = 50 节点 + 14 主气泡渲染性能 | jsdom 测试不实际渲染 (mock); 真实浏览器在 Task 9 完成后手测验证 |
| matchMedia 在 jsdom 不存在 | vitest.setup.ts polyfill 10 行 |
| 速度切换重启 setInterval 的边界条件 | useTimelinePlayer 单测覆盖 |
| Top-5 按 composite 排序的 null 处理 | pickTopByComposite 纯函数单测覆盖 |

---

## 10. 验收标准

完成后 `/rotation` 页面满足:

1. ✅ 默认显示最新一帧 (2026-06-15 实时归档)
2. ✅ 滑块拖动立即切换帧 (cache 命中无延迟; miss 走 SWR + 3 次重试)
3. ✅ ▶ 自动播放, 按 1x/2x/4x 速度推进, 末尾自动停止
4. ✅ ⏹ 重置到最新帧 + pause
5. ✅ 尾迹勾选 OFF (默认) → 仅 14 主气泡; ON → Top-5 尾迹叠加 (opacity 0.05→0.4)
6. ✅ index-error → 黄横幅 + RotationScatter fallback
7. ✅ frame-error → 黄横幅 + 上一帧保留
8. ✅ 移动端 (<768px) 双层堆叠布局
9. ✅ `npm test -- --run` 全绿 (~61 个 frontend 测试)
10. ✅ `npm run build` 无 TS 错误
