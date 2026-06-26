import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { RadarTabs } from '../RadarTabs';

const renderAt = (path: string) =>
  render(
    <MemoryRouter initialEntries={[path]}>
      <RadarTabs />
    </MemoryRouter>,
  );

describe('RadarTabs', () => {
  it('renders 3 tab links', () => {
    renderAt('/');
    expect(screen.getByText('主题轮动').closest('a')).toHaveAttribute('href', '/');
    expect(screen.getByText('跨市雷达').closest('a')).toHaveAttribute('href', '/radar');
    expect(screen.getByText('我的持仓').closest('a')).toHaveAttribute('href', '/portfolio');
  });

  it('marks rotation tab active on root path', () => {
    renderAt('/');
    const rotationLink = screen.getByText('主题轮动').closest('a')!;
    expect(rotationLink.className).toMatch(/bg-blue-600/);
  });

  it('marks rotation tab active on /rotation (legacy alias)', () => {
    renderAt('/rotation');
    const rotationLink = screen.getByText('主题轮动').closest('a')!;
    expect(rotationLink.className).toMatch(/bg-blue-600/);
  });

  it('marks radar tab active on /radar', () => {
    renderAt('/radar');
    const radarLink = screen.getByText('跨市雷达').closest('a')!;
    expect(radarLink.className).toMatch(/bg-blue-600/);
  });

  it('marks portfolio tab active on /portfolio', () => {
    renderAt('/portfolio');
    const portfolioLink = screen.getByText('我的持仓').closest('a')!;
    expect(portfolioLink.className).toMatch(/bg-blue-600/);
  });
});
