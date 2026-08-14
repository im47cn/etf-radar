import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import {
  GridFitnessRanking, GridTooltip, buildGridData, renderNameTick,
} from '@/components/evidence/GridFitnessRanking';

const TREND_ROW = {
  name: '⚠ 中概互联网/港股', score: 0.716, vol: 0.45, hurst: 0.498, verdict: 'marginal',
  ret60: -0.044, ret120: -0.197, trendRegime: 'down',
};

describe('GridFitnessRanking', () => {
  it('渲染标题与主题排名 (含 suitable/unsuitable 两类)', () => {
    render(<GridFitnessRanking themes={[
      { theme_id: 'a', name: '半导体', n: 1200, ann_vol: 0.32, hurst: 0.42, arch_neg_log10p: 5,
        pct_vol: 0.9, pct_mean_reversion: 0.7, pct_arch: 0.9, grid_score: 0.82, verdict: 'suitable',
        ret_60d: 0.02, ret_120d: 0.05, trend_regime: null },
      { theme_id: 'b', name: '电力', n: 1200, ann_vol: 0.18, hurst: 0.5, arch_neg_log10p: 3,
        pct_vol: 0.2, pct_mean_reversion: 0.5, pct_arch: 0.5, grid_score: 0.29, verdict: 'unsuitable',
        ret_60d: null, ret_120d: null, trend_regime: null },
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

  it('buildGridData 趋势护栏主题加 ⚠ 前缀并透传近期涨跌', () => {
    const data = buildGridData([
      { theme_id: 'cn', name: '中概互联', grid_score: 0.716, verdict: 'suitable',
        ret_60d: -0.044, ret_120d: -0.197, trend_regime: 'down' } as never,
      { theme_id: 'x', name: '震荡', grid_score: 0.5, verdict: 'marginal',
        ret_60d: 0.02, ret_120d: -0.03, trend_regime: null } as never,
    ]);
    expect(data[0].name).toBe('⚠ 中概互联');
    expect(data[0].trendRegime).toBe('down');
    expect(data[0].ret120).toBe(-0.197);
    expect(data[0].ret60).toBe(-0.044);
    expect(data[1].name).toBe('震荡'); // 非趋势不加前缀
    expect(data[1].trendRegime).toBeNull();
  });

  it('renderNameTick 渲染主题名', () => {
    const { container } = render(
      <svg>{renderNameTick({ x: 80, y: 10, payload: { value: '半导体' } })}</svg>,
    );
    expect(container.textContent).toContain('半导体');
  });

  it('GridTooltip 趋势主题显示单边下跌警示与近期涨跌', () => {
    const { container } = render(
      <GridTooltip active payload={[{ payload: TREND_ROW }]} />,
    );
    expect(container.textContent).toContain('近60日 -4.4%');
    expect(container.textContent).toContain('近120日 -19.7%');
    expect(container.textContent).toMatch(/单边下跌/);
    expect(container.textContent).toMatch(/套牢/);
  });

  it('GridTooltip 非趋势主题无警示行, 缺省涨跌显示 —', () => {
    const { container } = render(
      <GridTooltip active payload={[{ payload: {
        ...TREND_ROW, name: '震荡', trendRegime: null, ret60: null, ret120: null,
      } }]} />,
    );
    expect(container.textContent).not.toContain('单边');
    expect(container.textContent).toContain('近60日 —');
  });

  it('GridTooltip inactive / 空 payload 返回 null', () => {
    const { container } = render(<GridTooltip active={false} payload={[{ payload: TREND_ROW }]} />);
    expect(container.firstChild).toBeNull();
    const { container: c2 } = render(<GridTooltip active payload={[]} />);
    expect(c2.firstChild).toBeNull();
  });
});
