# 主题轮动板块 设计文档

> 版本: 1.0
> 日期: 2026-06-16
> 状态: 待审阅
> 上游 spec: `docs/superpowers/specs/2026-06-05-etf-radar-design.md` (v1 预留 RadarTabs 中标注的 "主题轮动 v2 预留")

---

## 0. 文档导览

| 章节 | 内容 | 适合谁先看 |
|------|------|----------|
| 1 | 目标 & 非目标 | 所有人 |
| 2 | 架构 (路由 + 组件树 + 数据流) | 前端 |
| 3 | Phase A 瞬时多窗口散点图 (现在做) | 前端 |
| 4 | Phase B 时间轴回放 (snapshots ≥20 天后) | 前端 + 后端 |
| 5 | 测试策略 | 前端 + QA |
| 6 | 实施风险 & 依赖 | 评审 |
| 附录 A | 决策摘要 (Q1-Q6) | 评审 |
| 附录 B | YAGNI 边界 | 评审 |
| 附录 C | 未来路线图 | 产品 |

---

## 1. 目标 & 非目标

### 1.1 Goals

1. **决策辅助** — 用户访问 `/rotation` 一眼看出当前市场轮动格局: 哪些主题在崛起 (左上)、哪些在退潮 (右下)、谁持续强势 (右上)
2. **复盘工具 (Phase B)** — 同页面提供"轨迹回放"模式, 14 主题在过去 30/60 天的散点位置变化轨迹
3. **零数据等待启动** — Phase A 仅依赖现有 `themes.json` 即可上线, Phase B 在 snapshots 累积 ≥20 天后激活
4. **保持 KISS** — 不引入新数据源, 不扩展 backend schema, 纯前端组合

### 1.2 Non-Goals (YAGNI)

- ❌ 不做"主题预测"算法 (机器学习 / 信号灯)
- ❌ 不做"买入推荐" (合规风险 + 不是产品定位)
- ❌ 不做主题级别的实时推送/通知 (v3 候选)
- ❌ 不在 Phase A 引入新 backend 字段
- ❌ 不做"自定义主题分组"功能

---

## 2. 架构

### 2.1 路由

引入 `react-router-dom@7` (~30KB gzipped), 使用 **HashRouter** 避免 GitHub Pages SPA fallback hack:

```
App.tsx
├─ <DataProvider>            (复用)
│   └─ <HashRouter>
│       ├─ <Header />        (复用, 内含 <NavTabs />)
│       ├─ <StaleBanner />   (复用)
│       ├─ <Routes>
│       │   ├─ Route path="/"          → <RadarPage />     (现有主页改造成路由组件)
│       │   └─ Route path="/rotation"  → <RotationPage />  (新增)
│       └─ </Routes>
```

URL 示例:
- 主页: `https://im47.cn/etf-radar/#/`
- 轮动: `https://im47.cn/etf-radar/#/rotation`

零部署配置, 用户直接刷新可访问。

### 2.2 组件树 (新增)

```
src/
├─ pages/
│   └─ RotationPage.tsx                ← 路由顶层组件 (统筹加载/错误状态)
├─ components/rotation/
│   ├─ RotationScatter.tsx             ← 散点图主组件 (Recharts ScatterChart)
│   ├─ QuadrantLegend.tsx              ← 四象限色彩图例 + 解读
│   ├─ ThemeBubbleTooltip.tsx          ← hover 弹卡片
│   └─ RotationTimeline.tsx            ← Phase B 时间滑块 (Phase A 暂留占位)
├─ lib/
│   └─ rotation.ts                     ← 数据派生纯函数
└─ types/
    └─ rotation.ts                     ← RotationPoint / Quadrant 类型
```

### 2.3 数据流

**Phase A**:
```
useDataContext().themes  →  themesToRotationPoints(themes)  →  RotationScatter
```
全部纯前端派生, 无新增网络请求。

**Phase B**:
```
useSWR<SnapshotsIndex>('/latest/snapshots-index.json')
  ↓
按需 lazy fetch /snapshots/<date>/themes.json (LRU 缓存 20 帧)
  ↓
按时间帧切换 RotationScatter 的 data prop
```

### 2.4 依赖增量

| 包 | 用途 | gzipped |
|----|------|---------|
| `react-router-dom@7` | HashRouter / Link / useNavigate | ~30 KB |
| (无其他) | Recharts/zod/swr 已有 | - |

---

## 3. Phase A — 瞬时多窗口散点图

### 3.1 数据派生 (纯函数)

`src/lib/rotation.ts`:

```ts
import type { Theme } from '@/types/themes';

export type Quadrant = 'leading' | 'rising' | 'lagging' | 'fading';

export interface RotationPoint {
  themeId: string;
  themeName: string;
  x: number;         // theme.strength.long  (1-99)
  y: number;         // theme.strength.short (1-99)
  size: number;      // theme.strength.composite (1-99)
  quadrant: Quadrant;
  tags: string[];
}

const QUADRANT_THRESHOLD = 50;  // 中线

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

**特点**: 100% 纯函数, 无副作用, 易测试。

### 3.2 Recharts 配置

```tsx
<ResponsiveContainer width="100%" height={500}>
  <ScatterChart margin={{ top: 24, right: 24, bottom: 48, left: 24 }}>
    <CartesianGrid strokeDasharray="3 3" />
    <XAxis type="number" dataKey="x" domain={[0, 100]}
           label={{ value: '长期强度 (60d)', position: 'bottom' }} />
    <YAxis type="number" dataKey="y" domain={[0, 100]}
           label={{ value: '短期强度 (1d)', angle: -90, position: 'left' }} />

    {/* 中线 */}
    <ReferenceLine x={50} stroke="#94a3b8" strokeDasharray="3 3" />
    <ReferenceLine y={50} stroke="#94a3b8" strokeDasharray="3 3" />

    {/* 四象限背景色 (淡 5% opacity) */}
    <ReferenceArea x1={50} x2={100} y1={50} y2={100} fill="#10b981" fillOpacity={0.05} />
    <ReferenceArea x1={0}  x2={50}  y1={50} y2={100} fill="#3b82f6" fillOpacity={0.05} />
    <ReferenceArea x1={0}  x2={50}  y1={0}  y2={50}  fill="#6b7280" fillOpacity={0.05} />
    <ReferenceArea x1={50} x2={100} y1={0}  y2={50}  fill="#ef4444" fillOpacity={0.05} />

    {/* 数据点 */}
    <Scatter data={points} shape={<ThemeBubble />}>
      {points.map(p => <Cell key={p.themeId} fill={QUADRANT_COLORS[p.quadrant]} />)}
    </Scatter>

    <Tooltip content={<ThemeBubbleTooltip />} cursor={{ strokeDasharray: '3 3' }} />
  </ScatterChart>
</ResponsiveContainer>
```

**气泡大小映射**: `radius = 8 + (composite / 99) * 12` → 范围 8-20px。

**主题名标签**: `<LabelList dataKey="themeName">`, 字号 11px, 偏移 16px 避免遮挡。

### 3.3 QUADRANT_COLORS 常量

```ts
// src/lib/rotation.ts
export const QUADRANT_COLORS: Record<Quadrant, string> = {
  leading: '#10b981',  // emerald-500
  rising:  '#3b82f6',  // blue-500
  lagging: '#6b7280',  // gray-500
  fading:  '#ef4444',  // red-500
};
```

图例与散点共用此常量, 防止偏差。

### 3.4 Tooltip 内容

hover 弹卡片显示完整数据:

```
存储芯片
─────────────────────
🏆 综合排名: #1 / 14    composite 97
📈 短期(1d):   #1       strength.short 99
📊 中期(5d):   #1       strength.mid 93
📉 长期(60d):  #1       strength.long 99
─────────────────────
1d:  -0.17%   5d: +15.29%
20d: +18.95%  60d: -
YTD: +85.09%
─────────────────────
标签: DRAM, NAND, 半导体
🇺🇸 主 ETF: DRAM (+ SOXX, SMH)
[点击查看 A 股映射 →]
```

点击气泡 → `navigate('/?theme=<id>')`, 回主页选中该主题 (复用现有 ThemeDetail 弹窗)。

### 3.5 QuadrantLegend

散点图下方:

```
🟢 持续强势 (Leading)  | 长期&短期都强 — 趋势龙头, 续航空间需评估
🔵 新崛起 (Rising)     | 长期弱但短期突涨 — 早期信号, 关注资金流入
🔴 退潮 (Fading)      | 长期强但短期跌 — 警惕高位回调
⚫ 持续弱势 (Lagging) | 长期&短期都弱 — 暂观望
```

明确解读 + 风险提示, 避免被误读为投资建议。

### 3.6 响应式 & 状态

**移动端 (max-width: 768px)**:
- 散点图高度 500 → 360
- 标签字号 11 → 9
- Tooltip 触发方式: hover → click

**加载/错误状态** (复用 DataProvider):
- `isLoading` → `<Skeleton className="h-[500px]" />`
- `error` → `<Alert variant="destructive">数据加载失败, 已显示上次成功快照</Alert>`
- `themes.length === 0` → `<Alert>暂无主题数据</Alert>`

---

## 4. Phase B — 时间轴回放 (snapshots ≥20 天后激活)

### 4.1 数据需求

新增 `data/latest/snapshots-index.json`:

```json
{
  "schema_version": "1.0",
  "generated_at": "2026-07-15T07:30:00+08:00",
  "snapshots": [
    {"date": "2026-06-16", "themes_path": "snapshots/2026-06-16/themes.json"},
    {"date": "2026-06-17", "themes_path": "snapshots/2026-06-17/themes.json"}
  ]
}
```

**后端改动**: `backend/src/output/archiver.py` 增加 `write_snapshots_index()` 函数,
`cn-eod-archive.yml` 末尾扫描 `data/snapshots/` 重新生成 index → 写 `data/latest/snapshots-index.json`。约 20 行 Python + 5 行 workflow。

### 4.2 与 data-archive 分支的关系

之前讨论的 X1 方案 (snapshots 搬到 `data-archive` 分支) 与 Phase B 直接冲突 — 前端无法 fetch data-archive 内容。

**本 spec 决策**: **暂不实施 X1**, snapshots 保留在 main 分支。

理由:
- Phase B 上线 ≥20 天后, 离当下还远
- 真到 Phase B 实施时再权衡 X1 (raw URL fetch / deploy 时复制 / 推迟 X1)
- 当前优先 Phase A 高 ROI 工作

### 4.3 UI 设计

复用 Phase A 散点图, 上方加时间滑块控件:

```
┌─────────────────────────────────────┐
│   ▶ ⏸ ⏹  [────●───────] 2026-07-08  │  ← 播放控件 + 时间滑块
│       速度 [1x ▼]   显示尾迹 [✓]    │
├─────────────────────────────────────┤
│         (同 §3 散点图)              │
│       带尾迹 (淡色历史位置)         │
└─────────────────────────────────────┘
```

**交互**:
- 滑块拖动 → 实时切换数据帧
- ▶ 播放 → 每 500ms 推进一帧 (速度可调 1x/2x/4x)
- 尾迹勾选 → 显示该主题过去 10 天的散点位置 (opacity 0.2)

### 4.4 实现要点

- **按需 lazy load + LRU 缓存 (max 20 帧)**: 全量 fetch 60 天 themes.json ≈ 600KB 太大
- **Recharts 帧切换**: Scatter `data` 数组替换即触发 react diff, 平滑过渡用 `animationDuration={300}`
- **尾迹实现**: 同一 ScatterChart 内多个 `<Scatter>` 序列, z-index 由旧到新

### 4.5 激活条件

`snapshots-index.json.snapshots.length < 20` →
`<RotationTimeline>` 占位显示 "数据积累中, 距离激活还需 X 天 (今日 / 20)", 散点图仍正常显示当前数据。

### 4.6 Phase B Schema 验证

`src/types/snapshotsIndex.ts` 增加 zod schema, 复用 DataProvider 同款 fetchAndParse 模式, 失败由 SWR 暴露错误。

---

## 5. 测试策略

复用 `vitest + @testing-library/react` 栈, 不引入新依赖。

### 5.1 单元测试 (纯函数, 目标覆盖 100%)

`tests/lib/rotation.test.ts`:

```ts
describe('classifyQuadrant', () => {
  it.each([
    [60, 60, 'leading'],
    [30, 60, 'rising'],
    [30, 30, 'lagging'],
    [60, 30, 'fading'],
    [50, 50, 'leading'],   // 边界: 中线归入右上
    [49, 49, 'lagging'],
  ])('strength.long=%i, short=%i → %s', (x, y, expected) => { ... });
});

describe('themesToRotationPoints', () => {
  it('maps strength fields correctly', ...);
  it('preserves theme order from input', ...);
  it('handles empty themes array', ...);
});
```

### 5.2 组件测试

`tests/components/rotation/RotationScatter.test.tsx`:
- 给定 14 themes mock → 渲染 14 个气泡 (用 `data-testid` 定位)
- ReferenceLine 在 x=50, y=50
- 4 象限背景色 (snapshot 或 style 断言)
- Tooltip hover 显示主题名 (fireEvent.mouseEnter)
- 点击气泡触发 `navigate('/?theme=<id>')` (mock useNavigate)

`tests/components/rotation/QuadrantLegend.test.tsx`:
- 4 条图例文本完整渲染
- 颜色 swatch 与 QUADRANT_COLORS 一致

`tests/pages/RotationPage.test.tsx`:
- isLoading=true → Skeleton 渲染
- error → Alert 渲染
- 正常数据 → 散点图 + 图例都渲染

### 5.3 集成测试 (路由)

`tests/router.test.tsx`:
- HashRouter `#/` → RadarPage 渲染
- HashRouter `#/rotation` → RotationPage 渲染
- NavTabs 点击切换 URL

### 5.4 不做

- ❌ 视觉回归 (@vitest/browser + Playwright 截图对比) — ROI 太低
- ❌ E2E (Playwright) — 现有 zod runtime + 组件测试已够

### 5.5 Phase B 测试增量 (占位)

Phase B 实施前补充:
- 时间滑块 React state 切换
- 播放/暂停按钮状态机
- snapshots-index.json fetch + zod 解析

---

## 6. 实施风险 & 依赖

### 6.1 风险

| # | 风险 | 影响 | 缓解 |
|---|------|------|------|
| R1 | react-router-dom 引入后 bundle +30KB | bundle 651KB → 681KB | gzip 后仅 +10KB, 可接受 |
| R2 | 14 标签可能在散点图上重叠 | 可读性下降 | LabelList 偏移 + collision 检测; 若仍乱, 改用 hover-only label |
| R3 | 移动端散点图体验差 | 用户流失 | 降高度 + click tooltip + 必要时显示主题列表替代 |
| R4 | Phase B `snapshots-index.json` 与 X1 方案冲突 | Phase B 阻塞 | 本 spec 已决策暂缓 X1; 真到 Phase B 时再权衡 |
| R5 | 当前数据 `composite` 极值集中 (90-99) → 气泡大小同质化 | 视觉编码失效 | 改用 `min-max normalize` 拉开差异 |

### 6.2 外部依赖

- 数据源: `themes.json` schema 已稳定 (v1 已固化), 本 spec 不要求改动
- 数据 freshness: 复用 `<StaleBanner>`, 若数据过期同步告警

---

## 附录 A: 决策摘要 (Q1-Q6)

| # | 问题 | 选择 | 理由 |
|---|------|------|------|
| Q1 | 功能目的 | 决策辅助 + 复盘工具 | 排除 "预警系统" YAGNI |
| Q2 | 时间维度 | 渐进式 Phase A → B | 零数据等待启动 |
| Q3 | 展现形式 | 散点象限图 | KISS, 视觉冲击最强 |
| Q4 | 坐标轴 | X=long, Y=short (中线 50) | 散户零学习成本 |
| Q5 | 视觉编码 | 象限色 + composite 大小 | 平衡叙事清晰 + 信息密度 |
| Q6 | 集成位置 | HashRouter 独立路由 `/rotation` | 现代 SPA, GitHub Pages 兼容 |

## 附录 B: YAGNI 边界

- 主题预测算法
- 自动买入信号
- 实时推送/通知
- 自定义主题分组
- backend schema 扩展 (Phase A)
- 视觉回归测试
- E2E 测试

## 附录 C: 未来路线图

| 版本 | 内容 | 触发条件 |
|------|------|----------|
| v2.0 Phase A | 本 spec 范围 | 立即可做 |
| v2.5 Phase B | 时间轴回放 | snapshots ≥20 天 |
| v3.0 | 主题级实时预警 | 用户主动反馈需求 |
| v3.x | 自定义主题分组 | 数据证明用户需要 |
