# 类型安全

## zod 校验所有外部 JSON（核心约定）

- 每份快照 JSON 在 `types/` 有对应 **zod schema**，fetch 后 `.parse()` 校验，类型从 schema 派生（`z.infer`）。真实：`types/marketTemperature.ts`, `types/snapshots.ts`, `types/meta.ts`。
- **schema 演进必须兼容旧数据（铁律，来自 `docs/CONVENTIONS.md`）**：新增字段用 **`.nullish()`**（同时接受 `null` 和 `undefined`），不要用 `.nullable()`（拒绝 `undefined`）。
  - 教训：PR #14 schema 1.0→1.1 后，前端 `.nullable()` 拒绝缺省键，历史 frame 全解析失败、trail 隐形（`57bf242` 用 `.nullish()` 兜住）。
- 多版本 schema 用归一化：`normalizeMarketTemperature` 同时解析 1.0/2.0，`.passthrough()` 容忍多余字段。

## TypeScript

- **`strict` 严格**。`build` = `tsc -b && vite build`；`typecheck` = `tsc -b --noEmit`（pre-push 跑，比 `tsc --noEmit` 更严，如 `Cannot find namespace 'JSX'` → 用推断或 `React.ReactElement`）。
- 类型定义在 `types/`（zod 派生）或组件内 `interface Props`。
- 避免 `any`；第三方无类型处局部 `// eslint-disable` 或断言，别扩散。

## 中央 URL 构造（`lib/dataUrls.ts`）

- 所有数据文件 URL 只在此构造（`LATEST_URLS`, `frameUrl`, `HOLDINGS_URLS` …）。
- 背景：`vite.config.ts` `publicDir: '../data'` 把内容平铺到根，fetch 用 `${BASE}latest/...`，**不能加 `data/` 前缀**。新增数据文件在此加一个 URL 常量，配合契约测试防错配。
