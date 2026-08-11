import { FIELD_DICTIONARY } from '@/lib/field-dictionary';
import type { Direction, SignalType } from '@/types/signals';

const TITLE: Record<SignalType, string> = {
  resonance: '共振说明',
  transmission: '传导说明',
  divergence: '背离说明',
};

const DIRECTION_LABEL: Record<Direction, string> = {
  up: '偏多 ▲',
  down: '偏空 ▼',
};

type SignalNoteProps = {
  signal: SignalType | null;
  // 方向仅对 resonance 有统计意义 (5年回测次日A股同向≈56%, 基线48.6%)
  direction?: Direction | null;
};

export const SignalNote = ({ signal, direction }: SignalNoteProps) => {
  if (!signal) return null;
  const showDir = signal === 'resonance' && direction;
  return (
    <div className="bg-blue-50 border border-blue-200 rounded p-3 text-sm">
      <div className="font-medium mb-1">
        {TITLE[signal]}
        {showDir ? (
          <span className="ml-2 text-blue-700">{DIRECTION_LABEL[direction]}</span>
        ) : null}
      </div>
      <div className="text-gray-700">{FIELD_DICTIONARY[signal]}</div>
      {showDir ? (
        <div className="mt-1 text-xs text-gray-500">
          方向取美股动量; 5年回测次日 A 股同向概率约 56%（基线 49%），扣交易成本后期望有限，仅作方向倾向参考。
        </div>
      ) : null}
    </div>
  );
};
