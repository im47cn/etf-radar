# 前端目录结构

React + TypeScript + Vite + Tailwind。SPA，HashRouter 路由，数据来自静态 JSON（`/latest/*.json`）。

## 布局（`frontend/src/`）

| 目录 | 职责 | 真实示例 |
|---|---|---|
| `pages/` | 路由页（薄容器，组合组件 + hook） | `RotationPage.tsx`, `TemperaturePage.tsx`, `RadarPage.tsx` |
| `components/<feature>/` | 按功能分组的组件 + 同级 `__tests__/` | `components/temperature/BreadthHeatmap.tsx`, `components/rotation/`, `components/Header/` |
| `components/ui/` | 通用基础组件 | — |
| `hooks/` | 自定义 hook（数据/状态逻辑） | `useMarketTemperature.ts`, `useEventsSnapshot.ts` |
| `lib/` | 纯工具 + 同级 `__tests__/` | `dataUrls.ts`（**唯一 URL 构造点**）, `breadthColor.ts`, `marketBreadth.ts` |
| `types/` | zod schema + 派生 TS 类型 | `marketTemperature.ts`, `snapshots.ts`, `meta.ts` |
| `providers/` | React Context（`*Context.ts` + `*Provider.tsx`） | `DataProvider.tsx` + `dataContext.ts` |
| `App.tsx` | 路由表 + Provider 嵌套 |

## 原则

- **页薄、组件厚**：`pages/` 只组合，逻辑在 hooks/components（`RadarPage.tsx` 就几行 JSX）。
- **功能分组**：组件按 feature 目录（`temperature/`, `rotation/`, `Header/`），不按类型平铺。
- **测试同级 colocate**：`components/x/__tests__/`, `lib/__tests__/`, `hooks/__tests__/`。
- **路径别名 `@/`** → `src/`（`vite.config.ts`）。
- **数据 URL 只在 `lib/dataUrls.ts` 构造**：`publicDir` 把 `../data` 平铺到根，fetch 用 `${BASE}latest/...` 不带 `data/` 前缀。禁止在别处硬编码数据路径。
