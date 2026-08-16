import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ScorecardPanel, buildScorecardRows } from '@/components/evidence/ScorecardPanel';
import type { ScorecardEntry } from '@/types/signalEvidence';

const entry = (over: Partial<ScorecardEntry>): ScorecardEntry => ({
  signal: 'resonance',
  tier: null,
  window_days: 60,
  n: 120,
  hit_rate: 0.55,
  ci_low: 0.46,
  ci_high: 0.64,
  baseline: 0.55,
  status: 'consistent',
  ...over,
});

describe('buildScorecardRows', () => {
  it('排序: resonance 前 -> 整体档前 -> 窗口升序', () => {
    const rows = buildScorecardRows([
      entry({ signal: 'transmission', window_days: 120, baseline: 0.49 }),
      entry({ tier: 'high', window_days: 120 }),
      entry({ signal: 'transmission', window_days: 60, baseline: 0.49 }),
      entry({ window_days: 120 }),
      entry({ tier: 'high', window_days: 60 }),
      entry({}),
    ]);
    expect(rows.map((r) => [r.signal, r.tier, r.window])).toEqual([
      ['resonance', null, 60],
      ['resonance', null, 120],
      ['resonance', 'high', 60],
      ['resonance', 'high', 120],
      ['transmission', null, 60],
      ['transmission', null, 120],
    ]);
  });

  it('nullish 兼容: 缺省字段兜底 (窗口/n/status 有默认)', () => {
    const rows = buildScorecardRows([
      entry({ tier: undefined, window_days: undefined, n: undefined, status: undefined }),
    ]);
    expect(rows[0].tier).toBeNull();
    expect(rows[0].window).toBeNull();
    expect(rows[0].n).toBe(0);
    expect(rows[0].status).toBe('insufficient');
  });

  it('高置信档标签: tier=high 加中文后缀', () => {
    const rows = buildScorecardRows([entry({ tier: 'high' })]);
    expect(rows[0].label).toBe('共振信号 · 高置信档');
  });
});

describe('ScorecardPanel 渲染', () => {
  it('渲染三态徽章 + 胜率与 CI 文本', () => {
    render(
      <ScorecardPanel
        entries={[
          entry({ status: 'consistent', hit_rate: 0.55, ci_low: 0.46, ci_high: 0.64 }),
          entry({ status: 'degraded', hit_rate: 0.46, ci_low: 0.4, ci_high: 0.53, window_days: 120 }),
          entry({ status: 'insufficient', n: 30, hit_rate: 0.4, ci_low: 0.2, ci_high: 0.6, window_days: 120, tier: 'high' }),
        ]}
      />,
    );
    expect(screen.getByText('信号计分卡')).toBeInTheDocument();
    expect(screen.getByText('与长期一致')).toBeInTheDocument();
    expect(screen.getByText('近期降效')).toBeInTheDocument();
    expect(screen.getByText('样本不足')).toBeInTheDocument();
    // 胜率与 CI 分属 span, 用 textContent 整体匹配 (限 td 避免父级重复命中)
    expect(
      screen.getByText((_, el) => el?.tagName === 'TD' && el.textContent === '55.0% (46.0% ~ 64.0%)'),
    ).toBeInTheDocument();
    expect(screen.getByText('共振信号 · 高置信档')).toBeInTheDocument();
  });

  it('空数据显示占位', () => {
    render(<ScorecardPanel entries={[]} />);
    expect(screen.getByText('暂无信号计分卡数据')).toBeInTheDocument();
  });
});

describe('ScorecardPanel 渲染', () => {
  it('三种状态徽章各就各位 (绿/黄/灰)', () => {
    render(<ScorecardPanel entries={[
      entry({ status: 'consistent' }),
      entry({ tier: 'high', status: 'degraded', window_days: 120 }),
      entry({ signal: 'transmission', status: 'insufficient', n: 10, baseline: 0.49 }),
    ]} />);
    expect(screen.getByText('与长期一致')).toBeInTheDocument();
    expect(screen.getByText('近期降效')).toBeInTheDocument();
    expect(screen.getByText('样本不足')).toBeInTheDocument();
  });

  it('胜率与 95% CI 文本渲染', () => {
    render(<ScorecardPanel entries={[entry({ hit_rate: 0.465, ci_low: 0.397, ci_high: 0.532 })]} />);
    expect(screen.getByText('46.5%')).toBeInTheDocument();
    expect(screen.getByText(/39\.7% ~ 53\.2%/)).toBeInTheDocument();
  });

  it('空数据显示占位', () => {
    render(<ScorecardPanel entries={[]} />);
    expect(screen.getByText(/暂无/)).toBeInTheDocument();
  });
});
