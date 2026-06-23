import type {
  AggregatedStock,
  EtfHoldingsSnapshot,
  StockSpot,
} from '@/types/holdings';

/**
 * 把多个 ETF 的 top-N 持仓合并为唯一个股清单：
 * - 同一股票出现在多个 ETF 中，权重累加，sourceEtfs 收集所有 ETF 代码
 * - 按累计权重降序排序；并列按 code 字典升序保证确定性
 * - spot 缺失 → spot = null
 */
export function aggregateHoldings(
  snapshots: EtfHoldingsSnapshot[],
  spots: Record<string, StockSpot>,
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
