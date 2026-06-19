import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { StaleBanner } from '../StaleBanner';
import type { MetaFile } from '@/types/meta';

const mockMeta = vi.hoisted(() => ({ value: null as MetaFile | null }));

vi.mock('@/providers/dataContext', () => ({
  useDataContext: () => ({ meta: mockMeta.value ?? undefined, isLoading: false, error: null }),
}));

const buildMeta = (overrides: Partial<MetaFile> = {}): MetaFile => ({
  schema_version: '1.1',
  last_full_refresh: { us: '2026-06-19', cn: '2026-06-19' },
  last_intraday_refresh: null,
  providers: {
    us: { status: 'ok', name: 'yfinance' },
    cn: { status: 'ok', name: 'akshare-em' },
  },
  failed_symbols: [],
  fallback_symbols: {},
  stale_minutes: 0,
  calendar: {
    us_trading_today: true,
    cn_trading_today: true,
    us_session_active: false,
    cn_session_active: false,
  },
  ...overrides,
});

describe('StaleBanner', () => {
  beforeEach(() => {
    mockMeta.value = null;
  });

  it('renders nothing when meta is null', () => {
    const { container } = render(<StaleBanner />);
    expect(container.firstChild).toBeNull();
  });

  it('renders nothing for fully healthy state', () => {
    mockMeta.value = buildMeta();
    const { container } = render(<StaleBanner />);
    expect(container.firstChild).toBeNull();
  });

  it('shows stale message when stale_minutes > 60', () => {
    mockMeta.value = buildMeta({
      stale_minutes: 90,
      providers: {
        us: { status: 'ok', name: 'yfinance' },
        cn: { status: 'degraded', name: 'akshare-em' },
      },
      failed_symbols: ['512000'],
    });
    render(<StaleBanner />);
    expect(screen.getByText(/已过期 90 分钟/)).toBeInTheDocument();
  });

  it('shows fallback warning when only fallback_symbols present', () => {
    mockMeta.value = buildMeta({
      providers: {
        us: { status: 'ok', name: 'yfinance' },
        cn: { status: 'fallback', name: 'akshare-em' },
      },
      fallback_symbols: { '159755': 'akshare-sina', '588000': 'akshare-sina' },
    });
    render(<StaleBanner />);
    expect(screen.getByText(/2.*ETF.*备用数据源/)).toBeInTheDocument();
  });

  it('prioritizes degraded over fallback when both present', () => {
    mockMeta.value = buildMeta({
      providers: {
        us: { status: 'ok', name: 'yfinance' },
        cn: { status: 'degraded', name: 'akshare-em' },
      },
      failed_symbols: ['512000'],
      fallback_symbols: { '159755': 'akshare-sina' },
    });
    render(<StaleBanner />);
    expect(screen.getByText(/Provider 降级/)).toBeInTheDocument();
    expect(screen.queryByText(/使用备用数据源/)).not.toBeInTheDocument();
  });

  it('prioritizes stale over degraded and fallback', () => {
    mockMeta.value = buildMeta({
      stale_minutes: 120,
      providers: {
        us: { status: 'ok', name: 'yfinance' },
        cn: { status: 'degraded', name: 'akshare-em' },
      },
      failed_symbols: ['512000'],
      fallback_symbols: { '159755': 'akshare-sina' },
    });
    render(<StaleBanner />);
    expect(screen.getByText(/已过期/)).toBeInTheDocument();
    expect(screen.queryByText(/Provider 降级/)).not.toBeInTheDocument();
    expect(screen.queryByText(/备用数据源/)).not.toBeInTheDocument();
  });
});
