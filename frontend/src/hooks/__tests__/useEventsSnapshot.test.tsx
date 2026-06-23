import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { setupServer } from 'msw/node';
import { http, HttpResponse } from 'msw';
import { SWRConfig } from 'swr';
import type { ReactNode } from 'react';
import { useEventsSnapshot } from '../useEventsSnapshot';

const server = setupServer();

const wrap = ({ children }: { children: ReactNode }) => (
  <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0, shouldRetryOnError: false }}>
    {children}
  </SWRConfig>
);

// 完整 theme fixture（满足 ThemeSchema 所有必填字段）
const mkThemeFixture = (id: string, strength = { short: 80, mid: 80, long: 80, composite: 80 }) => ({
  id,
  name: id,
  us_etfs: [],
  primary_us: null,
  primary_cn: '515000',
  tags: [],
  note: '',
  returns: { r_1d: null, r_5d: null, r_20d: null, r_60d: null, r_120d: null, r_ytd: null },
  strength,
  us_strength: null,
  cn_strength: null,
  rank: { short: 1, mid: 1, long: 1, composite: 1 },
});

beforeEach(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => { server.resetHandlers(); server.close(); });

describe('useEventsSnapshot', () => {
  it('成功拉取一日 themes+signals 并组装 Snapshot', async () => {
    server.use(
      http.get('*/snapshots/2026-06-23/themes.json', () => HttpResponse.json({
        schema_version: '1',
        generated_at: 'x',
        themes: [mkThemeFixture('cn_tech')],
      })),
      http.get('*/snapshots/2026-06-23/signals.json', () => HttpResponse.json({
        theme_signals: [{ theme_id: 'cn_tech', signal: 'resonance' }],
      })),
    );

    const { result } = renderHook(() => useEventsSnapshot('2026-06-23'), { wrapper: wrap });
    await waitFor(() => expect(result.current.snapshot).toBeDefined());
    expect(result.current.snapshot!.date).toBe('2026-06-23');
    expect(result.current.snapshot!.themes.get('cn_tech')?.quadrant).toBe('leading');
    expect(result.current.snapshot!.themes.get('cn_tech')?.signal).toBe('resonance');
  });

  it('signals 缺失时仍组装快照，signal=null', async () => {
    server.use(
      http.get('*/snapshots/2026-06-23/themes.json', () => HttpResponse.json({
        schema_version: '1',
        generated_at: 'x',
        themes: [mkThemeFixture('cn_tech')],
      })),
      http.get('*/snapshots/2026-06-23/signals.json', () => HttpResponse.json(
        { theme_signals: [] },
      )),
    );
    const { result } = renderHook(() => useEventsSnapshot('2026-06-23'), { wrapper: wrap });
    await waitFor(() => expect(result.current.snapshot).toBeDefined());
    expect(result.current.snapshot!.themes.get('cn_tech')?.signal).toBeNull();
  });

  it('date 为 undefined 时不发请求', () => {
    const { result } = renderHook(() => useEventsSnapshot(undefined), { wrapper: wrap });
    expect(result.current.snapshot).toBeUndefined();
    expect(result.current.error).toBeUndefined();
  });
});
