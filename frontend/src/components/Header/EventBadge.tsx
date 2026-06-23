import { Link } from 'react-router-dom';
import { useUserEvents } from '@/hooks/useUserEvents';

/**
 * Header 红点徽章（spec §5.5 验收）：
 *   - unread === 0 时不渲染（无干扰）
 *   - 点击跳 /portfolio
 */
export const EventBadge = () => {
  const { unreadCount } = useUserEvents();
  if (unreadCount === 0) return null;
  const text = unreadCount > 99 ? '99+' : String(unreadCount);
  return (
    <Link
      to="/portfolio"
      aria-label={`您有 ${unreadCount} 条未读事件`}
      className="inline-flex items-center justify-center min-w-5 h-5 px-1 rounded-full bg-red-500 text-white text-xs font-medium"
      data-testid="event-badge"
    >{text}</Link>
  );
};
