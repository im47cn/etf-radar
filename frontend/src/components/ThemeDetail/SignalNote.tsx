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

// 幅度置信档标签 (样本外验证 2024-26 段): high=|美股动量|≥1% 同向 57% / low=<0.3% ≈随机
const TIER_LABEL: Record<'high' | 'low', string> = {
  high: '高置信',
  low: '弱信号',
};

type SignalNoteProps = {
  signal: SignalType | null;
  // 方向仅对 resonance 有统计意义 (5年回测同向≈55-57%, 基线48.6%)
  direction?: Direction | null;
  directionTier?: 'high' | 'low' | null;
};

export const SignalNote = ({ signal, direction, directionTier }: SignalNoteProps) => {
  if (!signal) return null;
  const showDir = signal === 'resonance' && direction;
  return (
    <div className="bg-blue-50 border border-blue-200 rounded p-3 text-sm">
      <div className="font-medium mb-1">
        {TITLE[signal]}
        {showDir ? (
          <span className={directionTier === 'low' ? 'ml-2 text-gray-400' : 'ml-2 text-blue-700'}>
            {DIRECTION_LABEL[direction]}
            {directionTier ? `（${TIER_LABEL[directionTier]}）` : ''}
          </span>
        ) : null}
      </div>
      <div className="text-gray-700">{FIELD_DICTIONARY[signal]}</div>
      {showDir ? (
        <div className="mt-1 text-xs text-gray-500">
          {directionTier === 'high'
            ? '方向取美股动量；样本外验证 |动量|≥1% 时数日内 A 股同向概率约 57%（基线 49%）。'
            : directionTier === 'low'
              ? '方向取美股动量；样本外验证 |动量|<0.3% 时同向概率≈48%（≈随机），信号弱，仅供参考。'
              : '方向取美股动量；样本外验证数日内 A 股同向概率约 55%（基线 49%）。'}
          扣交易成本后期望有限，仅作数日方向倾向参考，非交易信号。
        </div>
      ) : null}
      {signal === 'transmission' ? (
        <div className="mt-1 text-xs text-gray-500">
          5年回测传导状态次日 A 股跟随率约 49%（≈随机），无方向预测力，仅作状态观察。
        </div>
      ) : null}
    </div>
  );
};
