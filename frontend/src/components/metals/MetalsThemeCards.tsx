import type { Theme } from '@/types/themes';
import { Progress } from '@/components/ui/progress';
import { formatPct } from '@/lib/format';
import { cn } from '@/lib/utils';

interface Props {
  themes: Theme[];
}

/** 贵金属组主题强度卡: 过滤 tags 含"贵金属", 复用既有双轨强度, 零新评分逻辑. */
export const MetalsThemeCards = ({ themes }: Props) => {
  const metals = themes.filter((t) => t.tags.includes('贵金属'));
  if (metals.length === 0) return null;
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
      {metals.map((t) => (
        <div key={t.id} className="rounded-lg border bg-white p-3">
          <div className="flex items-center justify-between">
            <span className="font-medium text-gray-800">{t.name}</span>
            <span className="text-xs text-gray-400">{t.primary_us ?? t.primary_cn ?? '—'}</span>
          </div>
          <div className="mt-2 space-y-1.5">
            {(['us_strength', 'cn_strength'] as const).map((dim) => {
              const s = t[dim];
              return (
                <div key={dim} className="flex items-center gap-2">
                  <span className="text-xs text-gray-500 w-7">{dim === 'us_strength' ? '美股' : 'A股'}</span>
                  {s == null ? (
                    <div className="h-2 flex-1 rounded bg-muted/40" aria-hidden />
                  ) : (
                    <>
                      <Progress value={s.composite} className="h-2 flex-1" />
                      <span className="text-xs tabular-nums text-gray-600 w-6 text-right">{s.composite}</span>
                    </>
                  )}
                </div>
              );
            })}
          </div>
          <div className="mt-2 flex gap-4 text-xs">
            {(['r_1d', 'r_20d', 'r_60d'] as const).map((k) => {
              const v = t.returns[k];
              return (
                <span key={k} className="text-gray-500">
                  {k === 'r_1d' ? '1日' : k === 'r_20d' ? '20日' : '60日'}
                  <span
                    className={cn('ml-1 tabular-nums', (v ?? 0) >= 0 ? 'text-blue-600' : 'text-red-600')}
                  >
                    {formatPct(v)}
                  </span>
                </span>
              );
            })}
          </div>
          {t.note && <p className="mt-2 text-xs text-gray-400">{t.note}</p>}
        </div>
      ))}
    </div>
  );
};
