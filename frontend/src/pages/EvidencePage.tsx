import { useMemo, useState, type ReactNode } from 'react';
import { useSignalEvidence } from '@/hooks/useSignalEvidence';
import { IcRollingChart } from '@/components/evidence/IcRollingChart';
import { IcHorizonBar } from '@/components/evidence/IcHorizonBar';
import { ArchRankingBar } from '@/components/evidence/ArchRankingBar';
import { R2AcfChart } from '@/components/evidence/R2AcfChart';
import { Modal } from '@/components/ui/Modal';
import { Skeleton } from '@/components/ui/skeleton';

const Section = ({ title, children }: { title: string; children: ReactNode }) => (
  <div className="space-y-1">
    <h3 className="text-sm font-semibold text-gray-700">{title}</h3>
    <div className="space-y-1 text-xs">{children}</div>
  </div>
);

/** 信号证据页: strength 月度 IC + 主题 ARCH 的 5 年样本外统计可视化 (非实时信号). */
export const EvidencePage = () => {
  const { data, error, isLoading } = useSignalEvidence();
  const [helpOpen, setHelpOpen] = useState(false);

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
      <div className="flex items-start justify-between gap-2 animate-fade-rise" style={{ animationDelay: '0ms' }}>
        <div>
          <h1 className="text-lg font-semibold text-gray-800">信号证据</h1>
          <p className="mt-0.5 text-xs text-gray-500">
            strength 主题信号的统计有效性 · {s.start ?? '?'} ~ {s.end ?? '?'}（{s.n_days ?? 0} 个交易日）
          </p>
        </div>
        <button
          type="button"
          onClick={() => setHelpOpen(true)}
          className="shrink-0 rounded border border-gray-200 bg-white px-2.5 py-1 text-xs text-gray-600 hover:bg-gray-50"
        >
          📖 使用说明
        </button>
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

      <Modal open={helpOpen} onClose={() => setHelpOpen(false)} title="信号证据 · 使用说明">
        <Section title="理论基础">
          <p>
            <strong>IC（信息系数）</strong>：横截面 Spearman 相关——某日主题强度排名 vs 未来 k 日收益排名的秩相关。
            IC &gt; 0 表示"强者续强"（强度有预测力）；IC ≈ 0 表示无预测力。本页 IC 来自 cn_strength.composite
            （多周期复合动量百分位）。
          </p>
          <p>
            <strong>ARCH（波动率聚集）</strong>：对收益率平方 r² 做 Ljung-Box 检验。显著 = r² 自相关 =
            高波动日后倾向延续高波动（波动率聚集），可用于波动率/风险建模。
          </p>
        </Section>

        <Section title="使用方法（4 图怎么读）">
          <p>① <strong>IC 滚动时序</strong>：看曲线是否持续 &gt; 0（alpha 稳定性）。红虚线 = 全期均值。</p>
          <p>② <strong>IC vs 持有期</strong>：柱随 horizon（1d→5d→20d）增大 = 慢变量趋势 alpha（月级强于日级）。</p>
          <p>③ <strong>ARCH 排序条形</strong>：红条 = r² 显著（波动率聚集）；越高越显著。点右上角 ? 看该图详情。</p>
          <p>④ <strong>r² ACF 衰减</strong>：强 ARCH 主题高位缓降，无 ARCH 主题迅速回 0。</p>
        </Section>

        <Section title="分析案例（5 年样本外实证）">
          <p>
            <strong>strength 月度 IC = 0.054（t=7.9）</strong>：真实但弱的 alpha。注意：123 日小样本曾高估到 0.144
            （AI 行情放大），5 年真实值约其 1/3——别用短样本 IC 做收益预期。
          </p>
          <p>
            <strong>87% 主题有 ARCH（26/30）</strong>：波动率聚集普遍，集中在高贝塔板块（半导体/医疗/黄金）。
            但日频收益方向白噪——唯一收益 alpha 在月级 strength 趋势，不在日频择时。
          </p>
        </Section>
      </Modal>
    </main>
  );
};
