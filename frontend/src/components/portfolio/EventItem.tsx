// frontend/src/components/portfolio/EventItem.tsx
// 单个事件 chip 组件：展示事件事实描述（L1+L2 立场：仅"信号事实形容词"，无买卖指令）

import type { UserEvent } from '@/lib/portfolio/eventTypes';
import type { Quadrant, SignalKind } from '@/lib/portfolio/types';
import { formatAffectedEtfs } from '@/lib/portfolio/eventDisplay';

interface Props {
  event:     UserEvent;
  themeName: string;
  /**
   * 当前持仓 ETF 代码集合（O(1) 查询）。
   * 提供则渲染副标题"影响你持仓的 SOXX"/"曾涉及你持仓的 SOXX（已卖出）"；
   * 不提供则不显示副标题（向后兼容旧调用方）。
   */
  currentHoldings?: Set<string>;
}

type Tone = 'green' | 'red' | 'gray';

/**
 * 事件颜色判定（L1+L2 立场：仅"信号事实形容词"，无指令）：
 *   - 绿：进入更强状态（leading / 上穿 / resonance）
 *   - 红：进入更弱状态（weak / 下穿 / divergence）
 *   - 灰：中性切换（无明显方向）
 */
function tone(event: UserEvent): Tone {
  switch (event.event_type) {
    case 'theme_quadrant_change': {
      // payload 自动收窄为 QuadrantChangePayload，无需 as 强转
      const to = event.payload.to;
      if (to === 'leading') return 'green';
      if (to === 'weak')    return 'red';
      return 'gray';
    }
    case 'theme_strength_cross_up':   return 'green';
    case 'theme_strength_cross_down': return 'red';
    case 'theme_signal_change': {
      // payload 自动收窄为 SignalChangePayload，无需 as 强转
      const to = event.payload.to;
      if (to === 'resonance')  return 'green';
      if (to === 'divergence') return 'red';
      return 'gray';
    }
  }
}

/** 象限中文标签 */
const QUADRANT_LABEL: Record<Quadrant, string> = {
  leading:   '领涨',
  weakening: '退潮',
  following: '跟随',
  weak:      '弱势',
};

/** 信号中文标签 */
const SIGNAL_LABEL: Record<SignalKind, string> = {
  resonance:    '共振',
  transmission: '传导',
  divergence:   '背离',
};

/** 生成事件文案（不含买卖指令） */
function label(event: UserEvent, themeName: string): string {
  switch (event.event_type) {
    case 'theme_quadrant_change':
      return `${themeName} 象限：${QUADRANT_LABEL[event.payload.from]} → ${QUADRANT_LABEL[event.payload.to]}`;
    case 'theme_strength_cross_up':
      if (event.payload.threshold === 75) return `${themeName} 强度上穿 75（进入强势区）`;
      if (event.payload.threshold === 50) return `${themeName} 强度上穿 50`;
      return `${themeName} 强度上穿 25`;
    case 'theme_strength_cross_down':
      if (event.payload.threshold === 25) return `${themeName} 强度下穿 25（进入弱势区）`;
      if (event.payload.threshold === 50) return `${themeName} 强度下穿 50`;
      return `${themeName} 强度下穿 75`;
    case 'theme_signal_change':
      return `${themeName} 信号：${SIGNAL_LABEL[event.payload.from]} → ${SIGNAL_LABEL[event.payload.to]}`;
  }
}

/** 色调对应左侧指示条颜色 */
const TONE_BAR: Record<Tone, string> = {
  green: 'bg-green-500',
  red:   'bg-red-500',
  gray:  'bg-gray-400',
};

export const EventItem = ({ event, themeName, currentHoldings }: Props) => {
  const t = tone(event);
  const isRead = event.read_at !== null;
  // 仅在传入 currentHoldings 时计算交集副标题，未传入则不显示
  const affected = currentHoldings ? formatAffectedEtfs(event, currentHoldings) : null;

  return (
    <div
      data-testid="event-root"
      className={`flex items-start gap-2 py-2 px-3 border-b last:border-b-0 ${isRead ? 'bg-gray-50 opacity-70' : 'bg-white'}`}
    >
      {/* 左侧颜色指示条 */}
      <span
        data-testid="event-color"
        data-color={t}
        className={`w-1 self-stretch rounded ${TONE_BAR[t]}`}
      />
      <div className="flex-1">
        {/* 事件文案（仅描述信号事实） */}
        <div className={`text-sm ${isRead ? 'text-gray-500' : 'text-gray-800'}`}>
          {label(event, themeName)}
        </div>
        {/* 持仓影响副标题（条件渲染：传 currentHoldings 且事件有 etf_codes 才显示） */}
        {affected && (
          <div data-testid="event-affected" className={`text-xs mt-0.5 ${isRead ? 'text-gray-400' : 'text-blue-600'}`}>
            {affected}
          </div>
        )}
        {/* 日期 */}
        <div className="text-xs text-gray-400 mt-0.5">{event.asof_date}</div>
      </div>
    </div>
  );
};
