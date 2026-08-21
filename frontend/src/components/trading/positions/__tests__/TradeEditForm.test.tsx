import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

vi.mock('@/hooks/useTrades', () => ({ useTrades: vi.fn() }));

import { useTrades } from '@/hooks/useTrades';
import { TradeEditForm } from '../TradeEditForm';
import type { Trade } from '@/lib/trading/types';

const editTrade = vi.fn();
const onDone = vi.fn();

const mkTrade = (over: Partial<Trade> = {}): Trade => ({
  id: 't1',
  user_id: 'u1',
  code: '600519',
  name: '贵州茅台',
  side: 'open',
  trade_date: '2026-08-19',
  price: 1710.5,
  shares: 100,
  stop_after: 1573.2,
  reason: 'test reason',
  created_at: '2026-08-19T07:00:00Z',
  updated_at: '2026-08-19T07:00:00Z',
  ...over,
});

beforeEach(() => {
  editTrade.mockReset().mockResolvedValue({ error: null });
  onDone.mockReset();
  vi.mocked(useTrades).mockReturnValue({
    editTrade, positions: [], trades: [], settings: null as never,
    loading: false, error: null, addTrade: vi.fn(), removeTrade: vi.fn(), updateSettings: vi.fn(), refresh: vi.fn(),
  } as never);
});

// 表单内按 label 定位输入（编辑表单无 placeholder）
const field = (label: string) => screen.getByLabelText(label, { exact: false }) as HTMLInputElement;

describe('TradeEditForm', () => {
  it('预填当前值（含 null 止损显示为空）', () => {
    render(<TradeEditForm trade={mkTrade({ stop_after: null })} onDone={onDone} />);
    expect(field('代码').value).toBe('600519');
    expect(field('名称').value).toBe('贵州茅台');
    expect(field('成交价').value).toBe('1710.5');
    expect(field('股数').value).toBe('100');
    expect(field('止损位').value).toBe('');
    expect(field('交易日期').value).toBe('2026-08-19');
    expect(screen.getByDisplayValue('开仓')).toBeInTheDocument();
  });

  it('合法提交调用 editTrade（修正后的值 + 原 reason）并 onDone 收起', async () => {
    render(<TradeEditForm trade={mkTrade()} onDone={onDone} />);
    fireEvent.change(field('名称'), { target: { value: '茅台' } });
    fireEvent.change(screen.getByDisplayValue('开仓'), { target: { value: 'add' } });
    fireEvent.change(field('交易日期'), { target: { value: '2026-08-20' } });
    fireEvent.change(field('股数'), { target: { value: '200' } });
    fireEvent.change(field('止损位'), { target: { value: '' } });
    fireEvent.click(screen.getByRole('button', { name: '保存修改' }));
    await waitFor(() => expect(editTrade).toHaveBeenCalledWith('t1', {
      code: '600519', name: '茅台', side: 'add',
      trade_date: '2026-08-20', price: 1710.5, shares: 200, stop_after: null,
      reason: 'test reason',
    }));
    await waitFor(() => expect(onDone).toHaveBeenCalled());
  });

  it('非法输入聚合报错且不提交', () => {
    render(<TradeEditForm trade={mkTrade()} onDone={onDone} />);
    fireEvent.change(field('代码'), { target: { value: '60051' } });
    fireEvent.change(field('成交价'), { target: { value: '0' } });
    fireEvent.click(screen.getByRole('button', { name: '保存修改' }));
    expect(screen.getByRole('alert').textContent).toContain('代码须为 6 位数字');
    expect(screen.getByRole('alert').textContent).toContain('价格须为正数');
    expect(editTrade).not.toHaveBeenCalled();
  });

  it('editTrade 失败展示错误且不收起', async () => {
    editTrade.mockResolvedValue({ error: '原记录已删除但新记录写入失败（network）' });
    render(<TradeEditForm trade={mkTrade()} onDone={onDone} />);
    fireEvent.click(screen.getByRole('button', { name: '保存修改' }));
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('原记录已删除但新记录写入失败'));
    expect(onDone).not.toHaveBeenCalled();
    expect(screen.getByLabelText('交易记录编辑')).toBeInTheDocument();
  });
});
