import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { breadthColor, breadthLabel } from '@/lib/breadthColor';
import { MarketTemperatureSchema } from '@/types/marketTemperature';
import { IndustryBreadthRanking } from '../IndustryBreadthRanking';
import { BreadthHeatmap } from '../BreadthHeatmap';

describe('breadthColor', () => {
  it('null -> 无数据灰', () => {
    expect(breadthColor(null)).toBe('#f1f5f9');
    expect(breadthColor(undefined)).toBe('#f1f5f9');
  });
  it('clamps and interpolates', () => {
    expect(breadthColor(0)).toBe('rgb(224, 231, 255)'); // 淡紫端点
    expect(breadthColor(-5)).toBe(breadthColor(0));
    expect(breadthColor(200)).toBe('rgb(253, 186, 116)'); // clamp 到 100 -> 橙端点
  });
  it('label buckets', () => {
    expect(breadthLabel(80)).toBe('过热');
    expect(breadthLabel(55)).toBe('偏暖');
    expect(breadthLabel(35)).toBe('偏冷');
    expect(breadthLabel(10)).toBe('冰点');
    expect(breadthLabel(null)).toBe('无数据');
  });
});

describe('MarketTemperatureSchema', () => {
  it('parses valid snapshot with nulls', () => {
    const snap = {
      schema_version: '1.0', generated_at: 'x', source: 'dapanyuntu', metric: 'ma20_above_ratio',
      dates: ['2026-07-01', '2026-07-02'],
      market: [{ date: '2026-07-01', rate: 36.7 }, { date: '2026-07-02', rate: null }],
      industries_l1: [{ name: '电子', series: [50, null], latest: 50 }],
      industries_l2: [{ name: '半导体', series: [40, 50], latest: 50 }],
    };
    expect(() => MarketTemperatureSchema.parse(snap)).not.toThrow();
  });
});

describe('IndustryBreadthRanking', () => {
  it('sorts by latest desc, null last, renders %', () => {
    render(
      <IndustryBreadthRanking
        rows={[
          { name: '低', series: [10], latest: 10 },
          { name: '空', series: [null], latest: null },
          { name: '高', series: [80], latest: 80 },
        ]}
      />,
    );
    const names = screen.getAllByTitle(/^[低高空]$/).map((e) => e.textContent);
    expect(names).toEqual(['高', '低', '空']);
    expect(screen.getByText('80.0%')).toBeInTheDocument();
  });
});

describe('BreadthHeatmap', () => {
  it('renders one cell per date per row', () => {
    render(
      <BreadthHeatmap
        dates={['2026-07-01', '2026-07-02']}
        rows={[{ name: '半导体', series: [40, null], latest: 40 }]}
      />,
    );
    expect(screen.getByTitle('半导体 2026-07-01: 40.0%')).toBeInTheDocument();
    expect(screen.getByTitle('半导体 2026-07-02: 无数据')).toBeInTheDocument();
  });
});
