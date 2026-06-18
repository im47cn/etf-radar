import { useDataContext } from '@/providers/dataContext';
import { formatRelativeTime } from '@/lib/format';

export const UpdateBadge = () => {
  const { meta } = useDataContext();
  if (!meta) return null;
  const last =
    meta.last_intraday_refresh ||
    meta.last_full_refresh.cn ||
    meta.last_full_refresh.us;
  const active = meta.calendar.cn_session_active ? '盘中刷新中' : '收盘';
  return (
    <div className="text-xs text-gray-500">
      更新 {formatRelativeTime(last)} · {active}
    </div>
  );
};
