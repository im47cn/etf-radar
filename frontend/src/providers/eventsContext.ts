import { createContext } from 'react';
import type { UserEvent, PendingEvent } from '@/lib/portfolio/eventTypes';

export interface UseEventsResult {
  events:    UserEvent[];
  unreadCount: number;
  loading:   boolean;
  error:     string | null;
  /** 批量插入；UNIQUE 约束自动 dedupe（ON CONFLICT DO NOTHING） */
  upsertEvents: (events: PendingEvent[]) => Promise<{ inserted: number; error: string | null }>;
  markRead:  (eventIds: string[]) => Promise<{ error: string | null }>;
  markAllRead: () => Promise<{ error: string | null }>;
}

export const defaultEventsResult: UseEventsResult = {
  events: [],
  unreadCount: 0,
  loading: false,
  error: null,
  upsertEvents: async () => ({ inserted: 0, error: 'EventsProvider 未挂载' }),
  markRead: async () => ({ error: 'EventsProvider 未挂载' }),
  markAllRead: async () => ({ error: 'EventsProvider 未挂载' }),
};

export const EventsContext = createContext<UseEventsResult>(defaultEventsResult);
