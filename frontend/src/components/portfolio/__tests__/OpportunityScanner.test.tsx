import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { OpportunityScanner } from '../OpportunityScanner';
import type { ThemeMetric } from '@/lib/portfolio/types';

const mkTheme = (
  id: string,
  composite: number,
  short: number,
): ThemeMetric => ({
  id,
  name:       `主题${id}`,
  primary_cn: `${id}-cn`,
  strength: { short, mid: 60, long: 60, composite },
});

const renderScanner = (themes: ThemeMetric[], ownedThemeIds = new Set<string>()) =>
  render(
    <MemoryRouter>
      <OpportunityScanner themes={themes} ownedThemeIds={ownedThemeIds} />
    </MemoryRouter>,
  );

describe('OpportunityScanner', () => {
  it('默认折叠，仅渲染标题', () => {
    renderScanner([mkTheme('a', 90, 90)]);
    expect(screen.getByText(/信号扫描/)).toBeInTheDocument();
    expect(screen.queryByText('主题a')).not.toBeInTheDocument();
  });

  it('标题显示候选数', () => {
    renderScanner([
      mkTheme('a', 90, 90),
      mkTheme('b', 80, 80),
      mkTheme('c', 60, 60),  // 不达标
    ]);
    expect(screen.getByText(/信号扫描\s*\(\s*2\s*\)/)).toBeInTheDocument();
  });

  it('点击标题展开，渲染候选卡', () => {
    renderScanner([mkTheme('a', 90, 90)]);
    fireEvent.click(screen.getByRole('button', { name: /信号扫描/ }));
    expect(screen.getByText('主题a')).toBeInTheDocument();
  });

  it('展开 + 候选为 0 时显示空态文案', () => {
    renderScanner([mkTheme('a', 60, 60)]); // 不达标
    fireEvent.click(screen.getByRole('button', { name: /信号扫描/ }));
    expect(screen.getByText(/当前无满足筛选条件的主题/)).toBeInTheDocument();
  });

  it('排除 ownedThemeIds', () => {
    renderScanner(
      [mkTheme('a', 90, 90), mkTheme('b', 90, 90)],
      new Set(['a']),
    );
    fireEvent.click(screen.getByRole('button', { name: /信号扫描/ }));
    expect(screen.queryByText('主题a')).not.toBeInTheDocument();
    expect(screen.getByText('主题b')).toBeInTheDocument();
  });

  it('再次点击标题折叠', () => {
    renderScanner([mkTheme('a', 90, 90)]);
    const btn = screen.getByRole('button', { name: /信号扫描/ });
    fireEvent.click(btn);
    expect(screen.getByText('主题a')).toBeInTheDocument();
    fireEvent.click(btn);
    expect(screen.queryByText('主题a')).not.toBeInTheDocument();
  });

  it('展开后展示阈值说明（用户知道筛选条件）', () => {
    renderScanner([mkTheme('a', 90, 90)]);
    fireEvent.click(screen.getByRole('button', { name: /信号扫描/ }));
    expect(screen.getByText(/75/)).toBeInTheDocument();
    expect(screen.getByText(/70/)).toBeInTheDocument();
  });
});
