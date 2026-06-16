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
    expect(screen.getByText('跨市雷达').closest('a')).toHaveAttribute('href', '/');
    expect(screen.getByText('主题轮动').closest('a')).toHaveAttribute('href', '/rotation');
    expect(screen.getByText(/持仓监控/)).toBeInTheDocument();
  });

  it('marks active tab when on root path', () => {
    renderAt('/');
    const radarLink = screen.getByText('跨市雷达').closest('a')!;
    expect(radarLink.className).toMatch(/bg-blue-600/);
  });

  it('marks rotation tab active on /rotation', () => {
    renderAt('/rotation');
    const rotationLink = screen.getByText('主题轮动').closest('a')!;
    expect(rotationLink.className).toMatch(/bg-blue-600/);
  });
});
