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
  it('renders tab links', () => {
    renderAt('/');
    expect(screen.getByText('温度').closest('a')).toHaveAttribute('href', '/');
    expect(screen.getByText('轮动').closest('a')).toHaveAttribute('href', '/rotation');
    expect(screen.getByText('雷达').closest('a')).toHaveAttribute('href', '/radar');
    expect(screen.getByText('持仓').closest('a')).toHaveAttribute('href', '/portfolio');
  });

  it('marks temperature tab active on /temperature', () => {
    renderAt('/temperature');
    expect(screen.getByText('温度').closest('a')!.className).toMatch(/bg-blue-600/);
  });

  it('marks temperature tab active on root path', () => {
    renderAt('/');
    const temperatureLink = screen.getByText('温度').closest('a')!;
    expect(temperatureLink.className).toMatch(/bg-blue-600/);
  });

  it('marks rotation tab active on /rotation (legacy alias)', () => {
    renderAt('/rotation');
    const rotationLink = screen.getByText('轮动').closest('a')!;
    expect(rotationLink.className).toMatch(/bg-blue-600/);
  });

  it('marks radar tab active on /radar', () => {
    renderAt('/radar');
    const radarLink = screen.getByText('雷达').closest('a')!;
    expect(radarLink.className).toMatch(/bg-blue-600/);
  });

  it('marks portfolio tab active on /portfolio', () => {
    renderAt('/portfolio');
    const portfolioLink = screen.getByText('持仓').closest('a')!;
    expect(portfolioLink.className).toMatch(/bg-blue-600/);
  });
});
