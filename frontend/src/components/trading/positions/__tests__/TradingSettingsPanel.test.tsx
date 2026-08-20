import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

vi.mock('@/hooks/useTrades', () => ({ useTrades: vi.fn() }));

import { useTrades } from '@/hooks/useTrades';
import { TradingSettingsPanel } from '../TradingSettingsPanel';
import { DEFAULT_SETTINGS_VALUES, type TradingSettings } from '@/lib/trading/types';

const updateSettings = vi.fn();

const mkSettings = (over: Partial<TradingSettings> = {}): TradingSettings => ({
  user_id: '',
  updated_at: '',
  ...DEFAULT_SETTINGS_VALUES,
  ...over,
});

const mockSettings = (settings: TradingSettings) => {
  vi.mocked(useTrades).mockReturnValue({
    settings, trades: [], positions: [], loading: false, error: null,
    addTrade: vi.fn(), removeTrade: vi.fn(), updateSettings, refresh: vi.fn(),
  } as never);
};

beforeEach(() => {
  updateSettings.mockReset().mockResolvedValue({ error: null });
});

const inputAt = (label: string) => screen.getByLabelText(label) as HTMLInputElement;

describe('TradingSettingsPanel', () => {
  it('渲染 settings 回填的默认值 (equity 空串)', () => {
    mockSettings(mkSettings());
    render(<TradingSettingsPanel />);
    expect(inputAt('账户权益（元）')).toHaveValue('');
    expect(inputAt('单笔风险 %')).toHaveValue('0.75');
    expect(inputAt('最多持仓数')).toHaveValue('5');
    expect(inputAt('单票市值上限 %')).toHaveValue('20');
    expect(inputAt('组合总风险上限 %')).toHaveValue('4');
  });

  it('settings 异步回填后输入框同步 (refresh 更新引用)', () => {
    mockSettings(mkSettings());
    const { rerender } = render(<TradingSettingsPanel />);
    mockSettings(mkSettings({ equity_cny: 200000, risk_per_trade_pct: 1 }));
    rerender(<TradingSettingsPanel />);
    expect(inputAt('账户权益（元）')).toHaveValue('200000');
    expect(inputAt('单笔风险 %')).toHaveValue('1');
  });

  it('合法保存透传五参数, equity 空串转 null, 成功提示', async () => {
    mockSettings(mkSettings());
    render(<TradingSettingsPanel />);
    fireEvent.change(inputAt('账户权益（元）'), { target: { value: '' } });
    fireEvent.change(inputAt('单笔风险 %'), { target: { value: '1' } });
    fireEvent.change(inputAt('单票市值上限 %'), { target: { value: '30' } });
    fireEvent.change(inputAt('组合总风险上限 %'), { target: { value: '5' } });
    fireEvent.click(screen.getByRole('button', { name: '保存参数' }));
    await waitFor(() => expect(screen.getByText('✓ 已保存')).toBeInTheDocument());
    expect(updateSettings).toHaveBeenCalledWith({
      equity_cny: null, risk_per_trade_pct: 1,
      max_positions: 5, max_position_pct: 30, max_portfolio_risk_pct: 5,
    });
  });

  it('非法值聚合报错且不保存', () => {
    mockSettings(mkSettings());
    render(<TradingSettingsPanel />);
    fireEvent.change(inputAt('账户权益（元）'), { target: { value: '-1' } });
    fireEvent.change(inputAt('单笔风险 %'), { target: { value: '0' } });
    fireEvent.change(inputAt('最多持仓数'), { target: { value: '2.5' } });
    fireEvent.click(screen.getByRole('button', { name: '保存参数' }));
    const alert = screen.getByRole('alert');
    expect(alert.textContent).toContain('账户权益须为正数（可留空）');
    expect(alert.textContent).toContain('单笔风险须为正数');
    expect(alert.textContent).toContain('最多持仓数须为正整数');
    expect(updateSettings).not.toHaveBeenCalled();
  });

  it('updateSettings 失败展示错误', async () => {
    updateSettings.mockResolvedValue({ error: 'Supabase 未配置' });
    mockSettings(mkSettings());
    render(<TradingSettingsPanel />);
    fireEvent.click(screen.getByRole('button', { name: '保存参数' }));
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Supabase 未配置'));
    expect(screen.queryByText('✓ 已保存')).toBeNull();
  });
});
