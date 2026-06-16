import { QUADRANT_COLORS, QUADRANT_LABELS } from '@/lib/rotation';
import type { Quadrant } from '@/types/rotation';

const ROWS: { q: Quadrant; desc: string }[] = [
  { q: 'leading', desc: '长期&短期都强 — 趋势龙头, 续航空间需评估' },
  { q: 'rising',  desc: '长期弱但短期突涨 — 早期信号, 关注资金流入' },
  { q: 'fading',  desc: '长期强但短期跌 — 警惕高位回调' },
  { q: 'lagging', desc: '长期&短期都弱 — 暂观望' },
];

export const QuadrantLegend = () => (
  <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-xs mt-4">
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
);
