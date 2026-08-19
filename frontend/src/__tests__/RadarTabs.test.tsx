import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { RadarTabs } from '@/components/Header/RadarTabs';

describe('RadarTabs', () => {
  it('旅程式顺序: 温度→雷达→轮动→持仓→自选→证据→网格→贵金属', () => {
    render(
      <MemoryRouter>
        <RadarTabs />
      </MemoryRouter>,
    );
    const labels = screen.getAllByRole('link').map((a) => a.textContent);
    expect(labels).toEqual(['温度', '雷达', '轮动', '持仓', '自选', '证据', '网格', '贵金属']);
  });

  it('当前路径对应 tab 高亮 (bg-blue-600)', () => {
    render(
      <MemoryRouter initialEntries={['/evidence']}>
        <RadarTabs />
      </MemoryRouter>,
    );
    expect(screen.getByText('证据').className).toContain('bg-blue-600');
    expect(screen.getByText('温度').className).not.toContain('bg-blue-600');
  });

  it('根路径 / 命中温度 tab (首页别名)', () => {
    render(
      <MemoryRouter initialEntries={['/']}>
        <RadarTabs />
      </MemoryRouter>,
    );
    expect(screen.getByText('温度').className).toContain('bg-blue-600');
  });
});
