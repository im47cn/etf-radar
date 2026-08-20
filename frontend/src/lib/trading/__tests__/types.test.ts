import { describe, it, expect } from 'vitest';
import {
  TradeSchema,
  TradeReviewSchema,
  TradingSettingsSchema,
  DEFAULT_SETTINGS_VALUES,
  TradeSideSchema,
  TradingApiError,
} from '../types';

const validTrade = {
  id:         'a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d',
  user_id:    'b2c3d4e5-f6a7-4b8c-9d0e-1f2a3b4c5d6e',
  code:       '600519',
  name:       '贵州茅台',
  side:       'open',
  trade_date: '2026-08-19',
  price:      1710.5,
  shares:     100,
  stop_after: 1573.2,
  reason:     'pivot 上方 2%',
  created_at: '2026-08-19T07:00:00Z',
  updated_at: '2026-08-19T07:00:00Z',
};

describe('TradeSchema', () => {
  it('合法行通过', () => {
    expect(TradeSchema.safeParse(validTrade).success).toBe(true);
  });

  it('可空字段允许 null', () => {
    const r = TradeSchema.safeParse({ ...validTrade, stop_after: null, reason: null });
    expect(r.success).toBe(true);
  });

  it('side 非法值拒绝', () => {
    expect(TradeSchema.safeParse({ ...validTrade, side: 'buy' }).success).toBe(false);
  });

  it('code 非 6 位数字拒绝', () => {
    expect(TradeSchema.safeParse({ ...validTrade, code: '60051' }).success).toBe(false);
    expect(TradeSchema.safeParse({ ...validTrade, code: '60051A' }).success).toBe(false);
  });

  it('trade_date 非 YYYY-MM-DD 拒绝', () => {
    expect(TradeSchema.safeParse({ ...validTrade, trade_date: '2026/08/19' }).success).toBe(false);
  });

  it('shares 必须正整数', () => {
    expect(TradeSchema.safeParse({ ...validTrade, shares: 100.5 }).success).toBe(false);
    expect(TradeSchema.safeParse({ ...validTrade, shares: 0 }).success).toBe(false);
  });

  it('price 非正数拒绝', () => {
    expect(TradeSchema.safeParse({ ...validTrade, price: 0 }).success).toBe(false);
  });
});

describe('TradeSideSchema', () => {
  it('四值枚举', () => {
    for (const s of ['open', 'add', 'reduce', 'close'] as const) {
      expect(TradeSideSchema.safeParse(s).success).toBe(true);
    }
    expect(TradeSideSchema.safeParse('sell').success).toBe(false);
  });
});

describe('TradeReviewSchema', () => {
  const validReview = {
    id:               'c3d4e5f6-a7b8-4c9d-8e1f-2a3b4c5d6e7f',
    user_id:          'b2c3d4e5-f6a7-4b8c-9d0e-1f2a3b4c5d6e',
    trade_id:         'a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d',
    review_date:      '2026-08-19',
    discipline_score: 75,
    result_r:         1.8,
    mae_pct:          -3.2,
    events:           { stop_moved: true, stage_change: 3 },
    computed_at:      '2026-08-19T12:00:00Z',
  };

  it('合法行通过（events 为 jsonb 对象）', () => {
    expect(TradeReviewSchema.safeParse(validReview).success).toBe(true);
  });

  it('全部可空字段允许 null', () => {
    const r = TradeReviewSchema.safeParse({
      ...validReview,
      discipline_score: null,
      result_r: null,
      mae_pct: null,
      events: null,
    });
    expect(r.success).toBe(true);
  });

  it('discipline_score 超 0-100 拒绝', () => {
    expect(TradeReviewSchema.safeParse({ ...validReview, discipline_score: 101 }).success).toBe(false);
  });
});

describe('TradingSettingsSchema / DEFAULT_SETTINGS_VALUES', () => {
  const validSettings = {
    user_id:                'b2c3d4e5-f6a7-4b8c-9d0e-1f2a3b4c5d6e',
    equity_cny:             100000,
    risk_per_trade_pct:     0.75,
    max_positions:          5,
    max_position_pct:       20,
    max_portfolio_risk_pct: 4,
    updated_at:             '2026-08-19T12:00:00Z',
  };

  it('合法行通过；equity_cny 允许 null（未设置）', () => {
    expect(TradingSettingsSchema.safeParse(validSettings).success).toBe(true);
    expect(TradingSettingsSchema.safeParse({ ...validSettings, equity_cny: null }).success).toBe(true);
  });

  it('默认值与规格 §1 第 7 条一致', () => {
    expect(DEFAULT_SETTINGS_VALUES).toEqual({
      equity_cny:             null,
      risk_per_trade_pct:     0.75,
      max_positions:          5,
      max_position_pct:       20,
      max_portfolio_risk_pct: 4,
    });
  });

  it('默认值本身可过 schema（补齐 user_id/updated_at 后）', () => {
    const r = TradingSettingsSchema.safeParse({
      ...DEFAULT_SETTINGS_VALUES,
      user_id:    'b2c3d4e5-f6a7-4b8c-9d0e-1f2a3b4c5d6e',
      updated_at: '',
    });
    expect(r.success).toBe(true);
  });
});

describe('TradingApiError', () => {
  it('类型化错误：kind 可区分', () => {
    const e = new TradingApiError('not_configured', 'Supabase 未配置');
    expect(e).toBeInstanceOf(Error);
    expect(e.name).toBe('TradingApiError');
    expect(e.kind).toBe('not_configured');
    expect(e.message).toBe('Supabase 未配置');
  });
});
