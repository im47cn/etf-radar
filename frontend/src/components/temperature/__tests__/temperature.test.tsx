import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { breadthColor, breadthLabel } from '@/lib/breadthColor';
import { normalizeMarketTemperature } from '@/types/marketTemperature';
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

describe('normalizeMarketTemperature', () => {
  it('normalizes legacy 1.0 flat -> ma20 period', () => {
    const snap = {
      schema_version: '1.0', dates: ['2026-07-01', '2026-07-02'],
      market: [{ date: '2026-07-01', rate: 36.7 }, { date: '2026-07-02', rate: null }],
      industries_l1: [{ name: '电子', series: [50, null], latest: 50 }],
      industries_l2: [{ name: '半导体', series: [40, 50], latest: 50 }],
    };
    const n = normalizeMarketTemperature(snap);
    expect(n.available).toEqual(['ma20']);
    expect(n.periods.ma20!.industries_l2[0].name).toBe('半导体');
  });

  it('normalizes 2.0 and reports available periods (ma120 all-null excluded)', () => {
    const pd = (rate: number | null) => ({
      market: [{ date: 'd0', rate }],
      industries_l1: [{ name: '电子', series: [rate], latest: rate }],
      industries_l2: [{ name: '半导体', l1: '电子', series: [rate], latest: rate }],
    });
    const snap = {
      schema_version: '2.0', dates: ['d0'],
      periods: { ma20: pd(32.9), ma60: pd(25.7), ma120: pd(null) },
    };
    const n = normalizeMarketTemperature(snap);
    expect(n.available).toEqual(['ma20', 'ma60']); // ma120 全 null 不可用
  });
});

describe('IndustryBreadthRanking', () => {
  it('sorts l1 by latest desc, null last, renders %', () => {
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

  it('expands l2 children on l1 click', () => {
    render(
      <IndustryBreadthRanking
        l1Rows={[{ name: '电子', series: [50], latest: 50 }]}
        l2Rows={[{ name: '半导体', l1: '电子', series: [87], latest: 87 }]}
      />,
    );
    expect(screen.queryByTitle('半导体')).not.toBeInTheDocument();
    fireEvent.click(screen.getByTitle('电子'));
    expect(screen.getByTitle('半导体')).toBeInTheDocument();
  });

  it('展开全部 expands all groups then 收起全部 collapses', () => {
    render(
      <IndustryBreadthRanking
        l1Rows={[{ name: '电子', series: [50], latest: 50 }, { name: '金融', series: [40], latest: 40 }]}
        l2Rows={[
          { name: '半导体', l1: '电子', series: [87], latest: 87 },
          { name: '证券', l1: '金融', series: [60], latest: 60 },
        ]}
      />,
    );
    fireEvent.click(screen.getByText('展开全部'));
    expect(screen.getByTitle('半导体')).toBeInTheDocument();
    expect(screen.getByTitle('证券')).toBeInTheDocument();
    fireEvent.click(screen.getByText('收起全部'));
    expect(screen.queryByTitle('半导体')).not.toBeInTheDocument();
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
