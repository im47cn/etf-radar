// frontend/src/components/portfolio/EventTimeline.tsx
// 持仓事件流面板：默认折叠，展开显示事件列表（L1+L2 立场：仅"事件事实陈述"，无买卖指令）

import { useState } from 'react';
import type { UserEvent } from '@/lib/portfolio/eventTypes';
import { EventItem } from './EventItem';

interface Props {
  events:      UserEvent[];
  themeNames:  Map<string, string>;
  unreadCount: number;
  markAllRead: () => Promise<{ error: string | null }>;
}

/**
 * 持仓事件流（与 OpportunityScanner 同 pattern，默认折叠）。
 *   - 标题显示未读数，与 Header 红点联动
 *   - 未知 themeId 使用 themeId 原始值兜底，防止崩溃
 *   - 立场：仅"事件事实陈述"，无买卖指令
 */
export const EventTimeline = ({ events, themeNames, unreadCount, markAllRead }: Props) => {
  const [open, setOpen] = useState(false);

  return (
    <section className="mt-6 border rounded-lg bg-gray-50">
      {/* 折叠标题按钮 */}
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between px-4 py-3 text-left"
        aria-expanded={open}
      >
        <span className="font-medium">
          {/* 标题：事件流(总数, 未读 N) */}
          {`事件流(${events.length}${unreadCount > 0 ? `, 未读 ${unreadCount}` : ''})`}
        </span>
        <span className="text-xs text-gray-500">{open ? '收起 ▲' : '展开 ▼'}</span>
      </button>

      {/* 展开内容 */}
      {open && (
        <div className="px-2 pb-2">
          {events.length === 0 ? (
            /* 空态文案 */
            <div className="text-sm text-gray-500 text-center py-6">
              暂无事件——持仓主题在最近一个交易日未发生信号变化。
            </div>
          ) : (
            <>
              {/* 操作栏：全部标为已读 */}
              <div className="flex justify-end px-2 py-1">
                <button
                  type="button"
                  onClick={() => { void markAllRead(); }}
                  className="text-xs text-blue-600 hover:underline disabled:opacity-50"
                  disabled={unreadCount === 0}
                >全部标为已读</button>
              </div>
              {/* 事件列表 */}
              <div className="bg-white border rounded">
                {events.map(e => (
                  <EventItem
                    key={e.id}
                    event={e}
                    themeName={themeNames.get(e.theme_id) ?? e.theme_id}
                  />
                ))}
              </div>
            </>
          )}
        </div>
      )}
    </section>
  );
};
