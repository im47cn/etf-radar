import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';

vi.mock('@/hooks/useTrades', () => ({ useTrades: vi.fn() }));

import { useTrades } from '@/hooks/useTrades';
import { PositionsList } from '../PositionsList';
import type { Position } from '@/lib/trading/types';

const mkPosition = (over: Partial<Position> = {}): Position => ({
  code: '600519',
  name: '贵州茅台',
  shares: 100,
  avg_cost: 1710.5,
  stop_current: 1573.2,
  ...over,
});

beforeEach(() => {
  vi.mocked(useTrades).mockReturnValue({
    positions: [], trades: [], settings: null as never,
    loading: false, error: null,
    addTrade: vi.fn(), removeTrade: vi.fn(), updateSettings: vi.fn(), refresh: vi.fn(),
  } as never);
});

describe('PositionsList', () => {
  it('无持仓显示空态引导', () => {
    render(<PositionsList />);
    expect(screen.getByText(/暂无持仓/)).toBeInTheDocument();
    expect(screen.getByText(/交易记录录入/)).toBeInTheDocument();
  });

  it('渲染持仓表: 代码/名称/股数/成本/止损位, null 止损降级 —', () => {
    vi.mocked(useTrades).mockReturnValue({
      positions: [mkPosition(), mkPosition({ code: '300750', name: '宁德时代', stop_current: null }), mkPosition({ code: '510300', name: '沪深300ETF', shares: 10000, avg_cost: 1.732, stop_current: 1.58 })],
      trades: [], settings: null as never, loading: false, error: null,
      addTrade: vi.fn(), removeTrade: vi.fn(), updateSettings: vi.fn(), refresh: vi.fn(),
    } as never);
    render(<PositionsList />);
    const rows = screen.getAllByRole('row');
    expect(rows).toHaveLength(4); // 表头 + 3 行
    expect(rows[1]?.textContent).toContain('600519');
    expect(rows[1]?.textContent).toContain('1710.500');
    expect(rows[1]?.textContent).toContain('1573.200');
    expect(rows[2]?.textContent).toContain('300750');
    expect(rows[2]?.textContent).toContain('—');
    expect(rows[3]?.textContent).toContain('510300');
    expect(rows[3]?.textContent).toContain('1.732');
    expect(rows[3]?.textContent).toContain('1.580');
  });
});
