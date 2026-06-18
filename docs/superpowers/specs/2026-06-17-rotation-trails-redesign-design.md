# RRG 轨迹视图重构设计 (Rotation Trails Redesign)

**Date**: 2026-06-17
**Status**: Draft — pending user review
**Author**: Brainstorming session with user

## 1. 背景与目标

### 1.1 问题陈述

用户使用 RRG (Relative Rotation Graph) 主题轮动图时反馈：

> "1x 动画下完全看不出来谁在移动以及移动关系。期望选中一个主题时可以看到该主题在过去 15 个交易日的变化情况。"

经诊断，问题不在"速度太快"——而在**动画范式本身**：多个主题在 30Hz 视觉刷新下同时变化，人眼天然无法横向比较运动差异。调速治标不治本。

### 1.2 目标

1. **看清谁在移动**：14 个主题的 15 日轨迹同框静态叠加，按当前象限着色，无动画干扰
2. **看清单一主题的详细变化**：单击主题进入粘性聚焦态，该主题轨迹高亮 + 蓝→红渐变 + 日期标签，其他主题灰化为背景
3. **可调节时间窗**：起止滑块控制轨迹长度（5~60 天，默认 10）

### 1.3 非目标 (YAGNI)

- 不保留动画播放器（删除 Phase B 的 `RotationTimelinePlayer` + `useTimelinePlayer`）
- 不做主题聚类 / 自动分组（14 条按象限色已足够辨认）
- 不绑 URL（trailRange 与 focusedThemeId 仅本地 state，不持久化、不可分享）
- 不做"静止主题"视觉退化标签（实际数据是否会出现这种情况尚未验证）
- 不做视觉回归 / screenshot diff 工具

## 2. 用户原始决策（来自 brainstorming）

| 维度 | 选择 |
|---|---|
| Q1 主方向 | B+C 混合：默认全主题叠加 + 单击进入单主题聚焦 |
| Q2 C 布局 | 全显 14 条按当前象限着色 |
| Q3 交互入口 | 单击粘性聚焦 + 显式"详情页 →"按钮 |
| Q4 信息密度 | 标准（轨迹 + 信息面板 + ETF chips） |
| Q5 动画处理 | 删 `useTimelinePlayer`，时间轴变"轨迹起止滑块" |
| 测试基础设施 | 本次引入 Playwright + e2e + CI |

## 3. 架构

### 3.1 顶层组件树

```
RotationPage
  └─ RotationTrailsOverlay (新, 主容器)
      ├─ useTrailRange (state: { startOffset, endOffset })
      ├─ useFocusedTheme (state: focusedId | null)
      ├─ TrailRangeSlider (受控)
      ├─ RotationScatterWithTrails (重写: 14 主题静态叠加 + 聚焦态视觉)
      └─ FocusedThemePanel (focusedId 非空时挂载, 右上 absolute / mobile 底 sheet)
```

### 3.2 关键设计决策

| 决策 | 选择 | 理由 |
|---|---|---|
| 渲染方式 | 单一扁平 Scatter series + Cell 数组着色 | 14 个独立 series 在 setFocus 时全部重渲染浪费 |
| 聚焦交互 | 粘性 toggle（单击 = 切换） | hover 在 mobile 无效；粘性更克制（用户决定看哪个） |
| hover 行为 | 极简 tooltip（仅 themeName + quadrant），100ms delay | 避免横扫散点时闪烁 |
| 详情页跳转 | 仅在 `FocusedThemePanel` 的显式按钮 | 解耦"查看"与"跳走" |
| ETF chips | 装饰性（仅显示） | 持仓页存在性未验证，YAGNI |
| trailRange 持久化 | 不持久化（每次默认 -10） | 探索性浏览，分享需求弱 |
| focusedId 进 URL | 否（纯本地 state） | 同上 |
| 静止主题视觉处理 | 不做（密集点堆叠即原始呈现） | 真实数据未验证，YAGNI |
| 性能护栏 | `React.memo` + `useMemo` + 扁平单 series | 14 series × 15 frame 在 setFocus 时不应全重渲染 |

## 4. 组件与文件清单

### 4.1 新增

```
frontend/src/components/rotation/
  RotationTrailsOverlay.tsx        (~80 行, 主容器, 装配 slider + scatter + panel)
  TrailRangeSlider.tsx             (~50 行, 双滑块, max 自动 clamp 到快照数)
  FocusedThemePanel.tsx            (~70 行, 浮窗, 主题信息 + ETF chips + 详情按钮)

frontend/src/hooks/
  useTrailRange.ts                 (~40 行, range state + clamp + reset)
  useFocusedTheme.ts               (~50 行, focus state + ESC/外部点击退出 + 主题不存在守卫)

frontend/e2e/
  rotation.spec.ts                 (Playwright 用例: 14 轨迹/聚焦/滑块/ESC)
  fixtures/snapshots/              (15 个测试快照 JSON, 含: 连续/中途新增/中途消失)

frontend/
  playwright.config.ts             (chromium + firefox + webkit, baseURL, dev server)
```

### 4.2 修改

```
frontend/src/components/rotation/
  RotationScatterWithTrails.tsx    (92 → ~110 行, 重写: 全主题渲染 + 聚焦态视觉 + memo)
  ThemeBubbleTooltip.tsx           (简化: 仅 themeName + quadrant)

frontend/src/lib/
  trailGradient.ts                 (buildTrails 签名: topThemeIds → opts.themeIds; 默认全主题; 支持 dayRange 截取)

frontend/src/pages/
  RotationPage.tsx                 (RotationTimelinePlayer → RotationTrailsOverlay)

frontend/package.json              (+@playwright/test, +scripts: test:e2e, test:e2e:install)

.github/workflows/ci.yml           (新增 e2e job: setup-node + playwright install + npm run test:e2e)
```

### 4.3 删除

```
frontend/src/components/rotation/
  RotationTimelinePlayer.tsx       (132 行)
  TimelineControls.tsx             (100 行)

frontend/src/hooks/
  useTimelinePlayer.ts             (101 行)

frontend/src/components/rotation/__tests__/
  RotationTimelinePlayer.test.tsx
  TimelineControls.test.tsx (若存在)

frontend/src/hooks/__tests__/
  useTimelinePlayer.test.tsx
```

### 4.4 净变化

- 删除：~333 行实现 + 对应测试
- 新增：~290 行实现 + e2e 基础设施
- **代码净减约 40 行**，外加 e2e 基础设施投资

## 5. 数据流

### 5.1 状态流向

```
DataProvider (现有, 提供 themes + snapshots)
    │
    ▼
RotationPage (现有, 处理 loading/error/empty)
    │
    ▼
RotationTrailsOverlay
    │
    ├─ trailRange = useTrailRange()       # 默认 { startOffset: -10, endOffset: 0 }
    │   └─ TrailRangeSlider 受控          # 用户拖动 → setRange()
    │
    ├─ focusedId = useFocusedTheme()      # 默认 null
    │   └─ RotationScatterWithTrails onClick(themeId) → toggle(themeId)
    │
    └─ trailFrames = useMemo(             # 截取 snapshots 按 trailRange
        () => snapshots.slice(trailRange.startOffset, trailRange.endOffset+1),
        [snapshots, trailRange]
      )
      ↓
      RotationScatterWithTrails
        ├─ buildTrails(trailFrames)       # 默认全主题, themeIds opts 可过滤
        ├─ focusedId 非空时:
        │   - 该主题: stroke 加粗 + 蓝→红渐变 + 起止日期 label
        │   - 其他主题: opacity 0.2 灰化, 轨迹隐藏
        └─ hover (debounce 100ms) → 极简 tooltip
```

### 5.2 Hook 契约

#### `useTrailRange`

```ts
type TrailRange = { startOffset: number; endOffset: number };

interface UseTrailRangeReturn {
  range: TrailRange;
  setRange: (range: TrailRange) => void;
  reset: () => void;
}

// 默认: { startOffset: -10, endOffset: 0 }
// 约束: -60 ≤ startOffset < endOffset ≤ 0
// 越界自动 clamp 到合法范围
```

#### `useFocusedTheme`

```ts
interface UseFocusedThemeOptions {
  validThemeIds: Set<string>;  // 用于守卫: 数据刷新后 id 失效自动退出
}

interface UseFocusedThemeReturn {
  focusedId: string | null;
  setFocused: (id: string | null) => void;
  toggle: (id: string) => void;  // 同 id 再点 = 退出
}

// 副作用:
// - 监听 ESC → setFocused(null)
// - 监听外部点击（非散点 + 非浮窗）→ setFocused(null)
// - useEffect: 当 focusedId 不在 validThemeIds 中 → setFocused(null)
// - 组件卸载时 cleanup 所有监听
```

#### `buildTrails` 改造

```diff
- function buildTrails(
-   frames: SnapshotFrame[],
-   topThemeIds: Set<string>
- ): Map<string, TrailPoint[]>

+ function buildTrails(
+   frames: SnapshotFrame[],
+   opts?: { themeIds?: Set<string> }
+ ): Map<string, TrailPoint[]>
```

- `opts.themeIds === undefined` → 返回全部主题轨迹
- `opts.themeIds === Set([...])` → 仅返回这些主题的轨迹
- opacity 梯度按 frame index 计算（越旧越淡，0.15 → 1.0）

## 6. 视觉规范

### 6.1 主图配色

沿用 `frontend/src/lib/rotation.ts` 现有 `QUADRANT_COLORS`：

| 象限 ID | 含义 | 实际色值 |
|---|---|---|
| `leading` | 强势 | `#10b981` 绿 |
| `rising` | 改善 | `#3b82f6` 蓝 |
| `lagging` | 落后 | `#6b7280` 灰 |
| `fading` | 弱化 | `#ef4444` 红 |

### 6.2 状态切换

| 状态 | 主题当前点 | 主题轨迹 |
|---|---|---|
| 无聚焦 (默认) | r=8, fill=quadrantColor, opacity 1.0 | 浅灰点序, opacity 0.15→1.0 |
| 聚焦该主题 | r=10, stroke 加粗 #000 2px | 蓝→红渐变 (`#1e40af` → `#b91c1c`), **仅起点 + 终点**加日期 label |
| 聚焦其他主题 | r=6, opacity 0.2 | 隐藏 |

### 6.3 FocusedThemePanel 布局

```
┌──────────────────────────────┐
│ AI 主题                    × │
│ 当前象限: 强势              │
│ ─────────────              │
│ 综合强度: 97 / 排名 #1      │
│ 20日涨幅: +32%             │
│ ─────────────              │
│ 关联 ETF (装饰性, 不可点):  │
│   DRAM (primary)  SOXX  SMH│
│ ─────────────              │
│ [查看详情页 →]              │
└──────────────────────────────┘

PC: 右上 absolute, w=280px, 不挤压主图
Mobile: 底部 sheet, w=100%, h=240px, 可下滑关闭
```

### 6.4 TrailRangeSlider

```
轨迹长度: 10 天
[●────────●─────────────] -60   0
   start=-10        end=0
```

- 双滑块组件，受控
- 显示当前 startOffset / endOffset 数值
- max 自动 clamp 到 `snapshots.length`（不允许越界）
- 滑块停在边界时无视觉反馈（YAGNI）

## 7. 错误处理与边界

| 场景 | 行为 |
|---|---|
| `themes.length === 0` | 沿用现有 `<Alert>暂无主题数据</Alert>` |
| `snapshots` 加载失败 | 沿用现有 destructive Alert（DataProvider 层） |
| `snapshots.length === 0` (本地无快照) | 仅画当前点，无轨迹；滑块 disabled |
| 某 frame 缺主题（中途新增主题） | buildTrails 跳过该点，轨迹断点处不连 |
| `trailRange.startOffset` 越界 | `useTrailRange.setRange` 自动 clamp |
| `focusedThemeId` 指向已不存在的主题 | `useFocusedTheme` 守卫自动退出 |
| 单主题 15 天位移接近 0（静止） | 不特殊处理，密集点堆叠即原始呈现 |
| Recharts hover 命中错主题 | 用扁平单 series + Cell 数组着色规避 |

### 7.1 交互边界

- **ESC 键** → 退出聚焦
- **点击 chart 外部空白** → 退出聚焦
- **重复点击同一主题** → toggle 退出
- **拖动 slider 不影响 focusedId**（用户可能想看同一主题的不同时间窗）

### 7.2 性能护栏

```ts
const RotationScatterWithTrails = React.memo(impl, (prev, next) =>
  prev.themes === next.themes &&
  prev.trailFrames === next.trailFrames &&
  prev.focusedId === next.focusedId
);

const trails = useMemo(
  () => buildTrails(trailFrames),
  [trailFrames]
);

// 14 series 扁平为 1 series + Cell.fill 数组
// 避免 setFocus 触发 14 个 series 重渲染
```

### 7.3 hover delay 实现

```ts
// 不引入 lodash, 原生 setTimeout + ref
const hoverTimerRef = useRef<NodeJS.Timeout | null>(null);

const onMouseEnter = (id: string) => {
  if (hoverTimerRef.current) clearTimeout(hoverTimerRef.current);
  hoverTimerRef.current = setTimeout(() => setHoverId(id), 100);
};

const onMouseLeave = () => {
  if (hoverTimerRef.current) clearTimeout(hoverTimerRef.current);
  setHoverId(null);
};
```

## 8. 测试策略

### 8.1 Unit (hooks)

| 文件 | 关键 case |
|---|---|
| `useTrailRange.test.tsx` | 默认 `[-10, 0]` / `setRange` 越界 clamp / `reset` 回默认 |
| `useFocusedTheme.test.tsx` | `setFocused` / `toggle` 同 id 退出 / ESC 退出 / 外部点击退出 / 主题不存在守卫 / 卸载 cleanup |

### 8.2 Unit (lib)

| 文件 | 关键 case |
|---|---|
| `trailGradient.test.ts` (扩展) | `buildTrails` 默认全主题 / `themeIds` opts 过滤 / opacity 梯度递减 / frame 缺主题时跳过 |

### 8.3 Component

| 文件 | 关键 case |
|---|---|
| `TrailRangeSlider.test.tsx` | 受控拖动触发 `onChange` / max 不超快照数 / `startOffset < endOffset` 约束 |
| `FocusedThemePanel.test.tsx` | 渲染 themeName/quadrant/strength/rank/r_20d / ETF chips 列表 / "详情页 →" 按钮调 navigate / × 按钮调 onClose / theme=null 不挂载 |
| `RotationScatterWithTrails.test.tsx` (重写) | 14 主题全画 / 点击散点触发 `onFocus` / hover 100ms 后才显 tooltip / focusedId 非空时其他主题灰化 |
| `RotationTrailsOverlay.test.tsx` | 装配三组件 / state 联动（slider → buildTrails） / focusedId 与 trailRange 独立可变 |

### 8.4 Integration

| 文件 | 关键 case |
|---|---|
| `RotationPage.test.tsx` (改) | data loading skeleton / error alert / 空主题 alert / `RotationTrailsOverlay` 挂载 |
| `router.test.tsx` (改) | 删除 `RotationTimelinePlayer` 相关断言 |

### 8.5 e2e (Playwright)

| 文件 | 用例 |
|---|---|
| `e2e/rotation.spec.ts` | (1) 页面加载后 14 个 scatter 点可见 / (2) 单击 AI 主题 → 浮窗出现 / (3) ESC 退出聚焦 → 浮窗消失 / (4) 拖动滑块 → trail 长度变化 / (5) 点击"详情页 →" → URL 跳到 `/?theme=ai` |

### 8.6 Playwright 配置要点

- Projects: chromium / firefox / webkit
- `webServer`: 启动 `npm run dev`（Vite 默认端口 5173）
- baseURL: `http://localhost:5173`
- `use.video`: `'retain-on-failure'`
- `reporter`: `['html', 'list']`

### 8.7 CI 集成

```yaml
# .github/workflows/ci.yml (新增 e2e job)
e2e:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v6
    - uses: actions/setup-node@v6
      with: { node-version: '24' }
    - run: cd frontend && npm ci
    - run: cd frontend && npx playwright install --with-deps
    - run: cd frontend && npm run test:e2e
    - uses: actions/upload-artifact@v6
      if: failure()
      with:
        name: playwright-report
        path: frontend/playwright-report/
```

### 8.8 vitest fake timer 注意

`hover delay` 测试使用 modern fake timer：

```ts
beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
});
```

避免 observation 9507 记录的 `shouldAdvanceTimeDelta` TS 兼容性坑。

### 8.9 TDD 顺序

1. `useTrailRange`（最纯）
2. `useFocusedTheme`（含 DOM 事件）
3. `trailGradient.buildTrails` 改造
4. `TrailRangeSlider`
5. `FocusedThemePanel`
6. `RotationScatterWithTrails` 重写
7. `RotationTrailsOverlay` 装配
8. `RotationPage` 改造
9. Playwright 基础设施 (config + CI)
10. e2e 用例
11. **最后**：删 `RotationTimelinePlayer` + `useTimelinePlayer` + `TimelineControls` 与对应测试

按此顺序每步绿测，最后一步删旧码时新码已完全替代。

## 9. 验收清单

- [ ] 默认进入 `/rotation` 页面，14 条主题轨迹可见，按象限着色
- [ ] 单击任一主题 → 该主题轨迹高亮 + 蓝红渐变 + 日期 label
- [ ] 其他主题灰化 opacity 0.2
- [ ] 右上角浮窗显示主题名/象限/强度/排名/20日涨幅/ETF chips/详情按钮
- [ ] 点击"详情页 →" → URL 变为 `/?theme=<id>`
- [ ] 点击 × / ESC / 外部空白 → 退出聚焦
- [ ] 拖动起止滑块 → 轨迹长度联动
- [ ] hover 散点 100ms 后显示极简 tooltip
- [ ] 移动端：浮窗变底部 sheet
- [ ] Playwright e2e 在 CI 通过（chromium + firefox + webkit）
- [ ] `RotationTimelinePlayer` / `useTimelinePlayer` / `TimelineControls` 已删除
- [ ] 单元测试全绿

## 10. 风险与缓解

| 风险 | 缓解 |
|---|---|
| Playwright 配置卡壳阻塞功能交付 | Playwright 基础设施作为 Task 9-10 单独立项，前 8 个 Task 可独立交付价值 |
| Recharts 在 14 series 下性能 | 性能护栏（memo + useMemo + 扁平单 series）已设计 |
| 删除 Phase B 动画 player 是不可逆决策 | Git 历史保留；如未来确需可恢复 |
| ETF 持仓页未实现导致 chip 装饰性"哑" | 装饰性即可，不阻塞 |
| 移动端浮窗 UX 退化 | 改为底部 sheet 已纳入设计 |

---

## Appendix A: Brainstorming 决策追溯

| 题 | 用户最终选择 | 时间戳 |
|---|---|---|
| Q1 | B+C 混合 | 1781699312（前 session） |
| Q2 | ① 全显 14 条按象限色 | 1781699731 |
| Q3 | ② 单击粘性聚焦 + 详情按钮（改自 ①） | 1781700155 |
| Q4 | ② 标准（轨迹+信息块+ETF） | 1781699766 |
| Q5 | ① 删 player + 起止滑块 | 1781699820 |
| 测试基础设施 | 本次捆绑引入 Playwright + CI | 用户口头确认 |

## Appendix B: 已驳回的方案

- **方案 hover-only (Q3①)**: 移动端废，ETF chips 操作易丢失
- **K-means 聚类 (Q2③)**: 14 主题不够多，YAGNI
- **保留动画 player 作可选 mode (Q5②)**: 双渲染路径维护成本高
- **trailRange / focusedId 进 URL**: 探索场景，分享需求弱
- **静止主题"无明显轮动"标签**: 数据未验证，YAGNI
- **Playwright 单独立项**: 用户坚持本次捆绑
