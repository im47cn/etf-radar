import { describe, it, expect } from 'vitest';
import { scorePortfolio } from '../engine';
import { themesMock, themeSignalsMock } from './__fixtures__/themes-mock';
import { etfsMock } from './__fixtures__/etfs-mock';
import type { Holding } from '../types';

const baseHolding = (etf_code: string, shares: number, cost_price: number | null = null): Holding => ({
  id:          `id-${etf_code}`,
  user_id:     'user-1',
  etf_code,
  shares,
  cost_price,
  note:        null,
  created_at:  '2026-06-21T00:00:00Z',
  updated_at:  '2026-06-21T00:00:00Z',
});

describe('scorePortfolio', () => {
  it('covered ETF: 完整字段填充', () => {
    const result = scorePortfolio({
      holdings: [baseHolding('512480', 1000, 2.0)],
      themes: themesMock,
      etfs: etfsMock,
      themeSignals: themeSignalsMock,
    });
    expect(result).toHaveLength(1);
    const s = result[0];
    expect(s.status).toBe('covered');
    expect(s.name).toBe('半导体ETF国联安');
    expect(s.themeId).toBe('storage_dram');
    expect(s.themeName).toBe('存储芯片');
    expect(s.themeSignal).toBe('resonance');
    expect(s.l2Tag).toBe('偏强');
    expect(s.momentumTag).toBe('动量向上');
    expect(s.quadrant).toBe('leading');
    expect(s.narrative).toContain('领涨象限');
  });

  it('covered ETF: 盈亏计算正确', () => {
    const result = scorePortfolio({
      holdings: [baseHolding('512480', 1000, 2.0)],  // 现价 2.481, 成本 2.0
      themes: themesMock,
      etfs: etfsMock,
      themeSignals: themeSignalsMock,
    });
    const s = result[0];
    expect(s.currentPrice).toBe(2.481);
    expect(s.marketValue).toBeCloseTo(2481, 1);
    expect(s.pnlAbs).toBeCloseTo(481, 1);
    expect(s.pnlPct).toBeCloseTo(0.2405, 3);
  });

  it('covered ETF: 无 cost_price 时盈亏为 null', () => {
    const result = scorePortfolio({
      holdings: [baseHolding('512480', 1000, null)],
      themes: themesMock,
      etfs: etfsMock,
      themeSignals: themeSignalsMock,
    });
    expect(result[0].pnlAbs).toBeNull();
    expect(result[0].pnlPct).toBeNull();
    expect(result[0].marketValue).toBeCloseTo(2481, 1);  // 市值仍可算
  });

  it('uncovered ETF: status=uncovered, 无主题字段', () => {
    const result = scorePortfolio({
      holdings: [baseHolding('510300', 500, 1.85)],  // 不在 etfsMock 内
      themes: themesMock,
      etfs: etfsMock,
      themeSignals: themeSignalsMock,
    });
    expect(result).toHaveLength(1);
    const s = result[0];
    expect(s.status).toBe('uncovered');
    expect(s.themeId).toBeUndefined();
    expect(s.themeSignal).toBeUndefined();
    expect(s.currentPrice).toBeNull();
    expect(s.marketValue).toBeNull();
    expect(s.l2Tag).toBeUndefined();
    expect(s.narrative).toBeUndefined();
  });

  it('混合：covered + uncovered 同时输出', () => {
    const result = scorePortfolio({
      holdings: [
        baseHolding('512480', 1000, 2.0),
        baseHolding('510300', 500, 1.85),
      ],
      themes: themesMock,
      etfs: etfsMock,
      themeSignals: themeSignalsMock,
    });
    expect(result).toHaveLength(2);
    expect(result.find(s => s.etfCode === '512480')?.status).toBe('covered');
    expect(result.find(s => s.etfCode === '510300')?.status).toBe('uncovered');
  });

  it('弱势 covered: l2Tag=偏弱, momentum=动量向下, 包含背离', () => {
    const result = scorePortfolio({
      holdings: [baseHolding('999999', 100, 1.0)],
      themes: themesMock,
      etfs: etfsMock,
      themeSignals: themeSignalsMock,
    });
    const s = result[0];
    expect(s.l2Tag).toBe('偏弱');
    expect(s.momentumTag).toBe('动量向下');
    expect(s.quadrant).toBe('weak');
    expect(s.narrative).toContain('背离');
  });

  it('空持仓输入 → 空数组', () => {
    expect(scorePortfolio({
      holdings: [], themes: themesMock, etfs: etfsMock, themeSignals: themeSignalsMock,
    })).toEqual([]);
  });
});
