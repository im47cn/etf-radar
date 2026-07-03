# 组件约定

## 模式（写实，本项目实际习惯）

- **函数组件 + 具名箭头导出**：`export const BreadthHeatmap = ({ ... }: Props) => (...)`。**不用** `export default`（页面/组件都 named export；`App.tsx` 例外用 default）。
- **Props 用 `interface Props`**（组件内局部定义），解构参数。示例 `components/temperature/BreadthThermometer.tsx`。
- **Tailwind 类内联**，无 CSS module / styled-components。条件类用模板串或小工具函数（`const linkClass = (active) => active ? '...' : '...'`）。
- **小而专**：一个组件一个职责。数据/派生计算用 `useMemo`，交互状态用 `useState`。复杂逻辑抽到 `hooks/` 或 `lib/`。
- **展示与取数分离**：组件接收已备好的 props（如 `BreadthHeatmap` 接 `dates/l1Rows/l2Rows`），取数在页面/hook 层（`useMarketTemperature`），组件本身不 fetch。

## 约定

- 颜色/样式派生逻辑抽到 `lib/`（如 `breadthColor.ts` 的 `breadthColor`/`breadthLevelColor`/`breadthTier`），组件只调用，保证单一真源不漂移。
- 列表渲染的 `key` 用稳定业务 id；`<Fragment key=...>` 包多元素，别用无 key 的 `<>`。
- SVG/图表等自绘用内联 SVG（如温度计 sparkline），`vectorEffect="non-scaling-stroke"` 处理拉伸。
- 可访问性：交互元素用真 `<button>`，`aria-expanded` 等；纹理/形状编码信息时去色仍可区分（见 `breadthTextureCss`）。
