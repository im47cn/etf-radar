import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import {
  breadthColor,
  breadthLabel,
  breadthTier,
  breadthLevelColor,
  breadthTextureCss,
  TIERS,
} from '@/lib/breadthColor';
import { normalizeMarketTemperature } from '@/types/marketTemperature';
import { IndustryBreadthRanking } from '../IndustryBreadthRanking';
import { BreadthHeatmap } from '../BreadthHeatmap';
import { BreadthLegend } from '../BreadthLegend';

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

describe('breadthTier / breadthLevelColor (色阶单一真源)', () => {
  it('tier 边界: 阈值 25/50/70, 无数据 -> null', () => {
    expect(breadthTier(null)).toBeNull();
    expect(breadthTier(undefined)).toBeNull();
    expect(breadthTier(24)?.key).toBe('cold');
    expect(breadthTier(25)?.key).toBe('cool');
    expect(breadthTier(49)?.key).toBe('cool');
    expect(breadthTier(50)?.key).toBe('warm');
    expect(breadthTier(69)?.key).toBe('warm');
    expect(breadthTier(70)?.key).toBe('hot');
  });

  it('breadthLevelColor 由 breadthColor(tier.mid) 派生 (无硬编码 hex 双真源)', () => {
    for (const t of TIERS) {
      expect(breadthLevelColor(t.mid)).toBe(breadthColor(t.mid));
    }
    expect(breadthLevelColor(null)).toBe('#f1f5f9'); // 无数据灰
  });

  it('breadthLevelColor 对非中点值落档取该档中点色 (锁分档正确, 非恒等)', () => {
    // 42 落 cool(25-50, mid 38); 若分档错位则与 breadthColor(38) 不等
    for (const v of [10, 42, 63, 88]) {
      const tier = breadthTier(v)!;
      expect(breadthLevelColor(v)).toBe(breadthColor(tier.mid));
      expect(breadthLevelColor(v)).not.toBe(breadthColor(v)); // 非中点 -> 与直接采样不同, 证明是离散派生
    }
  });
});

describe('breadthTextureCss (纹理编码 tier, 4 档互异)', () => {
  it('四档 backgroundImage 互异, 无数据无纹理', () => {
    const imgs = TIERS.map((t) => breadthTextureCss(t.mid).backgroundImage);
    expect(new Set(imgs).size).toBe(4);
    expect(breadthTextureCss(null)).toEqual({});
    expect(breadthTextureCss(undefined)).toEqual({});
  });
});

describe('BreadthLegend', () => {
  it('渲染 4 档 (档名+区间), 含 role=list 与 aria-label', () => {
    render(<BreadthLegend />);
    const list = screen.getByRole('list', { name: '市场温度色阶图例' });
    expect(list).toBeInTheDocument();
    expect(list.querySelectorAll('li')).toHaveLength(4);
    for (const t of TIERS) {
      expect(screen.getByText(t.label)).toBeInTheDocument();
      expect(screen.getByText(`${t.min}–${t.max}%`)).toBeInTheDocument();
    }
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

  it('shows child min-max range on l1 bar (whisker title)', () => {
    render(
      <IndustryBreadthRanking
        l1Rows={[{ name: '金融', series: [40], latest: 40 }]}
        l2Rows={[
          { name: '证券', l1: '金融', series: [100], latest: 100 },
          { name: '银行', l1: '金融', series: [10], latest: 10 },
        ]}
      />,
    );
    expect(screen.getByTitle('子行业区间 10.0–100.0%')).toBeInTheDocument();
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
