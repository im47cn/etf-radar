# 主题轮动象限图分布健康度指标 - 设计文档

**日期**：2026-06-18
**作者**：brainstorming session with user
**状态**：草案，待用户确认
**版本**：v2（基于 123 个历史快照回测后修订）

## 1. 背景与动机

主题轮动象限图（`RotationPage`）以双轨强度算法（百分位 × sigmoid 动量，详见 `backend/src/scoring/strength.py`）生成 X = 长期强度、Y = 短期强度，按固定阈值 50 划分四象限。该设计存在两个边缘失效场景：

- **强趋势市场**：主题挤到对角象限（左下或右上），中间两个象限空置，分类信息密度下降。
- **横盘市场**：主题聚集在中心 (50, 50) 附近，象限分类对噪声极度敏感，轻微数值波动就跨象限。

虽然百分位组件结构上保证了"全部 < 10"或"全部 > 90"的极端值不可能出现，但用户仍可能在分布退化的情况下误读图表。因此引入**分布健康度指标**，向用户暴露当前快照的分类信号质量，避免对低信息量分布做过度解读。

## 2. 设计目标

- 在象限图旁实时展示两个互补的健康度评分：**覆盖度**（quadrant coverage）与**鲁棒度**（boundary robustness）
- 数字 + 档位标签（彩色徽章）的双重编码，1 秒内可读
- 随时间轴聚焦帧自动更新，赋予历史快照可比较的健康度视图
- 阈值基于 123 个历史快照（2026-01 ~ 2026-06）的实测分位数校准，避免拍脑袋默认值
- 仅前端实现，不修改后端 pipeline、数据 schema 或 API 契约
- 可测试、可访问、与现有 Tailwind UI 风格一致

## 3. 指标定义

### 3.1 覆盖度 (Coverage)

四象限主题数的香农熵，反映"分类是否被某一象限主导"。

```
p_i = count_in_quadrant_i / total      # i ∈ {leading, rising, lagging, fading}
H = -Σ p_i × log2(p_i)                  # ∈ [0, 2]
coverage = (H / log2(4)) × 100         # 归一到 0-100
```

数学约定：`p_i = 0` 时，`p_i × log2(p_i) := 0`。

直觉解读：
- 100：四象限主题数完全均匀
- 50：两象限均匀（双极分布）
- 0：全部挤在一个象限

### 3.2 鲁棒度 (Robustness)

距离象限边界线 (x=50 或 y=50) 过近的主题占比的反向比例，反映"象限分类对小幅噪声的抗扰动能力"。

```
EDGE_THRESHOLD = 10                                       # 距边界 < 10 即视为脆弱
fragile_i = (|x_i - 50| < EDGE_THRESHOLD)
         OR (|y_i - 50| < EDGE_THRESHOLD)
robustness = (1 - count(fragile_i) / N) × 100             # 范围 [0, 100]
```

设计动机：用户最初提出的关切是"横盘市场象限分类对噪声敏感"——即少量收益波动就会让主题跨象限。这种脆弱性的直接度量是"有多少主题贴近边界线"，而非"主题离中心多远"（早期方案 Spread 在历史数据中分布过窄，stdev=2.9，实证信息量极低；详见 §10 附录）。

EDGE_THRESHOLD = 10 是首版默认。语义：strength 是 0-99 整数，10 单位约等于"一个交易日内收益波动 ±1% 引发的强度抖动幅度"的保守上界。后续可基于实际波动统计微调。

直觉解读：
- 100：没有主题贴近边界线，所有分类都"远离悬崖"
- 50：一半主题在边界缓冲带内，分类高度脆弱
- 0：所有主题都在边界附近，象限标签几乎无意义

### 3.3 档位切分

阈值基于 123 个历史快照的实测分位数（详见 §10）：

| 档位 | Coverage | Robustness | 颜色 | 含义 |
|---|---|---|---|---|
| 健康 (healthy) | ≥ 80 (≥ P50) | ≥ 77 (≥ P50) | green | 优于历史中位水平 |
| 警示 (caution) | 74–80 (P25–P50) | 69–77 (P25–P50) | amber | 处于历史下四分位 |
| 失衡 (imbalanced) | < 74 (< P25) | < 69 (< P25) | red | 罕见低分，分类高度可疑 |
| 数据不足 (insufficient) | N < 2 | N < 1 | gray | 主题数不足以计算 |

设计逻辑：用历史 P25/P50 作为档位切分点，意味着每档约对应"25% 健康、25% 警示、50% 失衡及以上"的历史频率。这让档位拥有数据驱动的可解释性——"失衡"意味着"分类质量低于历史 25% 的快照"，而非任意拍脑袋的阈值。

阈值可在未来运营中调整，但应同步更新本文档的 P25/P50 引用。

### 3.4 边界处理

| 场景 | Coverage | Robustness |
|---|---|---|
| `themes.length === 0` | grade = 'insufficient', score = 0 | grade = 'insufficient', score = 0 |
| `themes.length === 1` | grade = 'insufficient', score = 0 | 正常计算（单点的脆弱度 0 或 100 都有意义） |
| `themes.length >= 2` | 正常计算 | 正常计算 |

## 4. 架构与数据流

### 4.1 计算位置：纯前端实时

| 维度 | 前端实时（采纳） | 后端预计算（拒绝） |
|---|---|---|
| 时间轴联动 | 滑动时自动随当前帧重算 | 每个快照需新字段，schema 变更 |
| 计算成本 | O(N), N ≈ 10–20，<1ms | 占用 pipeline 时间 |
| 改动面 | 前端 3 个新文件 + 1 个修改 | backend models + pipeline + schema + tests + 前端 |
| 性质判断 | UI 解读层指标，非业务核心数据 | — |

### 4.2 数据流

```
useSnapshotsTimeline()
   └─ currentFrame  (随时间轴变动)
        └─ frame.themes
              └─ computeRotationHealth(themes)        ← 新增纯函数
                    └─ { coverage: {score, grade}, robustness: {score, grade} }
                          └─ <RotationHealthBar />    ← 新增展示组件
```

### 4.3 文件结构

```
frontend/src/
├── types/
│   └── rotation.ts                                ← 修改: 追加 HealthGrade / HealthScore 类型
├── lib/
│   ├── rotation.ts                                (现有, 不动)
│   ├── rotationHealth.ts                          ← 新增
│   └── __tests__/
│       └── rotationHealth.test.ts                 ← 新增
├── components/rotation/
│   ├── RotationHealthBar.tsx                      ← 新增
│   └── __tests__/
│       └── RotationHealthBar.test.tsx             ← 新增
└── pages/
    ├── RotationPage.tsx                           ← 修改: 计算并渲染
    └── __tests__/
        └── RotationPage.test.tsx                  ← 修改: 追加 3-4 个 case
```

### 4.4 类型契约

新增到 `frontend/src/types/rotation.ts`：

```ts
export type HealthGrade = 'healthy' | 'caution' | 'imbalanced' | 'insufficient';

export interface HealthMetric {
  score: number;   // 0-100, integer
  grade: HealthGrade;
}

export interface HealthScore {
  coverage: HealthMetric;
  robustness: HealthMetric;
}
```

### 4.5 模块 API

`frontend/src/lib/rotationHealth.ts`：

```ts
export const EDGE_THRESHOLD = 10;

export function computeCoverage(points: RotationPoint[]): number;
export function computeRobustness(points: RotationPoint[]): number;
export function gradeCoverage(score: number, n: number): HealthGrade;
export function gradeRobustness(score: number, n: number): HealthGrade;
export function computeRotationHealth(themes: Theme[]): HealthScore;
```

`computeRotationHealth` 是页面唯一调用的入口，内部完成 `themesToRotationPoints → 各分量计算 → 档位判定 → 组装`。

### 4.6 时间轴联动

健康度反映**当前时间轴聚焦帧**。当前 `useSnapshotsTimeline` API 是否暴露 `currentFrame` 需要在实现阶段确认；若未暴露，需要小幅扩展返回值（不破坏现有调用方）。

## 5. UI 渲染规格

### 5.1 布局位置

在 `RotationPage` 的描述文字与 chart 之间插入信息条：

```
┌────────────────────────────────────────────────────────────┐
│ 主题轮动象限图                                              │
│ X 轴为长期强度...气泡大小反映综合排名。                    │
│                                                            │
│ ┌──────────────────┬──────────────────┐ ← RotationHealthBar│
│ │ 覆盖度    72 警示 │ 鲁棒度    85 健康 │                   │
│ └──────────────────┴──────────────────┘                   │
│                                                            │
│ [ Scatter chart with trails ]                              │
│                                                            │
│ [ QuadrantLegend ]                                         │
└────────────────────────────────────────────────────────────┘
```

### 5.2 视觉样式

容器：

```tsx
<div
  className="grid grid-cols-2 gap-px bg-gray-200 border rounded overflow-hidden mb-4"
  role="region"
  aria-label="分布健康度"
>
  <HealthCell ... />
  <HealthCell ... />
</div>
```

单 cell：

```tsx
<div className="bg-white px-4 py-2 flex items-center justify-between" role="status">
  <span className="text-xs text-gray-600">{label}</span>
  <div className="flex items-center gap-2">
    <span className="text-lg font-semibold tabular-nums">{score}</span>
    <span className={GRADE_BADGE_CLASS[grade]}>{GRADE_LABEL[grade]}</span>
    <InfoTooltip>{tooltip}</InfoTooltip>
  </div>
</div>
```

档位徽章 className：

```ts
const GRADE_BADGE_CLASS: Record<HealthGrade, string> = {
  healthy:      'bg-green-100 text-green-700 px-2 py-0.5 rounded text-xs',
  caution:      'bg-amber-100 text-amber-700 px-2 py-0.5 rounded text-xs',
  imbalanced:   'bg-red-100   text-red-700   px-2 py-0.5 rounded text-xs',
  insufficient: 'bg-gray-100  text-gray-600  px-2 py-0.5 rounded text-xs',
};

const GRADE_LABEL: Record<HealthGrade, string> = {
  healthy:      '健康',
  caution:      '警示',
  imbalanced:   '失衡',
  insufficient: '数据不足',
};
```

### 5.3 Tooltip 文案

| 指标 | Tooltip |
|---|---|
| 覆盖度 | 四象限主题数的香农熵。100=四象限均匀，0=全部挤在一个象限。低分意味分类信号集中，需结合大盘环境理解。 |
| 鲁棒度 | 远离边界线 (x=50 或 y=50) 超过 10 单位的主题占比。低分意味多数主题贴近边界，小幅波动就会跨象限，分类信号脆弱；高分意味分类对噪声有抗扰动能力。 |

### 5.4 响应式

- 桌面（≥ 640px）：`grid-cols-2`，左右并排
- 移动（< 640px）：`grid-cols-1`，上下堆叠

### 5.5 无障碍

- 颜色 + 文字双重编码（不仅靠颜色区分档位）
- Cell 整体 `role="status"`，提供 `aria-label="覆盖度 72 分 警示"`
- Tooltip 用 `aria-describedby` 关联

### 5.6 空数据兜底

- `themes.length === 0`：信息条整体不渲染（页面已有空数据 Alert）
- `themes.length === 1`：覆盖度 cell 显示 "—" + grade='insufficient' 灰色徽章；鲁棒度 cell 正常计算

## 6. 测试策略

### 6.1 纯函数单元测试 (`lib/__tests__/rotationHealth.test.ts`)

| # | 测试用例 | 输入 | 期望 |
|---|---|---|---|
| 1 | `computeCoverage` 完全均匀 | 4 象限各 3 主题 | ≈ 100 |
| 2 | `computeCoverage` 单象限主导 | 全部 leading | 0 |
| 3 | `computeCoverage` 双极分布 | 6 leading + 6 lagging | 50 |
| 4 | `computeCoverage` 空数组 | `[]` | 0 |
| 5 | `computeCoverage` 单点 | 1 主题 | 0 |
| 6 | `computeRobustness` 全部远离边界 | 所有点 (10,10) | 100 |
| 7 | `computeRobustness` 全部贴边界 | 所有点 (50,50) | 0 |
| 8 | `computeRobustness` 部分脆弱 | 5 个 (10,10) + 5 个 (50,50) | 50 |
| 9 | `computeRobustness` 仅 x 贴边 | (50, 80) → 算脆弱 | 0 |
| 10 | `computeRobustness` 边界值 9.99 vs 10.01 | (50+9.99,80) 脆弱; (50+10.01,80) 安全 | 验证开区间 |
| 11 | `computeRobustness` 空数组 | `[]` | 0 |
| 12 | `gradeCoverage` 边界 ≥80 | 80, 79 | healthy, caution |
| 13 | `gradeCoverage` 边界 ≥74 | 74, 73 | caution, imbalanced |
| 14 | `gradeCoverage` 数据不足 | n < 2 | insufficient |
| 15 | `gradeRobustness` 边界 ≥77 | 77, 76 | healthy, caution |
| 16 | `gradeRobustness` 边界 ≥69 | 69, 68 | caution, imbalanced |
| 17 | `gradeRobustness` 数据不足 | n < 1 | insufficient |
| 18 | `computeRotationHealth` 集成 | mix 主题 | 结构完整 + 分数合理 |

### 6.2 组件渲染测试 (`components/rotation/__tests__/RotationHealthBar.test.tsx`)

| # | 测试用例 | 验证 |
|---|---|---|
| 1 | 渲染分数 | 显示 "72" 与 "警示" |
| 2 | 健康档位颜色 | 找到 `bg-green-100` |
| 3 | 警示档位颜色 | 找到 `bg-amber-100` |
| 4 | 失衡档位颜色 | 找到 `bg-red-100` |
| 5 | 双 cell 都渲染 | "覆盖度" + "鲁棒度" 都在 DOM |
| 6 | Tooltip 存在 | `title` 含说明文案 |
| 7 | 无障碍属性 | `role="status"` + `aria-label` 正确 |
| 8 | 数据不足占位 | grade='insufficient' 显示 "—" |

### 6.3 页面集成测试 (扩展现有 `pages/__tests__/RotationPage.test.tsx`)

| # | 测试用例 | 验证 |
|---|---|---|
| 1 | 数据加载完成后 HealthBar 渲染 | 找到 `覆盖度` 文本 |
| 2 | Loading 状态隐藏 | skeleton 渲染时无 HealthBar |
| 3 | Error 状态隐藏 | Alert 渲染时无 HealthBar |
| 4 | Empty 状态隐藏 | 空数据 Alert 时无 HealthBar |

### 6.4 不做的测试

- E2E：现有 `frontend/e2e/rotation.spec.ts` 已覆盖整页冒烟，HealthBar 存在性顺带覆盖
- 颜色十六进制值：Tailwind class 名验证已足够
- Tooltip 弹出动画：属于视觉测试范畴
- 时间轴逐帧更新：属于 `useSnapshotsTimeline` 测试责任，已有覆盖

## 7. 验收标准

- [ ] 所有新增/修改文件通过 `npx vitest run`
- [ ] 通过 `npx eslint src --max-warnings=0`（与现有 CI gate 对齐）
- [ ] `RotationPage` 在桌面/移动两个断点下渲染正确
- [ ] 滑动时间轴时健康度数值随之变化
- [ ] 颜色档位与档位标签文字一致
- [ ] Tooltip 在 hover 时可读
- [ ] 主题数为 0/1 时不出现 JS 错误

## 8. 不在本次范围内 (YAGNI)

- 历史趋势：相比昨日 delta 或迷你时间序列图
- 用户自定义档位阈值
- 后端 API 暴露健康度
- 健康度异常时的告警/通知机制
- 健康度数据导出（CSV/JSON）

以上均可作为后续迭代项，本次只交付"看得见"的核心指标。

## 9. 决策记录

| 决策 | 选项 | 选择 | 理由 |
|---|---|---|---|
| 健康度的语义 | 覆盖度 / 散度 / 双指标 / 单一合成分 | 双指标 | 覆盖度与脆弱度是正交问题，单一分数会掩盖某一维度的失衡 |
| 第二指标公式 | 中心距散度 / 边界脆弱度 | 边界脆弱度（Robustness） | 历史回测证明散度动态范围 stdev=2.9 信息量低；Robustness 直接对应原始关切，stdev=6.9 |
| 计算位置 | 前端实时 / 后端预计算 | 前端实时 | UI 解读层指标，且需随时间轴重算，前端计算成本 < 1ms |
| 档位阈值来源 | 拍脑袋 / 实测分位数 | 实测分位数 | 让"健康/警示/失衡"对应历史频率而非主观判断 |
| 时间轴联动 | 始终最新快照 / 随聚焦帧变 | 随聚焦帧变 | 历史快照的健康度可比是本指标的核心价值 |

## 10. 附录：回测数据

回测样本：`data/snapshots/2026-01-02 ~ 2026-06-18`，共 123 个有效快照，每快照 N≈13-14 个主题。

### 10.1 Coverage 分布

```
min=57.0  P5=63.2  P10=68.9  P25=74.4  median=80.5  P75=89.4  P90=92.1  P95=96.1  max=97.5
range=40.5  stdev=9.6
```

### 10.2 Robustness 分布

```
min=53.8  P5=61.5  P10=64.3  P25=69.2  median=76.9  P75=78.6  P90=84.6  P95=84.6  max=85.7
range=31.9  stdev=6.9
```

### 10.3 已废弃的散度 (Spread) 分布

```
min=50.1  median=58.3  max=65.1   range=15.0  stdev=2.9
```

range 仅 15，stdev 2.9——信息量过低，已被 Robustness 替换。保留该数据以备未来对决策的回溯审查。

### 10.4 阈值推导（美股）

阈值取自 Coverage/Robustness 的 P25 与 P50：

- Coverage：P25=74.4 → 取整 74；P50=80.5 → 取整 80
- Robustness：P25=69.2 → 取整 69；P50=76.9 → 取整 77

历史档位分布（按本次设定阈值反算）：

- Coverage：失衡 ~25% / 警示 ~25% / 健康 ~50%
- Robustness：失衡 ~25% / 警示 ~25% / 健康 ~50%

未来若分布漂移（如长期升至 P75 以上），需重新回测并更新本节阈值。

### 10.5 A 股阈值（2026-06-25 补标定）

`MarketViewSelector` 上线后 `RotationPage` 的健康度需要随视图切换。沿用美股阈值会出现系统性偏差（A 股主题数更多，coverage 普遍更高；cn_strength 分布略集中，robustness 略低）。基于 127 个有效快照（2026-01-02 ~ 2026-06-25, `cn_strength` 字段）按相同算法重算：

**A 股 Coverage 分布**

```
min=55.4  P5=66.9  P10=72.0  P25=81.1  median=88.8  P75=93.4  P90=97.0  P95=97.5  max=99.3
range=43.9  stdev=9.8
```

**A 股 Robustness 分布**

```
min=60.7  P5=64.3  P10=64.3  P25=71.4  median=75.0  P75=78.6  P90=78.6  P95=82.1  max=85.7
range=25.0  stdev=5.6
```

**A 股阈值取整**

- Coverage：P25=81，P50=89（vs 美股 74/80）
- Robustness：P25=71，P50=75（vs 美股 69/77）

实现见 `frontend/src/lib/rotationHealth.ts:HEALTH_THRESHOLDS`，`gradeCoverage` / `gradeRobustness` 第三参数接受 `RotationMode`，由 `computeRotationHealth(themes, mode)` 透传。`RotationPage` 经 `useUIState().marketView` → `marketViewToRotationMode` 选择口径。

标定脚本：临时性，已弃用（`/tmp/calibrate_cn_health.py`）。未来漂移时复刻该算法重算即可。
