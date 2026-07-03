import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
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
        l1Rows={[
          { name: '低', series: [10], latest: 10 },
          { name: '空', series: [null], latest: null },
          { name: '高', series: [80], latest: 80 },
        ]}
        l2Rows={[]}
      />,
    );
    const names = screen.getAllByTitle(/^[低高空]$/).map((e) => e.textContent);
    expect(names).toEqual(['高', '低', '空']);
    expect(screen.getByText('80.0%')).toBeInTheDocument();
  });

  it('switches to l2 rows on 二级 toggle', () => {
    render(
      <IndustryBreadthRanking
        l1Rows={[{ name: '电子', series: [50], latest: 50 }]}
        l2Rows={[{ name: '半导体', l1: '电子', series: [87], latest: 87 }]}
      />,
    );
    expect(screen.queryByTitle('半导体')).not.toBeInTheDocument();
    fireEvent.click(screen.getByText('二级'));
    expect(screen.getByTitle('半导体')).toBeInTheDocument();
  });
});

describe('BreadthHeatmap (collapsible)', () => {
  const props = {
    dates: ['2026-07-01', '2026-07-02'],
    l1Rows: [{ name: '电子', series: [50, 52], latest: 52 }],
    l2Rows: [
      { name: '半导体', l1: '电子', series: [40, null], latest: 40 },
      { name: '消费电子', l1: '电子', series: [60, 44], latest: 44 },
    ],
  };

  it('shows only l1 rows collapsed by default', () => {
    render(<BreadthHeatmap {...props} />);
    expect(screen.getByText('电子')).toBeInTheDocument();
    expect(screen.queryByText('半导体')).not.toBeInTheDocument();
  });

  it('expands children on l1 click', () => {
    render(<BreadthHeatmap {...props} />);
    fireEvent.click(screen.getByText('电子'));
    expect(screen.getByTitle('半导体 2026-07-01: 40.0%')).toBeInTheDocument();
    expect(screen.getByTitle('消费电子 2026-07-02: 44.0%')).toBeInTheDocument();
  });
});
