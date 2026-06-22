import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { HoldingScoreCard } from '../HoldingScoreCard';
import type { HoldingScore } from '@/lib/portfolio/types';

const coveredScore: HoldingScore = {
  etfCode: '512480',
  status: 'covered',
  name: '半导体ETF国联安',
  shares: 1000,
  costPrice: 2.0,
  currentPrice: 2.48,
  marketValue: 2480,
  pnlAbs: 480,
  pnlPct: 0.24,
  selfStrength: { short: 95, mid: 99, long: 99, composite: 98 },
  themeName: '存储芯片',
  themeId: 'storage_dram',
  themeSignal: 'resonance',
  themeUsStrength: { short: 99, mid: 96, long: 99, composite: 98 },
  themeCnStrength: { short: 96, mid: 99, long: 98, composite: 98 },
  quadrant: 'leading',
  l2Tag: '偏强',
  momentumTag: '动量向上',
  narrative: '位于领涨象限，综合强度 98 分位，中周期强劲，美股 A 股共振',
};

const uncoveredScore: HoldingScore = {
  etfCode: '159928',
  status: 'uncovered',
  shares: 500,
  costPrice: 1.85,
  currentPrice: null,
  marketValue: null,
  pnlAbs: null,
  pnlPct: null,
};

describe('HoldingScoreCard', () => {
  it('covered: 渲染所有字段', () => {
    render(<HoldingScoreCard score={coveredScore} onDelete={vi.fn()} />);
    expect(screen.getByText('512480')).toBeInTheDocument();
    expect(screen.getByText(/半导体ETF国联安/)).toBeInTheDocument();
    expect(screen.getByText('偏强')).toBeInTheDocument();
    expect(screen.getByText('动量向上')).toBeInTheDocument();
    expect(screen.getByText(/存储芯片/)).toBeInTheDocument();
    expect(screen.getByText(/位于领涨象限/)).toBeInTheDocument();
    expect(screen.getByText(/共振/)).toBeInTheDocument();
  });

  it('uncovered: 显示灰版 + 无信号提示', () => {
    render(<HoldingScoreCard score={uncoveredScore} onDelete={vi.fn()} />);
    expect(screen.getByText('159928')).toBeInTheDocument();
    expect(screen.getByText(/无信号/)).toBeInTheDocument();
    expect(screen.getByText(/不在信号覆盖范围/)).toBeInTheDocument();
  });

  it('delete 按钮触发 onDelete', () => {
    const onDelete = vi.fn();
    // 用 confirm spy 让 confirm 返回 true
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    render(<HoldingScoreCard score={coveredScore} onDelete={onDelete} />);
    fireEvent.click(screen.getByRole('button', { name: /删除/ }));
    expect(onDelete).toHaveBeenCalledWith('512480');
  });

  it('onEdit 存在时显示编辑按钮并回传 etfCode', () => {
    const onEdit = vi.fn();
    render(<HoldingScoreCard score={coveredScore} onDelete={vi.fn()} onEdit={onEdit} />);
    fireEvent.click(screen.getByRole('button', { name: /编辑/ }));
    expect(onEdit).toHaveBeenCalledWith('512480');
  });

  it('未提供 onEdit 不渲染编辑按钮', () => {
    render(<HoldingScoreCard score={coveredScore} onDelete={vi.fn()} />);
    expect(screen.queryByRole('button', { name: /编辑/ })).toBeNull();
  });
});
