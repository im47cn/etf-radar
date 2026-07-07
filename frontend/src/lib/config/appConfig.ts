// 前端应用配置：集中从构建时环境变量（VITE_*）读取，未配置时回落到默认值。
// 与后端约定的可调参数（如持仓上限）在此汇总，运营可通过部署环境变量调整而无需改代码，
// 沿用项目既有的 VITE_ 约定（见 supabase.ts / MembershipPanel.tsx）。
//
// 注意：env 为构建时注入，改值需重新构建部署；生产环境变量在 deploy-frontend.yml 注入。

// 解析正整数环境变量，非法或缺省时回落。
function readPositiveInt(raw: string | undefined, fallback: number): number {
  const n = Number(raw);
  return Number.isInteger(n) && n > 0 ? n : fallback;
}

export const appConfig = {
  // 免费版持仓上限；须与后端 005_holdings_free_limit.sql 触发器阈值一致。
  freeHoldingsLimit: readPositiveInt(import.meta.env.VITE_FREE_HOLDINGS_LIMIT, 5),
} as const;
