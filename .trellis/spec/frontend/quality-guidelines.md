# 前端质量约定

## 工具链（`frontend/package.json`）

- **eslint**（flat config）：`js.recommended` + `typescript-eslint.recommended` + `react-hooks` + `react-refresh`。命令 `npm run lint`（`eslint .`）。常踩：未用 import/变量、`no-unused-expressions`（三元当语句改 `if/else`）、react-hooks 依赖。
- **tsc**：`npm run typecheck`（`tsc -b --noEmit`）。pre-push 跑，较严。
- **vitest**：`npm run test`（`vitest`）。单文件 `npx vitest run src/path/x.test.tsx`。
- **playwright** e2e：`npm run test:e2e`（`e2e/`）。
- pre-push hook 跑 eslint + tsc -b + vite build；别 `--no-verify`。

## 测试

- **vitest + @testing-library/react**，测试就近 `__tests__/`（`components/x/__tests__/x.test.tsx`, `lib/__tests__/`, `hooks/__tests__/`）。
- 组件测试：`render` + `screen.getByText/getByTitle` + `fireEvent`；断言渲染/排序/交互（折叠展开、切换联动）。
- 纯逻辑（`lib/breadthColor`, zod normalize）单测边界（null/clamp/schema 1.0 vs 2.0/档位阈值）。
- **视觉验收用 playwright 截图**（起 dev server → 截图 → 肉眼核对布局），本项目重度依赖此法验收 UI。

## 约定

- 提交前跑相关 `vitest run` + `tsc -b --noEmit` + `eslint`。
- 数据 schema 变更时同步更新 zod（`.nullish()` 兼容）+ 测试，见 `type-safety.md`。
- 部署 = push main 触发 `deploy-frontend.yml`（GitHub Pages）；生产 canonical 域名 `im47.cn/etf-radar`（`im47cn.github.io` 是 301 跳转）。Pages 部署偶发瞬时失败，重试即可。
