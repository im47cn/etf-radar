import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { EventTimeline } from '../EventTimeline';
import type { UserEvent } from '@/lib/portfolio/eventTypes';

const themes = new Map<string, string>([['cn_tech', '科技'], ['cn_chem', '化工']]);

const mkEvent = (id: string, themeId: string, read = false): UserEvent => ({
  id, user_id: 'u1', event_type: 'theme_quadrant_change',
  theme_id: themeId, event_signature: `sig_${id}`,
  payload: { version: 1, from: 'weak', to: 'leading', etf_codes: ['510300'] },
  asof_date: '2026-06-23',
  created_at: '2026-06-23T01:00:00Z', read_at: read ? '2026-06-23T02:00:00Z' : null,
});

const markAllReadSpy = vi.fn().mockResolvedValue({ error: null });

describe('EventTimeline', () => {
  it('默认折叠（仅显示标题 + 未读数）', () => {
    render(<EventTimeline events={[mkEvent('e1', 'cn_tech')]} themeNames={themes}
      unreadCount={1} markAllRead={markAllReadSpy} />);
    expect(screen.getByText(/事件流/)).toBeInTheDocument();
    expect(screen.getByText(/未读 1/)).toBeInTheDocument();
    expect(screen.queryByTestId('event-root')).not.toBeInTheDocument();
  });

  it('展开后渲染事件列表', () => {
    render(<EventTimeline events={[mkEvent('e1', 'cn_tech')]} themeNames={themes}
      unreadCount={1} markAllRead={markAllReadSpy} />);
    fireEvent.click(screen.getByRole('button', { name: /事件流/ }));
    expect(screen.getByTestId('event-root')).toBeInTheDocument();
    expect(screen.getByText(/科技/)).toBeInTheDocument();
  });

  it('空事件展开后显示空态文案', () => {
    render(<EventTimeline events={[]} themeNames={themes}
      unreadCount={0} markAllRead={markAllReadSpy} />);
    fireEvent.click(screen.getByRole('button', { name: /事件流/ }));
    expect(screen.getByText(/暂无事件/)).toBeInTheDocument();
  });

  it('未知 themeId 不崩溃，使用 themeId 兜底', () => {
    render(<EventTimeline events={[mkEvent('e1', 'cn_unknown')]} themeNames={themes}
      unreadCount={1} markAllRead={markAllReadSpy} />);
    fireEvent.click(screen.getByRole('button', { name: /事件流/ }));
    expect(screen.getByText(/cn_unknown/)).toBeInTheDocument();
  });

  it('"全部标为已读"按钮调用 markAllRead', () => {
    render(<EventTimeline events={[mkEvent('e1', 'cn_tech')]} themeNames={themes}
      unreadCount={1} markAllRead={markAllReadSpy} />);
    fireEvent.click(screen.getByRole('button', { name: /事件流/ }));
    fireEvent.click(screen.getByRole('button', { name: /全部标为已读/ }));
    expect(markAllReadSpy).toHaveBeenCalled();
  });
});
