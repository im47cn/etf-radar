import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ReviewsList, reviewDimensions, reviewPnl } from '../ReviewsList';
import type { TradeReview } from '@/lib/trading/types';

const mkReview = (id: string, over: Partial<TradeReview> = {}): TradeReview => ({
  id,
  user_id: 'u1',
  trade_id: 'a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d',
  review_date: '2026-08-19',
  discipline_score: 75,
  result_r: 1.5,
  mae_pct: -3.2,
  events: {
    dimensions: { entry_in_buy_zone: true, stop_discipline: true, exit_responsiveness: false, position_compliance: true },
    open_stop: 1573.2,
    pnl: 1200,
  },
  computed_at: '2026-08-19T17:30:00Z',
  ...over,
});

describe('reviewDimensions / reviewPnl 窄化', () => {
  it('合法 events 提取四维与 pnl', () => {
    const r = mkReview('r1');
    expect(reviewDimensions(r.events)).toEqual({
      entry_in_buy_zone: true, stop_discipline: true, exit_responsiveness: false, position_compliance: true,
    });
    expect(reviewPnl(r.events)).toBe(1200);
  });

  it('null / 数组 / 缺键 / 非数值 pnl → null', () => {
    expect(reviewDimensions(null)).toBeNull();
    // 数组形态的脏 events（jsonb 可能是数组）须拒绝
    expect(reviewDimensions([1, 2] as unknown as Record<string, unknown>)).toBeNull();
    expect(reviewDimensions({ dimensions: 'x' })).toBeNull();
    expect(reviewDimensions({ open_stop: 1 })).toBeNull();
    expect(reviewPnl(null)).toBeNull();
    expect(reviewPnl({ pnl: '1200' })).toBeNull();
    expect(reviewPnl({ pnl: Number.NaN })).toBeNull();
    expect(reviewPnl({})).toBeNull();
  });
});

describe('ReviewsList', () => {
  it('无复盘显示空态说明 (Actions 尚未跑过)', () => {
    render(<ReviewsList reviews={[]} namesByTradeId={new Map()} />);
    expect(screen.getByText(/复盘评分将在每晚交易数据管线运行后生成/)).toBeInTheDocument();
  });

  it('渲染行: trade_id 映射代码/名称, 维度 ✓/✗', () => {
    const names = new Map([
      ['a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d', { code: '600519', name: '贵州茅台' }],
    ]);
    render(<ReviewsList reviews={[mkReview('r1')]} namesByTradeId={names} />);
    expect(screen.getByText('600519')).toBeInTheDocument();
    expect(screen.getByText('贵州茅台')).toBeInTheDocument();
    expect(screen.getByText('75')).toBeInTheDocument();
    expect(screen.getByText('+1.50R')).toBeInTheDocument();
    expect(screen.getByText('-3.20%')).toBeInTheDocument();
    expect(screen.getByText('✓ 入场在买区')).toBeInTheDocument();
    expect(screen.getByText('✓ 止损纪律')).toBeInTheDocument();
    expect(screen.getByText('✗ 退出响应')).toBeInTheDocument();
    expect(screen.getByText('✓ 仓位合规')).toBeInTheDocument();
  });

  it('trade_id 不在事件流中 → 代码 —; null 分降级 —; events null 无维度区', () => {
    render(
      <ReviewsList
        reviews={[mkReview('r1', { discipline_score: null, result_r: null, mae_pct: null, events: null })]}
        namesByTradeId={new Map()}
      />,
    );
    const row = screen.getByRole('listitem');
    expect(row.textContent).toContain('—'); // code 兜底
    expect(screen.getAllByText('—')).toHaveLength(4); // 代码/纪律分/结果/MAE 四处 null
    expect(screen.queryByText(/入场在买区/)).toBeNull();
  });
});
