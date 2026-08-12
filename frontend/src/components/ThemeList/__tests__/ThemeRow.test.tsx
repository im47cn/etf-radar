import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ThemeRow } from '../ThemeRow';
import type { Theme } from '@/types/themes';
import type { MarketView } from '@/lib/marketView';

const mkTheme = (overrides: Partial<Theme> = {}): Theme => ({
  id: 'm',
  name: '半导体',
  us_etfs: ['SOXX'],
  primary_us: 'SOXX',
  primary_cn: null,
  tags: [],
  note: '',
  returns: { r_1d: null, r_5d: null, r_20d: null, r_60d: null, r_120d: null, r_ytd: null },
  strength: { short: 50, mid: 50, long: 50, composite: 50 },
  us_strength: { short: 50, mid: 50, long: 50, composite: 50 },
  cn_strength: { short: 50, mid: 50, long: 50, composite: 50 },
  rank: { short: 1, mid: 1, long: 1, composite: 1 },
  ...overrides,
});

interface RenderRowOpts {
  theme: Theme;
  marketView?: MarketView;
}

const renderRow = ({ theme, marketView = 'us' }: RenderRowOpts) =>
  render(
    <ThemeRow
      index={0}
      theme={theme}
      signal={undefined}
      dimension="composite"
      marketView={marketView}
      selected={false}
      onClick={() => {}}
    />,
    {
      wrapper: ({ children }) => (
        <table>
          <tbody>{children}</tbody>
        </table>
      ),
    },
  );

describe('ThemeRow cn-only flag', () => {
  it('does NOT render flag for mapped theme', () => {
    renderRow({ theme: mkTheme() });
    expect(screen.queryByText('🇨🇳')).toBeNull();
  });

  it('renders flag for cn-only theme', () => {
    renderRow({
      theme: mkTheme({
        id: 'cn_x',
        name: '白酒',
        us_etfs: [],
        primary_us: null,
        primary_cn: '512690',
        us_strength: null,
      }),
    });
    expect(screen.getByText('🇨🇳')).toBeInTheDocument();
  });
});

describe('ThemeRow market-view-aware primary ETF', () => {
  it('cn-all view shows primary_cn for cn-only theme', () => {
    renderRow({
      theme: mkTheme({
        id: 'cn_csi300',
        name: '沪深300',
        us_etfs: [],
        primary_us: null,
        primary_cn: '510300',
        us_strength: null,
      }),
      marketView: 'cn-all',
    });
    expect(screen.getByText('510300')).toBeInTheDocument();
  });
});

describe('ThemeRow — signalVariant 分支', () => {
  it('signal=divergence → destructive Badge', () => {
    render(
      <table><tbody>
        <ThemeRow
          index={0}
          theme={mkTheme()}
          signal={{ theme_id: 'm', signal: 'divergence', direction: null, eta_days: null, note: null } as never}
          dimension="composite"
          marketView="us"
          selected={false}
          onClick={() => {}}
        />
      </tbody></table>,
    );
    expect(screen.getByText('背离')).toBeInTheDocument();
  });

  it('signal=transmission → secondary Badge', () => {
    render(
      <table><tbody>
        <ThemeRow
          index={0}
          theme={mkTheme()}
          signal={{ theme_id: 'm', signal: 'transmission', direction: null, eta_days: null, note: null } as never}
          dimension="composite"
          marketView="us"
          selected={false}
          onClick={() => {}}
        />
      </tbody></table>,
    );
    expect(screen.getByText('传导')).toBeInTheDocument();
  });

  it('signal=resonance → default Badge', () => {
    render(
      <table><tbody>
        <ThemeRow
          index={0}
          theme={mkTheme()}
          signal={{ theme_id: 'm', signal: 'resonance', direction: null, eta_days: null, note: null } as never}
          dimension="composite"
          marketView="us"
          selected={false}
          onClick={() => {}}
        />
      </tbody></table>,
    );
    expect(screen.getByText('共振')).toBeInTheDocument();
  });
});

describe('ThemeRow — 副标题 (P2 量化)', () => {
  it('signal 有 description 时副标题展示量化描述', () => {
    render(
      <table><tbody>
        <ThemeRow
          index={0}
          theme={mkTheme()}
          signal={{ theme_id: 'm', signal: 'resonance', direction: 'up', description: '美股半导体 composite 88 中长期走强, 共振偏多' } as never}
          dimension="composite"
          marketView="us"
          selected={false}
          onClick={() => {}}
        />
      </tbody></table>,
    );
    expect(screen.getByText(/composite 88 中长期走强/)).toBeInTheDocument();
  });
});

describe('ThemeRow — 排名与持仓标记', () => {
  it('index >= 3 用灰色圆形（非 top3）', () => {
    render(
      <table><tbody>
        <ThemeRow
          index={5}
          theme={mkTheme()}
          signal={undefined}
          dimension="composite"
          marketView="us"
          selected={false}
          onClick={() => {}}
        />
      </tbody></table>,
    );
    // 序号 06
    expect(screen.getByText('06')).toBeInTheDocument();
  });

  it('owned=true 显示 ⭐', () => {
    render(
      <table><tbody>
        <ThemeRow
          index={0}
          theme={mkTheme()}
          signal={undefined}
          dimension="composite"
          marketView="us"
          selected={false}
          onClick={() => {}}
          owned
        />
      </tbody></table>,
    );
    expect(screen.getByTitle('持仓中')).toBeInTheDocument();
  });

  it('selected=true 有选中样式', () => {
    render(
      <table><tbody>
        <ThemeRow
          index={0}
          theme={mkTheme()}
          signal={undefined}
          dimension="composite"
          marketView="us"
          selected
          onClick={() => {}}
        />
      </tbody></table>,
    );
    // selected → border-blue-600
    const row = document.querySelector('tr');
    expect(row?.className).toContain('border-blue-600');
  });

  it('strength=null 渲染占位条', () => {
    render(
      <table><tbody>
        <ThemeRow
          index={0}
          theme={mkTheme({ us_strength: null })}
          signal={undefined}
          dimension="composite"
          marketView="us"
          selected={false}
          onClick={() => {}}
        />
      </tbody></table>,
    );
    // strength null → aria-hidden 占位
    expect(document.querySelector('[aria-hidden]')).toBeTruthy();
  });

  it('primary_cn=null 且 us 视图 → 渲染 —', () => {
    renderRow({
      theme: mkTheme({ primary_cn: null }),
      marketView: 'us',
    });
    expect(screen.getAllByText('—').length).toBeGreaterThanOrEqual(1);
  });
});
