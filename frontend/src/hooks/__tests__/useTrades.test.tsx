import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';

// ── supabase mock（builder 模式，链式 thenable；走真实 api.ts → derivePositions 链路） ──
let tradesResult:   { data: unknown[] | null; error: { message: string } | null };
let settingsResult: { data: unknown | null;  error: { message: string } | null };
const insertMock = vi.fn();
const upsertMock = vi.fn();

function chain(result: { data: unknown; error: unknown }) {
  const p = Promise.resolve(result);
  const b = { order: () => b, then: (f: never, r: never) => p.then(f, r) };
  return b;
}

vi.mock('@/lib/supabase', () => ({
  isSupabaseConfigured: () => true,
  getSupabase: () => ({
    from: (table: string) => {
      if (table === 'trading_settings') {
        const p = Promise.resolve(settingsResult);
        return { select: () => ({ eq: () => ({ maybeSingle: () => p }) }), upsert: upsertMock };
      }
      return { select: () => chain(tradesResult), insert: insertMock };
    },
    channel: () => ({ on: () => ({ subscribe: () => undefined }) }),
    removeChannel: () => undefined,
  }),
}));

// ── auth mock ──
const mockAuthState = { user: { id: 'u1' } as { id: string } | null, status: 'authenticated' as string };
vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => mockAuthState,
  useAuthOptional: () => mockAuthState,
}));

import { TradesProvider } from '@/providers/TradesProvider';
import { useTrades } from '@/hooks/useTrades';

const UID = 'b2c3d4e5-f6a7-4b8c-9d0e-1f2a3b4c5d6e';

function tradeRow(id: string, side: string, price: number, shares: number, date: string, stop: number | null) {
  return {
    id, user_id: UID, code: '600519', name: '贵州茅台', side,
    trade_date: date, price, shares, stop_after: stop, reason: null,
    created_at: `${date}T07:00:00Z`, updated_at: `${date}T07:00:00Z`,
  };
}

const wrapper = ({ children }: { children: ReactNode }) => <TradesProvider>{children}</TradesProvider>;

beforeEach(() => {
  mockAuthState.user = { id: UID };
  mockAuthState.status = 'authenticated';
  tradesResult   = { data: [], error: null };
  settingsResult = { data: null, error: null };
  insertMock.mockReset().mockResolvedValue({ data: null, error: null });
  upsertMock.mockReset().mockResolvedValue({ error: null });
});

describe('useTrades (TradesProvider)', () => {
  it('authenticated: 拉取 trades 并推导持仓（open+add → 加权平均）', async () => {
    tradesResult = {
      data: [
        tradeRow('a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d', 'open', 100, 100, '2026-08-01', 90),
        tradeRow('b1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d', 'add', 110, 100, '2026-08-05', null),
      ],
      error: null,
    };
    const { result } = renderHook(() => useTrades(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.trades).toHaveLength(2);
    expect(result.current.positions).toEqual([
      { code: '600519', name: '贵州茅台', shares: 200, avg_cost: 105, stop_current: 90 },
    ]);
  });

  it('settings 无行 → 默认值（0.75/5/20/4）', async () => {
    const { result } = renderHook(() => useTrades(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.settings).toMatchObject({
      equity_cny: null, risk_per_trade_pct: 0.75, max_positions: 5, max_position_pct: 20, max_portfolio_risk_pct: 4,
    });
  });

  it('anonymous: trades/positions 空、settings 为默认、addTrade 拒绝', async () => {
    mockAuthState.user = null;
    mockAuthState.status = 'anonymous';
    const { result } = renderHook(() => useTrades(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.trades).toEqual([]);
    expect(result.current.positions).toEqual([]);
    expect(result.current.settings.equity_cny).toBeNull();
    await act(async () => {
      const r = await result.current.addTrade({
        code: '600519', name: 'x', side: 'open', trade_date: '2026-08-19', price: 1, shares: 1,
      });
      expect(r.error).toBe('未登录');
    });
    expect(insertMock).not.toHaveBeenCalled();
  });

  it('addTrade 成功 → insert 触库并刷新（新事件反映到 positions）', async () => {
    const { result } = renderHook(() => useTrades(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));

    // 下一次拉取返回新录入的 open 事件
    tradesResult = {
      data: [tradeRow('a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d', 'open', 1710.5, 100, '2026-08-19', 1573.2)],
      error: null,
    };
    await act(async () => {
      const r = await result.current.addTrade({
        code: '600519', name: '贵州茅台', side: 'open',
        trade_date: '2026-08-19', price: 1710.5, shares: 100, stop_after: 1573.2,
      });
      expect(r.error).toBeNull();
    });
    expect(insertMock).toHaveBeenCalledWith(expect.objectContaining({
      user_id: UID, code: '600519', side: 'open', stop_after: 1573.2,
    }));
    await waitFor(() => expect(result.current.positions).toHaveLength(1));
    expect(result.current.positions[0]).toMatchObject({ shares: 100, avg_cost: 1710.5, stop_current: 1573.2 });
  });

  it('addTrade 触库失败 → 返回错误消息，positions 不变', async () => {
    insertMock.mockResolvedValue({ data: null, error: { message: 'rls denied' } });
    const { result } = renderHook(() => useTrades(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));
    await act(async () => {
      const r = await result.current.addTrade({
        code: '600519', name: 'x', side: 'open', trade_date: '2026-08-19', price: 1, shares: 1,
      });
      expect(r.error).toBe('rls denied');
    });
    expect(result.current.positions).toEqual([]);
  });

  it('updateSettings 成功 → settings 刷新为 DB 值', async () => {
    const { result } = renderHook(() => useTrades(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));
    settingsResult = {
      data: {
        user_id: UID, equity_cny: 100000, risk_per_trade_pct: 0.75,
        max_positions: 5, max_position_pct: 20, max_portfolio_risk_pct: 4,
        updated_at: '2026-08-19T00:00:00Z',
      },
      error: null,
    };
    await act(async () => {
      const r = await result.current.updateSettings({ equity_cny: 100000 });
      expect(r.error).toBeNull();
    });
    expect(upsertMock).toHaveBeenCalledWith(
      expect.objectContaining({ user_id: UID, equity_cny: 100000 }),
      { onConflict: 'user_id' },
    );
    await waitFor(() => expect(result.current.settings.equity_cny).toBe(100000));
  });

  it('拉取 DB 错误 → error 状态可展示', async () => {
    tradesResult = { data: null, error: { message: 'connection refused' } };
    const { result } = renderHook(() => useTrades(), { wrapper });
    await waitFor(() => expect(result.current.error).toBe('connection refused'));
    expect(result.current.trades).toEqual([]);
  });

  it('Provider 外使用 → 抛错提示', () => {
    expect(() => renderHook(() => useTrades())).toThrow(/TradesProvider/);
  });
});
