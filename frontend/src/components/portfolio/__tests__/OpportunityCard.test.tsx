import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { OpportunityCard } from '../OpportunityCard';
import type { Opportunity } from '@/lib/portfolio/types';

const mkOpp = (overrides: Partial<Opportunity> = {}): Opportunity => ({
  themeId:     'storage_dram',
  themeName:   '存储芯片',
  primaryCn:   '512480',
  strength:    { short: 80, mid: 75, long: 60, composite: 85 },
  l2Tag:       '偏强',
  momentumTag: '动量向上',
  ...overrides,
});

const renderWithRouter = (opp: Opportunity) =>
  render(
    <MemoryRouter>
      <OpportunityCard opp={opp} />
    </MemoryRouter>,
  );

describe('OpportunityCard', () => {
  it('展示主题名 + 综合强度', () => {
    renderWithRouter(mkOpp());
    expect(screen.getByText('存储芯片')).toBeInTheDocument();
    expect(screen.getByText(/85/)).toBeInTheDocument();
  });

  it('展示 L2 标签', () => {
    renderWithRouter(mkOpp({ l2Tag: '偏强' }));
    expect(screen.getByText('偏强')).toBeInTheDocument();
  });

  it('动量向上时展示 momentumTag', () => {
    renderWithRouter(mkOpp({ momentumTag: '动量向上' }));
    expect(screen.getByText('动量向上')).toBeInTheDocument();
  });

  it('momentumTag 为 null 时不渲染该标签', () => {
    renderWithRouter(mkOpp({ momentumTag: null }));
    expect(screen.queryByText('动量向上')).not.toBeInTheDocument();
    expect(screen.queryByText('动量向下')).not.toBeInTheDocument();
  });

  it('跳转链接指向 RadarPage + theme 参数', () => {
    renderWithRouter(mkOpp({ themeId: 'robotics' }));
    const link = screen.getByRole('link', { name: /查看详情/ });
    expect(link.getAttribute('href')).toContain('theme=robotics');
  });

  it('文案保持 L1+L2 立场（不出现"买入/推荐"指令）', () => {
    renderWithRouter(mkOpp());
    const text = document.body.textContent ?? '';
    expect(text).not.toMatch(/推荐买入|建议买入|可买/);
  });
});
