# 前端开发规范

etf-radar 前端：React + TypeScript + Vite + Tailwind SPA。数据来自静态 JSON 快照（`/latest/*.json`），SWR 拉取 + zod 校验，GitHub Pages 部署。

---

## 规范索引

| 规范 | 说明 | 状态 |
|-------|-------------|--------|
| [目录结构](./directory-structure.md) | pages/components/hooks/lib/types/providers 布局 | ✅ 已填 |
| [组件约定](./component-guidelines.md) | 函数组件 + named export + Tailwind；单一真源色阶 + a11y 纹理 | ✅ 已填 |
| [Hook 约定](./hook-guidelines.md) | SWR + zod 数据 hook 标准形态 | ✅ 已填 |
| [状态管理](./state-management.md) | Context + SWR（无 Redux） | ✅ 已填 |
| [质量约定](./quality-guidelines.md) | eslint/tsc -b/vitest/playwright 视觉验收 | ✅ 已填 |
| [类型安全](./type-safety.md) | zod 校验 + schema 演进 `.nullish()` + 中央 dataUrls | ✅ 已填 |

---

## 最重要的三条（sub-agent 必读）

1. **所有外部 JSON 用 zod `.parse()` 校验**；schema 演进新增字段用 **`.nullish()`**（不是 `.nullable()`）兼容旧快照 —— `type-safety.md`。
2. **数据 URL 只在 `lib/dataUrls.ts` 构造**（平铺结构，`${BASE}latest/...` 无 `data/` 前缀）—— `type-safety.md`。
3. **函数组件 + 具名箭头导出 + Tailwind**；展示与取数分离（组件不 fetch，hook 拉数据）—— `component-guidelines.md`。

团队级协作约定另见 `docs/CONVENTIONS.md`。
