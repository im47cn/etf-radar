# 持仓监控模块设计

- **日期**：2026-06-21
- **状态**：Design Approved，待 plan
- **作者**：人 + AI（brainstorming session）
- **范围**：把现有跨市场强弱/轮动信号引擎延伸到"个人持仓"维度，提供持仓体检（a）、机会扫描（c）、轮动事件（d）三个子模块

> ⚠️ 本设计遵循项目 `docs/CONVENTIONS.md`：本文件**默认不入 git 历史**，作为执行期间的临时载体；由人工显式 `git add` 决定是否提交。

---

## 0. 背景与目标

ETF Radar 现有产品形态是"**全市场视角**"的信号发现工具：14 个美股主题 ETF 的强弱、轮动象限、A 股映射信号。所有 UI 都是匿名访问的静态展示。

**用户需求**："智能再平衡建议——把现有强弱/轮动信号转化为对我持仓的操作建议"。

**核心约束**（合规与产品定位）：

- 不做"明确买卖指令"（合规红线 + 工具定位漂移）
- 采用 **L1（信号事实陈述）+ 轻度 L2（形容词标签）**的输出立场
- 保留站点工具属性，登录/持仓属于**可选解锁功能**，不破坏匿名访问体验

**模块定位**：信号工具的延伸视角，而非投顾/账本。

## 1. 系统架构

### 1.1 总体架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                       浏览器（React + Vite）                       │
│                                                                   │
│   现有页：/  /rotation                                              │
│   新增页：/portfolio                                                │
│                                                                   │
│   ┌────────────────┐    ┌──────────────────┐                     │
│   │ Supabase JS    │    │ SWR fetch        │                     │
│   │ (Auth + DB)    │    │ themes/etfs/     │                     │
│   │                │    │ signals/         │                     │
│   │                │    │ snapshots JSON   │                     │
│   └────────┬───────┘    └────────┬─────────┘                     │
│            │                     │                                │
│            └──────────┬──────────┘                                │
│                       ↓                                           │
│           ┌──────────────────────────┐                            │
│           │  PortfolioEngine (TS)    │                            │
│           │  纯前端 JOIN + 评分计算    │                            │
│           └──────────────────────────┘                            │
└───────────┬─────────────────────────────────────────┬────────────┘
            │                                         │
            ↓                                         ↓
   ┌────────────────────┐                  ┌──────────────────────┐
   │  Supabase Cloud    │                  │  GitHub Pages        │
   │  - Auth            │                  │  - data/latest/*.json│
   │  - Postgres + RLS  │                  │  - data/snapshots/   │
   │  表：              │                  └──────────────────────┘
   │   user_holdings    │
   │   user_events      │
   └────────────────────┘
```

### 1.2 计算位置决策：纯前端 JOIN

**采用方案 A：纯前端 JOIN**。Supabase 仅作"持仓 + 事件"的 KV 存储，**不承担任何业务计算**。

理由：
- 持仓 N≤20 只，O(N) 计算无感
- 现有 themes/etfs/signals JSON 本来就在浏览器
- 零新增基建（无 Deno Edge Function 部署/测试成本）
- 算法可用 vitest 直接单测，无 mock Supabase 成本
- 未来若需迁移存储（如换回 localStorage），`PortfolioEngine` 完全不动

**否决方案**：
- Supabase Edge Function：多一套部署，无明显收益
- 扩展 Python pipeline：pipeline 是离线全市场视角，不知道每个用户持仓，本质不通

### 1.3 模块拆分（前端代码组织）

```
frontend/src/
├─ lib/
│  ├─ supabase.ts                  # Supabase client 单例
│  └─ portfolio/
│     ├─ types.ts                  # Holding / PortfolioScore / Event 类型
│     ├─ engine.ts                 # 纯函数：(holdings, themes, etfs, signals) → scored
│     ├─ rules.ts                  # L2 标签判定（"偏弱/偏强"等）
│     └─ eventDiff.ts              # Phase 3：日间快照差分
├─ hooks/
│  ├─ useAuth.ts                   # Supabase auth 状态 hook
│  ├─ useHoldings.ts               # CRUD + realtime subscription
│  └─ usePortfolioScores.ts        # 把 holdings + 公共 JSON 喂给 engine
├─ pages/
│  └─ PortfolioPage.tsx            # /portfolio 主页面
└─ components/portfolio/
   ├─ AuthGate.tsx                 # 未登录占位 + 登录入口
   ├─ HoldingsEditor.tsx           # 持仓 CRUD UI
   ├─ HoldingScoreCard.tsx         # 单只 ETF 体检卡
   ├─ OpportunityScanner.tsx       # Phase 2：机会扫描面板
   └─ EventTimeline.tsx            # Phase 3：站内信流
```

**单元边界**：`PortfolioEngine` 是纯函数模块，无 IO，无副作用，无 Supabase 依赖。

### 1.4 路由策略

`/portfolio` 独立路由作为主入口；同时在 `/` 和 `/rotation` 上**轻量叠加**持仓标记（金色外圈 + ⭐）让两套视图互通。

## 2. Supabase 数据模型

### 2.1 设计原则

- **极简表数**：Phase 1 只一张 `user_holdings`；Phase 3 加 `user_events`
- **RLS 全启用**：`user_id = auth.uid()` 锁死越权
- **Realtime 启用**：`user_holdings` 表订阅，多设备同步无须手动刷新
- **不建** `user_profile`（无偏好需求）、**不建** `portfolios`（一用户一组合）、**不建** `transactions`（不追溯每笔交易）

### 2.2 `user_holdings`（Phase 1）

```sql
CREATE TABLE user_holdings (
  id           uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id      uuid        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  etf_code     text        NOT NULL,                  -- 6 位 A 股 ETF 代码
  shares       numeric     NOT NULL CHECK (shares > 0),
  cost_price   numeric     CHECK (cost_price IS NULL OR cost_price > 0),
  note         text,
  created_at   timestamptz NOT NULL DEFAULT now(),
  updated_at   timestamptz NOT NULL DEFAULT now(),
  UNIQUE (user_id, etf_code)
);

CREATE INDEX idx_holdings_user ON user_holdings (user_id);

CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger AS $$
BEGIN NEW.updated_at = now(); RETURN NEW; END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_holdings_updated
  BEFORE UPDATE ON user_holdings
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

ALTER TABLE user_holdings ENABLE ROW LEVEL SECURITY;
CREATE POLICY holdings_own ON user_holdings
  FOR ALL TO authenticated
  USING      (user_id = auth.uid())
  WITH CHECK (user_id = auth.uid());
```

**字段决策注解**：
- `cost_price NULLABLE`：用户可不录，前端体检卡盈亏区自动隐藏
- `UNIQUE (user_id, etf_code)`：重复录入走 `ON CONFLICT DO UPDATE` 合并为加仓
- **不存** `market` 字段：v1 只支持 A 股，未来扩展时加

### 2.3 `user_events`（Phase 3）

```sql
CREATE TABLE user_events (
  id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         uuid        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  event_type      text        NOT NULL,             -- 'quadrant_change' | 'strength_cross_up' | 'strength_cross_down' | 'signal_change'
  etf_code        text        NOT NULL,
  theme_id        text,
  event_signature text        NOT NULL,             -- 'quadrant_change:510300:2026-06-21:leading_to_weakening'
  payload         jsonb       NOT NULL DEFAULT '{}'::jsonb,
  asof_date       date        NOT NULL,
  created_at      timestamptz NOT NULL DEFAULT now(),
  read_at         timestamptz,
  UNIQUE (user_id, event_signature)
);

CREATE INDEX idx_events_user_time ON user_events (user_id, created_at DESC);
CREATE INDEX idx_events_unread    ON user_events (user_id) WHERE read_at IS NULL;

ALTER TABLE user_events ENABLE ROW LEVEL SECURITY;
CREATE POLICY events_own ON user_events
  FOR ALL TO authenticated
  USING      (user_id = auth.uid())
  WITH CHECK (user_id = auth.uid());
```

**写入路径**：前端用户访问 `/portfolio` 时跑差分 → INSERT 带 `ON CONFLICT DO NOTHING`，UNIQUE 约束 dedupe。

### 2.4 Auth 配置

**启用 providers**：
- **Magic Link（邮箱）** — 主路径
- **Google OAuth** — 一键登录

**不启用**：
- 微信/QQ 登录（要企业资质 + OAuth 中转）
- Phone OTP（短信费用 + 国内号段配置复杂）

**Redirect URL 白名单**：
- `https://im47.cn/etf-radar/auth/callback`
- `http://localhost:5173/etf-radar/auth/callback`

### 2.5 环境变量

```env
VITE_SUPABASE_URL=https://xxxxx.supabase.co
VITE_SUPABASE_ANON_KEY=eyJxxx...
```

- GH Actions secrets：`SUPABASE_URL`, `SUPABASE_ANON_KEY` → `deploy-frontend.yml` build 时注入
- `anon key` 是公开设计（配合 RLS 保证安全）
- `service_role` key 永不入仓库；本项目无 server-side Supabase 调用

### 2.6 数据生命周期

| 操作 | 实现 |
|---|---|
| 用户注销账号 | ON DELETE CASCADE 自动清理 holdings/events |
| 持仓清空 | 前端按钮 + 二次确认 |
| 事件归档 | 不主动归档；前端默认只查 last 90 天 |

## 3. 信号融合引擎与体检逻辑

### 3.1 引擎 IO 定义（纯函数边界）

```ts
// frontend/src/lib/portfolio/engine.ts

export interface ScoreInputs {
  holdings:     Holding[];
  themes:       Theme[];
  etfs:         EtfMetric[];
  themeSignals: ThemeSignal[];
}

export interface HoldingScore {
  etfCode: string;
  status:  'covered' | 'uncovered';

  // 基础信息（uncovered 也有）
  name?:        string;
  shares:       number;
  costPrice?:   number;
  marketValue?: number;
  pnlPct?:      number;
  pnlAbs?:      number;

  // 仅 covered 才有
  selfStrength?:    Strength;
  themeId?:         string;
  themeName?:       string;
  themeUsStrength?: Strength;
  themeCnStrength?: Strength;
  themeSignal?:     'resonance' | 'transmission' | 'divergence';
  quadrant?:        'leading' | 'weakening' | 'following' | 'weak';
  l2Tag?:           StrengthTag;
  momentumTag?:     '动量向上' | '动量向下' | null;
  narrative?:       string;
}

export function scorePortfolio(inputs: ScoreInputs): HoldingScore[];
```

### 3.2 信号映射路径

```
持仓 etf_code
        │
        ├─→ etfs.json 查自身 strength
        │       └─→ 找到：status=covered
        │       └─→ 没找到：status=uncovered
        │
        └─→ themes.json 反查归属主题（theme.primary_cn === etf_code）
                  └─→ 记录 themeUsStrength / themeCnStrength
                  └─→ signals.json 查 theme_signal（共振/传导/背离）
```

### 3.3 L1 narrative 生成规则（事实陈述）

模板拼接，**仅描述客观信号位置**，**绝不出现"建议加仓/该减/卖出/买入"等指令性语言**。

```ts
function buildNarrative(score: HoldingScore): string {
  const parts: string[] = [];
  parts.push(`位于${quadrantLabel(score.quadrant)}`);
  parts.push(`综合强度 ${score.selfStrength.composite} 分位`);

  const mid = score.selfStrength.mid;
  if (mid >= 75) parts.push('中周期强劲');
  else if (mid <= 25) parts.push('中周期走弱');

  if (score.themeSignal === 'resonance')    parts.push('美股 A 股共振');
  if (score.themeSignal === 'transmission') parts.push('美股领先 A 股待跟随');
  if (score.themeSignal === 'divergence')   parts.push('美股 A 股背离');

  return parts.join('，');
}
```

**输出示例**："位于领涨象限，综合强度 95 分位，中周期强劲，美股 A 股共振"

### 3.4 L2 标签（轻度倾向，仅形容词）

```ts
function strengthTag(composite: number): StrengthTag {
  if (composite >= 75) return '偏强';
  if (composite >= 50) return '中性偏强';
  if (composite >= 25) return '中性偏弱';
  return '偏弱';
}

function momentumTag(short: number, mid: number): MomentumTag | null {
  if (short >= 70 && mid >= 60) return '动量向上';
  if (short <= 30 && mid <= 40) return '动量向下';
  return null;
}
```

**边界**：L2 标签是**形容词**不是**动词**——只说"它是什么状态"，不说"该怎么办"。

### 3.5 体检卡 UI 草图

```
┌──────────────────────────────────────────────────┐
│ 512480  半导体ETF国联安       [偏强] [动量向上]    │
│ 跟踪：中证全指半导体                              │
├──────────────────────────────────────────────────┤
│ 持仓 1000 份   成本 ¥2.10   现价 ¥2.48           │
│ 市值 ¥2,480   盈亏 +¥380  (+18.1%)              │
├──────────────────────────────────────────────────┤
│ 归属主题：存储芯片                                 │
│ ┌──── 双轨强度 ────┐  ┌──── 自身强度 ────┐       │
│ │  短  中  长  综  │  │  短  中  长  综  │       │
│ │ 99  96  99  98  │  │ 95  99  99  98  │       │
│ │ (美) (美) (美)   │  │  ETF 自身百分位   │       │
│ └─────────────────┘  └─────────────────┘        │
│                                                  │
│ 信号：美股 A 股共振                               │
│                                                  │
│ 位于领涨象限，综合强度 98 分位，中周期强劲，       │
│ 美股 A 股共振                                     │
└──────────────────────────────────────────────────┘
```

**uncovered 简化版**（灰显）：
```
┌──────────────────────────────────────────────────┐
│ 159928  消费ETF                          [无信号] │
├──────────────────────────────────────────────────┤
│ 持仓 500 份   成本 ¥1.85                          │
│                                                  │
│ ⓘ 该 ETF 不在信号覆盖范围（14 主题外），仅记录持仓 │
└──────────────────────────────────────────────────┘
```

### 3.6 机会扫描（Phase 2）

```ts
export function scanOpportunities(
  themes: Theme[],
  etfs: EtfMetric[],
  ownedCodes: Set<string>,
): Opportunity[] {
  return themes
    .filter(t => !ownedCodes.has(t.primary_cn))
    .filter(t => t.strength.composite >= 75)
    .filter(t => t.strength.short >= 70)
    .sort((a, b) => b.strength.composite - a.strength.composite)
    .slice(0, 10)
    .map(t => ({ /* 类似 HoldingScore 但无持仓字段 */ }));
}
```

UI：`/portfolio` 下方折叠面板"信号扫描"，文案"信号偏强"而非"推荐买入"。

### 3.7 事件差分（Phase 3）

```ts
export function detectEvents(
  todaySnapshot:     Snapshot,
  yesterdaySnapshot: Snapshot,
  holdings:          Holding[],
): PendingEvent[] {
  const events: PendingEvent[] = [];

  for (const h of holdings) {
    const today = lookup(todaySnapshot, h.etfCode);
    const yest  = lookup(yesterdaySnapshot, h.etfCode);
    if (!today || !yest) continue;     // uncovered 或新加 ETF 跳过

    // 事件 1：象限切换
    if (today.quadrant !== yest.quadrant) {
      events.push({
        event_type: 'quadrant_change',
        etf_code:   h.etfCode,
        event_signature: `quadrant_change:${h.etfCode}:${today.date}:${yest.quadrant}_to_${today.quadrant}`,
        payload:   { from: yest.quadrant, to: today.quadrant },
        asof_date: today.date,
      });
    }

    // 事件 2：跨越强度阈值
    for (const threshold of [25, 50, 75]) {
      if (yest.composite < threshold && today.composite >= threshold) {
        events.push({ event_type: 'strength_cross_up', /* ... */ });
      }
      if (yest.composite >= threshold && today.composite < threshold) {
        events.push({ event_type: 'strength_cross_down', /* ... */ });
      }
    }

    // 事件 3：主题信号变化
    if (today.themeSignal !== yest.themeSignal) {
      events.push({ event_type: 'signal_change', /* ... */ });
    }
  }

  return events;
}
```

**触发时机**：用户访问 `/portfolio` → 跑 diff → INSERT 到 `user_events`。
**节流**：localStorage 缓存 `last_detected_date`，同一天不重复跑。
**节假日处理**：用"上一个可用交易日"作为 yesterday，不依赖日历减 1。
**首次登录积压**：只检测 last 7 天的事件，不追溯过长历史。

### 3.8 测试策略

```
frontend/src/lib/portfolio/__tests__/
├─ engine.test.ts        # 6 种典型场景（covered/uncovered, 强/弱, 共振/传导/背离）
├─ rules.test.ts         # 边界值：composite=24/25/26/49/50/51/74/75/76
├─ eventDiff.test.ts     # 8 种状态转移 × 3 个阈值
└─ __fixtures__/
   ├─ themes-mock.json
   ├─ etfs-mock.json
   └─ snapshots-pair.json
```

## 4. UI 与路由

### 4.1 路由表

| 路径 | 组件 | 鉴权 | 阶段 |
|---|---|---|---|
| `/` | RadarPage（现有） | 匿名 | 现有 + 持仓叠加 |
| `/rotation` | RotationPage（现有） | 匿名 | 现有 + 持仓叠加 |
| `/portfolio` | PortfolioPage | 匿名可见登录占位 | Phase 1 |
| `/auth/callback` | AuthCallback | 公开 | Phase 1 |

### 4.2 Header 改造

```
┌─────────────────────────────────────────────────────────────┐
│ ETF Radar  [跨市雷达] [主题轮动] [我的持仓 🔴3]   📧 user@…  │
└─────────────────────────────────────────────────────────────┘
```

- 未登录：右侧 "登录" 按钮
- 登录后：邮箱缩略 + 下拉菜单（退出登录）
- 🔴N 徽章：Phase 3 加入，未读事件数

### 4.3 `/portfolio` 未登录态

居中登录卡 + 隐私声明：
- Magic Link 邮箱输入
- Google OAuth 一键
- 底部"数据隐私"三行说明（仅信号叠加 / 不分享 / 不构成投资建议）

### 4.4 `/portfolio` 登录态布局

```
┌─────────────────────────────────────────────────────────┐
│ 我的持仓（5 只）              [+ 添加持仓]  [⚙ 批量管理]  │
├─────────────────────────────────────────────────────────┤
│  体检卡网格（桌面 2-3 列，移动单列）                       │
├─────────────────────────────────────────────────────────┤
│  组合汇总（总市值/总盈亏/覆盖率/强弱分布）                 │
├─────────────────────────────────────────────────────────┤
│  [ ⊕ 信号扫描 ]  ← Phase 2                              │
│  [ ⊕ 最近事件 ]  ← Phase 3                              │
└─────────────────────────────────────────────────────────┘
```

**组合汇总字段语义**（涉及 covered/uncovered 混合时）：
- 总市值：**仅汇总 covered ETF**（uncovered 无现价）；若有 uncovered 持仓，附加一行"另含 N 只无估值持仓"
- 总盈亏：仅汇总同时有 `cost_price` 和 `current_price` 的 ETF
- 覆盖率：`covered 数 / 总持仓数`（如 4/5 = 80%）
- 强弱分布：仅基于 covered 持仓的 L2 标签计数（"偏强 2 只 / 中性 1 只 / 偏弱 1 只"）

### 4.5 持仓 CRUD（HoldingsEditor 模态）

- ETF 代码 autocomplete：搜 `etfs.json` 全集，显示 "[信号覆盖]" badge
- 非映射代码：允许提交 + toast 提示
- 重复 ETF：自动检测 + 合并加权平均成本确认弹窗
- 编辑/删除：体检卡 `⋯` 菜单 + 二次确认

### 4.6 现有页持仓叠加（轻量增强）

- RotationScatterWithTrails：持仓气泡加金色外圈 + ⭐
- ThemeList：持仓主题行首加 ⭐ 角标
- 实现：通过 `useHoldings()` hook 传入 `ownedThemeIds: Set<string>` prop
- 未登录无任何变化（渐进增强）

### 4.7 Phase 2 OpportunityScanner

折叠面板，默认折叠，标题显示候选数。展开后 3 列主题卡 + "跳转详情" 按钮（跳 `/?theme=<id>`）。

### 4.8 Phase 3 EventTimeline

折叠面板 + Header 红点联动。事件按 created_at 倒序，颜色：
- 🟢 利好（进入强势区、共振）
- 🟡 利空（进入弱势区、背离）
- 🔵 中性（象限切换但方向不明显）

### 4.9 Auth 流程

```
未登录 → 点 [发送登录链接] → Supabase 发邮件 → 用户点链接
  → /auth/callback?token=... → exchangeCodeForSession() → 写 localStorage session
  → redirect /portfolio → useAuth 检测 session → 登录态渲染
```

Google OAuth 路径相同。

### 4.10 设计系统对齐

- 复用 Tailwind v4 + shadcn/ui
- 配色对齐 RotationPage 四象限（强势=绿、弱势=红、中性=灰、金色外圈=持仓）

## 5. 分期交付路线图

### 5.1 三阶段总览

```
Phase 0 (~0.5d) ─→ Phase 1 (~7-8d) ─→ Phase 2 (~2-3d)
                                            │
                                            ▼
                                       Phase 3 (~5-7d)
```

**Phase 1 上线后至少跑 1-2 周再启动 Phase 2**，让 a 模块在真实使用中暴露问题。

### 5.2 Phase 0：基建准备（~0.5d）

| 子任务 | 验证标准 |
|---|---|
| 创建 Supabase 项目 | URL + anon key 到位 |
| 配置 Auth Providers（Magic Link + Google） | 控制台测试登录通 |
| 配置回调白名单 | 不报 redirect_uri_mismatch |
| GH Actions secrets：`SUPABASE_URL`, `SUPABASE_ANON_KEY` | `deploy-frontend.yml` 可读 |
| `schema.sql` 第一次 migration | 表+RLS 策略可见 |
| `.env.local.example` + README 更新 | 新人 clone 后可起服务 |

**风险**：Magic Link 邮件进国内邮箱垃圾箱（QQ/163）。**缓解**：README 提示检查垃圾箱 + 保留 Google OAuth 备选。

### 5.3 Phase 1：MVP 持仓体检（~7-8d）

| # | 任务 | 估时 |
|---|---|---|
| 1 | Supabase client + useAuth | 0.5d |
| 2 | `/portfolio` 路由 + AuthGate + 登录卡 | 1d |
| 3 | `/auth/callback` + Magic Link/OAuth 交换 | 0.5d |
| 4 | 持仓 CRUD：useHoldings + HoldingsEditor | 1.5d |
| 5 | PortfolioEngine + rules + 单测 | 2d |
| 6 | HoldingScoreCard（含 uncovered 灰显） | 1d |
| 7 | Header 改造 | 0.5d |
| 8 | 现有页叠加（金圈+⭐） | 0.5d |
| 9 | E2E 烟雾测试 | 0.5d |

**验收清单**：
- [ ] 匿名访问 `/` `/rotation` 体验零变化（除 Header 多一个导航）
- [ ] Magic Link 登录全流程通畅（含国内邮箱）
- [ ] Google OAuth 登录全流程通畅
- [ ] 录入 covered + uncovered ETF 成功
- [ ] 重复录入自动合并 + 重算加权平均成本
- [ ] 体检卡正确显示所有字段（市值/盈亏/L1 narrative/L2 标签/信号映射）
- [ ] uncovered ETF 灰显 + 明确提示
- [ ] 持仓 ETF 在 `/` `/rotation` 出现金圈/⭐
- [ ] 登出/重新登录持仓保留
- [ ] **多设备**：A 浏览器加持仓 → B 浏览器 Realtime 同步
- [ ] **RLS 红队**：SQL 直连越权读取被拒
- [ ] 单元测试 + E2E 烟雾全过

**已知 TBD（不阻塞）**：
- ETF 名称数据：v1 用本地 + "未识别"占位，后续考虑从 akshare 拉完整库
- 移动端 UX 精修：Phase 1 满足"可用"，深度优化进 Phase 1.5

**风险**：
| 风险 | 缓解 |
|---|---|
| GH Pages base path 与 callback URL 不匹配 | 提前在 Supabase 控制台配完整路径 |
| Vite env 在 GH Actions 构建丢失 | `deploy-frontend.yml` 显式 `env:` 注入 + 本地 bundle 校验 |
| anon key 暴露引起担忧 | 文档说明 Supabase 设计意图，安全靠 RLS |

### 5.4 Phase 2：机会扫描（~2-3d）

**前置**：Phase 1 上线运行 ≥1 周，无 P0 bug。

| # | 任务 | 估时 |
|---|---|---|
| 1 | `scanOpportunities()` + 单测 | 0.5d |
| 2 | OpportunityScanner 折叠面板 | 1d |
| 3 | "跳转主题详情" 路由集成 | 0.3d |
| 4 | E2E：持仓页点扫描 → 跳详情 | 0.2d |

**验收**：
- [ ] 正确排除已持仓 ETF
- [ ] 筛选条件可调（首版 composite≥75 + short≥70）
- [ ] 文案保持 L1+L2 立场（无"推荐买入"）
- [ ] 空态文案（满足条件可能为 0）

### 5.5 Phase 3：轮动事件 + 站内信流（~5-7d）

**前置**：Phase 1+2 上线 ≥2 周，有真实持仓样本可供 diff 测试。

| # | 任务 | 估时 |
|---|---|---|
| 1 | `user_events` 表 migration + RLS | 0.3d |
| 2 | `detectEvents()` + 单测（8 状态转移 × 3 阈值） | 2d |
| 3 | 事件写入路径：访问时 diff，UPSERT 去重 | 1d |
| 4 | EventTimeline 组件（已读/未读） | 1.5d |
| 5 | Header 红点徽章 + Realtime 订阅 | 0.7d |
| 6 | localStorage 缓存 last_detected_date | 0.3d |
| 7 | E2E + 历史快照 fixtures | 1.2d |

**验收**：
- [ ] covered ETF 在 quadrant/strength/signal 变化时正确生成事件
- [ ] uncovered / 新加 ETF 跳过差分不报错
- [ ] 同一事件 N 次访问只生成一条（UNIQUE 生效）
- [ ] 已读/未读状态正确
- [ ] Realtime：A 浏览器新事件 → B 浏览器红点实时更新
- [ ] 90 天前事件不显示
- [ ] 算法单测覆盖所有边界（穿越阈值、双向切换、相邻日 NaN）

**风险**：
| 风险 | 缓解 |
|---|---|
| 历史快照某天缺失（节假日） | 用"上一个可用交易日"，不依赖 `yesterday()` |
| 事件信号过敏感造成爆炸 | 阈值参数化，先观察再调优 |
| 长期未登录积压大量事件 | 首次登录只生成 last 7 天 |

### 5.6 上线节奏

- Phase 0+1 合并发布（一个 plan/PR）
- Phase 2 独立小 PR
- Phase 3 独立大 PR（带 e2e fixtures）

每个 PR 走现有 CI：`ci.yml`（pytest + vitest + playwright）→ `deploy-frontend.yml` 自动部署。

### 5.7 后续延伸（v2+，本设计不覆盖）

| 想法 | 是否值得 | 触发条件 |
|---|---|---|
| 非映射 ETF 取价 | 视反馈 | 用户高频抱怨"看不到现价" |
| 邮件每日摘要 | 视活跃度 | DAU 不高且 d 事件无人看 |
| 多组合 | 大概率 YAGNI | 明确用户请求 |
| 交易流水表 | 大概率 YAGNI | 用户要看历史成本演化 |
| 风险偏好问卷 | 不建议 | 漂移投顾 |

---

## 附录 A：决策记录（brainstorming session）

| # | 问题 | 选择 | 否决项 |
|---|---|---|---|
| Q1 | 持仓监控的本质需求 | C 智能再平衡建议 | A 视角叠加 / B 盈亏跟踪 / D 实时盯盘 |
| Q2 | 建议产出形态 | a + c + d 全做（分期） | b 目标权重（投顾化高风险） |
| Q3 | 持仓存储 | Supabase 全栈（Auth + Postgres + RLS） | Clerk + Supabase（过度方案）/ localStorage / 后端自建 |
| Q4 | 登录策略 | 匿名访问 + 登录解锁持仓 | 强制登录 / 匿名 localStorage + 可选云同步 |
| Q5 | 持仓范围 | A 股 ETF 任意代码（非映射灰显） | 仅映射表内 / +美股 / 任意标的账本 |
| Q6 | 建议严肃度 | L1 信号事实 + 轻度 L2 形容词 | L2 倾向标签 / L3 明确指令（合规风险） |
| Q7 | d 模块触达方式 | 仅站内信流 | 邮件 / Web Push / 微信 |
| Q8 | 非映射 ETF 是否取价 | v1 不取 | v1 即取（不必要的基建） |
| Q9 | 分期路径 | Phase 1 (a) → 2 (c) → 3 (d) | 一次性全做 / 仅做 a |

## 附录 B：关键架构决策记录（ADR）

### ADR-001：计算位置选纯前端 JOIN
- **决策**：所有信号融合、评分、事件差分在浏览器 TypeScript 完成
- **理由**：持仓规模小（O(N)），现有 JSON 本就在浏览器，零新增基建
- **不选 Supabase Edge Function 的代价**：失去 server-side 算力，但本场景无需
- **可逆性**：高。Engine 是纯函数，未来需要 server-side 计算时可直接复用

### ADR-002：Supabase 单一供应商，不引入 Clerk
- **决策**：Auth 与 DB 都用 Supabase
- **理由**：Supabase 自带 Auth 模块（Magic Link / OAuth）已满足需求；Clerk 的差异化价值（组织管理、企业 SSO）在本场景无意义
- **不选 Clerk 的代价**：放弃更精美的登录 UI 和更丰富的用户元数据能力
- **可逆性**：中。如未来确需 Clerk，迁移 Auth 是一次性工作但可行

### ADR-003：L1+L2 立场（不给指令）
- **决策**：所有建议输出限定为"事实陈述 + 形容词标签"
- **理由**：合规底线（避免触碰投顾业务监管）+ 守护工具定位
- **代价**：弱化"决策辅助"体验，用户需自行判断
- **可逆性**：低。一旦定调 L3 再回 L1 是产品倒退；从 L1 升 L2 容易

### ADR-004：UNIQUE (user_id, etf_code) 约束
- **决策**：一个用户一只 ETF 只能一行
- **理由**：信号计算不区分多笔成本；保持心智清晰
- **代价**：用户无法区分"主仓"和"定投仓"
- **可逆性**：中。可放宽为 `(user_id, etf_code, label)` 三元 UNIQUE

### ADR-005：事件用 event_signature dedupe
- **决策**：UNIQUE (user_id, event_signature) + ON CONFLICT DO NOTHING
- **理由**：同一事件多次访问不重复写
- **代价**：signature 算法变更会重新生成所有事件，要谨慎演进
- **可逆性**：低。一旦 signature 变更，历史事件夹生

## 附录 C：术语表

| 术语 | 含义 |
|---|---|
| covered | 持仓 ETF 在 `etfs.json` 14 只映射表内，有完整信号 |
| uncovered | 持仓 ETF 不在映射表内，仅记录无信号 |
| L1 narrative | 事实陈述式文案（"位于强势区，综合 85 分位"） |
| L2 标签 | 形容词胶囊（"偏强" / "动量向上"） |
| event_signature | 事件去重指纹，如 `quadrant_change:510300:2026-06-21:leading_to_weakening` |
| RLS | Postgres Row Level Security，按 `auth.uid()` 隔离 |
| Realtime | Supabase 的 WebSocket 表订阅推送机制 |
