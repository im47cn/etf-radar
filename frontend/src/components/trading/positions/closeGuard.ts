import type { Trade } from '@/lib/trading/types';

/** 服务端 008 trigger 同口径：超 7 天的 close 事件删除被拒，前端同步禁用。 */
export const CLOSE_DELETE_WINDOW_DAYS = 7;

export const isCloseDeleteLocked = (t: Trade, today = new Date()): boolean => {
  if (t.side !== 'close') return false;
  const day = Date.UTC(today.getFullYear(), today.getMonth(), today.getDate());
  const [y, m, d] = t.trade_date.split('-').map(Number) as [number, number, number];
  const trade = Date.UTC(y, m - 1, d);
  return day - trade > CLOSE_DELETE_WINDOW_DAYS * 86_400_000;
};
