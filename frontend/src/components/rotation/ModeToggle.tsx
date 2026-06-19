import type { RotationMode } from '@/lib/rotation';
import { cn } from '@/lib/utils';

interface Props {
  mode: RotationMode;
  onChange: (m: RotationMode) => void;
  usCount: number;
  cnCount: number;
}

export function ModeToggle({ mode, onChange, usCount, cnCount }: Props) {
  const btn = (m: RotationMode, label: string, count: number) => (
    <button
      key={m}
      type="button"
      aria-pressed={mode === m}
      onClick={() => onChange(m)}
      className={cn(
        'px-3 py-1 text-sm rounded border transition',
        mode === m
          ? 'bg-slate-900 text-white border-slate-900'
          : 'bg-white text-slate-700 border-slate-300 hover:bg-slate-50',
      )}
    >
      {label} <span className="ml-1 opacity-70">{count}</span>
    </button>
  );
  return (
    <div className="inline-flex gap-1" role="group" aria-label="散点图强度模式">
      {btn('us', '美股强度', usCount)}
      {btn('cn', 'A股强度', cnCount)}
    </div>
  );
}
