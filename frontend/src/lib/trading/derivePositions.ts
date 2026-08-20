// frontend/src/lib/trading/derivePositions.ts
// 交易事件流 → 当前持仓推导（纯函数，无 React/Supabase 依赖）
//
// 推导规则（规格 §2.4 trades 表语义）：
//   1. 按 (trade_date, created_at) 升序回放事件；同毫秒双键相同则保持数组原序（稳定排序）
//   2. open   → 建仓 {shares, avg_cost=price, stop=stop_after ?? null}
//   3. add    → 份额累加，avg_cost 加权平均；stop_after 更新止损位
//   4. reduce → 份额扣减，成本口径不变（卖出不改变剩余持仓成本）；stop_after 更新止损位
//   5. close  → 清仓移除；shares 扣到 ≤0 的 reduce 视同清仓
//   6. 容错：无持仓时 add 视作 open；无持仓时 reduce/close 忽略（脏数据不炸 UI）

import type { Position, Trade } from './types';

// 成本四舍五入到 4 位小数：A 股价格两位小数，加权平均最多 3-4 位，避免浮点尾差累积
function round4(x: number): number {
  return Math.round(x * 10000) / 10000;
}

export function derivePositions(trades: Trade[]): Position[] {
  const sorted = [...trades].sort((a, b) => {
    if (a.trade_date !== b.trade_date) return a.trade_date < b.trade_date ? -1 : 1;
    return a.created_at < b.created_at ? -1 : a.created_at > b.created_at ? 1 : 0;
  });

  const byCode = new Map<string, Position>();

  for (const t of sorted) {
    const cur = byCode.get(t.code);
    switch (t.side) {
      case 'open':
      case 'add': {
        // add 无持仓 → 视作 open（容错）
        const prevShares = cur?.shares ?? 0;
        const prevCost   = cur?.avg_cost ?? 0;
        const shares     = prevShares + t.shares;
        const avg_cost   = prevShares === 0
          ? t.price
          : (prevCost * prevShares + t.price * t.shares) / shares;
        byCode.set(t.code, {
          code:         t.code,
          name:         t.name,
          shares,
          avg_cost:     round4(avg_cost),
          stop_current: t.stop_after ?? cur?.stop_current ?? null,
        });
        break;
      }
      case 'reduce': {
        if (!cur) break; // 无持仓的 reduce：忽略（脏数据）
        const shares = cur.shares - t.shares;
        if (shares <= 0) { byCode.delete(t.code); break; } // 超额减仓视同清仓
        byCode.set(t.code, { ...cur, shares, stop_current: t.stop_after ?? cur.stop_current });
        break;
      }
      case 'close':
        byCode.delete(t.code);
        break;
    }
  }

  return [...byCode.values()];
}
