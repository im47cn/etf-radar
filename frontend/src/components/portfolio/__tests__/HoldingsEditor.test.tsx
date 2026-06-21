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
vi.mock('@/hooks/useHoldings', () => ({
  useHoldings: () => ({
    holdings: [], loading: false, error: null,
    upsert: upsertFn, remove: vi.fn(), refresh: vi.fn(),
  }),
}));

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
    // upsert 是 async，等一个 tick
    await new Promise(r => setTimeout(r, 0));
    expect(upsertFn).toHaveBeenCalledWith(expect.objectContaining({
      etf_code: '512480',
      shares: 1000,
    }));
  });
});
