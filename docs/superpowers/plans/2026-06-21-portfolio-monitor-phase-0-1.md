# 持仓监控 Phase 0+1 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 接入 Supabase（Auth + RLS Postgres），新增 `/portfolio` 路由实现登录后的持仓 CRUD 与"持仓体检卡"（a 模块 MVP）。

**Architecture:** Supabase 仅作持仓 KV 存储；所有信号融合在前端 TypeScript 纯函数完成（`lib/portfolio/engine.ts`）。`/portfolio` 独立路由，匿名访问 `/` 与 `/rotation` 体验零变化；登录后这两页轻量叠加"持仓 ⭐ + 金色外圈"标记。

**Tech Stack:** React 19 + Vite + TypeScript strict + Tailwind v4 + shadcn/ui + react-router-dom HashRouter + @supabase/supabase-js + zod + swr + vitest + playwright

**Spec Reference:** `docs/superpowers/specs/2026-06-21-portfolio-monitor-design.md`

---

## 重要：Git 操作约束

> **本计划遵循项目 CLAUDE.md 约定**：用户未主动要求时不计划 git 提交/分支操作。各任务的"代码 + 测试通过"即任务完成，**不在任务内自动 commit**。
>
> 用户在阶段性回顾时（建议每 3-5 个任务后）自行决定 stage 与 commit 范围。

## 文件结构

### 新建文件

```
backend/migrations/                                # 新增目录（如不存在）
└─ 001_user_holdings.sql                           # Phase 0 - Supabase schema

frontend/.env.local.example                        # Phase 0 - 环境变量模板
frontend/src/lib/
├─ supabase.ts                                     # Supabase client 单例
└─ portfolio/
   ├─ types.ts                                     # Holding / HoldingScore / Strength 等类型
   ├─ engine.ts                                    # scorePortfolio() 纯函数
   ├─ rules.ts                                     # strengthTag / momentumTag / buildNarrative
   └─ __tests__/
      ├─ engine.test.ts
      ├─ rules.test.ts
      └─ __fixtures__/
         ├─ themes-mock.ts
         └─ etfs-mock.ts

frontend/src/hooks/
├─ useAuth.ts                                      # Supabase auth 状态 + login/logout
└─ useHoldings.ts                                  # 持仓 CRUD + realtime subscription
                                                   #   (usePortfolioScores 合并进此 hook)

frontend/src/providers/
└─ AuthProvider.tsx                                # session context + onAuthStateChange

frontend/src/pages/
├─ PortfolioPage.tsx                               # /portfolio 主页面
└─ AuthCallback.tsx                                # /auth/callback OAuth/Magic Link 回调

frontend/src/components/portfolio/
├─ AuthGate.tsx                                    # 未登录占位 + 登录卡
├─ HoldingsEditor.tsx                              # 持仓 CRUD 模态
├─ EtfCodeAutocomplete.tsx                         # ETF 代码 autocomplete 子组件
├─ HoldingScoreCard.tsx                            # 单只 ETF 体检卡（covered/uncovered 双版本）
├─ PortfolioSummary.tsx                            # 组合汇总卡
├─ HoldingsList.tsx                                # 体检卡网格容器 + 空态
└─ __tests__/
   ├─ AuthGate.test.tsx
   ├─ HoldingsEditor.test.tsx
   ├─ HoldingScoreCard.test.tsx
   └─ PortfolioSummary.test.tsx

frontend/e2e/
└─ portfolio.spec.ts                               # E2E 烟雾
```

### 修改文件

```
frontend/package.json                              # 加 @supabase/supabase-js
frontend/src/App.tsx                               # 加 AuthProvider + 2 个新路由
frontend/src/components/Header/RadarTabs.tsx       # 替换 "持仓监控 (v3)" 占位为活动链接
frontend/src/components/Header/index.tsx           # 加用户菜单（登录按钮 / 邮箱下拉）
frontend/src/components/Header/UserMenu.tsx        # 新增子组件
frontend/src/components/rotation/RotationScatterWithTrails.tsx  # 接受 ownedThemeIds prop
frontend/src/components/ThemeList/                 # 行首加 ⭐ 角标（具体文件待 Read 确定）
frontend/src/pages/RotationPage.tsx                # 注入 ownedThemeIds
frontend/src/pages/RadarPage.tsx                   # 注入 ownedThemeIds
.github/workflows/deploy-frontend.yml              # 注入 SUPABASE env vars
README.md                                          # 加"持仓监控本地开发"章节
.gitignore                                         # 确认 .env.local 已忽略
```

---

# Phase 0：基建准备

## Task 0.1：人工操作 — 创建 Supabase 项目与 Auth Providers

**Files:** 无代码改动，**纯控制台操作**。

- [ ] **Step 1: 创建 Supabase 项目**

访问 https://supabase.com → New Project：
- 项目名：`etf-radar`
- Database password：生成强密码并保存到 1Password/密码管理器
- Region：Northeast Asia (Tokyo) 或 Southeast Asia (Singapore) — 国内访问较快
- Pricing：Free Tier

创建完成后，从 Settings → API 拿到：
- Project URL：`https://xxxxx.supabase.co`
- `anon` `public` key（很长的 JWT 字符串）

- [ ] **Step 2: 配置 Magic Link Auth Provider**

控制台 → Authentication → Providers → Email：
- Enable Email Provider：✓
- Confirm email：✗（关闭，避免国内邮箱二次验证麻烦）
- Secure email change：✓
- Secure password change：✓
- 保存

- [ ] **Step 3: 配置 Google OAuth Provider**

控制台 → Authentication → Providers → Google：
- Enable Google Provider：✓
- 跳到 https://console.cloud.google.com/ 创建 OAuth 2.0 Client ID：
  - Application type：Web application
  - Authorized redirect URI：`https://xxxxx.supabase.co/auth/v1/callback`（从 Supabase 控制台同一页复制）
- 把 Google 给的 Client ID + Client Secret 填回 Supabase
- 保存

- [ ] **Step 4: 配置回调 URL 白名单**

控制台 → Authentication → URL Configuration：
- Site URL：`https://im47.cn/etf-radar/`
- Redirect URLs：加入以下三条：
  ```
  https://im47.cn/etf-radar/
  https://im47.cn/etf-radar/#/auth/callback
  http://localhost:5173/etf-radar/
  http://localhost:5173/etf-radar/#/auth/callback
  ```

> 注意：HashRouter 使用 # fragment，Supabase 的 `detectSessionInUrl` 能正确处理。

- [ ] **Step 5: 验收**

- [ ] Supabase 控制台首页能看到项目
- [ ] Authentication → Providers 中 Email + Google 都为 Enabled
- [ ] 把 Project URL 和 anon key 记录到本地临时笔记（Task 0.3 要用）

---

## Task 0.2：编写 Supabase 数据库 schema

**Files:**
- Create: `backend/migrations/001_user_holdings.sql`

> 注：本项目主要后端是 Python pipeline，无 ORM/migration 框架。我们用纯 SQL 文件作为 schema 留档，**手动在 Supabase SQL Editor 执行**。后续 Phase 3 加 `user_events` 时增量再写 `002_user_events.sql`。

- [ ] **Step 1: 创建 migrations 目录与 schema 文件**

```bash
mkdir -p backend/migrations
```

创建 `backend/migrations/001_user_holdings.sql`：

```sql
-- 001_user_holdings.sql
-- 用户持仓表 + RLS 策略
-- 在 Supabase SQL Editor 中执行（一次性）

-- ========== updated_at 通用触发器函数 ==========
CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ========== user_holdings ==========
CREATE TABLE IF NOT EXISTS user_holdings (
  id           uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id      uuid        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  etf_code     text        NOT NULL,
  shares       numeric     NOT NULL CHECK (shares > 0),
  cost_price   numeric     CHECK (cost_price IS NULL OR cost_price > 0),
  note         text,
  created_at   timestamptz NOT NULL DEFAULT now(),
  updated_at   timestamptz NOT NULL DEFAULT now(),
  UNIQUE (user_id, etf_code)
);

CREATE INDEX IF NOT EXISTS idx_holdings_user
  ON user_holdings (user_id);

DROP TRIGGER IF EXISTS trg_holdings_updated ON user_holdings;
CREATE TRIGGER trg_holdings_updated
  BEFORE UPDATE ON user_holdings
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ========== RLS ==========
ALTER TABLE user_holdings ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS holdings_own ON user_holdings;
CREATE POLICY holdings_own ON user_holdings
  FOR ALL TO authenticated
  USING      (user_id = auth.uid())
  WITH CHECK (user_id = auth.uid());

-- ========== Realtime ==========
-- 在 Supabase 控制台 Database → Replication 中手动启用 user_holdings 的 Realtime publication
-- 或执行：
ALTER PUBLICATION supabase_realtime ADD TABLE user_holdings;
```

- [ ] **Step 2: 在 Supabase SQL Editor 中执行**

- 打开 Supabase 控制台 → SQL Editor → New Query
- 把整个 `001_user_holdings.sql` 内容粘贴进去
- 点 Run，应看到 "Success. No rows returned"

- [ ] **Step 3: 验收 — 表已建 + RLS 已启**

在 SQL Editor 执行验收 SQL：

```sql
-- 验收 1：表结构正确
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_name = 'user_holdings'
ORDER BY ordinal_position;

-- 验收 2：RLS 已启用
SELECT relname, relrowsecurity
FROM pg_class
WHERE relname = 'user_holdings';
-- 期望：relrowsecurity = true

-- 验收 3：策略存在
SELECT polname, polcmd FROM pg_policy
WHERE polrelid = 'user_holdings'::regclass;
-- 期望：1 条策略 holdings_own, polcmd='*' 即 ALL
```

- [ ] **Step 4: RLS 红队测试（手动）**

在 SQL Editor（以 service_role 身份）插入 2 个不同用户的数据测试隔离：

```sql
-- 用 SQL Editor 直接插入（绕过 RLS，仅测试用）
INSERT INTO user_holdings (user_id, etf_code, shares)
VALUES
  ('00000000-0000-0000-0000-000000000001', '510300', 100),
  ('00000000-0000-0000-0000-000000000002', '512480', 200);

-- 切换 role 到 authenticated 并模拟 user 1：
SET LOCAL role = 'authenticated';
SET LOCAL request.jwt.claims = '{"sub":"00000000-0000-0000-0000-000000000001"}';
SELECT etf_code FROM user_holdings;
-- 期望：只返回 510300，不返回 512480

-- 清理测试数据
RESET ROLE;
DELETE FROM user_holdings WHERE user_id IN
  ('00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000002');
```

---

## Task 0.3：配置环境变量（本地 + CI）

**Files:**
- Create: `frontend/.env.local.example`
- Modify: `.gitignore`（确认 `.env.local` 已忽略）

- [ ] **Step 1: 创建 .env.local.example**

```bash
cat > frontend/.env.local.example <<'EOF'
# 复制此文件为 .env.local 并填入真实值
# 持仓监控模块所需（不填则 /portfolio 路由功能不可用，但其它页面正常）

VITE_SUPABASE_URL=https://xxxxx.supabase.co
VITE_SUPABASE_ANON_KEY=eyJxxx-your-anon-key-here
EOF
```

- [ ] **Step 2: 验证 .gitignore 已忽略 .env.local**

```bash
grep -E '(^\.env\.local|^\*\.env\.local|^frontend/\.env\.local)' .gitignore
```

如未命中，追加：

```bash
echo '
# 持仓监控本地环境变量（含 Supabase URL 和 anon key）
frontend/.env.local
.env.local' >> .gitignore
```

- [ ] **Step 3: 本地创建 .env.local**

```bash
cp frontend/.env.local.example frontend/.env.local
# 编辑 frontend/.env.local，填入 Task 0.1 拿到的真实 URL 和 anon key
```

- [ ] **Step 4: 在 GitHub 仓库配置 Secrets**

访问 https://github.com/im47cn/etf-radar/settings/secrets/actions → New repository secret，添加：
- `SUPABASE_URL`：粘贴 Project URL
- `SUPABASE_ANON_KEY`：粘贴 anon key

- [ ] **Step 5: 验收**

```bash
# 本地 .env.local 存在但不被 git 追踪
ls frontend/.env.local
git check-ignore frontend/.env.local && echo "✓ ignored"

# GitHub Actions secrets 已添加（人工在 UI 确认）
```

---

## Task 0.4：修改 deploy-frontend.yml 注入 Supabase env

**Files:**
- Modify: `.github/workflows/deploy-frontend.yml`

- [ ] **Step 1: 先读现状**

```bash
cat .github/workflows/deploy-frontend.yml
```

定位到 `npm run build` 步骤所在的 job。

- [ ] **Step 2: 在 build 步骤前注入 env**

在 `- name: Build` 步骤上加 `env:` 块：

```yaml
      - name: Build
        env:
          VITE_SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
          VITE_SUPABASE_ANON_KEY: ${{ secrets.SUPABASE_ANON_KEY }}
        run: |
          cd frontend
          npm run build
```

> 注意：如 secrets 未配置，Vite 构建不会失败，但 import.meta.env.VITE_SUPABASE_URL 在运行时为 undefined。前端代码需做兜底（Task 1.2）。

- [ ] **Step 3: 验收（提交前 dry-run 校验）**

```bash
# YAML 语法检查（如果安装了 yq）
yq eval '.jobs' .github/workflows/deploy-frontend.yml > /dev/null
# 或用 Python
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/deploy-frontend.yml'))"
```

- [ ] **Step 4: 验收完成条件**

- [ ] workflow YAML 解析无错
- [ ] env 块只在 Build 步骤，不污染 deploy/upload 步骤

---

## Task 0.5：README 添加"持仓监控本地开发"章节

**Files:**
- Modify: `README.md`

- [ ] **Step 1: 在 README 的 "Frontend (Node 20+)" 节后追加章节**

定位 README.md 中 `### Frontend (Node 20+)` 章节，在其后插入：

```markdown
### 持仓监控本地开发（v3+）

`/portfolio` 路由需要 Supabase 凭据。**未配置不影响其他页面**，但 `/portfolio` 会显示"未配置"提示。

```bash
cp frontend/.env.local.example frontend/.env.local
# 编辑 .env.local，填入 Supabase Project URL 和 anon key
# 凭据可向项目维护者索取，或自行创建 Supabase 项目（见 docs/superpowers/specs/2026-06-21-portfolio-monitor-design.md）

npm run dev  # http://localhost:5173/etf-radar/#/portfolio
```

**Magic Link 登录**：邮件可能进国内邮箱（QQ/163）的垃圾箱，请检查；或使用 Google OAuth 一键登录。

**数据库 Schema**：见 `backend/migrations/001_user_holdings.sql`。在 Supabase SQL Editor 一次性执行。
```

- [ ] **Step 2: 验收**

```bash
grep -A2 "持仓监控本地开发" README.md
```

期望：能看到新加的章节标题。

---

# Phase 1：MVP 持仓体检（a 模块）

## Task 1.1：安装 @supabase/supabase-js

**Files:**
- Modify: `frontend/package.json`, `frontend/package-lock.json`

- [ ] **Step 1: 安装依赖**

```bash
cd frontend && npm install @supabase/supabase-js
```

- [ ] **Step 2: 验收**

```bash
cd frontend && node -e "console.log(require('@supabase/supabase-js').createClient.name)"
```

期望输出：`createClient`

```bash
cd frontend && grep '"@supabase/supabase-js"' package.json
```

期望：能看到版本号。

---

## Task 1.2：Supabase client 单例 + 环境变量兜底

**Files:**
- Create: `frontend/src/lib/supabase.ts`
- Create: `frontend/src/lib/__tests__/supabase.test.ts`

- [ ] **Step 1: 写测试 — 验证 isSupabaseConfigured 行为**

创建 `frontend/src/lib/__tests__/supabase.test.ts`：

```ts
import { describe, it, expect, vi, beforeEach } from 'vitest';

describe('supabase client', () => {
  beforeEach(() => {
    vi.resetModules();
  });

  it('isSupabaseConfigured returns false when env missing', async () => {
    vi.stubEnv('VITE_SUPABASE_URL', '');
    vi.stubEnv('VITE_SUPABASE_ANON_KEY', '');
    const mod = await import('../supabase');
    expect(mod.isSupabaseConfigured()).toBe(false);
  });

  it('isSupabaseConfigured returns true when env present', async () => {
    vi.stubEnv('VITE_SUPABASE_URL', 'https://test.supabase.co');
    vi.stubEnv('VITE_SUPABASE_ANON_KEY', 'fake-anon-key');
    const mod = await import('../supabase');
    expect(mod.isSupabaseConfigured()).toBe(true);
    expect(mod.getSupabase()).toBeDefined();
  });

  it('getSupabase throws when not configured', async () => {
    vi.stubEnv('VITE_SUPABASE_URL', '');
    vi.stubEnv('VITE_SUPABASE_ANON_KEY', '');
    const mod = await import('../supabase');
    expect(() => mod.getSupabase()).toThrow(/SUPABASE/);
  });
});
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd frontend && npx vitest run src/lib/__tests__/supabase.test.ts
```

期望：FAIL（模块不存在）

- [ ] **Step 3: 实现 supabase 单例**

创建 `frontend/src/lib/supabase.ts`：

```ts
import { createClient, SupabaseClient } from '@supabase/supabase-js';

const url     = import.meta.env.VITE_SUPABASE_URL ?? '';
const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY ?? '';

let client: SupabaseClient | null = null;

export function isSupabaseConfigured(): boolean {
  return Boolean(url && anonKey);
}

export function getSupabase(): SupabaseClient {
  if (!isSupabaseConfigured()) {
    throw new Error(
      'SUPABASE_NOT_CONFIGURED: VITE_SUPABASE_URL 或 VITE_SUPABASE_ANON_KEY 未配置。' +
      '请在 frontend/.env.local 中填入凭据后重启 dev server。'
    );
  }
  if (!client) {
    client = createClient(url, anonKey, {
      auth: {
        persistSession:  true,
        autoRefreshToken: true,
        detectSessionInUrl: true,
      },
    });
  }
  return client;
}
```

- [ ] **Step 4: 跑测试确认通过**

```bash
cd frontend && npx vitest run src/lib/__tests__/supabase.test.ts
```

期望：3 个测试全 PASS。

---

## Task 1.3：AuthProvider + useAuth hook

**Files:**
- Create: `frontend/src/providers/AuthProvider.tsx`
- Create: `frontend/src/hooks/useAuth.ts`
- Create: `frontend/src/providers/authContext.ts`
- Create: `frontend/src/hooks/__tests__/useAuth.test.tsx`

- [ ] **Step 1: 写测试 — 验证 useAuth 返回结构**

创建 `frontend/src/hooks/__tests__/useAuth.test.tsx`：

```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook } from '@testing-library/react';
import { AuthProvider } from '@/providers/AuthProvider';
import { useAuth } from '../useAuth';
import type { ReactNode } from 'react';

vi.mock('@/lib/supabase', () => ({
  isSupabaseConfigured: () => true,
  getSupabase: () => ({
    auth: {
      getSession: vi.fn().mockResolvedValue({ data: { session: null } }),
      onAuthStateChange: vi.fn(() => ({
        data: { subscription: { unsubscribe: vi.fn() } },
      })),
      signOut: vi.fn().mockResolvedValue({ error: null }),
      signInWithOtp: vi.fn().mockResolvedValue({ error: null }),
      signInWithOAuth: vi.fn().mockResolvedValue({ error: null }),
    },
  }),
}));

const wrapper = ({ children }: { children: ReactNode }) => (
  <AuthProvider>{children}</AuthProvider>
);

describe('useAuth', () => {
  beforeEach(() => vi.clearAllMocks());

  it('initial state: status=loading, user=null', () => {
    const { result } = renderHook(() => useAuth(), { wrapper });
    expect(result.current.status).toBe('loading');
    expect(result.current.user).toBeNull();
  });

  it('exposes signInWithMagicLink, signInWithGoogle, signOut', () => {
    const { result } = renderHook(() => useAuth(), { wrapper });
    expect(typeof result.current.signInWithMagicLink).toBe('function');
    expect(typeof result.current.signInWithGoogle).toBe('function');
    expect(typeof result.current.signOut).toBe('function');
  });
});
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd frontend && npx vitest run src/hooks/__tests__/useAuth.test.tsx
```

- [ ] **Step 3: 实现 authContext + AuthProvider**

创建 `frontend/src/providers/authContext.ts`：

```ts
import { createContext } from 'react';
import type { User } from '@supabase/supabase-js';

export type AuthStatus = 'loading' | 'authenticated' | 'anonymous' | 'unconfigured';

export interface AuthContextValue {
  status: AuthStatus;
  user:   User | null;
  signInWithMagicLink: (email: string) => Promise<{ error: string | null }>;
  signInWithGoogle:    () => Promise<{ error: string | null }>;
  signOut:             () => Promise<void>;
}

export const AuthContext = createContext<AuthContextValue | null>(null);
```

创建 `frontend/src/providers/AuthProvider.tsx`：

```tsx
import { useEffect, useState, useCallback, type ReactNode } from 'react';
import type { User } from '@supabase/supabase-js';
import { isSupabaseConfigured, getSupabase } from '@/lib/supabase';
import { AuthContext, type AuthStatus } from './authContext';

export const AuthProvider = ({ children }: { children: ReactNode }) => {
  const [status, setStatus] = useState<AuthStatus>('loading');
  const [user, setUser]     = useState<User | null>(null);

  useEffect(() => {
    if (!isSupabaseConfigured()) {
      setStatus('unconfigured');
      return;
    }
    const supabase = getSupabase();
    supabase.auth.getSession().then(({ data: { session } }) => {
      setUser(session?.user ?? null);
      setStatus(session?.user ? 'authenticated' : 'anonymous');
    });
    const { data: { subscription } } = supabase.auth.onAuthStateChange(
      (_event, session) => {
        setUser(session?.user ?? null);
        setStatus(session?.user ? 'authenticated' : 'anonymous');
      }
    );
    return () => subscription.unsubscribe();
  }, []);

  const signInWithMagicLink = useCallback(async (email: string) => {
    if (!isSupabaseConfigured()) return { error: '未配置 Supabase' };
    const { error } = await getSupabase().auth.signInWithOtp({
      email,
      options: { emailRedirectTo: `${window.location.origin}/etf-radar/#/auth/callback` },
    });
    return { error: error?.message ?? null };
  }, []);

  const signInWithGoogle = useCallback(async () => {
    if (!isSupabaseConfigured()) return { error: '未配置 Supabase' };
    const { error } = await getSupabase().auth.signInWithOAuth({
      provider: 'google',
      options:  { redirectTo: `${window.location.origin}/etf-radar/#/auth/callback` },
    });
    return { error: error?.message ?? null };
  }, []);

  const signOut = useCallback(async () => {
    if (!isSupabaseConfigured()) return;
    await getSupabase().auth.signOut();
  }, []);

  return (
    <AuthContext.Provider value={{ status, user, signInWithMagicLink, signInWithGoogle, signOut }}>
      {children}
    </AuthContext.Provider>
  );
};
```

创建 `frontend/src/hooks/useAuth.ts`：

```ts
import { useContext } from 'react';
import { AuthContext } from '@/providers/authContext';

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error('useAuth must be used within <AuthProvider>');
  }
  return ctx;
}
```

- [ ] **Step 4: 跑测试确认通过**

```bash
cd frontend && npx vitest run src/hooks/__tests__/useAuth.test.tsx
```

期望：2 个测试 PASS。

---

## Task 1.4：在 App.tsx 注入 AuthProvider + 新增 2 个路由

**Files:**
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: 修改 App.tsx**

替换文件内容为：

```tsx
import { HashRouter, Routes, Route } from 'react-router-dom';
import { DataProvider } from '@/providers/DataProvider';
import { UIStateProvider } from '@/providers/UIStateProvider';
import { AuthProvider } from '@/providers/AuthProvider';
import { Header } from '@/components/Header';
import { RadarPage } from '@/pages/RadarPage';
import { RotationPage } from '@/pages/RotationPage';
import { PortfolioPage } from '@/pages/PortfolioPage';
import { AuthCallback } from '@/pages/AuthCallback';

export default function App() {
  return (
    <DataProvider>
      <HashRouter>
        <AuthProvider>
          <UIStateProvider>
            <div className="min-h-screen bg-gray-50">
              <Header />
              <Routes>
                <Route path="/"               element={<RadarPage />} />
                <Route path="/rotation"       element={<RotationPage />} />
                <Route path="/portfolio"      element={<PortfolioPage />} />
                <Route path="/auth/callback"  element={<AuthCallback />} />
              </Routes>
            </div>
          </UIStateProvider>
        </AuthProvider>
      </HashRouter>
    </DataProvider>
  );
}
```

> 注意：此时 PortfolioPage 和 AuthCallback 尚未创建，TS 会报错。下两个 task 创建。

- [ ] **Step 2: 创建占位文件让 App 能编译**

创建 `frontend/src/pages/PortfolioPage.tsx`：
```tsx
export const PortfolioPage = () => <div>PortfolioPage (placeholder)</div>;
```

创建 `frontend/src/pages/AuthCallback.tsx`：
```tsx
export const AuthCallback = () => <div>AuthCallback (placeholder)</div>;
```

- [ ] **Step 3: 验收 — 现有测试不破**

```bash
cd frontend && npx vitest run 2>&1 | tail -20
```

期望：除新增的 supabase.test.ts / useAuth.test.tsx 外，已有测试全 PASS。

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -20
```

期望：无 TS 错误。

---

## Task 1.5：替换 RadarTabs 中的 "持仓监控 (v3)" 占位

**Files:**
- Modify: `frontend/src/components/Header/RadarTabs.tsx`

- [ ] **Step 1: 修改 RadarTabs**

把当前的：

```tsx
<span className="px-3 py-1 rounded text-gray-400 cursor-not-allowed" aria-disabled>
  持仓监控 (v3)
</span>
```

替换为：

```tsx
<Link to="/portfolio" className={linkClass(pathname === '/portfolio')}>
  我的持仓
</Link>
```

- [ ] **Step 2: 跑现有的 Header / RadarTabs 测试**

```bash
cd frontend && npx vitest run src/components/Header 2>&1 | tail -20
```

如果有测试断言旧文案 "持仓监控 (v3)" 或断言"disabled"，需更新断言为：
- 文案改成 "我的持仓"
- 不再是 disabled

- [ ] **Step 3: 验收**

```bash
cd frontend && npx vitest run src/components/Header 2>&1 | tail -5
```

期望：PASS。

---

## Task 1.6：AuthCallback 实际逻辑

**Files:**
- Modify: `frontend/src/pages/AuthCallback.tsx`

> Supabase 的 `detectSessionInUrl: true` 会自动从 URL 解析 session。此页面只需等 session 就绪后跳走。

- [ ] **Step 1: 实现 AuthCallback**

替换 `frontend/src/pages/AuthCallback.tsx`：

```tsx
import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/hooks/useAuth';

export const AuthCallback = () => {
  const { status } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    if (status === 'authenticated') {
      navigate('/portfolio', { replace: true });
    } else if (status === 'anonymous') {
      // session 解析后仍未登录，回登录页
      navigate('/portfolio', { replace: true });
    }
    // status === 'loading' / 'unconfigured' 时不动
  }, [status, navigate]);

  return (
    <div className="flex items-center justify-center min-h-[40vh] text-gray-600">
      <div className="text-center space-y-2">
        <div className="text-2xl">🔐</div>
        <div>正在完成登录...</div>
      </div>
    </div>
  );
};
```

- [ ] **Step 2: 验收**

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -10
```

期望：无错。

```bash
cd frontend && npx vitest run 2>&1 | tail -5
```

期望：所有现有测试仍 PASS。

---

## Task 1.7：AuthGate 组件（未登录登录卡）

**Files:**
- Create: `frontend/src/components/portfolio/AuthGate.tsx`
- Create: `frontend/src/components/portfolio/__tests__/AuthGate.test.tsx`

- [ ] **Step 1: 写测试**

创建 `frontend/src/components/portfolio/__tests__/AuthGate.test.tsx`：

```tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { AuthGate } from '../AuthGate';
import { AuthContext } from '@/providers/authContext';

const renderWithAuth = (status: 'loading' | 'anonymous' | 'unconfigured', overrides = {}) => {
  const value = {
    status,
    user: null,
    signInWithMagicLink: vi.fn().mockResolvedValue({ error: null }),
    signInWithGoogle:    vi.fn().mockResolvedValue({ error: null }),
    signOut:             vi.fn().mockResolvedValue(undefined),
    ...overrides,
  };
  render(
    <AuthContext.Provider value={value as never}>
      <AuthGate><div>protected</div></AuthGate>
    </AuthContext.Provider>
  );
  return value;
};

describe('AuthGate', () => {
  it('loading: shows skeleton, not children', () => {
    renderWithAuth('loading');
    expect(screen.queryByText('protected')).toBeNull();
    expect(screen.getByText(/加载中/)).toBeInTheDocument();
  });

  it('anonymous: shows login card', () => {
    renderWithAuth('anonymous');
    expect(screen.queryByText('protected')).toBeNull();
    expect(screen.getByText(/持仓信号监控/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /发送登录链接/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Google/ })).toBeInTheDocument();
  });

  it('unconfigured: shows config-missing message', () => {
    renderWithAuth('unconfigured');
    expect(screen.queryByText('protected')).toBeNull();
    expect(screen.getByText(/未配置 Supabase/)).toBeInTheDocument();
  });

  it('magic link: calls signInWithMagicLink with input', async () => {
    const { signInWithMagicLink } = renderWithAuth('anonymous');
    const input = screen.getByLabelText(/邮箱/);
    fireEvent.change(input, { target: { value: 'test@example.com' } });
    fireEvent.click(screen.getByRole('button', { name: /发送登录链接/ }));
    expect(signInWithMagicLink).toHaveBeenCalledWith('test@example.com');
  });
});
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd frontend && npx vitest run src/components/portfolio/__tests__/AuthGate.test.tsx
```

- [ ] **Step 3: 实现 AuthGate**

创建 `frontend/src/components/portfolio/AuthGate.tsx`：

```tsx
import { useState, type ReactNode } from 'react';
import { useAuth } from '@/hooks/useAuth';

export const AuthGate = ({ children }: { children: ReactNode }) => {
  const { status, signInWithMagicLink, signInWithGoogle } = useAuth();
  const [email, setEmail]   = useState('');
  const [msg, setMsg]       = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  if (status === 'loading') {
    return <div className="p-8 text-center text-gray-500">加载中...</div>;
  }

  if (status === 'unconfigured') {
    return (
      <div className="max-w-md mx-auto mt-12 p-6 border rounded bg-yellow-50">
        <div className="text-lg font-semibold mb-2">⚠ 未配置 Supabase</div>
        <div className="text-sm text-gray-700">
          持仓监控功能需要 Supabase 凭据。请联系管理员或参考
          <code className="mx-1 px-1 bg-gray-100">frontend/.env.local.example</code>
          自行配置。
        </div>
      </div>
    );
  }

  if (status === 'authenticated') return <>{children}</>;

  // status === 'anonymous'
  const handleMagicLink = async () => {
    if (!email) return;
    setSubmitting(true);
    setMsg(null);
    const { error } = await signInWithMagicLink(email);
    setSubmitting(false);
    setMsg(error ? `失败：${error}` : '✓ 登录链接已发送，请检查邮箱（含垃圾邮件）');
  };

  return (
    <div className="max-w-md mx-auto mt-12 p-6 border rounded bg-white shadow-sm">
      <h2 className="text-xl font-bold text-center mb-1">📊 持仓信号监控</h2>
      <p className="text-sm text-gray-600 text-center mb-6">
        把您的持仓接入跨市场强弱与轮动信号引擎
      </p>

      <label htmlFor="email" className="block text-sm font-medium mb-1">邮箱</label>
      <input
        id="email"
        type="email"
        value={email}
        onChange={e => setEmail(e.target.value)}
        placeholder="your@email.com"
        className="w-full px-3 py-2 border rounded mb-3"
      />
      <button
        onClick={handleMagicLink}
        disabled={!email || submitting}
        className="w-full px-4 py-2 bg-blue-600 text-white rounded disabled:bg-gray-300"
      >
        {submitting ? '发送中...' : '发送登录链接'}
      </button>

      <div className="text-center text-gray-400 my-3 text-xs">— 或 —</div>

      <button
        onClick={signInWithGoogle}
        className="w-full px-4 py-2 border rounded hover:bg-gray-50"
      >
        使用 Google 登录
      </button>

      {msg && (
        <div className={`mt-3 text-sm ${msg.startsWith('✓') ? 'text-green-600' : 'text-red-600'}`}>
          {msg}
        </div>
      )}

      <div className="mt-6 pt-4 border-t text-xs text-gray-500 space-y-1">
        <div>🔒 数据隐私</div>
        <div>• 持仓数据仅用于本站信号叠加</div>
        <div>• 不与任何第三方共享</div>
        <div>• 不构成投资建议</div>
      </div>
    </div>
  );
};
```

- [ ] **Step 4: 跑测试确认通过**

```bash
cd frontend && npx vitest run src/components/portfolio/__tests__/AuthGate.test.tsx
```

期望：4 个测试全 PASS。

---

## Task 1.8：portfolio 类型定义

**Files:**
- Create: `frontend/src/lib/portfolio/types.ts`

- [ ] **Step 1: 创建 types**

```ts
// frontend/src/lib/portfolio/types.ts

import { z } from 'zod';

// ========== 持仓（Supabase 表对应） ==========
export const HoldingSchema = z.object({
  id:          z.string().uuid(),
  user_id:     z.string().uuid(),
  etf_code:    z.string().regex(/^\d{6}$/, '必须是 6 位数字代码'),
  shares:      z.number().positive(),
  cost_price:  z.number().positive().nullable(),
  note:        z.string().nullable(),
  created_at:  z.string(),
  updated_at:  z.string(),
});
export type Holding = z.infer<typeof HoldingSchema>;

// ========== 信号融合产物 ==========
export interface Strength {
  short:     number;
  mid:       number;
  long:      number;
  composite: number;
}

export type StrengthTag = '偏强' | '中性偏强' | '中性偏弱' | '偏弱';
export type MomentumTag = '动量向上' | '动量向下';
export type Quadrant    = 'leading' | 'weakening' | 'following' | 'weak';
export type SignalKind  = 'resonance' | 'transmission' | 'divergence';

export interface HoldingScore {
  etfCode: string;
  status:  'covered' | 'uncovered';

  // 基础信息（两种都有）
  name?:        string;
  shares:       number;
  costPrice:    number | null;
  currentPrice: number | null;
  marketValue:  number | null;
  pnlPct:       number | null;
  pnlAbs:       number | null;

  // 仅 covered
  selfStrength?:    Strength;
  themeId?:         string;
  themeName?:       string;
  themeUsStrength?: Strength;
  themeCnStrength?: Strength;
  themeSignal?:     SignalKind;
  quadrant?:        Quadrant;
  l2Tag?:           StrengthTag;
  momentumTag?:     MomentumTag | null;
  narrative?:       string;
}

// ========== 引擎输入（轻量重定义，避免依赖 zod schemas） ==========
export interface ThemeMetric {
  id:           string;
  name:         string;
  primary_cn:   string;
  strength:     Strength;
  us_strength?: Strength;
  cn_strength?: Strength;
}

export interface EtfMetric {
  code:          string;
  name:          string;
  tracking_index?: string;
  price:         number;
  strength:      Strength;
}

export interface ThemeSignalEntry {
  theme_id: string;
  signal:   SignalKind;
}

export interface ScoreInputs {
  holdings:     Holding[];
  themes:       ThemeMetric[];
  etfs:         EtfMetric[];
  themeSignals: ThemeSignalEntry[];
}
```

- [ ] **Step 2: 验收 TypeScript 编译**

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -10
```

期望：无错。

---

## Task 1.9：rules.ts (L2 标签 + L1 narrative) + 单测

**Files:**
- Create: `frontend/src/lib/portfolio/rules.ts`
- Create: `frontend/src/lib/portfolio/__tests__/rules.test.ts`

- [ ] **Step 1: 写测试**

创建 `frontend/src/lib/portfolio/__tests__/rules.test.ts`：

```ts
import { describe, it, expect } from 'vitest';
import { strengthTag, momentumTag, quadrantLabel, buildNarrative, computeQuadrant } from '../rules';
import type { HoldingScore, Strength } from '../types';

describe('strengthTag', () => {
  it.each([
    [0,   '偏弱'],
    [24,  '偏弱'],
    [25,  '中性偏弱'],
    [49,  '中性偏弱'],
    [50,  '中性偏强'],
    [74,  '中性偏强'],
    [75,  '偏强'],
    [100, '偏强'],
  ])('composite=%i → %s', (c, expected) => {
    expect(strengthTag(c)).toBe(expected);
  });
});

describe('momentumTag', () => {
  it('short>=70 && mid>=60 → 动量向上', () => {
    expect(momentumTag(70, 60)).toBe('动量向上');
    expect(momentumTag(85, 75)).toBe('动量向上');
  });
  it('short<=30 && mid<=40 → 动量向下', () => {
    expect(momentumTag(30, 40)).toBe('动量向下');
    expect(momentumTag(10, 20)).toBe('动量向下');
  });
  it('其他 → null', () => {
    expect(momentumTag(50, 50)).toBeNull();
    expect(momentumTag(70, 50)).toBeNull();
    expect(momentumTag(30, 50)).toBeNull();
  });
});

describe('computeQuadrant', () => {
  // X=long, Y=short, 中线 50
  it.each([
    [75, 75, 'leading'],
    [75, 25, 'weakening'],
    [25, 75, 'following'],
    [25, 25, 'weak'],
    [50, 50, 'leading'],   // 边界归 leading（>= 50）
  ])('long=%i short=%i → %s', (long, short, expected) => {
    expect(computeQuadrant({ short, mid: 0, long, composite: 0 } as Strength)).toBe(expected);
  });
});

describe('quadrantLabel', () => {
  it('returns Chinese labels', () => {
    expect(quadrantLabel('leading')).toBe('领涨象限');
    expect(quadrantLabel('weakening')).toBe('转弱象限');
    expect(quadrantLabel('following')).toBe('跟随象限');
    expect(quadrantLabel('weak')).toBe('弱势象限');
  });
});

describe('buildNarrative', () => {
  const base: Partial<HoldingScore> = {
    quadrant: 'leading',
    selfStrength: { short: 90, mid: 80, long: 95, composite: 88 },
  };

  it('强势 + mid 强 + 共振', () => {
    const s = { ...base, themeSignal: 'resonance' } as HoldingScore;
    expect(buildNarrative(s)).toContain('位于领涨象限');
    expect(buildNarrative(s)).toContain('综合强度 88 分位');
    expect(buildNarrative(s)).toContain('中周期强劲');
    expect(buildNarrative(s)).toContain('美股 A 股共振');
  });

  it('弱势 + mid 弱 + 背离', () => {
    const s: HoldingScore = {
      etfCode: 'X',
      status:  'covered',
      shares:  1, costPrice: null, currentPrice: null, marketValue: null, pnlPct: null, pnlAbs: null,
      quadrant: 'weak',
      selfStrength: { short: 10, mid: 15, long: 12, composite: 13 },
      themeSignal:  'divergence',
    };
    const n = buildNarrative(s);
    expect(n).toContain('弱势象限');
    expect(n).toContain('中周期走弱');
    expect(n).toContain('美股 A 股背离');
  });

  it('中性 mid → 不输出中周期标签', () => {
    const s: HoldingScore = {
      etfCode: 'X', status: 'covered',
      shares: 1, costPrice: null, currentPrice: null, marketValue: null, pnlPct: null, pnlAbs: null,
      quadrant: 'leading',
      selfStrength: { short: 60, mid: 50, long: 60, composite: 57 },
    };
    expect(buildNarrative(s)).not.toContain('中周期');
  });

  it('绝不出现"建议/买入/卖出/加仓/减仓"', () => {
    const s: HoldingScore = {
      etfCode: 'X', status: 'covered',
      shares: 1, costPrice: null, currentPrice: null, marketValue: null, pnlPct: null, pnlAbs: null,
      quadrant: 'weak',
      selfStrength: { short: 10, mid: 10, long: 10, composite: 10 },
      themeSignal:  'divergence',
    };
    const n = buildNarrative(s);
    expect(n).not.toMatch(/建议|买入|卖出|加仓|减仓/);
  });
});
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd frontend && npx vitest run src/lib/portfolio/__tests__/rules.test.ts
```

- [ ] **Step 3: 实现 rules.ts**

创建 `frontend/src/lib/portfolio/rules.ts`：

```ts
import type { HoldingScore, Strength, StrengthTag, MomentumTag, Quadrant } from './types';

export function strengthTag(composite: number): StrengthTag {
  if (composite >= 75) return '偏强';
  if (composite >= 50) return '中性偏强';
  if (composite >= 25) return '中性偏弱';
  return '偏弱';
}

export function momentumTag(short: number, mid: number): MomentumTag | null {
  if (short >= 70 && mid >= 60) return '动量向上';
  if (short <= 30 && mid <= 40) return '动量向下';
  return null;
}

export function computeQuadrant(s: Strength): Quadrant {
  const longHigh  = s.long  >= 50;
  const shortHigh = s.short >= 50;
  if (longHigh  && shortHigh) return 'leading';
  if (longHigh  && !shortHigh) return 'weakening';
  if (!longHigh && shortHigh) return 'following';
  return 'weak';
}

export function quadrantLabel(q: Quadrant): string {
  switch (q) {
    case 'leading':   return '领涨象限';
    case 'weakening': return '转弱象限';
    case 'following': return '跟随象限';
    case 'weak':      return '弱势象限';
  }
}

export function buildNarrative(score: HoldingScore): string {
  if (score.status !== 'covered' || !score.quadrant || !score.selfStrength) {
    return '';
  }
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

- [ ] **Step 4: 跑测试确认通过**

```bash
cd frontend && npx vitest run src/lib/portfolio/__tests__/rules.test.ts
```

期望：所有边界值测试 PASS。

---

## Task 1.10：engine.ts (主评分函数) + fixtures + 单测

**Files:**
- Create: `frontend/src/lib/portfolio/engine.ts`
- Create: `frontend/src/lib/portfolio/__tests__/__fixtures__/themes-mock.ts`
- Create: `frontend/src/lib/portfolio/__tests__/__fixtures__/etfs-mock.ts`
- Create: `frontend/src/lib/portfolio/__tests__/engine.test.ts`

- [ ] **Step 1: 写 fixtures**

创建 `frontend/src/lib/portfolio/__tests__/__fixtures__/themes-mock.ts`：

```ts
import type { ThemeMetric, ThemeSignalEntry } from '@/lib/portfolio/types';

export const themesMock: ThemeMetric[] = [
  {
    id: 'storage_dram',
    name: '存储芯片',
    primary_cn: '512480',
    strength:    { short: 95, mid: 99, long: 99, composite: 98 },  // 不直接用
    us_strength: { short: 99, mid: 96, long: 99, composite: 98 },
    cn_strength: { short: 96, mid: 99, long: 98, composite: 98 },
  },
  {
    id: 'weak_theme',
    name: '弱势主题',
    primary_cn: '999999',
    strength:    { short: 10, mid: 10, long: 10, composite: 10 },
    us_strength: { short: 10, mid: 10, long: 10, composite: 10 },
    cn_strength: { short: 12, mid: 8,  long: 11, composite: 10 },
  },
];

export const themeSignalsMock: ThemeSignalEntry[] = [
  { theme_id: 'storage_dram', signal: 'resonance' },
  { theme_id: 'weak_theme',   signal: 'divergence' },
];
```

创建 `frontend/src/lib/portfolio/__tests__/__fixtures__/etfs-mock.ts`：

```ts
import type { EtfMetric } from '@/lib/portfolio/types';

export const etfsMock: EtfMetric[] = [
  {
    code: '512480',
    name: '半导体ETF国联安',
    tracking_index: '中证全指半导体',
    price: 2.481,
    strength: { short: 95, mid: 99, long: 99, composite: 98 },
  },
  {
    code: '999999',
    name: '弱势ETF',
    price: 1.0,
    strength: { short: 10, mid: 10, long: 10, composite: 10 },
  },
];
```

- [ ] **Step 2: 写 engine 测试**

创建 `frontend/src/lib/portfolio/__tests__/engine.test.ts`：

```ts
import { describe, it, expect } from 'vitest';
import { scorePortfolio } from '../engine';
import { themesMock, themeSignalsMock } from './__fixtures__/themes-mock';
import { etfsMock } from './__fixtures__/etfs-mock';
import type { Holding } from '../types';

const baseHolding = (etf_code: string, shares: number, cost_price: number | null = null): Holding => ({
  id:          `id-${etf_code}`,
  user_id:     'user-1',
  etf_code,
  shares,
  cost_price,
  note:        null,
  created_at:  '2026-06-21T00:00:00Z',
  updated_at:  '2026-06-21T00:00:00Z',
});

describe('scorePortfolio', () => {
  it('covered ETF: 完整字段填充', () => {
    const result = scorePortfolio({
      holdings: [baseHolding('512480', 1000, 2.0)],
      themes: themesMock,
      etfs: etfsMock,
      themeSignals: themeSignalsMock,
    });
    expect(result).toHaveLength(1);
    const s = result[0];
    expect(s.status).toBe('covered');
    expect(s.name).toBe('半导体ETF国联安');
    expect(s.themeId).toBe('storage_dram');
    expect(s.themeName).toBe('存储芯片');
    expect(s.themeSignal).toBe('resonance');
    expect(s.l2Tag).toBe('偏强');
    expect(s.momentumTag).toBe('动量向上');
    expect(s.quadrant).toBe('leading');
    expect(s.narrative).toContain('领涨象限');
  });

  it('covered ETF: 盈亏计算正确', () => {
    const result = scorePortfolio({
      holdings: [baseHolding('512480', 1000, 2.0)],  // 现价 2.481, 成本 2.0
      themes: themesMock,
      etfs: etfsMock,
      themeSignals: themeSignalsMock,
    });
    const s = result[0];
    expect(s.currentPrice).toBe(2.481);
    expect(s.marketValue).toBeCloseTo(2481, 1);
    expect(s.pnlAbs).toBeCloseTo(481, 1);
    expect(s.pnlPct).toBeCloseTo(0.2405, 3);
  });

  it('covered ETF: 无 cost_price 时盈亏为 null', () => {
    const result = scorePortfolio({
      holdings: [baseHolding('512480', 1000, null)],
      themes: themesMock,
      etfs: etfsMock,
      themeSignals: themeSignalsMock,
    });
    expect(result[0].pnlAbs).toBeNull();
    expect(result[0].pnlPct).toBeNull();
    expect(result[0].marketValue).toBeCloseTo(2481, 1);  // 市值仍可算
  });

  it('uncovered ETF: status=uncovered, 无主题字段', () => {
    const result = scorePortfolio({
      holdings: [baseHolding('510300', 500, 1.85)],  // 不在 etfsMock 内
      themes: themesMock,
      etfs: etfsMock,
      themeSignals: themeSignalsMock,
    });
    expect(result).toHaveLength(1);
    const s = result[0];
    expect(s.status).toBe('uncovered');
    expect(s.themeId).toBeUndefined();
    expect(s.themeSignal).toBeUndefined();
    expect(s.currentPrice).toBeNull();
    expect(s.marketValue).toBeNull();
    expect(s.l2Tag).toBeUndefined();
    expect(s.narrative).toBeUndefined();
  });

  it('混合：covered + uncovered 同时输出', () => {
    const result = scorePortfolio({
      holdings: [
        baseHolding('512480', 1000, 2.0),
        baseHolding('510300', 500, 1.85),
      ],
      themes: themesMock,
      etfs: etfsMock,
      themeSignals: themeSignalsMock,
    });
    expect(result).toHaveLength(2);
    expect(result.find(s => s.etfCode === '512480')?.status).toBe('covered');
    expect(result.find(s => s.etfCode === '510300')?.status).toBe('uncovered');
  });

  it('弱势 covered: l2Tag=偏弱, momentum=动量向下, 包含背离', () => {
    const result = scorePortfolio({
      holdings: [baseHolding('999999', 100, 1.0)],
      themes: themesMock,
      etfs: etfsMock,
      themeSignals: themeSignalsMock,
    });
    const s = result[0];
    expect(s.l2Tag).toBe('偏弱');
    expect(s.momentumTag).toBe('动量向下');
    expect(s.quadrant).toBe('weak');
    expect(s.narrative).toContain('背离');
  });

  it('空持仓输入 → 空数组', () => {
    expect(scorePortfolio({
      holdings: [], themes: themesMock, etfs: etfsMock, themeSignals: themeSignalsMock,
    })).toEqual([]);
  });
});
```

- [ ] **Step 3: 跑测试确认失败**

```bash
cd frontend && npx vitest run src/lib/portfolio/__tests__/engine.test.ts
```

- [ ] **Step 4: 实现 engine**

创建 `frontend/src/lib/portfolio/engine.ts`：

```ts
import type {
  Holding, HoldingScore, ScoreInputs,
  ThemeMetric, EtfMetric, ThemeSignalEntry,
} from './types';
import { strengthTag, momentumTag, computeQuadrant, buildNarrative } from './rules';

export function scorePortfolio(inputs: ScoreInputs): HoldingScore[] {
  const etfByCode    = new Map<string, EtfMetric>(inputs.etfs.map(e => [e.code, e]));
  const themeByPrimaryCn = new Map<string, ThemeMetric>(
    inputs.themes.map(t => [t.primary_cn, t]),
  );
  const signalByTheme = new Map<string, ThemeSignalEntry>(
    inputs.themeSignals.map(s => [s.theme_id, s]),
  );

  return inputs.holdings.map(h => buildScore(h, etfByCode, themeByPrimaryCn, signalByTheme));
}

function buildScore(
  h: Holding,
  etfByCode: Map<string, EtfMetric>,
  themeByPrimaryCn: Map<string, ThemeMetric>,
  signalByTheme: Map<string, ThemeSignalEntry>,
): HoldingScore {
  const etf = etfByCode.get(h.etf_code);

  if (!etf) {
    // uncovered
    return {
      etfCode:      h.etf_code,
      status:       'uncovered',
      shares:       h.shares,
      costPrice:    h.cost_price,
      currentPrice: null,
      marketValue:  null,
      pnlPct:       null,
      pnlAbs:       null,
    };
  }

  // covered
  const theme = themeByPrimaryCn.get(h.etf_code);
  const signal = theme ? signalByTheme.get(theme.id) : undefined;
  const quadrant = computeQuadrant(etf.strength);
  const l2Tag = strengthTag(etf.strength.composite);
  const mTag  = momentumTag(etf.strength.short, etf.strength.mid);

  const marketValue = h.shares * etf.price;
  const pnlAbs = h.cost_price !== null
    ? (etf.price - h.cost_price) * h.shares
    : null;
  const pnlPct = h.cost_price !== null && h.cost_price > 0
    ? (etf.price - h.cost_price) / h.cost_price
    : null;

  const score: HoldingScore = {
    etfCode:      h.etf_code,
    status:       'covered',
    name:         etf.name,
    shares:       h.shares,
    costPrice:    h.cost_price,
    currentPrice: etf.price,
    marketValue,
    pnlAbs,
    pnlPct,
    selfStrength: etf.strength,
    themeId:      theme?.id,
    themeName:    theme?.name,
    themeUsStrength: theme?.us_strength,
    themeCnStrength: theme?.cn_strength,
    themeSignal:  signal?.signal,
    quadrant,
    l2Tag,
    momentumTag:  mTag,
  };
  score.narrative = buildNarrative(score);
  return score;
}
```

- [ ] **Step 5: 跑测试确认通过**

```bash
cd frontend && npx vitest run src/lib/portfolio/__tests__/engine.test.ts
```

期望：7 个测试全 PASS。

---

## Task 1.11：useHoldings hook（read + realtime）

**Files:**
- Create: `frontend/src/hooks/useHoldings.ts`
- Create: `frontend/src/hooks/__tests__/useHoldings.test.tsx`

- [ ] **Step 1: 写测试（mock Supabase）**

创建 `frontend/src/hooks/__tests__/useHoldings.test.tsx`：

```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { AuthContext } from '@/providers/authContext';
import { useHoldings } from '../useHoldings';
import type { ReactNode } from 'react';

const fakeHoldings = [
  { id: '1', user_id: 'u', etf_code: '512480', shares: 100, cost_price: 2.0, note: null, created_at: '2026-01-01', updated_at: '2026-01-01' },
];

const selectMock = vi.fn();
const upsertMock = vi.fn();
const deleteMock = vi.fn();
const channelMock = vi.fn();

vi.mock('@/lib/supabase', () => ({
  isSupabaseConfigured: () => true,
  getSupabase: () => ({
    from: vi.fn(() => ({
      select: selectMock,
      upsert: upsertMock,
      delete: () => ({ eq: deleteMock }),
    })),
    channel: channelMock,
  }),
}));

const wrapper = (status: 'authenticated' | 'anonymous') => ({ children }: { children: ReactNode }) => (
  <AuthContext.Provider value={{
    status,
    user: status === 'authenticated' ? { id: 'u', email: 't@e.com' } as never : null,
    signInWithMagicLink: vi.fn(),
    signInWithGoogle:    vi.fn(),
    signOut:             vi.fn(),
  }}>
    {children}
  </AuthContext.Provider>
);

describe('useHoldings', () => {
  beforeEach(() => {
    selectMock.mockReset();
    channelMock.mockReset();
    channelMock.mockReturnValue({
      on: () => ({ subscribe: vi.fn(() => ({ unsubscribe: vi.fn() })) }),
    });
  });

  it('anonymous: 返回空数组 + loading=false', () => {
    const { result } = renderHook(() => useHoldings(), { wrapper: wrapper('anonymous') });
    expect(result.current.holdings).toEqual([]);
    expect(result.current.loading).toBe(false);
  });

  it('authenticated: 拉取持仓', async () => {
    selectMock.mockResolvedValue({ data: fakeHoldings, error: null });
    const { result } = renderHook(() => useHoldings(), { wrapper: wrapper('authenticated') });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.holdings).toHaveLength(1);
    expect(result.current.holdings[0].etf_code).toBe('512480');
  });
});
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd frontend && npx vitest run src/hooks/__tests__/useHoldings.test.tsx
```

- [ ] **Step 3: 实现 useHoldings**

创建 `frontend/src/hooks/useHoldings.ts`：

```ts
import { useEffect, useState, useCallback } from 'react';
import { isSupabaseConfigured, getSupabase } from '@/lib/supabase';
import { HoldingSchema, type Holding } from '@/lib/portfolio/types';
import { useAuth } from './useAuth';

export interface UseHoldingsResult {
  holdings: Holding[];
  loading:  boolean;
  error:    string | null;
  upsert:   (input: UpsertInput) => Promise<{ error: string | null; merged?: boolean }>;
  remove:   (etfCode: string) => Promise<{ error: string | null }>;
  refresh:  () => Promise<void>;
}

export interface UpsertInput {
  etf_code:   string;
  shares:     number;
  cost_price: number | null;
  note?:      string | null;
}

export function useHoldings(): UseHoldingsResult {
  const { user, status } = useAuth();
  const [holdings, setHoldings] = useState<Holding[]>([]);
  const [loading, setLoading]   = useState(false);
  const [error, setError]       = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!user || !isSupabaseConfigured()) {
      setHoldings([]);
      return;
    }
    setLoading(true);
    setError(null);
    const { data, error } = await getSupabase()
      .from('user_holdings')
      .select('*')
      .order('created_at', { ascending: false });
    if (error) {
      setError(error.message);
      setHoldings([]);
    } else {
      const parsed = (data ?? [])
        .map(r => HoldingSchema.safeParse(r))
        .filter(p => p.success)
        .map(p => p.data!);
      setHoldings(parsed);
    }
    setLoading(false);
  }, [user]);

  // 初始拉取
  useEffect(() => {
    if (status === 'authenticated') {
      refresh();
    } else {
      setHoldings([]);
      setLoading(false);
    }
  }, [status, refresh]);

  // Realtime 订阅
  useEffect(() => {
    if (status !== 'authenticated' || !isSupabaseConfigured()) return;
    const sub = getSupabase()
      .channel('user_holdings_changes')
      .on('postgres_changes', { event: '*', schema: 'public', table: 'user_holdings' }, () => {
        refresh();
      })
      .subscribe();
    return () => { sub.unsubscribe(); };
  }, [status, refresh]);

  // upsert：检测重复 → 合并加权平均成本
  const upsert = useCallback(async (input: UpsertInput) => {
    if (!user) return { error: '未登录' };

    const existing = holdings.find(h => h.etf_code === input.etf_code);
    let mergedShares = input.shares;
    let mergedCost   = input.cost_price;
    let merged       = false;

    if (existing) {
      merged = true;
      mergedShares = existing.shares + input.shares;
      // 加权平均成本（双方有 cost_price 才合并）
      if (existing.cost_price !== null && input.cost_price !== null) {
        mergedCost = (existing.cost_price * existing.shares + input.cost_price * input.shares) / mergedShares;
      } else {
        mergedCost = existing.cost_price ?? input.cost_price;
      }
    }

    const payload = {
      user_id:    user.id,
      etf_code:   input.etf_code,
      shares:     mergedShares,
      cost_price: mergedCost,
      note:       input.note ?? null,
    };

    const { error } = await getSupabase()
      .from('user_holdings')
      .upsert(payload, { onConflict: 'user_id,etf_code' });

    if (error) return { error: error.message };
    await refresh();
    return { error: null, merged };
  }, [user, holdings, refresh]);

  const remove = useCallback(async (etfCode: string) => {
    if (!user) return { error: '未登录' };
    const { error } = await getSupabase()
      .from('user_holdings')
      .delete()
      .eq('etf_code', etfCode);
    if (error) return { error: error.message };
    await refresh();
    return { error: null };
  }, [user, refresh]);

  return { holdings, loading, error, upsert, remove, refresh };
}
```

- [ ] **Step 4: 跑测试确认通过**

```bash
cd frontend && npx vitest run src/hooks/__tests__/useHoldings.test.tsx
```

期望：2 个测试 PASS。

---

## Task 1.12：usePortfolioScores hook（融合 holdings + JSON）

**Files:**
- Create: `frontend/src/hooks/usePortfolioScores.ts`

> 复用 `useHoldings` + DataProvider 已有的 themes/etfs/signals JSON。无新 IO，只是组合。

- [ ] **Step 1: 读 DataProvider，确认它暴露 themes/etfs/signals**

```bash
cat frontend/src/providers/DataProvider.tsx
cat frontend/src/providers/dataContext.ts
cat frontend/src/hooks/useData.ts
```

确认能拿到 `themes`, `etfs`, `signals`（或类似命名）。如果命名不一致，下文中替换为实际命名。

- [ ] **Step 2: 实现 usePortfolioScores**

创建 `frontend/src/hooks/usePortfolioScores.ts`：

```ts
import { useMemo } from 'react';
import { useData } from './useData';
import { useHoldings } from './useHoldings';
import { scorePortfolio } from '@/lib/portfolio/engine';
import type { HoldingScore, ThemeMetric, EtfMetric, ThemeSignalEntry } from '@/lib/portfolio/types';

export interface UsePortfolioScoresResult {
  scores: HoldingScore[];
  loading: boolean;
  /** 命中的主题 id 集合（用于现有页 ⭐/金圈叠加） */
  ownedThemeIds: Set<string>;
}

export function usePortfolioScores(): UsePortfolioScoresResult {
  const { holdings, loading } = useHoldings();
  const data = useData();

  const scores = useMemo(() => {
    if (!data?.themes || !data?.etfs) return [];
    // 字段命名假设：data.themes / data.etfs / data.signals?.theme_signals
    // 若 useData 字段名不同，调整 mapping
    const themes: ThemeMetric[] = data.themes.map((t: any) => ({
      id: t.id, name: t.name, primary_cn: t.primary_cn,
      strength: t.strength, us_strength: t.us_strength ?? null, cn_strength: t.cn_strength ?? null,
    }));
    const etfs: EtfMetric[] = data.etfs.map((e: any) => ({
      code: e.code, name: e.name, tracking_index: e.tracking_index,
      price: e.price, strength: e.strength,
    }));
    const themeSignals: ThemeSignalEntry[] = (data.signals?.theme_signals ?? []).map((s: any) => ({
      theme_id: s.theme_id, signal: s.signal,
    }));

    return scorePortfolio({ holdings, themes, etfs, themeSignals });
  }, [holdings, data]);

  const ownedThemeIds = useMemo(() => {
    const set = new Set<string>();
    for (const s of scores) {
      if (s.themeId) set.add(s.themeId);
    }
    return set;
  }, [scores]);

  return { scores, loading, ownedThemeIds };
}
```

> 注：上面用 `any` cast 是兼容现有 DataProvider 可能用了自己的 zod 类型。如有现成类型，替换为之。

- [ ] **Step 3: 验收 — TS 编译通过**

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -10
```

期望：无错。

---

## Task 1.13：EtfCodeAutocomplete 子组件

**Files:**
- Create: `frontend/src/components/portfolio/EtfCodeAutocomplete.tsx`

- [ ] **Step 1: 实现**

```tsx
import { useState, useMemo } from 'react';
import { useData } from '@/hooks/useData';

interface Props {
  value:    string;
  onChange: (code: string, isCovered: boolean) => void;
}

export const EtfCodeAutocomplete = ({ value, onChange }: Props) => {
  const data = useData();
  const [query, setQuery] = useState(value);

  const allOptions = useMemo(() => {
    return (data?.etfs ?? []).map((e: any) => ({
      code: e.code as string,
      name: e.name as string,
      covered: true,
    }));
  }, [data]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return allOptions.slice(0, 8);
    return allOptions
      .filter(o => o.code.includes(q) || o.name.toLowerCase().includes(q))
      .slice(0, 8);
  }, [query, allOptions]);

  const handlePick = (code: string, isCovered: boolean) => {
    setQuery(code);
    onChange(code, isCovered);
  };

  const handleManualInput = (raw: string) => {
    setQuery(raw);
    // 任意 6 位代码都允许提交
    if (/^\d{6}$/.test(raw)) {
      const isCovered = allOptions.some(o => o.code === raw);
      onChange(raw, isCovered);
    }
  };

  return (
    <div className="relative">
      <input
        type="text"
        value={query}
        onChange={e => handleManualInput(e.target.value)}
        placeholder="ETF 代码或名称（如 512480、半导体）"
        className="w-full px-3 py-2 border rounded"
      />
      {filtered.length > 0 && query !== value && (
        <div className="absolute z-10 w-full mt-1 bg-white border rounded shadow-lg max-h-60 overflow-y-auto">
          {filtered.map(o => (
            <button
              key={o.code}
              type="button"
              onClick={() => handlePick(o.code, o.covered)}
              className="w-full text-left px-3 py-2 hover:bg-gray-100 flex justify-between items-center"
            >
              <span>{o.code} {o.name}</span>
              {o.covered && (
                <span className="text-xs px-2 py-0.5 bg-blue-100 text-blue-700 rounded">信号覆盖</span>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
};
```

- [ ] **Step 2: 验收 — TS 编译通过**

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -10
```

---

## Task 1.14：HoldingsEditor 模态

**Files:**
- Create: `frontend/src/components/portfolio/HoldingsEditor.tsx`
- Create: `frontend/src/components/portfolio/__tests__/HoldingsEditor.test.tsx`

- [ ] **Step 1: 写测试**

创建 `frontend/src/components/portfolio/__tests__/HoldingsEditor.test.tsx`：

```tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { HoldingsEditor } from '../HoldingsEditor';

// 简单 mock useData / useHoldings 让组件能渲染
vi.mock('@/hooks/useData', () => ({
  useData: () => ({ etfs: [{ code: '512480', name: '半导体ETF国联安' }] }),
}));

const upsertFn = vi.fn().mockResolvedValue({ error: null, merged: false });
vi.mock('@/hooks/useHoldings', () => ({
  useHoldings: () => ({
    holdings: [], loading: false, error: null,
    upsert: upsertFn, remove: vi.fn(), refresh: vi.fn(),
  }),
}));

describe('HoldingsEditor', () => {
  it('open 时渲染表单', () => {
    render(<HoldingsEditor open onClose={vi.fn()} />);
    expect(screen.getByText('添加持仓')).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/ETF 代码/)).toBeInTheDocument();
  });

  it('不 open 时不渲染', () => {
    render(<HoldingsEditor open={false} onClose={vi.fn()} />);
    expect(screen.queryByText('添加持仓')).toBeNull();
  });

  it('提交：调用 upsert', async () => {
    upsertFn.mockClear();
    render(<HoldingsEditor open onClose={vi.fn()} />);
    fireEvent.change(screen.getByPlaceholderText(/ETF 代码/), { target: { value: '512480' } });
    fireEvent.change(screen.getByLabelText(/持有份额/), { target: { value: '1000' } });
    fireEvent.click(screen.getByRole('button', { name: /保存/ }));
    // upsert 是 async，等一个 tick
    await new Promise(r => setTimeout(r, 0));
    expect(upsertFn).toHaveBeenCalledWith(expect.objectContaining({
      etf_code: '512480',
      shares: 1000,
    }));
  });
});
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd frontend && npx vitest run src/components/portfolio/__tests__/HoldingsEditor.test.tsx
```

- [ ] **Step 3: 实现 HoldingsEditor**

创建 `frontend/src/components/portfolio/HoldingsEditor.tsx`：

```tsx
import { useState } from 'react';
import { useHoldings } from '@/hooks/useHoldings';
import { EtfCodeAutocomplete } from './EtfCodeAutocomplete';

interface Props {
  open:    boolean;
  onClose: () => void;
}

export const HoldingsEditor = ({ open, onClose }: Props) => {
  const { upsert } = useHoldings();
  const [code, setCode]       = useState('');
  const [isCovered, setCovered] = useState(false);
  const [shares, setShares]   = useState('');
  const [cost, setCost]       = useState('');
  const [note, setNote]       = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [msg, setMsg]         = useState<string | null>(null);

  if (!open) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!/^\d{6}$/.test(code)) {
      setMsg('请输入 6 位 ETF 代码');
      return;
    }
    const sharesNum = parseFloat(shares);
    if (!sharesNum || sharesNum <= 0) {
      setMsg('请输入有效份额');
      return;
    }
    setSubmitting(true);
    setMsg(null);
    const costNum = cost ? parseFloat(cost) : null;
    const { error, merged } = await upsert({
      etf_code:   code,
      shares:     sharesNum,
      cost_price: costNum && costNum > 0 ? costNum : null,
      note:       note || null,
    });
    setSubmitting(false);
    if (error) {
      setMsg(`保存失败：${error}`);
      return;
    }
    if (!isCovered) {
      setMsg('✓ 已保存（该 ETF 不在 14 主题覆盖范围内，仅记录持仓）');
    } else if (merged) {
      setMsg('✓ 已合并到现有持仓');
    } else {
      setMsg('✓ 已保存');
    }
    // 短暂展示后关闭
    setTimeout(() => { resetAndClose(); }, 1200);
  };

  const resetAndClose = () => {
    setCode(''); setCovered(false); setShares(''); setCost(''); setNote(''); setMsg(null);
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="bg-white rounded-lg shadow-xl max-w-md w-full">
        <div className="flex justify-between items-center p-4 border-b">
          <h3 className="text-lg font-semibold">添加持仓</h3>
          <button onClick={resetAndClose} className="text-gray-400 hover:text-gray-700">✕</button>
        </div>
        <form onSubmit={handleSubmit} className="p-4 space-y-3">
          <div>
            <label className="block text-sm font-medium mb-1">ETF 代码或名称</label>
            <EtfCodeAutocomplete value={code} onChange={(c, covered) => { setCode(c); setCovered(covered); }} />
          </div>
          <div>
            <label htmlFor="shares" className="block text-sm font-medium mb-1">持有份额 *</label>
            <input
              id="shares" type="number" step="any" min="0.0001"
              value={shares} onChange={e => setShares(e.target.value)}
              className="w-full px-3 py-2 border rounded" required
            />
          </div>
          <div>
            <label htmlFor="cost" className="block text-sm font-medium mb-1">平均成本（可选）</label>
            <input
              id="cost" type="number" step="any" min="0"
              value={cost} onChange={e => setCost(e.target.value)}
              className="w-full px-3 py-2 border rounded"
            />
          </div>
          <div>
            <label htmlFor="note" className="block text-sm font-medium mb-1">备注（可选）</label>
            <textarea
              id="note" rows={2}
              value={note} onChange={e => setNote(e.target.value)}
              className="w-full px-3 py-2 border rounded"
            />
          </div>
          {msg && (
            <div className={`text-sm ${msg.startsWith('✓') ? 'text-green-600' : 'text-red-600'}`}>
              {msg}
            </div>
          )}
          <div className="flex justify-end gap-2 pt-2">
            <button type="button" onClick={resetAndClose} className="px-4 py-2 border rounded">取消</button>
            <button type="submit" disabled={submitting} className="px-4 py-2 bg-blue-600 text-white rounded disabled:bg-gray-300">
              {submitting ? '保存中...' : '保存'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
```

- [ ] **Step 4: 跑测试确认通过**

```bash
cd frontend && npx vitest run src/components/portfolio/__tests__/HoldingsEditor.test.tsx
```

期望：3 个测试 PASS。

---

## Task 1.15：HoldingScoreCard 组件（covered + uncovered）

**Files:**
- Create: `frontend/src/components/portfolio/HoldingScoreCard.tsx`
- Create: `frontend/src/components/portfolio/__tests__/HoldingScoreCard.test.tsx`

- [ ] **Step 1: 写测试**

创建 `frontend/src/components/portfolio/__tests__/HoldingScoreCard.test.tsx`：

```tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { HoldingScoreCard } from '../HoldingScoreCard';
import type { HoldingScore } from '@/lib/portfolio/types';

const coveredScore: HoldingScore = {
  etfCode: '512480',
  status: 'covered',
  name: '半导体ETF国联安',
  shares: 1000,
  costPrice: 2.0,
  currentPrice: 2.48,
  marketValue: 2480,
  pnlAbs: 480,
  pnlPct: 0.24,
  selfStrength: { short: 95, mid: 99, long: 99, composite: 98 },
  themeName: '存储芯片',
  themeId: 'storage_dram',
  themeSignal: 'resonance',
  themeUsStrength: { short: 99, mid: 96, long: 99, composite: 98 },
  themeCnStrength: { short: 96, mid: 99, long: 98, composite: 98 },
  quadrant: 'leading',
  l2Tag: '偏强',
  momentumTag: '动量向上',
  narrative: '位于领涨象限，综合强度 98 分位，中周期强劲，美股 A 股共振',
};

const uncoveredScore: HoldingScore = {
  etfCode: '159928',
  status: 'uncovered',
  shares: 500,
  costPrice: 1.85,
  currentPrice: null,
  marketValue: null,
  pnlAbs: null,
  pnlPct: null,
};

describe('HoldingScoreCard', () => {
  it('covered: 渲染所有字段', () => {
    render(<HoldingScoreCard score={coveredScore} onDelete={vi.fn()} />);
    expect(screen.getByText('512480')).toBeInTheDocument();
    expect(screen.getByText(/半导体ETF国联安/)).toBeInTheDocument();
    expect(screen.getByText('偏强')).toBeInTheDocument();
    expect(screen.getByText('动量向上')).toBeInTheDocument();
    expect(screen.getByText(/存储芯片/)).toBeInTheDocument();
    expect(screen.getByText(/位于领涨象限/)).toBeInTheDocument();
    expect(screen.getByText(/共振/)).toBeInTheDocument();
  });

  it('uncovered: 显示灰版 + 无信号提示', () => {
    render(<HoldingScoreCard score={uncoveredScore} onDelete={vi.fn()} />);
    expect(screen.getByText('159928')).toBeInTheDocument();
    expect(screen.getByText(/无信号/)).toBeInTheDocument();
    expect(screen.getByText(/不在信号覆盖范围/)).toBeInTheDocument();
  });

  it('delete 按钮触发 onDelete', () => {
    const onDelete = vi.fn();
    // 用 confirm spy 让 confirm 返回 true
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    render(<HoldingScoreCard score={coveredScore} onDelete={onDelete} />);
    fireEvent.click(screen.getByRole('button', { name: /删除/ }));
    expect(onDelete).toHaveBeenCalledWith('512480');
  });
});
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd frontend && npx vitest run src/components/portfolio/__tests__/HoldingScoreCard.test.tsx
```

- [ ] **Step 3: 实现 HoldingScoreCard**

创建 `frontend/src/components/portfolio/HoldingScoreCard.tsx`：

```tsx
import type { HoldingScore } from '@/lib/portfolio/types';

interface Props {
  score:    HoldingScore;
  onDelete: (etfCode: string) => void;
}

const tagColor = (tag?: string) => {
  switch (tag) {
    case '偏强':       return 'bg-green-100 text-green-700';
    case '中性偏强':   return 'bg-green-50 text-green-600';
    case '中性偏弱':   return 'bg-orange-50 text-orange-600';
    case '偏弱':       return 'bg-red-100 text-red-700';
    case '动量向上':   return 'bg-blue-100 text-blue-700';
    case '动量向下':   return 'bg-amber-100 text-amber-700';
    default:           return 'bg-gray-100 text-gray-600';
  }
};

const fmtPct = (n: number | null) => n === null ? '—' : `${(n * 100).toFixed(1)}%`;
const fmtMoney = (n: number | null) => n === null ? '—' : `¥${n.toLocaleString('zh-CN', { maximumFractionDigits: 2 })}`;

export const HoldingScoreCard = ({ score, onDelete }: Props) => {
  const isUncovered = score.status === 'uncovered';

  const handleDelete = () => {
    if (window.confirm(`确定删除 ${score.etfCode} 的持仓记录吗？此操作不可恢复。`)) {
      onDelete(score.etfCode);
    }
  };

  return (
    <div className={`border rounded-lg p-4 ${isUncovered ? 'bg-gray-50 opacity-90' : 'bg-white'}`}>
      {/* Header */}
      <div className="flex justify-between items-start mb-2">
        <div>
          <div className="font-semibold">{score.etfCode}</div>
          {score.name && <div className="text-sm text-gray-600">{score.name}</div>}
        </div>
        <div className="flex flex-wrap gap-1 items-start">
          {isUncovered ? (
            <span className="text-xs px-2 py-0.5 rounded bg-gray-200 text-gray-600">无信号</span>
          ) : (
            <>
              {score.l2Tag && <span className={`text-xs px-2 py-0.5 rounded ${tagColor(score.l2Tag)}`}>{score.l2Tag}</span>}
              {score.momentumTag && <span className={`text-xs px-2 py-0.5 rounded ${tagColor(score.momentumTag)}`}>{score.momentumTag}</span>}
            </>
          )}
          <button onClick={handleDelete} title="删除" className="text-gray-400 hover:text-red-500 text-sm ml-1">
            ⋯
          </button>
        </div>
      </div>

      {/* 持仓 */}
      <div className="text-sm space-y-1 border-t pt-2">
        <div>持仓 {score.shares} 份 {score.costPrice !== null && `· 成本 ${fmtMoney(score.costPrice)}`}</div>
        {score.currentPrice !== null && (
          <div>现价 {fmtMoney(score.currentPrice)} · 市值 {fmtMoney(score.marketValue)}</div>
        )}
        {score.pnlAbs !== null && score.pnlPct !== null && (
          <div className={score.pnlAbs >= 0 ? 'text-green-600' : 'text-red-600'}>
            盈亏 {score.pnlAbs >= 0 ? '+' : ''}{fmtMoney(score.pnlAbs)} ({score.pnlAbs >= 0 ? '+' : ''}{fmtPct(score.pnlPct)})
          </div>
        )}
      </div>

      {/* uncovered 提示 */}
      {isUncovered && (
        <div className="mt-3 pt-2 border-t text-xs text-gray-500">
          ⓘ 该 ETF 不在信号覆盖范围（14 主题外），仅记录持仓信息
        </div>
      )}

      {/* covered: 信号区 */}
      {!isUncovered && score.themeName && (
        <div className="mt-3 pt-2 border-t text-sm space-y-2">
          <div className="text-gray-600">归属主题：<span className="font-medium text-gray-900">{score.themeName}</span></div>

          {score.themeUsStrength && score.selfStrength && (
            <div className="grid grid-cols-2 gap-2 text-xs">
              <div className="border rounded p-2">
                <div className="text-gray-500 mb-1">双轨强度（美/A）</div>
                <div>美 短{score.themeUsStrength.short} 中{score.themeUsStrength.mid} 长{score.themeUsStrength.long}</div>
                {score.themeCnStrength && (
                  <div>A 短{score.themeCnStrength.short} 中{score.themeCnStrength.mid} 长{score.themeCnStrength.long}</div>
                )}
              </div>
              <div className="border rounded p-2">
                <div className="text-gray-500 mb-1">ETF 自身百分位</div>
                <div>短 {score.selfStrength.short}</div>
                <div>中 {score.selfStrength.mid}</div>
                <div>长 {score.selfStrength.long}</div>
                <div>综合 {score.selfStrength.composite}</div>
              </div>
            </div>
          )}

          {score.narrative && (
            <div className="text-gray-700 text-xs leading-relaxed bg-gray-50 p-2 rounded">
              {score.narrative}
            </div>
          )}
        </div>
      )}
    </div>
  );
};
```

- [ ] **Step 4: 跑测试确认通过**

```bash
cd frontend && npx vitest run src/components/portfolio/__tests__/HoldingScoreCard.test.tsx
```

期望：3 个测试 PASS。

---

## Task 1.16：PortfolioSummary 组件

**Files:**
- Create: `frontend/src/components/portfolio/PortfolioSummary.tsx`
- Create: `frontend/src/components/portfolio/__tests__/PortfolioSummary.test.tsx`

- [ ] **Step 1: 写测试**

```tsx
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { PortfolioSummary } from '../PortfolioSummary';
import type { HoldingScore } from '@/lib/portfolio/types';

const mk = (overrides: Partial<HoldingScore>): HoldingScore => ({
  etfCode: 'X', status: 'covered',
  shares: 100, costPrice: 1.0, currentPrice: 1.5,
  marketValue: 150, pnlAbs: 50, pnlPct: 0.5,
  l2Tag: '偏强',
  ...overrides,
} as HoldingScore);

describe('PortfolioSummary', () => {
  it('全 covered: 汇总市值与盈亏', () => {
    render(<PortfolioSummary scores={[
      mk({ marketValue: 1000, pnlAbs: 100, pnlPct: 0.11 }),
      mk({ marketValue: 2000, pnlAbs: -50, pnlPct: -0.03 }),
    ]} />);
    expect(screen.getByText(/¥3,000/)).toBeInTheDocument();
    expect(screen.getByText(/覆盖率.*2.*\/.*2/)).toBeInTheDocument();
  });

  it('混合: 总市值仅含 covered, 附加 uncovered 数量', () => {
    render(<PortfolioSummary scores={[
      mk({ marketValue: 1000, pnlAbs: 100 }),
      mk({ status: 'uncovered', marketValue: null, pnlAbs: null }),
    ]} />);
    expect(screen.getByText(/¥1,000/)).toBeInTheDocument();
    expect(screen.getByText(/另含.*1.*只.*无估值/)).toBeInTheDocument();
    expect(screen.getByText(/覆盖率.*1.*\/.*2/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd frontend && npx vitest run src/components/portfolio/__tests__/PortfolioSummary.test.tsx
```

- [ ] **Step 3: 实现**

创建 `frontend/src/components/portfolio/PortfolioSummary.tsx`：

```tsx
import type { HoldingScore } from '@/lib/portfolio/types';

interface Props {
  scores: HoldingScore[];
}

export const PortfolioSummary = ({ scores }: Props) => {
  const covered = scores.filter(s => s.status === 'covered');
  const uncovered = scores.filter(s => s.status === 'uncovered');

  const totalMV = covered.reduce((sum, s) => sum + (s.marketValue ?? 0), 0);
  const totalPnl = covered
    .filter(s => s.pnlAbs !== null)
    .reduce((sum, s) => sum + (s.pnlAbs ?? 0), 0);
  const totalCost = covered
    .filter(s => s.pnlAbs !== null)
    .reduce((sum, s) => sum + ((s.marketValue ?? 0) - (s.pnlAbs ?? 0)), 0);
  const totalPnlPct = totalCost > 0 ? totalPnl / totalCost : null;

  const counts = {
    '偏强':     covered.filter(s => s.l2Tag === '偏强').length,
    '中性偏强': covered.filter(s => s.l2Tag === '中性偏强').length,
    '中性偏弱': covered.filter(s => s.l2Tag === '中性偏弱').length,
    '偏弱':     covered.filter(s => s.l2Tag === '偏弱').length,
  };

  if (scores.length === 0) return null;

  return (
    <div className="border-t border-b py-4 my-4 grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
      <div>
        <div className="text-gray-500">总市值</div>
        <div className="font-semibold text-lg">¥{totalMV.toLocaleString('zh-CN', { maximumFractionDigits: 0 })}</div>
        {uncovered.length > 0 && (
          <div className="text-xs text-gray-400">另含 {uncovered.length} 只无估值持仓</div>
        )}
      </div>
      <div>
        <div className="text-gray-500">总盈亏</div>
        <div className={`font-semibold text-lg ${totalPnl >= 0 ? 'text-green-600' : 'text-red-600'}`}>
          {totalPnl >= 0 ? '+' : ''}¥{Math.abs(totalPnl).toLocaleString('zh-CN', { maximumFractionDigits: 0 })}
        </div>
        {totalPnlPct !== null && (
          <div className={`text-xs ${totalPnl >= 0 ? 'text-green-600' : 'text-red-600'}`}>
            {totalPnl >= 0 ? '+' : ''}{(totalPnlPct * 100).toFixed(1)}%
          </div>
        )}
      </div>
      <div>
        <div className="text-gray-500">覆盖率</div>
        <div className="font-semibold text-lg">{covered.length} / {scores.length}</div>
      </div>
      <div>
        <div className="text-gray-500">强弱分布</div>
        <div className="text-xs space-x-2">
          {counts['偏强']     > 0 && <span className="text-green-700">偏强 {counts['偏强']}</span>}
          {counts['中性偏强'] > 0 && <span>中性偏强 {counts['中性偏强']}</span>}
          {counts['中性偏弱'] > 0 && <span>中性偏弱 {counts['中性偏弱']}</span>}
          {counts['偏弱']     > 0 && <span className="text-red-700">偏弱 {counts['偏弱']}</span>}
        </div>
      </div>
    </div>
  );
};
```

- [ ] **Step 4: 跑测试确认通过**

```bash
cd frontend && npx vitest run src/components/portfolio/__tests__/PortfolioSummary.test.tsx
```

期望：2 个测试 PASS。

---

## Task 1.17：HoldingsList 容器（含空态）

**Files:**
- Create: `frontend/src/components/portfolio/HoldingsList.tsx`

- [ ] **Step 1: 实现**

```tsx
import { useState } from 'react';
import { useHoldings } from '@/hooks/useHoldings';
import { usePortfolioScores } from '@/hooks/usePortfolioScores';
import { HoldingScoreCard } from './HoldingScoreCard';
import { HoldingsEditor } from './HoldingsEditor';
import { PortfolioSummary } from './PortfolioSummary';

export const HoldingsList = () => {
  const { remove } = useHoldings();
  const { scores, loading } = usePortfolioScores();
  const [editorOpen, setEditorOpen] = useState(false);

  if (loading) {
    return <div className="p-8 text-center text-gray-500">加载持仓...</div>;
  }

  return (
    <div>
      <div className="flex justify-between items-center mb-4">
        <h2 className="text-lg font-semibold">我的持仓（{scores.length} 只）</h2>
        <button
          onClick={() => setEditorOpen(true)}
          className="px-3 py-1.5 bg-blue-600 text-white rounded text-sm"
        >+ 添加持仓</button>
      </div>

      {scores.length === 0 ? (
        <div className="border rounded p-8 text-center bg-gray-50">
          <div className="text-gray-600 mb-2">还没有录入持仓</div>
          <div className="text-sm text-gray-500 mb-4">
            把您的 A 股 ETF 接入信号引擎，看看它们当下状态
          </div>
          <button
            onClick={() => setEditorOpen(true)}
            className="px-4 py-2 bg-blue-600 text-white rounded"
          >+ 添加第一只</button>
        </div>
      ) : (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {scores.map(s => (
              <HoldingScoreCard key={s.etfCode} score={s} onDelete={remove} />
            ))}
          </div>
          <PortfolioSummary scores={scores} />
        </>
      )}

      <HoldingsEditor open={editorOpen} onClose={() => setEditorOpen(false)} />
    </div>
  );
};
```

- [ ] **Step 2: 验收 TS 编译通过**

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -10
```

---

## Task 1.18：PortfolioPage 主页面

**Files:**
- Modify: `frontend/src/pages/PortfolioPage.tsx`

- [ ] **Step 1: 实现**

替换 `frontend/src/pages/PortfolioPage.tsx`：

```tsx
import { AuthGate } from '@/components/portfolio/AuthGate';
import { HoldingsList } from '@/components/portfolio/HoldingsList';

export const PortfolioPage = () => (
  <div className="max-w-6xl mx-auto p-4">
    <AuthGate>
      <HoldingsList />
    </AuthGate>
  </div>
);
```

- [ ] **Step 2: 验收**

```bash
cd frontend && npx tsc --noEmit && npx vitest run 2>&1 | tail -5
```

期望：TS 编译过；所有测试 PASS。

---

## Task 1.19：UserMenu（Header 用户菜单）

**Files:**
- Create: `frontend/src/components/Header/UserMenu.tsx`
- Modify: `frontend/src/components/Header/index.tsx`

- [ ] **Step 1: 实现 UserMenu**

```tsx
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '@/hooks/useAuth';

export const UserMenu = () => {
  const { status, user, signOut } = useAuth();
  const [open, setOpen] = useState(false);

  if (status === 'loading') return null;
  if (status === 'unconfigured') return null;

  if (status === 'anonymous') {
    return (
      <Link to="/portfolio" className="text-sm px-3 py-1 border rounded hover:bg-gray-50">
        登录
      </Link>
    );
  }

  const email = user?.email ?? '';
  const truncated = email.length > 20 ? email.slice(0, 17) + '...' : email;

  return (
    <div className="relative">
      <button
        onClick={() => setOpen(v => !v)}
        className="text-sm px-3 py-1 border rounded hover:bg-gray-50 flex items-center gap-1"
      >
        <span>📧 {truncated}</span>
        <span className="text-xs">▾</span>
      </button>
      {open && (
        <div className="absolute right-0 mt-1 min-w-[160px] bg-white border rounded shadow-lg z-50">
          <div className="px-3 py-2 text-xs text-gray-500 border-b">{email}</div>
          <button
            onClick={() => { signOut(); setOpen(false); }}
            className="w-full text-left px-3 py-2 text-sm hover:bg-gray-100"
          >
            退出登录
          </button>
        </div>
      )}
    </div>
  );
};
```

- [ ] **Step 2: 在 Header 中嵌入 UserMenu**

修改 `frontend/src/components/Header/index.tsx`：

```tsx
import { KpiCards } from './KpiCards';
import { StaleBanner } from './StaleBanner';
import { UpdateBadge } from './UpdateBadge';
import { RadarTabs } from './RadarTabs';
import { UserMenu } from './UserMenu';

export const Header = () => (
  <header className="border-b bg-white p-4 space-y-3">
    <div className="flex items-center justify-between">
      <div>
        <div className="text-xl font-bold">ETF Radar</div>
        <div className="text-xs text-gray-500">
          追踪美股主题 → 映射 A 股 ETF 联动信号
        </div>
      </div>
      <div className="flex items-center gap-3">
        <UpdateBadge />
        <UserMenu />
      </div>
    </div>
    <RadarTabs />
    <KpiCards />
    <StaleBanner />
  </header>
);
```

- [ ] **Step 3: 验收**

```bash
cd frontend && npx vitest run src/components/Header 2>&1 | tail -10
```

期望：现有 Header 测试 PASS。

---

## Task 1.20：现有页叠加 — RotationScatterWithTrails 接受 ownedThemeIds prop

**Files:**
- Modify: `frontend/src/components/rotation/RotationScatterWithTrails.tsx`
- Modify: `frontend/src/pages/RotationPage.tsx`

- [ ] **Step 1: 读现状 + 找气泡 SVG 渲染位置**

```bash
cat frontend/src/components/rotation/RotationScatterWithTrails.tsx | head -100
```

找到为每个气泡渲染 `<circle>` 或 `<g>` 的位置（通常按 theme.id 循环）。

- [ ] **Step 2: 加 prop 与金圈渲染**

在组件 Props 接口加：

```ts
interface Props {
  // ... 现有 props
  ownedThemeIds?: Set<string>;
}
```

在气泡循环中，theme.id 命中 ownedThemeIds 时额外渲染金色外圈：

```tsx
{ownedThemeIds?.has(theme.id) && (
  <circle
    cx={cx} cy={cy}
    r={radius + 4}
    fill="none"
    stroke="#facc15"
    strokeWidth="2"
    pointerEvents="none"
  />
)}
```

> 实际 SVG 坐标变量名以现有代码为准（cx/cy/r 可能叫 x/y/radius 等）。

如果有"持仓"⭐ 标记：

```tsx
{ownedThemeIds?.has(theme.id) && (
  <text x={cx + radius} y={cy - radius} fontSize="10" fill="#facc15">★</text>
)}
```

- [ ] **Step 3: RotationPage 注入 ownedThemeIds**

修改 `frontend/src/pages/RotationPage.tsx`：

在已有的 render 中调用 `usePortfolioScores()`，把 `ownedThemeIds` 传给 `RotationScatterWithTrails`：

```tsx
import { usePortfolioScores } from '@/hooks/usePortfolioScores';
// ...
const { ownedThemeIds } = usePortfolioScores();
// 把 ownedThemeIds 透传到 RotationScatterWithTrails props
```

- [ ] **Step 4: 跑现有 rotation 测试确认不破**

```bash
cd frontend && npx vitest run src/components/rotation 2>&1 | tail -10
```

如果有快照断言失败，确认变化是预期内（仅新增条件渲染），更新快照：

```bash
cd frontend && npx vitest run src/components/rotation -u 2>&1 | tail -5
```

- [ ] **Step 5: 验收**

```bash
cd frontend && npx tsc --noEmit && npx vitest run 2>&1 | tail -5
```

---

## Task 1.21：现有页叠加 — ThemeList 加 ⭐ 标记

**Files:**
- Modify: `frontend/src/components/ThemeList/` 中渲染主题行的文件
- Modify: `frontend/src/pages/RadarPage.tsx`

- [ ] **Step 1: 读 ThemeList 结构**

```bash
ls frontend/src/components/ThemeList/
cat frontend/src/components/ThemeList/index.tsx
```

定位渲染每个 theme 行的组件（如 `ThemeRow.tsx`）。

- [ ] **Step 2: 给主入口接收 ownedThemeIds**

如 ThemeList 接收一个 `themes` 列表，加 `ownedThemeIds?: Set<string>` prop 并透传给 row 子组件。

在 row 渲染时，theme.id 命中 ownedThemeIds → 行首加 ⭐：

```tsx
{ownedThemeIds?.has(theme.id) && (
  <span className="text-yellow-500 mr-1" title="持仓中">★</span>
)}
```

- [ ] **Step 3: RadarPage 注入 ownedThemeIds**

```tsx
import { usePortfolioScores } from '@/hooks/usePortfolioScores';
// ...
const { ownedThemeIds } = usePortfolioScores();
// 透传给 <ThemeList ownedThemeIds={ownedThemeIds} ... />
```

- [ ] **Step 4: 跑现有 ThemeList 测试**

```bash
cd frontend && npx vitest run src/components/ThemeList 2>&1 | tail -10
```

- [ ] **Step 5: 验收**

```bash
cd frontend && npx vitest run 2>&1 | tail -5
```

---

## Task 1.22：E2E 烟雾测试

**Files:**
- Create: `frontend/e2e/portfolio.spec.ts`

> 不需要真的登录 Supabase（CI 跑不通真实 OAuth）。验证未登录路径即可：
> - `/portfolio` 渲染登录卡
> - Header 链接存在
> - 切换路由不报错

- [ ] **Step 1: 写 E2E**

```ts
import { test, expect } from '@playwright/test';

test.describe('Portfolio (anonymous)', () => {
  test('Header 显示"我的持仓"链接 + 登录按钮', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByRole('link', { name: '我的持仓' })).toBeVisible();
  });

  test('/portfolio 未登录显示登录卡', async ({ page }) => {
    await page.goto('/#/portfolio');
    // 登录卡可能是登录态、未配置态或匿名态——任一文本都接受
    const cardVisible = await Promise.race([
      page.getByText('持仓信号监控').waitFor({ state: 'visible', timeout: 5000 }).then(() => 'login'),
      page.getByText('未配置 Supabase').waitFor({ state: 'visible', timeout: 5000 }).then(() => 'unconfig'),
    ]).catch(() => null);
    expect(cardVisible).toBeTruthy();
  });

  test('现有 / 和 /rotation 路由仍工作', async ({ page }) => {
    await page.goto('/');
    await expect(page).toHaveURL(/#\/?$/);
    await page.getByRole('link', { name: '主题轮动' }).click();
    await expect(page).toHaveURL(/#\/rotation/);
  });
});
```

- [ ] **Step 2: 跑 E2E**

```bash
cd frontend && npx playwright test e2e/portfolio.spec.ts 2>&1 | tail -20
```

期望：3 个测试 PASS。

> 如果 Supabase 未配置但本地确实启了 dev server，会走 "unconfigured" 分支。

- [ ] **Step 3: 跑全量 E2E 不破现有**

```bash
cd frontend && npx playwright test 2>&1 | tail -15
```

期望：所有 spec 文件全 PASS。

---

## Task 1.23：最终验收（人工 + 自动化）

**Files:** 无代码改动，纯校验。

- [ ] **Step 1: 全量测试**

```bash
cd frontend && npx vitest run 2>&1 | tail -10
cd frontend && npx playwright test 2>&1 | tail -10
cd frontend && npx tsc --noEmit 2>&1 | tail -5
cd frontend && npm run lint 2>&1 | tail -10
```

期望：vitest、playwright、tsc、lint 全部通过。

- [ ] **Step 2: 人工冒烟（需配置 .env.local）**

启动 dev server：
```bash
cd frontend && npm run dev
```

打开 http://localhost:5173/etf-radar/ 验证：

- [ ] 匿名访问 `/` 体验零变化（除 Header 多了"我的持仓"链接）
- [ ] 匿名访问 `/rotation` 体验零变化
- [ ] 点 Header "我的持仓" 跳到 `/portfolio` 看到登录卡
- [ ] Magic Link 登录全流程通畅（含国内邮箱，检查垃圾箱）
- [ ] Google OAuth 登录全流程通畅
- [ ] 录入 covered ETF（如 512480）成功，体检卡显示完整字段
- [ ] 录入 uncovered ETF（如 510300）成功，灰版卡片 + 无信号提示
- [ ] 重复录入 512480 弹"已合并"提示，份额累加，成本重算
- [ ] 删除持仓二次确认 → 删除成功
- [ ] 退出登录后跳回登录卡
- [ ] 再次登录持仓数据保留
- [ ] 登录后访问 `/rotation` 持仓主题气泡有金色外圈/⭐
- [ ] 登录后访问 `/` 持仓主题行首有 ⭐

- [ ] **Step 3: 多设备同步验收**

- 浏览器 A（如 Chrome）登录 → 加持仓 X
- 浏览器 B（如 Safari）登录同账号 → 应该看到持仓 X（Realtime 自动推送，无需手动刷新）

- [ ] **Step 4: RLS 红队验收**

参考 Task 0.2 Step 4 在 SQL Editor 执行越权读取测试，确认隔离生效。

- [ ] **Step 5: 性能 / 包大小检查**

```bash
cd frontend && npm run build 2>&1 | tail -10
ls -lh frontend/dist/assets/*.js | head -5
```

期望：bundle 体积增长 < 200KB（Supabase SDK 主要新增依赖）。

- [ ] **Step 6: README 更新检查**

```bash
grep -c "持仓监控本地开发" README.md
```

期望：≥ 1。

---

## 验收完成后

人工决定 commit 节奏与文案（项目惯例：feat / fix / refactor / perf 前缀 + 子作用域）。建议至少分两个 commit：

1. `feat(portfolio): Phase 0 Supabase infrastructure + schema`
2. `feat(portfolio): Phase 1 MVP holdings score cards`

或按你自己的偏好拆分。

---

## 风险与回滚

| 风险 | 触发 | 处理 |
|---|---|---|
| Supabase 服务故障 | 用户报错"无法登录"或"数据加载失败" | `/portfolio` 路由独立，不影响 `/` 和 `/rotation`；用户继续匿名使用其他功能 |
| anon key 泄露被滥用 | Supabase 控制台监控到异常请求 | 在 Supabase 控制台 rotate anon key + GH Actions secrets 更新 + 重新 deploy |
| 现有测试因路由变化失败 | CI 红 | Task 1.4 已含验收步骤；若 ThemeList 快照变化，更新快照 |
| Magic Link 国内邮箱不可达 | 用户报无法收邮件 | 文档已提示用 Google OAuth；可在 Supabase 配 SMTP 用自有邮箱 |

---

## 附录：依赖关系

```
Task 0.1 (Supabase 控制台) ─┐
Task 0.2 (schema)           ├── 阻塞 Task 1.* 所有 Supabase 调用
Task 0.3 (env)              ├── 阻塞 dev server 启动
Task 0.4 (CI env)           │
Task 0.5 (README)           │
                            │
Task 1.1 (install) ─────────┼── 阻塞所有后续
Task 1.2 (client) ──────────┼── 阻塞 1.3
Task 1.3 (useAuth) ─────────┼── 阻塞 1.6, 1.7, 1.19
Task 1.4 (App routes) ──────┼── 阻塞 1.5+
Task 1.5 (RadarTabs) ───────┤
Task 1.6 (AuthCallback) ────┤
Task 1.7 (AuthGate) ────────┤
Task 1.8 (types) ───────────┼── 阻塞 1.9, 1.10, 1.11, 1.12
Task 1.9 (rules) ───────────┼── 阻塞 1.10
Task 1.10 (engine) ─────────┼── 阻塞 1.12
Task 1.11 (useHoldings) ────┼── 阻塞 1.12, 1.14, 1.17
Task 1.12 (usePortfolioScores) ── 阻塞 1.17, 1.20, 1.21
Task 1.13 (autocomplete) ───┼── 阻塞 1.14
Task 1.14 (HoldingsEditor) ─┼── 阻塞 1.17
Task 1.15 (ScoreCard) ──────┼── 阻塞 1.17
Task 1.16 (Summary) ────────┼── 阻塞 1.17
Task 1.17 (HoldingsList) ───┼── 阻塞 1.18
Task 1.18 (PortfolioPage) ──┤
Task 1.19 (UserMenu) ───────┤
Task 1.20 (rotation overlay) ── 独立
Task 1.21 (themelist overlay) ── 独立
Task 1.22 (E2E) ────────────┼── 依赖 1.18 已上
Task 1.23 (验收) ────────────└── 依赖所有
```

**并行机会**：
- Task 1.9 / 1.10 / 1.11 / 1.13 在 Task 1.8 之后可并行
- Task 1.20 / 1.21 在 Task 1.12 之后可并行
- 适合用 `subagent-driven-development` 一次跑 3-4 个独立任务
