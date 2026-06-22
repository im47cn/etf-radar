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

const coveredNoThemeScore: HoldingScore = {
  etfCode: '159559',
  status: 'covered',
  name: '机器人ETF景顺',
  shares: 1000,
  costPrice: 1.40,
  currentPrice: 1.44,
  marketValue: 1440,
  pnlAbs: 40,
  pnlPct: 0.0286,
  selfStrength: { short: 73, mid: 76, long: 58, composite: 68 },
  // 故意不填 themeId/themeName/themeUsStrength — 仿 theme_id 反查未命中
  quadrant: 'leading',
  l2Tag: '中性偏强',
  momentumTag: '动量向上',
  narrative: '综合 68 分位，短中周期偏强',
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

  it('菜单默认折叠, 不占用页面空间', () => {
    render(<HoldingScoreCard score={coveredScore} onDelete={vi.fn()} onEdit={vi.fn()} />);
    expect(screen.queryByRole('menu')).toBeNull();
    expect(screen.queryByRole('menuitem', { name: /删除/ })).toBeNull();
    expect(screen.queryByRole('menuitem', { name: /编辑/ })).toBeNull();
    // 仅 kebab 触发器可见
    expect(screen.getByRole('button', { name: /操作菜单/ })).toBeInTheDocument();
  });

  it('点 ⋯ 展开菜单后, 点删除触发 onDelete', () => {
    const onDelete = vi.fn();
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    render(<HoldingScoreCard score={coveredScore} onDelete={onDelete} />);
    fireEvent.click(screen.getByRole('button', { name: /操作菜单/ }));
    fireEvent.click(screen.getByRole('menuitem', { name: /删除/ }));
    expect(onDelete).toHaveBeenCalledWith('512480');
  });

  it('onEdit 存在时菜单含编辑项, 点击回传 etfCode', () => {
    const onEdit = vi.fn();
    render(<HoldingScoreCard score={coveredScore} onDelete={vi.fn()} onEdit={onEdit} />);
    fireEvent.click(screen.getByRole('button', { name: /操作菜单/ }));
    fireEvent.click(screen.getByRole('menuitem', { name: /编辑/ }));
    expect(onEdit).toHaveBeenCalledWith('512480');
  });

  it('未提供 onEdit 时菜单不渲染编辑项, 仅删除可用', () => {
    render(<HoldingScoreCard score={coveredScore} onDelete={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: /操作菜单/ }));
    expect(screen.queryByRole('menuitem', { name: /编辑/ })).toBeNull();
    expect(screen.getByRole('menuitem', { name: /删除/ })).toBeInTheDocument();
  });

  it('1:N — 渲染次要归属 chip 行 + 边界提示文案', () => {
    const score: HoldingScore = {
      ...coveredScore,
      secondaryThemes: [{ id: 'semiconductor', name: '半导体' }],
    };
    render(<HoldingScoreCard score={score} onDelete={vi.fn()} />);
    expect(screen.getByText('也属于')).toBeInTheDocument();
    expect(screen.getByText('半导体')).toBeInTheDocument();
    // 边界提示：百分位仅基于主归属计算
    expect(screen.getByText(/百分位仅基于主归属计算/)).toBeInTheDocument();
  });

  it('1:N — secondaryThemes 超过 3 个时折叠为 +N', () => {
    const score: HoldingScore = {
      ...coveredScore,
      secondaryThemes: [
        { id: 't1', name: '主题一' },
        { id: 't2', name: '主题二' },
        { id: 't3', name: '主题三' },
        { id: 't4', name: '主题四' },
        { id: 't5', name: '主题五' },
      ],
    };
    render(<HoldingScoreCard score={score} onDelete={vi.fn()} />);
    expect(screen.getByText('主题一')).toBeInTheDocument();
    expect(screen.getByText('主题二')).toBeInTheDocument();
    expect(screen.getByText('主题三')).toBeInTheDocument();
    // 第 4、5 个不渲染为 chip
    expect(screen.queryByText('主题四')).toBeNull();
    expect(screen.queryByText('主题五')).toBeNull();
    // 显示 +2
    expect(screen.getByText('+2')).toBeInTheDocument();
  });

  it('1:N — 无次要归属时不渲染 chip 行', () => {
    render(<HoldingScoreCard score={coveredScore} onDelete={vi.fn()} />);
    expect(screen.queryByText('也属于')).toBeNull();
    expect(screen.queryByText(/百分位仅基于主归属计算/)).toBeNull();
  });

  it('covered 但无主题归属: 显示 ETF 自身百分位 + narrative, 不渲染归属主题区', () => {
    render(<HoldingScoreCard score={coveredNoThemeScore} onDelete={vi.fn()} />);
    // 仍是 covered 风格
    expect(screen.getByText('中性偏强')).toBeInTheDocument();
    expect(screen.getByText('动量向上')).toBeInTheDocument();
    // 自身百分位仍可见
    expect(screen.getByText(/ETF 自身百分位/)).toBeInTheDocument();
    // narrative 仍可见（"综合 68 分位"是 narrative 文案；"综合 68"是百分位数字 — 两处都出现）
    expect(screen.getAllByText(/综合 68/).length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText(/综合 68 分位/)).toBeInTheDocument();
    // 归属主题区域不渲染
    expect(screen.queryByText(/归属主题/)).toBeNull();
    expect(screen.queryByText(/双轨强度/)).toBeNull();
    // 不应误判为 uncovered
    expect(screen.queryByText(/无信号/)).toBeNull();
    expect(screen.queryByText(/不在信号覆盖范围/)).toBeNull();
  });
});
