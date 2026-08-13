import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ArchTimeSeries } from '@/components/evidence/ArchTimeSeries';

describe('ArchTimeSeries', () => {
  it('渲染逐月滚动标题', () => {
    render(<ArchTimeSeries timeSeries={[
      { period: '2024-09', arch_ratio: 0.55, arch_count: 16, tested: 29 },
      { period: '2024-10', arch_ratio: 0.66, arch_count: 19, tested: 29 },
    ]} />);
    expect(screen.getByText(/逐月·120日滚动/)).toBeInTheDocument();
  });

  it('空数据显示占位', () => {
    const { container } = render(<ArchTimeSeries timeSeries={[]} />);
    expect(container.textContent).toMatch(/暂无/);
  });
});
