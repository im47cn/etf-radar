import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { GridFitnessRanking, buildGridData, renderNameTick } from '@/components/evidence/GridFitnessRanking';

describe('GridFitnessRanking', () => {
  it('渲染标题与主题排名 (含 suitable/unsuitable 两类)', () => {
    render(<GridFitnessRanking themes={[
      { theme_id: 'a', name: '半导体', n: 1200, ann_vol: 0.32, hurst: 0.42, arch_neg_log10p: 5,
        pct_vol: 0.9, pct_mean_reversion: 0.7, pct_arch: 0.9, grid_score: 0.82, verdict: 'suitable' },
      { theme_id: 'b', name: '电力', n: 1200, ann_vol: 0.18, hurst: 0.5, arch_neg_log10p: 3,
        pct_vol: 0.2, pct_mean_reversion: 0.5, pct_arch: 0.5, grid_score: 0.29, verdict: 'unsuitable' },
    ]} />);
    expect(screen.getByText(/主题网格适配度排名/)).toBeInTheDocument();
  });

  it('空数据显示占位', () => {
    const { container } = render(<GridFitnessRanking themes={[]} />);
    expect(container.textContent).toMatch(/暂无/);
  });

  it('buildGridData 按 grid_score 降序 + verdict 缺省兜底', () => {
    const data = buildGridData([
      { theme_id: 'a', name: '低分', grid_score: 0.3 } as never,
      { theme_id: 'b', name: '高分', grid_score: 0.8, verdict: 'suitable' } as never,
    ]);
    expect(data[0].name).toBe('高分');
    expect(data[1].name).toBe('低分');
    expect(data[1].verdict).toBe('marginal'); // verdict 缺省 → marginal
  });

  it('renderNameTick 渲染主题名', () => {
    const { container } = render(
      <svg>{renderNameTick({ x: 80, y: 10, payload: { value: '半导体' } })}</svg>,
    );
    expect(container.textContent).toContain('半导体');
  });
});
