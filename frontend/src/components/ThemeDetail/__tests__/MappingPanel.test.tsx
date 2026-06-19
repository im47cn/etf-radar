import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MappingPanel } from '../MappingPanel';
import type { Theme } from '@/types/themes';

const mkTheme = (overrides: Partial<Theme> = {}): Theme => ({
  id: 'm',
  name: '半导体',
  us_etfs: ['SOXX'],
  primary_us: 'SOXX',
  primary_cn: null,
  tags: [],
  note: '',
  returns: {
    r_1d: null,
    r_5d: null,
    r_20d: null,
    r_60d: null,
    r_120d: null,
    r_ytd: null,
  },
  strength: { short: 50, mid: 50, long: 50, composite: 50 },
  us_strength: { short: 50, mid: 50, long: 50, composite: 50 },
  cn_strength: { short: 50, mid: 50, long: 50, composite: 50 },
  rank: { short: 1, mid: 1, long: 1, composite: 1 },
  ...overrides,
});

describe('MappingPanel cn-only fallback', () => {
  it('renders fallback message for cn-only theme', () => {
    render(
      <MappingPanel
        theme={mkTheme({
          id: 'cn_x',
          name: '白酒',
          us_etfs: [],
          primary_us: null,
          primary_cn: '512690',
          us_strength: null,
        })}
        confidence={null}
      />
    );
    expect(screen.getByText(/A 股本土赛道/)).toBeInTheDocument();
    expect(screen.getByText(/不展示映射相关字段/)).toBeInTheDocument();
  });

  it('does NOT render fallback for mapped theme', () => {
    render(<MappingPanel theme={mkTheme()} confidence={80} />);
    expect(screen.queryByText(/A 股本土赛道/)).toBeNull();
  });
});
