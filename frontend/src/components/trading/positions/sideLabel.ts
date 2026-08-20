// 交易事件 side 枚举 → 中文标签（positions/ 目录共享；事件分类是记账口径，非指令）
import type { TradeSide } from '@/lib/trading/types';

export const TRADE_SIDES: TradeSide[] = ['open', 'add', 'reduce', 'close'];

export const TRADE_SIDE_LABEL: Record<TradeSide, string> = {
  open: '开仓',
  add: '加仓',
  reduce: '减仓',
  close: '清仓',
};
