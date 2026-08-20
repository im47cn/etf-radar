import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

vi.mock('@/hooks/useTrades', () => ({ useTrades: vi.fn() }));

import { useTrades } from '@/hooks/useTrades';
import { TradeEntryForm } from '../TradeEntryForm';

const addTrade = vi.fn();

beforeEach(() => {
  addTrade.mockReset().mockResolvedValue({ error: null });
  vi.mocked(useTrades).mockReturnValue({
    addTrade, positions: [], trades: [], settings: null as never,
    loading: false, error: null, removeTrade: vi.fn(), updateSettings: vi.fn(), refresh: vi.fn(),
  } as never);
});

// 日期 input 的默认值是本地今天（本地时区切日, 不用 toISOString）
const todayLocal = (): string => {
  const d = new Date();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${d.getFullYear()}-${m}-${day}`;
};

const fillValid = (sideValue = 'open') => {
  fireEvent.change(screen.getByPlaceholderText('600519'), { target: { value: '600519' } });
  fireEvent.change(screen.getByPlaceholderText('贵州茅台'), { target: { value: '贵州茅台' } });
  fireEvent.change(screen.getByDisplayValue('开仓'), { target: { value: sideValue } });
  fireEvent.change(screen.getByPlaceholderText('17.10'), { target: { value: '1710.5' } });
  fireEvent.change(screen.getByPlaceholderText('100'), { target: { value: '100' } });
};

const submit = () => fireEvent.click(screen.getByRole('button', { name: '记入流水' }));

describe('TradeEntryForm', () => {
  it('默认渲染: 事件类型默认开仓, 日期默认今天, 含记账口径说明', () => {
    render(<TradeEntryForm />);
    expect(screen.getByLabelText('交易记录录入')).toBeInTheDocument();
    expect(screen.getByText(/不构成操作指令/)).toBeInTheDocument();
    const dateInput = screen.getByDisplayValue(todayLocal());
    expect(dateInput).toBeInTheDocument();
    expect(screen.getByDisplayValue('开仓')).toBeInTheDocument();
  });

  it('合法提交调用 addTrade 并清空/提示成功', async () => {
    render(<TradeEntryForm />);
    fillValid();
    fireEvent.change(screen.getByPlaceholderText('15.73'), { target: { value: '1573.2' } });
    submit();
    await waitFor(() => expect(screen.getByText('✓ 已记入流水')).toBeInTheDocument());
    expect(addTrade).toHaveBeenCalledTimes(1);
    expect(addTrade).toHaveBeenCalledWith({
      code: '600519', name: '贵州茅台', side: 'open',
      trade_date: todayLocal(), price: 1710.5, shares: 100, stop_after: 1573.2,
    });
    // 成功后清空输入
    expect(screen.getByPlaceholderText('600519')).toHaveValue('');
    expect(screen.getByPlaceholderText('17.10')).toHaveValue('');
  });

  it('止损位留空提交 stop_after 为 null; 清仓事件枚举透传', async () => {
    render(<TradeEntryForm />);
    fillValid('close');
    submit();
    await waitFor(() => expect(screen.getByText('✓ 已记入流水')).toBeInTheDocument());
    expect(addTrade).toHaveBeenCalledWith(expect.objectContaining({ side: 'close', stop_after: null }));
  });

  it('非法输入聚合报错且不提交 (代码/名称/价格/股数/止损位)', () => {
    render(<TradeEntryForm />);
    fireEvent.change(screen.getByPlaceholderText('600519'), { target: { value: '60051' } });
    fireEvent.change(screen.getByPlaceholderText('17.10'), { target: { value: '0' } });
    fireEvent.change(screen.getByPlaceholderText('100'), { target: { value: '1.5' } });
    fireEvent.change(screen.getByPlaceholderText('15.73'), { target: { value: '0' } });
    submit();
    expect(screen.getByRole('alert').textContent).toContain('代码须为 6 位数字');
    expect(screen.getByRole('alert').textContent).toContain('请填写名称');
    expect(screen.getByRole('alert').textContent).toContain('价格须为正数');
    expect(screen.getByRole('alert').textContent).toContain('股数须为正整数');
    expect(screen.getByRole('alert').textContent).toContain('止损位须为正数（可留空）');
    expect(addTrade).not.toHaveBeenCalled();
  });

  it('日期清空报错', () => {
    render(<TradeEntryForm />);
    fillValid();
    fireEvent.change(screen.getByDisplayValue(todayLocal()), { target: { value: '' } });
    submit();
    expect(screen.getByText(/请填写交易日期/)).toBeInTheDocument();
    expect(addTrade).not.toHaveBeenCalled();
  });

  it('addTrade 返回错误时展示且不清空表单', async () => {
    addTrade.mockResolvedValue({ error: '未登录' });
    render(<TradeEntryForm />);
    fillValid();
    submit();
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('未登录'));
    expect(screen.queryByText('✓ 已记入流水')).toBeNull();
    expect(screen.getByPlaceholderText('600519')).toHaveValue('600519');
  });
});
