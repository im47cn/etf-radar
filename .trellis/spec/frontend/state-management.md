# 状态管理

**无 Redux/Zustand/Jotai。** 用 React Context + SWR。

## 三层状态

| 类型 | 方案 | 示例 |
|---|---|---|
| **服务端数据**（快照 JSON） | **SWR**（缓存/重验/去重） | `useMarketTemperature`, `DataProvider` 内 `useSWR(LATEST_URLS.*)` |
| **跨组件共享状态** | **React Context**：`*Context.ts`(createContext) + `*Provider.tsx` | `DataProvider`+`dataContext`, `AuthProvider`, `EventsProvider`, `HoldingsProvider`, `UIStateProvider` |
| **局部 UI 状态** | `useState`/`useMemo` 组件内 | 折叠展开、周期切换、tab |

## Context 约定

- 拆两文件：`xContext.ts`（`createContext` + `useXContext()` hook）与 `xProvider.tsx`（Provider 组件，内部用 SWR 拉数据）。
- Provider 在 `App.tsx` 嵌套包裹。
- 消费用自定义 hook（`useDataContext()`），不直接 `useContext`。

## 原则

- 服务端数据一律 SWR，别手写 `useEffect + fetch + useState`。
- Context 只放真正跨组件共享的；能局部就局部。
- 数据 URL 统一走 `lib/dataUrls.ts`（见 `type-safety.md` / `directory-structure.md`）。
