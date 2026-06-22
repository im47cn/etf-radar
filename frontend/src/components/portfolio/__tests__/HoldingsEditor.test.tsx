import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { HoldingsEditor } from '../HoldingsEditor';

// EtfCodeAutocomplete 读 useDataContext().etfs?.etfs；stub 出最小满足结构
vi.mock('@/providers/dataContext', () => ({
  useDataContext: () => ({
    themes: undefined,
    etfs: {
      schema_version: '1.0',
      generated_at: '',
      etfs: [{ code: '512480', name: '半导体ETF国联安' }],
    },
    signals: undefined,
    meta: undefined,
    isLoading: false,
    error: null,
  }),
}));

const upsertFn = vi.fn().mockResolvedValue({ error: null, merged: false });
const updateFn = vi.fn().mockResolvedValue({ error: null });
vi.mock('@/hooks/useHoldings', () => ({
  useHoldings: () => ({
    holdings: [], loading: false, error: null,
    upsert: upsertFn, update: updateFn, remove: vi.fn(), refresh: vi.fn(),
  }),
}));

const editingHolding = {
  id: 'h1', user_id: 'u1', etf_code: '512480',
  shares: 100, cost_price: 2.0, note: '旧备注',
  created_at: '2026-01-01', updated_at: '2026-01-01',
};

describe('HoldingsEditor', () => {
  it('open 时渲染表单', () => {
    render(<HoldingsEditor open onClose={vi.fn()} />);
    expect(screen.getByText('添加持仓')).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/ETF 代码/)).toBeInTheDocument();
  });

  it('不 open 时不渲染', () => {
    render(<HoldingsEditor open={false} onClose={vi.fn()} />);
    expect(screen.queryByText('添加持仓')).toBeNull();
  });

  it('提交：调用 upsert', async () => {
    upsertFn.mockClear();
    render(<HoldingsEditor open onClose={vi.fn()} />);
    fireEvent.change(screen.getByPlaceholderText(/ETF 代码/), { target: { value: '512480' } });
    fireEvent.change(screen.getByLabelText(/持有份额/), { target: { value: '1000' } });
    fireEvent.click(screen.getByRole('button', { name: /保存/ }));
    await new Promise(r => setTimeout(r, 0));
    expect(upsertFn).toHaveBeenCalledWith(expect.objectContaining({
      etf_code: '512480',
      shares: 1000,
    }));
  });

  it('编辑模式：标题=编辑持仓 + 字段回填 + 代码只读', () => {
    render(<HoldingsEditor open onClose={vi.fn()} editing={editingHolding} />);
    expect(screen.getByText('编辑持仓')).toBeInTheDocument();
    expect(screen.getByLabelText(/ETF 代码 \(不可修改\)/)).toHaveValue('512480');
    expect(screen.getByLabelText(/持有份额/)).toHaveValue(100);
    expect(screen.getByText(/如需更改代码/)).toBeInTheDocument();
  });

  it('编辑模式提交：调用 update 不调 upsert', async () => {
    upsertFn.mockClear();
    updateFn.mockClear();
    render(<HoldingsEditor open onClose={vi.fn()} editing={editingHolding} />);
    fireEvent.change(screen.getByLabelText(/持有份额/), { target: { value: '500' } });
    fireEvent.click(screen.getByRole('button', { name: /保存/ }));
    await new Promise(r => setTimeout(r, 0));
    expect(updateFn).toHaveBeenCalledWith('512480', expect.objectContaining({
      shares: 500,
      cost_price: 2.0,
      note: '旧备注',
    }));
    expect(upsertFn).not.toHaveBeenCalled();
  });
});
