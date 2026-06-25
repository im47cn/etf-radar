import { describe, it, expect } from 'vitest';
import { leaderRank, compareLeader } from '../leaderRank';

describe('leaderRank', () => {
  it('returns higher rank for more stars', () => {
    expect(leaderRank('⭐⭐⭐')).toBeGreaterThan(leaderRank('⭐⭐'));
    expect(leaderRank('⭐⭐')).toBeGreaterThan(leaderRank('⭐'));
    expect(leaderRank('⭐')).toBeGreaterThan(leaderRank(''));
  });
  it('empty has lowest rank', () => {
    expect(leaderRank('')).toBe(0);
  });
});

describe('compareLeader', () => {
  it('sorts ⭐⭐⭐ before ⭐⭐ before ⭐ before empty', () => {
    const arr: Array<'⭐⭐⭐' | '⭐⭐' | '⭐' | ''> = ['', '⭐', '⭐⭐⭐', '⭐⭐'];
    arr.sort((a, b) => compareLeader(b, a));
    expect(arr).toEqual(['⭐⭐⭐', '⭐⭐', '⭐', '']);
  });
});
