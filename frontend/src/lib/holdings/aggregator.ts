import type {
  AggregatedStock,
  EtfHoldingsSnapshot,
  StockSpot,
} from '@/types/holdings';
import type { StockIndicators } from '@/types/stockIndicators';

/**
 * 把多个 ETF 的 top-N 持仓合并为唯一个股清单。
 * Phase 2 扩展：可选 indicators 参数（Map<code, StockIndicators>）
 * 在聚合时 join 到 .indicators 字段；跨主题股自然按 code 去重。
 */
export function aggregateHoldings(
  snapshots: EtfHoldingsSnapshot[],
  spots: Record<string, StockSpot>,
  indicators?: Map<string, StockIndicators>,
): AggregatedStock[] {
  const map = new Map<string, AggregatedStock>();

  for (const snap of snapshots) {
    for (const h of snap.top_holdings) {
      const existing = map.get(h.code);
      if (existing) {
        existing.cumulativeWeight += h.weight;
        if (!existing.sourceEtfs.includes(snap.etf_code)) {
          existing.sourceEtfs.push(snap.etf_code);
        }
      } else {
        map.set(h.code, {
          code: h.code,
          name: h.name,
          cumulativeWeight: h.weight,
          sourceEtfs: [snap.etf_code],
          spot: spots[h.code] ?? null,
          indicators: indicators?.get(h.code),
        });
      }
    }
  }

  return Array.from(map.values()).sort((a, b) => {
    if (b.cumulativeWeight !== a.cumulativeWeight) {
      return b.cumulativeWeight - a.cumulativeWeight;
    }
    return a.code.localeCompare(b.code);
  });
}
