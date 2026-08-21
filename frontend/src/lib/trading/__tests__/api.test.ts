import { describe, it, expect, vi, beforeEach } from 'vitest';
import { listTrades, insertTrade, deleteTrade, editTrade, getSettings, saveSettings, listReviews, getReviewAggregates } from '../api';
import { TradingApiError } from '../types';

// ── supabase mock（builder 模式：supabase-js 的 order/eq 返回可继续链式的 thenable） ──
let configured = true;
let tradesResult:    { data: unknown[] | null; error: { message: string } | null };
let reviewsResult:   { data: unknown[] | null; error: { message: string } | null };
let aggregatesResult: { data: unknown[] | null; error: { message: string } | null };
let settingsResult:  { data: unknown | null;  error: { message: string } | null };
const insertMock   = vi.fn();
const deleteEqMock = vi.fn();
const upsertMock   = vi.fn();

vi.mock('@/lib/supabase', () => ({
  isSupabaseConfigured: () => configured,
  getSupabase: () => ({ from: fromMock }),
}));

// thenable builder：order/eq 链式后可直接 await
function chain(result: { data: unknown; error: unknown }) {
  const p = Promise.resolve(result);
  const b = { order: () => b, then: (f: never, r: never) => p.then(f, r) };
  return b;
}

function fromMock(table: string) {
  if (table === 'trading_settings') {
    const p = Promise.resolve(settingsResult);
    return { select: () => ({ eq: () => ({ maybeSingle: () => p }) }), upsert: upsertMock };
  }
  if (table === 'trade_reviews') {
    return { select: () => chain(reviewsResult) };
  }
  if (table === 'review_aggregates') {
    return { select: () => ({ limit: () => chain(aggregatesResult) }) };
  }
  return { select: () => chain(tradesResult), insert: insertMock, delete: () => ({ eq: deleteEqMock }) };
}

const UID = 'b2c3d4e5-f6a7-4b8c-9d0e-1f2a3b4c5d6e';

const dbTradeRow = {
  id:         'a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d',
  user_id:    UID,
  code:       '600519',
  name:       '贵州茅台',
  side:       'open',
  trade_date: '2026-08-19',
  price:      1710.5,
  shares:     100,
  stop_after: 1573.2,
  reason:     null,
  created_at: '2026-08-19T07:00:00Z',
  updated_at: '2026-08-19T07:00:00Z',
};

beforeEach(() => {
  configured = true;
  tradesResult   = { data: [dbTradeRow], error: null };
  reviewsResult  = { data: [], error: null };
  settingsResult = { data: null, error: null };
  insertMock.mockReset().mockResolvedValue({ data: null, error: null });
  deleteEqMock.mockReset().mockResolvedValue({ error: null });
  upsertMock.mockReset().mockResolvedValue({ error: null });
});

describe('listTrades', () => {
  it('未登录 / 未配置 → 返回空且不触库', async () => {
    expect(await listTrades(null)).toEqual([]);
    configured = false;
    expect(await listTrades(UID)).toEqual([]);
  });

  it('已配置 → from(trades) 拉取并 zod 解析', async () => {
    const rows = await listTrades(UID);
    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({ code: '600519', side: 'open' });
  });

  it('坏行静默过滤（zod 拒绝 side 非法行）', async () => {
    tradesResult = { data: [dbTradeRow, { ...dbTradeRow, id: 'x', side: 'buy' }], error: null };
    expect((await listTrades(UID))).toHaveLength(1);
  });

  it('DB 错误 → 抛 TradingApiError(kind=db)', async () => {
    tradesResult = { data: null, error: { message: 'row-level security' } };
    await expect(listTrades(UID)).rejects.toBeInstanceOf(TradingApiError);
    await expect(listTrades(UID)).rejects.toMatchObject({ kind: 'db', message: 'row-level security' });
  });
});

describe('insertTrade', () => {
  it('未登录 → {error:"未登录"} 不触库', async () => {
    const r = await insertTrade(null, { code: '600519', name: 'x', side: 'open', trade_date: '2026-08-19', price: 1, shares: 1 });
    expect(r.error).toBe('未登录');
    expect(insertMock).not.toHaveBeenCalled();
  });

  it('成功 → insert 携带 user_id，stop_after/reason 缺省归一为 null', async () => {
    const r = await insertTrade(UID, {
      code: '600519', name: '贵州茅台', side: 'open',
      trade_date: '2026-08-19', price: 1710.5, shares: 100,
    });
    expect(r.error).toBeNull();
    expect(insertMock).toHaveBeenCalledWith(expect.objectContaining({
      user_id: UID, code: '600519', side: 'open',
      stop_after: null, reason: null,
    }));
  });

  it('失败 → 返回错误消息', async () => {
    insertMock.mockResolvedValue({ data: null, error: { message: 'duplicate' } });
    const r = await insertTrade(UID, { code: '600519', name: 'x', side: 'add', trade_date: '2026-08-19', price: 1, shares: 1 });
    expect(r.error).toBe('duplicate');
  });
});

describe('deleteTrade', () => {
  it('按 id 删除；未登录不触库', async () => {
    const r = await deleteTrade(UID, 'a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d');
    expect(r.error).toBeNull();
    expect(deleteEqMock).toHaveBeenCalledWith('id', 'a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d');
    expect((await deleteTrade(null, 'x')).error).toBe('未登录');
  });
});

describe('editTrade', () => {
  const TID = 'a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d';
  const input = { code: '600519', name: 'x', side: 'open' as const, trade_date: '2026-08-19', price: 1, shares: 1 };

  it('未登录 → 不触库', async () => {
    expect((await editTrade(null, TID, input)).error).toBe('未登录');
    expect(deleteEqMock).not.toHaveBeenCalled();
    expect(insertMock).not.toHaveBeenCalled();
  });

  it('成功 → 先删后插', async () => {
    const r = await editTrade(UID, TID, input);
    expect(r.error).toBeNull();
    expect(deleteEqMock).toHaveBeenCalledWith('id', TID);
    expect(insertMock).toHaveBeenCalledWith(expect.objectContaining({ user_id: UID, code: '600519' }));
  });

  it('删除失败（如 008 护栏拦截超 7 天 close）→ 短路不插入', async () => {
    deleteEqMock.mockResolvedValue({ error: { message: 'close event locked' } });
    const r = await editTrade(UID, TID, input);
    expect(r.error).toBe('close event locked');
    expect(insertMock).not.toHaveBeenCalled();
  });

  it('插入失败 → 提示原记录已删需重录（非原子风险显式暴露）', async () => {
    insertMock.mockResolvedValue({ data: null, error: { message: 'network' } });
    const r = await editTrade(UID, TID, input);
    expect(r.error).toContain('原记录已删除但新记录写入失败');
    expect(r.error).toContain('network');
  });
});

describe('listReviews', () => {
  it('未登录 → 返回空；已配置 → from(trade_reviews) 拉取', async () => {
    expect(await listReviews(null)).toEqual([]);
    expect(await listReviews(UID)).toEqual([]);
  });

  it('合法复盘行通过 zod', async () => {
    reviewsResult = {
      data: [{
        id: 'c3d4e5f6-a7b8-4c9d-8e1f-2a3b4c5d6e7f', user_id: UID,
        trade_id: 'a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d',
        review_date: '2026-08-19', discipline_score: 75, result_r: 1.8,
        mae_pct: -3.2, events: { stop_moved: true }, computed_at: '2026-08-19T12:00:00Z',
      }],
      error: null,
    };
    const rows = await listReviews(UID);
    expect(rows).toHaveLength(1);
    expect(rows[0].discipline_score).toBe(75);
  });
});

describe('getSettings', () => {
  it('未登录 → 默认值（user_id 空串）', async () => {
    const s = await getSettings(null);
    expect(s).toEqual({
      user_id: '', updated_at: '',
      equity_cny: null, risk_per_trade_pct: 0.75, max_positions: 5, max_position_pct: 20, max_portfolio_risk_pct: 4,
    });
  });

  it('无行 → 默认值', async () => {
    const s = await getSettings(UID);
    expect(s.user_id).toBe(UID);
    expect(s.risk_per_trade_pct).toBe(0.75);
    expect(s.equity_cny).toBeNull();
  });

  it('已有行 → 返回 DB 值', async () => {
    settingsResult = {
      data: {
        user_id: UID, equity_cny: 250000, risk_per_trade_pct: 1,
        max_positions: 3, max_position_pct: 25, max_portfolio_risk_pct: 5,
        updated_at: '2026-08-19T00:00:00Z',
      },
      error: null,
    };
    const s = await getSettings(UID);
    expect(s).toMatchObject({ equity_cny: 250000, max_positions: 3 });
  });

  it('行损坏 → 回退默认值不抛错；DB 错 → 抛 TradingApiError', async () => {
    settingsResult = { data: { user_id: UID, risk_per_trade_pct: -1 }, error: null };
    expect((await getSettings(UID)).risk_per_trade_pct).toBe(0.75);
    settingsResult = { data: null, error: { message: 'boom' } };
    await expect(getSettings(UID)).rejects.toMatchObject({ kind: 'db' });
  });
});

describe('saveSettings', () => {
  it('upsert onConflict user_id；未登录不触库', async () => {
    const r = await saveSettings(UID, { equity_cny: 100000, max_positions: 4 });
    expect(r.error).toBeNull();
    expect(upsertMock).toHaveBeenCalledWith(
      expect.objectContaining({ user_id: UID, equity_cny: 100000, max_positions: 4 }),
      { onConflict: 'user_id' },
    );
    expect((await saveSettings(null, {})).error).toBe('未登录');
  });
});


// ── getReviewAggregates (物化快照, 单行或 null) ───────────────────────

const aggRow = {
  user_id: UID,
  as_of: '2026-08-21',
  stats: { n: 7, win_rate: 0.571, avg_r: 1.2, profit_factor: 1.85, expectancy: 120.5, max_drawdown: 800, by_regime: {} },
  computed_at: '2026-08-21T09:30:00Z',
};

describe('getReviewAggregates', () => {
  it('未配置/未登录返回 null', async () => {
    configured = false;
    expect(await getReviewAggregates(null)).toBeNull();
    configured = true;
    expect(await getReviewAggregates(null)).toBeNull();
  });

  it('有物化行: 解析返回首行', async () => {
    aggregatesResult = { data: [aggRow], error: null };
    const row = await getReviewAggregates(UID);
    expect(row?.as_of).toBe('2026-08-21');
    expect(row?.stats.win_rate).toBe(0.571);
  });

  it('空表: 返回 null (Actions 未跑过)', async () => {
    aggregatesResult = { data: [], error: null };
    expect(await getReviewAggregates(UID)).toBeNull();
  });

  it('坏行被 zod 过滤: 行不合法返回 null', async () => {
    aggregatesResult = { data: [{ ...aggRow, stats: { n: 'x' } }], error: null };
    expect(await getReviewAggregates(UID)).toBeNull();
  });

  it('db error: 抛 TradingApiError', async () => {
    aggregatesResult = { data: null, error: { message: 'rls denied' } };
    await expect(getReviewAggregates(UID)).rejects.toThrow(TradingApiError);
  });
});
