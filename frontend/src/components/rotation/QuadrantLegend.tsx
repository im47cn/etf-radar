import { QUADRANT_COLORS, QUADRANT_LABELS } from '@/lib/rotation';
import type { Quadrant } from '@/types/rotation';
import {
  STROKE_WIDTH_LOW,
  STROKE_WIDTH_MID,
  STROKE_WIDTH_HIGH,
  MID_STROKE_COLOR,
  MID_STROKE_DASHARRAY_LOW,
} from '@/lib/midStroke';

const ROWS: { q: Quadrant; desc: string }[] = [
  { q: 'leading', desc: '长期&短期都强 — 趋势龙头, 续航空间需评估' },
  { q: 'rising',  desc: '长期弱但短期突涨 — 早期信号, 关注资金流入' },
  { q: 'fading',  desc: '长期强但短期跌 — 警惕高位回调' },
  { q: 'lagging', desc: '长期&短期都弱 — 暂观望' },
];

const MID_TIERS: { w: number; label: string; dash?: string }[] = [
  { w: STROKE_WIDTH_LOW,  label: '弱', dash: MID_STROKE_DASHARRAY_LOW },
  { w: STROKE_WIDTH_MID,  label: '中'  },
  { w: STROKE_WIDTH_HIGH, label: '强'  },
];

export const QuadrantLegend = () => (
  <div className="mt-4 space-y-3 text-xs">
    <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
      {ROWS.map(({ q, desc }) => (
        <div key={q} className="flex items-center gap-2">
          <span
            className="inline-block w-3 h-3 rounded-full shrink-0"
            style={{ backgroundColor: QUADRANT_COLORS[q] }}
            aria-hidden
          />
          <span className="font-medium">{QUADRANT_LABELS[q]}</span>
          <span className="text-gray-600">| {desc}</span>
        </div>
      ))}
    </div>
    <div className="flex items-center gap-3 pt-1 border-t border-gray-200">
      <span className="font-medium text-gray-700">中周期强度</span>
      <span className="text-gray-500">(气泡边框)</span>
      {MID_TIERS.map(({ w, label, dash }) => (
        <span key={w} className="flex items-center gap-1">
          <svg width="16" height="16" aria-hidden>
            <circle
              cx="8" cy="8" r="5"
              fill="#fff"
              stroke={MID_STROKE_COLOR}
              strokeWidth={w}
              strokeDasharray={dash}
            />
          </svg>
          <span className="text-gray-600">{label}</span>
        </span>
      ))}
    </div>
  </div>
);
