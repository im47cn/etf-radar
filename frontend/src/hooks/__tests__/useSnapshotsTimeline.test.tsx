import { describe, it, expect, beforeAll, afterAll, afterEach, vi } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { SWRConfig } from 'swr';
import React from 'react';
import { server } from '@/mocks/server';
import { useSnapshotsTimeline } from '../useSnapshotsTimeline';
import { mkFrame } from '@/__fixtures__/snapshots';

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

// SWR 默认 shouldRetryOnError 会让 indexError 永远 pending; 测试里关掉
const Wrapper = ({ children }: { children: React.ReactNode }) => (
  <SWRConfig
    value={{
      provider: () => new Map(),
      dedupingInterval: 0,
      shouldRetryOnError: false,
    }}
  >
    {children}
  </SWRConfig>
);

// mkIndex(5) 在 GMT+8 时区生成 2026-01-01..2026-01-05 (toISOString 转 UTC 后切日期)
// 所以 latest = 2026-01-05, frame-error 测试用 2026-01-02 (有效日期)
describe('useSnapshotsTimeline', () => {
  it('initializes to latest date once index loads', async () => {
    const { result } = renderHook(() => useSnapshotsTimeline(), { wrapper: Wrapper });
    await waitFor(() => expect(result.current.status).toBe('ready'));
    expect(result.current.currentDate).toBe('2026-01-05');
    expect(result.current.frame?.date).toBe('2026-01-05');
  });

  it('transitions to index-error when index fetch fails', async () => {
    server.use(http.get('*/snapshots-index.json', () => HttpResponse.error()));
    const { result } = renderHook(() => useSnapshotsTimeline(), { wrapper: Wrapper });
    await waitFor(() => expect(result.current.status).toBe('index-error'));
  });

  it('keeps previous frame on frame-error (preserves frame field)', async () => {
    // 先注册一个目标日期的失败 handler, 这样启动 prefetch 时这帧就不会进 cache
    // 然后 setDate(目标日期) 会重新走 3-retry 路径并失败.
    // 用 fake timers 跳过 5s/10s/20s 退避以加速测试 (生产代码不变).
    server.use(
      http.get('*/snapshots/2026-01-02/themes.json', () => HttpResponse.error()),
    );
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const { result } = renderHook(() => useSnapshotsTimeline(), { wrapper: Wrapper });
    // 启动时 latest=2026-01-05 应该 ready (2026-01-02 prefetch 静默失败)
    await waitFor(() => expect(result.current.status).toBe('ready'));
    const initialFrame = result.current.frame;
    expect(initialFrame).toBeDefined();
    expect(initialFrame?.date).toBe('2026-01-05');

    // 推进启动 prefetch 中失败帧的 retry 退避 (5s + 10s = 15s), 等 inflight 释放
    await vi.advanceTimersByTimeAsync(60_000);

    act(() => result.current.setDate('2026-01-02'));
    // 再推进新一轮 setDate 的 retry 退避
    await vi.advanceTimersByTimeAsync(60_000);
    await waitFor(() => expect(result.current.status).toBe('frame-error'));
    expect(result.current.error).toBe('2026-01-02');
    expect(result.current.frame).toBe(initialFrame);
    vi.useRealTimers();
  }, 30_000);

  it('cache hit on repeated setDate (no extra fetch)', async () => {
    let frameFetches = 0;
    server.use(
      http.get('*/snapshots/:date/themes.json', ({ params }) => {
        frameFetches++;
        const date = params.date as string;
        return HttpResponse.json({
          schema_version: '1.0',
          generated_at: `${date}T00:00:00+08:00`,
          themes: mkFrame(date).themes,
        });
      }),
    );
    const { result } = renderHook(() => useSnapshotsTimeline(), { wrapper: Wrapper });
    await waitFor(() => expect(result.current.status).toBe('ready'));
    // 等待 startup prefetch 完成 (recent 10, 但 index 只有 5)
    await waitFor(() => expect(frameFetches).toBeGreaterThanOrEqual(5));
    const before = frameFetches;
    act(() => result.current.setDate('2026-01-05'));
    await waitFor(() => expect(result.current.frame?.date).toBe('2026-01-05'));
    expect(frameFetches).toBe(before);
  });

  it('prefetch loads requested dates into cache', async () => {
    let frameFetches: string[] = [];
    server.use(
      http.get('*/snapshots/:date/themes.json', ({ params }) => {
        const date = params.date as string;
        frameFetches.push(date);
        return HttpResponse.json({
          schema_version: '1.0',
          generated_at: `${date}T00:00:00+08:00`,
          themes: mkFrame(date).themes,
        });
      }),
    );
    const { result } = renderHook(() => useSnapshotsTimeline(), { wrapper: Wrapper });
    await waitFor(() => expect(result.current.status).toBe('ready'));
    // 启动 prefetch 已拉全部 5 帧 (≥5), 等其完成
    await waitFor(() => expect(frameFetches.length).toBeGreaterThanOrEqual(5));
    const before = frameFetches.length;
    act(() => result.current.prefetch(['2026-01-02', '2026-01-03']));
    // 已缓存 ⇒ prefetch 不再发请求, 验证缓存确实命中: setDate 同步切 frame
    act(() => result.current.setDate('2026-01-02'));
    await waitFor(() => expect(result.current.frame?.date).toBe('2026-01-02'));
    expect(frameFetches.length).toBe(before);
  });

  it('startup prefetches recent 10 frames (or all if fewer)', async () => {
    const prefetched: string[] = [];
    server.use(
      http.get('*/snapshots/:date/themes.json', ({ params }) => {
        const date = params.date as string;
        prefetched.push(date);
        return HttpResponse.json({
          schema_version: '1.0',
          generated_at: `${date}T00:00:00+08:00`,
          themes: mkFrame(date).themes,
        });
      }),
    );
    const { result } = renderHook(() => useSnapshotsTimeline(), { wrapper: Wrapper });
    await waitFor(() => expect(result.current.status).toBe('ready'));
    await waitFor(() => expect(prefetched.length).toBeGreaterThanOrEqual(5));
  });
});
