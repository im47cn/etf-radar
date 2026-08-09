import { useMemo, useState, type ReactNode } from 'react';
import { useSignalEvidence } from '@/hooks/useSignalEvidence';
import { IcRollingChart } from '@/components/evidence/IcRollingChart';
import { IcHorizonBar } from '@/components/evidence/IcHorizonBar';
import { ArchRankingBar } from '@/components/evidence/ArchRankingBar';
import { R2AcfChart } from '@/components/evidence/R2AcfChart';
import { Modal } from '@/components/ui/Modal';
import { Skeleton } from '@/components/ui/skeleton';
import { AuthGate } from '@/components/portfolio/AuthGate';
import { MemberGate } from '@/components/membership/MemberGate';

const Section = ({ title, children }: { title: string; children: ReactNode }) => (
  <div className="space-y-1">
    <h3 className="text-sm font-semibold text-gray-700">{title}</h3>
    <div className="space-y-1 text-xs">{children}</div>
  </div>
);

/** 信号证据内容: strength 月度 IC + 主题 ARCH 的 5 年样本外统计可视化 (非实时信号). */
const EvidenceContent = () => {
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
    <main className="flex flex-col gap-4 animate-crossfade">
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
            <strong>IC 量级解读</strong>：|IC| &lt; 0.05 弱、0.05–0.1 中、&gt; 0.1 强（业界经验量级）。
            本页月度 IC ≈ 0.054 属"弱但显著"——有 alpha 但不大，扣交易成本后更薄。
          </p>
          <p>
            <strong>ARCH（波动率聚集）</strong>：对收益率平方 r² 做 Ljung-Box 检验。显著 = r² 自相关 =
            高波动日后倾向延续高波动。这是 GARCH 类波动率模型的基础（GARCH 显式建模这种聚集）。
          </p>
        </Section>

        <Section title="使用方法（4 图怎么读）">
          <p>① <strong>IC 多窗口时序</strong>：5/20/60 三线。短窗口看拐点、长窗口看趋势；红虚线 = 60 日均值。点图例切换窗口。</p>
          <p>② <strong>IC vs 持有期</strong>：柱 = 全样本均值，竖线 = 历史 min-max 范围，红色顶标 = 最近 5 日实际。柱随 horizon 增 = 慢变量 alpha。</p>
          <p>③ <strong>ARCH 排序</strong>：红条 = r² 显著（波动聚集），越高越强。点 ? 看详情。</p>
          <p>④ <strong>r² ACF 衰减</strong>：全行业，默认显强/弱代表，点图例切换。缓降 = ARCH，速降 = 无记忆。</p>
          <p>
            <strong>常见误读</strong>：IC 显著 ≠ 高收益（排名相关，且扣成本后衰减）；ARCH 显著 ≠ 收益可预测
            （ARCH 是波动率聚集，对收益方向无预测力）。
          </p>
        </Section>

        <Section title="分析案例（5 年样本外实证）">
          <p>
            <strong>strength 月度 IC = 0.054（t=7.9）</strong>：弱但显著。<strong>为什么 123 日高估到 0.144</strong>：
            2026 H1 含 AI 趋势行情，趋势期 IC 被放大；5 年跨牛熊后回归 0.054。教训：短样本 IC 不可信，须多年验证。
          </p>
          <p>
            <strong>87% 主题有 ARCH（26/30）</strong>：波动聚集普遍，集中高贝塔（半导体/医疗/黄金）。日频收益白噪——
            收益 alpha 仅在月级 strength 趋势，不在日频择时或波动率方向。
          </p>
        </Section>
      </Modal>
    </main>
  );
};

/**
 * 信号证据页（会员功能）：登录 + 付费会员双层门控，通过后渲染 EvidenceContent。
 * 门控仅 UX 层；数据访问边界由后端强制。
 */
export const EvidencePage = () => (
  <div className="max-w-6xl mx-auto p-4">
    <AuthGate copy="evidence">
      <MemberGate copy="evidence">
        <EvidenceContent />
      </MemberGate>
    </AuthGate>
  </div>
);
