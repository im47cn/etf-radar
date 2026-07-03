import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { MarketBreadth } from '@/lib/marketBreadth';
import { MarketThermometer } from '../MarketThermometer';

const mk = (o: Partial<MarketBreadth> = {}): MarketBreadth => ({
  total: 41,
  up: 30,
  down: 10,
  flat: 1,
  breadthPct: (30 / 41) * 100,
  medianR1d: 0.012,
  ...o,
});

describe('MarketThermometer', () => {
  it('渲染涨跌平家数', () => {
    render(<MarketThermometer breadth={mk()} />);
    expect(screen.getByText(/涨\s*30/)).toBeInTheDocument();
    expect(screen.getByText(/跌\s*10/)).toBeInTheDocument();
    expect(screen.getByText(/平\s*1/)).toBeInTheDocument();
  });

  it('中位收益渲染为带符号百分比', () => {
    render(<MarketThermometer breadth={mk({ medianR1d: 0.012 })} />);
    expect(screen.getByText('+1.20%')).toBeInTheDocument();
  });

  it('下跌中位渲染负号', () => {
    render(<MarketThermometer breadth={mk({ medianR1d: -0.0234 })} />);
    expect(screen.getByText('-2.34%')).toBeInTheDocument();
  });

  it('渲染上涨占比', () => {
    render(<MarketThermometer breadth={mk({ up: 20, down: 20, flat: 0, total: 40, breadthPct: 50 })} />);
    expect(screen.getByText(/50%/)).toBeInTheDocument();
  });

  it('提供无障碍 region 标签', () => {
    render(<MarketThermometer breadth={mk()} />);
    expect(screen.getByRole('region', { name: '市场温度' })).toBeInTheDocument();
  });

  it('空样本显示数据不足、中位占位符', () => {
    render(<MarketThermometer breadth={mk({ total: 0, up: 0, down: 0, flat: 0, breadthPct: 0, medianR1d: null })} />);
    expect(screen.getByText('数据不足')).toBeInTheDocument();
    expect(screen.getByText('—')).toBeInTheDocument();
  });
});
