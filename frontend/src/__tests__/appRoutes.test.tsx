import { describe, expect, it, afterEach, vi } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import type { ReactNode } from 'react';

// App 级路由接线测试: providers 全部 passthrough / Header 置空,
// 页面组件替换为 marker stub —— 只验证 Route → 组件 / Navigate 重定向分支.
vi.mock('@/providers/DataProvider', () => ({
  DataProvider: ({ children }: { children?: ReactNode }) => <>{children}</>,
}));
vi.mock('@/providers/AuthProvider', () => ({
  AuthProvider: ({ children }: { children?: ReactNode }) => <>{children}</>,
}));
vi.mock('@/providers/HoldingsProvider', () => ({
  HoldingsProvider: ({ children }: { children?: ReactNode }) => <>{children}</>,
}));
vi.mock('@/providers/TradesProvider', () => ({
  TradesProvider: ({ children }: { children?: ReactNode }) => <>{children}</>,
}));
vi.mock('@/providers/EventsProvider', () => ({
  EventsProvider: ({ children }: { children?: ReactNode }) => <>{children}</>,
}));
vi.mock('@/components/Header', () => ({ Header: () => null }));

vi.mock('@/pages/TemperaturePage', () => ({ TemperaturePage: () => <div>temperature-page-marker</div> }));
vi.mock('@/pages/RotationPage', () => ({ RotationPage: () => <div>rotation-page-marker</div> }));
vi.mock('@/pages/RadarPage', () => ({ RadarPage: () => <div>radar-page-marker</div> }));
vi.mock('@/pages/EvidencePage', () => ({ EvidencePage: () => <div>evidence-page-marker</div> }));
vi.mock('@/pages/GridPage', () => ({ GridPage: () => <div>grid-page-marker</div> }));
vi.mock('@/pages/MetalsPage', () => ({ MetalsPage: () => <div>metals-page-marker</div> }));
vi.mock('@/pages/TradingPage', () => ({ TradingPage: () => <div>trading-page-marker</div> }));
vi.mock('@/pages/MembershipPage', () => ({ MembershipPage: () => <div>membership-page-marker</div> }));
vi.mock('@/pages/WatchlistPage', () => ({ WatchlistPage: () => <div>watchlist-page-marker</div> }));
vi.mock('@/pages/AuthCallback', () => ({ AuthCallback: () => <div>auth-callback-marker</div> }));
vi.mock('@/pages/StocksPage', () => ({ StocksPage: () => <div>stocks-page-marker</div> }));

import App from '@/App';

const renderAtHash = (hash: string) => {
  window.location.hash = hash;
  render(<App />);
};

afterEach(() => {
  cleanup();
  window.location.hash = '';
});

describe('App 路由 (HashRouter)', () => {
  it('#/portfolio 重定向到 #/trading?tab=holdings 并渲染 TradingPage', () => {
    renderAtHash('#/portfolio');
    expect(window.location.hash).toBe('#/trading?tab=holdings');
    expect(screen.getByText('trading-page-marker')).toBeInTheDocument();
  });

  it('#/watchlist 路由保留, 渲染 WatchlistPage', () => {
    renderAtHash('#/watchlist');
    expect(screen.getByText('watchlist-page-marker')).toBeInTheDocument();
  });

  it('#/ 根路径渲染 TemperaturePage', () => {
    renderAtHash('#/');
    expect(screen.getByText('temperature-page-marker')).toBeInTheDocument();
  });
});
