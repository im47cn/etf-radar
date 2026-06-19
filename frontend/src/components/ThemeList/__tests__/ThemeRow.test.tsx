import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ThemeRow } from '../ThemeRow';
import type { Theme } from '@/types/themes';

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

const renderRow = (theme: Theme) =>
  render(
    <ThemeRow
      index={0}
      theme={theme}
      signal={undefined}
      dimension="composite"
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

describe('ThemeRow A 股专属 pill', () => {
  it('does NOT render pill for mapped theme', () => {
    renderRow(mkTheme());
    expect(screen.queryByText('A股专属')).toBeNull();
  });

  it('renders pill for cn-only theme', () => {
    renderRow(
      mkTheme({
        id: 'cn_x',
        name: '白酒',
        us_etfs: [],
        primary_us: null,
        primary_cn: '512690',
        us_strength: null,
      }),
    );
    expect(screen.getByText('A股专属')).toBeInTheDocument();
  });
});
