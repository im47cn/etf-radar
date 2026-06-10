import { FIELD_DICTIONARY } from '@/lib/field-dictionary';
import type { SignalType } from '@/types/signals';

const TITLE: Record<SignalType, string> = {
  resonance: '共振说明',
  transmission: '传导说明',
  divergence: '背离说明',
};

export const SignalNote = ({ signal }: { signal: SignalType | null }) => {
  if (!signal) return null;
  return (
    <div className="bg-blue-50 border border-blue-200 rounded p-3 text-sm">
      <div className="font-medium mb-1">{TITLE[signal]}</div>
      <div className="text-gray-700">{FIELD_DICTIONARY[signal]}</div>
    </div>
  );
};
