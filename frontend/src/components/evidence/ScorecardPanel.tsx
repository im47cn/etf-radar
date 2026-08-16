import type { ScorecardEntry } from '@/types/signalEvidence';
import { ChartCard, EmptyCard } from '@/components/ChartCard';

interface Props {
  entries: ScorecardEntry[];
}

const SIGNAL_LABEL: Record<string, string> = {
  resonance: '共振信号',
  transmission: '传导信号',
};

/** status 徽章: 颜色 + 中文标签 */
const STATUS_META: Record<string, { color: string; label: string }> = {
  consistent: { color: '#059669', label: '与长期一致' },   // 绿
  degraded: { color: '#d97706', label: '近期降效' },       // 黄/琥珀
  insufficient: { color: '#9ca3af', label: '样本不足' },    // 灰
};

export interface ScorecardRow {
  key: string;
  signal: string;
  tier: string | null;
  label: string;
  window: number | null;
  n: number;
  hitRate: number | null;
  ciLow: number | null;
  ciHigh: number | null;
  baseline: number | null;
  status: string;
}

/** 计分卡记录 → 展示行: 信号(resonance 前) → 档位(整体前, 高置信档后) → 窗口升序. 模块级纯函数便于直接测试. */
// eslint-disable-next-line react-refresh/only-export-components -- 纯函数导出仅为测试直调, 不影响 fast refresh
export function buildScorecardRows(entries: ScorecardEntry[]): ScorecardRow[] {
  const rows = entries.map((e, i) => {
    const signal = e.signal ?? '';
    const tier = e.tier ?? null;
    const window = e.window_days ?? null;
    const label = `${SIGNAL_LABEL[signal] ?? signal}${tier === 'high' ? ' · 高置信档' : ''}`;
    const n = e.n ?? 0;
    const hitRate = e.hit_rate ?? null;
    const ciLow = e.ci_low ?? null;
    const ciHigh = e.ci_high ?? null;
    const baseline = e.baseline ?? null;
    const status = e.status ?? 'insufficient';
    return {
      key: `${signal}-${tier ?? 'all'}-${window ?? '?'}-${i}`,
      signal, tier, label, window, n, hitRate, ciLow, ciHigh, baseline, status,
    };
  });
  const sigOrder = (s: string) => (s === 'resonance' ? 0 : 1);
  rows.sort(
    (a, b) =>
      sigOrder(a.signal) - sigOrder(b.signal) ||
      (a.tier === 'high' ? 1 : 0) - (b.tier === 'high' ? 1 : 0) ||
      (a.window ?? 0) - (b.window ?? 0),
  );
  return rows;
}

const fmtPct = (v: number | null) => (v == null ? '—' : `${(v * 100).toFixed(1)}%`);

/** 信号计分卡: resonance/transmission 近端滚动胜率 vs 5 年长期基线, 附 95% CI 与状态判定. */
export const ScorecardPanel = ({ entries }: Props) => {
  const rows = buildScorecardRows(entries);
  if (!rows.length) return <EmptyCard text="暂无信号计分卡数据" />;

  return (
    <ChartCard
      title="信号计分卡"
      subtitle="近 60/120 交易日事件胜率 vs 长期基线 · 次日 A 股 ETF 同向率"
      helpTitle="信号计分卡 · 读法"
      help={
        <>
          <p><strong>指标</strong>：信号日的<strong>主题动量方向</strong>（美股动量代理，theme r_1d 符号）vs <strong>次日 A 股 ETF 涨跌方向</strong>是否同向。长期基线为 5 年样本外点估计：共振 55%，高置信档（|动量|≥1%）57%，传导 49%≈随机（传导无方向语义，仅展示"≈随机"）。</p>
          <p><strong>状态判定</strong>：<span className="text-emerald-600">绿 = 与长期一致</span>（95% CI 含基线或更高），<span className="text-amber-600">黄 = 近期降效</span>（CI 上界低于基线），灰 = 样本不足（n&lt;50）。CI 为正态近似 95% 置信区间。</p>
          <p><strong>小样本警示</strong>：CI 含基线即视为一致；60 日窗口样本常 &lt;100，勿按单月表现判断信号死活——5 年回测里 150 日样本曾把 87% 的 ARCH 漏检成 13%。</p>
        </>
      }
    >
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-gray-200 text-left text-gray-500">
              <th className="py-1.5 pr-3 font-medium">信号</th>
              <th className="py-1.5 pr-3 font-medium">窗口</th>
              <th className="py-1.5 pr-3 font-medium">实际胜率 (95% CI)</th>
              <th className="py-1.5 pr-3 font-medium">基线</th>
              <th className="py-1.5 pr-3 font-medium">n</th>
              <th className="py-1.5 font-medium">状态</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const meta = STATUS_META[r.status] ?? STATUS_META.insufficient;
              return (
                <tr key={r.key} className="border-b border-gray-100 last:border-0">
                  <td className="py-1.5 pr-3 text-gray-700">{r.label}</td>
                  <td className="py-1.5 pr-3 text-gray-600">{r.window == null ? '—' : `${r.window}日`}</td>
                  <td className="py-1.5 pr-3 text-gray-800">
                    {fmtPct(r.hitRate)}
                    {r.ciLow != null && r.ciHigh != null && (
                      <span className="text-gray-400">
                        {' '}({fmtPct(r.ciLow)} ~ {fmtPct(r.ciHigh)})
                      </span>
                    )}
                  </td>
                  <td className="py-1.5 pr-3 text-gray-600">{fmtPct(r.baseline)}</td>
                  <td className="py-1.5 pr-3 text-gray-600">{r.n}</td>
                  <td className="py-1.5">
                    <span
                      className="inline-block rounded-full px-2 py-0.5 text-[10px] font-medium text-white"
                      style={{ backgroundColor: meta.color }}
                    >
                      {meta.label}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </ChartCard>
  );
};
