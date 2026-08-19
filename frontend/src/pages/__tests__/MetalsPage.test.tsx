import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { MetalsSchema } from '@/types/metals';
import { useSubscription } from '@/lib/subscription/useSubscription';
import { MetalsPage } from '@/pages/MetalsPage';

vi.mock('@/lib/subscription/useSubscription', () => ({ useSubscription: vi.fn() }));
vi.mock('@/hooks/useMetals', () => ({ useMetals: vi.fn() }));
vi.mock('@/providers/dataContext', () => ({ useDataContext: vi.fn() }));

const { useMetals } = await import('@/hooks/useMetals');
const { useDataContext } = await import('@/providers/dataContext');

const METALS = {
  schema_version: '1.0',
  generated_at: '2026-08-19T16:00:00+08:00',
  as_of: '2026-08-19',
  gold_silver_ratio: { value: 6.92, percentile_5y: 0.113, series: [['2026-01-02', 7.1], ['2026-08-19', 6.92]] },
  real_rate: { tip_price: 107.38, change_60d: 1.2, corr_gold_20d: 0.45 },
  dxy: { value: 98.87, r_20d: -0.0224, r_60d: -0.0045 },
  miner_leverage: { ratio: 0.236, percentile_1y: 0.992 },
  cn_side: {
    gold_etf: { code: '518880', name: '黄金ETF', price: 9.078, r_1d: 0.01, r_20d: 0.05, r_60d: 0.08, amount_yi: 20.5, premium_pct: null },
    silver_lof: { code: '161226', name: '白银LOF', price: 1.833, r_1d: -0.024, r_20d: -0.037, r_60d: -0.27, amount_yi: 2.28, premium_pct: null },
  },
  source_status: { gold_silver: 'ok', real_rate: 'ok', dxy: 'ok', miner_leverage: 'ok', cn_side: 'ok' },
};

const THEMES = {
  schema_version: '1.1',
  generated_at: 'x',
  themes: [
    { id: 'gold', name: '黄金', us_etfs: ['GLD', 'SLV'], primary_us: 'GLD', primary_cn: '518880',
      tags: ['黄金', '贵金属', '避险'], note: '', returns: { r_1d: 0.01, r_5d: 0.02, r_20d: 0.03, r_60d: 0.04, r_120d: 0.05, r_ytd: 0.1 },
      strength: { short: 50, mid: 50, long: 50, composite: 50 },
      us_strength: { short: 60, mid: 50, long: 40, composite: 50 },
      cn_strength: { short: 40, mid: 30, long: 20, composite: 30 },
      rank: { short: 1, mid: 1, long: 1, composite: 1 } },
    { id: 'silver', name: '白银', us_etfs: ['SLV'], primary_us: 'SLV', primary_cn: '161226',
      tags: ['白银', '贵金属'], note: 'A股端为白银LOF(161226), 场内流动性受限',
      returns: { r_1d: 0.03, r_5d: 0.01, r_20d: 0.09, r_60d: -0.13, r_120d: -0.3, r_ytd: -0.09 },
      strength: { short: 92, mid: 36, long: 15, composite: 39 },
      us_strength: { short: 92, mid: 36, long: 15, composite: 39 },
      cn_strength: { short: 24, mid: 5, long: 5, composite: 9 },
      rank: { short: 1, mid: 2, long: 5, composite: 3 } },
    { id: 'semi', name: '半导体', us_etfs: ['SOXX'], primary_us: 'SOXX', primary_cn: '512480',
      tags: ['半导体'], note: '', returns: { r_1d: 0, r_5d: 0, r_20d: 0, r_60d: 0, r_120d: 0, r_ytd: 0 },
      strength: { short: 10, mid: 10, long: 10, composite: 10 },
      us_strength: { short: 10, mid: 10, long: 10, composite: 10 },
      cn_strength: { short: 10, mid: 10, long: 10, composite: 10 },
      rank: { short: 2, mid: 2, long: 2, composite: 2 } },
  ],
};

describe('MetalsSchema 归一化', () => {
  it('完整产物解析', () => {
    const m = MetalsSchema.parse(METALS);
    expect(m.gold_silver_ratio.value).toBe(6.92);
    expect(m.source_status.dxy).toBe('ok');
  });

  it('缺省/降级字段 → null, series 缺省 → []', () => {
    const m = MetalsSchema.parse({
      ...METALS,
      gold_silver_ratio: { value: null, percentile_5y: null }, // series 缺省
      real_rate: { tip_price: null, change_60d: null, corr_gold_20d: null },
      dxy: { value: null, r_20d: null, r_60d: null },
      miner_leverage: { ratio: null, percentile_1y: null },
      cn_side: { gold_etf: undefined, silver_lof: null },
      as_of: null,
    });
    expect(m.gold_silver_ratio.value).toBeNull();
    expect(m.gold_silver_ratio.series).toEqual([]);
    expect(m.real_rate.corr_gold_20d).toBeNull();
    expect(m.cn_side.gold_etf).toBeNull();
    expect(m.as_of).toBeNull();
  });
});

describe('MetalsPage', () => {
  const setup = ({ member = true }: { member?: boolean } = {}) => {
    vi.mocked(useSubscription).mockReturnValue({ state: member ? 'member' : 'non-member' } as never);
    vi.mocked(useMetals).mockReturnValue({ data: METALS, error: undefined, isLoading: false } as never);
    vi.mocked(useDataContext).mockReturnValue({ themes: THEMES } as never);
    return render(
      <MemoryRouter>
        <MetalsPage />
      </MemoryRouter>,
    );
  };

  it('渲染宏观指标与贵金属主题卡(过滤非贵金属主题)', () => {
    setup();
    expect(screen.getByText('贵金属')).toBeInTheDocument();
    expect(screen.getByText('6.92')).toBeInTheDocument(); // 金银比
    expect(screen.getByText('黄金')).toBeInTheDocument();
    expect(screen.getByText('白银')).toBeInTheDocument();
    expect(screen.queryByText('半导体')).not.toBeInTheDocument(); // 非贵金属被过滤
    expect(screen.getAllByText(/161226/).length).toBeGreaterThanOrEqual(1); // A股端行情(行情行+主题卡)
    // LOF 警告条: SLV r60 -0.13 vs LOF r60 -0.27 → 偏离 14pp
    expect(screen.getByRole('status').textContent).toContain('14pp');
  });

  it('非会员: 分位与利率相关上锁', () => {
    setup({ member: false });
    expect(screen.getAllByText(/🔒/).length).toBeGreaterThanOrEqual(2);
  });

  it('会员: 显示分位百分数', () => {
    setup();
    expect(screen.getByText('11%')).toBeInTheDocument(); // 0.113 → 11%
  });

  it('会员: 分位色阶覆盖 amber/red 档', () => {
    for (const p of [0.65, 0.9]) {
      vi.mocked(useSubscription).mockReturnValue({ state: 'member' } as never);
      vi.mocked(useMetals).mockReturnValue({
        data: { ...METALS, gold_silver_ratio: { ...METALS.gold_silver_ratio, percentile_5y: p } },
        error: undefined,
        isLoading: false,
      } as never);
      vi.mocked(useDataContext).mockReturnValue({ themes: THEMES } as never);
      const { unmount } = render(
        <MemoryRouter>
          <MetalsPage />
        </MemoryRouter>,
      );
      expect(screen.getByText(`${Math.round(p * 100)}%`)).toBeInTheDocument();
      unmount();
    }
  });

  it('数据缺失时降级提示', () => {
    vi.mocked(useSubscription).mockReturnValue({ state: 'member' } as never);
    vi.mocked(useMetals).mockReturnValue({ data: undefined, error: new Error('x'), isLoading: false } as never);
    vi.mocked(useDataContext).mockReturnValue({ themes: undefined } as never);
    render(
      <MemoryRouter>
        <MetalsPage />
      </MemoryRouter>,
    );
    expect(screen.getByText('暂无贵金属数据')).toBeInTheDocument();
  });

  it('加载中显示骨架', () => {
    vi.mocked(useSubscription).mockReturnValue({ state: 'member' } as never);
    vi.mocked(useMetals).mockReturnValue({ data: undefined, error: undefined, isLoading: true } as never);
    vi.mocked(useDataContext).mockReturnValue({ themes: undefined } as never);
    render(
      <MemoryRouter>
        <MetalsPage />
      </MemoryRouter>,
    );
    expect(screen.getByLabelText('加载中')).toBeInTheDocument();
  });

  it('组件降级: 全 missing + null 值渲染占位而非崩溃', () => {
    vi.mocked(useSubscription).mockReturnValue({ state: 'member' } as never);
    vi.mocked(useMetals).mockReturnValue({
      data: {
        ...METALS,
        as_of: null,
        gold_silver_ratio: { value: null, percentile_5y: null, series: [] },
        real_rate: { tip_price: null, change_60d: null, corr_gold_20d: null },
        dxy: { value: null, r_20d: null, r_60d: null },
        miner_leverage: { ratio: null, percentile_1y: null },
        source_status: { gold_silver: 'missing', real_rate: 'missing', dxy: 'missing', miner_leverage: 'missing', cn_side: 'missing' },
      },
      error: undefined,
      isLoading: false,
    } as never);
    vi.mocked(useDataContext).mockReturnValue({
      themes: {
        ...THEMES,
        themes: [
          // 历史 snapshot 形态: us_strength/cn_strength 缺省 → null, note 空
          { ...THEMES.themes[0], us_strength: undefined, cn_strength: undefined, note: '' },
        ],
      },
    } as never);
    render(
      <MemoryRouter>
        <MetalsPage />
      </MemoryRouter>,
    );
    expect(screen.getAllByText('数据源不可用').length).toBe(4);
    expect(screen.getAllByText('—').length).toBeGreaterThanOrEqual(4); // null 值占位
    expect(screen.getByText(/截至/).textContent).toContain('—'); // as_of null → 占位
  });

  it('无贵金属主题时主题区不渲染卡片', () => {
    vi.mocked(useSubscription).mockReturnValue({ state: 'member' } as never);
    vi.mocked(useMetals).mockReturnValue({ data: METALS, error: undefined, isLoading: false } as never);
    vi.mocked(useDataContext).mockReturnValue({
      themes: { ...THEMES, themes: [THEMES.themes[2]] }, // 仅半导体
    } as never);
    render(
      <MemoryRouter>
        <MetalsPage />
      </MemoryRouter>,
    );
    expect(screen.queryByText('黄金')).not.toBeInTheDocument();
    expect(screen.queryByText('白银')).not.toBeInTheDocument();
  });

  it('null 边界: cn_side 半缺 + 行情字段 null + cn-only 主题', () => {
    vi.mocked(useSubscription).mockReturnValue({ state: 'member' } as never);
    vi.mocked(useMetals).mockReturnValue({
      data: {
        ...METALS,
        real_rate: { tip_price: 107.0, change_60d: -0.5, corr_gold_20d: null },
        cn_side: {
          gold_etf: { code: '518880', name: null, price: null, r_1d: null, amount_yi: null, premium_pct: null },
          silver_lof: null, // A股端半缺 → 行情行只剩黄金
        },
      },
      error: undefined,
      isLoading: false,
    } as never);
    // primary_us/primary_cn 均 null 的贵金属主题 (cn-only 历史形态) + 空 note + returns null
    vi.mocked(useDataContext).mockReturnValue({
      themes: {
        ...THEMES,
        themes: [{
          ...THEMES.themes[0], primary_us: null, primary_cn: null, note: '',
          returns: { r_1d: null, r_5d: null, r_20d: null, r_60d: null, r_120d: null, r_ytd: null },
        }],
      },
    } as never);
    render(
      <MemoryRouter>
        <MetalsPage />
      </MemoryRouter>,
    );
    expect(screen.getByText('黄金 ETF · 518880')).toBeInTheDocument(); // name null → 用 code
    expect(screen.queryByText(/白银 LOF/)).not.toBeInTheDocument();
  });
});
