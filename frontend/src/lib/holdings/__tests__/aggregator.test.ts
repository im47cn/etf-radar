import { describe, expect, it } from 'vitest';
import { aggregateHoldings } from '../aggregator';
import type { EtfHoldingsSnapshot, StockSpot } from '@/types/holdings';

const snap = (etf: string, holdings: Array<[string, string, number]>): EtfHoldingsSnapshot => ({
  etf_code: etf,
  etf_name: `${etf}-name`,
  disclosure_date: '2026-03-31',
  fetched_at: '2026-06-23T00:00:00+00:00',
  top_holdings: holdings.map(([code, name, weight]) => ({ code, name, weight })),
});

const spot = (name: string, close: number, r1d: number | null): StockSpot => ({
  name, close, r_1d: r1d,
});

describe('aggregateHoldings', () => {
  it('expands single ETF holdings sorted by weight desc', () => {
    const out = aggregateHoldings(
      [snap('512480', [['002129', 'TCL中环', 8.5], ['603501', '韦尔股份', 7.2]])],
      {},
    );
    expect(out.map(s => s.code)).toEqual(['002129', '603501']);
    expect(out[0].cumulativeWeight).toBe(8.5);
    expect(out[0].sourceEtfs).toEqual(['512480']);
    expect(out[0].spot).toBeNull();
  });

  it('sums weight when same stock appears in multiple ETFs', () => {
    const out = aggregateHoldings(
      [
        snap('512480', [['002129', 'TCL中环', 8.5]]),
        snap('159870', [['002129', 'TCL中环', 5.0]]),
      ],
      {},
    );
    expect(out).toHaveLength(1);
    expect(out[0].cumulativeWeight).toBeCloseTo(13.5);
    expect(out[0].sourceEtfs).toEqual(['512480', '159870']);
  });

  it('attaches spot when available', () => {
    const out = aggregateHoldings(
      [snap('512480', [['002129', 'TCL中环', 8.5]])],
      { '002129': spot('TCL中环', 12.5, 0.025) },
    );
    expect(out[0].spot).toEqual({ name: 'TCL中环', close: 12.5, r_1d: 0.025 });
  });

  it('leaves spot null when missing', () => {
    const out = aggregateHoldings(
      [snap('512480', [['002129', 'TCL中环', 8.5]])],
      { '603501': spot('韦尔股份', 98, 0) },
    );
    expect(out[0].spot).toBeNull();
  });

  it('returns empty array on empty input', () => {
    expect(aggregateHoldings([], {})).toEqual([]);
  });

  it('sorts cumulative weight desc with ties broken by code', () => {
    const out = aggregateHoldings(
      [snap('512480', [['B', 'B-name', 5.0], ['A', 'A-name', 5.0], ['C', 'C-name', 10.0]])],
      {},
    );
    expect(out.map(s => s.code)).toEqual(['C', 'A', 'B']);
  });
});
