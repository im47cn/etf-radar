import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

vi.mock('@/hooks/useAuth', () => ({ useAuth: vi.fn() }));
vi.mock('@/hooks/useTrades', () => ({ useTrades: vi.fn() }));
vi.mock('@/lib/trading/api', () => ({ listReviews: vi.fn(), getReviewAggregates: vi.fn() }));

import { useAuth } from '@/hooks/useAuth';
import { useTrades } from '@/hooks/useTrades';
import { getReviewAggregates, listReviews } from '@/lib/trading/api';
import { ReviewsTab, aggregateReviews } from '../ReviewsTab';
import type { Trade, TradeReview } from '@/lib/trading/types';

const mkReview = (id: string, over: Partial<TradeReview> = {}): TradeReview => ({
  id,
  user_id: 'u1',
  trade_id: `trade-${id}`,
  review_date: '2026-08-19',
  discipline_score: 75,
  result_r: 1.5,
  mae_pct: -3.2,
  events: { dimensions: {}, open_stop: null, pnl: 100 },
  computed_at: '2026-08-19T17:30:00Z',
  ...over,
});

const mkTradeRow = (id: string, code: string): Trade => ({
  id, user_id: 'u1', code, name: `${code}名`, side: 'open',
  trade_date: '2026-08-18', price: 10, shares: 100, stop_after: null, reason: null,
  created_at: '2026-08-18T07:00:00Z', updated_at: '2026-08-18T07:00:00Z',
});

beforeEach(() => {
  vi.mocked(useAuth).mockReturnValue({ user: { id: 'uid' }, status: 'authenticated' } as never);
  vi.mocked(useTrades).mockReturnValue({
    trades: [], positions: [], settings: null as never, loading: false, error: null,
    addTrade: vi.fn(), removeTrade: vi.fn(), updateSettings: vi.fn(), refresh: vi.fn(),
  } as never);
  vi.mocked(listReviews).mockReset().mockResolvedValue([]);
  vi.mocked(getReviewAggregates).mockReset().mockResolvedValue(null);
});

// ── aggregateReviews 纯函数 ───────────────────────────────────────────

describe('aggregateReviews', () => {
  it('空数组全 null', () => {
    expect(aggregateReviews([])).toEqual({ n: 0, winRate: null, avgR: null, profitFactor: null, expectancy: null });
  });

  it('混合盈亏: 胜率/平均R/盈亏比/期望按后端口径', () => {
    const reviews = [
      mkReview('a', { result_r: 2, events: { pnl: 100 } }),
      mkReview('b', { result_r: -1, events: { pnl: -50 } }),
      mkReview('c', { result_r: null, events: { pnl: 200 } }),
    ];
    const agg = aggregateReviews(reviews);
    expect(agg.n).toBe(3);
    expect(agg.winRate).toBeCloseTo(2 / 3, 6);
    expect(agg.avgR).toBeCloseTo(0.5, 6); // 只均可得 R: (2-1)/2
    expect(agg.profitFactor).toBeCloseTo(300 / 50, 6);
    expect(agg.expectancy).toBeCloseTo(250 / 3, 6);
  });

  it('无亏损样本 → 盈亏比 null; pnl=0 不计胜', () => {
    const agg = aggregateReviews([
      mkReview('a', { events: { pnl: 100 } }),
      mkReview('b', { events: { pnl: 0 } }),
    ]);
    expect(agg.winRate).toBeCloseTo(0.5, 6);
    expect(agg.profitFactor).toBeNull();
  });

  it('pnl 全缺失 → 胜率/期望 null, R 口径独立计算', () => {
    const agg = aggregateReviews([
      mkReview('a', { result_r: 1.5, events: null }),
      mkReview('b', { result_r: -0.5, events: null }),
    ]);
    expect(agg.winRate).toBeNull();
    expect(agg.expectancy).toBeNull();
    expect(agg.avgR).toBeCloseTo(0.5, 6);
  });
});

// ── ReviewsTab 容器 ──────────────────────────────────────────────────

describe('ReviewsTab', () => {
  it('加载中显示骨架 (listReviews pending)', () => {
    vi.mocked(listReviews).mockReturnValue(new Promise(() => undefined) as never);
    render(<ReviewsTab />);
    expect(screen.getByLabelText('加载中')).toBeInTheDocument();
    expect(screen.queryByText('复盘统计')).toBeNull();
  });

  it('Actions 未跑过: 空数组 → 统计卡全 — + 空态说明', async () => {
    render(<ReviewsTab />);
    await waitFor(() => expect(screen.getByText(/复盘评分将在每晚交易数据管线运行后生成/)).toBeInTheDocument());
    expect(screen.getAllByText('—')).toHaveLength(4); // 四张统计卡
    expect(screen.getByText('复盘统计')).toBeInTheDocument();
  });

  it('有数据: 统计卡数值 + trade_id 映射代码', async () => {
    vi.mocked(listReviews).mockResolvedValue([
      mkReview('a', { result_r: 2, events: { pnl: 100 }, discipline_score: 100 }),
      mkReview('b', { result_r: -1, events: { pnl: -50 }, discipline_score: 50 }),
    ]);
    vi.mocked(useTrades).mockReturnValue({
      trades: [mkTradeRow('trade-a', '600519')],
      positions: [], settings: null as never, loading: false, error: null,
      addTrade: vi.fn(), removeTrade: vi.fn(), updateSettings: vi.fn(), refresh: vi.fn(),
    } as never);
    render(<ReviewsTab />);
    await waitFor(() => expect(screen.getByText('50.0%')).toBeInTheDocument()); // 胜率 1/2
    expect(screen.getByText('+0.50R')).toBeInTheDocument(); // 平均 R
    expect(screen.getByText('2.00')).toBeInTheDocument(); // 盈亏比
    expect(screen.getByText('+25 元')).toBeInTheDocument(); // 期望
    expect(screen.getByText(/2 笔已复盘/)).toBeInTheDocument();
    expect(screen.getByText('600519')).toBeInTheDocument(); // 映射命中
    expect(screen.getByText('—')).toBeInTheDocument(); // trade-b 未命中 → code —
  });

  it('listReviews 失败显示错误提示', async () => {
    vi.mocked(listReviews).mockRejectedValue(new Error('db down'));
    render(<ReviewsTab />);
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('db down'));
  });
});


// ── 物化聚合快照 (单一权威口径) ───────────────────────────────────────

describe('ReviewsTab 物化聚合', () => {
  it('有物化快照: 统计卡用服务端数值并标注服务端统一口径', async () => {
    vi.mocked(listReviews).mockResolvedValue([mkReview('1', { events: { pnl: 100 } })]);
    vi.mocked(getReviewAggregates).mockResolvedValue({
      user_id: 'uid',
      as_of: '2026-08-19',
      stats: { n: 7, win_rate: 0.571, avg_r: 1.2, profit_factor: 1.85, expectancy: 120.5, max_drawdown: 800, by_regime: {} },
      computed_at: '2026-08-19T17:30:00Z',
    } as never);
    render(<ReviewsTab />);
    await waitFor(() => {
      expect(screen.getByText('7 笔已复盘 · 服务端统一口径')).toBeInTheDocument();
    });
    expect(screen.getByText('57.1%')).toBeInTheDocument();
    expect(screen.getByText('+1.20R')).toBeInTheDocument();
    expect(screen.getByText('1.85')).toBeInTheDocument();
    expect(screen.getByText('+121 元')).toBeInTheDocument();
  });

  it('无物化快照: 落客户端兜底口径标注', async () => {
    vi.mocked(listReviews).mockResolvedValue([mkReview('1', { events: { pnl: 100 } })]);
    render(<ReviewsTab />);
    await waitFor(() => {
      expect(screen.getByText(/客户端兜底口径/)).toBeInTheDocument();
    });
    expect(screen.queryByText(/服务端统一口径/)).toBeNull();
  });

  it('物化快照读失败不阻断: 静默落兜底口径', async () => {
    vi.mocked(listReviews).mockResolvedValue([mkReview('1')]);
    vi.mocked(getReviewAggregates).mockRejectedValue(new Error('rls denied'));
    render(<ReviewsTab />);
    await waitFor(() => {
      expect(screen.getByText(/客户端兜底口径/)).toBeInTheDocument();
    });
  });
});
