import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ArchTimeSeries } from '@/components/evidence/ArchTimeSeries';

describe('ArchTimeSeries', () => {
  it('渲染逐季标题 (含 is_partial true/false 两类点)', () => {
    render(<ArchTimeSeries timeSeries={[
      { period: '2024-Q3', arch_ratio: 0.55, arch_count: 16, tested: 29 },
      { period: '2026-Q3', arch_ratio: 0.07, arch_count: 2, tested: 30, is_partial: true },
    ]} />);
    expect(screen.getByText(/ARCH 显著比例（逐季）/)).toBeInTheDocument();
  });

  it('空数据显示占位', () => {
    const { container } = render(<ArchTimeSeries timeSeries={[]} />);
    expect(container.textContent).toMatch(/暂无/);
  });
});
