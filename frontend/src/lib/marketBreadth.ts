/**
 * 市场温度计: 从一组 r_1d 收益率算涨跌家数广度 (breadth).
 *
 * 与主题象限图 (RRG 相对轮动图) 正交: 象限图看"谁在轮动", 广度看"今天冷暖"。
 * RRG 对全市场普涨/普跌结构性失明 (相对排名不动), 广度正好补这个盲区。
 */

export interface MarketBreadth {
  total: number; // 有效样本数 (剔除 null)
  up: number; // r_1d > 0
  down: number; // r_1d < 0
  flat: number; // r_1d === 0
  breadthPct: number; // up / total * 100, 空集为 0
  medianR1d: number | null; // 整体涨跌中枢, 空集为 null
}

function median(sorted: number[]): number {
  const n = sorted.length;
  const mid = Math.floor(n / 2);
  return n % 2 === 0 ? (sorted[mid - 1] + sorted[mid]) / 2 : sorted[mid];
}

export function computeMarketBreadth(values: Array<number | null>): MarketBreadth {
  const valid = values.filter((v): v is number => v !== null);
  const total = valid.length;
  if (total === 0) {
    return { total: 0, up: 0, down: 0, flat: 0, breadthPct: 0, medianR1d: null };
  }

  let up = 0;
  let down = 0;
  let flat = 0;
  for (const v of valid) {
    if (v > 0) up++;
    else if (v < 0) down++;
    else flat++;
  }

  const sorted = [...valid].sort((a, b) => a - b);
  return {
    total,
    up,
    down,
    flat,
    breadthPct: (up / total) * 100,
    medianR1d: median(sorted),
  };
}
