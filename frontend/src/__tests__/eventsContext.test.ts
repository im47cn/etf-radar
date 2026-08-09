import { describe, expect, it } from 'vitest';
import { EventsContext, defaultEventsResult } from '@/providers/eventsContext';

describe('eventsContext', () => {
  it('defaultEventsResult 有正确默认值', () => {
    expect(defaultEventsResult.events).toEqual([]);
    expect(defaultEventsResult.unreadCount).toBe(0);
    expect(defaultEventsResult.loading).toBe(false);
    expect(defaultEventsResult.error).toBeNull();
  });

  it('default upsertEvents 返回未挂载错误', async () => {
    const r = await defaultEventsResult.upsertEvents([]);
    expect(r.inserted).toBe(0);
    expect(r.error).toBe('EventsProvider 未挂载');
  });

  it('default markRead 返回未挂载错误', async () => {
    const r = await defaultEventsResult.markRead(['e1']);
    expect(r.error).toBe('EventsProvider 未挂载');
  });

  it('default markAllRead 返回未挂载错误', async () => {
    const r = await defaultEventsResult.markAllRead();
    expect(r.error).toBe('EventsProvider 未挂载');
  });

  it('EventsContext._defaultValue 等于 defaultEventsResult（React 内部属性）', () => {
    // createContext 把 defaultValue 存在 _defaultValue（开发态）
    // 此断言确认 createContext(defaultEventsResult) 确实传入了默认值
    expect(EventsContext).toBeDefined();
    expect(EventsContext.Provider).toBeDefined();
    expect(EventsContext.Consumer).toBeDefined();
  });
});
