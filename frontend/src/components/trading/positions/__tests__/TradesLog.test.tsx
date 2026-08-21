import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';

vi.mock('@/hooks/useTrades', () => ({ useTrades: vi.fn() }));

import { useTrades } from '@/hooks/useTrades';
import { TradesLog } from '../TradesLog';
import { isCloseDeleteLocked } from '../closeGuard';
import type { Trade } from '@/lib/trading/types';

const mkTrade = (id: string, over: Partial<Trade> = {}): Trade => ({
  id,
  user_id: 'u1',
  code: '600519',
  name: '贵州茅台',
  side: 'open',
  trade_date: '2026-08-19',
  price: 1710.5,
  shares: 100,
  stop_after: 1573.2,
  reason: null,
  created_at: '2026-08-19T07:00:00Z',
  updated_at: '2026-08-19T07:00:00Z',
  ...over,
});

const removeTrade = vi.fn();
const editTrade = vi.fn();

const mockTrades = (trades: Trade[]) => {
  vi.mocked(useTrades).mockReturnValue({
    trades, positions: [], settings: null as never, loading: false, error: null,
    addTrade: vi.fn(), removeTrade, editTrade, updateSettings: vi.fn(), refresh: vi.fn(),
  } as never);
};

beforeEach(() => {
  removeTrade.mockReset().mockResolvedValue({ error: null });
  editTrade.mockReset().mockResolvedValue({ error: null });
});

const rowOf = (code: string) => screen.getByText(code).closest('li') as HTMLElement;

describe('TradesLog', () => {
  it('无记录显示空态', () => {
    mockTrades([]);
    render(<TradesLog />);
    expect(screen.getByText(/暂无交易记录/)).toBeInTheDocument();
  });

  it('事件流最新在前, 含事件标签与止损位; null 止损不显示止损段', () => {
    // 契约: trades 来自 listTrades 按 trade_date 升序
    mockTrades([
      mkTrade('t1', { trade_date: '2026-08-18' }),
      mkTrade('t3', { trade_date: '2026-08-19', side: 'add', price: 1720 }),
      mkTrade('t2', { trade_date: '2026-08-20', side: 'reduce', shares: 50, stop_after: null }),
    ]);
    render(<TradesLog />);
    const items = screen.getAllByRole('listitem');
    expect(items).toHaveLength(3);
    expect(items[0]?.textContent).toContain('2026-08-20'); // 最新在前
    expect(items[0]?.textContent).toContain('减仓');
    expect(items[0]?.textContent).not.toContain('止损位');
    expect(items[1]?.textContent).toContain('加仓');
    expect(items[1]?.textContent).toContain('止损位 1573.20');
    expect(items[2]?.textContent).toContain('2026-08-18');
  });

  it('删除两步确认: 先变确认按钮, 再点才调用 removeTrade', async () => {
    mockTrades([
      mkTrade('t1'),
      mkTrade('t2', { code: '300750', name: '宁德时代', trade_date: '2026-08-20' }),
    ]);
    render(<TradesLog />);
    fireEvent.click(within(rowOf('600519')).getByRole('button', { name: '删除' }));
    expect(screen.getAllByRole('button', { name: '删除' })).toHaveLength(1); // 只剩另一行的删除
    expect(screen.getByRole('button', { name: '确认删除' })).toBeInTheDocument();
    expect(removeTrade).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: '确认删除' }));
    await waitFor(() => expect(removeTrade).toHaveBeenCalledWith('t1'));
  });

  it('切换确认目标: 点另一行删除时前一行恢复', () => {
    mockTrades([
      mkTrade('t1', { trade_date: '2026-08-18' }),
      mkTrade('t2', { trade_date: '2026-08-20', side: 'reduce', shares: 50 }),
    ]);
    render(<TradesLog />);
    const rows = screen.getAllByRole('listitem');
    const delFirst = within(rows[0] as HTMLElement).getByRole('button', { name: '删除' });
    const delSecond = within(rows[1] as HTMLElement).getByRole('button', { name: '删除' });
    fireEvent.click(delFirst);
    expect(within(rows[0] as HTMLElement).getByRole('button', { name: '确认删除' })).toBeInTheDocument();
    fireEvent.click(delSecond);
    // 第一行恢复「删除」, 第二行进入确认
    expect(within(rows[0] as HTMLElement).getByRole('button', { name: '删除' })).toBeInTheDocument();
    expect(within(rows[1] as HTMLElement).getByRole('button', { name: '确认删除' })).toBeInTheDocument();
  });

  it('removeTrade 失败展示错误', async () => {
    removeTrade.mockResolvedValue({ error: '网络错误' });
    mockTrades([mkTrade('t1')]);
    render(<TradesLog />);
    fireEvent.click(screen.getByRole('button', { name: '删除' }));
    fireEvent.click(screen.getByRole('button', { name: '确认删除' }));
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('网络错误'));
  });
});


// ── 编辑（删旧插新, 修正错录） ──────────────────────────────────────

describe('TradesLog 编辑入口', () => {
  it('点击编辑展开行内表单（预填当前值）, 隐藏该行操作按钮; 取消后收起', () => {
    mockTrades([mkTrade('t1', { trade_date: '2026-08-19' })]);
    render(<TradesLog />);
    fireEvent.click(screen.getByRole('button', { name: '编辑' }));
    const form = screen.getByLabelText('交易记录编辑');
    expect((form.querySelector('input') as HTMLInputElement).value).toBe('600519'); // 预填代码
    expect(screen.getByDisplayValue('开仓')).toBeInTheDocument();                    // 预填事件类型
    expect(screen.getByDisplayValue('1710.5')).toBeInTheDocument();                  // 预填价格
    // 编辑中该行不再显示删除按钮
    expect(within(rowOf('600519')).queryByRole('button', { name: '删除' })).toBeNull();
    fireEvent.click(within(form).getByRole('button', { name: '取消' }));
    expect(screen.queryByLabelText('交易记录编辑')).toBeNull();
    expect(screen.getByRole('button', { name: '删除' })).toBeInTheDocument();
  });

  it('编辑保存调用 editTrade 并携带原 reason; 成功后表单收起', async () => {
    mockTrades([mkTrade('t1', { reason: 'pivot breakthrough' })]);
    render(<TradesLog />);
    fireEvent.click(screen.getByRole('button', { name: '编辑' }));
    fireEvent.change(screen.getByDisplayValue('1710.5'), { target: { value: '1720.0' } });
    fireEvent.click(screen.getByRole('button', { name: '保存修改' }));
    await waitFor(() => expect(editTrade).toHaveBeenCalledWith('t1', expect.objectContaining({
      price: 1720,
      reason: 'pivot breakthrough',
    })));
    await waitFor(() => expect(screen.queryByLabelText('交易记录编辑')).toBeNull());
  });
});


// ── 清仓事件删除护栏 (008 同口径) ────────────────────────────────────

describe('isCloseDeleteLocked + TradesLog 锁定 UI', () => {
  it('纯函数: close 超 7 天锁定, 7 天内/非 close 不锁', () => {
    const today = new Date('2026-08-21T00:00:00Z');
    const close8d = mkTrade('c8', { side: 'close', trade_date: '2026-08-12' });
    const close7d = mkTrade('c7', { side: 'close', trade_date: '2026-08-14' });
    const openOld = mkTrade('o1', { side: 'open', trade_date: '2026-01-01' });
    expect(isCloseDeleteLocked(close8d, today)).toBe(true);
    expect(isCloseDeleteLocked(close7d, today)).toBe(false);
    expect(isCloseDeleteLocked(openOld, today)).toBe(false);
  });

  it('锁定 close: 显示已锁定, 无删除按钮', () => {
    vi.useFakeTimers().setSystemTime(new Date('2026-08-21T00:00:00Z'));
    try {
      mockTrades([mkTrade('c1', { side: 'close', trade_date: '2026-08-10' })]);
      render(<TradesLog />);
      expect(screen.getByText('已锁定')).toBeInTheDocument();
      expect(screen.queryByRole('button', { name: '删除' })).toBeNull();
      expect(screen.queryByRole('button', { name: '编辑' })).toBeNull(); // 编辑=删+插, 同口径禁用
    } finally {
      vi.useRealTimers();
    }
  });

  it('7 天内 close: 可删且两步确认显示复活警告', () => {
    vi.useFakeTimers().setSystemTime(new Date('2026-08-21T00:00:00Z'));
    try {
      mockTrades([mkTrade('c2', { side: 'close', trade_date: '2026-08-18' })]);
      render(<TradesLog />);
      fireEvent.click(screen.getByRole('button', { name: '删除' }));
      expect(screen.getByText(/删除清仓事件会使该交易回到持仓列表/)).toBeInTheDocument();
      expect(screen.getByRole('button', { name: '确认删除' })).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });
});
