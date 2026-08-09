import { useMemo } from 'react';
import { useSignalEvidence } from '@/hooks/useSignalEvidence';
import { IcRollingChart } from '@/components/evidence/IcRollingChart';
import { IcHorizonBar } from '@/components/evidence/IcHorizonBar';
import { ArchRankingBar } from '@/components/evidence/ArchRankingBar';
import { R2AcfChart } from '@/components/evidence/R2AcfChart';
import { Skeleton } from '@/components/ui/skeleton';

/** 信号证据页: strength 月度 IC + 主题 ARCH 的 5 年样本外统计可视化 (非实时信号). */
export const EvidencePage = () => {
  const { data, error, isLoading } = useSignalEvidence();

  const themeNames = useMemo(() => {
    const m: Record<string, string> = {};
    for (const t of data?.arch?.themes ?? []) m[t.theme_id] = t.name ?? t.theme_id;
    return m;
  }, [data]);

  if (isLoading)
    return (
      <div className="flex flex-col gap-4 p-4" aria-busy="true" aria-label="加载中">
        <Skeleton className="h-20" />
        <Skeleton className="h-64" />
        <Skeleton className="h-48" />
      </div>
    );
  if (error || !data) return <div className="p-8 text-center text-gray-400">暂无信号证据数据</div>;

  const s = data.sample;

  return (
    <main className="flex flex-col gap-4 p-4 animate-crossfade">
      <div className="animate-fade-rise" style={{ animationDelay: '0ms' }}>
        <h1 className="text-lg font-semibold text-gray-800">信号证据</h1>
        <p className="mt-0.5 text-xs text-gray-500">
          strength 主题信号的统计有效性 · {s.start ?? '?'} ~ {s.end ?? '?'}（{s.n_days ?? 0} 个交易日）
        </p>
      </div>

      <div className="animate-fade-rise" style={{ animationDelay: '120ms' }}>
        <IcRollingChart rolling={data.ic.rolling} />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2 animate-fade-rise" style={{ animationDelay: '180ms' }}>
        <IcHorizonBar byHorizon={data.ic.by_horizon} />
        <ArchRankingBar themes={data.arch.themes} />
      </div>

      <div className="animate-fade-rise" style={{ animationDelay: '240ms' }}>
        <R2AcfChart acf={data.arch.representative_acf} themeNames={themeNames} />
      </div>

      <p className="animate-fade-rise text-xs text-gray-400" style={{ animationDelay: '300ms' }}>
        口径说明：IC = 横截面 spearman（cn_strength.composite 排名，未来 k 日收益排名）；ARCH = r² 的
        Ljung-Box 检验（McLeod-Li，波动率聚集）。本页为 5 年样本外统计证据（非实时交易信号），月度预计算。
      </p>
    </main>
  );
};
