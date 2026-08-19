import { describe, expect, it } from 'vitest';
import { render } from '@testing-library/react';
import { Sparkline } from '../Sparkline';

describe('Sparkline', () => {
  it('点数 <2 时渲染空占位', () => {
    const { container } = render(<Sparkline points={[]} />);
    expect(container.querySelector('svg')).toBeNull();
  });

  it('上行走势画蓝色路径, 下行走势画红色', () => {
    const up = render(<Sparkline points={[['d1', 1], ['d2', 2], ['d3', 3]]} />);
    expect(up.container.querySelector('path')?.getAttribute('class')).toContain('stroke-blue-600');
    const down = render(<Sparkline points={[['d1', 3], ['d2', 2], ['d3', 1]]} />);
    expect(down.container.querySelector('path')?.getAttribute('class')).toContain('stroke-red-600');
  });

  it('全部等值 (span=0) 不除零', () => {
    const { container } = render(<Sparkline points={[['d1', 5], ['d2', 5]]} />);
    expect(container.querySelector('path')?.getAttribute('d')).toBeTruthy();
  });
});
