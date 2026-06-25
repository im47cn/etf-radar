import type { LeaderStar } from '@/types/stockIndicators';

/**
 * 龙头标签的可排序整数表示。
 * 高分排前：⭐⭐⭐=3, ⭐⭐=2, ⭐=1, ''=0
 */
export function leaderRank(s: LeaderStar): number {
  switch (s) {
    case '⭐⭐⭐': return 3;
    case '⭐⭐': return 2;
    case '⭐': return 1;
    default: return 0;
  }
}

export function compareLeader(a: LeaderStar, b: LeaderStar): number {
  return leaderRank(a) - leaderRank(b);
}
